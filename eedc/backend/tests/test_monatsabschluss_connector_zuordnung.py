"""Monatsabschluss: die Feld→Investition-Zuordnung schlägt die kWp-Verteilung (A13, #352).

`_mapped_or_distribute` (api/routes/connector.py) ist die Zuordnungs-SoT: ist
eine Kategorie („pv", „speicher") in `connector_config["field_inv_map"]` einer
Investition zugeordnet, geht der Zählerstand ganz dorthin — sonst greift die
proportionale kWp-/Kapazitäts-Verteilung. Die Connector-Vorschau und die
MQTT-Energie-Bridge nutzen sie seit jeher; der Monatsabschluss rief
`_distribute_by_param` direkt auf und hat die Zuordnung damit übergangen.

Folge: Wer seinen Wechselrichter-Sensor einem Modul zugeordnet hatte, bekam
trotzdem einen nach Nennleistung zerlegten Vorschlag — und damit einen
gerechneten Wert dort, wo eine Messung vorliegt.
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
    "2025-05-31T23:00:00": {"pv_erzeugung_kwh": 10_000.0, "batterie_ladung_kwh": 1_000.0},
    "2025-06-30T23:00:00": {"pv_erzeugung_kwh": 12_000.0, "batterie_ladung_kwh": 1_600.0},
}


async def _seed(db, *, mit_zuordnung: bool) -> tuple[int, dict[str, int]]:
    anlage = Anlage(
        anlagenname="Zuordnungs-Test", leistung_kwp=17.0,
        standort_plz="10115", latitude=48.0, longitude=11.0,
        connector_config={"connector_id": "fronius", "meter_snapshots": SNAPSHOTS},
    )
    db.add(anlage)
    await db.flush()

    ids: dict[str, int] = {}
    for bez, kwp in (("Dach Süd", 12.0), ("Dach Nord", 5.0)):
        inv = Investition(
            anlage_id=anlage.id, typ="pv-module", bezeichnung=bez,
            anschaffungsdatum=date(2024, 1, 1), leistung_kwp=kwp,
            anschaffungskosten_gesamt=1000.0 * kwp,
        )
        db.add(inv)
        await db.flush()
        ids[bez] = inv.id

    if mit_zuordnung:
        cfg = dict(anlage.connector_config)
        cfg["field_inv_map"] = {"pv": ids["Dach Süd"]}
        anlage.connector_config = cfg
    await db.flush()
    return anlage.id, ids


async def _pv_vorschlaege(db, anlage_id: int) -> dict[str, list]:
    resp = await get_monatsabschluss(anlage_id, 2025, 6, db=db)
    treffer: dict[str, list] = {}
    for inv in resp.investitionen:
        for feld in inv.felder:
            if feld.feld != "pv_erzeugung_kwh":
                continue
            treffer[inv.bezeichnung] = [
                v for v in feld.vorschlaege if v.quelle == "local_connector"
            ]
    return treffer


async def test_zugeordnetes_modul_bekommt_den_gemessenen_wert(db):
    """Zuordnung „pv" → Dach Süd: voller Zählerstand, Mess-Beschriftung, Konfidenz 90."""
    anlage_id, _ = await _seed(db, mit_zuordnung=True)
    treffer = await _pv_vorschlaege(db, anlage_id)

    assert len(treffer["Dach Süd"]) == 1
    v = treffer["Dach Süd"][0]
    assert v.wert == 2000.0, "Zuordnung ⇒ die volle Zählerstand-Differenz, nicht 1200 kWh"
    assert v.beschreibung == "Vom Wechselrichter (Zählerstand-Differenz)"
    assert v.konfidenz == KONFIDENZ_CONNECTOR_GEMESSEN


async def test_nicht_zugeordnetes_modul_bekommt_keinen_connector_vorschlag(db):
    """Der Zählerstand ist bereits vollständig vergeben — ein zweiter Anteil wäre Doppelzählung."""
    anlage_id, _ = await _seed(db, mit_zuordnung=True)
    treffer = await _pv_vorschlaege(db, anlage_id)
    assert treffer["Dach Nord"] == [], (
        "Bei expliziter Zuordnung darf kein weiteres Modul einen Anteil desselben "
        "Zählerstands vorgeschlagen bekommen (Σ wäre > gemessene Differenz)."
    )


async def test_ohne_zuordnung_bleibt_die_verteilung_mit_ihrer_beschriftung(db):
    """Die Ehrlichkeit aus A3/a2 bleibt: ohne Zuordnung verteilt und als solches etikettiert."""
    anlage_id, _ = await _seed(db, mit_zuordnung=False)
    treffer = await _pv_vorschlaege(db, anlage_id)

    werte = {bez: vs[0].wert for bez, vs in treffer.items()}
    assert werte == {"Dach Süd": 1411.8, "Dach Nord": 588.2}  # 12/5 von 17 kWp
    assert round(sum(werte.values())) == 2000
    for bez, vs in treffer.items():
        assert "anteilig nach kWp" in vs[0].beschreibung, bez
        assert vs[0].konfidenz == KONFIDENZ_CONNECTOR_VERTEILT, bez
