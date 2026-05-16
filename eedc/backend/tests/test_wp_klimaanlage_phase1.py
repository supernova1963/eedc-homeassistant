"""
Phase 1 Klimaanlage-Erweiterung im WP-Modell (Forum #548 alex_s9027).

Split-Klimaanlagen sind physikalisch Luft-Luft-Wärmepumpen (Reverse-Cycle),
haben aber typischerweise keinen Wärmemengenzähler — nur einen Stromzähler.

Phase 1 macht zwei Anpassungen:
1. Daten-Checker meldet bei `wp_art="luft_luft"` keine "Heizwärme fehlt"-Warnung
   (das ist bei Klimas das normale Verhalten, kein Datenloch).
2. JAZ/COP-Berechnung in den Cockpit-Routes liefert None statt 0, wenn
   wp_strom > 0 aber wp_waerme = 0 (siehe geänderte uebersicht.py / komponenten.py /
   pdf_operations.py / social.py / jahresbericht.py).
"""

from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND_ROOT))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.orm import selectinload  # noqa: E402

from backend.core.database import Base  # noqa: E402
from backend.models import Anlage, Investition, InvestitionMonatsdaten, Monatsdaten  # noqa: E402
from backend.services.daten_checker import DatenChecker  # noqa: E402


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


async def _reload_anlage(session, anlage_id):
    result = await session.execute(
        select(Anlage)
        .options(selectinload(Anlage.investitionen).selectinload(Investition.monatsdaten))
        .where(Anlage.id == anlage_id)
    )
    anlage = result.scalar_one()
    monatsdaten = list((await session.execute(
        select(Monatsdaten).where(Monatsdaten.anlage_id == anlage.id)
    )).scalars().all())
    return anlage, monatsdaten


def _imd(inv_id, jahr, monat, *, stromverbrauch_kwh=None, heizenergie_kwh=None):
    """Hilfs-Konstruktor für InvestitionMonatsdaten."""
    daten = {}
    if stromverbrauch_kwh is not None:
        daten["stromverbrauch_kwh"] = stromverbrauch_kwh
    if heizenergie_kwh is not None:
        daten["heizenergie_kwh"] = heizenergie_kwh
    return InvestitionMonatsdaten(
        investition_id=inv_id, jahr=jahr, monat=monat,
        verbrauch_daten=daten,
    )


async def test_klima_meldet_keine_heizwaerme_warnung():
    """Bei wp_art='luft_luft' fehlt die Heizenergie-Warnung im Daten-Checker."""
    async with _session_ctx() as session:
        anlage = Anlage(
            anlagenname="TestKlima",
            leistung_kwp=10.0,
            installationsdatum=date(2025, 1, 1),
        )
        session.add(anlage)
        await session.flush()

        klima = Investition(
            anlage_id=anlage.id, typ="waermepumpe",
            bezeichnung="Daikin Split", anschaffungsdatum=date(2025, 1, 1),
            parameter={"wp_art": "luft_luft"},
        )
        session.add(klima)
        await session.flush()

        # Stromverbrauch vorhanden, Heizenergie NICHT (Klima-Realität)
        for monat in range(1, 6):
            session.add(_imd(klima.id, 2025, monat, stromverbrauch_kwh=100.0))

        # Mindest-Anlagenmonatsdaten, damit Checker läuft
        for monat in range(1, 6):
            session.add(Monatsdaten(
                anlage_id=anlage.id, jahr=2025, monat=monat,
                einspeisung_kwh=200.0, netzbezug_kwh=150.0,
            ))
        await session.commit()

        anlage_loaded, monatsdaten = await _reload_anlage(session, anlage.id)
        klima_loaded = next(i for i in anlage_loaded.investitionen if i.typ == "waermepumpe")

        checker = DatenChecker(session)
        ergebnisse = checker._check_wp_monatsdaten(
            klima_loaded, "Daikin Split", klima_loaded.parameter, []
        )

        # Es darf KEINE "Heizwärme fehlt"-Meldung kommen
        heiz_warnungen = [
            e for e in ergebnisse if "Heizwärme fehlt" in e.meldung
        ]
        assert not heiz_warnungen, (
            f"Klimaanlage darf keine Heizwärme-Warnung bekommen, "
            f"erhielt aber: {[e.meldung for e in heiz_warnungen]}"
        )


async def test_klassische_wp_meldet_heizwaerme_warnung_weiterhin():
    """Bei wp_art='luft_wasser' (Standard-WP) fehlt die Heizwärme-Warnung weiterhin
    wenn heizenergie_kwh nicht vorliegt — kein Regress."""
    async with _session_ctx() as session:
        anlage = Anlage(
            anlagenname="TestWP",
            leistung_kwp=10.0,
            installationsdatum=date(2025, 1, 1),
        )
        session.add(anlage)
        await session.flush()

        wp = Investition(
            anlage_id=anlage.id, typ="waermepumpe",
            bezeichnung="Vitocal", anschaffungsdatum=date(2025, 1, 1),
            parameter={"wp_art": "luft_wasser"},
        )
        session.add(wp)
        await session.flush()

        for monat in range(1, 6):
            session.add(_imd(wp.id, 2025, monat, stromverbrauch_kwh=100.0))

        for monat in range(1, 6):
            session.add(Monatsdaten(
                anlage_id=anlage.id, jahr=2025, monat=monat,
                einspeisung_kwh=200.0, netzbezug_kwh=150.0,
            ))
        await session.commit()

        anlage_loaded, monatsdaten = await _reload_anlage(session, anlage.id)
        wp_loaded = next(i for i in anlage_loaded.investitionen if i.typ == "waermepumpe")

        checker = DatenChecker(session)
        ergebnisse = checker._check_wp_monatsdaten(
            wp_loaded, "Vitocal", wp_loaded.parameter, monatsdaten
        )

        heiz_warnungen = [
            e for e in ergebnisse if "Heizwärme fehlt" in e.meldung
        ]
        assert heiz_warnungen, (
            "Klassische Luft-Wasser-WP muss Heizwärme-Warnung bekommen, "
            "wenn heizenergie_kwh fehlt — sonst ist die Klima-Sonderbehandlung "
            "zu breit."
        )


async def test_wp_ohne_param_meldet_heizwaerme_warnung():
    """Legacy-WP ohne wp_art-Parameter zählt als klassische WP, bekommt Warnung."""
    async with _session_ctx() as session:
        anlage = Anlage(
            anlagenname="TestLegacy",
            leistung_kwp=10.0,
            installationsdatum=date(2025, 1, 1),
        )
        session.add(anlage)
        await session.flush()

        wp = Investition(
            anlage_id=anlage.id, typ="waermepumpe",
            bezeichnung="Legacy WP", anschaffungsdatum=date(2025, 1, 1),
            parameter={},  # kein wp_art
        )
        session.add(wp)
        await session.flush()

        for monat in range(1, 6):
            session.add(_imd(wp.id, 2025, monat, stromverbrauch_kwh=100.0))
        for monat in range(1, 6):
            session.add(Monatsdaten(
                anlage_id=anlage.id, jahr=2025, monat=monat,
                einspeisung_kwh=200.0, netzbezug_kwh=150.0,
            ))
        await session.commit()

        anlage_loaded, monatsdaten = await _reload_anlage(session, anlage.id)
        wp_loaded = next(i for i in anlage_loaded.investitionen if i.typ == "waermepumpe")

        checker = DatenChecker(session)
        ergebnisse = checker._check_wp_monatsdaten(
            wp_loaded, "Legacy WP", wp_loaded.parameter, monatsdaten
        )

        heiz_warnungen = [
            e for e in ergebnisse if "Heizwärme fehlt" in e.meldung
        ]
        assert heiz_warnungen, "Legacy-WP ohne wp_art darf nicht als Klima durchgehen"
