"""Charakterisierungs-Netz für die Phase-1-Gruppierung in `get_roi_dashboard`.

Vor der Extraktion des strukturellen Gruppierers (`_gruppiere_investitionen`
→ pv_systeme / standalone / orphan_pv_module) pinnen diese Tests die zwei
Gruppierungs-Ausgänge, die das Bestands-Test-Netz NICHT gezielt abdeckte:

- **Orphan-PV-Modul** (PV-Modul ohne gültige Wechselrichter-Zuordnung) →
  eigene ROIBerechnung mit Suffix „(ohne WR)" + Hinweis.
- **DC-gekoppelter Speicher** (Speicher mit Wechselrichter-Parent) →
  Komponente innerhalb des PV-System-ROI mit `dc_gekoppelt = True`.

(pv-system mit Modul: `test_roi_dashboard_sonstige_310`; Standalone-Typen +
AC-Speicher: `test_roi_dashboard_sonstige_310` / `test_speicher_dashboard_attribut_bug`.)

Reiner Read-Pfad, verhaltensneutral — die Asserts beschreiben den IST-Stand,
damit die nachfolgende Extraktion byte-identisch bleibt.
"""

from __future__ import annotations

from datetime import date

from backend.api.routes.investitionen.crud import get_roi_dashboard
from backend.models import Anlage, Investition, Monatsdaten
from backend.models.investition import InvestitionMonatsdaten


# ============================================================================
# Orphan-PV-Modul: PV-Modul ohne Wechselrichter-Zuordnung
# ============================================================================


async def test_roi_orphan_pv_modul_ohne_wechselrichter(db):
    """PV-Modul ohne parent → eigene Berechnung „(ohne WR)" + Hinweis."""
    anlage = Anlage(anlagenname="Test", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2026, monat=5,
                       netzbezug_kwh=100.0, einspeisung_kwh=300.0))
    pv = Investition(
        anlage_id=anlage.id, typ="pv-module", bezeichnung="Dach-Ost",
        parent_investition_id=None, leistung_kwp=10.0,
        anschaffungsdatum=date(2024, 1, 1), anschaffungskosten_gesamt=10000.0,
    )
    db.add(pv)
    await db.flush()
    db.add(InvestitionMonatsdaten(
        investition_id=pv.id, jahr=2026, monat=5,
        verbrauch_daten={"pv_erzeugung_kwh": 800.0},
    ))
    await db.flush()

    result = await get_roi_dashboard(
        anlage_id=anlage.id, strompreis_cent=30.0, einspeiseverguetung_cent=8.0,
        benzinpreis_euro=None, jahr=2026, db=db,
    )
    orphan = next(b for b in result.berechnungen if b.investition_id == pv.id)
    assert orphan.investition_typ == "pv-module"
    assert orphan.investition_bezeichnung == "Dach-Ost (ohne WR)"
    assert "ohne Wechselrichter-Zuordnung" in orphan.detail_berechnung["hinweis"]
    # Einziges Modul → voller Einsparungsanteil (anteil 100 %).
    assert orphan.detail_berechnung["anteil_prozent"] == 100.0


# ============================================================================
# DC-gekoppelter Speicher: Speicher mit Wechselrichter-Parent
# ============================================================================


async def test_roi_dc_speicher_unter_wechselrichter(db):
    """Speicher mit WR-Parent → Komponente im PV-System (`dc_gekoppelt`)."""
    anlage = Anlage(anlagenname="Test", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2026, monat=5,
                       netzbezug_kwh=100.0, einspeisung_kwh=200.0))
    wr = Investition(
        anlage_id=anlage.id, typ="wechselrichter", bezeichnung="Hybrid-WR",
        anschaffungsdatum=date(2024, 1, 1), anschaffungskosten_gesamt=2000.0,
    )
    db.add(wr)
    await db.flush()
    speicher = Investition(
        anlage_id=anlage.id, typ="speicher", bezeichnung="DC-Speicher",
        parent_investition_id=wr.id,
        anschaffungsdatum=date(2024, 1, 1), anschaffungskosten_gesamt=6000.0,
        parameter={"kapazitaet_kwh": 10, "wirkungsgrad_prozent": 95},
    )
    db.add(speicher)
    await db.flush()
    db.add(InvestitionMonatsdaten(
        investition_id=speicher.id, jahr=2026, monat=5,
        verbrauch_daten={"ladung_kwh": 300.0, "entladung_kwh": 270.0},
    ))
    await db.flush()

    result = await get_roi_dashboard(
        anlage_id=anlage.id, strompreis_cent=30.0, einspeiseverguetung_cent=8.0,
        benzinpreis_euro=None, jahr=2026, db=db,
    )
    # WR mit nur DC-Speicher (ohne PV-Modul) wird als PV-System angezeigt.
    system = next(b for b in result.berechnungen if b.investition_typ == "pv-system")
    speicher_komp = next(
        k for k in system.komponenten if k.investition_id == speicher.id
    )
    assert speicher_komp.detail["dc_gekoppelt"] is True
    # Speicher landet NICHT als eigenständige (AC-)Standalone-Berechnung.
    assert all(b.investition_id != speicher.id for b in result.berechnungen)
