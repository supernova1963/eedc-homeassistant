"""
Akzeptanztest für Genauigkeits-Tracking-Bug — IST darf keine
Batterie-Netto-Ladung als PV-Erzeugung mitzählen (Rainer-PN 2026-05-16).

Self-contained Standalone-Script:

    eedc/backend/venv/bin/python eedc/backend/tests/test_genauigkeit_pv_only.py

Hintergrund (siehe `docs/KONZEPT-ETAPPE-4-HA-LTS-SOT.md` Abschnitt 5): die
alte Filter-Logik `v > 0 and k not in {strompreis, netzbezug, einspeisung}`
ließ alle Sub-Keys mit positivem Wert durch — auch `batterie_*` mit netto
positiver Tages-Ladung. Bei einer Anlage mit ~5 kWh Netto-Batterie-Ladung
am Tag entstand 5 kWh künstliche IST-Überschätzung gegenüber PV-Ertrag.

Fix: Whitelist auf `pv_*` + `bkw_*` Prefix — analog Frontend-Tabelle.

Geprüft:
  1. komponenten_kwh = {pv_3: 67, batterie_5: 4.7, wp_7: -3.2}
     → IST muss exakt 67 sein, NICHT 71.7 (alt) oder 67 + 4.7 = 71.7
  2. komponenten_kwh = {pv_3: 50, bkw_4: 17, sonstiges_8: 2}
     → IST muss exakt 67 (pv + bkw), nicht 69 (inkl. sonstiges)
  3. komponenten_kwh nur Verbraucher (negative Werte) → IST = 0
  4. komponenten_kwh leer/None → ist_kwh = None
"""

from __future__ import annotations

import asyncio
import sys
import traceback
from contextlib import asynccontextmanager
from datetime import date, timedelta
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[2]  # eedc/
sys.path.insert(0, str(_BACKEND_ROOT))

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402

from backend.core.database import Base  # noqa: E402
from backend.models import Anlage  # noqa: E402, F401
from backend.models.tages_energie_profil import TagesZusammenfassung  # noqa: E402


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


async def _make_anlage(db: AsyncSession) -> int:
    anlage = Anlage(anlagenname="Test", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    return anlage.id


async def _seed_tz(
    db: AsyncSession,
    anlage_id: int,
    datum: date,
    komponenten_kwh: dict,
    pv_prognose_kwh: float | None = None,
) -> None:
    db.add(TagesZusammenfassung(
        anlage_id=anlage_id, datum=datum,
        komponenten_kwh=komponenten_kwh,
        pv_prognose_kwh=pv_prognose_kwh,
    ))


async def _call_genauigkeit(anlage_id: int, db: AsyncSession):
    from backend.api.routes.prognosen import get_prognosen_genauigkeit
    return await get_prognosen_genauigkeit(anlage_id=anlage_id, tage=30, db=db)


async def test_batterie_nettoladen_zaehlt_nicht():
    """Batterie-Sub-Key mit netto positivem Tageswert darf nicht in IST."""
    async with _session_ctx() as db:
        anlage_id = await _make_anlage(db)
        gestern = date.today() - timedelta(days=1)
        await _seed_tz(db, anlage_id, gestern, komponenten_kwh={
            "pv_3": 67.0,
            "batterie_5": 4.7,    # netto Ladung — darf nicht zur IST-Erzeugung
            "wp_7": -3.2,         # Verbraucher (negativ)
            "strompreis": 32.5,   # ct/kWh, nie Energie
        }, pv_prognose_kwh=68.0)
        await db.commit()

        res = await _call_genauigkeit(anlage_id, db)
        eintrag = res.tage[0]
        assert eintrag.ist_kwh == 67.0, (
            f"IST muss exakt PV sein (67.0), bekommen: {eintrag.ist_kwh}"
        )


async def test_pv_und_bkw_werden_summiert():
    """pv_* und bkw_* gehen in IST; sonstiges_* nicht."""
    async with _session_ctx() as db:
        anlage_id = await _make_anlage(db)
        gestern = date.today() - timedelta(days=1)
        await _seed_tz(db, anlage_id, gestern, komponenten_kwh={
            "pv_3": 50.0,
            "bkw_4": 17.0,
            "sonstiges_8": 2.0,   # eigene Erzeuger-Investition, aber kein PV
        })
        await db.commit()

        res = await _call_genauigkeit(anlage_id, db)
        eintrag = res.tage[0]
        assert eintrag.ist_kwh == 67.0, (
            f"IST = pv + bkw = 67.0; bekommen: {eintrag.ist_kwh} "
            "(falls 69.0: sonstiges fälschlich mitgezählt)"
        )


async def test_nur_verbraucher_ist_null():
    """Tag ohne PV-Erzeugung (z. B. Wartung): IST = 0."""
    async with _session_ctx() as db:
        anlage_id = await _make_anlage(db)
        gestern = date.today() - timedelta(days=1)
        await _seed_tz(db, anlage_id, gestern, komponenten_kwh={
            "wp_7": -8.5,
            "wallbox_2": -15.0,
        })
        await db.commit()

        res = await _call_genauigkeit(anlage_id, db)
        eintrag = res.tage[0]
        assert eintrag.ist_kwh == 0.0, (
            f"Reine Verbraucher: IST=0, bekommen: {eintrag.ist_kwh}"
        )


async def test_leeres_komponenten_kwh_keine_ist():
    """Wenn komponenten_kwh leer/None: IST bleibt None — Tag nicht in Statistik."""
    async with _session_ctx() as db:
        anlage_id = await _make_anlage(db)
        gestern = date.today() - timedelta(days=1)
        await _seed_tz(db, anlage_id, gestern, komponenten_kwh=None)
        await db.commit()

        res = await _call_genauigkeit(anlage_id, db)
        eintrag = res.tage[0]
        assert eintrag.ist_kwh is None, (
            f"Leeres komponenten_kwh → ist_kwh=None, bekommen: {eintrag.ist_kwh}"
        )


_TESTS = [
    test_batterie_nettoladen_zaehlt_nicht,
    test_pv_und_bkw_werden_summiert,
    test_nur_verbraucher_ist_null,
    test_leeres_komponenten_kwh_keine_ist,
]


async def _run_all() -> int:
    failures = 0
    for test in _TESTS:
        try:
            await test()
            print(f"OK   {test.__name__}")
        except AssertionError as e:
            failures += 1
            print(f"FAIL {test.__name__}\n     {e}")
        except Exception:
            failures += 1
            print(f"ERR  {test.__name__}")
            traceback.print_exc()
    return failures


if __name__ == "__main__":
    failures = asyncio.run(_run_all())
    if failures:
        print(f"\n{failures} von {len(_TESTS)} Tests fehlgeschlagen.")
        sys.exit(1)
    print(f"\nAlle {len(_TESTS)} Tests grün.")
