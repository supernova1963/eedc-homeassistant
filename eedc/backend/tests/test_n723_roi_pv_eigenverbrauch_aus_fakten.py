"""N-723 — Auswertungen → ROI, Zeile PV-System: der Eigenverbrauch kommt aus den Monats-Fakten (wie Cockpit), ohne den
Anteil des Balkonkraftwerks (das seine eigene Zeile hat, ADR-002/P9).

Am HEAD `7fb9b026` gemessen (Triage 12.10., Nr. 40): die Zeile rechnete `Eigenverbrauch = PV-Module − Einspeisung der
ganzen Anlage` (`roi_pv.py`):

* **BHKW** (Sonstiges-Erzeuger 300 kWh/Monat, Einspeisung 500): 1 560 € / EV 3 600 kWh / CO₂ 1 368 kg — Cockpit → Jahr
  2 640 € (EV 7 200). Vertrag 03.09.2026: der Strom eines sonstigen Erzeugers geht vollständig in EV-Ersparnis und
  Einspeisung der Anlage auf.
* **Abgabe an Dritte** (100 kWh/Monat): 1 824 € — Cockpit → Jahr 1 464 € (EV 3 600); dieselbe kWh stand als Ersparnis UND
  als Erlös der Mieterstrom-Zeile.

Entscheid Master 12.10. (Option A): Anlagen-Eigenverbrauch der Monats-Fakten minus der BKW-Anteil
(`bkw_eigenverbrauch_anteil`). Symmetrie-Probe: ROI PV-System = Cockpit → Jahr minus BKW-Anteil.
"""
from __future__ import annotations

from datetime import date

import pytest

from backend.api.routes.cockpit.jahr import get_cockpit_jahr
from backend.api.routes.investitionen.crud import get_roi_dashboard
from backend.models import Anlage, Investition, InvestitionMonatsdaten, Monatsdaten, Strompreis

J = 2025
AB = date(2024, 1, 1)
NETZ, EINSP = 0.30, 0.08


async def _anlage(db, form: str):
    a = Anlage(anlagenname=form, leistung_kwp=10.0)
    db.add(a)
    await db.flush()
    db.add(Strompreis(anlage_id=a.id, verwendung="allgemein", gueltig_ab=date(2023, 1, 1),
                      netzbezug_arbeitspreis_cent_kwh=30.0, einspeiseverguetung_cent_kwh=8.0))
    wr = Investition(anlage_id=a.id, typ="wechselrichter", bezeichnung="WR", anschaffungsdatum=AB,
                     anschaffungskosten_gesamt=2000.0)
    db.add(wr)
    await db.flush()
    pv = Investition(anlage_id=a.id, typ="pv-module", bezeichnung="Dach", leistung_kwp=10.0, anschaffungsdatum=AB,
                     anschaffungskosten_gesamt=10000.0, parent_investition_id=wr.id)
    db.add(pv)
    await db.flush()
    einsp, extra = 400.0, []
    if form == "bhkw":
        s = Investition(anlage_id=a.id, typ="sonstiges", bezeichnung="BHKW", anschaffungsdatum=AB,
                        anschaffungskosten_gesamt=5000.0, parameter={"kategorie": "erzeuger"})
        db.add(s)
        await db.flush()
        extra.append((s, {"erzeugung_kwh": 300.0}))
        einsp = 500.0
    elif form == "abgabe":
        s = Investition(anlage_id=a.id, typ="sonstiges", bezeichnung="Mieter", anschaffungsdatum=AB,
                        anschaffungskosten_gesamt=500.0, parameter={"kategorie": "abgabe"})
        db.add(s)
        await db.flush()
        extra.append((s, {"abgabe_kwh": 100.0}))
    elif form == "bkw":
        b = Investition(anlage_id=a.id, typ="balkonkraftwerk", bezeichnung="Balkon", leistung_kwp=0.8,
                        anschaffungsdatum=AB, anschaffungskosten_gesamt=600.0)
        db.add(b)
        await db.flush()
        extra.append((b, {"pv_erzeugung_kwh": 60.0}))
        einsp = 415.0
    for m in range(1, 13):
        db.add(Monatsdaten(anlage_id=a.id, jahr=J, monat=m, einspeisung_kwh=einsp, netzbezug_kwh=200.0))
        db.add(InvestitionMonatsdaten(investition_id=pv.id, jahr=J, monat=m, verbrauch_daten={"pv_erzeugung_kwh": 800.0}))
        for inv, d in extra:
            db.add(InvestitionMonatsdaten(investition_id=inv.id, jahr=J, monat=m, verbrauch_daten=dict(d)))
    await db.commit()
    return a, wr


async def _roi_und_cockpit(db, a, wr, jahr=J):
    roi = await get_roi_dashboard(anlage_id=a.id, strompreis_cent=None, einspeiseverguetung_cent=None,
                                  benzinpreis_euro=None, jahr=jahr, db=db)
    zeile = next(b for b in roi.berechnungen if b.investition_id == wr.id)
    k = (await get_cockpit_jahr(anlage_id=a.id, jahr=J, db=db))["kopf"]
    return zeile, (k if isinstance(k, dict) else k.model_dump())


@pytest.mark.asyncio
@pytest.mark.parametrize("form, soll_euro, soll_ev", [
    ("rein", 1824.0, 4800.0),       # Gegenprobe: ohne weitere Erzeuger/Abgabe unverändert
    ("bhkw", 2640.0, 7200.0),       # vorher 1 560 € / 3 600 kWh
    ("abgabe", 1464.0, 3600.0),     # vorher 1 824 € / 4 800 kWh
])
async def test_pv_zeile_gleich_cockpit_jahr(db, form, soll_euro, soll_ev):
    a, wr = await _anlage(db, form)
    zeile, k = await _roi_und_cockpit(db, a, wr)
    assert zeile.detail_berechnung["eigenverbrauch_kwh_jahr"] == pytest.approx(soll_ev)
    assert zeile.jahres_einsparung == pytest.approx(soll_euro, abs=0.01)
    assert zeile.jahres_einsparung == pytest.approx(k["ev_ersparnis_euro"] + k["einspeise_erloes_euro"], abs=0.01)
    # CO₂ auf derselben Menge (DI-2, P15): Eigenverbrauch × Strommix.
    assert zeile.co2_einsparung_kg == pytest.approx(soll_ev * 0.38, abs=0.5)


@pytest.mark.asyncio
async def test_bkw_anteil_zaehlt_nicht_in_der_pv_zeile(db):
    """Balkonkraftwerk 60 kWh/Monat mit eigener ROI-Zeile: Anlagen-EV 445/Monat (Cockpit), BKW-Anteil 445 × 60/860 —
    die PV-Zeile trägt den Rest; sonst stünde der BKW-Eigenverbrauch in zwei Zeilen (P9). Vorher 1 784,40 €."""
    a, wr = await _anlage(db, "bkw")
    zeile, k = await _roi_und_cockpit(db, a, wr)
    bkw_anteil_jahr = 12 * 445.0 * 60.0 / 860.0
    assert k["eigenverbrauch_kwh"] == pytest.approx(5340.0)
    assert zeile.detail_berechnung["eigenverbrauch_kwh_jahr"] == pytest.approx(round(5340.0 - bkw_anteil_jahr), abs=1)
    assert zeile.jahres_einsparung == pytest.approx(
        k["ev_ersparnis_euro"] + k["einspeise_erloes_euro"] - bkw_anteil_jahr * NETZ, abs=0.01)


@pytest.mark.asyncio
async def test_alle_jahre_liest_dieselben_fakten(db):
    """„Alle Jahre" (jahr=None) über dieselben Monats-Fakten: bei einem vollen Jahr dieselbe Zahl wie das Einzeljahr."""
    a, wr = await _anlage(db, "bhkw")
    zeile, _k = await _roi_und_cockpit(db, a, wr, jahr=None)
    assert zeile.jahres_einsparung == pytest.approx(2640.0, abs=0.01)
