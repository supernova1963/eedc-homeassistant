"""
Datenquellen-V4 — Store-Abgleich nach V3-Wizard-Save (Fix-Paket v3.46, F3).

Der V3-Sensor-Mapping-Wizard schreibt `sensor_mapping` komplett neu. Vorher
löschte das die V4-Stores (`quellen`/`invertieren`) — Gateway-Invert dabei
irreversibel (Boot-Migrationen sind marker-einmalig, Gateway-Zeilen stehen
schon auf invertieren=False). Deckt: Übernahme fremder Keys, entity_id-Folge,
HA-first-Upgrade inkl. §2h-Gateway-Deaktivierung, `keine`-Respekt, Entfernen
der Wizard-Invert-Domäne bei Erhalt der Energie-Feld-Inverts.
"""

from datetime import date

import pytest
from sqlalchemy import select

from backend.models.anlage import Anlage
from backend.models.investition import Investition
from backend.models.mqtt_gateway_mapping import MqttGatewayMapping
from backend.services.datenquellen_wizard_sync import (
    sync_stores_nach_wizard_save,
    uebernehme_fremde_mapping_keys,
)


def test_uebernehme_fremde_mapping_keys():
    """Wizard-Besitz (basis/investitionen/solcast_config) bleibt neu; alles
    andere — auch künftige, hier unbekannte Keys — wird übernommen."""
    alt = {
        "basis": {"einspeisung": {"strategie": "sensor", "sensor_id": "sensor.alt"}},
        "investitionen": {"1": {}},
        "solcast_config": {"modus": "api"},
        "quellen": {"basis_energy_einspeisung_kwh": {"quelle": "keine"}},
        "invertieren": {"inv_energy_1_ladung_kwh": True},
        "zukunft_key": {"x": 1},
    }
    neu = {"basis": {}, "investitionen": {}}
    ergebnis = uebernehme_fremde_mapping_keys(alt, neu)
    assert ergebnis["basis"] == {}
    assert "solcast_config" not in ergebnis
    assert ergebnis["quellen"] == {"basis_energy_einspeisung_kwh": {"quelle": "keine"}}
    assert ergebnis["invertieren"] == {"inv_energy_1_ladung_kwh": True}
    assert ergebnis["zukunft_key"] == {"x": 1}
    assert uebernehme_fremde_mapping_keys(None, {"basis": {}}) == {"basis": {}}


async def _anlage(db, sensor_mapping: dict) -> Anlage:
    a = Anlage(anlagenname="Test", leistung_kwp=10.0, sensor_mapping=sensor_mapping)
    db.add(a)
    await db.flush()
    inv = Investition(
        anlage_id=a.id, typ="pv-module", bezeichnung="PV",
        anschaffungsdatum=date(2020, 1, 1),
    )
    db.add(inv)
    await db.flush()
    return a


@pytest.mark.asyncio
async def test_ha_eintrag_folgt_neuem_mapping(db):
    """entity_id wird aktualisiert; ohne HA-Sensor fällt der HA-Eintrag weg."""
    a = await _anlage(db, {
        "basis": {"einspeisung": {"strategie": "sensor", "sensor_id": "sensor.NEU"}},
        "investitionen": {},
        "quellen": {
            # stale entity nach Wizard-Edit → muss auf sensor.NEU folgen
            "basis_energy_einspeisung_kwh": {"quelle": "ha_connector", "entity_id": "sensor.ALT"},
            # Feld hat im neuen Mapping keinen HA-Sensor mehr → Eintrag weg
            "basis_energy_netzbezug_kwh": {"quelle": "ha_connector", "entity_id": "sensor.weg"},
        },
    })
    await sync_stores_nach_wizard_save(db, a)
    quellen = a.sensor_mapping["quellen"]
    assert quellen["basis_energy_einspeisung_kwh"]["entity_id"] == "sensor.NEU"
    assert quellen["basis_energy_einspeisung_kwh"]["quelle"] == "ha_connector"
    assert "basis_energy_netzbezug_kwh" not in quellen


@pytest.mark.asyncio
async def test_ha_first_upgrade_inbound_und_gateway(db):
    """Neu gemappter HA-Sensor gewinnt über inbound/gateway (B8 §2h);
    die Gateway-Zeile wird deaktiviert, nicht gelöscht."""
    a = await _anlage(db, {
        "basis": {},
        "investitionen": {"1": {"live": {"leistung_w": "sensor.pv_w"},
                                "felder": {"pv_erzeugung_kwh": {"strategie": "sensor", "sensor_id": "sensor.pv"}}}},
    })
    gw = MqttGatewayMapping(
        anlage_id=a.id, quell_topic="shellies/em/power",
        ziel_key="live/inv/1_PV/leistung_w", aktiv=True,
    )
    db.add(gw)
    await db.flush()
    mapping = dict(a.sensor_mapping)
    mapping["quellen"] = {
        "inv_live_1_leistung_w": {"quelle": "mqtt_gateway", "mapping_id": gw.id},
        "inv_energy_1_pv_erzeugung_kwh": {"quelle": "mqtt_inbound_standard"},
    }
    a.sensor_mapping = mapping

    await sync_stores_nach_wizard_save(db, a)
    quellen = a.sensor_mapping["quellen"]
    assert quellen["inv_live_1_leistung_w"]["quelle"] in ("ha_app", "ha_connector")
    assert quellen["inv_live_1_leistung_w"]["entity_id"] == "sensor.pv_w"
    assert quellen["inv_energy_1_pv_erzeugung_kwh"]["entity_id"] == "sensor.pv"
    assert gw.aktiv is False
    noch_da = (await db.execute(
        select(MqttGatewayMapping).where(MqttGatewayMapping.id == gw.id)
    )).scalar_one()
    assert noch_da is not None


@pytest.mark.asyncio
async def test_keine_und_mqtt_ohne_ha_bleiben(db):
    """`keine` (bewusste Wahl) und gateway/inbound ohne neuen HA-Sensor bleiben."""
    a = await _anlage(db, {
        "basis": {},
        "investitionen": {},
        "quellen": {
            "inv_energy_1_pv_erzeugung_kwh": {"quelle": "keine"},
            "basis_energy_netzbezug_kwh": {"quelle": "mqtt_inbound_standard"},
        },
    })
    await sync_stores_nach_wizard_save(db, a)
    quellen = a.sensor_mapping["quellen"]
    assert quellen["inv_energy_1_pv_erzeugung_kwh"] == {"quelle": "keine"}
    assert quellen["basis_energy_netzbezug_kwh"] == {"quelle": "mqtt_inbound_standard"}


@pytest.mark.asyncio
async def test_invert_wizard_domaene_raus_energie_bleibt(db):
    """`basis_live_*`/`inv_live_*` verlassen den Store (Wahrheit = frisches
    live_invert, Laufzeit unioniert — sonst wäre Abwählen im Wizard wirkungslos);
    Energie-Feld-Inverts (migrierte Gateway-Herkunft) bleiben."""
    a = await _anlage(db, {
        "basis": {"live_invert": {}},  # Wizard hat Invert gerade ABGEWÄHLT
        "investitionen": {},
        "invertieren": {
            "basis_live_einspeisung_w": True,   # alte Faltung → muss raus
            "inv_live_1_leistung_w": True,      # dito
            "inv_energy_1_ladung_kwh": True,    # Gateway-Herkunft → bleibt
        },
    })
    await sync_stores_nach_wizard_save(db, a)
    invert = a.sensor_mapping["invertieren"]
    assert invert == {"inv_energy_1_ladung_kwh": True}
