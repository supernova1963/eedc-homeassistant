"""Charakterisierungs-Tests: aktueller_monat.get_aktueller_monat —
per-Investition-Finanzdetails (T-Konto, InvestitionFinancialDetail).

Spur 0 des Backend-Refactoring-Plans: der T-Konto-Block (Zeilen ~1349-1530,
großer Typ-Switch über BKW/Speicher/WP/E-Auto/Wallbox/Sonstiges + Inclusion-
Guard) war laut Profilierung "gar nicht getestet". Diese Tests fixieren das
Verhalten je Typ + die Aufnahme-Regel, bevor ein InvestitionFinancialBuilder
extrahiert wird.

Aktuelles Verhalten (Stand v3.45.0), netz_p = 30 ct, einsp_p = 8 ct (allgemein-Tarif):
  - balkonkraftwerk: ersparnis = (eigenverbrauch|pv) × netz_p; erloes = einspeisung × einsp_p
  - speicher:        ersparnis = entladung × netz_p ("Entladung-Ersparnis")
  - sonstiges:       ersparnis = eigenverbrauch × netz_p; erloes = einspeisung × einsp_p
  - waermepumpe:     ersparnis via berechne_wp_ersparnis (Label "Ersparnis vs. Gas")
  - e-auto dienstlich: Wirtschaftlichkeits-Zweig übersprungen, sonstige Erträge bleiben
  - betriebskosten_monat_euro = betriebskosten_jahr / 12
  - Inclusion-Guard: kein Detail, wenn weder bk noch ersparnis/erloes/sonstige > 0

Geschwister-Datei (Symbol get_aktueller_monat):
  - test_aktueller_monat_datenquellen_prioritaet.py (Quellen-Priorisierung)
  - test_aktueller_monat_connector_override_325.py
"""

from __future__ import annotations

from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.routes.aktueller_monat import get_aktueller_monat
from backend.models import Anlage, Investition, Monatsdaten, Strompreis
from backend.models.investition import InvestitionMonatsdaten

JAHR, MONAT = 2024, 5


def _detail_by_id(res, inv_id):
    for d in res.investitionen_financials:
        if d.investition_id == inv_id:
            return d
    return None


async def _seed_anlage(db: AsyncSession) -> Anlage:
    anlage = Anlage(anlagenname="TKonto", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    db.add(Strompreis(
        anlage_id=anlage.id, verwendung="allgemein", gueltig_ab=date(2024, 1, 1),
        netzbezug_arbeitspreis_cent_kwh=30.0, einspeiseverguetung_cent_kwh=8.0,
    ))
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=JAHR, monat=MONAT,
                       netzbezug_kwh=0.0, einspeisung_kwh=0.0))
    return anlage


async def _add_inv(db, anlage, typ, *, vd: dict, betriebskosten_jahr=None,
                   parameter=None) -> int:
    inv = Investition(anlage_id=anlage.id, typ=typ, bezeichnung=f"{typ}-Test",
                      anschaffungsdatum=date(2024, 1, 1),
                      betriebskosten_jahr=betriebskosten_jahr,
                      parameter=parameter)
    db.add(inv)
    await db.flush()
    if vd is not None:
        db.add(InvestitionMonatsdaten(investition_id=inv.id, jahr=JAHR, monat=MONAT,
                                      verbrauch_daten=vd))
    return inv.id


async def test_bkw_eigenverbrauch_und_einspeise_erloes(db):
    anlage = await _seed_anlage(db)
    bkw_id = await _add_inv(db, anlage, "balkonkraftwerk",
                            vd={"eigenverbrauch_kwh": 100.0, "einspeisung_kwh": 50.0})
    await db.commit()

    res = await get_aktueller_monat(anlage_id=anlage.id, jahr=JAHR, monat=MONAT, db=db)
    d = _detail_by_id(res, bkw_id)
    assert d is not None
    assert d.ersparnis_euro == 30.0   # 100 × 30 ct
    assert d.ersparnis_label == "Eigenverbrauch-Ersparnis"
    assert d.erloes_euro == 4.0        # 50 × 8 ct


async def test_speicher_entladung_ersparnis_und_betriebskosten(db):
    anlage = await _seed_anlage(db)
    sp_id = await _add_inv(db, anlage, "speicher",
                           vd={"entladung_kwh": 80.0}, betriebskosten_jahr=120.0)
    await db.commit()

    res = await get_aktueller_monat(anlage_id=anlage.id, jahr=JAHR, monat=MONAT, db=db)
    d = _detail_by_id(res, sp_id)
    assert d is not None
    assert d.ersparnis_euro == 24.0    # 80 × 30 ct
    assert d.ersparnis_label == "Entladung-Ersparnis"
    assert d.betriebskosten_monat_euro == 10.0  # 120 / 12


async def test_sonstiges_eigenverbrauch_und_erloes(db):
    anlage = await _seed_anlage(db)
    so_id = await _add_inv(db, anlage, "sonstiges",
                           vd={"eigenverbrauch_kwh": 10.0, "einspeisung_kwh": 20.0})
    await db.commit()

    res = await get_aktueller_monat(anlage_id=anlage.id, jahr=JAHR, monat=MONAT, db=db)
    d = _detail_by_id(res, so_id)
    assert d is not None
    assert d.ersparnis_euro == 3.0     # 10 × 30 ct
    assert d.erloes_euro == 1.6        # 20 × 8 ct


async def test_dienstwagen_zweig_uebersprungen_aber_sonstige_ertraege_bleiben(db):
    """E-Auto mit ist_dienstlich: Wirtschaftlichkeits-Ersparnis wird NICHT
    berechnet (kein Verbrenner-Vergleich für Firmenwagen), aber typ-unabhängige
    sonstige Erträge (z.B. AG-Vergütung) erscheinen weiterhin."""
    anlage = await _seed_anlage(db)
    dw_id = await _add_inv(db, anlage, "e-auto",
                           vd={"km_gefahren": 1000.0, "ladung_kwh": 200.0,
                               "sonstige_positionen": [
                                   {"bezeichnung": "AG-Vergütung", "betrag": 50.0,
                                    "typ": "ertrag"}]},
                           parameter={"ist_dienstlich": True})
    await db.commit()

    res = await get_aktueller_monat(anlage_id=anlage.id, jahr=JAHR, monat=MONAT, db=db)
    d = _detail_by_id(res, dw_id)
    assert d is not None
    assert d.ersparnis_euro is None              # Verbrenner-Vergleich übersprungen
    assert d.sonstige_ertraege_euro == 50.0


async def test_waermepumpe_ersparnis_vs_gas_label(db):
    """WP-Zweig verdrahtet berechne_wp_ersparnis korrekt (Label + Wert gesetzt).
    Die Ersparnis-Mathematik selbst ist in test_*wp*-Dateien abgedeckt."""
    anlage = await _seed_anlage(db)
    wp_id = await _add_inv(db, anlage, "waermepumpe",
                           vd={"heizenergie_kwh": 300.0, "stromverbrauch_kwh": 100.0})
    await db.commit()

    res = await get_aktueller_monat(anlage_id=anlage.id, jahr=JAHR, monat=MONAT, db=db)
    d = _detail_by_id(res, wp_id)
    assert d is not None
    assert d.ersparnis_label == "Ersparnis vs. Gas"
    assert d.ersparnis_euro is not None


async def test_inclusion_guard_pv_ohne_finanzwerte_fehlt(db):
    """Eine Investition ohne Betriebskosten/Ersparnis/Erlös/Sonstige (hier ein
    PV-Modul — kein eigener T-Konto-Zweig) erscheint NICHT in der Liste."""
    anlage = await _seed_anlage(db)
    pv_id = await _add_inv(db, anlage, "pv-module",
                           vd={"pv_erzeugung_kwh": 500.0})
    await db.commit()

    res = await get_aktueller_monat(anlage_id=anlage.id, jahr=JAHR, monat=MONAT, db=db)
    assert _detail_by_id(res, pv_id) is None
