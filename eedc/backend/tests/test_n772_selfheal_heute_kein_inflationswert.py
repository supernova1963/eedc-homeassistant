"""N-772-Wächter — der laufende Tag im HA-Add-on mit Self-Healing aus der HA-Statistik trägt keinen Inflationswert.

Warum es diesen Wächter gibt: N-772 (3.11.2026) hat am Snapshot-Pfad die Sperre `datum < heute` entfernt (#290 Bug B).
Die Sperre schützte das alte Rand-Diff `snap[Folgetag 00:00] − snap[Tag 00:00]`, dessen Zukunfts-Rand das Self-Healing
(`snapshot/reader.get_snapshot`: DB → HA-Statistik → MQTT, mit Rückschreiben) mit dem AKTUELLEN Zählerstand füllte — der
laufende Tag wurde aufgeblasen. Seit E5 ist die Tagestabelle slot-basiert; die Nachmessung zu N-772 hat das #290-Szenario
nachgebaut (Messskript `plans/messung-triage-2026-11-03/probe_290_selfheal_heute.py`), und diese Datei hält es in der Suite
fest. Ohne sie prüfte niemand den Angriff: `test_n772_laufender_tag_zaehler_delta.py` heilt aus MQTT, nicht aus HA, und die
gedrehten #290-Proben (`test_aggregator_290_preserve.py`) halten nur das neue Verhalten fest.

Konstellation (Add-on-Zuordnung): WP-Stromzähler UND WP-Leistung als HA-Sensoren, keine LTS-Stunden für heute
(`lts_tagestabelle` → None), die Zählerstände an den Rändern heilt der Reader aus der gestellten HA-Statistik. Zwei Leser:
  * realistisch — `get_value_at` kennt nur Stände bis zur letzten abgeschlossenen Stunde (Hourly-Zeile ≈ 12 min nach voller
    Stunde), ein Zukunfts-Rand bleibt ohne Stand;
  * pathologisch (#290-Verdacht, obere Schranke) — liefert für JEDEN Zeitpunkt, auch in der Zukunft, den aktuellen Stand.
Zugesichert wird in beiden Fällen: Tageswert == Σ der Stunden derselben Tabelle, Tageswert ≤ Zähler-Delta bis jetzt, kein
geheilter Rand über dem aktuellen Stand. Beim realistischen Leser zusätzlich: Tageswert = Delta der abgelaufenen Stunden,
kein Snapshot in der Zukunft. Die Achse-2-Drift-Warnung (Zähler 24 h gegen Leistung nur 10–12 Uhr, synthetisch) ist in dieser
Konstellation vorbestehend und wird nicht geprüft.

Uhr: `aggregator.date.today()` und `ltv.datetime.now()` sind auf TAG 12:30 gestellt (Muster der Schwesterdatei).
Schwesterdatei: test_n772_laufender_tag_zaehler_delta.py (MQTT-Zähler, Standalone), test_aggregator_290_preserve.py.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import select

from backend.models.mqtt_live_snapshot import MqttLiveSnapshot
from backend.models.sensor_snapshot import SensorSnapshot
from backend.models.tages_energie_profil import TagesEnergieProfil
from backend.services import live_tagesverlauf_service as ltv
from backend.services.energie_profil.source import Source
from backend.tests import factories

TAG = date(2026, 9, 4)
JETZT = datetime(2026, 9, 4, 12, 30)
#: kWh je Stunde des WP-Stromzählers — von 00:00 bis 12:00 genau 2,75 kWh (die Lab-Größe aus N-772).
RATE = 2.75 / 12.0
BASIS = 12345.0


def _stand(t: datetime) -> float:
    return round(BASIS + RATE * (t - datetime.combine(TAG, datetime.min.time())).total_seconds() / 3600, 4)


class _HaStatistik:
    """Gestellter HA-Statistik-Dienst an der Naht `reader.get_ha_statistics_service`."""

    def __init__(self, pathologisch: bool):
        self.pathologisch = pathologisch
        self.is_available = True
        self.anfragen: list[datetime] = []

    def get_value_at(self, sensor_id, zeitpunkt, toleranz_minuten=10, short_term=False, als_stand=False):
        self.anfragen.append(zeitpunkt)
        if self.pathologisch:
            return _stand(min(zeitpunkt, JETZT))   # «HA liefert den aktuellen Stand» — auch für die Zukunft
        if zeitpunkt + timedelta(minutes=12) <= JETZT:   # Hourly-Zeile erst nach Abschluss der Stunde
            return _stand(zeitpunkt)
        return None


def _stelle_naehte(monkeypatch, ha: _HaStatistik) -> None:
    from backend.services import strompreis_markt_service as sms
    from backend.services.energie_profil import _helpers, aggregator
    from backend.services.snapshot import lts_aggregator, reader

    class _Heute(date):
        @classmethod
        def today(cls):
            return TAG

    class _Uhr(datetime):
        @classmethod
        def now(cls, tz=None):
            return JETZT if tz is None else JETZT.astimezone(tz)

    async def keine_preise(land, tag):
        return {}

    async def kein_lts(*a, **k):
        return None

    beginn = datetime.combine(TAG, datetime.min.time())

    async def history(ids, start, end):
        reihe = []
        t = max(start, beginn + timedelta(hours=10))
        while t <= min(end, beginn + timedelta(hours=12), JETZT):
            reihe.append((t, 1000.0))
            t += timedelta(minutes=5)
        return ({i: reihe for i in ids if i == "sensor.wp_w"}, {i: "W" for i in ids if i == "sensor.wp_w"})

    monkeypatch.setattr(aggregator, "date", _Heute)
    monkeypatch.setattr(ltv, "datetime", _Uhr)
    monkeypatch.setattr(_helpers, "_tage_zurueck", lambda tag: (TAG - tag).days)
    monkeypatch.setattr(sms, "get_strompreis_stunden", keine_preise)
    monkeypatch.setattr(lts_aggregator, "lts_tagestabelle", kein_lts)
    monkeypatch.setattr(reader, "get_ha_statistics_service", lambda: ha)
    monkeypatch.setattr(ltv, "get_history_normalized", history)


async def _ha_wp_anlage(db, name: str):
    """Add-on-Zuordnung: kWh-Zähler und Leistung der WP als HA-Sensoren; Leistungskurve 1000 W 10:00–12:00 (Riemann 2,0 kWh)."""
    a = await factories.anlage(db, anlagenname=name, leistung_kwp=8.0, sensor_mapping={})
    wp = await factories.investition(db, a.id, "waermepumpe", bezeichnung="WP", anschaffungsdatum=date(2020, 1, 1))
    a.sensor_mapping = {"investitionen": {str(wp.id): {
        "felder": {"stromverbrauch_kwh": {"strategie": "sensor", "sensor_id": "sensor.wp_kwh"}},
        "live": {"leistung_w": "sensor.wp_w"}}},
        "quellen": {f"inv_live_{wp.id}_leistung_w": {"quelle": "mqtt_inbound_standard"}}}
    await db.commit()
    beginn = datetime.combine(TAG, datetime.min.time())
    for i in range(24):
        ts = beginn + timedelta(hours=10, minutes=5 * i)
        db.add(MqttLiveSnapshot(anlage_id=a.id, timestamp=ts, component_key=f"inv:{wp.id}:leistung_w",
                                value_w=1000.0, ts_unix=int(ts.timestamp())))
    await db.commit()
    return a, wp


async def _lauf(db, monkeypatch, pathologisch: bool):
    from backend.services.energie_profil.aggregator import aggregate_day

    ha = _HaStatistik(pathologisch)
    _stelle_naehte(monkeypatch, ha)
    a, wp = await _ha_wp_anlage(db, f"N772-SELFHEAL-{int(pathologisch)}")
    tz = await aggregate_day(a, TAG, db, source=Source.SCHEDULER)
    assert tz is not None
    wert = tz.komponenten_kwh[f"waermepumpe_{wp.id}"]
    zeilen = (await db.execute(select(TagesEnergieProfil).where(TagesEnergieProfil.anlage_id == a.id))).scalars().all()
    stunden = {z.stunde: z.waermepumpe_kw for z in zeilen if z.waermepumpe_kw is not None}
    snaps = (await db.execute(select(SensorSnapshot.zeitpunkt, SensorSnapshot.wert_kwh)
                              .where(SensorSnapshot.anlage_id == a.id).order_by(SensorSnapshot.zeitpunkt))).all()
    zukunft = [(z, w) for z, w in snaps if z > JETZT]
    # Die drei Zusicherungen beider Leser:
    assert wert > 0, f"Zählerpfad (positiv), nicht die Senke der Kurve: {wert}"
    assert wert == pytest.approx(sum(stunden.values()), abs=0.01), "Tag == Σ der Stunden derselben Tabelle"
    assert wert <= RATE * 13.5 + 0.01, f"kein Inflationswert über dem Zähler-Delta bis jetzt (12:30): {wert}"
    assert all(w <= _stand(JETZT) for _, w in zukunft), "kein geheilter Zukunfts-Rand über dem aktuellen Stand"
    return wert, stunden, zukunft


@pytest.mark.asyncio
async def test_realistischer_ha_leser_traegt_delta_der_abgelaufenen_stunden(db, monkeypatch):
    """HA kennt nur abgeschlossene Stunden ⇒ Tageswert = Delta [Vortag 23:00, 12:00] = 13 Slots à RATE, kein Zukunfts-Snapshot."""
    wert, stunden, zukunft = await _lauf(db, monkeypatch, pathologisch=False)
    assert wert == pytest.approx(RATE * 13, abs=0.01), "Zähler-Delta der abgelaufenen Stunden, nicht Riemann-Σ 2,0"
    assert max(stunden) <= 13, "keine Menge nach der laufenden Stunde"
    assert zukunft == [], "ein Rand ohne Stand wird nicht geheilt"


@pytest.mark.asyncio
async def test_pathologischer_ha_leser_blaest_den_tag_nicht_auf(db, monkeypatch):
    """#290-Verdacht als obere Schranke: HA liefert für jeden Rand den aktuellen Stand ⇒ der Tag bleibt beim Zähler-Delta bis
    jetzt (Slot 13 trägt die halbe Stunde, spätere Slots 0); geheilte Zukunfts-Ränder tragen höchstens den aktuellen Stand."""
    wert, stunden, zukunft = await _lauf(db, monkeypatch, pathologisch=True)
    assert wert == pytest.approx(RATE * 13.5, abs=0.01), "genau das Delta bis 12:30, nichts darüber"
    # Slot 13 = 12:00 → 13:00, sein rechter Rand ist geheilt mit dem Stand von 12:30 ⇒ genau die halbe Stunde.
    assert stunden[13] == pytest.approx(RATE * 0.5, abs=0.01), "laufende Stunde trägt nur das Delta bis jetzt"
    assert all(v == pytest.approx(0.0, abs=1e-6) for h, v in stunden.items() if h > 13), "Zukunfts-Slots ohne Menge"
    assert len(zukunft) == 11 and all(w == _stand(JETZT) for _, w in zukunft), "geheilte Ränder 13:00–23:00 = Stand 12:30"
