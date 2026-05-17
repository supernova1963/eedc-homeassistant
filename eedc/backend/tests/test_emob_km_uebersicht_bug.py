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

Standalone-Runner, analog test_emob_pool_komponenten.py:

    eedc/backend/venv/bin/python eedc/backend/tests/test_emob_km_uebersicht_bug.py
"""

from __future__ import annotations

import asyncio
import sys
import traceback
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND_ROOT))

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402

from backend.core.database import Base  # noqa: E402
from backend.models import (  # noqa: E402, F401
    Anlage, Investition, InvestitionMonatsdaten, Monatsdaten,
)


@asynccontextmanager
async def _session_ctx():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    session = Session()
    try:
        yield session
    finally:
        await session.close()
        await engine.dispose()


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


async def test_H1_baseline_privat_bool_false():
    """Klassischer Fall: ist_dienstlich=False (echtes Bool), km gepflegt."""
    async with _session_ctx() as db:
        anlage_id = await _seed_basis(db)
        await _seed_eauto(db, anlage_id, parameter={"ist_dienstlich": False})
        await db.commit()
        result = await _call_uebersicht(anlage_id, db)
        assert result.emob_km == 3000, f"erwartet 3000, war {result.emob_km}"


async def test_H2_dienstwagen_bool_true():
    """Dienstwagen mit ist_dienstlich=True → km werden ausgefiltert."""
    async with _session_ctx() as db:
        anlage_id = await _seed_basis(db)
        await _seed_eauto(db, anlage_id, parameter={"ist_dienstlich": True})
        await db.commit()
        result = await _call_uebersicht(anlage_id, db)
        assert result.emob_km == 0, f"Dienstwagen darf nicht zählen, war {result.emob_km}"


async def test_H3_string_false_sollte_privat_sein():
    """ist_dienstlich='false' (String) → Python: bool('false') == True →
    fällt im aktuellen Code in Dienstlich-Zweig → km == 0 obwohl gepflegt.
    Wenn dieser Test FAIL ist, haben wir den Bug reproduziert."""
    async with _session_ctx() as db:
        anlage_id = await _seed_basis(db)
        await _seed_eauto(db, anlage_id, parameter={"ist_dienstlich": "false"})
        await db.commit()
        result = await _call_uebersicht(anlage_id, db)
        assert result.emob_km == 3000, (
            f"ist_dienstlich='false' sollte als 'nicht dienstlich' interpretiert "
            f"werden → 3000 km, war {result.emob_km}"
        )


async def test_H4_string_true_dienstwagen():
    """ist_dienstlich='true' (String) → soll als Dienstwagen behandelt werden."""
    async with _session_ctx() as db:
        anlage_id = await _seed_basis(db)
        await _seed_eauto(db, anlage_id, parameter={"ist_dienstlich": "true"})
        await db.commit()
        result = await _call_uebersicht(anlage_id, db)
        assert result.emob_km == 0, f"Dienstwagen via String, erwartet 0, war {result.emob_km}"


async def test_H5_parameter_none():
    """parameter is None → kein ist_dienstlich-Key → muss als 'privat' gelten."""
    async with _session_ctx() as db:
        anlage_id = await _seed_basis(db)
        await _seed_eauto(db, anlage_id, parameter=None)
        await db.commit()
        result = await _call_uebersicht(anlage_id, db)
        assert result.emob_km == 3000, f"erwartet 3000, war {result.emob_km}"


async def test_H7_dienstwagen_plus_nichtdienstliche_wallbox():
    """Strukturmuster: dienstliches E-Auto (ist_dienstlich=True), private
    Wallbox (ist_dienstlich nicht gesetzt → wird wie False behandelt).

    Erwartung: emob_km = 0 (E-Auto-Zweig im Dienstlich-Filter
    rausgefiltert), aber emob_ladung_kwh > 0 (Wallbox läuft durch den Pool).
    Das ist das designte Verhalten — der User sieht eine asymmetrische
    Kachel (Ladung sichtbar, km nicht), weil Wallbox-Loadpoint und
    E-Auto-Vehicle unterschiedlich gefiltert werden, obwohl sie denselben
    Strom messen."""
    async with _session_ctx() as db:
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


async def test_H8_optional_aus_lokalem_backup():
    """Optional: liest ein eedc-Backup-JSON aus einem nicht-versionierten
    Pfad ein und prüft, dass die Cockpit-Übersicht für die enthaltenen
    Anlagen zumindest *konsistent* mit dem reinen IMD-Aggregat
    übereinstimmt. Wenn keine Backup-Datei vorhanden ist: SKIP.

    Pfad: eedc/backend/tests/fixtures/local/backup.json
    (per .gitignore ausgeschlossen)
    """
    fixture = Path(__file__).parent / "fixtures" / "local" / "backup.json"
    if not fixture.exists():
        print(f"     (skip: {fixture.relative_to(Path(__file__).parents[2])} nicht vorhanden)")
        return

    import json
    payload = json.loads(fixture.read_text(encoding="utf-8"))

    async with _session_ctx() as db:
        anlage_id = await _load_backup_anlage(db, payload)
        result = await _call_uebersicht(anlage_id, db)

        # Vergleichswert: dieselbe Aggregation, aber direkt aus IMD ohne
        # Dienstlich-Filter (so wie der E-Auto-Detail-Tab es macht).
        from sqlalchemy import select
        from backend.models import Investition, InvestitionMonatsdaten
        e_autos = (await db.execute(
            select(Investition).where(
                Investition.anlage_id == anlage_id,
                Investition.typ == "e-auto",
            )
        )).scalars().all()
        ea_ids = [e.id for e in e_autos]
        imds = (await db.execute(
            select(InvestitionMonatsdaten).where(
                InvestitionMonatsdaten.investition_id.in_(ea_ids)
            )
        )).scalars().all() if ea_ids else []
        km_ungefiltert = sum(
            (imd.verbrauch_daten or {}).get("km_gefahren", 0) or 0
            for imd in imds
        )

        # Falls min. ein E-Auto dienstlich ist: Übersicht zeigt 0 km, aber
        # ungefilterte Summe > 0 → das ist genau der Screenshot-Effekt.
        dienstlich_vorhanden = any(
            (e.parameter or {}).get("ist_dienstlich") is True for e in e_autos
        )
        if dienstlich_vorhanden and km_ungefiltert > 0:
            assert result.emob_km < km_ungefiltert, (
                f"Erwartung Screenshot-Szenario: Übersicht-km ({result.emob_km}) "
                f"< Detail-Tab-km ({km_ungefiltert}), Dienstwagen wird gefiltert"
            )
            print(f"     (Backup-Anlage: Übersicht={result.emob_km} km, "
                  f"Detail-Tab-Summe={km_ungefiltert:.0f} km → Dienstwagen-Filter aktiv)")
        else:
            assert result.emob_km == km_ungefiltert, (
                f"Ohne Dienstwagen-Filter müssen Übersicht und Detail-Tab "
                f"übereinstimmen — war {result.emob_km} vs. {km_ungefiltert}"
            )


async def _load_backup_anlage(db: AsyncSession, payload: dict) -> int:
    """Lädt nur die Felder, die der Test braucht — bewusst minimal, damit
    keine Side-Effects (Tarife, PVGIS etc.) das Verhalten verändern."""
    a = payload.get("anlage") or {}
    anlage = Anlage(
        anlagenname=a.get("anlagenname") or "Imported",
        leistung_kwp=a.get("leistung_kwp") or 0.0,
    )
    db.add(anlage)
    await db.flush()

    def _parse_date(s):
        return date.fromisoformat(s) if s else None

    def _add_inv(inv_data, parent_id=None):
        inv = Investition(
            anlage_id=anlage.id,
            typ=inv_data["typ"],
            bezeichnung=inv_data.get("bezeichnung") or inv_data["typ"],
            anschaffungsdatum=_parse_date(inv_data.get("anschaffungsdatum")),
            stilllegungsdatum=_parse_date(inv_data.get("stilllegungsdatum")),
            parameter=inv_data.get("parameter"),
        )
        db.add(inv)
        return inv

    invs_to_persist: list[tuple[Investition, list[dict]]] = []
    for inv_data in payload.get("investitionen") or []:
        inv = _add_inv(inv_data)
        invs_to_persist.append((inv, inv_data.get("monatsdaten") or []))
        for child in inv_data.get("children") or []:
            child_inv = _add_inv(child)
            invs_to_persist.append((child_inv, child.get("monatsdaten") or []))

    await db.flush()
    for inv, md_list in invs_to_persist:
        for md in md_list:
            db.add(InvestitionMonatsdaten(
                investition_id=inv.id,
                jahr=md["jahr"], monat=md["monat"],
                verbrauch_daten=md.get("verbrauch_daten") or {},
            ))
    # Basis-Monatsdaten (für Anlagen-Energiebilanz, sonst null-Felder)
    for md in payload.get("monatsdaten") or []:
        db.add(Monatsdaten(
            anlage_id=anlage.id,
            jahr=md["jahr"], monat=md["monat"],
            einspeisung_kwh=md.get("einspeisung_kwh") or 0.0,
            netzbezug_kwh=md.get("netzbezug_kwh") or 0.0,
        ))
    await db.commit()
    return anlage.id


async def test_H6_szenario_screenshot_eauto_plus_wallbox():
    """Screenshot-Reproduktion: E-Auto + Wallbox, beide nicht dienstlich.
    E-Auto trägt km, Wallbox trägt ladung_kwh (Loadpoint-Sicht).
    Erwartung: emob_km > 0 und emob_ladung_kwh > 0 gleichzeitig."""
    async with _session_ctx() as db:
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


# ── Runner ──


_TESTS = [
    test_H1_baseline_privat_bool_false,
    test_H2_dienstwagen_bool_true,
    test_H3_string_false_sollte_privat_sein,
    test_H4_string_true_dienstwagen,
    test_H5_parameter_none,
    test_H6_szenario_screenshot_eauto_plus_wallbox,
    test_H7_dienstwagen_plus_nichtdienstliche_wallbox,
    test_H8_optional_aus_lokalem_backup,
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
        except Exception as e:
            failures += 1
            print(f"ERR  {fn.__name__}: {type(e).__name__}: {e}")
            traceback.print_exc()
    if failures:
        print(f"\n{failures}/{len(_TESTS)} Tests fehlgeschlagen.")
        return 1
    print(f"\nAlle {len(_TESTS)} Tests grün.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
