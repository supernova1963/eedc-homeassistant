"""Monatsabschluss: kWp-verteilte Connector-Werte heißen nicht mehr „gemessen" (A3/a2).

Ein Connector liefert EINEN PV-Zählerstand. Bei mehreren Modulen wurde der
Monatsdifferenz-Wert nach `leistung_kwp` zerlegt und trotzdem als „Vom
Wechselrichter (Zählerstand-Differenz)" mit Konfidenz 90 — also auf Augenhöhe
mit HA-Statistik (92) und MQTT (91) — angeboten. Der Vorschlag ist an dieser
Stelle aber keine Messung des Moduls, sondern ein Modell.

Bei genau EINEM Modul geht der Zählerstand unzerlegt dorthin: dann bleibt es
eine Messung und Text/Konfidenz bleiben unverändert.
"""

from __future__ import annotations

from datetime import date

from backend.api.routes.monatsabschluss.views import (
    KONFIDENZ_CONNECTOR_GEMESSEN,
    KONFIDENZ_CONNECTOR_VERTEILT,
    get_monatsabschluss,
)
from backend.models import Anlage, Investition


SNAPSHOTS = {
    "2025-05-31T23:00:00": {"pv_erzeugung_kwh": 10_000.0},
    "2025-06-30T23:00:00": {"pv_erzeugung_kwh": 12_000.0},  # Δ = 2000 kWh
}


async def _seed(db, *, anzahl_module: int) -> int:
    anlage = Anlage(
        anlagenname="Connector-Test", leistung_kwp=20.0,
        standort_plz="10115", latitude=48.0, longitude=11.0,
        connector_config={"connector_id": "fronius", "meter_snapshots": SNAPSHOTS},
    )
    db.add(anlage)
    await db.flush()
    kwps = [12.0, 5.0, 3.0][:anzahl_module]
    for i, kwp in enumerate(kwps, start=1):
        db.add(Investition(
            anlage_id=anlage.id, typ="pv-module", bezeichnung=f"Dach {i}",
            anschaffungsdatum=date(2024, 1, 1), leistung_kwp=kwp,
            anschaffungskosten_gesamt=1000.0 * kwp,
        ))
    await db.flush()
    return anlage.id


async def _connector_vorschlaege(db, anlage_id: int) -> list:
    resp = await get_monatsabschluss(anlage_id, 2025, 6, db=db)
    treffer = []
    for inv in resp.investitionen:
        for feld in inv.felder:
            if feld.feld != "pv_erzeugung_kwh":
                continue
            treffer += [
                (inv.bezeichnung, v) for v in feld.vorschlaege
                if v.quelle == "local_connector"
            ]
    return treffer


async def test_verteilter_connector_wert_ist_als_verteilt_beschriftet(db):
    anlage_id = await _seed(db, anzahl_module=3)
    treffer = await _connector_vorschlaege(db, anlage_id)
    assert len(treffer) == 3, "je Modul ein Connector-Vorschlag erwartet"
    for bezeichnung, v in treffer:
        assert "anteilig nach kWp" in v.beschreibung, bezeichnung
        assert "Pro-String-Genauigkeit eingeschränkt" in v.beschreibung, bezeichnung
        assert v.konfidenz == KONFIDENZ_CONNECTOR_VERTEILT
    # Σ der Vorschläge bleibt die gemessene Monatsdifferenz (2000 kWh).
    assert sum(v.wert for _, v in treffer) == 2000.0
    # 12/5/3 kWp → 1200/500/300
    assert sorted(v.wert for _, v in treffer) == [300.0, 500.0, 1200.0]


async def test_konfidenz_liegt_unter_jeder_gemessenen_quelle(db):
    """HA-Statistik 92 · MQTT-Inbound 91 · Connector-Zählerstand 90."""
    assert KONFIDENZ_CONNECTOR_VERTEILT < KONFIDENZ_CONNECTOR_GEMESSEN == 90
    assert KONFIDENZ_CONNECTOR_VERTEILT < 91  # MQTT_INBOUND
    assert KONFIDENZ_CONNECTOR_VERTEILT < 92  # HA_STATISTICS
    assert KONFIDENZ_CONNECTOR_VERTEILT > 80  # Vormonat — Σ + Monat sind gemessen


async def test_einzelmodul_bleibt_gemessen_beschriftet(db):
    """Ein Modul = nichts zu verteilen; Text und Konfidenz unverändert."""
    anlage_id = await _seed(db, anzahl_module=1)
    treffer = await _connector_vorschlaege(db, anlage_id)
    assert len(treffer) == 1
    _, v = treffer[0]
    assert v.beschreibung == "Vom Wechselrichter (Zählerstand-Differenz)"
    assert v.konfidenz == KONFIDENZ_CONNECTOR_GEMESSEN
    assert v.wert == 2000.0
