"""
Akzeptanztests für die periodengenaue & jahresverlauf-gewichtete Berechnung
des spezifischen Ertrags im Cockpit.

Hintergrund: Vorher wurde `spez_ertrag = pv_erzeugung / kWp` gerechnet. Im
laufenden Jahr (Jan–Mai sind nur ~30 % des Jahresertrags) sah der Wert dann
absurd niedrig aus. Jetzt: `pv_erzeugung / (kWp × periode_anteil)`, wobei
`periode_anteil` aus den PVGIS-Monatsgewichten kommt (Fallback: typische
52°N-Verteilung).

Self-contained Standalone-Script:

    eedc/backend/venv/bin/python eedc/backend/tests/test_cockpit_spez_ertrag_periode.py
"""

from __future__ import annotations

import asyncio
import sys
import traceback
from contextlib import asynccontextmanager
from datetime import date, datetime
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[2]  # eedc/
sys.path.insert(0, str(_BACKEND_ROOT))

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402

from backend.core.database import Base  # noqa: E402
from backend.models import (  # noqa: E402, F401
    Anlage, Investition, InvestitionMonatsdaten, Monatsdaten,
)
from backend.models.pvgis_prognose import PVGISPrognose  # noqa: E402


# Typische 52°N-Monatsverteilung (Prozent des Jahresertrags) — identisch zum
# Fallback im Cockpit-Endpoint. Summe ≈ 100.
SEASON_52N = {
    1: 2.5, 2: 4.5, 3: 8.0, 4: 11.5, 5: 13.0, 6: 13.5,
    7: 13.5, 8: 12.0, 9: 9.0, 10: 6.5, 11: 3.5, 12: 2.5,
}


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


async def _setup_anlage_5kwp(session: AsyncSession) -> tuple[Anlage, Investition]:
    """5-kWp-Anlage mit einem PV-Modul, Inbetriebnahme 2020."""
    anlage = Anlage(
        anlagenname="TestAnlage", leistung_kwp=5.0,
        latitude=52.0, longitude=10.0,
    )
    session.add(anlage)
    await session.flush()

    pv = Investition(
        anlage_id=anlage.id,
        typ="pv-module",
        bezeichnung="PV-Modul",
        leistung_kwp=5.0,
        anschaffungsdatum=date(2020, 1, 1),
    )
    session.add(pv)
    await session.flush()
    return anlage, pv


def _add_pvgis_prognose(session: AsyncSession, anlage_id: int) -> None:
    """PVGIS-Prognose mit 52°N-Monatsverteilung, Jahresertrag 5000 kWh
    (=> Soll-spez-Ertrag 1000 kWh/kWp bei 5 kWp)."""
    monatswerte = [
        {"monat": m, "e_m": 5000.0 * (anteil / 100.0), "h_m": 0.0, "sd_m": 0.0}
        for m, anteil in SEASON_52N.items()
    ]
    session.add(PVGISPrognose(
        anlage_id=anlage_id,
        abgerufen_am=datetime(2025, 12, 1),
        latitude=52.0, longitude=10.0,
        neigung_grad=30.0, ausrichtung_grad=0.0,
        system_losses=14.0,
        jahresertrag_kwh=5000.0,
        spezifischer_ertrag_kwh_kwp=1000.0,
        gesamt_leistung_kwp=5.0,
        monatswerte=monatswerte,
        ist_aktiv=True,
    ))


def _add_imd(session: AsyncSession, inv_id: int, jahr: int, monat: int, kwh: float) -> None:
    session.add(InvestitionMonatsdaten(
        investition_id=inv_id, jahr=jahr, monat=monat,
        verbrauch_daten={"pv_erzeugung_kwh": kwh},
    ))


# ── Tests ───────────────────────────────────────────────────────────────────


async def test_ytd_mit_pvgis_wird_annualisiert():
    """4 Monate Jan–Apr 2026 mit Erzeugung gemäß 52°N-Verteilung
    (5000 kWh × (2.5+4.5+8.0+11.5)/100 = 1325 kWh).

    Erwartet: spez_ertrag annualisiert auf ~1000 kWh/kWp, NICHT die rohe
    265 kWh/kWp (= 1325 / 5).
    """
    from backend.api.routes.cockpit.uebersicht import get_cockpit_uebersicht

    async with _session_ctx() as session:
        anlage, pv = await _setup_anlage_5kwp(session)
        _add_pvgis_prognose(session, anlage.id)

        jan_apr_anteil = sum(SEASON_52N[m] for m in (1, 2, 3, 4)) / 100.0
        pv_ytd_kwh = 5000.0 * jan_apr_anteil  # 1325 kWh
        for m in (1, 2, 3, 4):
            kwh = 5000.0 * (SEASON_52N[m] / 100.0)
            _add_imd(session, pv.id, 2026, m, kwh)
        await session.commit()

        resp = await get_cockpit_uebersicht(anlage_id=anlage.id, jahr=2026, db=session)

        # Roher Wert wäre pv_ytd_kwh / 5 = 265 kWh/kWp — viel zu niedrig.
        # Annualisiert: pv_ytd_kwh / (5 × jan_apr_anteil) ≈ 1000 kWh/kWp.
        roh = round(pv_ytd_kwh / 5.0, 1)
        annualisiert = round(pv_ytd_kwh / (5.0 * jan_apr_anteil), 1)

        assert resp.spezifischer_ertrag_kwh_kwp is not None, "spez_ertrag darf nicht None sein"
        assert abs(resp.spezifischer_ertrag_kwh_kwp - annualisiert) < 1.0, (
            f"Erwartet ~{annualisiert} kWh/kWp (annualisiert), "
            f"war {resp.spezifischer_ertrag_kwh_kwp} (roh wäre {roh})"
        )


async def test_komplettes_jahr_unveraendert():
    """Volles Jahr 12 Monate, Jahresertrag 5000 kWh — periode_anteil=1.0.
    Erwartet: spez_ertrag == 1000 kWh/kWp (wie vor dem Fix)."""
    from backend.api.routes.cockpit.uebersicht import get_cockpit_uebersicht

    async with _session_ctx() as session:
        anlage, pv = await _setup_anlage_5kwp(session)
        _add_pvgis_prognose(session, anlage.id)

        for m in range(1, 13):
            kwh = 5000.0 * (SEASON_52N[m] / 100.0)
            _add_imd(session, pv.id, 2025, m, kwh)
        await session.commit()

        resp = await get_cockpit_uebersicht(anlage_id=anlage.id, jahr=2025, db=session)

        assert resp.spezifischer_ertrag_kwh_kwp is not None
        assert abs(resp.spezifischer_ertrag_kwh_kwp - 1000.0) < 1.0, (
            f"Volljahr soll 1000 kWh/kWp ergeben, war {resp.spezifischer_ertrag_kwh_kwp}"
        )


async def test_fallback_ohne_pvgis_nutzt_52n_verteilung():
    """Keine PVGISPrognose vorhanden — Fallback auf die typische 52°N-
    Verteilung soll den gleichen Periodenanteil ergeben wie der explizite
    PVGIS-Fall (im Test ist die PVGIS-Verteilung absichtlich identisch
    mit dem Fallback)."""
    from backend.api.routes.cockpit.uebersicht import get_cockpit_uebersicht

    async with _session_ctx() as session:
        anlage, pv = await _setup_anlage_5kwp(session)
        # KEINE PVGISPrognose

        jan_apr_anteil = sum(SEASON_52N[m] for m in (1, 2, 3, 4)) / 100.0
        pv_ytd_kwh = 5000.0 * jan_apr_anteil
        for m in (1, 2, 3, 4):
            kwh = 5000.0 * (SEASON_52N[m] / 100.0)
            _add_imd(session, pv.id, 2026, m, kwh)
        await session.commit()

        resp = await get_cockpit_uebersicht(anlage_id=anlage.id, jahr=2026, db=session)

        annualisiert = pv_ytd_kwh / (5.0 * jan_apr_anteil)  # ≈ 1000
        roh = pv_ytd_kwh / 5.0  # ≈ 265

        assert resp.spezifischer_ertrag_kwh_kwp is not None
        assert abs(resp.spezifischer_ertrag_kwh_kwp - annualisiert) < 1.0, (
            f"Fallback-Verteilung soll auf ~{annualisiert:.1f} annualisieren, "
            f"war {resp.spezifischer_ertrag_kwh_kwp} (roh wäre {roh:.1f})"
        )
        # Sicherheitsnetz: alter Bug würde den rohen Wert liefern.
        assert resp.spezifischer_ertrag_kwh_kwp > 500, (
            "Fallback darf nicht in den alten rohen Pfad zurückfallen "
            f"(wäre ~{roh:.0f} kWh/kWp)"
        )


# ── Runner ──────────────────────────────────────────────────────────────────


_ASYNC_TESTS = [
    test_ytd_mit_pvgis_wird_annualisiert,
    test_komplettes_jahr_unveraendert,
    test_fallback_ohne_pvgis_nutzt_52n_verteilung,
]


async def _main() -> int:
    failures = 0
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
    total = len(_ASYNC_TESTS)
    if failures:
        print(f"\n{failures}/{total} Tests fehlgeschlagen.")
        return 1
    print(f"\nAlle {total} Tests grün.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
