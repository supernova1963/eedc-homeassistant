"""Phase 2a Etappe 4 — Daten-Migration auf die kanonische Heimladungs-Quelle.

Deckt die Entscheidungen 2–4 ab (docs/KONZEPT-WALLBOX-EAUTO.md):
höherer Wert gewinnt → Wallbox; unauflösbar → stehenlassen; nur aktive Monate;
Multi-Wallbox überspringen. Plus Idempotenz.
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select

from backend.models import Anlage, Investition, InvestitionMonatsdaten
from backend.services.migrations.migrate_emob_canonical_source import (
    migrate_emob_canonical_source,
)

pytestmark = pytest.mark.asyncio


async def _anlage(db) -> int:
    a = Anlage(anlagenname="T", leistung_kwp=10.0)
    db.add(a)
    await db.flush()
    return a.id


async def _inv(db, anlage_id, typ, *, anschaffung=date(2024, 1, 1), parameter=None) -> Investition:
    i = Investition(
        anlage_id=anlage_id, typ=typ, bezeichnung=typ,
        anschaffungsdatum=anschaffung, aktiv=True, parameter=parameter or {},
    )
    db.add(i)
    await db.flush()
    return i


async def _imd(db, inv_id, jahr, monat, vd):
    db.add(InvestitionMonatsdaten(
        investition_id=inv_id, jahr=jahr, monat=monat, verbrauch_daten=vd,
    ))


async def _vd(db, inv_id, jahr, monat) -> dict:
    m = (await db.execute(
        select(InvestitionMonatsdaten).where(
            InvestitionMonatsdaten.investition_id == inv_id,
            InvestitionMonatsdaten.jahr == jahr,
            InvestitionMonatsdaten.monat == monat,
        )
    )).scalar_one_or_none()
    return dict(m.verbrauch_daten) if m and m.verbrauch_daten else (None if m is None else {})


async def test_dual_eauto_groesser_wandert_in_wallbox(db):
    """E-Auto trägt mehr Heimladung als die Wallbox → E-Auto-Trias wandert in
    die Wallbox, E-Auto-Heim-Keys geräumt, km bleibt."""
    aid = await _anlage(db)
    wb = await _inv(db, aid, "wallbox")
    ea = await _inv(db, aid, "e-auto")
    await _imd(db, wb.id, 2026, 4, {"ladung_kwh": 200, "ladung_pv_kwh": 100, "ladung_netz_kwh": 100})
    await _imd(db, ea.id, 2026, 4, {"ladung_kwh": 250, "ladung_pv_kwh": 150,
                                    "ladung_netz_kwh": 100, "km_gefahren": 1200})
    await db.commit()

    await migrate_emob_canonical_source(db)

    wb_vd = await _vd(db, wb.id, 2026, 4)
    assert wb_vd["ladung_kwh"] == 250
    assert wb_vd["ladung_pv_kwh"] == 150
    assert wb_vd["ladung_netz_kwh"] == 100
    ea_vd = await _vd(db, ea.id, 2026, 4)
    assert "ladung_kwh" not in ea_vd and "ladung_pv_kwh" not in ea_vd and "ladung_netz_kwh" not in ea_vd
    assert ea_vd["km_gefahren"] == 1200  # Fahrzeug-Daten bleiben


async def test_dual_wallbox_groesser_nur_eauto_geraeumt(db):
    """Wallbox ist bereits die (größere) Quelle → nur die redundante E-Auto-
    Heimladung wird geräumt, die Wallbox bleibt unangetastet."""
    aid = await _anlage(db)
    wb = await _inv(db, aid, "wallbox")
    ea = await _inv(db, aid, "e-auto")
    await _imd(db, wb.id, 2026, 4, {"ladung_kwh": 500, "ladung_pv_kwh": 300, "ladung_netz_kwh": 200})
    await _imd(db, ea.id, 2026, 4, {"ladung_kwh": 250, "ladung_pv_kwh": 150, "ladung_netz_kwh": 100})
    await db.commit()

    await migrate_emob_canonical_source(db)

    wb_vd = await _vd(db, wb.id, 2026, 4)
    assert wb_vd["ladung_kwh"] == 500 and wb_vd["ladung_pv_kwh"] == 300
    ea_vd = await _vd(db, ea.id, 2026, 4)
    assert not any(k in ea_vd for k in ("ladung_kwh", "ladung_pv_kwh", "ladung_netz_kwh"))


async def test_eauto_ohne_wallbox_imd_legt_wallbox_imd_an(db):
    """E-Auto trägt Heimladung, die Wallbox hat für den Monat keine IMD →
    Wallbox-IMD wird angelegt und bekommt die E-Auto-Trias."""
    aid = await _anlage(db)
    wb = await _inv(db, aid, "wallbox")
    ea = await _inv(db, aid, "e-auto")
    await _imd(db, ea.id, 2026, 4, {"ladung_kwh": 300, "ladung_pv_kwh": 200,
                                    "ladung_netz_kwh": 100, "km_gefahren": 900})
    await db.commit()

    await migrate_emob_canonical_source(db)

    wb_vd = await _vd(db, wb.id, 2026, 4)
    assert wb_vd is not None  # IMD wurde angelegt
    assert wb_vd["ladung_kwh"] == 300 and wb_vd["ladung_pv_kwh"] == 200 and wb_vd["ladung_netz_kwh"] == 100
    ea_vd = await _vd(db, ea.id, 2026, 4)
    assert not any(k in ea_vd for k in ("ladung_kwh", "ladung_pv_kwh", "ladung_netz_kwh"))
    assert ea_vd["km_gefahren"] == 900


async def test_unaufloesbar_total_vs_pv_split_bleibt(db):
    """Wallbox nur Total (kein PV), E-Auto nur PV-Split → Gewinner (WB, Total
    500) hätte keinen PV-Split, Verlierer (EA) schon → unauflösbar, beide
    unverändert (Daten-Checker übernimmt)."""
    aid = await _anlage(db)
    wb = await _inv(db, aid, "wallbox")
    ea = await _inv(db, aid, "e-auto")
    await _imd(db, wb.id, 2026, 4, {"ladung_kwh": 500})            # pv=0, netz=500
    await _imd(db, ea.id, 2026, 4, {"ladung_pv_kwh": 300})         # pv=300, total/netz unklar
    await db.commit()

    await migrate_emob_canonical_source(db)

    wb_vd = await _vd(db, wb.id, 2026, 4)
    assert wb_vd == {"ladung_kwh": 500}
    ea_vd = await _vd(db, ea.id, 2026, 4)
    assert ea_vd == {"ladung_pv_kwh": 300}  # unverändert


async def test_wallbox_inaktiver_monat_eauto_bleibt(db):
    """Vor der Wallbox-Anschaffung (Schuko-Ladung) bleibt das E-Auto die Quelle
    — der Monat wird nicht migriert."""
    aid = await _anlage(db)
    wb = await _inv(db, aid, "wallbox", anschaffung=date(2026, 6, 1))
    ea = await _inv(db, aid, "e-auto", anschaffung=date(2024, 1, 1))
    await _imd(db, ea.id, 2026, 4, {"ladung_kwh": 300, "ladung_pv_kwh": 200, "ladung_netz_kwh": 100})
    await db.commit()

    await migrate_emob_canonical_source(db)

    ea_vd = await _vd(db, ea.id, 2026, 4)
    assert ea_vd["ladung_kwh"] == 300 and ea_vd["ladung_pv_kwh"] == 200  # unverändert
    assert await _vd(db, wb.id, 2026, 4) is None  # keine WB-IMD angelegt


async def test_pre_wallbox_bleibt_post_wallbox_migriert(db):
    """Gemischt: Monat vor Wallbox-Anschaffung bleibt beim E-Auto, Monat nach
    Anschaffung wird in die Wallbox migriert."""
    aid = await _anlage(db)
    wb = await _inv(db, aid, "wallbox", anschaffung=date(2026, 5, 1))
    ea = await _inv(db, aid, "e-auto", anschaffung=date(2024, 1, 1))
    await _imd(db, ea.id, 2026, 4, {"ladung_kwh": 100, "ladung_pv_kwh": 60, "ladung_netz_kwh": 40})
    await _imd(db, ea.id, 2026, 6, {"ladung_kwh": 120, "ladung_pv_kwh": 70, "ladung_netz_kwh": 50})
    await db.commit()

    await migrate_emob_canonical_source(db)

    # April (vor WB): bleibt beim E-Auto
    ea_apr = await _vd(db, ea.id, 2026, 4)
    assert ea_apr["ladung_kwh"] == 100
    assert await _vd(db, wb.id, 2026, 4) is None
    # Juni (nach WB): in die Wallbox migriert
    wb_jun = await _vd(db, wb.id, 2026, 6)
    assert wb_jun["ladung_kwh"] == 120 and wb_jun["ladung_pv_kwh"] == 70
    ea_jun = await _vd(db, ea.id, 2026, 6)
    assert not any(k in ea_jun for k in ("ladung_kwh", "ladung_pv_kwh", "ladung_netz_kwh"))


async def test_multi_wallbox_anlage_uebersprungen(db):
    """Mehrere Wallboxen → mehrdeutiges Ziel → Anlage unverändert."""
    aid = await _anlage(db)
    wb1 = await _inv(db, aid, "wallbox")
    wb2 = await _inv(db, aid, "wallbox")
    ea = await _inv(db, aid, "e-auto")
    await _imd(db, ea.id, 2026, 4, {"ladung_kwh": 300, "ladung_pv_kwh": 200, "ladung_netz_kwh": 100})
    await db.commit()

    await migrate_emob_canonical_source(db)

    ea_vd = await _vd(db, ea.id, 2026, 4)
    assert ea_vd["ladung_kwh"] == 300  # unverändert
    assert await _vd(db, wb1.id, 2026, 4) is None
    assert await _vd(db, wb2.id, 2026, 4) is None


async def test_steckerlader_ohne_wallbox_unveraendert(db):
    """Kein Wallbox-Investition → E-Auto bleibt Quelle, nichts passiert."""
    aid = await _anlage(db)
    ea = await _inv(db, aid, "e-auto")
    await _imd(db, ea.id, 2026, 4, {"ladung_kwh": 800, "ladung_pv_kwh": 500, "ladung_netz_kwh": 300})
    await db.commit()

    await migrate_emob_canonical_source(db)

    ea_vd = await _vd(db, ea.id, 2026, 4)
    assert ea_vd["ladung_kwh"] == 800 and ea_vd["ladung_pv_kwh"] == 500


async def test_idempotent_zweiter_lauf_keine_aenderung(db):
    """Zweiter Lauf findet keine E-Auto-Heimladung mehr → No-op."""
    aid = await _anlage(db)
    wb = await _inv(db, aid, "wallbox")
    ea = await _inv(db, aid, "e-auto")
    await _imd(db, wb.id, 2026, 4, {"ladung_kwh": 100, "ladung_pv_kwh": 50, "ladung_netz_kwh": 50})
    await _imd(db, ea.id, 2026, 4, {"ladung_kwh": 250, "ladung_pv_kwh": 150, "ladung_netz_kwh": 100})
    await db.commit()

    await migrate_emob_canonical_source(db)
    wb_nach_1 = await _vd(db, wb.id, 2026, 4)
    await migrate_emob_canonical_source(db)
    wb_nach_2 = await _vd(db, wb.id, 2026, 4)

    assert wb_nach_1 == wb_nach_2 == {"ladung_kwh": 250, "ladung_pv_kwh": 150, "ladung_netz_kwh": 100}
