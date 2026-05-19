"""
Akzeptanztest für E-Mobilitäts-Pool-Doppelzählungs-Fix in
`cockpit/komponenten.py` (#231 NongJoWo).

Hintergrund: Wallbox-IMD (Loadpoint-Sicht) und E-Auto-IMD (Vehicle-Sicht)
messen oft denselben Stromfluss aus zwei Perspektiven. Aufsummieren ergibt
Doppelzählung — sichtbar bei NongJoWo in Auswertungen → Komponenten →
E-Mobilität (PV-Anteil > 100 %).

Pattern (analog `aktueller_monat._aggregate`, Memory `project_pool_fix_emob.md`):
  - Getrennte Akkumulatoren `eauto_*` + `wb_*` pro Monat
  - `ist_dienstlich`-Filter
  - Beim Konsolidieren pro Feld die größere Quelle (`max`) gewinnen lassen
  - km + v2h kommen nur vom E-Auto (Wallbox kennt das nicht)

Geprüft:
  1. Wallbox + E-Auto im selben Monat → max-Pool, keine Doppelung
  2. Nur Wallbox → wb_*-Werte landen im Aggregat
  3. Nur E-Auto → eauto_*-Werte landen im Aggregat
  4. Dienstwagen wird übersprungen (ist_dienstlich=True)
"""

from __future__ import annotations

import traceback
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import (  # noqa: F401
    Anlage, Investition, InvestitionMonatsdaten, Monatsdaten,
)


async def _call_komponenten(anlage_id: int, db: AsyncSession):
    from backend.api.routes.cockpit.komponenten import get_komponenten_zeitreihe
    return await get_komponenten_zeitreihe(
        anlage_id=anlage_id, jahr=None, db=db,
    )


async def _seed_anlage_mit_basis(db: AsyncSession) -> int:
    """Anlage + Basis-Monatsdaten Mai 2025 anlegen."""
    anlage = Anlage(anlagenname="Test", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    db.add(Monatsdaten(
        anlage_id=anlage.id, jahr=2025, monat=5,
        netzbezug_kwh=100.0, einspeisung_kwh=200.0,
    ))
    return anlage.id


async def test_wallbox_und_eauto_keine_doppelung(db):
    """Beide Quellen liefern Werte → max gewinnt, keine Doppelung."""
    anlage_id = await _seed_anlage_mit_basis(db)

    # Wallbox-Investition mit Loadpoint-Wahrheit
    wb = Investition(
        anlage_id=anlage_id, typ="wallbox",
        bezeichnung="Wallbox", anschaffungsdatum=date(2024, 1, 1),
    )
    # E-Auto-Investition mit Vehicle-Sicht (dieselbe physische Ladung,
    # in beiden Investitionen gepflegt — z.B. Loadpoint+App)
    ea = Investition(
        anlage_id=anlage_id, typ="e-auto",
        bezeichnung="E-Auto", anschaffungsdatum=date(2024, 1, 1),
    )
    db.add_all([wb, ea])
    await db.flush()

    # Beide zeigen 100 kWh Gesamtladung, 60 kWh PV-Anteil
    # Sum würde 200/120 ergeben (Doppelzählung), max muss 100/60 ergeben
    db.add(InvestitionMonatsdaten(
        investition_id=wb.id, jahr=2025, monat=5,
        verbrauch_daten={
            "ladung_kwh": 100, "ladung_pv_kwh": 60,
            "ladung_netz_kwh": 40,
        },
    ))
    db.add(InvestitionMonatsdaten(
        investition_id=ea.id, jahr=2025, monat=5,
        verbrauch_daten={
            "ladung_kwh": 100, "ladung_pv_kwh": 60,
            "ladung_netz_kwh": 40,
            "km_gefahren": 800,  # km nur vom E-Auto
        },
    ))
    await db.commit()

    result = await _call_komponenten(anlage_id, db)
    mai = next(m for m in result.monatswerte if m.monat == 5)

    assert mai.emob_ladung_kwh == 100, (
        f"Pool-max muss 100 sein (nicht 200 = Sum), war {mai.emob_ladung_kwh}"
    )
    assert mai.emob_ladung_pv_kwh == 60, (
        f"PV-Pool-max 60, war {mai.emob_ladung_pv_kwh}"
    )
    assert mai.emob_pv_anteil_prozent == 60.0, (
        f"PV-Anteil 60 %, war {mai.emob_pv_anteil_prozent}"
    )
    assert mai.emob_km == 800, (
        f"km nur vom E-Auto (800), war {mai.emob_km}"
    )


async def test_nur_wallbox_kein_eauto(db):
    """Wallbox vorhanden, kein E-Auto → wb_*-Werte landen im Aggregat."""
    anlage_id = await _seed_anlage_mit_basis(db)
    wb = Investition(
        anlage_id=anlage_id, typ="wallbox",
        bezeichnung="Wallbox", anschaffungsdatum=date(2024, 1, 1),
    )
    db.add(wb)
    await db.flush()
    db.add(InvestitionMonatsdaten(
        investition_id=wb.id, jahr=2025, monat=5,
        verbrauch_daten={"ladung_kwh": 80, "ladung_pv_kwh": 50},
    ))
    await db.commit()

    result = await _call_komponenten(anlage_id, db)
    mai = next(m for m in result.monatswerte if m.monat == 5)
    assert mai.emob_ladung_kwh == 80, f"war {mai.emob_ladung_kwh}"
    assert mai.emob_ladung_pv_kwh == 50, f"war {mai.emob_ladung_pv_kwh}"
    assert mai.emob_km == 0, f"keine km ohne E-Auto, war {mai.emob_km}"


async def test_nur_eauto_keine_wallbox(db):
    """E-Auto vorhanden, keine Wallbox → eauto_*-Werte landen im Aggregat."""
    anlage_id = await _seed_anlage_mit_basis(db)
    ea = Investition(
        anlage_id=anlage_id, typ="e-auto",
        bezeichnung="E-Auto", anschaffungsdatum=date(2024, 1, 1),
    )
    db.add(ea)
    await db.flush()
    db.add(InvestitionMonatsdaten(
        investition_id=ea.id, jahr=2025, monat=5,
        verbrauch_daten={
            "ladung_kwh": 90, "ladung_pv_kwh": 70,
            "km_gefahren": 1200, "v2h_entladung_kwh": 5,
        },
    ))
    await db.commit()

    result = await _call_komponenten(anlage_id, db)
    mai = next(m for m in result.monatswerte if m.monat == 5)
    assert mai.emob_ladung_kwh == 90, f"war {mai.emob_ladung_kwh}"
    assert mai.emob_ladung_pv_kwh == 70, f"war {mai.emob_ladung_pv_kwh}"
    assert mai.emob_km == 1200, f"war {mai.emob_km}"
    assert mai.emob_v2h_kwh == 5, f"war {mai.emob_v2h_kwh}"


async def test_dienstwagen_wird_uebersprungen(db):
    """ist_dienstlich-Investition trägt nicht zum E-Mob-Pool bei
    (feedback_dienstwagen_alle_checks.md)."""
    anlage_id = await _seed_anlage_mit_basis(db)
    ea_priv = Investition(
        anlage_id=anlage_id, typ="e-auto",
        bezeichnung="Privates E-Auto",
        anschaffungsdatum=date(2024, 1, 1),
        parameter={"ist_dienstlich": False},
    )
    ea_dienst = Investition(
        anlage_id=anlage_id, typ="e-auto",
        bezeichnung="Firmenwagen",
        anschaffungsdatum=date(2024, 1, 1),
        parameter={"ist_dienstlich": True},
    )
    db.add_all([ea_priv, ea_dienst])
    await db.flush()
    db.add(InvestitionMonatsdaten(
        investition_id=ea_priv.id, jahr=2025, monat=5,
        verbrauch_daten={"ladung_kwh": 50, "ladung_pv_kwh": 30, "km_gefahren": 500},
    ))
    db.add(InvestitionMonatsdaten(
        investition_id=ea_dienst.id, jahr=2025, monat=5,
        verbrauch_daten={"ladung_kwh": 200, "ladung_pv_kwh": 100, "km_gefahren": 2000},
    ))
    await db.commit()

    result = await _call_komponenten(anlage_id, db)
    mai = next(m for m in result.monatswerte if m.monat == 5)
    # Dienstwagen darf NICHT zum Pool beitragen
    assert mai.emob_ladung_kwh == 50, (
        f"nur Privates E-Auto (50), Dienstwagen ausgefiltert, "
        f"war {mai.emob_ladung_kwh}"
    )
    assert mai.emob_km == 500, f"nur Private km, war {mai.emob_km}"


# ── Runner ──────────────────────────────────────────────────────────────────


_TESTS = [
    test_wallbox_und_eauto_keine_doppelung,
    test_nur_wallbox_kein_eauto,
    test_nur_eauto_keine_wallbox,
    test_dienstwagen_wird_uebersprungen,
]


async def _main() -> int:
    failures = 0
    for fn in _TESTS:
        try:
            await fn()
            print(f"OK   {fn.__name__}")
        except AssertionError as e:
            failures += 1
            print(f"FAIL {fn.__name__}: {e}")
            traceback.print_exc()
        except Exception as e:
            failures += 1
            print(f"ERR  {fn.__name__}: {type(e).__name__}: {e}")
            traceback.print_exc()
    if failures:
        print(f"\n{failures}/{len(_TESTS)} Tests fehlgeschlagen.")
        return 1
    print(f"\nAlle {len(_TESTS)} Tests grün.")
    return 0

