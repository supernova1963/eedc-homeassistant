"""N-772 — der laufende Tag ohne HA-Langzeitstatistik trägt das Zähler-Delta, nicht die Live-Σ der Kurve.

Fall (Lab 26.10.2026, Standalone-S4-Nachmessung, Halt M-3): eine Anlage ohne HA-LTS (Standalone, reine MQTT, Mischform)
hat für die Wärmepumpe einen kWh-Zähler über MQTT und eine Leistungskurve. Bis v4.2.1 lieferte der Snapshot-Pfad am
laufenden Tag keinen Tageswert (`komponenten_tagesgesamt_und_peaks`, an `datum < today` gekoppelt) — `komponenten_kwh`
war die Riemann-Summe der Kurve, für die Wärmepumpe mit negativem Vorzeichen (Senke), und der laufende Monat zeigte
für heute den Integralwert (Lab: 2,0 statt 2,75 kWh). Am Folgetag schrieb der Snapshot-Pfad den Zählerwert.

Diese Probe läuft durch den echten Schreibpfad (`aggregate_day`) mit echter Snapshot-Tabelle (MqttEnergySnapshot) —
kein Mock der Tagestabelle. Uhr: der Aggregator liest `date.today()` über `aggregator.date`, der Tagesverlauf
`datetime.now()` über `ltv.datetime`; beide werden in der Testfunktion auf TAG 12:30 gestellt.
Schwesterdatei: test_standalone_s4_mischform.py (M-3, gestellte Tagestabelle).
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import select

from backend.models.mqtt_energy_snapshot import MqttEnergySnapshot
from backend.models.mqtt_live_snapshot import MqttLiveSnapshot
from backend.models.tages_energie_profil import TagesEnergieProfil
from backend.services import live_tagesverlauf_service as ltv
from backend.services.energie_profil.source import Source
from backend.tests import factories

TAG = date(2026, 9, 4)
#: kWh je Stunde des WP-Stromzählers — von 00:00 bis 12:00 genau 2,75 kWh (die Lab-Größe).
RATE = 2.75 / 12.0


def _uhr_klasse(jetzt: datetime):
    class _Uhr(datetime):
        @classmethod
        def now(cls, tz=None):
            return jetzt if tz is None else jetzt.astimezone(tz)
    return _Uhr


def _stelle_uhr(monkeypatch, heute: date, jetzt: datetime) -> None:
    from backend.services import strompreis_markt_service as sms
    from backend.services.energie_profil import _helpers, aggregator

    class _Heute(date):
        @classmethod
        def today(cls):
            return heute

    async def keine_preise(land, tag):
        return {}

    monkeypatch.setattr(aggregator, "date", _Heute)
    monkeypatch.setattr(ltv, "datetime", _uhr_klasse(jetzt))
    monkeypatch.setattr(_helpers, "_tage_zurueck", lambda tag: (heute - tag).days)
    monkeypatch.setattr(sms, "get_strompreis_stunden", keine_preise)


async def _mqtt_wp_anlage(db, jetzt: datetime):
    """WP-Stromzähler über MQTT (alle 5 min ab Vortag 23:00 bis `jetzt`) und WP-Leistung 1000 W 10:00–12:00."""
    a = await factories.anlage(db, anlagenname="N772", leistung_kwp=8.0, sensor_mapping={})
    wp = await factories.investition(db, a.id, "waermepumpe", bezeichnung="WP", anschaffungsdatum=date(2020, 1, 1))
    a.sensor_mapping = {"quellen": {f"inv_live_{wp.id}_leistung_w": {"quelle": "mqtt_inbound_standard"},
                                    f"inv_energy_{wp.id}_stromverbrauch_kwh": {"quelle": "mqtt_inbound_standard"}}}
    beginn = datetime.combine(TAG, datetime.min.time())
    t = beginn - timedelta(hours=1)
    while t <= jetzt:
        stunden = (t - beginn).total_seconds() / 3600
        db.add(MqttEnergySnapshot(anlage_id=a.id, energy_key=f"inv/{wp.id}/stromverbrauch_kwh",
                                  value_kwh=round(12345.0 + RATE * stunden, 4), timestamp=t))
        t += timedelta(minutes=5)
    for i in range(24):
        ts = beginn + timedelta(hours=10, minutes=5 * i)
        db.add(MqttLiveSnapshot(anlage_id=a.id, timestamp=ts, component_key=f"inv:{wp.id}:leistung_w",
                                value_w=1000.0, ts_unix=int(ts.timestamp())))
    await db.commit()
    return a, wp


def _drift_logs(caplog) -> list[str]:
    return [r.getMessage() for r in caplog.records if "Drift" in r.getMessage()]


@pytest.mark.asyncio
async def test_laufender_tag_ohne_lts_traegt_zaehler_delta_mit_positivem_vorzeichen(db, monkeypatch, caplog):
    """Heute, kein LTS, Snapshots vorhanden ⇒ `komponenten_kwh[WP]` = Zähler-Delta der abgelaufenen Stunden (positiv),
    nicht die Riemann-Σ der Kurve (−2,0); die Komponenten-Invariante schweigt."""
    from backend.services.energie_profil.aggregator import aggregate_day

    jetzt = datetime.combine(TAG, datetime.min.time()) + timedelta(hours=12, minutes=30)
    _stelle_uhr(monkeypatch, TAG, jetzt)
    a, wp = await _mqtt_wp_anlage(db, jetzt)

    with caplog.at_level(logging.WARNING):
        tz = await aggregate_day(a, TAG, db, source=Source.SCHEDULER)

    wert = tz.komponenten_kwh[f"waermepumpe_{wp.id}"]
    assert wert > 0, f"Vorzeichen des Zählerpfads (positiv), nicht der Senke der Kurve: {wert}"
    # Stundenfenster [Vortag 23:00, 12:00]: 13 abgelaufene Slots à RATE (Slot 0 = Vortag 23:00 → 00:00).
    assert wert == pytest.approx(RATE * 13, abs=0.01), "Zähler-Delta, nicht Riemann-Σ 2,0"
    # Kein Zukunfts-Rand im Tageswert (#290 Bug B): Tag == Σ der geschriebenen Stunden derselben Tabelle.
    zeilen = (await db.execute(select(TagesEnergieProfil).where(TagesEnergieProfil.anlage_id == a.id))).scalars().all()
    assert sum(z.waermepumpe_kw or 0 for z in zeilen) == pytest.approx(wert, abs=0.01)
    assert max(z.stunde for z in zeilen if z.waermepumpe_kw) <= 13, "keine Menge nach der laufenden Stunde"
    assert _drift_logs(caplog) == []


@pytest.mark.asyncio
async def test_vergangener_tag_unveraendert_zaehler_delta(db, monkeypatch, caplog):
    """Gegenprobe: derselbe Tag am Folgetag gelesen (bisheriger Weg) — derselbe Zählerwert der vorhandenen Stunden."""
    from backend.services.energie_profil.aggregator import aggregate_day

    jetzt = datetime.combine(TAG, datetime.min.time()) + timedelta(hours=12, minutes=30)
    _stelle_uhr(monkeypatch, TAG + timedelta(days=1), jetzt + timedelta(days=1))
    a, wp = await _mqtt_wp_anlage(db, jetzt)

    with caplog.at_level(logging.WARNING):
        tz = await aggregate_day(a, TAG, db, source=Source.SCHEDULER)

    assert tz.komponenten_kwh[f"waermepumpe_{wp.id}"] == pytest.approx(RATE * 13, abs=0.01)
