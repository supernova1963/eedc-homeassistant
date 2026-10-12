"""N-724 — Balkonkraftwerk: eine Ersparnis in Hub und T-Konto, und der Hub-Kopf ist die Summe seiner Monatsreihe.

Am HEAD `7fb9b026` gemessen (Triage 12.10., Nr. 44b/102):

* **T-Konto gegen Hub.** *Cockpit → Monat → T-Konto*, Zeile „Balkon", setzte die **ganze** Erzeugung als Eigenverbrauch an
  (`aktueller_monat/tkonto.py`: ``eigenverbrauch_kwh or pv_erzeugung_kwh``) — 90 kWh × 30 ct = 27,00 €. *Komponenten →
  Balkonkraftwerk* bewertet denselben Monat mit dem Anteil an der Hausbilanz (``bkw_eigenverbrauch_anteil``, ADR-002/P9,
  ``core/berechnungen/bkw_finanz.py``). Jetzt rechnen beide über dieselbe Stelle (``bkw_beitrag_im_monat``).
* **Kopf gegen Reihe.** Die Kopf-Einspeisung war ``Σ Erzeugung − Σ bewerteter EV`` über ALLE Monate, auch über die ohne
  Zählerzeile (nicht bewertbar, Reihe ``None``) — 75,1 gegen Σ Reihe 15,1; die EV-Quote teilte durch die Erzeugung aller
  Monate (28,5 % gegen 66,5 %). Und eine gespeicherte Einspeisung in EINEM Monat verdrängte die abgeleitete der übrigen.
"""
from __future__ import annotations

from datetime import date

import pytest

from backend.api.routes.aktueller_monat import get_aktueller_monat
from backend.api.routes.investitionen.dashboard_balkonkraftwerk import get_balkonkraftwerk_dashboard
from backend.models import Anlage, Investition, InvestitionMonatsdaten, Monatsdaten, Strompreis

J = 2025
AB = date(2024, 1, 1)


async def _anlage(db, name: str) -> Anlage:
    a = Anlage(anlagenname=name, leistung_kwp=10.0)
    db.add(a)
    await db.flush()
    db.add(Strompreis(anlage_id=a.id, verwendung="allgemein", gueltig_ab=date(2023, 1, 1),
                      netzbezug_arbeitspreis_cent_kwh=30.0, einspeiseverguetung_cent_kwh=8.0))
    return a


def _inv(a, typ, name, kwp, **kw) -> Investition:
    return Investition(anlage_id=a.id, typ=typ, bezeichnung=name, leistung_kwp=kwp, anschaffungsdatum=AB,
                       anschaffungskosten_gesamt=100.0, **kw)


def _tkonto_bkw(res, bkw_id):
    return next((d for d in res.investitionen_financials if d.investition_id == bkw_id), None)


@pytest.mark.asyncio
async def test_tkonto_balkon_gleich_hub_mit_dachanlage(db):
    """Dach 900 + Balkon 90 kWh, Einspeisung 300 ⇒ Anlagen-EV 690, Anteil Balkon 690 × 90/990 = 62,73 kWh ⇒ 18,82 €.

    Hub-Monat und T-Konto-Zeile nennen dieselbe Zahl; vorher T-Konto 27,00 € (90 × 30 ct)."""
    a = await _anlage(db, "Hub=T-Konto")
    dach, bkw = _inv(a, "pv-module", "Dach", 9.0), _inv(a, "balkonkraftwerk", "Balkon", 0.8)
    db.add_all([dach, bkw])
    await db.flush()
    db.add(Monatsdaten(anlage_id=a.id, jahr=J, monat=6, einspeisung_kwh=300.0, netzbezug_kwh=200.0))
    db.add(InvestitionMonatsdaten(investition_id=dach.id, jahr=J, monat=6, verbrauch_daten={"pv_erzeugung_kwh": 900.0}))
    db.add(InvestitionMonatsdaten(investition_id=bkw.id, jahr=J, monat=6, verbrauch_daten={"pv_erzeugung_kwh": 90.0}))
    await db.commit()

    (karte,) = await get_balkonkraftwerk_dashboard(anlage_id=a.id, strompreis_cent=None, db=db)
    hub_euro = karte.zusammenfassung["gesamt_ersparnis_euro"]
    assert hub_euro == pytest.approx(690.0 * 90.0 / 990.0 * 0.30, abs=0.01)

    res = await get_aktueller_monat(anlage_id=a.id, jahr=J, monat=6, db=db)
    zeile = _tkonto_bkw(res, bkw.id)
    assert zeile is not None
    assert zeile.ersparnis_euro == pytest.approx(hub_euro, abs=0.01)
    assert zeile.ersparnis_euro != pytest.approx(27.0)


@pytest.mark.asyncio
async def test_tkonto_balkon_abgetreten_traegt_nichts(db):
    """Balkon mit eigenem Zähler 90 kWh und Modul-Kindern (ADR-002/P11): die Kinder tragen, der Hub nennt 0 € — das
    T-Konto hat dann keine Balkon-Ersparnis (vorher 27,00 €, zusätzlich zur Erzeugung der Kinder im Anlagen-EV)."""
    a = await _anlage(db, "abgetreten")
    bkw = _inv(a, "balkonkraftwerk", "Balkon", 0.8)
    db.add(bkw)
    await db.flush()
    k1 = _inv(a, "pv-module", "Kind 1", 0.3, parent_investition_id=bkw.id)
    k2 = _inv(a, "pv-module", "Kind 2", 0.5, parent_investition_id=bkw.id)
    db.add_all([k1, k2])
    await db.flush()
    db.add(Monatsdaten(anlage_id=a.id, jahr=J, monat=6, einspeisung_kwh=25.0, netzbezug_kwh=200.0))
    db.add(InvestitionMonatsdaten(investition_id=bkw.id, jahr=J, monat=6, verbrauch_daten={"pv_erzeugung_kwh": 90.0}))
    await db.commit()

    (karte,) = await get_balkonkraftwerk_dashboard(anlage_id=a.id, strompreis_cent=None, db=db)
    assert karte.zusammenfassung["gesamt_ersparnis_euro"] == 0.0
    res = await get_aktueller_monat(anlage_id=a.id, jahr=J, monat=6, db=db)
    zeile = _tkonto_bkw(res, bkw.id)
    assert zeile is None or not zeile.ersparnis_euro


@pytest.mark.asyncio
async def test_hub_kopf_gleich_summe_der_reihe_monat_ohne_zaehlerzeile(db):
    """Fall A: Juni mit Zählerzeile (Balkon allein 45,1, Einspeisung 15,1 ⇒ EV 30,0), Juli 60 kWh ohne Zählerzeile
    (nicht bewertbar). Kopf-Einspeisung = Σ Reihe = 15,1 (vorher 75,1); EV-Quote über die bewertbaren Monate 66,5 %
    (vorher 28,5 %)."""
    a = await _anlage(db, "Fall A")
    bkw = _inv(a, "balkonkraftwerk", "Balkon", 0.8)
    db.add(bkw)
    await db.flush()
    db.add(Monatsdaten(anlage_id=a.id, jahr=J, monat=6, einspeisung_kwh=15.1, netzbezug_kwh=80.0))
    db.add(InvestitionMonatsdaten(investition_id=bkw.id, jahr=J, monat=6, verbrauch_daten={"pv_erzeugung_kwh": 45.1}))
    db.add(InvestitionMonatsdaten(investition_id=bkw.id, jahr=J, monat=7, verbrauch_daten={"pv_erzeugung_kwh": 60.0}))
    await db.commit()

    (karte,) = await get_balkonkraftwerk_dashboard(anlage_id=a.id, strompreis_cent=None, db=db)
    reihe = karte.monatsreihe
    z = karte.zusammenfassung
    sigma_einsp = sum(m.einspeisung_kwh for m in reihe if m.einspeisung_kwh is not None)
    assert sigma_einsp == pytest.approx(15.1, abs=0.05)
    assert z["gesamt_einspeisung_kwh"] == pytest.approx(round(sigma_einsp, 1))
    assert z["gesamt_eigenverbrauch_kwh"] == pytest.approx(
        round(sum(m.eigenverbrauch_kwh for m in reihe if m.eigenverbrauch_kwh is not None), 1))
    assert z["eigenverbrauch_quote_prozent"] == pytest.approx(66.5, abs=0.1)


@pytest.mark.asyncio
async def test_hub_kopf_gleich_summe_der_reihe_gespeicherte_einspeisung(db):
    """Fall B: Juni mit gespeicherter BKW-Einspeisung 10,0 (Altbestand), Juli ohne — Juli leitet ab (Erzeugung − EV).
    Kopf = Σ Reihe (vorher Kopf 10,0: die gespeicherte verdrängte die abgeleitete)."""
    a = await _anlage(db, "Fall B")
    bkw = _inv(a, "balkonkraftwerk", "Balkon", 0.8)
    db.add(bkw)
    await db.flush()
    for m in (6, 7):
        db.add(Monatsdaten(anlage_id=a.id, jahr=J, monat=m, einspeisung_kwh=15.1, netzbezug_kwh=80.0))
    db.add(InvestitionMonatsdaten(investition_id=bkw.id, jahr=J, monat=6,
                                  verbrauch_daten={"pv_erzeugung_kwh": 45.1, "einspeisung_kwh": 10.0}))
    db.add(InvestitionMonatsdaten(investition_id=bkw.id, jahr=J, monat=7, verbrauch_daten={"pv_erzeugung_kwh": 45.1}))
    await db.commit()

    (karte,) = await get_balkonkraftwerk_dashboard(anlage_id=a.id, strompreis_cent=None, db=db)
    sigma_einsp = sum(m.einspeisung_kwh for m in karte.monatsreihe if m.einspeisung_kwh is not None)
    assert sigma_einsp == pytest.approx(25.1, abs=0.05)
    assert karte.zusammenfassung["gesamt_einspeisung_kwh"] == pytest.approx(round(sigma_einsp, 1))


@pytest.mark.asyncio
async def test_hub_und_tkonto_mit_dem_ev_preis_des_monats(db):
    """Entscheid Master 12.10.: Hub und T-Konto bewerten mit DEMSELBEN Preis — dem EV-Preis des Monats (P9: der
    BKW-Eigenverbrauch zählt wie Eigenverbrauch). Lage mit gemessenem EV-Ø (`test_n607`: EV-Preis 10 ct, Bezug 40 ct):
    BKW 50 kWh neben Dach 1 000, Einspeisung 600 ⇒ Anteil 450 × 50/1 050 = 21,43 kWh ⇒ 2,14 €. Vorher Hub 30 ct
    (Stammpreis, 6,43 €) gegen T-Konto 10 ct."""
    from backend.tests.test_n607_ev_preis_monatsroute import _anlage as _flex_anlage

    aid = await _flex_anlage(db)
    bkw = Investition(anlage_id=aid, typ="balkonkraftwerk", bezeichnung="Balkon", leistung_kwp=0.8,
                      anschaffungsdatum=date(2024, 1, 1))
    db.add(bkw)
    await db.flush()
    db.add(InvestitionMonatsdaten(investition_id=bkw.id, jahr=2025, monat=7, verbrauch_daten={"pv_erzeugung_kwh": 50.0}))
    await db.commit()

    res = await get_aktueller_monat(anlage_id=aid, jahr=2025, monat=7, db=db)
    zeile = _tkonto_bkw(res, bkw.id)
    soll = 450.0 * 50.0 / 1050.0 * 0.10
    assert zeile.ersparnis_euro == pytest.approx(soll, abs=0.01)

    (karte,) = await get_balkonkraftwerk_dashboard(anlage_id=aid, strompreis_cent=None, db=db)
    # Der Hub summiert über alle Monate; das BKW hat nur Juli 2025.
    assert karte.zusammenfassung["ersparnis_eigenverbrauch_euro"] == pytest.approx(zeile.ersparnis_euro, abs=0.01)
