"""
Datenquellen-V4 — die Speicher-Felder heißen an der Fläche, wie sie gemeint sind.

Auslöser Forum simon42 #89667/62 + /64 + /71 (MartyBr, Plenticore): sein
Wechselrichter liefert `charge_from_pv` und `charge_from_grid` getrennt. Auf der
Zuordnungs-Fläche standen „Ladung" und „Netzladung" nebeneinander — er legte den
PV-Anteil auf „Ladung" und den Netz-Anteil auf „Netzladung", was 421 + 73 kWh
ergab statt der gemessenen 494. Das richtige Label gibt es seit #281
(`label_wenn`: „Ladung (gesamt, inkl. Netz)"), nur löste die Fläche es nicht auf:
sie zieht ihre Felder über `get_alle_felder_fuer_investition` (bewusst ohne
Bedingungsfilter, damit eine bestehende Zuordnung nicht unsichtbar verschwindet)
— und die Funktion reichte die Roh-Definition durch.

Zweiter Befund derselben Fläche (#89667/54 + /58): „Ø Ladepreis" ist ein
MONATSWERT in ct/kWh, für den es keinen Erfassungsweg aus Sensor oder Topic gibt.
Angeboten wurde er trotzdem; der zugeordnete Sensor bewirkte nichts, löste aber
eine Daten-Checker-Meldung aus. Er ist jetzt `nur_manuell` — erfassbar bleibt er
im Monatsabschluss und im CSV-Import.
"""

from __future__ import annotations

import pytest

from backend.core.field_definitions import (
    INVESTITION_FELDER,
    get_alle_felder_fuer_investition,
    get_felder_fuer_investition,
)
from backend.models.anlage import Anlage
from backend.models.investition import Investition
# Import registriert das Modell in `Base.metadata` — der `/felder`-Handler fragt
# die Gateway-Zeilen ab, die Tabelle muss in der Test-DB existieren.
from backend.models.mqtt_gateway_mapping import MqttGatewayMapping  # noqa: F401
from backend.api.routes.datenquellen import get_datenquellen_felder
from backend.services.mqtt_topic_registry import build_expected_topics


def _labels(felder: list[dict]) -> dict[str, str]:
    return {f["feld"]: f["label"] for f in felder}


# ─── Label-Auflösung (pur) ──────────────────────────────────────────────────

def test_ladung_heisst_gesamt_sobald_netzladung_im_spiel_ist():
    labels = _labels(get_alle_felder_fuer_investition("speicher", {"laedt_aus_netz": True}))
    assert labels["ladung_kwh"] == "Ladung (gesamt, inkl. Netz)"
    assert labels["ladung_netz_kwh"] == "Netzladung"


def test_arbitrage_impliziert_netzladung_auch_ohne_eigenes_flag():
    """Wer Arbitrage fährt, lädt aus dem Netz — dasselbe Label muss greifen."""
    labels = _labels(get_alle_felder_fuer_investition("speicher", {"arbitrage_faehig": True}))
    assert labels["ladung_kwh"] == "Ladung (gesamt, inkl. Netz)"


def test_reiner_pv_speicher_behaelt_das_kurze_label():
    labels = _labels(get_alle_felder_fuer_investition("speicher", {}))
    assert labels["ladung_kwh"] == "Ladung"


def test_beide_feld_wege_sagen_dasselbe():
    """Monatsabschluss (gefiltert) und Zuordnungs-Fläche (ungefiltert) dürfen ein
    Feld nicht verschieden benennen — das war der ganze Fehler."""
    params = {"laedt_aus_netz": True}
    eingabe = _labels(get_felder_fuer_investition("speicher", params))
    flaeche = _labels(get_alle_felder_fuer_investition("speicher", params))
    for feld, label in eingabe.items():
        assert flaeche[feld] == label, feld


def test_die_definition_bleibt_unveraendert():
    """Die Feld-Dicts sind Modul-Konstanten — eine Auflösung darf sie nicht
    umschreiben, sonst trägt die nächste Investition das fremde Label."""
    get_alle_felder_fuer_investition("speicher", {"laedt_aus_netz": True})
    roh = {f["feld"]: f["label"] for f in INVESTITION_FELDER["speicher"]}
    assert roh["ladung_kwh"] == "Ladung"


# ─── Ø Ladepreis ist nicht zuordenbar ───────────────────────────────────────

def test_ladepreis_ist_nur_manuell():
    feld = next(
        f for f in get_alle_felder_fuer_investition("speicher", {"arbitrage_faehig": True})
        if f["feld"] == "speicher_ladepreis_cent"
    )
    assert feld["nur_manuell"] is True
    # Erfassbar bleibt er: der Monatsabschluss zeigt ihn weiter.
    assert "speicher_ladepreis_cent" in _labels(
        get_felder_fuer_investition("speicher", {"arbitrage_faehig": True})
    )


@pytest.mark.asyncio
async def test_ladepreis_erscheint_nicht_an_der_flaeche(db):
    anlage = Anlage(anlagenname="Test", leistung_kwp=10.0, sensor_mapping={})
    db.add(anlage)
    await db.flush()
    inv = Investition(
        anlage_id=anlage.id, typ="speicher", bezeichnung="Pylontech",
        parameter={"arbitrage_faehig": True, "laedt_aus_netz": True},
    )
    db.add(inv)
    await db.flush()

    resp = await get_datenquellen_felder(anlage.id, db)
    felder = {f["id"]: f for g in resp["gruppen"] for f in g["felder"]}

    assert f"inv_energy_{inv.id}_speicher_ladepreis_cent" not in felder, sorted(felder)
    # Die Energie-Felder daneben bleiben zuordenbar — und tragen das lange Label.
    ladung = felder[f"inv_energy_{inv.id}_ladung_kwh"]
    assert "gesamt, inkl. Netz" in ladung["label"]

    # Kein erwartetes MQTT-Topic für einen Wert, den kein Leser aus MQTT zieht
    # (sonst meldet die Abdeckungs-Prüfung #134 eine unschließbare Lücke).
    topics = await build_expected_topics(db, anlage)
    ladepreis = [t for t in topics if t.get("feld") == "speicher_ladepreis_cent"]
    assert ladepreis and all(t["nur_manuell"] for t in ladepreis)
