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

Fix: SoT-Helper `get_emob_heimladung_canonical` (Phase 2a) — EINE Quelle
liefert die komplette, konsistente Trias (`pv+netz==ladung`), nie feldweise
gemischt. Alle Sichten rufen ihn (bzw. die km-Attribution mit derselben
strukturellen Quellen-Entscheidung) auf.

Geprüft:
  - Helper-Unit: Gewinner-Quelle liefert konsistente Trias, `pv+netz==ladung`
  - junky84-Form (Wallbox real, E-Auto verirrte Streudaten) → Wallbox gewinnt
  - Regression: Komponenten-PV-Anteil kann nie > 100 % werden
  - Cross-View: Wallbox-Dashboard, Komponenten, E-Auto-Dashboard zeigen
    bei identischen Daten dieselbe Heimladungs-Trias
"""

from __future__ import annotations


from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import (  # noqa: F401
    Anlage, Investition, InvestitionMonatsdaten,
)
from backend.tests import factories
# Hinweis: Die Helfer-Unit-Tests der Quellen-Wahl leben in
# `test_emob_heimladung_canonical.py` (strukturelle Regel) bzw.
# `test_emob_readsite_symmetrie.py` (Helfer-Kontrakt). Hier bleibt die
# #262-Cross-View-Regression über die echten Read-Endpunkte.


# ── Integration: Seed-Helfer ────────────────────────────────────────────────


async def _seed_anlage(db: AsyncSession) -> int:
    return (await factories.anlage(db)).id


async def _add_inv(db, anlage_id, typ, bezeichnung):
    return await factories.investition(db, anlage_id, typ, bezeichnung=bezeichnung)


async def _add_imd(db, inv_id, jahr, monat, daten):
    await factories.imd(db, inv_id, jahr, monat, daten)


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
        anlage_id=anlage_id, strompreis_cent=30.0, db=db))[0].zusammenfassung
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
