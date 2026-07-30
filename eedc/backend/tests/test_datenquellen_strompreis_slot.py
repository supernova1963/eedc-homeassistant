"""
Datenquellen-V4 — der Strompreis-Sensor ist wieder zuordenbar.

`sensor_mapping["basis"]["strompreis"]` speist die Strompreis-Mitschrift
(`energie_profil/_helpers.py`): stündlicher LTS-Mittelwert → `TEP.strompreis_cent`
→ verbrauchsgewichteter Ø-Bezugspreis + Ø-Ladepreis der Speicher-Netzladung.
Gesetzt werden konnte das Feld bis v3 im Sensor-Mapping-Wizard („Basis-Sensoren",
`BasisSensorenStep.tsx`); beim V4-Umbau ist der Slot ersatzlos entfallen. Das
Backend las ihn weiter — nur neu zuordnen ging nicht mehr, und im Forum
(#89667/55) verwies ein Tester noch auf den Weg, den es nicht mehr gab.

Drei Eigenschaften machen den Slot aus, jede hier gewächtert:

1. **Nur bei ausdrücklich dynamischem Tarif sichtbar.** Bei einem Festpreis
   gehört der Preis in die Stammdaten. Ein angebotener Preis-Slot verleitet
   sonst zum Konstanten-Sensor — genau das war #89667/54 (MartyBr hing seinen
   Festpreis-Template-Sensor mangels Alternative an den Speicher-Ø-Ladepreis).
2. **HA-only.** Kein Leser fragt MQTT für diesen Wert ab; Gateway/Inbound
   wären ein Versprechen ohne Einlösung.
3. **Kein MQTT-Topic.** Der Slot darf NICHT in der Topic-Registry landen, sonst
   meldet die MQTT-Abdeckungs-Prüfung (#134) eine Lücke, die niemand schließen
   kann.
"""

from __future__ import annotations

from datetime import date

import pytest
from fastapi import HTTPException

from backend.api.routes.datenquellen import (
    QuelleSetRequest, get_datenquellen_felder, set_feld_quelle,
)
from backend.models.anlage import Anlage
# Import registriert das Modell in `Base.metadata` — der `/felder`-Handler fragt
# die Gateway-Zeilen ab, die Tabelle muss in der Test-DB existieren.
from backend.models.mqtt_gateway_mapping import MqttGatewayMapping  # noqa: F401
from backend.models.strompreis import Strompreis
from backend.services.datenquellen_mapping_sync import uebernehme_quelle_ins_mapping
from backend.services.datenquellen_resolver import ha_entity_fuer_feld
from backend.services.mqtt_topic_registry import build_expected_topics

FID = "basis_preis_strompreis"


# ─── Schreib-Schicht (pur) ──────────────────────────────────────────────────

def test_schreibt_den_eintrag_den_die_mitschrift_liest():
    """Bitgleich zu dem, was der V3-Wizard schrieb — der Leser bleibt unberührt."""
    mapping: dict = {}
    assert uebernehme_quelle_ins_mapping(
        mapping, FID, "ha_app", "sensor.tibber_preis") is True
    assert mapping["basis"]["strompreis"] == {
        "strategie": "sensor", "sensor_id": "sensor.tibber_preis",
    }


def test_wegschalten_entwertet_den_eintrag():
    """„Keine Quelle" muss den Sensor entwerten, sonst zeigt die Fläche ihn
    weiter als zugeordnet (Stufe 1 der B8-2-Auflösung)."""
    mapping = {"basis": {"strompreis": {"strategie": "sensor", "sensor_id": "sensor.alt"}}}
    assert uebernehme_quelle_ins_mapping(mapping, FID, "keine", None) is True
    assert mapping["basis"]["strompreis"] == {"strategie": "keine"}


def test_resolver_findet_die_entity():
    mapping = {"basis": {"strompreis": {"strategie": "sensor", "sensor_id": "sensor.awattar"}}}
    assert ha_entity_fuer_feld(FID, mapping, {}, {}) == "sensor.awattar"
    # Entwerteter Eintrag ist keine Zuordnung.
    assert ha_entity_fuer_feld(
        "basis_preis_strompreis", {"basis": {"strompreis": {"strategie": "keine"}}}, {}, {},
    ) is None


# ─── Sichtbarkeit an der Fläche ─────────────────────────────────────────────

async def _anlage(db, *, vertragsart: str | None, mapping: dict | None = None) -> Anlage:
    a = Anlage(anlagenname="Test", leistung_kwp=10.0, sensor_mapping=mapping or {})
    db.add(a)
    await db.flush()
    db.add(Strompreis(
        anlage_id=a.id,
        netzbezug_arbeitspreis_cent_kwh=28.67,
        einspeiseverguetung_cent_kwh=8.2,
        gueltig_ab=date(2024, 1, 1),
        vertragsart=vertragsart,
        verwendung="allgemein",
    ))
    await db.flush()
    return a


def _felder_flat(resp) -> dict:
    return {f["id"]: f for g in resp["gruppen"] for f in g["felder"]}


@pytest.mark.asyncio
async def test_slot_erscheint_bei_dynamischem_tarif(db):
    a = await _anlage(db, vertragsart="dynamisch")
    felder = _felder_flat(await get_datenquellen_felder(a.id, db))

    assert FID in felder, sorted(felder)
    slot = felder[FID]
    assert slot["einheit"] == "ct/kWh"
    assert slot["kategorie"] == "preis"
    # HA-only: die Fläche blendet Gateway/Inbound anhand dieser Kennung aus.
    assert slot["nur_ha"] is True
    # Ein Preis ist kein Pflichtfeld — ohne ihn rechnet eedc mit dem Arbeitspreis.
    assert slot["bedarf"] == "optional"


@pytest.mark.asyncio
@pytest.mark.parametrize("vertragsart", ["fix", None])
async def test_slot_bleibt_bei_festpreis_verborgen(db, vertragsart):
    """Kein Preis-Slot ohne dynamischen Tarif — auch nicht beim leeren Dropdown
    (`vertragsart` ist optional, leer ist der Normalfall)."""
    a = await _anlage(db, vertragsart=vertragsart)
    assert FID not in _felder_flat(await get_datenquellen_felder(a.id, db))


@pytest.mark.asyncio
async def test_bestehende_zuordnung_wird_angezeigt(db):
    """Eine v3-Zuordnung war nie verloren — sie muss an der Fläche auftauchen,
    sobald der Slot wieder da ist."""
    a = await _anlage(db, vertragsart="dynamisch", mapping={
        "basis": {"strompreis": {"strategie": "sensor", "sensor_id": "sensor.tibber"}},
    })
    slot = _felder_flat(await get_datenquellen_felder(a.id, db))[FID]

    assert slot["ha_entity"] == "sensor.tibber"
    assert slot["quelle"] in ("ha_app", "ha_connector")


# ─── HA-only + kein MQTT-Topic ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_mqtt_quelle_wird_abgelehnt(db):
    """Der Riegel für den direkten API-Weg — die Fläche bietet es gar nicht an."""
    a = await _anlage(db, vertragsart="dynamisch")
    for quelle in ("mqtt_gateway", "mqtt_inbound_standard"):
        with pytest.raises(HTTPException) as fehler:
            await set_feld_quelle(a.id, FID, QuelleSetRequest(quelle=quelle), db)
        assert fehler.value.status_code == 400
        assert "HA-Sensor" in fehler.value.detail


@pytest.mark.asyncio
async def test_erzeugt_kein_erwartetes_mqtt_topic(db):
    """Wächter: der Slot darf die Topic-Registry nicht anfassen.

    Stünde er dort, erwartete die MQTT-Abdeckungs-Prüfung (#134) ein Topic,
    das eedc nie liest — dieselbe Klasse Fehlalarm wie #89667/54.
    """
    a = await _anlage(db, vertragsart="dynamisch")
    topics = await build_expected_topics(db, a, investitionen=[])

    assert not [t for t in topics if "strompreis" in t["topic"]], topics
    assert not [t for t in topics if t["match_key"][0] == "basis_preis"]
