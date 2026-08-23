"""
Reproduktion: User meldet "Cockpit-Übersicht-Kachel E-Mobilität zeigt
Gefahrene km = 0", obwohl im E-Auto-Detail-Tab km für die gleichen Monate
sichtbar sind und die KPI "Gefahren" eine echte Zahl liefert (sl@osyscon
2026-05-17).

IMD enthält `verbrauch_daten.km_gefahren` per E-Auto-IMD. Beide Code-Pfade
(`/cockpit/uebersicht` und `/dashboard/e-auto`) lesen exakt dasselbe Feld
unter denselben aktiv-Filtern.

Hypothesen, die wir hier durchspielen:

  H1: ist_dienstlich=False, km gepflegt              → emob_km > 0  (Baseline)
  H2: ist_dienstlich=True,  km gepflegt              → emob_km == 0 (erwartet)
  H3: ist_dienstlich="false" (String!), km gepflegt  → erwartet emob_km > 0,
        aber Python-Bug: `if "false":` ist truthy → fällt in Dienstlich-Zweig
        → emob_km == 0 (String-vs-Bool-Drift)
  H4: ist_dienstlich="true"  (String!), km gepflegt  → emob_km == 0  (analog truthy)
  H5: parameter == None,                       km    → emob_km > 0
  H6: Wallbox nicht-dienstlich + E-Auto nicht-dienstlich mit km → emob_km > 0
      (Reproduktion des Screenshot-Szenarios)

Lauf über pytest (der im Docstring genannte Standalone-Runner existierte in
dieser Datei nicht — der `# ── Runner ──`-Block darunter war leer):

    cd eedc && python -m pytest backend/tests/test_emob_km_uebersicht_bug.py -q

H8 („optional aus lokalem Backup") ist am 2026-08-23 entfallen (M4, Etappe E1):
Er kehrte bei fehlender Fixture **still** zurück, die Suite meldete ihn damit
als *passed*, obwohl er nichts gemessen hat — und die Fixture konnte nie
existieren, weil `fixtures/local/` bewusst git-ignoriert ist (echte
Nutzer-Backups gehören nicht ins Repo). Entscheid Gernots: löschen.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import (  # noqa: F401
    Anlage, Investition, InvestitionMonatsdaten, Monatsdaten,
)


async def _call_uebersicht(anlage_id: int, db: AsyncSession):
    from backend.api.routes.cockpit.uebersicht import get_cockpit_uebersicht
    return await get_cockpit_uebersicht(anlage_id=anlage_id, jahr=None, db=db)


async def _seed_basis(db: AsyncSession) -> int:
    anlage = Anlage(anlagenname="Test", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    db.add(Monatsdaten(
        anlage_id=anlage.id, jahr=2026, monat=4,
        netzbezug_kwh=100.0, einspeisung_kwh=200.0,
    ))
    return anlage.id


async def _seed_eauto(db: AsyncSession, anlage_id: int, parameter: dict | None,
                     km: int = 3000, ladung_kwh: float = 365.0) -> int:
    inv = Investition(
        anlage_id=anlage_id, typ="e-auto",
        bezeichnung="Test E-Auto",
        anschaffungsdatum=date(2024, 1, 1),
        parameter=parameter,
    )
    db.add(inv)
    await db.flush()
    db.add(InvestitionMonatsdaten(
        investition_id=inv.id, jahr=2026, monat=4,
        verbrauch_daten={
            "ladung_kwh": ladung_kwh,
            "ladung_pv_kwh": ladung_kwh * 0.99,
            "ladung_netz_kwh": ladung_kwh * 0.01,
            "km_gefahren": km,
        },
    ))
    return inv.id


# ── Tests ──


async def test_H1_baseline_privat_bool_false(db):
    """Klassischer Fall: ist_dienstlich=False (echtes Bool), km gepflegt."""
    anlage_id = await _seed_basis(db)
    await _seed_eauto(db, anlage_id, parameter={"ist_dienstlich": False})
    await db.commit()
    result = await _call_uebersicht(anlage_id, db)
    assert result.emob_km == 3000, f"erwartet 3000, war {result.emob_km}"


async def test_H2_dienstwagen_bool_true(db):
    """Dienstwagen mit ist_dienstlich=True → km werden ausgefiltert."""
    anlage_id = await _seed_basis(db)
    await _seed_eauto(db, anlage_id, parameter={"ist_dienstlich": True})
    await db.commit()
    result = await _call_uebersicht(anlage_id, db)
    assert result.emob_km == 0, f"Dienstwagen darf nicht zählen, war {result.emob_km}"


async def test_H3_string_false_sollte_privat_sein(db):
    """ist_dienstlich='false' (String) → Python: bool('false') == True →
    fällt im aktuellen Code in Dienstlich-Zweig → km == 0 obwohl gepflegt.
    Wenn dieser Test FAIL ist, haben wir den Bug reproduziert."""
    anlage_id = await _seed_basis(db)
    await _seed_eauto(db, anlage_id, parameter={"ist_dienstlich": "false"})
    await db.commit()
    result = await _call_uebersicht(anlage_id, db)
    assert result.emob_km == 3000, (
        f"ist_dienstlich='false' sollte als 'nicht dienstlich' interpretiert "
        f"werden → 3000 km, war {result.emob_km}"
    )


async def test_H4_string_true_dienstwagen(db):
    """ist_dienstlich='true' (String) → soll als Dienstwagen behandelt werden."""
    anlage_id = await _seed_basis(db)
    await _seed_eauto(db, anlage_id, parameter={"ist_dienstlich": "true"})
    await db.commit()
    result = await _call_uebersicht(anlage_id, db)
    assert result.emob_km == 0, f"Dienstwagen via String, erwartet 0, war {result.emob_km}"


async def test_H5_parameter_none(db):
    """parameter is None → kein ist_dienstlich-Key → muss als 'privat' gelten."""
    anlage_id = await _seed_basis(db)
    await _seed_eauto(db, anlage_id, parameter=None)
    await db.commit()
    result = await _call_uebersicht(anlage_id, db)
    assert result.emob_km == 3000, f"erwartet 3000, war {result.emob_km}"


async def test_H7_dienstwagen_plus_nichtdienstliche_wallbox(db):
    """Strukturmuster: dienstliches E-Auto (ist_dienstlich=True), private
    Wallbox (ist_dienstlich nicht gesetzt → wird wie False behandelt).

    Erwartung: emob_km = 0 (E-Auto-Zweig im Dienstlich-Filter
    rausgefiltert), aber emob_ladung_kwh > 0 (Wallbox läuft durch den Pool).
    Das ist das designte Verhalten — der User sieht eine asymmetrische
    Kachel (Ladung sichtbar, km nicht), weil Wallbox-Loadpoint und
    E-Auto-Vehicle unterschiedlich gefiltert werden, obwohl sie denselben
    Strom messen."""
    anlage_id = await _seed_basis(db)
    ea = Investition(
        anlage_id=anlage_id, typ="e-auto",
        bezeichnung="Test-Dienstwagen",
        anschaffungsdatum=date(2024, 1, 1),
        parameter={"ist_dienstlich": True},
    )
    wb = Investition(
        anlage_id=anlage_id, typ="wallbox",
        bezeichnung="Test-Wallbox",
        anschaffungsdatum=date(2024, 1, 1),
        parameter={},  # kein ist_dienstlich-Key
    )
    db.add_all([ea, wb])
    await db.flush()
    db.add(InvestitionMonatsdaten(
        investition_id=ea.id, jahr=2026, monat=4,
        verbrauch_daten={"km_gefahren": 2500, "ladung_kwh": 20.0},
    ))
    db.add(InvestitionMonatsdaten(
        investition_id=wb.id, jahr=2026, monat=4,
        verbrauch_daten={"ladung_kwh": 350.0, "ladung_pv_kwh": 340.0},
    ))
    await db.commit()

    result = await _call_uebersicht(anlage_id, db)
    assert result.emob_km == 0, (
        f"Dienstwagen → km gefiltert, erwartet 0, war {result.emob_km}"
    )
    assert 340 <= result.emob_ladung_kwh <= 360, (
        f"Wallbox-Pool muss durchkommen, war {result.emob_ladung_kwh}"
    )


async def test_H6_szenario_screenshot_eauto_plus_wallbox(db):
    """Screenshot-Reproduktion: E-Auto + Wallbox, beide nicht dienstlich.
    E-Auto trägt km, Wallbox trägt ladung_kwh (Loadpoint-Sicht).
    Erwartung: emob_km > 0 und emob_ladung_kwh > 0 gleichzeitig."""
    anlage_id = await _seed_basis(db)
    # E-Auto: km + kleine Vehicle-Sicht-Ladung (oft schlechter gepflegt)
    ea_id = await _seed_eauto(
        db, anlage_id,
        parameter={"ist_dienstlich": False},
        km=3000, ladung_kwh=360.0,
    )
    # Wallbox: Loadpoint-Wahrheit, leicht höher
    wb = Investition(
        anlage_id=anlage_id, typ="wallbox",
        bezeichnung="Wallbox",
        anschaffungsdatum=date(2024, 1, 1),
        parameter={"ist_dienstlich": False},
    )
    db.add(wb)
    await db.flush()
    db.add(InvestitionMonatsdaten(
        investition_id=wb.id, jahr=2026, monat=4,
        verbrauch_daten={
            "ladung_kwh": 370.0,
            "ladung_pv_kwh": 366.0,
            "ladung_netz_kwh": 4.0,
        },
    ))
    await db.commit()

    result = await _call_uebersicht(anlage_id, db)
    assert result.emob_km == 3000, (
        f"Screenshot-Bug: km müssen ankommen, war {result.emob_km}"
    )
    assert result.emob_ladung_kwh > 360, (
        f"Ladung max-Pool > 360, war {result.emob_ladung_kwh}"
    )

