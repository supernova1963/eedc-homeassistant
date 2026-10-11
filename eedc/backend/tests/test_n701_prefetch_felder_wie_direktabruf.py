"""N-701: der Prefetch fragt dieselben Open-Meteo-Felder wie der Direktabruf.

⛔ **Der Defekt** (Analyse ``ANALYSE-NEBENFUNDE-RF9-E.md`` §E2): Der Live-Wetter-
Prefetch (``prefetch_service._prefetch_live_wetter``, seit 37d7ca74) schreibt unter
den Schlüssel der Route, führte aber eine eigene Kopie der Parameterliste — ohne
die stündliche ``sunshine_duration``. Die Route las den Eintrag (0 Abrufe) und
``_sonnenstunden`` fand nichts: «Sonnenstunden», «bisher», «Rest» leer, in
Cockpit → Live fehlten die SunProgressBar-Zeile und «Xh Ym Sonne», bis zu 60 min
(Ein-Gruppen-Anlage; direkt geholt 10,0 / bisher + Rest 10,0).

**Was jetzt gilt:** eine Feldliste, ein Ort — ``LIVE_WETTER_HOURLY_FELDER`` /
``LIVE_WETTER_DAILY_FELDER`` in ``api/routes/live_wetter.py``; Direktabruf und
Prefetch lesen sie beide.

Gestellt: ``httpx.AsyncClient`` als Open-Meteo-Attrappe, die — wie die echte API —
nur die **angefragten** Variablen liefert, und die Nähte aus
``test_n698_live_wetter_prefetch_luecke.py``. Der Cache ist der echte (L1).
Uhr-unabhängig: geprüft werden die Tagessumme und «bisher + Rest», nicht die
Aufteilung nach der laufenden Stunde.
"""
from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import select

from backend.api.routes import live_wetter
from backend.api.routes.live_wetter import LiveWetterResponse, get_live_wetter
from backend.models import Anlage, Investition
from backend.services import prefetch_service
from backend.services.wetter import cache as wetter_cache

pytestmark = pytest.mark.asyncio

TAG = "2026-03-10"
_SONNE_S = [0.0] * 6 + [3000.0] * 12 + [0.0] * 6     # 36 000 s = 10,0 h


def _om_voll() -> dict:
    times = [f"{TAG}T{h:02d}:00" for h in range(24)]
    n = len(times)
    return {
        "hourly": {
            "time": times, "temperature_2m": [12.0] * n, "weather_code": [1] * n,
            "cloud_cover": [30] * n, "precipitation": [0.0] * n,
            "shortwave_radiation": [0.0] * 6 + [300.0] * 12 + [0.0] * 6,
            "sunshine_duration": _SONNE_S,
            "global_tilted_irradiance": [0.0] * 6 + [450.0] * 12 + [0.0] * 6,
        },
        "daily": {"time": [TAG], "sunshine_duration": [36000.0], "temperature_2m_min": [6.0],
                  "temperature_2m_max": [15.0], "sunrise": [f"{TAG}T06:40"], "sunset": [f"{TAG}T18:10"]},
    }


class _Resp:
    def __init__(self, body: dict):
        self._body = body

    def raise_for_status(self):
        return None

    def json(self):
        return self._body


@pytest.fixture
def om(monkeypatch):
    """Open-Meteo gestellt: liefert nur angefragte Variablen; ``om["params"]`` schneidet jeden Abruf mit."""
    stand = {"params": []}

    class _Client:
        def __init__(self, *a, **k):  # noqa: ARG002
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, params=None):  # noqa: ARG002
            p = dict(params or {})
            stand["params"].append(p)
            voll = _om_voll()
            h = [v for v in p.get("hourly", "").split(",") if v]
            d = [v for v in p.get("daily", "").split(",") if v]
            return _Resp({
                "hourly": {k: v for k, v in voll["hourly"].items() if k == "time" or k in h},
                "daily": {k: v for k, v in voll["daily"].items() if k == "time" or k in d},
            })

    monkeypatch.setattr(httpx, "AsyncClient", _Client)
    return stand


_EINE_GRUPPE = [{"neigung": 30, "ausrichtung": 0, "kwp": 10.0}]


async def test_prefetch_eintrag_traegt_die_felder_des_direktabrufs(om):
    """Feldgleichheit über den Cache-Eintrag: Prefetch ⊇ Direktabruf (und dieselben Parameter)."""
    lat, lon = 49.701, 9.701
    key = live_wetter.live_wetter_cache_key(lat, lon, _EINE_GRUPPE, "auto")
    wetter_cache._cache.pop(key, None)
    try:
        anlage = SimpleNamespace(id=701, latitude=lat, longitude=lon, wetter_modell="auto")
        direkt = await live_wetter._lade_forecast_gecached(anlage, _EINE_GRUPPE, key)
        assert direkt is not None and len(om["params"]) == 1
        p_direkt = om["params"][0]
        wetter_cache._cache.pop(key, None)

        await prefetch_service._prefetch_live_wetter(lat, lon, _EINE_GRUPPE, "auto")
        assert len(om["params"]) == 2
        p_prefetch = om["params"][1]
        eintrag = wetter_cache._cache_get(key)
        assert eintrag is not None

        for teil in ("hourly", "daily"):
            fehlt = set(direkt[0][teil]) - set(eintrag[0][teil])
            assert not fehlt, (
                f"Der Prefetch-Eintrag ({teil}) fehlt {sorted(fehlt)} gegenüber dem Direktabruf — "
                f"die Route liest ihn ohne eigenen Abruf (N-701)."
            )
        assert p_prefetch == p_direkt, (
            f"Prefetch und Direktabruf fragen verschiedene Parameter: {p_prefetch} ≠ {p_direkt} (N-701)."
        )
    finally:
        wetter_cache._cache.pop(key, None)


@pytest.fixture
def naehte(monkeypatch):
    import backend.services.ha_state_service as hss
    import backend.services.mqtt_inbound_service as mis
    import backend.services.prognose_kanon as pk
    import backend.services.solcast_service as scs
    import backend.services.verbrauchsprognose_heute as vph
    from backend.services.prognose_kanon import KanonPrognose, KanonTag

    async def _keins(*a, **k):  # noqa: ARG001
        return None

    async def _kanon_leer(*a, **k):  # noqa: ARG001
        tag = KanonTag(datum=TAG, om_kwh=None, eedc_kwh=None, vm_kwh=None, nm_kwh=None, profil=None,
                       om_stundenprofil_kwh=None, om_vollstaendig=True)
        return KanonPrognose(tage=[tag], rest_heute_kwh=None, ist_bisher_kwh=None,
                             heute_rollend_kwh=None, skalar_fallback=None)

    async def _wahl(*a, **k):  # noqa: ARG001
        return vph.ProfilWahl()

    class _HA:
        is_available = False

    monkeypatch.setattr(live_wetter, "_get_lernfaktor", _keins)
    monkeypatch.setattr(live_wetter, "_speichere_prognose", lambda *a, **k: _keins())
    monkeypatch.setattr(pk, "kanon_tagesprognose", _kanon_leer)
    monkeypatch.setattr(vph, "waehle_verbrauchsprofil", _wahl)
    monkeypatch.setattr(hss, "get_ha_state_service", lambda: _HA())
    monkeypatch.setattr(mis, "get_mqtt_inbound_service", lambda: None)
    monkeypatch.setattr(scs, "get_solcast_forecast", _keins)


async def _route(db, a) -> dict:
    roh = await get_live_wetter(anlage_id=a.id, demo=False, db=db)
    return LiveWetterResponse.model_validate(roh).model_dump(mode="json")


async def test_route_liefert_nach_einem_prefetch_die_sonnenstunden(db, om, naehte):
    a = Anlage(anlagenname="N-701", leistung_kwp=10.0, latitude=48.701, longitude=11.701)
    db.add(a)
    await db.flush()
    db.add(Investition(anlage_id=a.id, typ="pv-module", bezeichnung="Süd",
                       anschaffungsdatum=date(2024, 1, 1), leistung_kwp=10.0,
                       neigung_grad=30.0, parameter={"ausrichtung_grad": 0}))
    await db.flush()
    gruppen = live_wetter._get_pv_orientierungsgruppen(list((await db.execute(
        select(Investition).where(Investition.anlage_id == a.id))).scalars()))
    key = live_wetter.live_wetter_cache_key(a.latitude, a.longitude, gruppen, "auto")
    wetter_cache._cache.pop(key, None)
    try:
        direkt = await _route(db, a)
        assert direkt["sonnenstunden"] == pytest.approx(10.0)
        wetter_cache._cache.pop(key, None)

        await prefetch_service._prefetch_live_wetter(a.latitude, a.longitude, gruppen, "auto")
        om["params"].clear()
        danach = await _route(db, a)
        assert om["params"] == [], "Die Route bedient sich aus dem Prefetch-Eintrag (kein eigener Abruf)."
        assert danach["sonnenstunden"] == pytest.approx(10.0), (
            f"Nach dem Prefetch fehlen die Sonnenstunden: {danach['sonnenstunden']!r} "
            f"(bisher {danach['sonnenstunden_bisher']!r}, Rest {danach['sonnenstunden_rest']!r}) — N-701."
        )
        assert danach["sonnenstunden_bisher"] is not None and danach["sonnenstunden_rest"] is not None
        assert danach["sonnenstunden_bisher"] + danach["sonnenstunden_rest"] == pytest.approx(10.0, abs=0.11)
        assert danach["pv_prognose_kwh"] == pytest.approx(direkt["pv_prognose_kwh"])
    finally:
        wetter_cache._cache.pop(key, None)
