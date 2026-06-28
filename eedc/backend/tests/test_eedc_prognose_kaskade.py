"""Tests — Korrekturprofil-Kaskade im Export-/Day+1–3-Pfad (#150-Folge).

Deckt ab:
  - Layer-Helper ``korrigiere_tagesprofil``: Pflicht-Invariante
    Tageswert == Σ exportierte Stunden-Slots, Fallback-Semantik.
  - Kaskaden-Mock: Stunden-Faktoren ≠ Skalar → Tageswert folgt den
    Stunden-Faktoren (nicht dem Skalar).
  - Symmetrie HA-Export ↔ ``berechne_eedc_prognose`` (gleiche Quelle wie die
    „eedc"-Spalte im Prognosen-Vergleich) — [[feedback_aggregator_symmetrie]].
  - Regression: ohne Kaskaden-Profil UND ohne Legacy-Skalar ändert sich
    nichts (Faktor 1.0); OpenMeteo-Schätzpfad ohne Stunden-Basis fällt auf
    Tages-Ertrag × Skalar zurück (kein Profil-Attribut).
  - ``klassifiziere_stunde`` klassifiziert sauber mit ``wetter_code=None``
    (alte Cache-Einträge ohne stündlichen weather_code, Versions-Skew).
"""

from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from backend.core.berechnungen.prognose_korrektur import korrigiere_tagesprofil
from backend.models import Anlage, Investition, Monatsdaten
from backend.services.wetter.utils import klassifiziere_stunde


# ── Layer-Helper (rein) ──────────────────────────────────────────────────────

def test_korrigiere_tagesprofil_invariante_tageswert_ist_summe():
    roh = [0.0] * 8 + [1.234, 2.345, 3.456, 2.111] + [0.0] * 12
    faktoren = [None] * 8 + [0.8, 1.1, 0.95, 1.05] + [None] * 12
    p = korrigiere_tagesprofil(roh, faktoren, fallback_faktor=0.9)
    assert p.tageswert_kwh == pytest.approx(sum(p.stundenprofil_export_kwh), abs=0.051)
    assert len(p.stunden_kwh) == 24
    assert len(p.stundenprofil_export_kwh) == 24


def test_korrigiere_tagesprofil_fallback_kette():
    roh = [1.0] * 24
    # Stunde 0: Kaskaden-Faktor 0.5; Rest: Miss → Fallback 0.8.
    faktoren = [0.5] + [None] * 23
    p = korrigiere_tagesprofil(roh, faktoren, fallback_faktor=0.8)
    assert p.stunden_kwh[0] == pytest.approx(0.5)
    assert p.stunden_kwh[1] == pytest.approx(0.8)
    # Ohne jeden Faktor (frische Anlage): 1.0 — heutiges Verhalten.
    p2 = korrigiere_tagesprofil(roh, [None] * 24, fallback_faktor=None)
    assert p2.stunden_kwh[5] == pytest.approx(1.0)
    assert p2.tageswert_kwh == pytest.approx(24.0)


def test_korrigiere_tagesprofil_robust_gegen_kurze_listen_und_none():
    p = korrigiere_tagesprofil([None, 1.0, 2.0], [0.5], fallback_faktor=2.0)
    assert p.stunden_kwh[0] == 0.0          # None-Slot → 0
    assert p.stunden_kwh[1] == pytest.approx(2.0)   # Faktor-Liste zu kurz → Fallback
    assert p.stunden_kwh[3] == 0.0          # Roh-Liste zu kurz → 0


# ── klassifiziere_stunde ohne stündlichen weather_code ───────────────────────

def test_klassifiziere_stunde_ohne_code():
    assert klassifiziere_stunde(10, 0.0, None) == "klar"
    assert klassifiziere_stunde(90, 0.0, None) == "diffus"
    assert klassifiziere_stunde(50, 2.0, None) == "wechselhaft"
    assert klassifiziere_stunde(None, None, None) is None


# ── Verdrahtung mit gemockten Quellen ────────────────────────────────────────

def _fake_solar_prognose(tageswerte):
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
def _patch_quellen(monkeypatch):
    import backend.services.solar_forecast_service as sfs
    import backend.api.routes.live_wetter as lw
    from backend.services.korrekturprofil_lookup import _cache

    async def fake_get_solar_prognose(**kwargs):
        return _fake_solar_prognose([20.0, 18.0, 15.0, 12.0])

    async def fake_lernfaktor(anlage_id, db, quelle="openmeteo"):
        return 0.9

    monkeypatch.setattr(sfs, "get_solar_prognose", fake_get_solar_prognose)
    monkeypatch.setattr(lw, "_get_lernfaktor", fake_lernfaktor)
    _cache.clear()


async def _seed_pv_anlage(db) -> Anlage:
    anlage = Anlage(
        anlagenname="Kaskade-Test",
        leistung_kwp=10.0,
        latitude=48.8,
        longitude=9.2,
        standort_land="DE",
        prognose_quelle="eedc",
    )
    db.add(anlage)
    await db.flush()
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2025, monat=1,
                       netzbezug_kwh=100.0, einspeisung_kwh=200.0))
    db.add(Investition(anlage_id=anlage.id, typ="pv-module", bezeichnung="Dach",
                       leistung_kwp=10.0, anschaffungsdatum=date(2024, 1, 1)))
    await db.flush()
    return anlage


async def test_kaskaden_faktoren_uebersteuern_skalar(db, _patch_quellen, monkeypatch):
    """Stunden-Faktoren ≠ Skalar → Tageswert folgt den Stunden-Faktoren."""
    import backend.services.eedc_prognose_service as eps
    import backend.services.prognose_kanon as kanon

    async def fake_faktoren(db_, **kwargs):
        # Vormittag (8–12) dämpfen, Nachmittag (13–17) Kaskaden-Miss → Skalar.
        return [0.5 if 8 <= h <= 12 else None for h in range(24)]

    # Die Korrektur-Mathematik liegt seit dem Prognose-Kanon im Kanon-Service.
    monkeypatch.setattr(kanon, "korrekturfaktoren_fuer_tag", fake_faktoren)

    anlage = await _seed_pv_anlage(db)
    prog = await eps.berechne_eedc_prognose(db, anlage, days=4)

    # Tag+1: roh 1.8 kWh/Slot in 8–17. Stunden 8–12: ×0.5 (5×0.9=4.5),
    # Stunden 13–17: ×0.9 Skalar (5×1.62=8.1) → 12.6 ≠ 18×0.9=16.2.
    tag1 = prog.tage[1]
    assert tag1.tageswert_kwh == pytest.approx(12.6, abs=0.06)
    assert tag1.tageswert_kwh != pytest.approx(18.0 * 0.9, abs=0.5)
    # Invariante gilt auch mit gemischten Faktoren.
    assert tag1.tageswert_kwh == pytest.approx(
        sum(tag1.profil.stundenprofil_export_kwh), abs=0.051
    )


async def test_symmetrie_export_gleich_eedc_prognose(db, _patch_quellen):
    """HA-Export-Sensoren und gemeinsamer eedc-Prognose-Pfad (= Quelle der
    Vergleichs-Spalte „eedc") zeigen denselben Tageswert."""
    from backend.api.routes.ha_export import calculate_anlage_sensors
    from backend.services.eedc_prognose_service import berechne_eedc_prognose

    anlage = await _seed_pv_anlage(db)
    sensors = await calculate_anlage_sensors(db, anlage)
    by_key = {sv.definition.key: sv for sv in sensors}
    prog = await berechne_eedc_prognose(db, anlage, days=4)

    for offset, key in ((1, "eedc_prognose_day_plus_1_kwh"),
                        (2, "eedc_prognose_day_plus_2_kwh"),
                        (3, "eedc_prognose_day_plus_3_kwh")):
        assert by_key[key].value == pytest.approx(prog.tage[offset].tageswert_kwh)
        assert by_key[key].zusatz_attribute["stundenprofil_kwh"] == list(
            prog.tage[offset].profil.stundenprofil_export_kwh
        )


async def test_schaetzpfad_ohne_stundenbasis_faellt_auf_skalar(db, _patch_quellen, monkeypatch):
    """OpenMeteo-Schätzpfad (Tagessumme ohne Hourly-Daten): Tageswert =
    Tages-Ertrag × Skalar, KEIN Stundenprofil-Attribut."""
    import backend.services.solar_forecast_service as sfs
    from backend.api.routes.ha_export import calculate_anlage_sensors

    async def fake_ohne_stunden(**kwargs):
        prognose = _fake_solar_prognose([20.0, 18.0, 15.0, 12.0])
        for tag in prognose.tageswerte:
            tag.stunden_kw = [0.0] * 24
        return prognose

    monkeypatch.setattr(sfs, "get_solar_prognose", fake_ohne_stunden)

    anlage = await _seed_pv_anlage(db)
    sensors = await calculate_anlage_sensors(db, anlage)
    by_key = {sv.definition.key: sv for sv in sensors}

    assert by_key["eedc_prognose_day_plus_1_kwh"].value == pytest.approx(18.0 * 0.9, abs=0.05)
    assert "stundenprofil_kwh" not in by_key["eedc_prognose_day_plus_1_kwh"].zusatz_attribute


async def test_ohne_profile_und_ohne_skalar_faktor_eins(db, _patch_quellen, monkeypatch):
    """Frische Anlage: weder Kaskaden-Profil noch Legacy-Skalar → Faktor 1.0
    (heutiges Verhalten, Regressionstest Verhaltens-Erwartung)."""
    import backend.api.routes.live_wetter as lw
    from backend.services.eedc_prognose_service import berechne_eedc_prognose

    async def kein_lernfaktor(anlage_id, db_, quelle="openmeteo"):
        return None

    monkeypatch.setattr(lw, "_get_lernfaktor", kein_lernfaktor)

    anlage = await _seed_pv_anlage(db)
    prog = await berechne_eedc_prognose(db, anlage, days=4)
    assert prog.tage[1].tageswert_kwh == pytest.approx(18.0, abs=0.05)
