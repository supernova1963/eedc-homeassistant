"""N-789 — der Daten-Checker kennt tote Felder an *Sonstiges*-Geräten (#443).

**Der Fall (rilmor-mhrs, #443, Version 4.2.2):** zwei *Sonstiges*-Geräte der
Kategorie «Abgabe an Dritte» tragen in den Monaten April–August 2026 ihre kWh
in ``erzeugung_kwh`` — aus der Zeit, als sie Erzeuger waren. Seit 4.0.41 zählt
der Wert in **keiner** Bilanz (der Abgabe-Zweig von ``imd_typ_beitrag`` setzt
die Erzeugung 0), Cockpit → Monat zeigt «—», und der Anwender bekam weder einen
Hinweis noch einen Weg, den Alt-Wert zu entfernen.

**Die Ursache:** ``INVESTITION_FELDER["sonstiges"]`` ist ein Dict je Kategorie,
keine Liste. Die N-393-Regel kehrte dort leer zurück, und
``groesse_gibt_es_am_geraet`` lief fail-open — «Wert entfernen» antwortete für
jedes Sonstiges-Feld mit 409.

**Maßstab ist der Lesepfad, nicht die Registry-Liste.** Ein Feld ist an einem
Gerät mit gepflegter Kategorie tot, wenn **kein** Leser es liest: der Monat
(``imd_typ_beitrag``), der Tag (``sonstiges_feld_reihenfolge``) und der
Zählerstand-Pfad (``zaehlerstaende``). Der Wächter-Test unten befragt die drei
Leser selbst und hält die Antwort von ``groesse_gibt_es_am_geraet`` dagegen —
wer einen Lesepfad ändert, ohne ``sonstiges_gelesene_felder`` mitzuziehen,
wird hier rot.
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import date
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from backend.core.berechnungen.imd_monatsaggregat import ImdTypBeitrag, imd_typ_beitrag
from backend.core.field_definitions import (
    INVESTITION_FELDER,
    SONSTIGES_VERBRAUCH_FELDER,
    groesse_gibt_es_am_geraet,
    sonstiges_feld_reihenfolge,
)
from backend.models import Anlage, Investition, InvestitionMonatsdaten, Monatsdaten
from backend.models.data_provenance_log import DataProvenanceLog
from backend.services.daten_checker import DatenChecker
from backend.services.daten_checker.kategorien import link_monat_erfassen
from backend.services.zaehlerstaende import ist_zaehler_investition

_SONSTIGES = INVESTITION_FELDER["sonstiges"]

#: Jedes Feld, das ein *Sonstiges*-Gerät tragen kann: die Vereinigung der
#: Kategorie-Listen und der Legacy-Zwilling ``verbrauch_kwh`` (Ersatzgruppe).
_ALLE_FELDER = sorted(
    {f["feld"] for liste in _SONSTIGES.values() for f in liste}
    | set(SONSTIGES_VERBRAUCH_FELDER)
)


# ── (a) Wächter: tot = kein Lesepfad liest ──────────────────────────────────

def _gemessen_gelesen(kategorie: str, feld: str) -> bool:
    """Liest irgendein Pfad ``feld`` an einem Gerät dieser Kategorie?"""
    inv = SimpleNamespace(typ="sonstiges", parameter={"kategorie": kategorie})
    leer = asdict(ImdTypBeitrag(typ="sonstiges"))
    monat = asdict(imd_typ_beitrag(inv, {feld: 1.0})) != leer
    tag = feld in sonstiges_feld_reihenfolge(kategorie)
    zaehlerstand = feld == "zaehlerstand" and ist_zaehler_investition(inv)
    return monat or tag or zaehlerstand


@pytest.mark.parametrize("kategorie", sorted(_SONSTIGES))
def test_waechter_tot_heisst_kein_lesepfad_liest(kategorie):
    """Die Menge der Felder, die nirgends beitragen, ist genau die Menge, für
    die ``groesse_gibt_es_am_geraet`` ``False`` sagt — je gepflegter Kategorie."""
    tot_gemessen = {f for f in _ALLE_FELDER if not _gemessen_gelesen(kategorie, f)}
    tot_helfer = {
        f for f in _ALLE_FELDER
        if not groesse_gibt_es_am_geraet("sonstiges", f, {"kategorie": kategorie})
    }
    assert tot_helfer == tot_gemessen


def test_waechter_registry_liste_ist_immer_lebendig():
    """Was die Kategorie im Monatsabschluss anbietet, liest auch ein Pfad."""
    for kategorie, liste in _SONSTIGES.items():
        for f in liste:
            assert _gemessen_gelesen(kategorie, f["feld"]), (kategorie, f["feld"])


def test_abgabe_kennt_genau_zwei_lebendige_felder():
    """Der Melder-Fall: an «Abgabe an Dritte» leben nur Abgabe und Erlös."""
    lebendig = {
        f for f in _ALLE_FELDER
        if groesse_gibt_es_am_geraet("sonstiges", f, {"kategorie": "abgabe"})
    }
    assert lebendig == {"abgabe_kwh", "einspeise_erloes_euro"}


def test_ungepflegte_kategorie_und_unbekanntes_feld_bleiben_fail_open():
    for parameter in ({}, {"kategorie": ""}, {"kategorie": "unbekannt"}, None):
        for f in _ALLE_FELDER:
            assert groesse_gibt_es_am_geraet("sonstiges", f, parameter), (parameter, f)
    assert groesse_gibt_es_am_geraet("sonstiges", "leistung_w", {"kategorie": "abgabe"})
    assert groesse_gibt_es_am_geraet("sonstiges", "ladung_kwh", {"kategorie": "zaehler"})


# ── Der Checker ──────────────────────────────────────────────────────────────

async def _anlage_mit(db, *, parameter: dict, monate: dict[int, dict]):
    anlage = Anlage(anlagenname="N-789", leistung_kwp=10.0,
                    installationsdatum=date(2026, 1, 1))
    db.add(anlage)
    await db.flush()
    inv = Investition(
        anlage_id=anlage.id, typ="sonstiges", bezeichnung="Allg. Strom",
        anschaffungsdatum=date(2026, 1, 1), anschaffungskosten_gesamt=1000.0,
        parameter=parameter,
    )
    db.add(inv)
    await db.flush()
    for monat, daten in monate.items():
        db.add(InvestitionMonatsdaten(
            investition_id=inv.id, jahr=2026, monat=monat, verbrauch_daten=dict(daten),
            source_provenance={
                f"verbrauch_daten.{k}": {"source": "manual:form", "writer": "test",
                                         "written_at": "2026-07-01T00:00:00"}
                for k in daten
            },
        ))
        db.add(Monatsdaten(anlage_id=anlage.id, jahr=2026, monat=monat,
                           einspeisung_kwh=100.0, netzbezug_kwh=100.0))
    await db.commit()
    geladen = (await db.execute(
        select(Investition).options(selectinload(Investition.monatsdaten))
        .where(Investition.id == inv.id)
    )).scalar_one()
    return anlage, geladen


def _befunde(db, inv):
    return DatenChecker(db)._check_werte_in_nicht_gefuehrten_feldern(
        inv, inv.bezeichnung, inv.parameter or {}
    )


_ROBERT = {m: {"erzeugung_kwh": 40.0 + m} for m in (4, 5, 6, 7, 8)} | {
    9: {"einspeise_erloes_euro": 12.5}, 10: {"abgabe_kwh": 51.0, "einspeise_erloes_euro": 12.0},
}


@pytest.mark.asyncio
async def test_abgabe_mit_alter_erzeugung_ergibt_eine_meldung_mit_angebot(db):
    """(b) Roberts Fall: EINE INFO mit fünf Monaten und der Aktion."""
    _, inv = await _anlage_mit(db, parameter={"kategorie": "abgabe"}, monate=_ROBERT)
    befunde = _befunde(db, inv)
    assert len(befunde) == 1
    e = befunde[0]
    assert e.schwere.value == "info"
    assert e.kategorie.value == "investitionen"
    assert e.meldung == (
        "Allg. Strom: Erzeugung in 5 Monat(en) gespeichert — ein Gerät der "
        "Kategorie «Abgabe an Dritte» führt das Feld nicht"
    )
    assert e.action_kind == "feldwert_entfernen"
    assert e.action_label == "Wert entfernen"
    assert e.action_params == {
        "investition_id": inv.id, "feld": "erzeugung_kwh", "label": "Erzeugung",
        "monate": ["04/2026", "05/2026", "06/2026", "07/2026", "08/2026"],
    }
    assert e.details.startswith("04/2026, 05/2026, 06/2026, 07/2026, 08/2026. ")
    assert "Der Wert zählt in keiner Bilanz." in e.details
    assert "„Abgabe (kWh)“" in e.details, "das Angebot nennt das Ziel-Feld"
    assert "Einstellungen → Daten → Monatsdaten" in e.details
    assert e.details.endswith("eedc löscht und verschiebt nichts von allein.")
    assert e.link == link_monat_erfassen("04/2026")
    assert e.investition_id == inv.id


@pytest.mark.asyncio
async def test_andere_kategorie_bekommt_den_allgemeinen_ausweg(db):
    """Ein Verbraucher mit Einspeisung: kein Abgabe-Angebot, sondern «Kategorie zurück»."""
    _, inv = await _anlage_mit(
        db, parameter={"kategorie": "verbraucher"},
        monate={3: {"verbrauch_sonstig_kwh": 80.0, "einspeisung_kwh": 5.0}},
    )
    befunde = _befunde(db, inv)
    assert len(befunde) == 1
    e = befunde[0]
    assert e.action_params["feld"] == "einspeisung_kwh"
    assert "Kategorie «Verbraucher»" in e.meldung, "Anwender-Sprache, nicht der Registry-Schlüssel"
    assert "Abgabe (kWh)" not in e.details
    assert "stelle die Kategorie zurück" in e.details
    assert "Der Wert zählt in keiner Bilanz." in e.details


@pytest.mark.asyncio
async def test_erzeuger_mit_ersatzfeld_bleibt_still(db):
    """(c) N-667: ohne ``erzeugung_kwh`` ist ``verbrauch_kwh`` die Erzeugung — lebendig."""
    _, inv = await _anlage_mit(
        db, parameter={"kategorie": "erzeuger"},
        monate={6: {"verbrauch_kwh": 120.0}, 7: {"verbrauch_sonstig_kwh": 90.0}},
    )
    assert _befunde(db, inv) == []


@pytest.mark.asyncio
async def test_ungepflegte_kategorie_bleibt_still(db):
    """(d) Ohne gepflegte Kategorie liest der Monat alles (Site-3-Verhalten)."""
    _, inv = await _anlage_mit(
        db, parameter={},
        monate={6: {"erzeugung_kwh": 10.0, "verbrauch_sonstig_kwh": 5.0,
                    "einspeisung_kwh": 2.0, "bezug_netz_kwh": 1.0}},
    )
    assert _befunde(db, inv) == []


@pytest.mark.asyncio
async def test_eine_null_loest_nichts_aus(db):
    """(e) Eine 0 ist keine Aussage und rechnet nirgends mit."""
    _, inv = await _anlage_mit(
        db, parameter={"kategorie": "abgabe"},
        monate={6: {"erzeugung_kwh": 0, "abgabe_kwh": 30.0}},
    )
    assert _befunde(db, inv) == []


@pytest.mark.asyncio
async def test_der_gesamtlauf_des_checkers_traegt_die_meldung(db):
    """(f) Der Aufruf aus ``stammdaten.py`` erreicht auch *Sonstiges*."""
    anlage, _ = await _anlage_mit(db, parameter={"kategorie": "abgabe"}, monate=_ROBERT)
    result = await DatenChecker(db).check_anlage(anlage.id)
    treffer = [e for e in result.ergebnisse if e.action_kind == "feldwert_entfernen"]
    assert len(treffer) == 1
    assert treffer[0].action_params["feld"] == "erzeugung_kwh"
    assert len(treffer[0].action_params["monate"]) == 5


# ── Der Endpunkt ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_endpunkt_entfernt_alte_erzeugung_am_abgabe_geraet(db):
    """(g) Alle fünf Monate, je Monat ein Audit-Eintrag; Abgabe und Erlös bleiben."""
    from backend.api.routes.monatsdaten import delete_feldwert_nicht_gefuehrt

    _, inv = await _anlage_mit(db, parameter={"kategorie": "abgabe"}, monate=_ROBERT)
    antwort = await delete_feldwert_nicht_gefuehrt(inv.id, "erzeugung_kwh", db=db)
    assert antwort["entfernt"] == 5
    assert [(m["monat"], m["wert"]) for m in antwort["monate"]] == [
        (4, 44.0), (5, 45.0), (6, 46.0), (7, 47.0), (8, 48.0),
    ]
    zeilen = (await db.execute(
        select(InvestitionMonatsdaten).where(InvestitionMonatsdaten.investition_id == inv.id)
        .order_by(InvestitionMonatsdaten.monat)
    )).scalars().all()
    assert all("erzeugung_kwh" not in (z.verbrauch_daten or {}) for z in zeilen)
    assert zeilen[-1].verbrauch_daten == {"abgabe_kwh": 51.0, "einspeise_erloes_euro": 12.0}

    logs = (await db.execute(
        select(DataProvenanceLog).where(
            DataProvenanceLog.field_name == "verbrauch_daten.erzeugung_kwh"
        )
    )).scalars().all()
    assert len(logs) == 5
    assert all(log.new_value is None and "N-393" in log.decision_reason for log in logs)

    geladen = (await db.execute(
        select(Investition).options(selectinload(Investition.monatsdaten))
        .where(Investition.id == inv.id)
    )).scalar_one()
    assert _befunde(db, geladen) == [], "danach ist der Checker still"


@pytest.mark.asyncio
@pytest.mark.parametrize(("kategorie", "feld", "monate"), [
    ("abgabe", "abgabe_kwh", {6: {"abgabe_kwh": 30.0}}),
    ("erzeuger", "verbrauch_kwh", {6: {"verbrauch_kwh": 120.0}}),
])
async def test_endpunkt_weist_ein_lebendiges_feld_ab(db, kategorie, feld, monate):
    """(h) Ein Feld, das ein Pfad liest, wird im Formular geleert — 409."""
    from backend.api.routes.monatsdaten import delete_feldwert_nicht_gefuehrt

    _, inv = await _anlage_mit(db, parameter={"kategorie": kategorie}, monate=monate)
    with pytest.raises(HTTPException) as exc:
        await delete_feldwert_nicht_gefuehrt(inv.id, feld, db=db)
    assert exc.value.status_code == 409
    zeile = (await db.execute(
        select(InvestitionMonatsdaten).where(InvestitionMonatsdaten.investition_id == inv.id)
    )).scalar_one()
    assert zeile.verbrauch_daten == monate[6], "nichts angefasst"


# ── (i) Erwartete MQTT-Topics (``daten_checker/sensoren.py``) ───────────────

@pytest.mark.asyncio
@pytest.mark.parametrize("kategorie", sorted(_SONSTIGES))
async def test_erwartete_topics_eines_sonstiges_geraets_bleiben_unveraendert(db, kategorie):
    """Die Topic-Liste kommt aus der Feldliste der Kategorie
    (``get_felder_fuer_sonstiges``) — jedes ihrer Felder ist lebendig. Der Filter
    ``groesse_gibt_es_am_geraet`` in ``sensoren.py`` nimmt deshalb auch nach
    N-789 kein Topic eines *Sonstiges*-Geräts heraus; ein totes Feld (z. B.
    ``erzeugung_kwh`` an einem Abgabe-Gerät) steht gar nicht erst in der Liste."""
    from backend.services.mqtt_topic_registry import build_expected_topics

    anlage, inv = await _anlage_mit(db, parameter={"kategorie": kategorie}, monate={})
    topics = await build_expected_topics(db, anlage, investitionen=[inv])
    energie = [e for e in topics if e["match_key"][0] == "inv_energy"]
    erwartet = {f["feld"] for f in _SONSTIGES[kategorie]}
    assert {e["feld"] for e in energie} == erwartet
    for e in topics:
        if e["match_key"][0] in ("inv_energy", "inv_live"):
            assert groesse_gibt_es_am_geraet(e["typ"], e["feld"], inv.parameter), e["feld"]


# ── Nachbesserung nach Master-Entscheid (10.11.2026) ────────────────────────

@pytest.mark.asyncio
async def test_abgabe_angebot_nur_an_hauptgroessen(db):
    """Erzeugung und Einspeisung am Abgabe-Gerät ⇒ zwei INFOs, nur die Erzeugung trägt das Angebot."""
    _, inv = await _anlage_mit(
        db, parameter={"kategorie": "abgabe"},
        monate={5: {"erzeugung_kwh": 40.0, "einspeisung_kwh": 12.0}},
    )
    befunde = {e.action_params["feld"]: e for e in _befunde(db, inv)}
    assert set(befunde) == {"erzeugung_kwh", "einspeisung_kwh"}
    assert "„Abgabe (kWh)“" in befunde["erzeugung_kwh"].details
    assert "„Abgabe (kWh)“" not in befunde["einspeisung_kwh"].details
    assert "stelle die Kategorie zurück" in befunde["einspeisung_kwh"].details
    assert "«Abgabe an Dritte»" in befunde["einspeisung_kwh"].meldung


@pytest.mark.asyncio
async def test_legacy_feld_ohne_registry_label_wird_gemeldet_und_entfernt(db):
    """``verbrauch_kwh`` führt keine Kategorie-Liste: Label vom kanonischen Geschwister, Aktion, Endpunkt entfernt."""
    from backend.api.routes.monatsdaten import delete_feldwert_nicht_gefuehrt

    _, inv = await _anlage_mit(db, parameter={"kategorie": "abgabe"}, monate={6: {"verbrauch_kwh": 500.0}})
    befunde = _befunde(db, inv)
    assert len(befunde) == 1
    e = befunde[0]
    assert e.meldung.startswith("Allg. Strom: Verbrauch in 1 Monat(en) gespeichert")
    assert e.action_kind == "feldwert_entfernen"
    assert e.action_params == {
        "investition_id": inv.id, "feld": "verbrauch_kwh", "label": "Verbrauch", "monate": ["06/2026"],
    }
    assert "„Abgabe (kWh)“" in e.details, "Verbrauch ist eine Hauptgröße"
    antwort = await delete_feldwert_nicht_gefuehrt(inv.id, "verbrauch_kwh", db=db)
    assert antwort["entfernt"] == 1
    assert antwort["monate"][0]["wert"] == 500.0

