"""
Unit-Tests für PV-Counter-Spike-Cap (Forum #529 / dietmar1968).

Bug: HA-Counter-Off-by-one nach Restart erzeugt pv_kw=109 kW Stundenwert
bei 11.2-kWp-Anlage. Aggregator schrieb den Spike ungekappt in
TagesEnergieProfil.pv_kw. Reaggregation war idempotent → keine Heilung.

Fix v3.30.2:
- SoT-Helper `schwelle_pv_einspeisung_stunde_kwh(kwp) = kwp × 1.5`
- Cap in `get_hourly_kwh_by_category` für Kategorien "pv" und "einspeisung":
  Wert > Schwelle → None (Lücke statt Spike)
- Daten-Checker zieht dieselbe Schwelle aus dem Helper (SoT-Konvention).
"""

from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND_ROOT))

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402

from backend.core.database import Base  # noqa: E402
from backend.models import Anlage, Investition  # noqa: E402
from backend.models.sensor_snapshot import SensorSnapshot  # noqa: E402
from backend.services.snapshot.aggregator import get_hourly_kwh_by_category  # noqa: E402
from backend.services.snapshot.plausibility import (  # noqa: E402
    SPIKE_FAKTOR_STUNDE,
    cap_pv_einspeisung_stunde,
    schwelle_pv_einspeisung_stunde_kwh,
)


# ───────────────────────────── Helper ──────────────────────────────


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


async def _make_anlage_with_pv(
    session: AsyncSession, *, leistung_kwp: float = 11.2,
) -> tuple[Anlage, Investition]:
    """Anlage mit einem PV-Modul + Counter-Mapping."""
    anlage = Anlage(anlagenname="Test PV", leistung_kwp=leistung_kwp, standort_land="DE")
    session.add(anlage)
    await session.flush()
    inv = Investition(
        anlage_id=anlage.id,
        typ="pv-module",
        bezeichnung="Dach Süd",
        parameter={"leistung_kwp": leistung_kwp},
    )
    session.add(inv)
    await session.flush()
    anlage.sensor_mapping = {
        "investitionen": {
            str(inv.id): {
                "felder": {
                    "pv_erzeugung_kwh": {
                        "strategie": "sensor",
                        "sensor_id": "sensor.pv_total",
                    }
                }
            }
        }
    }
    await session.commit()
    return anlage, inv


async def _put_snapshot(
    session: AsyncSession,
    anlage_id: int,
    sensor_key: str,
    zeitpunkt: datetime,
    wert: float,
) -> None:
    session.add(SensorSnapshot(
        anlage_id=anlage_id,
        sensor_key=sensor_key,
        zeitpunkt=zeitpunkt,
        wert_kwh=wert,
        quelle="ha_statistics",
    ))


# ───────────────────────────── SoT-Schwelle ──────────────────────────────


def test_schwelle_pv_einspeisung_stunde_kwh_normalfall():
    """11.2 kWp × 1.5 = 16.8 kWh/h."""
    assert abs(schwelle_pv_einspeisung_stunde_kwh(11.2) - 16.8) < 1e-9


def test_schwelle_pv_einspeisung_stunde_kwh_kein_kwp():
    """Ohne kWp → kein Cap (Schwelle None)."""
    assert schwelle_pv_einspeisung_stunde_kwh(None) is None
    assert schwelle_pv_einspeisung_stunde_kwh(0) is None
    assert schwelle_pv_einspeisung_stunde_kwh(-1) is None


def test_spike_faktor_konstante_dokumentiert():
    """Die Konstante steht im SoT-Helper, nicht in Konsumenten."""
    assert SPIKE_FAKTOR_STUNDE == 1.5


# ───────────────────────────── Cap-Funktion ──────────────────────────────


def test_cap_unter_schwelle_unveraendert():
    """Werte unter Schwelle bleiben unverändert."""
    out = cap_pv_einspeisung_stunde(
        12.0, 16.8, anlage_id=1, datum=date(2026, 5, 14), stunde=11, kategorie="pv"
    )
    assert out == 12.0


def test_cap_ueber_schwelle_None():
    """Werte über Schwelle werden zu None (Lücke)."""
    out = cap_pv_einspeisung_stunde(
        109.0, 16.8, anlage_id=1, datum=date(2026, 5, 14), stunde=11, kategorie="pv"
    )
    assert out is None


def test_cap_schwelle_none_kein_cap():
    """Ohne Schwelle (kein kWp) findet kein Cap statt — auch nicht bei Riesenwert."""
    out = cap_pv_einspeisung_stunde(
        9999.0, None, anlage_id=1, datum=date(2026, 5, 14), stunde=11, kategorie="pv"
    )
    assert out == 9999.0


def test_cap_wert_none_bleibt_none():
    """None-Eingabe → None-Ausgabe (keine Spike-Konstruktion)."""
    out = cap_pv_einspeisung_stunde(
        None, 16.8, anlage_id=1, datum=date(2026, 5, 14), stunde=11, kategorie="pv"
    )
    assert out is None


def test_cap_grenzwert_exakt_durchlassen():
    """Wert == Schwelle ist noch zulässig (≤, nicht <)."""
    out = cap_pv_einspeisung_stunde(
        16.8, 16.8, anlage_id=1, datum=date(2026, 5, 14), stunde=11, kategorie="pv"
    )
    assert out == 16.8


# ───────────────────────────── Integration: Aggregator ──────────────────────────────


async def test_aggregator_pv_spike_geklemmt():
    """
    Forum #529-Szenario: pv_kw=109 kW um 11:00 bei 11.2-kWp-Anlage.
    Slot 11 muss nach Cap None liefern, andere Slots unverändert.

    Backward-Konvention: Slot h = snap[h] − snap[h−1] (Boundary-Offsets −1..23).
    """
    async with _session_ctx() as session:
        anlage, inv = await _make_anlage_with_pv(session, leistung_kwp=11.2)

        datum = date(2026, 5, 14)
        sensor_key = f"inv:{inv.id}:pv_erzeugung_kwh"

        # 25 Boundary-Snapshots: Counter wächst stündlich um 2 kWh,
        # außer von h=10 → h=11 wo der Spike-Sprung +109 kWh passiert.
        base = 1000.0
        for offset in range(-1, 24):
            ts = datetime.combine(datum, datetime.min.time()) + timedelta(hours=offset)
            # Stunde 11 hat einen Sprung von +109 statt +2
            if offset >= 11:
                wert = base + (offset + 1) * 2 + 107  # +107 zusätzlich nach Spike
            else:
                wert = base + (offset + 1) * 2
            await _put_snapshot(session, anlage.id, sensor_key, ts, wert)
        await session.commit()

        result = await get_hourly_kwh_by_category(
            session, anlage, {str(inv.id): inv}, datum
        )

        # Slot 11 enthält den Spike → muss nach Cap None sein
        assert result[11]["pv"] is None, f"Slot 11 sollte gekappt sein, ist: {result[11]['pv']}"

        # Slot 10 (vor Spike): normaler Wert ~2 kWh
        assert result[10]["pv"] is not None
        assert abs(result[10]["pv"] - 2.0) < 0.01

        # Slot 12 (nach Spike): normaler Wert ~2 kWh — kein Folge-Cap
        assert result[12]["pv"] is not None
        assert abs(result[12]["pv"] - 2.0) < 0.01


async def test_aggregator_pv_normal_kein_cap():
    """Normalbetrieb: alle Stundenwerte unter Schwelle → keine None-Werte."""
    async with _session_ctx() as session:
        anlage, inv = await _make_anlage_with_pv(session, leistung_kwp=11.2)

        datum = date(2026, 5, 14)
        sensor_key = f"inv:{inv.id}:pv_erzeugung_kwh"

        # Counter wächst stündlich um 8 kWh (Sommer-Peak realistisch < 16.8)
        for offset in range(-1, 24):
            ts = datetime.combine(datum, datetime.min.time()) + timedelta(hours=offset)
            wert = 1000.0 + (offset + 1) * 8
            await _put_snapshot(session, anlage.id, sensor_key, ts, wert)
        await session.commit()

        result = await get_hourly_kwh_by_category(
            session, anlage, {str(inv.id): inv}, datum
        )

        # Alle Slots haben pv ≈ 8 kWh (unter Schwelle 16.8)
        for h in range(24):
            assert result[h]["pv"] is not None, f"Slot {h} sollte gefüllt sein"
            assert abs(result[h]["pv"] - 8.0) < 0.01, f"Slot {h}: {result[h]['pv']}"


async def test_aggregator_anlage_ohne_kwp_kein_cap():
    """
    Anlage ohne leistung_kwp → kein Cap (Schwelle None). Selbst absurde
    Stundenwerte bleiben unverändert, weil ohne kWp keine sinnvolle Grenze
    bekannt ist (Daten-Checker filtert solche Anlagen aus eigenem Pfad).
    """
    async with _session_ctx() as session:
        anlage, inv = await _make_anlage_with_pv(session, leistung_kwp=0.0)

        datum = date(2026, 5, 14)
        sensor_key = f"inv:{inv.id}:pv_erzeugung_kwh"

        # Spike von +50 kWh
        for offset in range(-1, 24):
            ts = datetime.combine(datum, datetime.min.time()) + timedelta(hours=offset)
            wert = 1000.0 + (offset + 1) * 2
            if offset >= 11:
                wert += 48
            await _put_snapshot(session, anlage.id, sensor_key, ts, wert)
        await session.commit()

        result = await get_hourly_kwh_by_category(
            session, anlage, {str(inv.id): inv}, datum
        )

        # Slot 11 enthält den Spike (~50 kWh) — bleibt erhalten, kein Cap
        assert result[11]["pv"] is not None
        assert result[11]["pv"] > 40


# ───────────────────────────── Daten-Checker SoT-Konsistenz ──────────────────────────────


def test_daten_checker_schwelle_aus_sot_helper():
    """
    Daten-Checker und Aggregator nutzen dieselbe Schwelle aus
    `plausibility.schwelle_pv_einspeisung_stunde_kwh`. Wer den Faktor ändert,
    ändert beide Stellen automatisch — kein Drift mehr möglich.
    """
    import inspect

    from backend.services import daten_checker as dc

    src = inspect.getsource(dc.DatenChecker._check_energieprofil_plausibilitaet)
    # Garantiert: keine eigene `kwp * 1.5`-Hardcodierung mehr in daten_checker
    assert "kwp * 1.5" not in src, "daten_checker enthält noch eigene Schwelle — SoT-Drift!"
    assert "schwelle_pv_einspeisung_stunde_kwh" in src, "daten_checker nutzt SoT-Helper nicht"
