"""Phase 2a Etappe 4 — Daten-Migration auf die kanonische Heimladungs-Quelle.

Deckt die Entscheidungen 2–4 ab (docs/KONZEPT-WALLBOX-EAUTO.md):
höherer Wert gewinnt → Wallbox; unauflösbar → stehenlassen; nur aktive Monate;
Multi-Wallbox überspringen. Plus Idempotenz.
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select

from backend.models import Investition, InvestitionMonatsdaten
from backend.services.migrations.migrate_emob_canonical_source import (
    migrate_emob_canonical_source,
)
from backend.tests import factories

pytestmark = pytest.mark.asyncio


async def _anlage(db) -> int:
    return (await factories.anlage(db, anlagenname="T")).id


async def _inv(db, anlage_id, typ, *, anschaffung=date(2024, 1, 1), parameter=None) -> Investition:
    i = Investition(
        anlage_id=anlage_id, typ=typ, bezeichnung=typ,
        anschaffungsdatum=anschaffung, aktiv=True, parameter=parameter or {},
    )
    db.add(i)
    await db.flush()
    return i


async def _imd(db, inv_id, jahr, monat, vd):
    await factories.imd(db, inv_id, jahr, monat, vd)


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


# ── RF-42 (3.11.2026): benannte Proben für die Zweige, die die Proben oben nicht trafen ──────────────────────
# Gemessen mit einer Zeilenspur (sys.settrace) der neun Proben oben über `migrate_emob_canonical_source`: ungesehen
# waren das inaktive E-Auto (beim Sammeln der Monate und beim Summieren), die Summe ≤ 0, der Fehler im
# Aktivitätsprotokoll; dazu die Gegen-Seiten der Bedingungen (E-Auto-Zeile ohne Heimladung, E-Auto-Zeile ohne
# Heim-Keys, Dienstwagen, Protokoll ohne Befund) und die Zähler im Protokoll. Vor dem Schnitt am HEAD grün.

_MIG_LOGGER = "backend.services.migrations.migrate_emob_canonical_source"


async def test_eauto_vor_seiner_anschaffung_bleibt(db):
    """Eine E-Auto-Zeile aus einem Monat, in dem das E-Auto noch nicht aktiv war, zählt nicht — unverändert."""
    aid = await _anlage(db)
    wb = await _inv(db, aid, "wallbox")
    ea = await _inv(db, aid, "e-auto", anschaffung=date(2026, 6, 1))
    await _imd(db, ea.id, 2026, 4, {"ladung_kwh": 300, "ladung_pv_kwh": 200, "ladung_netz_kwh": 100})
    await db.commit()

    await migrate_emob_canonical_source(db)

    assert await _vd(db, ea.id, 2026, 4) == {"ladung_kwh": 300, "ladung_pv_kwh": 200, "ladung_netz_kwh": 100}
    assert await _vd(db, wb.id, 2026, 4) is None


async def test_zweites_eauto_inaktiv_im_monat_zaehlt_nicht_mit(db):
    """Zwei E-Autos, das zweite im Monat noch nicht aktiv: nur das erste wandert, das zweite bleibt stehen."""
    aid = await _anlage(db)
    wb = await _inv(db, aid, "wallbox")
    ea1 = await _inv(db, aid, "e-auto")
    ea2 = await _inv(db, aid, "e-auto", anschaffung=date(2026, 6, 1))
    await _imd(db, ea1.id, 2026, 4, {"ladung_kwh": 100, "ladung_pv_kwh": 60, "ladung_netz_kwh": 40})
    await _imd(db, ea2.id, 2026, 4, {"ladung_kwh": 400, "ladung_pv_kwh": 300, "ladung_netz_kwh": 100})
    await db.commit()

    await migrate_emob_canonical_source(db)

    assert await _vd(db, wb.id, 2026, 4) == {"ladung_kwh": 100, "ladung_pv_kwh": 60, "ladung_netz_kwh": 40}
    assert await _vd(db, ea1.id, 2026, 4) == {}
    assert await _vd(db, ea2.id, 2026, 4) == {"ladung_kwh": 400, "ladung_pv_kwh": 300, "ladung_netz_kwh": 100}


async def test_zwei_eautos_summe_wandert_zweites_ohne_heim_keys_unberuehrt(db):
    """Zwei aktive E-Autos: die Summe der Heimladung wandert; das zweite trägt nur km und bleibt wie es ist."""
    aid = await _anlage(db)
    wb = await _inv(db, aid, "wallbox")
    ea1 = await _inv(db, aid, "e-auto")
    ea2 = await _inv(db, aid, "e-auto")
    await _imd(db, ea1.id, 2026, 4, {"ladung_kwh": 100.0004, "ladung_pv_kwh": 60.0004, "ladung_netz_kwh": 40,
                                     "km_gefahren": 800})
    await _imd(db, ea2.id, 2026, 4, {"km_gefahren": 500})
    await db.commit()

    await migrate_emob_canonical_source(db)

    assert await _vd(db, wb.id, 2026, 4) == {"ladung_kwh": 100.0, "ladung_pv_kwh": 60.0, "ladung_netz_kwh": 40}
    assert await _vd(db, ea1.id, 2026, 4) == {"km_gefahren": 800}
    assert await _vd(db, ea2.id, 2026, 4) == {"km_gefahren": 500}


async def test_eauto_zeile_ohne_heimladung_wird_nicht_angefasst(db):
    """Eine E-Auto-Zeile ohne Heimladung (nur km) öffnet keinen Monat — keine Wallbox-Zeile entsteht."""
    aid = await _anlage(db)
    wb = await _inv(db, aid, "wallbox")
    ea = await _inv(db, aid, "e-auto")
    await _imd(db, ea.id, 2026, 4, {"km_gefahren": 900})
    await db.commit()

    await migrate_emob_canonical_source(db)

    assert await _vd(db, ea.id, 2026, 4) == {"km_gefahren": 900}
    assert await _vd(db, wb.id, 2026, 4) is None


async def test_summe_der_eautos_nicht_positiv_bleibt(db):
    """Eine negative Korrekturzeile am zweiten E-Auto drückt die Monatssumme unter null — der Monat bleibt."""
    aid = await _anlage(db)
    wb = await _inv(db, aid, "wallbox")
    ea1 = await _inv(db, aid, "e-auto")
    ea2 = await _inv(db, aid, "e-auto")
    await _imd(db, ea1.id, 2026, 4, {"ladung_kwh": 100, "ladung_pv_kwh": 50, "ladung_netz_kwh": 50})
    await _imd(db, ea2.id, 2026, 4, {"ladung_pv_kwh": -60, "ladung_netz_kwh": -60})
    await db.commit()

    await migrate_emob_canonical_source(db)

    assert await _vd(db, ea1.id, 2026, 4) == {"ladung_kwh": 100, "ladung_pv_kwh": 50, "ladung_netz_kwh": 50}
    assert await _vd(db, ea2.id, 2026, 4) == {"ladung_pv_kwh": -60, "ladung_netz_kwh": -60}
    assert await _vd(db, wb.id, 2026, 4) is None


async def test_dienstwagen_wird_nicht_migriert(db):
    """Ein dienstliches E-Auto ist nicht Teil der Heimladung — die Anlage zählt als «ohne E-Auto»."""
    aid = await _anlage(db)
    wb = await _inv(db, aid, "wallbox")
    ea = await _inv(db, aid, "e-auto", parameter={"ist_dienstlich": True})
    await _imd(db, ea.id, 2026, 4, {"ladung_kwh": 300, "ladung_pv_kwh": 200, "ladung_netz_kwh": 100})
    await db.commit()

    await migrate_emob_canonical_source(db)

    assert await _vd(db, ea.id, 2026, 4) == {"ladung_kwh": 300, "ladung_pv_kwh": 200, "ladung_netz_kwh": 100}
    assert await _vd(db, wb.id, 2026, 4) is None


async def test_dienstliche_wallbox_zaehlt_nicht_als_zweite(db):
    """Eine dienstliche Wallbox neben der privaten macht die Anlage nicht mehrdeutig — Ziel ist die private."""
    aid = await _anlage(db)
    wb = await _inv(db, aid, "wallbox")
    wb_dienst = await _inv(db, aid, "wallbox", parameter={"ist_dienstlich": True})
    ea = await _inv(db, aid, "e-auto")
    await _imd(db, ea.id, 2026, 4, {"ladung_kwh": 300, "ladung_pv_kwh": 200, "ladung_netz_kwh": 100})
    await db.commit()

    await migrate_emob_canonical_source(db)

    assert await _vd(db, wb.id, 2026, 4) == {"ladung_kwh": 300, "ladung_pv_kwh": 200, "ladung_netz_kwh": 100}
    assert await _vd(db, wb_dienst.id, 2026, 4) is None
    assert await _vd(db, ea.id, 2026, 4) == {}


def _protokoll_abfangen(monkeypatch) -> list[dict]:
    from backend.services import activity_service

    aufrufe: list[dict] = []

    async def _log_activity(**kwargs):
        aufrufe.append({k: v for k, v in kwargs.items() if k != "db"})

    monkeypatch.setattr(activity_service, "log_activity", _log_activity)
    return aufrufe


async def test_zaehler_im_protokoll_und_aktivitaet(db, monkeypatch, caplog):
    """Vier Anlagen, je ein Ausgang: Zähler in der Log-Zeile und im Aktivitätsprotokoll stehen wortgleich."""
    aufrufe = _protokoll_abfangen(monkeypatch)
    caplog.set_level("INFO", logger=_MIG_LOGGER)
    # A: April E-Auto gewinnt (migriert), Mai Wallbox gewinnt (nur geleert)
    a = await _anlage(db)
    wb_a = await _inv(db, a, "wallbox")
    ea_a = await _inv(db, a, "e-auto")
    await _imd(db, ea_a.id, 2026, 4, {"ladung_kwh": 250, "ladung_pv_kwh": 150, "ladung_netz_kwh": 100})
    await _imd(db, wb_a.id, 2026, 5, {"ladung_kwh": 500, "ladung_pv_kwh": 300, "ladung_netz_kwh": 200})
    await _imd(db, ea_a.id, 2026, 5, {"ladung_kwh": 250, "ladung_pv_kwh": 150, "ladung_netz_kwh": 100})
    # B: unauflösbar
    b = await _anlage(db)
    wb_b = await _inv(db, b, "wallbox")
    ea_b = await _inv(db, b, "e-auto")
    await _imd(db, wb_b.id, 2026, 4, {"ladung_kwh": 500})
    await _imd(db, ea_b.id, 2026, 4, {"ladung_pv_kwh": 300})
    # C: zwei Wallboxen
    c = await _anlage(db)
    await _inv(db, c, "wallbox")
    await _inv(db, c, "wallbox")
    ea_c = await _inv(db, c, "e-auto")
    await _imd(db, ea_c.id, 2026, 4, {"ladung_kwh": 300})
    # D: nur E-Auto
    d = await _anlage(db)
    ea_d = await _inv(db, d, "e-auto")
    await _imd(db, ea_d.id, 2026, 4, {"ladung_kwh": 300})
    await db.commit()

    await migrate_emob_canonical_source(db)

    assert [r.getMessage() for r in caplog.records if r.name == _MIG_LOGGER] == [
        "Phase-2a-Emob-Migration: 1 Monate Trias→Wallbox, 1 Monate nur E-Auto geräumt, 1 unauflösbar "
        "(Daten-Checker), 1 Multi-WB-Anlagen übersprungen, 1 Anlagen betroffen."
    ]
    assert aufrufe == [{
        "kategorie": "migration",
        "aktion": "E-Mob-Heimladung auf Wallbox konsolidiert (Phase 2a)",
        "details": (
            "1 Anlage(n): 1 Monate E-Auto-Heimladung in die Wallbox verschoben, 1 Monate nur das (redundante) "
            "E-Auto geräumt. 1 Monat(e) blieben unverändert (uneindeutige Daten → Daten-Checker), 1 Anlage(n) mit "
            "mehreren Wallboxen übersprungen. Heimladung wird ab jetzt kanonisch an der Wallbox geführt."
        ),
        "erfolg": True,
    }]


@pytest.mark.parametrize("fall", ["ohne_befund", "nur_unaufloesbar", "nur_multi_wallbox"])
async def test_aktivitaet_nur_bei_befund(db, monkeypatch, fall):
    """Das Aktivitätsprotokoll schreibt, sobald eine der drei Zahlen (betroffen · unauflösbar · Multi-WB) > 0 ist."""
    aufrufe = _protokoll_abfangen(monkeypatch)
    aid = await _anlage(db)
    ea = await _inv(db, aid, "e-auto")
    if fall == "nur_unaufloesbar":
        wb = await _inv(db, aid, "wallbox")
        await _imd(db, wb.id, 2026, 4, {"ladung_kwh": 500})
        await _imd(db, ea.id, 2026, 4, {"ladung_pv_kwh": 300})
    else:
        await _imd(db, ea.id, 2026, 4, {"ladung_kwh": 300})
    if fall == "nur_multi_wallbox":
        await _inv(db, aid, "wallbox")
        await _inv(db, aid, "wallbox")
    await db.commit()

    await migrate_emob_canonical_source(db)

    assert len(aufrufe) == (0 if fall == "ohne_befund" else 1)


async def test_fehler_im_aktivitaetsprotokoll_bricht_nicht_ab(db, monkeypatch, caplog):
    """Wirft das Aktivitätsprotokoll, bleibt die Migration geschrieben (Commit davor) und das Log nennt den Fehler."""
    from backend.services import activity_service

    async def _wirft(**_kwargs):
        raise RuntimeError("gestellt")

    monkeypatch.setattr(activity_service, "log_activity", _wirft)
    caplog.set_level("WARNING", logger=_MIG_LOGGER)
    aid = await _anlage(db)
    wb = await _inv(db, aid, "wallbox")
    ea = await _inv(db, aid, "e-auto")
    await _imd(db, ea.id, 2026, 4, {"ladung_kwh": 300, "ladung_pv_kwh": 200, "ladung_netz_kwh": 100})
    await db.commit()

    await migrate_emob_canonical_source(db)

    assert await _vd(db, wb.id, 2026, 4) == {"ladung_kwh": 300, "ladung_pv_kwh": 200, "ladung_netz_kwh": 100}
    assert [r.getMessage() for r in caplog.records if r.name == _MIG_LOGGER] == [
        "Activity-Log (Emob-Migration) fehlgeschlagen: RuntimeError: gestellt"
    ]
