"""Nennleistung wird überall über die SoT-Helper gelesen (A24-2, ADR-002/P3-a).

Die #229-Klasse: `Investition.leistung_kwp` existiert als Tabellen-Spalte UND
als Schlüssel im `parameter`-JSON. Welche der beiden gefüllt ist, hängt an der
Herkunft der Komponente — Import- und Altbestand haben die Spalte leer und die
kWp nur im Detail-Feld. Jede Lesestelle, die nur die Spalte kannte, sah dort
still 0.

Dieser Test hält **je nutzersichtbarer Zahl** aus dem A23-Befund eine Fixture
mit exakt dieser Datenlage gegen die betroffene Sicht. Zu jedem „die Zahl
stimmt jetzt"-Fall gehört die Gegenprobe, dass der Spalten-Fall unverändert
bleibt — ein Fix, der beide Wege auf denselben Fallback zieht, wäre keine
Heilung.

Zweiter Strang: die BKW-Formel lag in acht Varianten im Code (Befund §4.1).
`get_bkw_kwp`/`get_erzeuger_kwp` lösen sie ab; getestet sind hier die beiden
Varianten, die dabei ihr Verhalten ändern — der `anzahl`-Default im
BKW-Dashboard (N-D) und der fehlende `or 0` in der Cockpit-Übersicht (N-H).
"""

from __future__ import annotations

from datetime import date, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from backend.api.routes.cockpit.pv_strings import (
    get_pv_strings,
    get_pv_strings_gesamtlaufzeit,
)
from backend.api.routes.cockpit.uebersicht import get_cockpit_uebersicht
from backend.api.routes.investitionen.crud import get_roi_dashboard
from backend.api.routes.investitionen.dashboards import get_balkonkraftwerk_dashboard
from backend.core.berechnungen.co2_amortisation import graue_last_einzeln
from backend.core.berechnungen.spez_ertrag import kwp_aktiv_im_monat
from backend.models import Anlage, Investition, InvestitionMonatsdaten, Monatsdaten
from backend.models.pvgis_prognose import PVGISPrognose
from backend.services.daten_checker import DatenChecker
from backend.services.live_komponenten_builder import build_komponenten

# Dieselbe Nennleistung, einmal in der Spalte und einmal nur im Detail-Feld.
# Beide Fixtures müssen dieselbe Zahl produzieren — das ist der ganze Test.
_KWP = 6.0
_NUR_PARAMETER = {"kwp": _KWP}


# ── Fixture-Bausteine ──────────────────────────────────────────────────────

async def _anlage_zwei_module(db, *, sued_spalte, sued_param) -> int:
    """Zwei PV-Strings 6 + 4 kWp. `sued_*` steuert, WO die 6 kWp stehen.

    Der Ost-String hat seine 4 kWp immer in der Spalte — so ist jede Sicht
    zugleich ein Test auf den GEMISCHTEN Pflegezustand, in dem der Nenner der
    Verteilung zu klein wird und die übrigen Strings zu viel abbekommen.
    """
    anlage = Anlage(anlagenname="Zwei-Strings", leistung_kwp=10.0, latitude=48.0,
                    longitude=11.0)
    db.add(anlage)
    await db.flush()
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2026, monat=5,
                       einspeisung_kwh=300.0, netzbezug_kwh=200.0,
                       pv_erzeugung_kwh=1000.0))
    sued = Investition(anlage_id=anlage.id, typ="pv-module", bezeichnung="Süd",
                       anschaffungsdatum=date(2024, 1, 1),
                       leistung_kwp=sued_spalte, parameter=sued_param,
                       ausrichtung="Süd", neigung_grad=30)
    ost = Investition(anlage_id=anlage.id, typ="pv-module", bezeichnung="Ost",
                      anschaffungsdatum=date(2024, 1, 1), leistung_kwp=4.0,
                      ausrichtung="Ost", neigung_grad=30)
    db.add_all([sued, ost])
    await db.flush()
    db.add(PVGISPrognose(
        anlage_id=anlage.id, abgerufen_am=datetime(2026, 1, 1),
        latitude=48.0, longitude=11.0, neigung_grad=30.0, ausrichtung_grad=0.0,
        jahresertrag_kwh=10000.0, spezifischer_ertrag_kwh_kwp=1000.0,
        gesamt_leistung_kwp=10.0,
        monatswerte=[{"monat": m, "e_m": 1000.0} for m in range(1, 13)],
        ist_aktiv=True,
    ))
    await db.commit()
    return anlage.id


async def _anlage_mit_bkw(db, *, spalte, parameter) -> int:
    anlage = Anlage(anlagenname="BKW", leistung_kwp=0.8)
    db.add(anlage)
    await db.flush()
    bkw = Investition(anlage_id=anlage.id, typ="balkonkraftwerk",
                      bezeichnung="Balkon Süd", anschaffungsdatum=date(2024, 1, 1),
                      leistung_kwp=spalte, parameter=parameter)
    db.add(bkw)
    await db.flush()
    db.add(InvestitionMonatsdaten(
        investition_id=bkw.id, jahr=2026, monat=5,
        verbrauch_daten={"pv_erzeugung_kwh": 80.0, "eigenverbrauch_kwh": 60.0},
    ))
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2026, monat=5,
                       einspeisung_kwh=20.0, netzbezug_kwh=100.0,
                       pv_erzeugung_kwh=80.0))
    await db.commit()
    return anlage.id


def _inv(**kw) -> Investition:
    """Loses ORM-Objekt für die reinen Rechen-Helper (keine DB nötig)."""
    kw.setdefault("bezeichnung", "Modul")
    kw.setdefault("parameter", {})
    return Investition(**kw)


# ── PVGIS: Gesamtprognose der Anlage ───────────────────────────────────────

@pytest.fixture
def pvgis_stub(monkeypatch):
    """`_berechne_pvgis_modul` deterministisch: 1000 kWh je kWp, keine HTTP-I/O.

    Damit ist jede Ertragszahl direkt die kWp, die bei der Berechnung ankam —
    genau die Größe, um die es hier geht.
    """
    from backend.api.routes import pvgis as pvgis_mod
    from backend.api.routes.pvgis import PVGISMonthlyData

    async def _stub(*, leistung_kwp, **_):
        monate = [PVGISMonthlyData(monat=m, e_m=leistung_kwp * 1000 / 12,
                                   h_m=100.0, sd_m=10.0) for m in range(1, 13)]
        return monate, leistung_kwp * 1000

    monkeypatch.setattr(pvgis_mod, "_berechne_pvgis_modul", _stub)


async def test_pvgis_gesamtprognose_enthaelt_das_param_only_modul(db, pvgis_stub):
    """Vorher fiel der Süd-String KOMPLETT aus der Anlagen-Prognose:
    `if not modul.leistung_kwp: continue`. Jahresertrag 4.000 statt 10.000 kWh,
    und die String-Liste zeigte nur ein Modul von zweien."""
    from backend.api.routes.pvgis import get_pvgis_prognose

    anlage_id = await _anlage_zwei_module(db, sued_spalte=None,
                                          sued_param=_NUR_PARAMETER)

    prognose = await get_pvgis_prognose(anlage_id=anlage_id, db=db)

    assert prognose.gesamt_leistung_kwp == pytest.approx(10.0)
    assert prognose.jahresertrag_kwh == pytest.approx(10000.0)
    assert {m.bezeichnung: m.leistung_kwp for m in prognose.module} == {
        "Süd": 6.0, "Ost": 4.0,
    }


async def test_pvgis_gesamtprognose_spaltenfall_unveraendert(db, pvgis_stub):
    """Gegenprobe: mit gepflegter Spalte kommt exakt dasselbe heraus."""
    from backend.api.routes.pvgis import get_pvgis_prognose

    anlage_id = await _anlage_zwei_module(db, sued_spalte=_KWP, sued_param={})

    prognose = await get_pvgis_prognose(anlage_id=anlage_id, db=db)

    assert prognose.gesamt_leistung_kwp == pytest.approx(10.0)
    assert prognose.jahresertrag_kwh == pytest.approx(10000.0)


async def test_pvgis_einzelmodul_liefert_prognose_statt_http_400(db, pvgis_stub):
    """Vorher: HTTP 400 „PV-Modul hat keine Leistung (kWp) definiert" — für ein
    Modul, dessen Nennleistung gepflegt IST."""
    from backend.api.routes.pvgis import get_pvgis_modul_prognose

    anlage_id = await _anlage_zwei_module(db, sued_spalte=None,
                                          sued_param=_NUR_PARAMETER)
    sued = (await db.execute(
        select(Investition).where(Investition.anlage_id == anlage_id,
                                  Investition.bezeichnung == "Süd")
    )).scalar_one()

    resp = await get_pvgis_modul_prognose(investition_id=sued.id, db=db)

    assert resp["leistung_kwp"] == pytest.approx(6.0)
    assert resp["jahresertrag_kwh"] == pytest.approx(6000.0)
    assert resp["spezifischer_ertrag_kwh_kwp"] == pytest.approx(1000.0)


async def test_pvgis_einzelmodul_ohne_jede_kwp_bleibt_400(db, pvgis_stub):
    """Der Fix darf die Prüfung nicht stilllegen: weder Spalte noch
    Detail-Feld ⇒ der harte Fehler ist weiterhin richtig."""
    from fastapi import HTTPException

    from backend.api.routes.pvgis import get_pvgis_modul_prognose

    anlage_id = await _anlage_zwei_module(db, sued_spalte=None, sued_param={})
    sued = (await db.execute(
        select(Investition).where(Investition.anlage_id == anlage_id,
                                  Investition.bezeichnung == "Süd")
    )).scalar_one()

    with pytest.raises(HTTPException) as exc:
        await get_pvgis_modul_prognose(investition_id=sued.id, db=db)
    assert exc.value.status_code == 400


async def test_gespeicherte_prognose_zeigt_kwp_statt_null(db):
    """`/prognose/{id}/aktiv` baut die Multi-String-Anzeige: der param-only
    gepflegte String stand dort mit „0,0 kWp"."""
    from backend.api.routes.pvgis import get_aktive_prognose

    anlage_id = await _anlage_zwei_module(db, sued_spalte=None,
                                          sued_param=_NUR_PARAMETER)
    sued = (await db.execute(
        select(Investition).where(Investition.anlage_id == anlage_id,
                                  Investition.bezeichnung == "Süd")
    )).scalar_one()
    prognose = (await db.execute(
        select(PVGISPrognose).where(PVGISPrognose.anlage_id == anlage_id)
    )).scalar_one()
    prognose.module_monatswerte = {
        str(sued.id): [{"monat": m, "e_m": 500.0} for m in range(1, 13)]
    }
    await db.commit()

    resp = await get_aktive_prognose(anlage_id=anlage_id, db=db)

    modul = next(m for m in resp["module"] if m["investition_id"] == sued.id)
    assert modul["leistung_kwp"] == pytest.approx(6.0)


# ── PV-Strings: SOLL-Verteilung ────────────────────────────────────────────

async def test_pv_strings_soll_verteilung_bei_param_only_modul(db):
    """Vorher: `gesamt_kwp` = 4 statt 10 ⇒ der Süd-String bekam SOLL 0
    (Abweichung −100 %) und der Ost-String das 2,5-fache seines Anteils."""
    anlage_id = await _anlage_zwei_module(db, sued_spalte=None,
                                          sued_param=_NUR_PARAMETER)

    resp = await get_pv_strings(anlage_id=anlage_id, jahr=2026, db=db)

    assert resp.anlagen_leistung_kwp == pytest.approx(10.0)
    assert {s.bezeichnung: s.leistung_kwp for s in resp.strings} == {
        "Süd": 6.0, "Ost": 4.0,
    }
    # SOLL folgt dem kWp-Anteil 60/40 der PVGIS-Monatswerte (1000 kWh im Mai).
    soll = {s.bezeichnung: s.prognose_jahr_kwh for s in resp.strings}
    assert soll["Süd"] == pytest.approx(600.0)
    assert soll["Ost"] == pytest.approx(400.0)


async def test_pv_strings_soll_verteilung_spaltenfall_identisch(db):
    """Gegenprobe: die Zahlen des Spalten-Falls sind dieselben."""
    anlage_id = await _anlage_zwei_module(db, sued_spalte=_KWP, sued_param={})

    resp = await get_pv_strings(anlage_id=anlage_id, jahr=2026, db=db)

    assert resp.anlagen_leistung_kwp == pytest.approx(10.0)
    assert {s.bezeichnung: s.prognose_jahr_kwh for s in resp.strings} == {
        "Süd": pytest.approx(600.0), "Ost": pytest.approx(400.0),
    }


async def test_pv_strings_gesamtlaufzeit_ebenfalls(db):
    """Dieselbe Verteilung in der zweiten Sicht — sie hatte ihre eigene Kopie
    derselben Summe (Befund §1.1, `pv_strings.py:536/560`)."""
    anlage_id = await _anlage_zwei_module(db, sued_spalte=None,
                                          sued_param=_NUR_PARAMETER)

    resp = await get_pv_strings_gesamtlaufzeit(anlage_id=anlage_id, db=db)

    assert resp.anlagen_leistung_kwp == pytest.approx(10.0)
    assert {s.bezeichnung: s.leistung_kwp for s in resp.strings} == {
        "Süd": 6.0, "Ost": 4.0,
    }


# ── Cockpit: Kachel „Anlagenleistung" + spezifischer Ertrag ────────────────

async def test_cockpit_anlagenleistung_und_spez_ertrag(db):
    """Zwei Kacheln aus einer Zeile: `anlagenleistung_kwp` ist zugleich der
    `fallback_kwp` des spezifischen Ertrags. Vorher 4,0 kWp statt 10,0 — und
    ein entsprechend zu hoher spez. Ertrag."""
    anlage_id = await _anlage_zwei_module(db, sued_spalte=None,
                                          sued_param=_NUR_PARAMETER)

    resp = await get_cockpit_uebersicht(anlage_id=anlage_id, jahr=2026, db=db)

    assert resp.anlagenleistung_kwp == pytest.approx(10.0)
    # Gegenprobe gegen den Spalten-Fall: identische Anlage, kWp in der Spalte.
    anlage_spalte = await _anlage_zwei_module(db, sued_spalte=_KWP, sued_param={})
    ref = await get_cockpit_uebersicht(anlage_id=anlage_spalte, jahr=2026, db=db)
    assert resp.anlagenleistung_kwp == pytest.approx(ref.anlagenleistung_kwp)
    assert resp.spezifischer_ertrag_kwh_kwp == pytest.approx(
        ref.spezifischer_ertrag_kwh_kwp)


def test_kwp_aktiv_im_monat_nennt_den_effektiven_wert():
    """Nenner des annualisierten spez. Ertrags (Cockpit-Kachel UND HA-Sensor).
    Bei gemischter Pflege war er zu klein ⇒ Kennzahl zu hoch."""
    module = [
        _inv(typ="pv-module", leistung_kwp=None, parameter={"kwp": 6.0},
             anschaffungsdatum=date(2024, 1, 1)),
        _inv(typ="pv-module", leistung_kwp=4.0, anschaffungsdatum=date(2024, 1, 1)),
    ]

    assert kwp_aktiv_im_monat(module, 2026, 5) == pytest.approx(10.0)


def test_kwp_aktiv_im_monat_bkw_ueber_leistung_wp():
    """BKW-Zweig: `leistung_wp × anzahl` bleibt erhalten, Lese-Default 1."""
    bkw = _inv(typ="balkonkraftwerk", leistung_kwp=None,
               parameter={"leistung_wp": 400, "anzahl": 2},
               anschaffungsdatum=date(2024, 1, 1))
    ohne_anzahl = _inv(typ="balkonkraftwerk", leistung_kwp=None,
                       parameter={"leistung_wp": 400},
                       anschaffungsdatum=date(2024, 1, 1))

    assert kwp_aktiv_im_monat([bkw], 2026, 5) == pytest.approx(0.8)
    assert kwp_aktiv_im_monat([ohne_anzahl], 2026, 5) == pytest.approx(0.4)


# ── ROI: Einsparungs-/CO₂-Anteil je Modul ──────────────────────────────────

async def test_roi_anteil_je_modul_bei_param_only(db):
    """Vorher bekam das param-only gepflegte Modul `anteil = 0` — also 0 €
    Einsparung, 0 kg CO₂ und keine Amortisation, während das andere Modul
    100 % statt 40 % zugerechnet bekam."""
    anlage_id = await _anlage_zwei_module(db, sued_spalte=None,
                                          sued_param=_NUR_PARAMETER)
    for inv in (await db.execute(
        select(Investition).where(Investition.anlage_id == anlage_id)
    )).scalars().all():
        inv.anschaffungskosten_gesamt = 6000.0
    await db.commit()

    resp = await get_roi_dashboard(
        anlage_id=anlage_id, strompreis_cent=30.0, einspeiseverguetung_cent=8.0,
        benzinpreis_euro=None, jahr=2026, db=db,
    )

    # Beide Module sind Orphans (kein Wechselrichter) → eigene ROI-Zeilen.
    anteile = {
        b.investition_bezeichnung: b.detail_berechnung.get("anteil_prozent")
        for b in resp.berechnungen
    }
    assert anteile == {
        "Süd (ohne WR)": pytest.approx(60.0),
        "Ost (ohne WR)": pytest.approx(40.0),
    }, "vorher: Süd 0 %, Ost 100 %"
    # `anteil` ist der Multiplikator für Einsparung UND CO₂ derselben Zeile —
    # mit 0 % gäbe es für das param-only-Modul beides nicht.
    assert all(b.detail_berechnung["anteil_prozent"] > 0
               for b in resp.berechnungen)


async def test_roi_dashboard_ohne_jede_kwp_liefert_keinen_500(db):
    """An der Box gefunden: `anteil` wurde nur INNERHALB des kWp-Zweigs gesetzt,
    danach aber gelesen, sobald `gesamt_kwp > 0`. Ein Modul ganz ohne
    Nennleistung neben einem gepflegten ⇒ `UnboundLocalError` ⇒ **500er im
    ganzen ROI-Dashboard**, nicht nur eine 0 in einer Zeile."""
    anlage_id = await _anlage_zwei_module(db, sued_spalte=None, sued_param={})
    for inv in (await db.execute(
        select(Investition).where(Investition.anlage_id == anlage_id)
    )).scalars().all():
        inv.anschaffungskosten_gesamt = 5000.0
    await db.commit()

    resp = await get_roi_dashboard(
        anlage_id=anlage_id, strompreis_cent=30.0, einspeiseverguetung_cent=8.0,
        benzinpreis_euro=None, jahr=2026, db=db,
    )

    anteile = {
        b.investition_bezeichnung: b.detail_berechnung.get("anteil_prozent")
        for b in resp.berechnungen
    }
    assert anteile == {
        "Süd (ohne WR)": 0,          # keine kWp ⇒ kein Anteil, aber kein Absturz
        "Ost (ohne WR)": pytest.approx(100.0),
    }


# ── Live-Dashboard: Auslastungsbalken der PV-Kachel ────────────────────────

def test_live_komponente_traegt_kwp_aus_dem_detailfeld():
    """Frontend zeigt „Auslastung: X % von Y kWp". Ohne kWp fehlt der Balken
    ersatzlos und ohne Hinweis."""
    anlage = Anlage(anlagenname="Test", leistung_kwp=6.0, standort_land="DE")
    inv = _inv(typ="pv-module", bezeichnung="Süd", leistung_kwp=None,
               parameter={"kwp": 6.0})

    res = build_komponenten(
        anlage, {"pv_gesamt_w": 3000.0, "einspeisung_w": 100.0, "netzbezug_w": None},
        {"pv": {"leistung_w": 3000.0}}, {"pv": inv}, {"pv": {}},
    )

    kachel = next(k for k in res["komponenten"] if k["key"].startswith("pv_"))
    assert kachel["leistung_kwp"] == pytest.approx(6.0)


def test_sonstiger_erzeuger_bleibt_ohne_kwp():
    """Gegenprobe zur Migration: ein BHKW unter „Sonstiges/Erzeuger" bekommt
    bewusst KEINE kWp (keine PV → keine Auslastung in %)."""
    anlage = Anlage(anlagenname="Test", leistung_kwp=6.0, standort_land="DE")
    bhkw = _inv(typ="sonstiges", bezeichnung="BHKW", leistung_kwp=5.0,
                parameter={"kategorie": "erzeuger"})

    res = build_komponenten(
        anlage, {"pv_gesamt_w": 0.0, "einspeisung_w": 0.0, "netzbezug_w": None},
        {"bhkw": {"leistung_w": 2000.0}}, {"bhkw": bhkw}, {"bhkw": {}},
    )

    kachel = next(k for k in res["komponenten"] if k["key"].startswith("sonstige_"))
    assert kachel["leistung_kwp"] is None


# ── CO₂: graue Last / Amortisation ─────────────────────────────────────────

def test_graue_last_pv_aus_dem_detailfeld():
    """Vorher: `0,0 kg` mit Quelle „fehlt" — die Anzeige meldete eine Größe als
    fehlend, die gepflegt ist."""
    inv = _inv(typ="pv-module", leistung_kwp=None, parameter={"kwp": 6.0})
    ref = _inv(typ="pv-module", leistung_kwp=6.0)

    kg, quelle = graue_last_einzeln(inv)
    kg_ref, quelle_ref = graue_last_einzeln(ref)

    assert kg == pytest.approx(kg_ref) and kg > 0
    assert quelle == quelle_ref != "fehlt"


def test_graue_last_bkw_ueber_leistung_wp():
    """Der CO₂-Pfad teilte sich PV und BKW einen Zweig ohne jeden Fallback
    (achte BKW-Variante, Befund §4.1)."""
    bkw = _inv(typ="balkonkraftwerk", leistung_kwp=None,
               parameter={"leistung_wp": 400, "anzahl": 2})
    ref = _inv(typ="balkonkraftwerk", leistung_kwp=0.8)

    assert graue_last_einzeln(bkw)[0] == pytest.approx(graue_last_einzeln(ref)[0])


def test_graue_last_ohne_jede_kwp_bleibt_fehlt():
    """Gegenprobe: ohne gepflegte Nennleistung bleibt „fehlt" richtig."""
    kg, quelle = graue_last_einzeln(_inv(typ="pv-module", leistung_kwp=None))
    assert kg == 0.0 and quelle == "fehlt"


# ── BKW-Dashboard (N-D) + Cockpit-500er (N-H) ──────────────────────────────

async def test_bkw_dashboard_ohne_anzahl_nicht_mehr_doppelte_leistung(db):
    """N-D: das Dashboard las `anzahl` mit Default **2**, alle anderen Stellen
    mit 1. Ein BKW ohne gepflegte `anzahl` wurde mit doppelter Leistung und
    damit halbem spezifischem Ertrag ausgewiesen."""
    anlage_id = await _anlage_mit_bkw(db, spalte=None,
                                      parameter={"leistung_wp": 400})

    resp = await get_balkonkraftwerk_dashboard(
        anlage_id=anlage_id, strompreis_cent=30.0,
        einspeiseverguetung_cent=8.0, db=db)

    zus = resp[0].zusammenfassung
    assert zus["leistung_wp"] == pytest.approx(400.0), "vorher 800 Wp"
    assert zus["anzahl_module"] == 1
    # 80 kWh / 0,4 kWp = 200 kWh/kWp (vorher 100, weil der Nenner doppelt war)
    assert zus["spezifischer_ertrag_kwh_kwp"] == pytest.approx(200.0)


async def test_bkw_dashboard_spalte_gewinnt_gegen_parameter(db):
    """Das Dashboard hatte die Priorität UMGEKEHRT (`parameter` vor Spalte) und
    ignorierte damit den vom Formular gepflegten Spaltenwert."""
    anlage_id = await _anlage_mit_bkw(
        db, spalte=0.8, parameter={"leistung_wp": 300, "anzahl": 1})

    resp = await get_balkonkraftwerk_dashboard(
        anlage_id=anlage_id, strompreis_cent=30.0,
        einspeiseverguetung_cent=8.0, db=db)

    assert resp[0].zusammenfassung["leistung_wp"] == pytest.approx(800.0)


async def test_cockpit_uebersicht_ueberlebt_leistung_wp_null(db):
    """N-H: `params.get("leistung_wp", 0)` OHNE `or 0` warf bei
    `leistung_wp: null` einen TypeError — ein 500er in der Cockpit-Übersicht."""
    anlage_id = await _anlage_mit_bkw(
        db, spalte=None, parameter={"leistung_wp": None, "anzahl": 2})

    resp = await get_cockpit_uebersicht(anlage_id=anlage_id, jahr=2026, db=db)

    assert resp.anlagenleistung_kwp == pytest.approx(0.8), "Anlagen-Fallback"


# ── PDF: Anlagendokumentation (N-I) ────────────────────────────────────────

def test_pdf_nennleistung_aus_dem_detailfeld():
    """Das Dokumentations-PDF verschwieg eine gepflegte Nennleistung: der Guard
    las nur die Spalte und ließ die Zeile ganz weg."""
    from backend.services.pdf.builders.anlagendokumentation import (
        _build_investition_tech_grid,
    )

    grid = dict(_build_investition_tech_grid(
        _inv(typ="pv-module", leistung_kwp=None, parameter={"kwp": 6.0})))

    assert grid["Nennleistung"] == "6.00 kWp"


def test_pdf_speicher_bekommt_kwh_statt_kwp():
    """N-I: `_build_investition_tech_grid` labelte JEDEN Typ als
    „Nennleistung … kWp" — auch den Speicher, dessen Spalte kWh trägt (N-G).
    Falsche Einheit im Dokument, unabhängig von der #229-Frage."""
    from backend.services.pdf.builders.anlagendokumentation import (
        _build_investition_tech_grid,
    )

    speicher = dict(_build_investition_tech_grid(
        _inv(typ="speicher", leistung_kwp=10.0)))
    wr = dict(_build_investition_tech_grid(
        _inv(typ="wechselrichter", leistung_kwp=8.0)))

    assert speicher == {"Kapazität": "10.0 kWh"}
    assert wr == {"Nennleistung": "8.0 kW (AC)"}


# ── Daten-Checker: BKW-Seite des N66-Vergleichs ────────────────────────────

async def _anlage_pv_und_bkw(db, *, bkw_spalte, bkw_param) -> Anlage:
    anlage = Anlage(anlagenname="PV+BKW", leistung_kwp=6.8)
    db.add(anlage)
    await db.flush()
    db.add(Investition(anlage_id=anlage.id, typ="pv-module", bezeichnung="Dach",
                       anschaffungsdatum=date(2022, 5, 1), leistung_kwp=6.0,
                       ausrichtung="Süd", neigung_grad=30, parameter={}))
    db.add(Investition(anlage_id=anlage.id, typ="balkonkraftwerk",
                       bezeichnung="Balkon", anschaffungsdatum=date(2023, 4, 1),
                       leistung_kwp=bkw_spalte, parameter=bkw_param))
    await db.commit()
    return (await db.execute(
        select(Anlage)
        .options(selectinload(Anlage.investitionen).selectinload(Investition.monatsdaten))
        .where(Anlage.id == anlage.id)
    )).scalar_one()


async def test_daten_checker_bkw_kwp_nur_im_detailfeld(db):
    """N66 auf der BKW-Seite: die Duplikat-Formel im Checker kannte den
    `parameter`-kWp-Zweig nicht ⇒ Σ 6,0 statt 6,8 ⇒ Falschmeldung."""
    anlage = await _anlage_pv_und_bkw(db, bkw_spalte=None, bkw_param={"kwp": 0.8})

    ergebnisse = DatenChecker(db)._check_stammdaten(anlage)

    assert not [r for r in ergebnisse
                if "stimmt nicht mit Anlagenleistung überein" in r.meldung], (
        f"Falschmeldung trotz gepflegter kWp: {[r.meldung for r in ergebnisse]}"
    )


async def test_daten_checker_echte_bkw_abweichung_bleibt(db):
    """Gegenprobe: der Fix darf die Prüfung nicht stilllegen."""
    anlage = await _anlage_pv_und_bkw(db, bkw_spalte=None, bkw_param={"kwp": 0.2})

    ergebnisse = DatenChecker(db)._check_stammdaten(anlage)

    treffer = [r for r in ergebnisse
               if "stimmt nicht mit Anlagenleistung überein" in r.meldung]
    assert len(treffer) == 1, f"Befund erwartet: {[r.meldung for r in ergebnisse]}"


async def test_daten_checker_bkw_leistung_wp_weiterhin_erkannt(db):
    """Der bisher einzige BKW-Zweig (`leistung_wp × anzahl`) bleibt erhalten."""
    anlage = await _anlage_pv_und_bkw(
        db, bkw_spalte=None, bkw_param={"leistung_wp": 400, "anzahl": 2})

    ergebnisse = DatenChecker(db)._check_stammdaten(anlage)

    assert not [r for r in ergebnisse
                if "stimmt nicht mit Anlagenleistung überein" in r.meldung]
