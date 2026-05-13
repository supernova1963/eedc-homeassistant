"""
Akzeptanztests für den `ist_aktiv_im_monat`-Filter und seine Anwendung in
Read-Sites (#236 detLAN).

Self-contained Standalone-Script:

    eedc/backend/venv/bin/python eedc/backend/tests/test_investition_aktiv_filter.py

Geprüft:
  1. Helper-Verhalten — anschaffungsdatum + stilllegungsdatum (Eckfälle)
  2. Integration: /api/monatsdaten/aggregiert/{anlage_id} aggregiert keine
     IMDs aus Monaten vor anschaffungsdatum (Hauptbefund #236)
"""

from __future__ import annotations

import asyncio
import sys
import traceback
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[2]  # eedc/
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


# ── Helper-Tests ────────────────────────────────────────────────────────────


def test_ist_aktiv_im_monat_ohne_grenzen():
    """Ohne anschaffungs- und stilllegungsdatum: immer aktiv."""
    inv = Investition(anschaffungsdatum=None, stilllegungsdatum=None)
    assert inv.ist_aktiv_im_monat(2024, 1) is True
    assert inv.ist_aktiv_im_monat(2026, 12) is True


def test_ist_aktiv_im_monat_vor_anschaffung():
    """Monate vor anschaffungsdatum.month: nicht aktiv. Anschaffungsmonat selbst: aktiv."""
    inv = Investition(anschaffungsdatum=date(2025, 4, 15), stilllegungsdatum=None)
    assert inv.ist_aktiv_im_monat(2025, 3) is False, "März vor April-Anschaffung"
    assert inv.ist_aktiv_im_monat(2025, 4) is True, "April-Anschaffungsmonat (Tag-15 im Monat)"
    assert inv.ist_aktiv_im_monat(2025, 5) is True
    assert inv.ist_aktiv_im_monat(2024, 12) is False
    assert inv.ist_aktiv_im_monat(2025, 1) is False


def test_ist_aktiv_im_monat_nach_stilllegung():
    """Monate nach stilllegungsdatum.month: nicht aktiv. Stilllegungsmonat selbst: aktiv."""
    inv = Investition(
        anschaffungsdatum=date(2024, 1, 1),
        stilllegungsdatum=date(2025, 8, 15),
    )
    assert inv.ist_aktiv_im_monat(2025, 7) is True
    assert inv.ist_aktiv_im_monat(2025, 8) is True, "Stilllegungsmonat zählt teilweise"
    assert inv.ist_aktiv_im_monat(2025, 9) is False, "September nach Aug-Stilllegung"


def test_ist_aktiv_im_monat_kombiniert():
    """Anschaffungs- und Stilllegungsdatum gemeinsam — Sandwich-Test."""
    inv = Investition(
        anschaffungsdatum=date(2025, 4, 10),
        stilllegungsdatum=date(2026, 2, 28),
    )
    assert inv.ist_aktiv_im_monat(2025, 3) is False
    assert inv.ist_aktiv_im_monat(2025, 4) is True
    assert inv.ist_aktiv_im_monat(2025, 12) is True
    assert inv.ist_aktiv_im_monat(2026, 2) is True
    assert inv.ist_aktiv_im_monat(2026, 3) is False


# ── Integration: /aggregiert/{anlage_id} respektiert Anschaffungsdatum ──────


async def test_aggregiert_endpoint_ignoriert_vor_anschaffungs_imd():
    """detLAN-Hauptbefund #236 — Drift-Symptom-Test.

    Setup: Anlage seit 2024. WP-Investition mit Anschaffung April 2025.
    Test-Daten:
      - IMD März 2025 (vor Anschaffung) für die WP: strom=100, waerme=400
      - IMD April 2025 (Anschaffungsmonat) für die WP: strom=80, waerme=320
    Erwartet: Aggregiert pro Monat — März WP-Werte = None (Komponente
    in dem Monat nicht aktiv, nicht "echte 0"; CLAUDE.md-Linie 0 ≠ None),
    April WP-Werte = 80/320.
    """
    from backend.api.routes.monatsdaten import list_monatsdaten_aggregiert

    async with _session_ctx() as session:
        # Anlage anlegen
        anlage = Anlage(anlagenname="TestAnlage", leistung_kwp=10.0)
        session.add(anlage)
        await session.flush()

        # Basis-Monatsdaten für März + April (Anlage hatte schon Netzwerte vorher)
        for monat in (3, 4):
            session.add(Monatsdaten(
                anlage_id=anlage.id,
                jahr=2025, monat=monat,
                netzbezug_kwh=200.0, einspeisung_kwh=50.0,
            ))

        # WP-Investition mit Anschaffung April 2025
        wp = Investition(
            anlage_id=anlage.id,
            typ="waermepumpe",
            bezeichnung="Test-WP",
            anschaffungsdatum=date(2025, 4, 1),
        )
        session.add(wp)
        await session.flush()

        # IMD: März (vor Anschaffung) + April (ok)
        session.add(InvestitionMonatsdaten(
            investition_id=wp.id, jahr=2025, monat=3,
            verbrauch_daten={"stromverbrauch_kwh": 100, "heizenergie_kwh": 400},
        ))
        session.add(InvestitionMonatsdaten(
            investition_id=wp.id, jahr=2025, monat=4,
            verbrauch_daten={"stromverbrauch_kwh": 80, "heizenergie_kwh": 320},
        ))
        await session.commit()

        # Endpoint aufrufen (kw-arg, sonst kollidiert mit Depends-Default)
        result = await list_monatsdaten_aggregiert(
            anlage_id=anlage.id, jahr=None, db=session,
        )
        by_monat = {(r.jahr, r.monat): r for r in result}

        maerz = by_monat.get((2025, 3))
        april = by_monat.get((2025, 4))

        assert maerz is not None, "März-Monatsdaten erwartet"
        assert april is not None, "April-Monatsdaten erwartet"
        assert maerz.wp_strom_kwh is None, (
            f"März WP-Strom muss None sein (Komponente nicht aktiv, nicht 'echte 0'), "
            f"war {maerz.wp_strom_kwh!r}"
        )
        assert maerz.wp_heizung_kwh is None, (
            f"März WP-Heizung muss None sein, war {maerz.wp_heizung_kwh!r}"
        )
        assert april.wp_strom_kwh == 80, (
            f"April WP-Strom muss 80 sein (Wert aus IMD), war {april.wp_strom_kwh!r}"
        )
        assert april.wp_heizung_kwh == 320, (
            f"April WP-Heizung muss 320 sein, war {april.wp_heizung_kwh!r}"
        )


async def test_aggregiert_endpoint_echte_null_unterscheidet_sich_von_none():
    """CLAUDE.md-Linie 0 ≠ None — IMD mit Wert 0 (z.B. Heizung im Sommer)
    muss als 0 ausgespielt werden, nicht als None."""
    from backend.api.routes.monatsdaten import list_monatsdaten_aggregiert

    async with _session_ctx() as session:
        anlage = Anlage(anlagenname="TestAnlage", leistung_kwp=10.0)
        session.add(anlage)
        await session.flush()

        session.add(Monatsdaten(
            anlage_id=anlage.id, jahr=2025, monat=7,
            netzbezug_kwh=80.0, einspeisung_kwh=200.0,
        ))

        wp = Investition(
            anlage_id=anlage.id, typ="waermepumpe",
            bezeichnung="Test-WP", anschaffungsdatum=date(2024, 1, 1),
        )
        session.add(wp)
        await session.flush()

        # Sommer-Monat: WP läuft kaum — Heizung tatsächlich 0, Warmwasser ein wenig.
        session.add(InvestitionMonatsdaten(
            investition_id=wp.id, jahr=2025, monat=7,
            verbrauch_daten={
                "stromverbrauch_kwh": 30,
                "heizenergie_kwh": 0,        # echte 0!
                "warmwasser_kwh": 90,
            },
        ))
        await session.commit()

        result = await list_monatsdaten_aggregiert(
            anlage_id=anlage.id, jahr=None, db=session,
        )
        juli = next(r for r in result if r.monat == 7)

        assert juli.wp_strom_kwh == 30, (
            f"WP-Strom muss 30 sein (Wert vorhanden), war {juli.wp_strom_kwh!r}"
        )
        assert juli.wp_heizung_kwh == 0, (
            f"WP-Heizung muss 0 sein (echte 0, IMD vorhanden), war {juli.wp_heizung_kwh!r}"
        )
        assert juli.wp_warmwasser_kwh == 90, (
            f"WP-Warmwasser muss 90 sein, war {juli.wp_warmwasser_kwh!r}"
        )


# ── Runner ──────────────────────────────────────────────────────────────────


_SYNC_TESTS = [
    test_ist_aktiv_im_monat_ohne_grenzen,
    test_ist_aktiv_im_monat_vor_anschaffung,
    test_ist_aktiv_im_monat_nach_stilllegung,
    test_ist_aktiv_im_monat_kombiniert,
]

_ASYNC_TESTS = [
    test_aggregiert_endpoint_ignoriert_vor_anschaffungs_imd,
    test_aggregiert_endpoint_echte_null_unterscheidet_sich_von_none,
]


async def _main() -> int:
    failures = 0
    for fn in _SYNC_TESTS:
        try:
            fn()
            print(f"OK   {fn.__name__}")
        except AssertionError as e:
            failures += 1
            print(f"FAIL {fn.__name__}: {e}")
            traceback.print_exc()
        except Exception as e:
            failures += 1
            print(f"ERR  {fn.__name__}: {type(e).__name__}: {e}")
            traceback.print_exc()
    for fn in _ASYNC_TESTS:
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
    total = len(_SYNC_TESTS) + len(_ASYNC_TESTS)
    if failures:
        print(f"\n{failures}/{total} Tests fehlgeschlagen.")
        return 1
    print(f"\nAlle {total} Tests grün.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
