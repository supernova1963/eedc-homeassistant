"""F-37 — die Summe der zugerechneten Posten darf die erzeugte Energie nicht übersteigen.

**Der Befund, an der dev-Box gemessen (18.08.2026, Nachstellung von #381):** Die ROI-Sicht
stellte den Speicher-Spread **neben** die PV-Ersparnis und addierte beides —
2.133 kWh Eigenverbrauch × 31,95 ct **plus** 717,1 kWh Entladung × 23,95 ct.
Ergebnis: **55,9 ct für eine Kilowattstunde, die einmal geflossen ist**
(895,64 € statt 723,89 €, Amortisation 2,24 statt 2,77 Jahre).

`Eigenverbrauch = Erzeugung − Einspeisung` enthält alles, was durch den Speicher
lief: was in den Akku ging und wieder heraus, wurde nicht eingespeist. Am Code
belegt durch `berechnungen/verbrauch.py`, wo die Speicherladung abgezogen wird,
**um** den Direktverbrauch zu erhalten.

**Warum es dieser Test ist und kein weiterer Einzelfall-Test.** Jede beteiligte Formel war
einzeln korrekt und einzeln gewächtert; **3.054 Proben waren grün**. Der Fehler lag in ihrer
**Summe** — und keine Probe addierte zwei Posten und hielt das Ergebnis gegen die physikalische
Menge. Genau das tut dieser Test, und zwar unabhängig davon, wie viele Posten es künftig gibt.
Bauform: `test_netto_ertrag_vier_wege_symmetrie` (v4.0.5), eine Ebene tiefer.

⚠ Er prüft **nicht**, ob die Aufteilung *fair* ist — nur, dass die Summe nicht mehr behauptet,
als die Anlage erzeugt hat. Eine Obergrenze ist die schwächere, aber die haltbare Zusicherung:
sie gilt auch für Posten, die es heute noch nicht gibt.
"""

from __future__ import annotations

from datetime import date, datetime

import pytest

from backend.api.routes.investitionen.crud import get_roi_dashboard
from backend.models import Anlage, Investition, Monatsdaten
from backend.models.investition import InvestitionMonatsdaten

STROM_CT = 31.95
EEG_CT = 8.0


async def _anlage(db, *, speicher_parent: bool, mit_bkw: bool = True):
    """PV + Speicher, wahlweise am Trägergerät (DC) oder eigenständig (AC)."""
    anlage = Anlage(anlagenname="F-37", leistung_kwp=2.0)
    db.add(anlage)
    await db.flush()

    # Erzeugung 1.000 kWh, Einspeisung 300 ⇒ Eigenverbrauch 700 kWh.
    for monat in range(1, 6):
        db.add(Monatsdaten(anlage_id=anlage.id, jahr=2026, monat=monat,
                           einspeisung_kwh=60.0, netzbezug_kwh=200.0))

    parent = None
    if mit_bkw:
        bkw = Investition(
            anlage_id=anlage.id, typ="balkonkraftwerk", bezeichnung="BKW",
            anschaffungsdatum=date(2025, 1, 1), anschaffungskosten_gesamt=700.0,
            parameter={"leistung_wp": 500, "anzahl": 4},
        )
        db.add(bkw)
        await db.flush()
        parent = bkw.id

    modul = Investition(
        anlage_id=anlage.id, typ="pv-module", bezeichnung="Module",
        parent_investition_id=parent, leistung_kwp=2.0,
        anschaffungsdatum=date(2025, 1, 1), anschaffungskosten_gesamt=700.0,
    )
    speicher = Investition(
        anlage_id=anlage.id, typ="speicher", bezeichnung="Akku",
        parent_investition_id=parent if speicher_parent else None,
        leistung_kwp=5.0, anschaffungsdatum=date(2025, 1, 1),
        anschaffungskosten_gesamt=600.0,
        parameter={"kapazitaet_kwh": 5.0, "wirkungsgrad_prozent": 90},
    )
    db.add_all([modul, speicher])
    await db.flush()

    for monat in range(1, 6):
        db.add(InvestitionMonatsdaten(
            investition_id=modul.id, jahr=2026, monat=monat,
            verbrauch_daten={"pv_erzeugung_kwh": 200.0},
        ))
        db.add(InvestitionMonatsdaten(
            investition_id=speicher.id, jahr=2026, monat=monat,
            verbrauch_daten={"ladung_kwh": 80.0, "entladung_kwh": 72.0,
                             "ladung_netz_kwh": 0.0},
        ))
    await db.commit()
    return anlage


async def _dashboard(db, anlage_id):
    return await get_roi_dashboard(
        anlage_id=anlage_id, strompreis_cent=STROM_CT,
        einspeiseverguetung_cent=EEG_CT, benzinpreis_euro=None, jahr=2026, db=db,
    )


def _obergrenze(d) -> float:
    """Was die Anlage höchstens einbringen kann: jede kWh genau einmal.

    Eigenverbrauch zum vollen Strompreis (mehr kann eine selbst verbrauchte
    Kilowattstunde nicht sparen) plus die tatsächliche Einspeisung zur
    Vergütung. Der Speicher **verschiebt** Energie, er erzeugt keine.
    """
    for b in d.berechnungen:
        det = b.detail_berechnung or {}
        if "eigenverbrauch_kwh_jahr" in det:
            return (det["eigenverbrauch_kwh_jahr"] * STROM_CT / 100
                    + det["einspeisung_kwh_jahr"] * EEG_CT / 100)
    raise AssertionError("keine PV-Zeile mit Detailwerten gefunden")


@pytest.mark.parametrize("speicher_parent", [True, False], ids=["dc-am-traeger", "ac-eigenstaendig"])
async def test_summe_ueberschreitet_die_erzeugung_nicht(db, speicher_parent):
    """Die Kernzusicherung — für BEIDE Zuordnungen.

    Der eigenständige Speicher ist dabei der häufigere Fall: ein AC-Speicher
    bringt seinen eigenen Wechselrichter mit und hat darum meist gar keine
    Zuordnung. Ein Fix, der nur den Träger-Zweig repariert, ließe ihn offen.
    """
    anlage = await _anlage(db, speicher_parent=speicher_parent)
    d = await _dashboard(db, anlage.id)

    grenze = _obergrenze(d)
    assert d.gesamt_jahres_einsparung <= grenze + 0.01, (
        f"Summe {d.gesamt_jahres_einsparung:.2f} > Obergrenze {grenze:.2f} — "
        "eine Kilowattstunde wird mehrfach bewertet"
    )


@pytest.mark.parametrize("speicher_parent", [True, False], ids=["dc-am-traeger", "ac-eigenstaendig"])
async def test_zeilensumme_bleibt_die_gesamtzahl(db, speicher_parent):
    """Die Zerlegung darf die Zusicherung `Σ Zeilen == gesamt` nicht brechen."""
    anlage = await _anlage(db, speicher_parent=speicher_parent)
    d = await _dashboard(db, anlage.id)

    summe = sum(b.jahres_einsparung for b in d.berechnungen
                if b.jahres_einsparung is not None)
    assert abs(summe - d.gesamt_jahres_einsparung) < 0.01


async def test_speicher_behaelt_seine_eigene_zahl(db):
    """Weg C, nicht Weg B: die Zurechnung geht nicht verloren.

    Der Speicher soll weiterhin sagen können, was er beiträgt — sonst hätte der
    Nutzer keine Antwort mehr auf „was bringt mir der Akku". Gekürzt wird der
    PV-Topf, nicht die Speicher-Zeile.
    """
    anlage = await _anlage(db, speicher_parent=True)
    d = await _dashboard(db, anlage.id)

    system = next(b for b in d.berechnungen if b.komponenten)
    speicher = next(k for k in system.komponenten if k.typ == "speicher")
    assert speicher.einsparung is not None
    assert speicher.einsparung > 0


async def test_pv_topf_faellt_nicht_unter_null(db):
    """Ein sehr großer Speicher darf keine negative PV-Zeile erzeugen."""
    anlage = Anlage(anlagenname="Riesenakku", leistung_kwp=1.0)
    db.add(anlage)
    await db.flush()
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2026, monat=5,
                       einspeisung_kwh=5.0, netzbezug_kwh=100.0))
    modul = Investition(anlage_id=anlage.id, typ="pv-module", bezeichnung="M",
                        leistung_kwp=1.0, anschaffungsdatum=date(2025, 1, 1),
                        anschaffungskosten_gesamt=500.0)
    speicher = Investition(anlage_id=anlage.id, typ="speicher", bezeichnung="XXL",
                           leistung_kwp=100.0, anschaffungsdatum=date(2025, 1, 1),
                           anschaffungskosten_gesamt=9000.0,
                           parameter={"kapazitaet_kwh": 100.0, "wirkungsgrad_prozent": 95})
    db.add_all([modul, speicher])
    await db.flush()
    db.add(InvestitionMonatsdaten(investition_id=modul.id, jahr=2026, monat=5,
                                  verbrauch_daten={"pv_erzeugung_kwh": 10.0}))
    await db.commit()

    d = await _dashboard(db, anlage.id)
    for b in d.berechnungen:
        if b.jahres_einsparung is not None:
            assert b.jahres_einsparung >= -0.01, f"{b.investition_bezeichnung} negativ"
