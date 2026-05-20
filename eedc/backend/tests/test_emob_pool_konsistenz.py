"""E-Mobilitäts-Pool-Konsistenz über alle Sichten (#262 junky84, v3.31.6).

Hintergrund: junky84 meldete nach v3.31.5 vier verschiedene Zahlen für
dieselbe evcc-Ladung (4127 kWh Wahrheit):

  | Sicht                      | Ladung | PV   | Netz | PV-Anteil |
  | Cockpit › E-Auto      ✅   | 4127   | 1989 | 2138 | 48 %      |
  | Cockpit › Wallbox          | 5278   | 1989 | 3289 | 38 %      |
  | Auswertungen › Komponenten | 4130   | 1989 | 3514 | —         |

Komponenten zeigte PV 48 % + Netz 85 % = 133 % — mathematisch unmöglich.

Ursache: vier Sichten poolten E-Auto- + Wallbox-IMD mit feldweisem
`max(eauto_X, wb_X)` — drei unabhängige max()-Aufrufe für total/pv/netz
können `pv` aus Quelle A und `netz` aus Quelle B nehmen → das Tripel ist
intern inkonsistent (`pv + netz != total`). Nur das E-Auto-Dashboard war
korrekt, weil es als einzige Sicht über `compute_emob_pool_attribution`
EINE ganze Quelle poolt.

Fix: SoT-Helper `aggregiere_emob_ladung` — die Quelle mit der größeren
Heimladung gewinnt die komplette Trias. Alle Sichten rufen ihn auf.

Geprüft:
  - Helper-Unit: Gewinner-Quelle liefert konsistente Trias, `pv+netz==ladung`
  - junky84-Form (Wallbox real, E-Auto verirrte Streudaten) → Wallbox gewinnt
  - Regression: Komponenten-PV-Anteil kann nie > 100 % werden
  - Cross-View: Wallbox-Dashboard, Komponenten, E-Auto-Dashboard zeigen
    bei identischen Daten dieselbe Heimladungs-Trias
"""

from __future__ import annotations

from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import (  # noqa: F401
    Anlage, Investition, InvestitionMonatsdaten,
)
from backend.services.eauto_wirtschaftlichkeit import aggregiere_emob_ladung


# ── Unit-Tests: aggregiere_emob_ladung ──────────────────────────────────────


def test_helper_konsistente_trias_pv_plus_netz_gleich_ladung():
    """Garantie: pv_kwh + netz_kwh == ladung_kwh, egal welche Quelle gewinnt."""
    pool = aggregiere_emob_ladung(
        eauto_imd_data=[],
        wallbox_imd_data=[{"ladung_kwh": 250, "ladung_pv_kwh": 120,
                           "ladung_netz_kwh": 130}],
    )
    assert pool.quelle == "wallbox"
    assert pool.pv_kwh == 120.0
    assert pool.netz_kwh == 130.0
    assert pool.ladung_kwh == pool.pv_kwh + pool.netz_kwh == 250.0


def test_helper_groessere_heimladung_gewinnt_komplett():
    """Die Quelle mit der größeren Heimladung liefert die ganze Trias —
    nie feldweise gemischt."""
    # Wallbox: 250 kWh (pv-lastig), E-Auto: 180 kWh (netz-lastig)
    pool = aggregiere_emob_ladung(
        eauto_imd_data=[{"ladung_kwh": 180, "ladung_pv_kwh": 30,
                         "ladung_netz_kwh": 150}],
        wallbox_imd_data=[{"ladung_kwh": 250, "ladung_pv_kwh": 200,
                           "ladung_netz_kwh": 50}],
    )
    # Wallbox gewinnt (250 > 180) → komplette Wallbox-Trias, kein Mix
    assert pool.quelle == "wallbox"
    assert (pool.pv_kwh, pool.netz_kwh, pool.ladung_kwh) == (200.0, 50.0, 250.0)
    # feldweises max() hätte netz=150 (aus E-Auto) genommen → verworfen


def test_helper_eauto_gewinnt_wenn_groesser():
    """E-Auto-Quelle gewinnt, wenn sie die größere Heimladung hat (Premium-
    Setup mit eigenen Vehicle-Sensoren)."""
    pool = aggregiere_emob_ladung(
        eauto_imd_data=[{"ladung_kwh": 300, "ladung_pv_kwh": 180,
                         "ladung_netz_kwh": 120}],
        wallbox_imd_data=[{"ladung_kwh": 200, "ladung_pv_kwh": 100,
                           "ladung_netz_kwh": 100}],
    )
    assert pool.quelle == "e-auto"
    assert (pool.pv_kwh, pool.netz_kwh, pool.ladung_kwh) == (180.0, 120.0, 300.0)


def test_helper_junky84_form_wallbox_real_eauto_streudaten():
    """junky84-Form: Wallbox trägt die echte evcc-Ladung, das E-Auto hat
    verirrte Streudaten (ladung_kwh ohne PV-Split → Helper liest alles als
    Netz). Solange die Wallbox-Heimladung größer ist, gewinnt sie — feldweises
    max() hätte den hohen E-Auto-Netz-Wert durchgereicht."""
    pool = aggregiere_emob_ladung(
        # E-Auto: ladung_kwh ohne pv-Key → netz = 180, pv = 0
        eauto_imd_data=[{"ladung_kwh": 180}],
        # Wallbox: evcc-Form ohne netz-Key → netz = 250 - 200 = 50
        wallbox_imd_data=[{"ladung_kwh": 250, "ladung_pv_kwh": 200}],
    )
    assert pool.quelle == "wallbox"
    assert pool.pv_kwh == 200.0
    assert pool.netz_kwh == 50.0          # NICHT 180 (E-Auto-Streudaten)
    assert pool.ladung_kwh == 250.0       # NICHT 430 (Mix)


def test_helper_extern_paarweise_aus_quelle_mit_hoeheren_kosten():
    """Externe Ladung kommt als Paar (kWh, €) aus der Quelle mit den höheren
    externen Kosten — unabhängig davon, wer die Heimladung gewinnt."""
    pool = aggregiere_emob_ladung(
        eauto_imd_data=[{"ladung_kwh": 50, "ladung_pv_kwh": 50,
                         "ladung_extern_kwh": 40, "ladung_extern_euro": 22}],
        wallbox_imd_data=[{"ladung_kwh": 300, "ladung_pv_kwh": 300,
                           "ladung_extern_kwh": 5, "ladung_extern_euro": 3}],
    )
    # Heimladung: Wallbox gewinnt (300 > 50)
    assert pool.quelle == "wallbox"
    # Extern: E-Auto-Paar gewinnt (22 € > 3 €) — kWh + € bleiben gepaart
    assert pool.extern_kwh == 40.0
    assert pool.extern_euro == 22.0


def test_helper_leere_quellen():
    """Keine Daten → Null-Trias, quelle == 'leer'."""
    pool = aggregiere_emob_ladung(eauto_imd_data=[], wallbox_imd_data=[])
    assert pool.quelle == "leer"
    assert pool.ladung_kwh == pool.pv_kwh == pool.netz_kwh == 0.0


# ── Integration: Seed-Helfer ────────────────────────────────────────────────


async def _seed_anlage(db: AsyncSession) -> int:
    anlage = Anlage(anlagenname="Test", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    return anlage.id


async def _add_inv(db, anlage_id, typ, bezeichnung):
    inv = Investition(
        anlage_id=anlage_id, typ=typ, bezeichnung=bezeichnung,
        anschaffungsdatum=date(2024, 1, 1),
    )
    db.add(inv)
    await db.flush()
    return inv


async def _add_imd(db, inv_id, jahr, monat, daten):
    db.add(InvestitionMonatsdaten(
        investition_id=inv_id, jahr=jahr, monat=monat, verbrauch_daten=daten,
    ))


# ── Regression: Komponenten-PV-Anteil kann nie > 100 % werden ───────────────


async def test_komponenten_pv_anteil_nie_ueber_100_prozent(db):
    """#262-Kernregression: feldweises max() ergab PV 48 % + Netz 85 % = 133 %.
    Bei inkonsistenten E-Auto-/Wallbox-Quellen darf das Komponenten-Tripel
    nie mehr `pv + netz > ladung` liefern."""
    from backend.api.routes.cockpit.komponenten import get_komponenten_zeitreihe

    anlage_id = await _seed_anlage(db)
    wb = await _add_inv(db, anlage_id, "wallbox", "Wallbox")
    ea = await _add_inv(db, anlage_id, "e-auto", "E-Auto")

    # Wallbox: konsistente evcc-Trias (120 kWh, pv-lastig)
    await _add_imd(db, wb.id, 2026, 4, {
        "ladung_kwh": 120, "ladung_pv_kwh": 72, "ladung_netz_kwh": 48,
    })
    # E-Auto: verirrte Streudaten — ladung_kwh ohne pv-Key → Helper liest
    # alles als Netz (100 kWh). Feldweises max() hätte netz=100 (E-Auto) +
    # pv=72 (Wallbox) gemischt → 72 + 100 = 172 > 120.
    await _add_imd(db, ea.id, 2026, 4, {"ladung_kwh": 100, "km_gefahren": 900})
    await db.commit()

    result = await get_komponenten_zeitreihe(anlage_id=anlage_id, jahr=None, db=db)
    monat = next(m for m in result.monatswerte if m.monat == 4)

    # Trias intern konsistent
    assert (
        abs(monat.emob_ladung_pv_kwh + monat.emob_ladung_netz_kwh
            - monat.emob_ladung_kwh) < 0.1
    ), (
        f"PV ({monat.emob_ladung_pv_kwh}) + Netz "
        f"({monat.emob_ladung_netz_kwh}) muss Ladung "
        f"({monat.emob_ladung_kwh}) ergeben"
    )
    # PV-Anteil physikalisch ≤ 100 %
    assert monat.emob_pv_anteil_prozent is not None
    assert monat.emob_pv_anteil_prozent <= 100.0, (
        f"PV-Anteil {monat.emob_pv_anteil_prozent} % > 100 % — #262-Regression"
    )
    # Wallbox gewinnt (120 > 100) → konsistente Wallbox-Trias
    assert monat.emob_ladung_kwh == 120.0
    assert monat.emob_ladung_pv_kwh == 72.0
    assert monat.emob_ladung_netz_kwh == 48.0


async def test_wallbox_dashboard_eauto_streudaten_blaehen_netz_nicht_auf(db):
    """junky84-Befund: Wallbox-Dashboard zeigte Netz zu hoch, weil
    `max(eauto_netz, wb_netz)` die verirrten E-Auto-Streudaten durchreichte.
    Jetzt gewinnt die ganze Wallbox-Quelle."""
    from backend.api.routes.investitionen import get_wallbox_dashboard

    anlage_id = await _seed_anlage(db)
    wb = await _add_inv(db, anlage_id, "wallbox", "Wallbox")
    ea = await _add_inv(db, anlage_id, "e-auto", "E-Auto")

    # Wallbox: echte Ladung, pv-lastig (250 kWh)
    await _add_imd(db, wb.id, 2026, 4, {
        "ladung_kwh": 250, "ladung_pv_kwh": 200, "ladung_netz_kwh": 50,
    })
    # E-Auto: Streudaten ohne pv-Key → Helper liest 180 kWh als Netz.
    # Altes max(): netz = max(50, 180) = 180, heim = 200 + 180 = 380.
    await _add_imd(db, ea.id, 2026, 4, {"ladung_kwh": 180, "km_gefahren": 800})
    await db.commit()

    result = await get_wallbox_dashboard(
        anlage_id=anlage_id, strompreis_cent=30.0, db=db,
    )
    z = result[0].zusammenfassung
    assert z["ladung_netz_kwh"] == 50.0, (
        f"Netz darf nicht aus E-Auto-Streudaten aufgebläht werden, "
        f"war {z['ladung_netz_kwh']}"
    )
    assert z["ladung_pv_kwh"] == 200.0
    assert z["gesamt_heim_ladung_kwh"] == 250.0   # nicht 380
    assert z["pv_anteil_prozent"] == 80.0


async def test_cross_view_konsistenz_wallbox_komponenten_eauto(db):
    """Alle drei junky84-Sichten zeigen bei identischen Daten dieselbe
    Heimladungs-Trias — keine Drift mehr zwischen den Pfaden."""
    from backend.api.routes.investitionen import (
        get_eauto_dashboard, get_wallbox_dashboard,
    )
    from backend.api.routes.cockpit.komponenten import get_komponenten_zeitreihe

    anlage_id = await _seed_anlage(db)
    wb = await _add_inv(db, anlage_id, "wallbox", "Wallbox")
    ea = await _add_inv(db, anlage_id, "e-auto", "E-Auto")

    # Wallbox trägt die evcc-Wahrheit, E-Auto nur km + verirrte Streudaten
    await _add_imd(db, wb.id, 2026, 3, {
        "ladung_kwh": 300, "ladung_pv_kwh": 144, "ladung_netz_kwh": 156,
    })
    await _add_imd(db, wb.id, 2026, 4, {
        "ladung_kwh": 260, "ladung_pv_kwh": 130, "ladung_netz_kwh": 130,
    })
    await _add_imd(db, ea.id, 2026, 3, {"km_gefahren": 1000, "ladung_kwh": 90})
    await _add_imd(db, ea.id, 2026, 4, {"km_gefahren": 900, "ladung_kwh": 70})
    await db.commit()

    wb_z = (await get_wallbox_dashboard(
        anlage_id=anlage_id, strompreis_cent=30.0, db=db))[0].zusammenfassung
    ea_z = (await get_eauto_dashboard(
        anlage_id=anlage_id, strompreis_cent=30.0, benzinpreis_euro=1.65,
        db=db))[0].zusammenfassung
    komp = await get_komponenten_zeitreihe(anlage_id=anlage_id, jahr=None, db=db)
    komp_pv = sum(m.emob_ladung_pv_kwh for m in komp.monatswerte)
    komp_netz = sum(m.emob_ladung_netz_kwh for m in komp.monatswerte)

    # Wahrheit: Wallbox-Summe (Monate gewinnen einzeln, beide Monate WB > EA)
    erwartet_pv = 144 + 130
    erwartet_netz = 156 + 130

    assert wb_z["ladung_pv_kwh"] == erwartet_pv
    assert wb_z["ladung_netz_kwh"] == erwartet_netz
    assert abs(ea_z["ladung_pv_kwh"] - erwartet_pv) < 0.1
    assert abs(ea_z["ladung_netz_kwh"] - erwartet_netz) < 0.1
    assert abs(komp_pv - erwartet_pv) < 0.1
    assert abs(komp_netz - erwartet_netz) < 0.1
