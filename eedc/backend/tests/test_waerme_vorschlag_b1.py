"""B1 — der Wärme-Vorschlag rechnet mit dem Strom derselben Funktion und sagt, dass er schätzt.

SOLL Wärme/Klima §6, Präzisierung F2–F5 (05.09.2026): abgeleitete Wärme ist als
**gekennzeichnete Schätzung** zulässig, nie Kennzahl-Basis — und sie entsteht nur
aus dem Strom derselben Funktion. Gemessen am Code vom 05.09.: (1) ohne getrennte
Strommessung schlug der Dienst BEIDE Wärmefelder aus dem Gesamtstrom vor
(Doppelzählung); (2) an dietmar1968s Klimaanlage mit Betriebsart-Zählern rechnete
er E_gesamt × 3,5 — 254 kWh Kühlstrom wurden 889 kWh „Warmwasser" (T89667 #295);
(3) der übernommene Vorschlag trug keine Marke und galt jeder Lesestelle als Messung.
"""
from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from backend.core.berechnungen.imd_monatsaggregat import imd_typ_beitrag
from backend.core.berechnungen.modus_split import (
    ABLEITUNGS_REGELN_WAERME,
    REGEL_JAZ_MODUS_SPLIT,
    REGEL_JAZ_VORSCHLAG,
    heizwaerme_ist_abgeleitet,
    warmwasser_ist_abgeleitet,
)
from backend.core.berechnungen.waerme_vorschlag import (
    gesamtstrom_ist_heizstrom,
    strom_basis_fuer_waerme_vorschlag,
)
from backend.models import Anlage, Investition, InvestitionMonatsdaten
from backend.services.provenance import ERLAUBTE_ABLEITUNGEN, gepruefte_ableitung
from backend.services.vorschlag_service import VorschlagQuelle, VorschlagService

JAZ = {"jaz": 3.5}
GETRENNT = {"jaz": 3.5, "getrennte_strommessung": True}


# ── Der Layer: welche Basis ─────────────────────────────────────────────────

def test_f2_gesamtstrom_traegt_nur_die_heizwaerme():
    """Ohne getrennte Messung: Heizwärme aus dem Gesamtstrom, Warmwasser KEIN Vorschlag.

    Bis B1 kamen beide aus demselben Strom — „Lücken füllen" übernahm beide, und
    die Gesamtwärme stand doppelt in der Zeile.
    """
    daten = {"stromverbrauch_kwh": 300.0}
    heiz = strom_basis_fuer_waerme_vorschlag("heizenergie_kwh", daten, JAZ)
    assert heiz is not None and heiz.strom_kwh == 300.0 and heiz.sprosse == "F2"
    assert strom_basis_fuer_waerme_vorschlag("warmwasser_kwh", daten, JAZ) is None


def test_f5_getrennte_messung_je_funktion_ihr_strom():
    daten = {"strom_heizen_kwh": 200.0, "strom_warmwasser_kwh": 60.0}
    heiz = strom_basis_fuer_waerme_vorschlag("heizenergie_kwh", daten, GETRENNT)
    ww = strom_basis_fuer_waerme_vorschlag("warmwasser_kwh", daten, GETRENNT)
    assert (heiz.strom_kwh, heiz.sprosse) == (200.0, "F5")
    assert (ww.strom_kwh, ww.sprosse) == (60.0, "F5")


def test_f4_betriebsart_zaehler_schlaegt_den_gesamtstrom_dietmars_juni():
    """dietmars Klimaanlage im Juni: 254 kWh gesamt, davon 0 Heizbetrieb.

    Bis B1: 254 × 3,5 = 889 kWh „Wärme". Jetzt: Heizstrom 0 ⇒ 0 kWh — und
    Warmwasser gar kein Vorschlag (kein getrennter Warmwasser-Strom).
    """
    daten = {
        "stromverbrauch_kwh": 254.0,
        "betriebsart_strom_heizen_kwh": 0.0,
        "betriebsart_strom_kuehlen_kwh": 250.0,
    }
    heiz = strom_basis_fuer_waerme_vorschlag("heizenergie_kwh", daten, JAZ)
    assert heiz is not None
    assert heiz.strom_kwh == 0.0 and heiz.sprosse == "F4" and heiz.label == "Strom Heizbetrieb"
    assert strom_basis_fuer_waerme_vorschlag("warmwasser_kwh", daten, JAZ) is None


def test_gesamtstrom_mit_fremder_spur_ist_kein_heizstrom():
    """Kühlstrom in der Zeile, aber kein Heiz-Betriebsart-Zähler ⇒ kein Vorschlag.

    Nicht der Gesamtstrom mit Warnung — nichts. Ein falscher Vorschlag kostet eine
    Ersparnis, die es nicht gab.
    """
    assert gesamtstrom_ist_heizstrom({"stromverbrauch_kwh": 254.0}) is True
    assert gesamtstrom_ist_heizstrom(
        {"stromverbrauch_kwh": 254.0, "betriebsart_strom_kuehlen_kwh": 250.0}
    ) is False
    assert gesamtstrom_ist_heizstrom(
        {"stromverbrauch_kwh": 254.0, "betriebsart_nutzenergie_kuehlen_kwh": 700.0}
    ) is False
    assert gesamtstrom_ist_heizstrom(
        {"stromverbrauch_kwh": 254.0, "strom_warmwasser_kwh": 40.0}
    ) is False
    assert strom_basis_fuer_waerme_vorschlag(
        "heizenergie_kwh",
        {"stromverbrauch_kwh": 254.0, "betriebsart_strom_kuehlen_kwh": 250.0},
        JAZ,
    ) is None


def test_die_bauart_entscheidet_nichts_r1():
    """Dieselbe Zeile, andere Bauart — dieselbe Basis (ADR-002/P13 hält es baumweit)."""
    daten = {"stromverbrauch_kwh": 300.0}
    a = strom_basis_fuer_waerme_vorschlag("heizenergie_kwh", daten, {**JAZ, "wp_art": "luft_luft"})
    b = strom_basis_fuer_waerme_vorschlag("heizenergie_kwh", daten, {**JAZ, "wp_art": "luft_wasser"})
    assert a == b


def test_ohne_strom_kein_vorschlag():
    assert strom_basis_fuer_waerme_vorschlag("heizenergie_kwh", {}, JAZ) is None
    assert strom_basis_fuer_waerme_vorschlag("heizenergie_kwh", {"strom_heizen_kwh": None}, GETRENNT) is None
    assert strom_basis_fuer_waerme_vorschlag("pv_erzeugung_kwh", {"stromverbrauch_kwh": 1.0}, JAZ) is None


# ── Die Marke ───────────────────────────────────────────────────────────────

def test_die_marke_ist_erlaubt_und_beide_regeln_sind_ableitungen():
    assert REGEL_JAZ_VORSCHLAG in ERLAUBTE_ABLEITUNGEN, "der Client meldet sie zurück"
    assert gepruefte_ableitung(REGEL_JAZ_VORSCHLAG) == REGEL_JAZ_VORSCHLAG
    assert ABLEITUNGS_REGELN_WAERME == {REGEL_JAZ_MODUS_SPLIT, REGEL_JAZ_VORSCHLAG}


def test_die_weiche_kennt_beide_marken_und_beide_felder():
    prov = {"verbrauch_daten.heizenergie_kwh": {"abgeleitet": REGEL_JAZ_VORSCHLAG}}
    assert heizwaerme_ist_abgeleitet(prov) is True
    assert warmwasser_ist_abgeleitet(prov) is False
    prov_ww = {"verbrauch_daten.warmwasser_kwh": {"abgeleitet": REGEL_JAZ_VORSCHLAG}}
    assert warmwasser_ist_abgeleitet(prov_ww) is True
    assert heizwaerme_ist_abgeleitet(prov_ww) is False
    assert warmwasser_ist_abgeleitet({"verbrauch_daten.warmwasser_kwh": {"abgeleitet": "kwp_anteil"}}) is False


def test_abgeleitetes_warmwasser_sperrt_die_arbeitszahl_im_aggregat():
    """`wp_waerme_abgeleitet` zählt jetzt beide Funktionen — ein abgeleiteter Teil sperrt."""
    class _Inv:
        typ = "waermepumpe"
        parameter = {"getrennte_strommessung": True}
    daten = {"strom_heizen_kwh": 200.0, "strom_warmwasser_kwh": 60.0,
             "heizenergie_kwh": 700.0, "warmwasser_kwh": 210.0}
    ohne = imd_typ_beitrag(_Inv(), daten, {})
    assert ohne.wp_waerme_abgeleitet == 0.0
    nur_ww = imd_typ_beitrag(_Inv(), daten, {
        "verbrauch_daten.warmwasser_kwh": {"abgeleitet": REGEL_JAZ_VORSCHLAG},
    })
    assert nur_ww.wp_waerme_abgeleitet == 210.0
    beide = imd_typ_beitrag(_Inv(), daten, {
        "verbrauch_daten.heizenergie_kwh": {"abgeleitet": REGEL_JAZ_MODUS_SPLIT},
        "verbrauch_daten.warmwasser_kwh": {"abgeleitet": REGEL_JAZ_VORSCHLAG},
    })
    assert beide.wp_waerme_abgeleitet == 910.0
    assert beide.wp_waerme == 910.0, "die Menge selbst bleibt — abgeleitet heißt nicht weg"


# ── Der Dienst ──────────────────────────────────────────────────────────────

async def _wp_mit_monat(db, *, parameter: dict, daten: dict):
    anlage = Anlage(anlagenname="B1", leistung_kwp=10.0, installationsdatum=date(2026, 1, 1))
    db.add(anlage)
    await db.flush()
    inv = Investition(
        anlage_id=anlage.id, typ="waermepumpe", bezeichnung="WP",
        anschaffungsdatum=date(2026, 1, 1), anschaffungskosten_gesamt=1.0,
        parameter=parameter,
    )
    db.add(inv)
    await db.flush()
    db.add(InvestitionMonatsdaten(investition_id=inv.id, jahr=2026, monat=6, verbrauch_daten=daten))
    await db.commit()
    return anlage, inv


@pytest.mark.asyncio
async def test_dienst_dietmars_juni_schlaegt_null_heizwaerme_und_kein_warmwasser_vor(db):
    anlage, inv = await _wp_mit_monat(
        db, parameter={"wp_art": "luft_luft", "jaz": 3.5},
        daten={"stromverbrauch_kwh": 254.0, "betriebsart_strom_heizen_kwh": 0.0,
               "betriebsart_strom_kuehlen_kwh": 250.0},
    )
    svc = VorschlagService(db)
    heiz = [v for v in await svc.get_vorschlaege(anlage.id, "heizenergie_kwh", 2026, 6, inv.id)
            if v.quelle == VorschlagQuelle.BERECHNUNG]
    ww = [v for v in await svc.get_vorschlaege(anlage.id, "warmwasser_kwh", 2026, 6, inv.id)
          if v.quelle == VorschlagQuelle.BERECHNUNG]
    assert len(heiz) == 1 and heiz[0].wert == 0.0
    assert heiz[0].abgeleitet == REGEL_JAZ_VORSCHLAG
    assert "Strom Heizbetrieb" in heiz[0].beschreibung and "keine Messung" in heiz[0].beschreibung
    assert ww == [], "254 × 3,5 = 889 — genau der Vorschlag, den es nicht mehr gibt"


@pytest.mark.asyncio
async def test_dienst_f2_ein_vorschlag_statt_zwei(db):
    anlage, inv = await _wp_mit_monat(
        db, parameter={"jaz": 3.5}, daten={"stromverbrauch_kwh": 300.0},
    )
    svc = VorschlagService(db)
    heiz = [v for v in await svc.get_vorschlaege(anlage.id, "heizenergie_kwh", 2026, 6, inv.id)
            if v.quelle == VorschlagQuelle.BERECHNUNG]
    ww = [v for v in await svc.get_vorschlaege(anlage.id, "warmwasser_kwh", 2026, 6, inv.id)
          if v.quelle == VorschlagQuelle.BERECHNUNG]
    assert [v.wert for v in heiz] == [1050.0]
    assert heiz[0].details["sprosse"] == "F2"
    assert ww == []


@pytest.mark.asyncio
async def test_dienst_f5_je_funktion_ihr_strom_und_scop_je_funktion(db):
    anlage, inv = await _wp_mit_monat(
        db,
        parameter={"getrennte_strommessung": True, "effizienz_modus": "scop",
                   "scop_heizung": 4.0, "scop_warmwasser": 2.5},
        daten={"strom_heizen_kwh": 200.0, "strom_warmwasser_kwh": 60.0},
    )
    svc = VorschlagService(db)
    heiz = [v for v in await svc.get_vorschlaege(anlage.id, "heizenergie_kwh", 2026, 6, inv.id)
            if v.quelle == VorschlagQuelle.BERECHNUNG]
    ww = [v for v in await svc.get_vorschlaege(anlage.id, "warmwasser_kwh", 2026, 6, inv.id)
          if v.quelle == VorschlagQuelle.BERECHNUNG]
    assert [v.wert for v in heiz] == [800.0]
    assert [v.wert for v in ww] == [150.0]
    assert all(v.abgeleitet == REGEL_JAZ_VORSCHLAG for v in heiz + ww)


@pytest.mark.asyncio
async def test_dienst_ohne_jaz_kein_vorschlag(db):
    anlage, inv = await _wp_mit_monat(db, parameter={}, daten={"stromverbrauch_kwh": 300.0})
    svc = VorschlagService(db)
    heiz = [v for v in await svc.get_vorschlaege(anlage.id, "heizenergie_kwh", 2026, 6, inv.id)
            if v.quelle == VorschlagQuelle.BERECHNUNG]
    assert heiz == []
