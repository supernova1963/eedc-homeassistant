"""Tests #150 Slice A — eedc-PV-Prognose-Export nach HA.

Rest-Ertrag heute + Tagesprognose Tag+1/2/3 + „Speicher voll um" (SoC-Sim ab
aktuellem Speicherstand). Reine Sim-Logik isoliert, Verdrahtung mit gemockten
Wetter-Quellen.
"""

from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from backend.core.berechnungen.speicher_simulation import simuliere_speicher_tag
from backend.models import Anlage, Investition, Monatsdaten


# ── Speicher-Simulation (rein) ──────────────────────────────────────────────

def test_speicher_voll_um_aus_aktuellem_soc():
    # 10 kWh Speicher, Start 50 % (=5 kWh), 1 kWh Überschuss/h ab 10 Uhr.
    pv = [0.0] * 24
    for h in range(10, 16):
        pv[h] = 1.0
    sim = simuliere_speicher_tag(pv, [0.0] * 24, speicher_kap_kwh=10.0,
                                 start_soc_prozent=50.0, start_stunde=10)
    # 5 kWh fehlen bis voll → nach 5 h (Stunden 10..14) bei 100 % → "14:00".
    assert sim.speicher_voll_um == "14:00"
    assert sim.end_soc_prozent == pytest.approx(100.0)


def test_speicher_ohne_kapazitaet_keine_sim():
    sim = simuliere_speicher_tag([1.0] * 24, [0.0] * 24, speicher_kap_kwh=0.0,
                                 start_soc_prozent=50.0)
    assert sim.speicher_voll_um is None
    assert sim.soc_pro_stunde == {}


def test_speicher_start_stunde_ueberspringt_vergangenheit():
    # Überschuss am Vormittag wird ignoriert, wenn erst ab 14 Uhr simuliert wird.
    pv = [5.0] * 12 + [0.0] * 12
    sim = simuliere_speicher_tag(pv, [0.0] * 24, speicher_kap_kwh=10.0,
                                 start_soc_prozent=50.0, start_stunde=14)
    assert sim.speicher_voll_um is None
    assert min(sim.soc_pro_stunde) == 14


# ── Verdrahtung: calculate_anlage_sensors mit gemockten Quellen ─────────────

def _fake_solar_prognose(tageswerte):
    # Σ stunden_kw == pv_ertrag_kwh (gleiche Invariante wie der echte
    # solar_forecast_service: Tagessumme = Σ Stunden-Erträge).
    heute = date.today()
    tage = [
        SimpleNamespace(
            datum=(heute + timedelta(days=i)).isoformat(),
            pv_ertrag_kwh=val,
            stunden_kw=[val / 10 if 8 <= h < 18 else 0.0 for h in range(24)],
        )
        for i, val in enumerate(tageswerte)
    ]
    return SimpleNamespace(tageswerte=tage)


@pytest.fixture
def _patch_prognose(monkeypatch):
    import backend.services.solar_forecast_service as sfs
    import backend.api.routes.live_wetter as lw
    from backend.services.korrekturprofil_lookup import _cache

    async def fake_get_solar_prognose(**kwargs):
        return _fake_solar_prognose([20.0, 18.0, 15.0, 12.0])  # heute, +1, +2, +3

    async def fake_lernfaktor(anlage_id, db, quelle="openmeteo"):
        return 0.9

    monkeypatch.setattr(sfs, "get_solar_prognose", fake_get_solar_prognose)
    monkeypatch.setattr(lw, "_get_lernfaktor", fake_lernfaktor)
    # Kaskaden-Profil-Cache ist prozessweit (anlage_id-keyed) — Leaks aus
    # anderen Tests vermeiden; ohne Profile fällt jede Stunde auf den Skalar.
    _cache.clear()


async def _seed_pv_anlage(db, prognose_quelle="eedc") -> Anlage:
    anlage = Anlage(
        anlagenname="Prognose-Test",
        leistung_kwp=10.0,
        latitude=48.8,
        longitude=9.2,
        standort_land="DE",
        prognose_quelle=prognose_quelle,
    )
    db.add(anlage)
    await db.flush()
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2025, monat=1,
                       netzbezug_kwh=100.0, einspeisung_kwh=200.0))
    db.add(Investition(anlage_id=anlage.id, typ="pv-module", bezeichnung="Dach",
                       leistung_kwp=10.0, anschaffungsdatum=date(2024, 1, 1)))
    await db.flush()
    return anlage


async def test_prognose_sensoren_erscheinen(db, _patch_prognose):
    from backend.api.routes.ha_export import calculate_anlage_sensors

    anlage = await _seed_pv_anlage(db)
    sensors = await calculate_anlage_sensors(db, anlage)
    by_key = {sv.definition.key: sv for sv in sensors}

    # Tagesprognosen = Σ korrigierte Stunden-Slots; ohne Kaskaden-Profil
    # greift der Skalar-Fallback 0.9 → wie bisher pv_ertrag × 0.9
    # (Regressions-Erwartung: Anlagen OHNE Profil verhalten sich unverändert).
    assert by_key["eedc_prognose_day_plus_1_kwh"].value == pytest.approx(18.0 * 0.9, abs=0.05)
    assert by_key["eedc_prognose_day_plus_2_kwh"].value == pytest.approx(15.0 * 0.9, abs=0.05)
    assert by_key["eedc_prognose_day_plus_3_kwh"].value == pytest.approx(12.0 * 0.9, abs=0.05)
    assert "eedc_prognose_heute_kwh" in by_key
    assert "eedc_prognose_rest_today_kwh" in by_key
    # Rest ⊆ Tageswert: heute = IST bisher + Rest (Rainer-PN 2026-06-11).
    assert by_key["eedc_prognose_rest_today_kwh"].value <= by_key["eedc_prognose_heute_kwh"].value
    # Stundenprofile reisen als Attribut mit (kein eigenes Topic) — heute UND
    # Tag+1/2/3 (Geparkt-Trigger Kaskaden-Umzug, Gernot-Entscheid 2026-06-11).
    assert len(by_key["eedc_prognose_heute_kwh"].zusatz_attribute["stundenprofil_kwh"]) == 24
    for day_key in ("eedc_prognose_day_plus_1_kwh",
                    "eedc_prognose_day_plus_2_kwh",
                    "eedc_prognose_day_plus_3_kwh"):
        profil = by_key[day_key].zusatz_attribute["stundenprofil_kwh"]
        assert len(profil) == 24
        # Pflicht-Invariante: Sensor-State == Σ exportierte Stundenwerte.
        assert by_key[day_key].value == pytest.approx(sum(profil), abs=0.051)


async def test_rest_heute_ist_echter_rest(db, _patch_prognose, monkeypatch):
    """„Rest heute" = NUR Σ verbleibende Stunden (ohne IST) — der alte Sensor
    enthielt das IST und war damit faktisch der Tageswert unter irreführendem
    Namen (Rainer-PN 2026-06-11)."""
    from datetime import datetime as real_datetime, time as dt_time
    import backend.services.ha_export_prognose as hep
    from backend.api.routes.ha_export import calculate_anlage_sensors

    class _FixedNoon(real_datetime):
        @classmethod
        def now(cls, tz=None):
            return real_datetime.combine(date.today(), dt_time(12, 0), tzinfo=tz)

    monkeypatch.setattr(hep, "datetime", _FixedNoon)

    anlage = await _seed_pv_anlage(db)
    sensors = await calculate_anlage_sensors(db, anlage)
    by_key = {sv.definition.key: sv for sv in sensors}

    # Profil heute: 2.0 kWh in Stunden 8–17 (Tageswert 20), Skalar 0.9. Um
    # 12:00 sind die Rest-Slots 13..17 → 5 × 2.0 × 0.9 = 9.0 kWh. Kein
    # IST-Profil geseedet → Tageswert == Rest.
    assert by_key["eedc_prognose_rest_today_kwh"].value == pytest.approx(9.0, abs=0.05)
    assert by_key["eedc_prognose_heute_kwh"].value == pytest.approx(9.0, abs=0.05)


async def test_quellen_regel_nur_eedc_kein_solcast_sfml(db, _patch_prognose):
    """Auch bei gewählter Solcast-Quelle exportiert eedc NUR eigene Prognose-Werte."""
    from backend.api.routes.ha_export import calculate_anlage_sensors

    anlage = await _seed_pv_anlage(db, prognose_quelle="solcast")
    sensors = await calculate_anlage_sensors(db, anlage)
    keys = {sv.definition.key for sv in sensors}

    assert any(k.startswith("eedc_prognose_") for k in keys)
    assert not any("solcast" in k or "sfml" in k for k in keys)
