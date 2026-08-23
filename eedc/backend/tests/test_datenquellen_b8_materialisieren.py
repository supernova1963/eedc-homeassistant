"""
Datenquellen-V4 B8 — Materialisierung der effektiven Quelle je Feld.

Deckt die Kern-Entscheidung (`_ha_entity_fuer_feld`) und den End-to-End-Lauf
gegen eine echte Anlage/Investition ab: HA-first, Gateway, konservativ Inbound,
Respekt vor bestehenden expliziten Einträgen (additiv/idempotent), §2h-Gateway-
Deaktivierung.
"""


import pytest
from sqlalchemy import select

from backend.models.anlage import Anlage
from backend.models.mqtt_gateway_mapping import MqttGatewayMapping
from backend.services.migrations.migrate_datenquellen_materialisieren import (
    _ha_entity_fuer_feld,
    _topic_suffix,
    materialisiere_datenquellen,
)
from backend.tests import factories


# ─── _ha_entity_fuer_feld (pur) ──────────────────────────────────────────

_MAPPING = {
    "basis": {
        "einspeisung": {"strategie": "sensor", "sensor_id": "sensor.einsp"},
        "netzbezug": {"strategie": "manuell"},  # kein Sensor
        "live": {"einspeisung_w": "sensor.einsp_w"},
    },
    "investitionen": {
        "2": {
            "felder": {
                "pv_erzeugung_kwh": {"strategie": "sensor", "sensor_id": "sensor.pv"},
                "ladevorgaenge": {"strategie": "sensor", "sensor_id": "sensor.lv"},  # nicht-kumulativ
            },
            "live": {"leistung_w": "sensor.pv_w", "soc": "sensor.soc"},
        },
    },
}


def test_ha_entity_live_und_energie():
    m, bl, il = _MAPPING, _MAPPING["basis"]["live"], {"2": _MAPPING["investitionen"]["2"]["live"]}
    # Basis live
    assert _ha_entity_fuer_feld("basis_live_einspeisung_w", m, bl, il) == "sensor.einsp_w"
    assert _ha_entity_fuer_feld("basis_live_netzbezug_w", m, bl, il) is None
    # Basis energy (Key-Normalisierung einspeisung_kwh → basis["einspeisung"])
    assert _ha_entity_fuer_feld("basis_energy_einspeisung_kwh", m, bl, il) == "sensor.einsp"
    assert _ha_entity_fuer_feld("basis_energy_netzbezug_kwh", m, bl, il) is None  # manuell
    assert _ha_entity_fuer_feld("basis_energy_pv_gesamt_kwh", m, bl, il) is None  # kein Basis-Counter
    # Inv live
    assert _ha_entity_fuer_feld("inv_live_2_leistung_w", m, bl, il) == "sensor.pv_w"
    assert _ha_entity_fuer_feld("inv_live_2_soc", m, bl, il) == "sensor.soc"
    # Inv energy + NICHT-kumulatives Feld (ladevorgaenge) direkt aus felder gelesen
    assert _ha_entity_fuer_feld("inv_energy_2_pv_erzeugung_kwh", m, bl, il) == "sensor.pv"
    assert _ha_entity_fuer_feld("inv_energy_2_ladevorgaenge", m, bl, il) == "sensor.lv"
    # Unbekanntes Feld
    assert _ha_entity_fuer_feld("inv_energy_9_ladung_kwh", m, bl, il) is None


def test_topic_suffix():
    assert _topic_suffix("eedc/1_Demo/live/einspeisung_w") == "live/einspeisung_w"
    assert _topic_suffix("eedc/1_Demo/energy/inv/2_Bar/pv_erzeugung_kwh") == "energy/inv/2_Bar/pv_erzeugung_kwh"
    assert _topic_suffix("nurzwei/segmente") is None


# ─── End-to-End gegen echte Anlage/Investition ───────────────────────────

async def _anlage_mit_pv(db, sensor_mapping: dict) -> Anlage:
    return await factories.anlage_mit_pv(db, sensor_mapping)


@pytest.mark.asyncio
async def test_materialisieren_ha_gateway_inbound(db):
    """HA-first, Gateway, konservativ Inbound — je Feld die richtige Quelle."""
    a = await _anlage_mit_pv(db, {
        "investitionen": {
            "1": {"felder": {"pv_erzeugung_kwh": {"strategie": "sensor", "sensor_id": "sensor.pv"}}},
        },
    })
    # Ein Gateway-Mapping für das Live-Leistungs-Feld der Investition.
    gw = MqttGatewayMapping(
        anlage_id=a.id, quell_topic="shellies/em/power",
        ziel_key="live/inv/1_PV/leistung_w", aktiv=True,
    )
    db.add(gw)
    await db.flush()

    await materialisiere_datenquellen(db)
    quellen = a.sensor_mapping["quellen"]

    # HA-Zuordnung materialisiert (Add-on-Test → ha_app oder ha_connector je Env)
    pv_energy = quellen.get("inv_energy_1_pv_erzeugung_kwh")
    assert pv_energy and pv_energy["quelle"] in ("ha_app", "ha_connector")
    assert pv_energy["entity_id"] == "sensor.pv"
    # Gateway-Feld materialisiert
    lw = quellen.get("inv_live_1_leistung_w")
    assert lw and lw["quelle"] == "mqtt_gateway" and lw["mapping_id"] == gw.id
    # Ein Feld ohne HA/Gateway → konservativ Inbound (Basis-Temperatur/Netzbezug)
    assert quellen.get("basis_energy_netzbezug_kwh", {}).get("quelle") == "mqtt_inbound_standard"
    assert quellen.get("basis_live_aussentemperatur_c", {}).get("quelle") == "mqtt_inbound_standard"


@pytest.mark.asyncio
async def test_materialisieren_respektiert_bestehende_und_idempotent(db):
    """Bestehende explizite Einträge (auch keine) bleiben; zweiter Lauf ändert nichts."""
    a = await _anlage_mit_pv(db, {
        "investitionen": {
            "1": {"felder": {"pv_erzeugung_kwh": {"strategie": "sensor", "sensor_id": "sensor.pv"}}},
        },
        "quellen": {
            "inv_energy_1_pv_erzeugung_kwh": {"quelle": "keine"},  # bewusste Wahl
        },
    })

    await materialisiere_datenquellen(db)
    q1 = dict(a.sensor_mapping["quellen"])
    # Bewusste keine-Wahl UNBERÜHRT (nicht auf HA überschrieben)
    assert q1["inv_energy_1_pv_erzeugung_kwh"] == {"quelle": "keine"}
    # Andere Felder wurden materialisiert
    assert "inv_live_1_leistung_w" in q1

    # Zweiter Lauf: idempotent (keine Änderung)
    await materialisiere_datenquellen(db)
    assert dict(a.sensor_mapping["quellen"]) == q1


@pytest.mark.asyncio
async def test_materialisieren_deaktiviert_paralleles_gateway(db):
    """§2h: hat ein Feld HA UND ein Gateway-Mapping → Gateway wird deaktiviert."""
    a = await _anlage_mit_pv(db, {
        "investitionen": {
            "1": {
                "felder": {"pv_erzeugung_kwh": {"strategie": "sensor", "sensor_id": "sensor.pv"}},
                "live": {"leistung_w": "sensor.pv_w"},  # HA-Sensor fürs Live-Feld
            },
        },
    })
    gw = MqttGatewayMapping(
        anlage_id=a.id, quell_topic="shellies/em/power",
        ziel_key="live/inv/1_PV/leistung_w", aktiv=True,
    )
    db.add(gw)
    await db.flush()

    await materialisiere_datenquellen(db)
    quellen = a.sensor_mapping["quellen"]

    # leistung_w hat HA → HA gewinnt, Gateway-Zeile deaktiviert (nicht gelöscht)
    assert quellen["inv_live_1_leistung_w"]["quelle"] in ("ha_app", "ha_connector")
    assert quellen["inv_live_1_leistung_w"]["entity_id"] == "sensor.pv_w"
    assert gw.aktiv is False
    # Zeile existiert noch (nur deaktiviert)
    still = (await db.execute(select(MqttGatewayMapping).where(MqttGatewayMapping.id == gw.id))).scalar_one()
    assert still is not None
