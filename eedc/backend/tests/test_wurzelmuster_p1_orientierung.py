"""Regressionstest P1 — ein Anlagen-Kennwert nie aus EINER Investition (A20/Paket C).

Regel (Befund-Sweep `docs/drafts/archive/BEFUND-SWEEP-WURZELMUSTER.md` §2): ein
Anlagen-Kennwert darf nie aus einer einzelnen Investition abgeleitet werden —
außer der Aufrufer hat vorher **bewiesen**, dass alle Investitionen in diesem
Kennwert übereinstimmen (Guard im Code, nicht im Kommentar).

Ein Grep-Wächter ist für dieses Muster nicht möglich (§8): `strings[0]` ist im
geguardeten Fall (`len(unique_orientations) == 1`) genau die richtige Form, und
der Guard steht in einer anderen Zeile. Deshalb dieser Regressionstest: eine
**Multi-Orientierungs-Anlage durch alle Prognose-Pfade**, mit der Assertion,
dass jeder Pfad mehr als eine Orientierung sieht.

**Warum ausgeglichenes Ost/West und nicht die Demo-Anlage.** Bei Süd-Dominanz
heben sich Orientierungsfehler in der Tagessumme weitgehend auf — die
Demo-Anlage zeigte in A11 nur +1,5 % Abweichung, während dieselbe Rechnung an
einer ausgeglichenen Ost/West-Anlage −8,0 % danebenlag. Ein Kollaps auf die
zufällig erste Investition ist dort sofort sichtbar: 5 kWp Ost + 5 kWp West
ergeben mit „alles Ost" 30 % zu wenig, mit „alles West" 30 % zu viel.
"""

from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from backend.models import Anlage, Investition, TagesEnergieProfil

# Ost liefert 70 % der West-Energie — der Unterschied, an dem ein
# Orientierungs-Kollaps in der Tagessumme sichtbar wird.
_OST_FAKTOR = 0.7
_TAGESFAKTOR = 2.0  # kWh pro kWp und Tag (flach, damit die Rechnung im Kopf geht)


def _slots(kwp: float, ausrichtung: int) -> list[float]:
    """24 kWh-Slots; Tagessumme = kwp × Tagesfaktor (× 0,7 im Osten)."""
    faktor = _OST_FAKTOR if ausrichtung < 0 else 1.0
    roh = [1.0 if 8 <= h <= 17 else 0.0 for h in range(24)]
    s = sum(roh)
    return [kwp * _TAGESFAKTOR * faktor * r / s for r in roh]


def _fake_prognose(kwp: float, ausrichtung: int, days: int | None = None):
    heute = date.today()
    tage = []
    for i in range(days or 4):
        slots = _slots(kwp, ausrichtung)
        tage.append(SimpleNamespace(
            datum=(heute + timedelta(days=i)).isoformat(),
            pv_ertrag_kwh=round(sum(slots), 3),
            stunden_kw=slots,
            stunden_bewoelkung=[0.0] * 24,
            stunden_niederschlag=[0.0] * 24,
            stunden_wetter_code=[0] * 24,
            gti_kwh_m2=round(sum(slots) / max(kwp, 0.001), 3),
            ghi_kwh_m2=0.0,
            sonnenstunden=8.0,
            temperatur_max_c=22.0,
            temperatur_min_c=12.0,
            bewoelkung_prozent=10,
            niederschlag_mm=0.0,
            schnee_cm=0.0,
            wetter_symbol="sunny",
            pv_ertrag_morgens_kwh=round(sum(slots[:13]), 3),
            pv_ertrag_nachmittags_kwh=round(sum(slots[13:]), 3),
            datenquelle="best_match",
        ))
    summe = sum(t.pv_ertrag_kwh for t in tage)
    return SimpleNamespace(
        tageswerte=tage, kwp_gesamt=kwp, neigung=30, ausrichtung=ausrichtung,
        system_losses_prozent=14.0,
        prognose_zeitraum={"von": tage[0].datum, "bis": tage[-1].datum},
        summe_kwh=round(summe, 1), durchschnitt_kwh_tag=round(summe / len(tage), 2),
        datenquelle="Best Match", abgerufen_am="2026-07-26T06:00:00",
    )


# Erwartungswerte für 5 kWp Ost + 5 kWp West, ein Tag:
FAN_OUT_KWH = 5 * _TAGESFAKTOR * _OST_FAKTOR + 5 * _TAGESFAKTOR  # 17.0 — richtig
KOLLAPS_OST_KWH = 10 * _TAGESFAKTOR * _OST_FAKTOR                # 14.0 — „alles Ost"
KOLLAPS_WEST_KWH = 10 * _TAGESFAKTOR                             # 20.0 — „alles West"


@pytest.fixture
def _abrufe(monkeypatch):
    """Patcht OpenMeteo; sammelt jeden Abruf als ``(kwp, ausrichtung)``."""
    import backend.services.solar_forecast_service as sfs
    import backend.api.routes.live_wetter as lw
    from backend.services.korrekturprofil_lookup import _cache

    calls: list[tuple[float, int]] = []

    async def fake_get_solar_prognose(**kwargs):
        calls.append((kwargs["kwp"], kwargs["ausrichtung"]))
        return _fake_prognose(kwargs["kwp"], kwargs["ausrichtung"], kwargs.get("days"))

    async def kein_lernfaktor(anlage_id, db, quelle="openmeteo"):
        return None

    monkeypatch.setattr(sfs, "get_solar_prognose", fake_get_solar_prognose)
    monkeypatch.setattr(lw, "_get_lernfaktor", kein_lernfaktor)
    _cache.clear()
    return calls


async def _seed_ost_west(db) -> Anlage:
    """Ausgeglichene Ost/West-Anlage: 5 kWp Ost (−90°) + 5 kWp West (+90°), 30°."""
    anlage = Anlage(
        anlagenname="Ost/West", leistung_kwp=10.0,
        latitude=48.8, longitude=9.2, standort_land="DE", prognose_quelle="eedc",
    )
    db.add(anlage)
    await db.flush()
    for kwp, azi, name in ((5.0, -90, "Ostdach"), (5.0, 90, "Westdach")):
        db.add(Investition(
            anlage_id=anlage.id, typ="pv-module", bezeichnung=name,
            leistung_kwp=kwp, neigung_grad=30,
            anschaffungsdatum=date(2024, 1, 1),
            parameter={"ausrichtung_grad": azi},
        ))
    await db.flush()
    return anlage


async def _seed_verbrauchsprofil(db, anlage_id: int, tage: int = 6) -> None:
    """``/tagesprognose`` antwortet ohne ≥3 vollständige Tage mit 422."""
    heute = date.today()
    for d in range(1, tage + 1):
        for stunde in range(24):
            db.add(TagesEnergieProfil(
                anlage_id=anlage_id, datum=heute - timedelta(days=d),
                stunde=stunde, verbrauch_kw=0.4,
            ))
    await db.flush()


# ── Pfad 1: /tagesprognose, Kanon-Weg ───────────────────────────────────────

async def test_tagesprognose_kanon_faechert_auf(db, _abrufe):
    """Der kanonische Weg (Multi-String-Fan-out) sieht beide Dachflächen."""
    from backend.api.routes.energie_profil.views import get_tagesprognose

    anlage = await _seed_ost_west(db)
    await _seed_verbrauchsprofil(db, anlage.id)
    resp = await get_tagesprognose(anlage.id, datum=date.today() + timedelta(days=1), db=db)

    assert {a for _, a in _abrufe} == {-90, 90}
    assert resp.pv_summe_kwh == pytest.approx(FAN_OUT_KWH, abs=0.1)


# ── Pfad 2: /tagesprognose, Fallback-Weg (N51) ──────────────────────────────

async def test_tagesprognose_fallback_faechert_auf(db, _abrufe, monkeypatch):
    """N51: der Fallback-Pfad (Kanon ohne Ergebnis) holte OpenMeteo mit EINEM
    Abruf über die Gesamt-kWp und der Orientierung von ``aktive_invs[0]`` —
    Query ohne ``ORDER BY``, die Zeile war also die zufällig erste. An dieser
    Anlage sind das 14,0 statt 17,0 kWh (−17,6 %); je nach DB-Reihenfolge auch
    20,0 kWh (+17,6 %). Der Pfad fächert jetzt wie der Kanon auf."""
    import backend.api.routes.energie_profil.views as views
    from backend.api.routes.energie_profil.views import get_tagesprognose

    async def kein_kanon(*args, **kwargs):
        return None

    monkeypatch.setattr(views, "_pv_stunden_aus_kanon", kein_kanon)

    anlage = await _seed_ost_west(db)
    await _seed_verbrauchsprofil(db, anlage.id)
    resp = await get_tagesprognose(anlage.id, datum=date.today() + timedelta(days=1), db=db)

    assert {a for _, a in _abrufe} == {-90, 90}
    assert resp.pv_summe_kwh == pytest.approx(FAN_OUT_KWH, abs=0.1)
    assert abs(resp.pv_summe_kwh - KOLLAPS_OST_KWH) > 1.0
    assert abs(resp.pv_summe_kwh - KOLLAPS_WEST_KWH) > 1.0


async def test_tagesprognose_fallback_meldet_teilsumme(db, _abrufe, monkeypatch):
    """P4 im Fallback: fällt eine Orientierungsgruppe aus, ist der Tagesverlauf
    eine Teilsumme — und die Antwort sagt es, statt sie als vollen Wert
    auszuliefern."""
    import backend.api.routes.energie_profil.views as views
    import backend.services.solar_forecast_service as sfs
    from backend.api.routes.energie_profil.views import get_tagesprognose

    async def kein_kanon(*args, **kwargs):
        return None

    async def nur_west(**kwargs):
        if kwargs["ausrichtung"] < 0:
            return None
        return _fake_prognose(kwargs["kwp"], kwargs["ausrichtung"], kwargs.get("days"))

    monkeypatch.setattr(views, "_pv_stunden_aus_kanon", kein_kanon)
    monkeypatch.setattr(sfs, "get_solar_prognose", nur_west)

    anlage = await _seed_ost_west(db)
    await _seed_verbrauchsprofil(db, anlage.id)
    resp = await get_tagesprognose(anlage.id, datum=date.today() + timedelta(days=1), db=db)

    assert any("Dachflächen" in h for h in (resp.hinweise or []))


# ── Pfad 3: /solar-prognose (14-Tage) ───────────────────────────────────────

async def test_solar_prognose_faechert_auf(db, _abrufe, monkeypatch):
    """Der Aussichten-Endpoint fragt je Orientierungsgruppe getrennt ab."""
    import backend.api.routes.solar_prognose as sp
    from backend.api.routes.solar_prognose import get_solar_prognose_endpoint

    async def kein_kanon(*args, **kwargs):
        return None

    monkeypatch.setattr(sp, "kanon_tagesprognose", kein_kanon)

    anlage = await _seed_ost_west(db)
    await get_solar_prognose_endpoint(anlage.id, tage=7, db=db)

    assert {a for _, a in _abrufe} == {-90, 90}


# ── Pfad 4: Live-Wetter (N52) ───────────────────────────────────────────────

async def test_live_wetter_gti_faechert_auf(db, monkeypatch):
    """N52: die Live-Seite gewichtet GTI über ALLE Orientierungsgruppen. Der
    Haupt-Abruf trägt im Multi-Fall kein `tilt`/`azimuth` — beides käme aus
    ``gruppen[0]``, und die Reihenfolge war vor A20 die der DB-Query."""
    import backend.api.routes.live_wetter as lw

    gti_calls: list[tuple[int, int]] = []

    async def fake_gti(client, latitude, longitude, neigung, ausrichtung):
        gti_calls.append((neigung, ausrichtung))
        return [100.0] * 24

    class _Resp:
        def raise_for_status(self):
            return None

        def json(self):
            heute = date.today().isoformat()
            return {
                "hourly": {
                    "time": [f"{heute}T{h:02d}:00" for h in range(24)],
                    "temperature_2m": [20.0] * 24,
                    "weather_code": [0] * 24,
                    "cloud_cover": [0] * 24,
                    "precipitation": [0.0] * 24,
                    "shortwave_radiation": [200.0] * 24,
                    "sunshine_duration": [1800.0] * 24,
                },
                "daily": {
                    "sunshine_duration": [36000.0],
                    "temperature_2m_max": [24.0], "temperature_2m_min": [12.0],
                    "sunrise": [f"{heute}T06:00"], "sunset": [f"{heute}T21:00"],
                },
            }

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, *a, **k):
            return _Resp()

    monkeypatch.setattr(lw, "_fetch_multi_string_gti", lw._fetch_multi_string_gti)
    monkeypatch.setattr(lw, "_fetch_gti_for_gruppe", fake_gti)
    monkeypatch.setattr(lw.httpx, "AsyncClient", lambda *a, **k: _Client())
    monkeypatch.setattr(lw, "_cache_get", lambda *a, **k: None)
    monkeypatch.setattr(lw, "_cache_set", lambda *a, **k: None)
    monkeypatch.setattr(lw, "_error_cache_check", lambda *a, **k: False)

    anlage = await _seed_ost_west(db)
    await lw.get_live_wetter(anlage_id=anlage.id, demo=False, db=db)

    assert {a for _, a in gti_calls} == {-90, 90}


# ── kWp-Lesen: Spalte ODER parameter-JSON, überall über den SoT-Helper ──────

async def test_orientierungsgruppen_lesen_kwp_ueber_den_sot(db):
    """Ein Modul mit kWp nur im ``parameter``-JSON darf nicht aus der
    Gruppierung fallen. Die Live-Seite las bis A20 ``pv.leistung_kwp`` direkt —
    ein solches Dach fehlte dort in Gesamt-kWp UND GTI-Gewichtung."""
    from backend.api.routes.live_wetter import _get_pv_orientierungsgruppen

    anlage = await _seed_ost_west(db)
    db.add(Investition(
        anlage_id=anlage.id, typ="pv-module", bezeichnung="Süd (kWp nur im JSON)",
        leistung_kwp=None, neigung_grad=30,
        anschaffungsdatum=date(2024, 1, 1),
        parameter={"ausrichtung_grad": 0, "kwp": 4.0},
    ))
    await db.flush()

    from sqlalchemy import select
    invs = (await db.execute(
        select(Investition).where(Investition.anlage_id == anlage.id)
    )).scalars().all()

    gruppen = _get_pv_orientierungsgruppen(invs)
    assert sum(g["kwp"] for g in gruppen) == pytest.approx(14.0)
    assert {g["ausrichtung"] for g in gruppen} == {-90, 0, 90}
    # Deterministische Reihenfolge: stärkste Gruppe zuerst (der Cache-Key und
    # der Ein-Gruppen-Zweig lesen `gruppen[0]`).
    assert gruppen[0]["kwp"] == pytest.approx(5.0)


async def test_aussichten_kwp_liest_parameter_gepflegte_module(db):
    """N36: ``_lade_anlage_mit_pv`` summierte nur die Spalte — ein Modul mit
    kWp im ``parameter`` fehlte in der Anlagenleistung, und der
    ``or anlage.leistung_kwp``-Fallback greift nur bei Summe 0."""
    from backend.api.routes.aussichten import _lade_anlage_mit_pv

    anlage = await _seed_ost_west(db)
    db.add(Investition(
        anlage_id=anlage.id, typ="pv-module", bezeichnung="Süd (kWp nur im JSON)",
        leistung_kwp=None, neigung_grad=30,
        anschaffungsdatum=date(2024, 1, 1),
        parameter={"ausrichtung_grad": 0, "kwp": 4.0},
    ))
    await db.flush()

    _, _, _, kwp = await _lade_anlage_mit_pv(db, anlage.id)
    assert kwp == pytest.approx(14.0)


async def test_prefetch_waermt_den_key_den_der_endpoint_liest(db):
    """N56: Prefetch und Endpoint bauen den Live-Wetter-Cache-Key aus derselben
    Funktion. Vorher standen zwei Format-Strings nebeneinander, gesichert nur
    durch den Kommentar „muss exakt übereinstimmen"."""
    from sqlalchemy import select
    from backend.api.routes.live_wetter import (
        _get_pv_orientierungsgruppen, live_wetter_cache_key,
    )

    anlage = await _seed_ost_west(db)
    invs = (await db.execute(
        select(Investition).where(Investition.anlage_id == anlage.id)
    )).scalars().all()
    gruppen = _get_pv_orientierungsgruppen(invs)

    key = live_wetter_cache_key(anlage.latitude, anlage.longitude, gruppen, "auto")
    # Die ganze Gruppen-Signatur steckt im Key — nicht nur die stärkste Gruppe.
    assert "-90" in key and "90" in key
    assert key != live_wetter_cache_key(
        anlage.latitude, anlage.longitude, gruppen[:1], "auto"
    )
