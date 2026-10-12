"""Päckchen J — drei Handgriffe zu den verworfenen Nebenfunden L3, L6 und L8 (Analyse `ANALYSE-NEBENFUNDE-L1-L8.md`,
12.10.2026). Keine Register-Funde; je Handgriff eine Probe, am HEAD `0c3a89fa` rot.

* **L3** Daten-Checker «Monate vor dem ersten Tarif»: der Satz nannte nur «Vorbelegung 30 ct/kWh» — die Einspeisung
  rechnet dort mit 8,2 ct, und ein gepflegter Monats-Ø (bzw. Monatssatz) schlägt die Vorbelegung.
* **L6** `get_finanz_prognose` mit PVGIS-Monatswert `e_m = None` (nur aus einer von Hand bearbeiteten Export-Datei):
  `TypeError` in `finanz_prognose.py` (`pv <= 0` bzw. `sum(...)`); jetzt `or 0` wie die Nachbarn.
* **L8** Vorschau des eigenen Formats bei zwei Haupt-Spalten für dasselbe Geräte-Feld (zwei Schreibweisen desselben
  Gerätenamens): der Import schreibt die erste (N-710), die Vorschau zeigte beide Werte — jetzt nur die gewinnende.

Schwesterdateien: test_daten_checker_strompreis_luecke.py (der Checker-Fall), test_n699_pdf_betriebskosten_amortisation.py
(die Prognose mit `e_m = None`), test_n710_csv_suffix_alt_ein_wert.py (Vorschau = Import bei zwei Spalten).
"""

from __future__ import annotations

from datetime import date, datetime

import pytest

from backend.tests import factories
from backend.tests.custom_import_hilfen import csv_text, imd, importiere, vorschau

JAHR, MONAT = 2025, 6


@pytest.mark.asyncio
async def test_l3_checker_nennt_beide_preisseiten_der_vorbelegung(db):
    from backend.models import Anlage, Monatsdaten, Strompreis
    from backend.services.daten_checker import DatenChecker

    a = Anlage(anlagenname="L3", leistung_kwp=5.0)
    db.add(a)
    await db.flush()
    db.add(Strompreis(anlage_id=a.id, netzbezug_arbeitspreis_cent_kwh=30.0, einspeiseverguetung_cent_kwh=8.0,
                      gueltig_ab=date(2025, 9, 1)))
    for m in (7, 8, 9):
        db.add(Monatsdaten(anlage_id=a.id, jahr=2025, monat=m, einspeisung_kwh=100.0, netzbezug_kwh=100.0))
    await db.commit()

    treffer = [e for e in (await DatenChecker(db).check_anlage(a.id)).ergebnisse
               if "vor dem ersten Tarif" in e.meldung]
    assert len(treffer) == 1, [e.meldung for e in treffer]
    details = treffer[0].details or ""
    assert "30 ct/kWh" in details and "8,2 ct/kWh" in details, details
    assert "Monats-Ø" in details and "Monatssatz" in details, details


@pytest.mark.asyncio
async def test_l6_finanz_prognose_rechnet_mit_fehlendem_pvgis_monatswert(db):
    from backend.api.routes.aussichten.finanzen import get_finanz_prognose
    from backend.models.pvgis_prognose import PVGISPrognose
    from backend.tests.test_n699_pdf_betriebskosten_amortisation import _m, _seed

    aid = await _seed(db, monate=_m((2025,)), pv_bk=120.0)
    mw = [{"monat": m, "e_m": 500.0, "h_m": 100.0, "sd_m": 9.0} for m in range(1, 13)]
    mw[2]["e_m"] = None
    db.add(PVGISPrognose(anlage_id=aid, latitude=48.0, longitude=11.0, neigung_grad=30.0, ausrichtung_grad=0.0,
                         system_losses=14.0, jahresertrag_kwh=6000.0, spezifischer_ertrag_kwh_kwp=1000.0,
                         gesamt_leistung_kwp=6.0, monatswerte=mw, ist_aktiv=True,
                         abgerufen_am=datetime(2025, 1, 1, 12, 0)))
    await db.commit()

    p = await get_finanz_prognose(aid, monate=12, db=db)
    assert p.amortisations_fortschritt_prozent is not None
    assert len(p.monatswerte) == 12


@pytest.mark.asyncio
async def test_l8_vorschau_zeigt_bei_zwei_haupt_spalten_nur_die_gewinnende(db):
    """BKW «Balkon», zwei Spalten mit dem Haupt-Suffix (`Balkon_Erzeugung_kWh` = 100, `balkon_Erzeugung_kWh` = 120;
    der normalisierte Präfix trifft beide): der Import schreibt die erste (100), die Vorschau zeigt nur sie."""
    anlage = await factories.anlage(db)
    bkw = await factories.investition(db, anlage.id, "balkonkraftwerk", bezeichnung="Balkon", leistung_kwp=0.8)
    await db.commit()
    zuordnung = [("Jahr", "jahr"), ("Monat", "monat"), ("Einsp", "einspeisung_kwh")]
    text = csv_text(["Jahr", "Monat", "Einsp", "Balkon_Erzeugung_kWh", "balkon_Erzeugung_kWh"],
                    [JAHR, MONAT, 50, 100, 120])

    v = await vorschau(db, anlage.id, text, zuordnung)
    assert v.monate[0].inv_werte == {"Balkon_Erzeugung_kWh": 100.0}, v.monate[0].inv_werte

    antwort = await importiere(db, anlage.id, text, zuordnung, [(JAHR, MONAT)])
    assert antwort.erfolg, antwort.fehler
    assert await imd(db, bkw.id, JAHR, MONAT) == {"pv_erzeugung_kwh": 100.0}


@pytest.mark.asyncio
async def test_l8_vorschau_mehrere_zeilen_zeigt_was_der_import_schreibt(db):
    """Tageswerte: v09 bekommt die Monatssumme je Spalte als EINE Zeile und nimmt die erste Spalte — die Vorschau
    zeigt dieselbe."""
    anlage = await factories.anlage(db)
    bkw = await factories.investition(db, anlage.id, "balkonkraftwerk", bezeichnung="Balkon", leistung_kwp=0.8)
    await db.commit()
    zuordnung = [("Jahr", "jahr"), ("Monat", "monat"), ("Einsp", "einspeisung_kwh")]
    text = csv_text(["Jahr", "Monat", "Einsp", "Balkon_Erzeugung_kWh", "balkon_Erzeugung_kWh"],
                    [JAHR, MONAT, 20, 60, 70], [JAHR, MONAT, 30, 40, 50])

    v = await vorschau(db, anlage.id, text, zuordnung)
    gezeigt = v.monate[0].inv_werte
    assert gezeigt == {"Balkon_Erzeugung_kWh": 100.0}, gezeigt
    antwort = await importiere(db, anlage.id, text, zuordnung, [(JAHR, MONAT)])
    assert antwort.erfolg, antwort.fehler
    assert await imd(db, bkw.id, JAHR, MONAT) == {"pv_erzeugung_kwh": 100.0}
