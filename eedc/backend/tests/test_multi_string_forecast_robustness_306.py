"""Regressionstests #306: Multi-String/BKW-Tagesprognose kollabiert bei
transienten OpenMeteo-Aussetzern auf einen Solo-String/BKW-Wert.

Ursache: Beide Multi-String-Fan-out-Pfade verschluckten eine gescheiterte
Orientierungsgruppe still und verteilten ihr kWp-Gewicht NICHT um — die
verbleibende Summe entspricht dann nur der Absolut-Produktion der Überlebenden.
Der Prefetch-Job fror diesen kollabierten Wert als Tagesprognose ein und
verzerrte Genauigkeits-Tracking + Lernfaktor.

Fix: beide Pfade melden Unvollständigkeit; der Persist-Pfad friert einen
unvollständigen Tag nicht als OpenMeteo-Wert ein (Solcast bleibt unberührt).
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date

import pytest
from sqlalchemy import select

from backend.api.routes import live_wetter
from backend.services import prefetch_service
from backend.services.wetter.cache import _cache_get
from backend.models.tages_energie_profil import TagesZusammenfassung
from backend.services import solar_forecast_service as sfs
from backend.services.solar_forecast_service import (
    PVStringConfig,
    SolarPrognoseResponse,
    SolarPrognoseTag,
    get_multi_string_prognose,
)

HEUTE = date.today().isoformat()


def _fake_response(kwp: float, tages_kwh: float) -> SolarPrognoseResponse:
    """Minimale SolarPrognoseResponse mit einem Tageswert für heute."""
    tag = SolarPrognoseTag(
        datum=HEUTE, pv_ertrag_kwh=tages_kwh, gti_kwh_m2=5.0, ghi_kwh_m2=4.0,
        sonnenstunden=8.0, temperatur_max_c=20.0, temperatur_min_c=10.0,
        bewoelkung_prozent=20, niederschlag_mm=0.0, schnee_cm=0.0,
    )
    return SolarPrognoseResponse(
        anlage_id=None, kwp_gesamt=kwp, neigung=30, ausrichtung=0,
        system_losses_prozent=14.0, prognose_zeitraum={},
        summe_kwh=tages_kwh, durchschnitt_kwh_tag=tages_kwh,
        tageswerte=[tag], string_prognosen=None,
        datenquelle="best_match", abgerufen_am="2026-05-29T00:00:00",
    )


# ── get_multi_string_prognose (Freeze-Pfad via Prefetch) ────────────────────

async def test_multi_string_alle_gruppen_ok_ist_vollstaendig(monkeypatch):
    strings = [PVStringConfig("Dach Süd", 5.0, 30, 0), PVStringConfig("BKW", 0.8, 60, 0)]

    async def fake_gsp(**kw):
        return _fake_response(kw["kwp"], kw["kwp"] * 4.0)

    monkeypatch.setattr(sfs, "get_solar_prognose", fake_gsp)
    res = await get_multi_string_prognose(50.0, 8.0, strings, days=7)

    assert res is not None
    assert res["vollstaendig"] is True
    assert len(res["string_prognosen"]) == 2


async def test_multi_string_eine_gruppe_faellt_aus_ist_unvollstaendig(monkeypatch):
    """Fällt die kleine BKW-Gruppe aus, überlebt nur der große Dachstring —
    summe_kwh kollabiert, und genau das muss das Flag anzeigen."""
    strings = [PVStringConfig("Dach Süd", 5.0, 30, 0), PVStringConfig("BKW", 0.8, 60, 0)]

    async def fake_gsp(**kw):
        if kw["kwp"] < 1.0:   # BKW-Call schlägt transient fehl
            return None
        return _fake_response(kw["kwp"], kw["kwp"] * 4.0)

    monkeypatch.setattr(sfs, "get_solar_prognose", fake_gsp)
    res = await get_multi_string_prognose(50.0, 8.0, strings, days=7)

    assert res is not None                       # ein Survivor → dict
    assert res["vollstaendig"] is False          # aber als unvollständig markiert
    assert len(res["string_prognosen"]) == 1


# ── _fetch_multi_string_gti (Live-Endpoint-Pfad) ────────────────────────────

async def test_fetch_multi_string_gti_alle_gruppen_ok(monkeypatch):
    gruppen = [
        {"kwp": 5.0, "neigung": 30, "ausrichtung": 0},
        {"kwp": 5.0, "neigung": 30, "ausrichtung": 90},
    ]

    async def fake_grp(client, lat, lon, neigung, ausrichtung):
        return [800.0] * 24

    monkeypatch.setattr(live_wetter, "_fetch_gti_for_gruppe", fake_grp)
    kombiniert, vollstaendig = await live_wetter._fetch_multi_string_gti(50.0, 8.0, gruppen)

    assert vollstaendig is True
    assert len(kombiniert) == 24
    assert kombiniert[12] == pytest.approx(800.0)  # gleichgewichtetes Mittel


async def test_fetch_multi_string_gti_eine_gruppe_none_ist_unvollstaendig(monkeypatch):
    gruppen = [
        {"kwp": 5.0, "neigung": 30, "ausrichtung": 0},
        {"kwp": 0.8, "neigung": 60, "ausrichtung": 0},   # BKW
    ]

    async def fake_grp(client, lat, lon, neigung, ausrichtung):
        return None if neigung == 60 else [800.0] * 24   # BKW-Call fällt aus

    monkeypatch.setattr(live_wetter, "_fetch_gti_for_gruppe", fake_grp)
    kombiniert, vollstaendig = await live_wetter._fetch_multi_string_gti(50.0, 8.0, gruppen)

    assert vollstaendig is False
    # untergewichtet: nur die 5.0-kWp-Gruppe (Gewicht 5.0/5.8) trägt bei
    assert kombiniert[12] == pytest.approx(800.0 * (5.0 / 5.8))


# ── _speichere_prognose: None-Guard (provenance-naher Persist) ──────────────

async def test_speichere_prognose_none_laesst_bestandswert_stehen(db, monkeypatch):
    """Wird der OpenMeteo-Wert wegen unvollständigem Fan-out als None übergeben,
    darf ein bereits gespeicherter pv_prognose_kwh NICHT überschrieben werden;
    Solcast wird trotzdem persistiert."""
    from backend.core import database

    @asynccontextmanager
    async def fake_session():
        yield db   # Test-Session statt Prod-Session; Fixture schließt sie

    monkeypatch.setattr(database, "get_session", fake_session)

    # 1) Vollständiger Lauf: OpenMeteo-Tageswert wird eingefroren
    await live_wetter._speichere_prognose(anlage_id=1, datum=date.today(), prognose_kwh=42.0)

    # 2) Unvollständiger Lauf: OpenMeteo None, aber Solcast vorhanden
    await live_wetter._speichere_prognose(
        anlage_id=1, datum=date.today(), prognose_kwh=None, solcast_kwh=50.0,
    )

    row = (
        await db.execute(
            select(TagesZusammenfassung).where(
                TagesZusammenfassung.anlage_id == 1,
                TagesZusammenfassung.datum == date.today(),
            )
        )
    ).scalar_one()

    assert row.pv_prognose_kwh == 42.0      # Bestandswert unangetastet
    assert row.solcast_prognose_kwh == 50.0  # Solcast trotzdem geschrieben


# ── Prefetch ↔ Endpoint: Cache-Tupel-Arität (3er-Vertrag) ───────────────────
# Regression: Prefetch schrieb ein 2er-Tupel (data, None) in denselben
# live_wetter:-Cache-Key, den der Endpoint mit `data, multi_gti,
# multi_vollstaendig = cached` (3er) entpackt → ValueError „expected 3, got 2",
# Live-Seite zeigt „Keine Wetterdaten verfügbar". Beide müssen 3 Werte führen.


class _FakeResp:
    def raise_for_status(self):
        return None

    def json(self):
        return {"hourly": {"time": []}}


class _FakeClient:
    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, *a, **k):
        return _FakeResp()


# A20/N56: Der Cache-Key kommt aus dem Endpoint-Modul, nicht aus einer
# Format-String-Kopie im Test — sonst prüft der Test eine dritte Wahrheit.
_EINE_GRUPPE = [{"neigung": 30, "ausrichtung": 0, "kwp": 10.0}]
_ZWEI_GRUPPEN = [
    {"neigung": 30, "ausrichtung": -90, "kwp": 5.0},
    {"neigung": 30, "ausrichtung": 90, "kwp": 5.0},
]


async def test_prefetch_cache_ist_3er_tupel_single_vollstaendig(monkeypatch):
    from backend.api.routes.live_wetter import live_wetter_cache_key

    monkeypatch.setattr(prefetch_service.httpx, "AsyncClient", _FakeClient)

    await prefetch_service._prefetch_live_wetter(
        50.0, 8.0, _EINE_GRUPPE, wetter_modell="auto",
    )

    cached = _cache_get(live_wetter_cache_key(50.0, 8.0, _EINE_GRUPPE, "auto"))
    assert cached is not None
    # 3er-Unpack wie im Endpoint (live_wetter.py:1011) darf NICHT mehr crashen
    data, multi_gti, multi_vollstaendig = cached
    assert multi_gti is None
    assert multi_vollstaendig is True   # Single-String: kein Fan-out, vollständig


async def test_prefetch_cache_3er_tupel_multi_markiert_unvollstaendig(monkeypatch):
    from backend.api.routes.live_wetter import live_wetter_cache_key

    monkeypatch.setattr(prefetch_service.httpx, "AsyncClient", _FakeClient)

    await prefetch_service._prefetch_live_wetter(
        51.0, 9.0, _ZWEI_GRUPPEN, wetter_modell="auto",
    )

    cached = _cache_get(live_wetter_cache_key(51.0, 9.0, _ZWEI_GRUPPEN, "auto"))
    assert cached is not None
    data, multi_gti, multi_vollstaendig = cached
    # Prefetch macht keinen Multi-String-Fan-out → als unvollständig markiert,
    # damit kein kollabierter Tageswert in den Lernfaktor einfriert (#306)
    assert multi_vollstaendig is False
