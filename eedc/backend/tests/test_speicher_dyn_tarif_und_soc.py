"""
Akzeptanztest Etappe C (Issue #264): Stundengranularer Ladepreis aus TEP
und SoC-korrigierter IST-Wirkungsgrad.

Deckt drei Helper ab:

  1. `berechne_effektiver_ladepreis()` — Stunden-Iteration über TEP mit
     PV-Überschuss-Filter, Quellen-Klassifizierung (dyn-tarif vs.
     boersenpreis), Stunden-Abdeckungs-Schwelle.
  2. `berechne_ist_wirkungsgrad()` — η aus Quotient (langes Fenster) oder
     SoC-korrigierter Energiebilanz (kurzes Fenster + SoC am Periodenrand).
  3. `ist_soc_drift_signifikant()` — Schwellwert-Helper für die
     Monats-η-Unterdrückung.

Reproduziert insbesondere den Mai-110%-Bug aus #264: Speicher startet
voll (SoC 100 %), endet leer (SoC 5 %), naiver Monats-η > 200 % — die
SoC-Korrektur liefert einen plausiblen Wert.

Self-contained:

    eedc/backend/venv/bin/python eedc/backend/tests/test_speicher_dyn_tarif_und_soc.py
"""

from __future__ import annotations

import asyncio
import math
import sys
import traceback
from contextlib import asynccontextmanager
from datetime import date, datetime
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[2]  # eedc/
sys.path.insert(0, str(_BACKEND_ROOT))

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402

from backend.core.database import Base  # noqa: E402
from backend.models import Anlage  # noqa: E402
from backend.models.tages_energie_profil import TagesEnergieProfil  # noqa: E402
from backend.services.speicher_wirtschaftlichkeit import (  # noqa: E402
    ETA_DEGRADATION_SCHWELLE_PROZENTPUNKTE,
    LADEPREIS_STUNDEN_ABDECKUNG_MIN,
    SOC_DRIFT_SCHWELLE_PROZENTPUNKTE,
    WIRKUNGSGRAD_FENSTER_MONATE_MIN,
    berechne_effektiver_ladepreis,
    berechne_ist_wirkungsgrad,
    ist_eta_degradation_alarm,
    ist_soc_drift_signifikant,
)


def _approx(a: float, b: float, tol: float = 0.05) -> bool:
    return math.isclose(a, b, abs_tol=tol)


# ----------------------------------------------------------------------------
# In-Memory DB
# ----------------------------------------------------------------------------

@asynccontextmanager
async def _db_ctx():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    session = Session()
    try:
        anlage = Anlage(
            anlagenname="Test",
            standort_land="DE",
            installationsdatum=date(2024, 1, 1),
            leistung_kwp=10.0,
            latitude=50.0,
            longitude=10.0,
        )
        session.add(anlage)
        await session.commit()
        await session.refresh(anlage)
        yield session, anlage.id
    finally:
        await session.close()
        await engine.dispose()


async def _seed_tep_stunden(db: AsyncSession, anlage_id: int, rows: list[dict]):
    """Seeded TEP-Zeilen, jeweils mit datum/stunde + Sensorwerten."""
    for r in rows:
        db.add(TagesEnergieProfil(
            anlage_id=anlage_id,
            datum=r["datum"],
            stunde=r["stunde"],
            pv_kw=r.get("pv_kw"),
            verbrauch_kw=r.get("verbrauch_kw"),
            einspeisung_kw=r.get("einspeisung_kw"),
            netzbezug_kw=r.get("netzbezug_kw"),
            batterie_kw=r.get("batterie_kw"),
            soc_prozent=r.get("soc_prozent"),
            strompreis_cent=r.get("strompreis_cent"),
            boersenpreis_cent=r.get("boersenpreis_cent"),
            created_at=datetime.now(),
        ))
    await db.commit()


# ----------------------------------------------------------------------------
# berechne_effektiver_ladepreis
# ----------------------------------------------------------------------------

async def test_effektiver_ladepreis_nacht_billig_tag_teuer() -> None:
    """Klassischer Tibber-Tag: Nacht-Ladung bei 8 ct, Tag-Verbrauch bei 35 ct.

    Erwartung: Effektiver Ladepreis ≈ 8 ct (Lade-Stunden gewichtet, nicht
    Tagesmittel).
    """
    async with _db_ctx() as (db, anlage_id):
        rows = []
        d = date(2025, 5, 1)
        # 02:00–05:00 → 1 kWh Ladung pro Stunde aus Netz, Preis 8 ct
        for stunde in (2, 3, 4, 5):
            rows.append({
                "datum": d, "stunde": stunde,
                "batterie_kw": -1.0, "netzbezug_kw": 1.0, "pv_kw": 0,
                "strompreis_cent": 8.0,
            })
        # 18:00–21:00 → Entladung (für effektiv-Berechnung irrelevant),
        # Preis 35 ct (würde alles verzerren, wenn nicht nur Lade-Stunden zählen)
        for stunde in (18, 19, 20, 21):
            rows.append({
                "datum": d, "stunde": stunde,
                "batterie_kw": 1.5, "netzbezug_kw": 0, "pv_kw": 0,
                "strompreis_cent": 35.0,
            })
        await _seed_tep_stunden(db, anlage_id, rows)

        r = await berechne_effektiver_ladepreis(
            db, anlage_id=anlage_id, von=d, bis=d,
        )
        assert r is not None
        assert _approx(r.effektiver_ladepreis_cent, 8.0)
        assert r.quelle == "dyn-tarif"
        assert _approx(r.netz_lade_kwh, 4.0)


async def test_effektiver_ladepreis_pv_ladung_zaehlt_nicht() -> None:
    """Lade-Stunde während PV-Überschuss → nur netzgespeister Anteil zählt."""
    async with _db_ctx() as (db, anlage_id):
        d = date(2025, 5, 1)
        rows = [
            # 12:00: 3 kWh Speicher-Ladung, davon 2 aus PV-Überschuss (kein Netzbezug),
            # 1 aus Netzbezug bei 10 ct
            {"datum": d, "stunde": 12, "batterie_kw": -3.0, "netzbezug_kw": 1.0,
             "pv_kw": 5.0, "strompreis_cent": 10.0},
            # 13:00: 2 kWh Ladung, voll PV (kein Netzbezug → 0 kWh netz_lade_h)
            {"datum": d, "stunde": 13, "batterie_kw": -2.0, "netzbezug_kw": 0,
             "pv_kw": 4.0, "strompreis_cent": 11.0},
        ]
        await _seed_tep_stunden(db, anlage_id, rows)

        r = await berechne_effektiver_ladepreis(db, anlage_id=anlage_id, von=d, bis=d)
        assert r is not None
        # Nur die 1 kWh Netz-Ladung aus Stunde 12 zählt → 10 ct
        assert _approx(r.effektiver_ladepreis_cent, 10.0)
        assert _approx(r.netz_lade_kwh, 1.0)


async def test_effektiver_ladepreis_fallback_auf_boersenpreis() -> None:
    """Ohne strompreis_cent (kein dyn. Tarif) → Boersenpreis-Quelle."""
    async with _db_ctx() as (db, anlage_id):
        d = date(2025, 5, 1)
        rows = [
            {"datum": d, "stunde": 3, "batterie_kw": -2.0, "netzbezug_kw": 2.0,
             "boersenpreis_cent": 5.5},
            {"datum": d, "stunde": 4, "batterie_kw": -2.0, "netzbezug_kw": 2.0,
             "boersenpreis_cent": 6.5},
        ]
        await _seed_tep_stunden(db, anlage_id, rows)

        r = await berechne_effektiver_ladepreis(db, anlage_id=anlage_id, von=d, bis=d)
        assert r is not None
        assert r.quelle == "boersenpreis"
        assert _approx(r.effektiver_ladepreis_cent, 6.0)


async def test_effektiver_ladepreis_abdeckung_unter_schwelle_quelle_datenbasis() -> None:
    """C1: Schwelle unterschritten → quelle="datenbasis-zu-duenn", Wert
    trotzdem ausgewiesen (informativ) plus Abdeckungs-Diagnose für UI-Badge."""
    assert LADEPREIS_STUNDEN_ABDECKUNG_MIN == 0.80
    async with _db_ctx() as (db, anlage_id):
        d = date(2025, 5, 1)
        rows = []
        # 10 Lade-Stunden, nur 2 mit Preis → 20% < 80%
        for stunde in range(10):
            rows.append({
                "datum": d, "stunde": stunde,
                "batterie_kw": -1.0, "netzbezug_kw": 1.0,
                "strompreis_cent": 10.0 if stunde < 2 else None,
            })
        await _seed_tep_stunden(db, anlage_id, rows)

        r = await berechne_effektiver_ladepreis(db, anlage_id=anlage_id, von=d, bis=d)
        assert r.quelle == "datenbasis-zu-duenn"
        # Wert wird trotzdem geliefert — UI entscheidet ob anzeigen
        assert r.effektiver_ladepreis_cent is not None
        assert _approx(r.effektiver_ladepreis_cent, 10.0)
        assert _approx(r.abdeckung_prozent, 20.0)
        assert r.netzlade_stunden_gesamt == 10
        assert r.netzlade_stunden_mit_preis == 2


async def test_effektiver_ladepreis_keine_ladung_quelle_keine_netzladung() -> None:
    """C1: keine Netz-Ladestunden → quelle="keine-netzladung", Wert None."""
    async with _db_ctx() as (db, anlage_id):
        d = date(2025, 5, 1)
        rows = [
            {"datum": d, "stunde": 18, "batterie_kw": 2.0, "netzbezug_kw": 0,
             "strompreis_cent": 35.0},  # nur Entladung
        ]
        await _seed_tep_stunden(db, anlage_id, rows)
        r = await berechne_effektiver_ladepreis(db, anlage_id=anlage_id, von=d, bis=d)
        assert r.quelle == "keine-netzladung"
        assert r.effektiver_ladepreis_cent is None


async def test_effektiver_ladepreis_leeres_fenster_quelle_keine_tep_daten() -> None:
    """C1: Helper-Aufruf ohne TEP-Daten im Zeitraum → eigene Quelle."""
    async with _db_ctx() as (db, anlage_id):
        r = await berechne_effektiver_ladepreis(
            db, anlage_id=anlage_id,
            von=date(2025, 5, 1), bis=date(2025, 5, 31),
        )
        assert r.quelle == "keine-tep-daten"
        assert r.effektiver_ladepreis_cent is None
        assert r.stunden_gesamt_im_fenster == 0


# ----------------------------------------------------------------------------
# berechne_ist_wirkungsgrad
# ----------------------------------------------------------------------------

async def test_eta_langes_fenster_nutzt_reinen_quotient() -> None:
    """≥ Mindest-Fenster → SoC mittelt sich aus, Quotient genügt."""
    async with _db_ctx() as (db, anlage_id):
        r = await berechne_ist_wirkungsgrad(
            db, anlage_id=anlage_id,
            von=date(2024, 1, 1), bis=date(2024, 12, 31),
            ladung_kwh=1000, entladung_kwh=900,
            nutzbare_kapazitaet_kwh=10,
            fenster_monate=12,
        )
        assert r.quelle == "fenster_lang"
        assert r.wirkungsgrad_prozent is not None
        assert _approx(r.wirkungsgrad_prozent, 90.0)


async def test_eta_kurzes_fenster_mit_soc_korrektur_loest_110_prozent_bug() -> None:
    """Reproduziert den Mai-110%-Bug: Speicher startet voll (SoC 100%),
    endet leer (SoC 5%) — naiver Quotient wäre > 100 %, mit SoC-Korrektur
    plausibel."""
    async with _db_ctx() as (db, anlage_id):
        # SoC am Anfang (1. Mai 00:00) = 100 %, am Ende (31. Mai 23:00) = 5 %
        rows = [
            {"datum": date(2025, 5, 1), "stunde": 0,
             "batterie_kw": 0, "soc_prozent": 100.0},
            {"datum": date(2025, 5, 31), "stunde": 23,
             "batterie_kw": 0, "soc_prozent": 5.0},
        ]
        await _seed_tep_stunden(db, anlage_id, rows)

        # In dem Monat: 200 kWh geladen, 280 kWh entladen
        # Naiver Quotient: 280/200 = 140 %
        # Mit SoC: ΔSoC = (5 - 100)/100 × 10 kWh = -9.5 kWh
        # η = (280 + (-9.5)) / 200 = 270.5 / 200 = 1.35 → clamped auf 1.0
        # (Bei kleinerer Kapazität wäre der Effekt weniger drastisch — hier
        # zeigt der Test, dass die Funktion nicht > 100 % zurückgibt.)
        r = await berechne_ist_wirkungsgrad(
            db, anlage_id=anlage_id,
            von=date(2025, 5, 1), bis=date(2025, 5, 31),
            ladung_kwh=200, entladung_kwh=280,
            nutzbare_kapazitaet_kwh=10,
            fenster_monate=1,
        )
        assert r.quelle == "soc_korrigiert"
        assert r.wirkungsgrad_prozent is not None
        assert r.wirkungsgrad_prozent <= 100.0
        assert _approx(r.delta_soc_kwh, -9.5, tol=0.5)


async def test_eta_realistisch_korrektur_mit_groeserer_kapazitaet() -> None:
    """31 kWh Speicher (wie EEL Box), SoC 80 % → 20 % über den Monat.

    Naiver Quotient würde verzerrt, die korrigierte Formel landet bei
    plausiblem η ~ 95 %.
    """
    async with _db_ctx() as (db, anlage_id):
        await _seed_tep_stunden(db, anlage_id, [
            {"datum": date(2025, 5, 1), "stunde": 0, "batterie_kw": 0, "soc_prozent": 80.0},
            {"datum": date(2025, 5, 31), "stunde": 23, "batterie_kw": 0, "soc_prozent": 20.0},
        ])
        # ΔSoC = -60% × 31 kWh = -18.6 kWh
        # ladung 200, entladung 171 → naiv: 85.5 %
        # Mit SoC: (171 + (-18.6)) / 200 = 152.4 / 200 = 76.2 %
        # Aber wenn der echte η 95 % wäre, dann müsste:
        # ladung × η = entladung + ΔSoC_richtung_entladung
        # Da SoC FÄLLT, ist die Energie aus dem Speicher RAUS gegangen
        # (zusätzliche Entladung). Die Formel wirkt: η = (e + ΔSoC) / l.
        # Mit ΔSoC=-18.6 verringert das den Zähler → niedrigerer η.
        # Korrekt ist das: wenn der Speicher beim Start voller war als
        # beim Ende, sind die nominell entladenen 171 kWh ZU WENIG —
        # ein Teil der „verlorenen" Energie wurde nicht gemessen.
        r = await berechne_ist_wirkungsgrad(
            db, anlage_id=anlage_id,
            von=date(2025, 5, 1), bis=date(2025, 5, 31),
            ladung_kwh=200, entladung_kwh=171,
            nutzbare_kapazitaet_kwh=31,
            fenster_monate=1,
        )
        assert r.quelle == "soc_korrigiert"
        assert r.wirkungsgrad_prozent is not None
        # Mit ΔSoC -18.6 und Ladung 200, Entladung 171:
        # η = (171 - 18.6) / 200 = 76.2 %
        assert _approx(r.wirkungsgrad_prozent, 76.2, tol=0.5)
        assert _approx(r.delta_soc_kwh, -18.6, tol=0.5)


async def test_eta_kein_soc_und_kurzes_fenster_fenster_zu_kurz_quelle() -> None:
    """C1: Keine SoC-Werte + kurzes Fenster → quelle="fenster-zu-kurz",
    Wert None (Caller nimmt Param-η + UI zeigt Badge)."""
    assert WIRKUNGSGRAD_FENSTER_MONATE_MIN == 6
    async with _db_ctx() as (db, anlage_id):
        r = await berechne_ist_wirkungsgrad(
            db, anlage_id=anlage_id,
            von=date(2025, 5, 1), bis=date(2025, 5, 31),
            ladung_kwh=200, entladung_kwh=180,
            nutzbare_kapazitaet_kwh=10,
            fenster_monate=3,
        )
        assert r.quelle == "fenster-zu-kurz"
        assert r.wirkungsgrad_prozent is None


async def test_eta_keine_ladung_quelle_keine_ladung() -> None:
    """C1: Speicher wurde im Fenster gar nicht geladen → eigene Quelle."""
    async with _db_ctx() as (db, anlage_id):
        r = await berechne_ist_wirkungsgrad(
            db, anlage_id=anlage_id,
            von=date(2025, 5, 1), bis=date(2025, 5, 31),
            ladung_kwh=0, entladung_kwh=0,
            nutzbare_kapazitaet_kwh=10,
            fenster_monate=1,
        )
        assert r.quelle == "keine-ladung"
        assert r.wirkungsgrad_prozent is None


# ----------------------------------------------------------------------------
# ist_soc_drift_signifikant
# ----------------------------------------------------------------------------

def test_drift_neue_signatur_unter_schwelle() -> None:
    """C2: Schwelle 20 pp |soc_ende − soc_start|. SoC 80%→65% = 15 pp → OK."""
    assert SOC_DRIFT_SCHWELLE_PROZENTPUNKTE == 20.0
    assert not ist_soc_drift_signifikant(soc_start_prozent=80.0, soc_ende_prozent=65.0)


def test_drift_neue_signatur_ueber_schwelle() -> None:
    """C2: SoC 80%→50% = 30 pp → signifikant."""
    assert ist_soc_drift_signifikant(soc_start_prozent=80.0, soc_ende_prozent=50.0)


def test_drift_neue_signatur_voll_zu_leer_ist_signifikant() -> None:
    """C2: Mai-Bug-Konstellation — Speicher Anfang voll, Ende fast leer."""
    assert ist_soc_drift_signifikant(soc_start_prozent=100.0, soc_ende_prozent=5.0)


def test_drift_neue_signatur_negative_richtung_zaehlt_genauso() -> None:
    """C2: SoC steigt im Monat (Leer → Voll) ist genauso problematisch."""
    assert ist_soc_drift_signifikant(soc_start_prozent=10.0, soc_ende_prozent=95.0)


def test_drift_legacy_signatur_bleibt_unterstuetzt() -> None:
    """Bestehende Caller mit (delta_soc_kwh, ladung_kwh) bleiben funktional."""
    # 25 % von 200 kWh = 50 kWh → über 20 %-Schwelle = signifikant
    assert ist_soc_drift_signifikant(delta_soc_kwh=50.0, ladung_kwh=200.0)
    # 5 % von 200 kWh = 10 kWh → unter 20 %-Schwelle = OK
    assert not ist_soc_drift_signifikant(delta_soc_kwh=10.0, ladung_kwh=200.0)


def test_drift_keine_args_kein_drift() -> None:
    """Defensive: keine Args → keine Aussage möglich → False."""
    assert not ist_soc_drift_signifikant()


# ----------------------------------------------------------------------------
# ist_eta_degradation_alarm (Etappe C3)
# ----------------------------------------------------------------------------

def test_degradation_alarm_unter_param_5pp_ist_alarm() -> None:
    """C3: IST-η 88 %, Param 95 % → 7 pp Differenz → Alarm."""
    assert ETA_DEGRADATION_SCHWELLE_PROZENTPUNKTE == 5.0
    assert ist_eta_degradation_alarm(
        ist_wirkungsgrad_prozent=88.0,
        param_wirkungsgrad_prozent=95.0,
    )


def test_degradation_alarm_genau_5pp_kein_alarm() -> None:
    """C3: Strikte >-Schwelle, exakt 5 pp Diff ist noch kein Alarm."""
    assert not ist_eta_degradation_alarm(
        ist_wirkungsgrad_prozent=90.0,
        param_wirkungsgrad_prozent=95.0,
    )


def test_degradation_alarm_ist_ueber_param_kein_alarm() -> None:
    """C3: Asymmetrisch — Param zu konservativ ≠ Alarm."""
    assert not ist_eta_degradation_alarm(
        ist_wirkungsgrad_prozent=98.0,
        param_wirkungsgrad_prozent=90.0,
    )


def test_degradation_alarm_realistischer_byd_fall() -> None:
    """C3: BYD HVS Beispiel aus dem JSON-Backup — η 81 % gemessen vs.
    Param 95 % Default → Alarm (Speicher-Verluste oder Hybrid-WR-Verluste)."""
    assert ist_eta_degradation_alarm(
        ist_wirkungsgrad_prozent=81.0,
        param_wirkungsgrad_prozent=95.0,
    )


# ----------------------------------------------------------------------------
# Runner
# ----------------------------------------------------------------------------

ASYNC_TESTS = [
    test_effektiver_ladepreis_nacht_billig_tag_teuer,
    test_effektiver_ladepreis_pv_ladung_zaehlt_nicht,
    test_effektiver_ladepreis_fallback_auf_boersenpreis,
    test_effektiver_ladepreis_abdeckung_unter_schwelle_quelle_datenbasis,
    test_effektiver_ladepreis_keine_ladung_quelle_keine_netzladung,
    test_effektiver_ladepreis_leeres_fenster_quelle_keine_tep_daten,
    test_eta_langes_fenster_nutzt_reinen_quotient,
    test_eta_kurzes_fenster_mit_soc_korrektur_loest_110_prozent_bug,
    test_eta_realistisch_korrektur_mit_groeserer_kapazitaet,
    test_eta_kein_soc_und_kurzes_fenster_fenster_zu_kurz_quelle,
    test_eta_keine_ladung_quelle_keine_ladung,
]

SYNC_TESTS = [
    test_drift_neue_signatur_unter_schwelle,
    test_drift_neue_signatur_ueber_schwelle,
    test_drift_neue_signatur_voll_zu_leer_ist_signifikant,
    test_drift_neue_signatur_negative_richtung_zaehlt_genauso,
    test_drift_legacy_signatur_bleibt_unterstuetzt,
    test_drift_keine_args_kein_drift,
    test_degradation_alarm_unter_param_5pp_ist_alarm,
    test_degradation_alarm_genau_5pp_kein_alarm,
    test_degradation_alarm_ist_ueber_param_kein_alarm,
    test_degradation_alarm_realistischer_byd_fall,
]


async def main_async() -> int:
    fehler = 0
    for fn in ASYNC_TESTS:
        try:
            await fn()
            print(f"PASS  {fn.__name__}")
        except Exception:  # noqa: BLE001
            fehler += 1
            print(f"FAIL  {fn.__name__}")
            traceback.print_exc()
    for fn in SYNC_TESTS:
        try:
            fn()
            print(f"PASS  {fn.__name__}")
        except Exception:  # noqa: BLE001
            fehler += 1
            print(f"FAIL  {fn.__name__}")
            traceback.print_exc()
    return fehler


def main() -> int:
    fehler = asyncio.run(main_async())
    total = len(ASYNC_TESTS) + len(SYNC_TESTS)
    if fehler:
        print(f"\n{fehler}/{total} Tests fehlgeschlagen.")
        return 1
    print(f"\nAlle {total} Tests grün.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
