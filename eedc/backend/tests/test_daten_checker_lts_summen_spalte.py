"""
Akzeptanztest: „in der Statistik vorhanden" reicht für einen Zähler nicht.

Ein Sensor mit `state_class: measurement` steht in HA's `statistics_meta`
(HA führt für ihn Mittel-/Min-/Max-Werte), hat aber **keine Summen-Spalte**.
`get_hourly_kwh_deltas_for_day` überspringt dann jede Zeile dieses Sensors — er
fehlt im Ergebnis, Cockpit → Tag und die Stundenwerte bleiben auf 0. Der
LTS-Check fragte bis 2026-07-29 nur die **Existenz** ab und meldete deshalb
„alle kWh-Sensoren verfügbar", während die Auswertung leer blieb.

Gemeldet als Forum simon42 #89667/44 (pipp086): Live-Ansicht mit Werten, Tag
auf 0, Daten-Checker grün. Betroffene Gerätefamilie: bitShake/Tasmota, deren
Auto-Discovery gar kein `state_class` setzt (HA-Core #104305) — die Anwender
tragen es von Hand nach, und `measurement` statt `total_increasing` ist der
bekannte Griff daneben.

Die Live-Ansicht ist NICHT betroffen: sie rechnet aus den Watt-Sensoren. Genau
diese Spreizung macht den Fall von außen unsichtbar.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.models import Anlage, Investition  # noqa: F401
from backend.services.daten_checker import CheckSeverity


class _FakeHaStats:
    """HA-LTS-Doppel mit drei Zuständen je Sensor."""

    is_available = True

    def __init__(self, fehlend: set[str] | None = None, ohne_sum: set[str] | None = None):
        self._fehlend = fehlend or set()
        self._ohne_sum = ohne_sum or set()

    def filter_summen_faehige_sensor_ids(self, sids):
        mit_sum = [s for s in sids if s not in self._fehlend and s not in self._ohne_sum]
        ohne_sum = [s for s in sids if s in self._ohne_sum]
        fehlend = [s for s in sids if s in self._fehlend]
        return mit_sum, ohne_sum, fehlend


async def _seed(db: AsyncSession, *, mit_counter: bool = False) -> Anlage:
    anlage = Anlage(anlagenname="Test", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    db.add(Investition(
        anlage_id=anlage.id, typ="waermepumpe" if mit_counter else "pv-module",
        bezeichnung="WP" if mit_counter else "WR Süd",
        leistung_kwp=10.0, anschaffungsdatum=date(2024, 1, 1), aktiv=True,
    ))
    await db.flush()
    inv_id = (await db.execute(select(Investition))).scalars().first().id
    felder = (
        {"wp_starts_anzahl": {"strategie": "sensor", "sensor_id": "sensor.wp_starts"}}
        if mit_counter else
        {"pv_erzeugung_kwh": {"strategie": "sensor", "sensor_id": "sensor.pv"}}
    )
    anlage.sensor_mapping = {
        "basis": {
            "einspeisung": {"strategie": "sensor", "sensor_id": "sensor.e_out"},
            "netzbezug": {"strategie": "sensor", "sensor_id": "sensor.e_in"},
        },
        "investitionen": {str(inv_id): {"felder": felder}},
    }
    await db.commit()
    return (await db.execute(
        select(Anlage).options(selectinload(Anlage.investitionen)).where(Anlage.id == anlage.id)
    )).scalar_one()


def _patch(monkeypatch, fake):
    import backend.services.ha_statistics_service as ha_mod
    monkeypatch.setattr(ha_mod, "get_ha_statistics_service", lambda: fake)


async def test_zaehler_ohne_summen_spalte_wird_gemeldet(db, monkeypatch):
    """Der gemeldete Fall: Sensor da, aber ohne `sum` → WARNING statt OK."""
    from backend.services.daten_checker import DatenChecker

    anlage = await _seed(db)
    _patch(monkeypatch, _FakeHaStats(ohne_sum={"sensor.e_out", "sensor.e_in"}))

    ergebnisse = await DatenChecker(db)._check_sensor_mapping_lts(anlage)

    warnungen = [r for r in ergebnisse if r.schwere == CheckSeverity.WARNING]
    assert len(warnungen) == 1, [r.meldung for r in ergebnisse]
    assert "Summen-Spalte" in warnungen[0].meldung
    details = warnungen[0].details or ""
    # Beide Zähler beim Namen, mit Label statt Roh-Key.
    assert "sensor.e_out" in details and "sensor.e_in" in details
    assert "Basis: Einspeisung" in details and "Basis: Netzbezug" in details
    # Die Lösung steht dabei — und die ehrliche Einordnung der Live-Ansicht.
    assert "total_increasing" in details
    assert "Live" in details
    # Kein irreführendes OK daneben.
    assert not [r for r in ergebnisse if r.schwere == CheckSeverity.OK]


async def test_summenfaehige_zaehler_bleiben_ok(db, monkeypatch):
    """Gegenprobe: mit Summen-Spalte bleibt es bei genau einer OK-Meldung."""
    from backend.services.daten_checker import DatenChecker

    anlage = await _seed(db)
    _patch(monkeypatch, _FakeHaStats())

    ergebnisse = await DatenChecker(db)._check_sensor_mapping_lts(anlage)

    assert [r.schwere for r in ergebnisse] == [CheckSeverity.OK]
    assert "verfügbar" in ergebnisse[0].meldung


async def test_fehlender_sensor_meldet_weiter_die_alte_ursache(db, monkeypatch):
    """Regressionsschutz: „gar nicht in der Statistik" behält seinen eigenen
    Text (fehlendes `state_class`) — die zwei Ursachen dürfen nicht
    verschmelzen, sie brauchen verschiedene Handgriffe."""
    from backend.services.daten_checker import DatenChecker

    anlage = await _seed(db)
    _patch(monkeypatch, _FakeHaStats(fehlend={"sensor.e_out"}))

    ergebnisse = await DatenChecker(db)._check_sensor_mapping_lts(anlage)

    warnungen = [r for r in ergebnisse if r.schwere == CheckSeverity.WARNING]
    assert len(warnungen) == 1
    assert "nicht in HA-Long-Term-Statistics" in warnungen[0].meldung
    assert "Summen-Spalte" not in warnungen[0].meldung


async def test_counter_ohne_summen_spalte_eigene_meldung(db, monkeypatch):
    """WP-Counter laufen ohne `sum` weiter (Snapshot-Service), aber die
    Korrektur-Werkzeuge greifen nicht — eigener Text, eigene Erwartung."""
    from backend.services.daten_checker import DatenChecker

    anlage = await _seed(db, mit_counter=True)
    _patch(monkeypatch, _FakeHaStats(ohne_sum={"sensor.wp_starts"}))

    ergebnisse = await DatenChecker(db)._check_sensor_mapping_lts(anlage)

    counter_warnung = [
        r for r in ergebnisse
        if r.schwere == CheckSeverity.WARNING and "Counter-Sensor" in r.meldung
    ]
    assert len(counter_warnung) == 1, [r.meldung for r in ergebnisse]
    assert "Summen-Spalte" in counter_warnung[0].meldung
    assert "Korrektur-Werkzeuge" in counter_warnung[0].meldung
    # Die kWh-Zähler dieser Anlage sind in Ordnung → OK-Meldung bleibt.
    assert [r for r in ergebnisse if r.schwere == CheckSeverity.OK]
