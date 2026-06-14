"""Block 1 — gezielte Regressionstests für die BEWUSSTEN Verhaltensänderungen
D1 (WP-Resolver kanonisch) und D3 (Dienstwagen-Filter) in list_monatsdaten_aggregiert.

Diese Site (`/aggregiert`) war vor Block 1 die einzige, die WP-Heizung roh las
(ohne heizung_kwh-Legacy-Fallback) und keinen Dienstwagen-Filter hatte. Beide
Abweichungen sind Maintainer-bestätigte Bugfixes (2026-06-14), nicht im
Char-Netz (das saubere Pipeline-Daten nutzt) abgedeckt — daher hier separat.
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.api.routes.monatsdaten import list_monatsdaten_aggregiert
from backend.models import Anlage, Investition, InvestitionMonatsdaten, Monatsdaten


async def _anlage(db) -> Anlage:
    a = Anlage(anlagenname="D1D3", leistung_kwp=5.0)
    db.add(a)
    await db.flush()
    db.add(Monatsdaten(anlage_id=a.id, jahr=2026, monat=4,
                       einspeisung_kwh=100.0, netzbezug_kwh=100.0))
    return a


def _inv(a, typ, parameter=None):
    return Investition(anlage_id=a.id, typ=typ, bezeichnung=f"{typ}",
                       anschaffungsdatum=date(2024, 1, 1), aktiv=True,
                       parameter=parameter or {})


async def test_d1_wp_legacy_heizung_kwh_kanonisch(db):
    """D1: WP mit Legacy `heizung_kwh` (kein `heizenergie_kwh`) wird jetzt
    kanonisch gelesen — vorher war wp_heizung_kwh fälschlich 0."""
    a = await _anlage(db)
    wp = _inv(a, "waermepumpe")
    db.add(wp)
    await db.flush()
    db.add(InvestitionMonatsdaten(
        investition_id=wp.id, jahr=2026, monat=4,
        verbrauch_daten={"heizung_kwh": 500, "warmwasser_kwh": 100,
                         "stromverbrauch_kwh": 200}))
    await db.commit()

    rows = await list_monatsdaten_aggregiert(anlage_id=a.id, jahr=2026, db=db)
    assert len(rows) == 1
    assert rows[0].wp_heizung_kwh == pytest.approx(500.0)   # Legacy berücksichtigt
    assert rows[0].wp_warmwasser_kwh == pytest.approx(100.0)
    assert rows[0].wp_strom_kwh == pytest.approx(200.0)


async def test_d3_dienstwagen_eauto_ausgeschlossen(db):
    """D3: dienstliches E-Auto fließt nicht mehr in eauto_ladung/km — ohne
    nicht-dienstliche E-Mob bleibt das Feld None (keine IMD beigetragen)."""
    a = await _anlage(db)
    eauto = _inv(a, "e-auto", {"ist_dienstlich": True})
    db.add(eauto)
    await db.flush()
    db.add(InvestitionMonatsdaten(
        investition_id=eauto.id, jahr=2026, monat=4,
        verbrauch_daten={"km_gefahren": 1000, "ladung_pv_kwh": 100,
                         "ladung_netz_kwh": 50}))
    await db.commit()

    rows = await list_monatsdaten_aggregiert(anlage_id=a.id, jahr=2026, db=db)
    assert len(rows) == 1
    assert rows[0].eauto_km is None        # dienstlich → nicht gezählt
    assert rows[0].eauto_ladung_kwh is None


async def test_d3_nicht_dienstlich_weiter_gezaehlt(db):
    """Gegenprobe: nicht-dienstliches E-Auto + Wallbox zählen weiter."""
    a = await _anlage(db)
    eauto = _inv(a, "e-auto")
    wb = _inv(a, "wallbox", {"ist_dienstlich": False})
    db.add_all([eauto, wb])
    await db.flush()
    db.add(InvestitionMonatsdaten(
        investition_id=eauto.id, jahr=2026, monat=4,
        verbrauch_daten={"km_gefahren": 800}))
    db.add(InvestitionMonatsdaten(
        investition_id=wb.id, jahr=2026, monat=4,
        verbrauch_daten={"ladung_kwh": 300, "ladung_pv_kwh": 180}))
    await db.commit()

    rows = await list_monatsdaten_aggregiert(anlage_id=a.id, jahr=2026, db=db)
    assert rows[0].eauto_km == pytest.approx(800.0)
    assert rows[0].wallbox_ladung_kwh == pytest.approx(300.0)
    assert rows[0].wallbox_ladung_pv_kwh == pytest.approx(180.0)
