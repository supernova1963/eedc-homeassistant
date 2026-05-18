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


async def test_alle_jahre_mit_anlagen_erweiterung():
    """Regression: Anlage über die Jahre erweitert. Bei „alle Jahre" darf
    der Nenner nicht den heutigen kWp-Stand × Jahresanzahl nutzen, sondern
    muss die pro Monat tatsächlich aktive PV-Leistung verwenden.

    Szenario: 3 kWp seit 2020, +6 kWp seit 2023 (heute 9 kWp).
    Jeder Modul-Anteil produziert sauber 1000 kWh/kWp/Jahr.
      - A (3 kWp): 6 Jahre × 3000 kWh = 18000 kWh
      - B (6 kWp): 3 Jahre × 6000 kWh = 18000 kWh
      - Σ = 36000 kWh
    Korrekt: 3 kWp·3 Jahre + 9 kWp·3 Jahre = 36 kWp·Jahre → 1000 kWh/kWp.
    Buggy (heutige 9 kWp × 6 Jahre = 54): nur ~667 kWh/kWp.
    """
    from backend.api.routes.cockpit.uebersicht import get_cockpit_uebersicht

    async with _session_ctx() as session:
        anlage = Anlage(
            anlagenname="ErweiterungsAnlage", leistung_kwp=9.0,
            latitude=52.0, longitude=10.0,
        )
        session.add(anlage)
        await session.flush()

        pv_a = Investition(
            anlage_id=anlage.id, typ="pv-module", bezeichnung="PV A",
            leistung_kwp=3.0, anschaffungsdatum=date(2020, 1, 1),
        )
        pv_b = Investition(
            anlage_id=anlage.id, typ="pv-module", bezeichnung="PV B",
            leistung_kwp=6.0, anschaffungsdatum=date(2023, 1, 1),
        )
        session.add_all([pv_a, pv_b])
        await session.flush()

        # PVGIS-Prognose (Jahresertrag/kWp ist hier irrelevant, nur Verteilung)
        _add_pvgis_prognose(session, anlage.id)

        # A: 2020–2025 (6 Jahre × 3000 kWh)
        for jahr in range(2020, 2026):
            for m in range(1, 13):
                kwh = 3000.0 * (SEASON_52N[m] / 100.0)
                _add_imd(session, pv_a.id, jahr, m, kwh)
        # B: 2023–2025 (3 Jahre × 6000 kWh)
        for jahr in range(2023, 2026):
            for m in range(1, 13):
                kwh = 6000.0 * (SEASON_52N[m] / 100.0)
                _add_imd(session, pv_b.id, jahr, m, kwh)
        await session.commit()

        resp = await get_cockpit_uebersicht(anlage_id=anlage.id, jahr=None, db=session)

        # Sanity-Check Eingangsdaten
        assert abs(resp.pv_erzeugung_kwh - 36000.0) < 1.0, (
            f"Test-Setup defekt: pv_erzeugung sollte 36000 sein, war {resp.pv_erzeugung_kwh}"
        )
        assert resp.spezifischer_ertrag_kwh_kwp is not None
        assert abs(resp.spezifischer_ertrag_kwh_kwp - 1000.0) < 5.0, (
            f"Anlagen-Erweiterung: spez_ertrag muss 1000 kWh/kWp sein "
            f"(per-Monat-aktives kWp), war {resp.spezifischer_ertrag_kwh_kwp}. "
            f"Bug-Wert wäre ~667."
        )


async def test_alle_jahre_ignoriert_vor_pv_monate():
    """Regression: bei jahr=None (alle Jahre) darf periode_anteil nicht aus
    WP-/Zähler-Monaten vor PV-Inbetriebnahme aufgebläht werden.

    Szenario: PV seit 2024 (2 volle Jahre 2024+2025), WP-IMDs seit 2020 (4
    weitere Jahre nur WP), Stromzähler-Monatsdaten seit 2018 (6 weitere
    Jahre). Bug-Symptom war: covered_months umfasste 2018–2025 → periode
    ≈ 8, spez_ertrag = total_pv / (kWp × 8) statt × 2.
    """
    from backend.api.routes.cockpit.uebersicht import get_cockpit_uebersicht

    async with _session_ctx() as session:
        anlage, pv = await _setup_anlage_5kwp(session)
        # PV-Anschaffung explizit 2024 setzen (überschreibt _setup-Default)
        pv.anschaffungsdatum = date(2024, 1, 1)

        # WP seit 2020 — IMDs vor PV-Zeit
        wp = Investition(
            anlage_id=anlage.id, typ="waermepumpe",
            bezeichnung="WP", anschaffungsdatum=date(2020, 1, 1),
        )
        session.add(wp)
        await session.flush()

        _add_pvgis_prognose(session, anlage.id)

        # WP-IMDs für 2020–2023 (vor PV) — dürfen periode_anteil NICHT aufblähen
        for jahr in (2020, 2021, 2022, 2023):
            for m in range(1, 13):
                session.add(InvestitionMonatsdaten(
                    investition_id=wp.id, jahr=jahr, monat=m,
                    verbrauch_daten={"stromverbrauch_kwh": 100.0, "heizenergie_kwh": 400.0},
                ))

        # Zähler-Monatsdaten ab 2018 (noch früher) — dürfen ebenfalls nicht zählen
        for jahr in (2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025):
            for m in range(1, 13):
                session.add(Monatsdaten(
                    anlage_id=anlage.id, jahr=jahr, monat=m,
                    netzbezug_kwh=200.0, einspeisung_kwh=50.0,
                ))

        # PV-IMDs für 2 volle Jahre 2024+2025 (gemäß 52°N-Verteilung)
        for jahr in (2024, 2025):
            for m in range(1, 13):
                kwh = 5000.0 * (SEASON_52N[m] / 100.0)
                _add_imd(session, pv.id, jahr, m, kwh)
        await session.commit()

        resp = await get_cockpit_uebersicht(anlage_id=anlage.id, jahr=None, db=session)

        # 2 PV-Jahre × 5000 kWh / (5 kWp × 2) = 1000 kWh/kWp.
        # Buggy-Verhalten lieferte ~250 (Faktor ~4 zu niedrig).
        assert resp.spezifischer_ertrag_kwh_kwp is not None
        assert abs(resp.spezifischer_ertrag_kwh_kwp - 1000.0) < 5.0, (
            f"'Alle Jahre' muss 1000 kWh/kWp ergeben (2 volle PV-Jahre), "
            f"war {resp.spezifischer_ertrag_kwh_kwp}"
        )


async def test_alle_jahre_mit_teil_stilllegung():
    """Regression: Anlage wird über die Jahre verkleinert (Teil-Rückbau).
    Bei „alle Jahre" muss der Nenner pro Monat die DAMALS aktive Leistung
    nutzen — sonst wird in den frühen Jahren mit der heute noch
    verbleibenden Restleistung gerechnet und der Wert ist zu hoch.

    Szenario: 10 kWp seit 2020. Anfang 2023 wird ein 4-kWp-Modul
    stillgelegt → ab 2023 nur noch 6 kWp aktiv.
      - A (6 kWp, durchgehend): 6 Jahre × 6000 kWh = 36000 kWh
      - B (4 kWp, 2020–2022):   3 Jahre × 4000 kWh = 12000 kWh
      - Σ pv_erzeugung = 48000 kWh
    Korrekt: 6 kWp·6 Jahre + 4 kWp·3 Jahre = 48 kWp·Jahre → 1000 kWh/kWp.
    Buggy (heutige 6 kWp × 6 Jahre = 36): 48000/36 ≈ 1333 (zu hoch).
    """
    from backend.api.routes.cockpit.uebersicht import get_cockpit_uebersicht

    async with _session_ctx() as session:
        anlage = Anlage(
            anlagenname="StilllegungsAnlage", leistung_kwp=6.0,
            latitude=52.0, longitude=10.0,
        )
        session.add(anlage)
        await session.flush()

        pv_a = Investition(
            anlage_id=anlage.id, typ="pv-module", bezeichnung="PV A (Bestand)",
            leistung_kwp=6.0, anschaffungsdatum=date(2020, 1, 1),
        )
        pv_b = Investition(
            anlage_id=anlage.id, typ="pv-module", bezeichnung="PV B (rückgebaut)",
            leistung_kwp=4.0,
            anschaffungsdatum=date(2020, 1, 1),
            stilllegungsdatum=date(2022, 12, 31),
        )
        session.add_all([pv_a, pv_b])
        await session.flush()

        _add_pvgis_prognose(session, anlage.id)

        # A: 2020–2025 (6 Jahre × 6000 kWh)
        for jahr in range(2020, 2026):
            for m in range(1, 13):
                _add_imd(session, pv_a.id, jahr, m, 6000.0 * (SEASON_52N[m] / 100.0))
        # B: 2020–2022 (3 Jahre × 4000 kWh) — stillgelegt Ende 2022
        for jahr in range(2020, 2023):
            for m in range(1, 13):
                _add_imd(session, pv_b.id, jahr, m, 4000.0 * (SEASON_52N[m] / 100.0))
        await session.commit()

        resp = await get_cockpit_uebersicht(anlage_id=anlage.id, jahr=None, db=session)

        assert abs(resp.pv_erzeugung_kwh - 48000.0) < 1.0, (
            f"Test-Setup defekt: pv_erzeugung sollte 48000 sein, war {resp.pv_erzeugung_kwh}"
        )
        # anlagenleistung_kwp = heute aktive Module = 6 kWp (B ist stillgelegt)
        assert abs(resp.anlagenleistung_kwp - 6.0) < 0.01, (
            f"anlagenleistung_kwp soll 6.0 (nur PV A heute aktiv) sein, "
            f"war {resp.anlagenleistung_kwp}"
        )
        assert resp.spezifischer_ertrag_kwh_kwp is not None
        assert abs(resp.spezifischer_ertrag_kwh_kwp - 1000.0) < 5.0, (
            f"Teil-Rückbau: spez_ertrag muss 1000 kWh/kWp sein "
            f"(per-Monat-aktives kWp), war {resp.spezifischer_ertrag_kwh_kwp}. "
            f"Bug-Wert wäre ~1333 (heutige 6 kWp über alle 6 Jahre)."
        )


# ── Runner ──────────────────────────────────────────────────────────────────


_ASYNC_TESTS = [
    test_ytd_mit_pvgis_wird_annualisiert,
    test_komplettes_jahr_unveraendert,
    test_fallback_ohne_pvgis_nutzt_52n_verteilung,
    test_alle_jahre_mit_anlagen_erweiterung,
    test_alle_jahre_mit_teil_stilllegung,
    test_alle_jahre_ignoriert_vor_pv_monate,
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
