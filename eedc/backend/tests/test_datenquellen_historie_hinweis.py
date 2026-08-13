"""Konzept #192 B — Zuordnungsänderung meldet die unberührte Historie.

Die Fläche schreibt jede Zuordnung sofort und einzeln; einen Wizard-Abschluss,
an dem der ursprüngliche Entwurf seinen Diff-Block zeigen wollte, gibt es im V4
nicht mehr. Stattdessen sammelt ein Vermerk in `anlage.sensor_mapping`, was sich
geändert hat, bis der Anwender quittiert.

Geprüft wird die **Wirkung** an drei Achsen:
1. reine Entscheidungslogik (`services/datenquellen_historie.py`),
2. die beiden Schreibpfade der Fläche (Quelle + Vorzeichen),
3. die Grenze: ohne aggregierte Historie schweigt der Hinweis.
"""

from datetime import date

import pytest
from fastapi import HTTPException

from backend.api.routes.datenquellen import (
    InvertSetRequest,
    QuelleSetRequest,
    get_datenquellen_felder,
    quittiere_historie_hinweis,
    set_feld_invert,
    set_feld_quelle,
)
from backend.models.anlage import Anlage
from backend.models.investition import Investition
from backend.models.tages_energie_profil import TagesZusammenfassung
from backend.services.datenquellen_historie import (
    HISTORIE_HINWEIS_KEY,
    ist_echte_aenderung,
    vermerk_ergaenzen,
    vermerk_leeren,
    vermerk_lesen,
)


# ─── Reine Entscheidungslogik ────────────────────────────────────────────

def test_gleiche_wahl_ist_keine_aenderung():
    """Der Picker erneut geöffnet und bestätigt — kein Anlass für einen Hinweis.

    Ohne diese Grenze meldete sich der Block bei jedem Klick; ein Hinweis ohne
    Anlass wird weggeklickt statt gelesen.
    """
    eintrag = {"quelle": "ha_app", "entity_id": "sensor.pv"}
    assert ist_echte_aenderung(eintrag, dict(eintrag)) is False


def test_none_und_leer_sind_dasselbe():
    """Beides heißt „kein eigener Eintrag" (Quelle = Grundeinstellung)."""
    assert ist_echte_aenderung(None, {}) is False
    assert ist_echte_aenderung({}, None) is False


def test_mapping_id_allein_ist_keine_aenderung():
    """Die Gateway-Zeilen-ID wechselt beim Upsert, ohne dass Werte anders werden."""
    assert ist_echte_aenderung(
        {"quelle": "mqtt_gateway", "mapping_id": 1},
        {"quelle": "mqtt_gateway", "mapping_id": 2},
    ) is False


def test_quellenwechsel_ist_eine_aenderung():
    assert ist_echte_aenderung(
        {"quelle": "keine"}, {"quelle": "ha_app", "entity_id": "sensor.pv"}
    ) is True
    assert ist_echte_aenderung(
        {"quelle": "ha_app", "entity_id": "sensor.alt"},
        {"quelle": "ha_app", "entity_id": "sensor.neu"},
    ) is True


def test_mehrere_felder_sammeln_sich_in_einem_vermerk():
    """Wer eine Komponente einrichtet, ordnet fünf Felder zu — und soll EINEN
    Hinweis sehen, nicht fünf."""
    m: dict = {}
    vermerk_ergaenzen(m, field_id="a", label="Netzbezug (kWh)", jetzt_iso="T1")
    vermerk_ergaenzen(m, field_id="b", label="Einspeisung (kWh)", jetzt_iso="T2")
    vermerk = vermerk_lesen(m)
    assert [f["label"] for f in vermerk["felder"]] == ["Netzbezug (kWh)", "Einspeisung (kWh)"]
    # `seit` ist der ERSTE Zeitpunkt: ab da sind die Werte neu, und das ist die
    # Grenze, die der Anwender für die Bereichs-Reparatur braucht.
    assert vermerk["seit"] == "T1"


def test_dasselbe_feld_zweimal_steht_einmal_drin():
    m: dict = {}
    vermerk_ergaenzen(m, field_id="a", label="Netzbezug (kWh)", jetzt_iso="T1")
    vermerk_ergaenzen(m, field_id="a", label="Netzbezug (kWh)", jetzt_iso="T2")
    assert len(vermerk_lesen(m)["felder"]) == 1


def test_leerer_vermerk_wird_nicht_gemeldet():
    """Ein Restposten ohne Felder ist kein Hinweis — sonst zeigte die Fläche
    einen leeren gelben Block."""
    assert vermerk_lesen({HISTORIE_HINWEIS_KEY: {"felder": [], "seit": "T1"}}) is None
    assert vermerk_lesen({}) is None
    assert vermerk_leeren({}) is False


# ─── Die beiden Schreibpfade der Fläche ──────────────────────────────────

async def _anlage(db, *, mit_historie: bool, sensor_mapping: dict | None = None) -> Anlage:
    a = Anlage(anlagenname="Test", leistung_kwp=10.0, sensor_mapping=sensor_mapping or {})
    db.add(a)
    await db.flush()
    db.add(Investition(
        anlage_id=a.id, typ="pv-module", bezeichnung="Süd",
        anschaffungsdatum=date(2020, 1, 1), leistung_kwp=10.0,
    ))
    if mit_historie:
        db.add(TagesZusammenfassung(anlage_id=a.id, datum=date(2026, 8, 1)))
    await db.flush()
    return a


@pytest.mark.asyncio
async def test_quellenwechsel_vermerkt_die_historie(db):
    a = await _anlage(db, mit_historie=True)
    await set_feld_quelle(
        a.id, "basis_energy_netzbezug",
        QuelleSetRequest(quelle="ha_connector", entity_id="sensor.netz"), db,
    )
    vermerk = vermerk_lesen(a.sensor_mapping)
    assert vermerk is not None
    assert [f["id"] for f in vermerk["felder"]] == ["basis_energy_netzbezug"]
    # Das Label kommt aus derselben Registry, die die Fläche zeigt — nicht die
    # technische Kennung, wenn es sich auflösen lässt.
    assert vermerk["felder"][0]["label"]


@pytest.mark.asyncio
async def test_ohne_historie_schweigt_der_hinweis(db):
    """Ersteinrichtung im Setup-Wizard: ein Dutzend Zuordnungen, keine Vergangenheit.

    Ein Hinweis auf eine Historie, die es nicht gibt, wäre reiner Lärm.
    """
    a = await _anlage(db, mit_historie=False)
    await set_feld_quelle(
        a.id, "basis_energy_netzbezug",
        QuelleSetRequest(quelle="ha_connector", entity_id="sensor.netz"), db,
    )
    assert vermerk_lesen(a.sensor_mapping) is None


@pytest.mark.asyncio
async def test_dieselbe_wahl_noch_einmal_erzeugt_keinen_hinweis(db):
    a = await _anlage(db, mit_historie=True)
    req = QuelleSetRequest(quelle="ha_connector", entity_id="sensor.netz")
    await set_feld_quelle(a.id, "basis_energy_netzbezug", req, db)
    a.sensor_mapping = dict(a.sensor_mapping)
    vermerk_leeren(a.sensor_mapping)
    await db.commit()

    await set_feld_quelle(a.id, "basis_energy_netzbezug", req, db)
    assert vermerk_lesen(a.sensor_mapping) is None


@pytest.mark.asyncio
async def test_vorzeichenwechsel_vermerkt_die_historie(db):
    """Das Vorzeichen dreht die Aggregation — der Anlass der Speicher-
    Vorzeichen-Selbstkorrektur (v3.45.7)."""
    a = await _anlage(db, mit_historie=True)
    await set_feld_invert(
        a.id, "inv_live_1_leistung_w", InvertSetRequest(invertieren=True), db,
    )
    assert vermerk_lesen(a.sensor_mapping) is not None


@pytest.mark.asyncio
async def test_vorzeichen_unveraendert_erzeugt_keinen_hinweis(db):
    a = await _anlage(db, mit_historie=True)
    await set_feld_invert(
        a.id, "inv_live_1_leistung_w", InvertSetRequest(invertieren=False), db,
    )
    assert vermerk_lesen(a.sensor_mapping) is None


# ─── Auslieferung an die Fläche + Quittung ───────────────────────────────

@pytest.mark.asyncio
async def test_felder_antwort_traegt_den_hinweis(db):
    a = await _anlage(db, mit_historie=True)
    await set_feld_quelle(
        a.id, "basis_energy_einspeisung",
        QuelleSetRequest(quelle="ha_connector", entity_id="sensor.ein"), db,
    )
    antwort = await get_datenquellen_felder(a.id, db)
    assert antwort["historie_hinweis"] is not None
    assert antwort["historie_hinweis"]["felder"]


@pytest.mark.asyncio
async def test_quittung_raeumt_den_hinweis_weg(db):
    a = await _anlage(db, mit_historie=True)
    await set_feld_quelle(
        a.id, "basis_energy_einspeisung",
        QuelleSetRequest(quelle="ha_connector", entity_id="sensor.ein"), db,
    )
    assert (await quittiere_historie_hinweis(a.id, db))["quittiert"] is True
    assert (await get_datenquellen_felder(a.id, db))["historie_hinweis"] is None
    # Zweite Quittung ist folgenlos statt ein Fehler.
    assert (await quittiere_historie_hinweis(a.id, db))["quittiert"] is False


@pytest.mark.asyncio
async def test_quittung_unbekannte_anlage(db):
    with pytest.raises(HTTPException) as exc:
        await quittiere_historie_hinweis(9999, db)
    assert exc.value.status_code == 404
