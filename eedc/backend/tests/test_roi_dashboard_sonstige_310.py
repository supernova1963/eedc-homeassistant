"""ROI-Dashboard: manuell gepflegte „Sonstige Erträge & Ausgaben" einrechnen — #310.

rilmor-mhrs (#310): Die per Investition/Monat erfassten `sonstige_positionen`
(z. B. Einspeise-Erträge eines zweiten Wechselrichters mit eigenem Tarif)
wurden im ROI-Dashboard (`Auswertung → Monatsberichte → Investitionen`) nie
berücksichtigt — wohl aber im Cockpit-Monatsbericht und in der Aussichten-
Finanzprognose. Dadurch stimmte der ROI in der Auswertungs-Sicht nicht.

`get_roi_dashboard` rechnet die Beträge jetzt über den SoT-Helper
`berechne_sonstige_netto` ein — für alle Typen (Standalone + PV-System +
Orphan-Modul). Bei `jahr=None` auf Jahresbasis gemittelt (gleiche Basis wie
die PV-Einsparungs-Mittelung).
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.api.routes.investitionen.crud import get_roi_dashboard
from backend.models import Anlage, Investition, Monatsdaten
from backend.models.investition import InvestitionMonatsdaten


def _sonstige(positionen: list[dict]) -> dict:
    return {"sonstige_positionen": positionen}


async def _berechnung_fuer(result, inv_id: int):
    return next(b for b in result.berechnungen if b.investition_id == inv_id)


# ============================================================================
# Standalone (typ „sonstiges") — jahr-spezifisch
# ============================================================================


async def test_roi_standalone_sonstige_jahr_spezifisch(db):
    """jahr=2026: das ROI-Netto der Investition = Σ sonstige Netto des Jahres."""
    anlage = Anlage(anlagenname="Test", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    inv = Investition(
        anlage_id=anlage.id, typ="sonstiges", bezeichnung="Zweit-WR-Ertrag",
        anschaffungsdatum=date(2024, 1, 1),
        anschaffungskosten_gesamt=1000.0,
        betriebskosten_jahr=0.0,
        einsparung_prognose_jahr=0.0,
    )
    db.add(inv)
    await db.flush()
    db.add(InvestitionMonatsdaten(
        investition_id=inv.id, jahr=2026, monat=4,
        verbrauch_daten=_sonstige([{"bezeichnung": "THG", "betrag": 200.0, "typ": "ertrag"}]),
    ))
    db.add(InvestitionMonatsdaten(
        investition_id=inv.id, jahr=2026, monat=5,
        verbrauch_daten=_sonstige([{"bezeichnung": "Reparatur", "betrag": 50.0, "typ": "ausgabe"}]),
    ))
    await db.flush()

    result = await get_roi_dashboard(
        anlage_id=anlage.id, strompreis_cent=None, einspeiseverguetung_cent=None,
        benzinpreis_euro=None, jahr=2026, db=db,
    )
    b = await _berechnung_fuer(result, inv.id)
    # 200 € Ertrag − 50 € Ausgabe = 150 € netto
    assert b.detail_berechnung["sonstige_netto_euro"] == pytest.approx(150.0)
    assert b.jahres_einsparung == pytest.approx(150.0)


async def test_roi_standalone_sonstige_jahr_none_gemittelt(db):
    """jahr=None: Σ sonstige Netto über alle Jahre / Anzahl Jahre mit Monatsdaten."""
    anlage = Anlage(anlagenname="Test", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    # Zwei Jahre mit Monatsdaten → Divisor 2 (gleiche Basis wie PV-Mittelung).
    for j in (2025, 2026):
        db.add(Monatsdaten(anlage_id=anlage.id, jahr=j, monat=1,
                           netzbezug_kwh=100.0, einspeisung_kwh=200.0))
    inv = Investition(
        anlage_id=anlage.id, typ="sonstiges", bezeichnung="Ertrag",
        anschaffungsdatum=date(2024, 1, 1),
        anschaffungskosten_gesamt=1000.0,
        betriebskosten_jahr=0.0, einsparung_prognose_jahr=0.0,
    )
    db.add(inv)
    await db.flush()
    db.add(InvestitionMonatsdaten(
        investition_id=inv.id, jahr=2026, monat=4,
        verbrauch_daten=_sonstige([{"bezeichnung": "THG", "betrag": 150.0, "typ": "ertrag"}]),
    ))
    await db.flush()

    result = await get_roi_dashboard(
        anlage_id=anlage.id, strompreis_cent=None, einspeiseverguetung_cent=None,
        benzinpreis_euro=None, jahr=None, db=db,
    )
    b = await _berechnung_fuer(result, inv.id)
    # 150 € / 2 Jahre = 75 €/Jahr
    assert b.detail_berechnung["sonstige_netto_euro"] == pytest.approx(75.0)
    assert b.jahres_einsparung == pytest.approx(75.0)


async def test_roi_standalone_ohne_sonstige_bleibt_null(db):
    """Ohne sonstige Positionen: Feld 0, kein Effekt (Regressions-Schutz)."""
    anlage = Anlage(anlagenname="Test", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    inv = Investition(
        anlage_id=anlage.id, typ="sonstiges", bezeichnung="Leer",
        anschaffungsdatum=date(2024, 1, 1),
        anschaffungskosten_gesamt=1000.0,
        betriebskosten_jahr=0.0, einsparung_prognose_jahr=0.0,
    )
    db.add(inv)
    await db.flush()

    result = await get_roi_dashboard(
        anlage_id=anlage.id, strompreis_cent=None, einspeiseverguetung_cent=None,
        benzinpreis_euro=None, jahr=2026, db=db,
    )
    b = await _berechnung_fuer(result, inv.id)
    assert b.detail_berechnung["sonstige_netto_euro"] == pytest.approx(0.0)
    assert b.jahres_einsparung == pytest.approx(0.0)


# ============================================================================
# PV-System — Roberts Fall: Ertrag am Wechselrichter gepflegt
# ============================================================================


async def test_roi_pv_system_sonstige_am_wechselrichter(db):
    """Sonstige Erträge am WR fließen in den PV-System-ROI (Roberts Fall)."""
    anlage = Anlage(anlagenname="Test", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2026, monat=5,
                       netzbezug_kwh=100.0, einspeisung_kwh=300.0))
    wr = Investition(
        anlage_id=anlage.id, typ="wechselrichter", bezeichnung="WR-2",
        anschaffungsdatum=date(2024, 1, 1), anschaffungskosten_gesamt=2000.0,
    )
    db.add(wr)
    await db.flush()
    pv = Investition(
        anlage_id=anlage.id, typ="pv-module", bezeichnung="Dach-Ost",
        parent_investition_id=wr.id, leistung_kwp=10.0,
        anschaffungsdatum=date(2024, 1, 1), anschaffungskosten_gesamt=10000.0,
    )
    db.add(pv)
    await db.flush()
    db.add(InvestitionMonatsdaten(
        investition_id=pv.id, jahr=2026, monat=5,
        verbrauch_daten={"pv_erzeugung_kwh": 800.0},
    ))
    # Ertrag am Wechselrichter (eigener Einspeisetarif) — Roberts Konstellation.
    db.add(InvestitionMonatsdaten(
        investition_id=wr.id, jahr=2026, monat=5,
        verbrauch_daten=_sonstige([{"bezeichnung": "Einspeise-Sondertarif", "betrag": 120.0, "typ": "ertrag"}]),
    ))
    await db.flush()

    result = await get_roi_dashboard(
        anlage_id=anlage.id, strompreis_cent=30.0, einspeiseverguetung_cent=8.0,
        benzinpreis_euro=None, jahr=2026, db=db,
    )
    system = next(b for b in result.berechnungen if b.investition_typ == "pv-system")
    assert system.detail_berechnung["sonstige_netto_euro"] == pytest.approx(120.0)
