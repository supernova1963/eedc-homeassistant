"""N-695: die Quellen-Tage der Live-Wetter-Route sagen je TEILWERT, woher VM/NM kommen.

⛔ **Der Defekt:** Bei Solcast als Quelle liefert der Live-Pfad nur für HEUTE
einen Stundenverlauf (``solcast.hourly_kw``); für Morgen/Übermorgen trägt
``prognose_quelle_tage`` die Solcast-Tageszahl, aber ``vm_kwh``/``nm_kwh`` =
``None``. Die Kachel *Cockpit → Live → Solar-Aussicht* füllt sie aus dem
eedc-Kanon — unter „Solar-Aussicht (Solcast)", ohne Vermerk, und die Teile
addieren sich nicht zur Kopfzahl (Analyse §C1: 9,7 kWh über 13,0 + 15,0; das
#401-Symptom). Der Vermerk hing nur am Tageswert (``rueckfall``). Dieselbe
Klasse: SFML ohne ``forecast``-Attribut hat an KEINEM Tag ein Profil.

**Was jetzt gilt** (HANDBUCH_PROGNOSEN §2.3: eine Näherung bleibt stehen und
wird dazugesagt): jeder Tag trägt ``vm_nm_rueckfall`` — ``"eedc"``, wenn die
gewählte Quelle für ihn kein Stundenprofil hat, sonst ``None``. Das Frontend
schreibt dann „eedc" an die Teilwerte (``SolarAussichtTeilwerte.test.tsx``).

Über HTTP (ASGI, der echte Router mit ``response_model``) — das Feld muss beim
Anwender ankommen, nicht nur in der Rohrückgabe. Gestellt sind dieselben Nähte
wie in ``test_n689_live_wetter_antwortmodell.py``; dazu die Uhr des
Phasenmoduls (``live_wetter_antwort.date``) auf einen festen Tag, damit die
Solcast-Folgetage per Datum zugeordnet werden können (kein ``date.today()`` in
der Probe, Wächter ``test_konformitaet_echte_uhr_in_tests.py``).
Schwesterdateien: ``test_n689_live_wetter_antwortmodell.py``,
``test_n696_live_wetter_solcast_rueckfall.py``.
"""
from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI

from backend.api.deps import get_db
from backend.api.routes import live_wetter, live_wetter_antwort
from backend.models import Anlage

pytestmark = pytest.mark.asyncio

TAG = date(2026, 3, 10)


class _FesterTag(date):
    """``date`` mit fester ``today()`` — nur für das Phasenmodul der Route."""

    @classmethod
    def today(cls):
        return cls(TAG.year, TAG.month, TAG.day)


def _iso(i: int) -> str:
    return date.fromordinal(TAG.toordinal() + i).isoformat()


def _om() -> dict:
    times = [f"{TAG.isoformat()}T{h:02d}:00" for h in range(24)]
    n = len(times)
    return {
        "hourly": {
            "time": times,
            "temperature_2m": [12.0] * n, "weather_code": [1] * n, "cloud_cover": [30] * n,
            "precipitation": [0.0] * n,
            "shortwave_radiation": [0.0] * 6 + [300.0] * 12 + [0.0] * 6,
            "sunshine_duration": [0.0] * 6 + [3000.0] * 12 + [0.0] * 6,
            "global_tilted_irradiance": [0.0] * 6 + [400.0] * 12 + [0.0] * 6,
        },
        "daily": {"temperature_2m_min": [6.0], "temperature_2m_max": [15.0],
                  "sunrise": [f"{TAG.isoformat()}T06:40"], "sunset": [f"{TAG.isoformat()}T18:10"]},
    }


def _kanon():
    from backend.services.prognose_kanon import KanonPrognose, KanonTag
    slots = [round(max(0.0, 2.6 - 0.37 * abs(h - 12.5)), 3) for h in range(24)]
    tag = KanonTag(datum=TAG.isoformat(), om_kwh=19.9, eedc_kwh=21.4, vm_kwh=9.9, nm_kwh=11.4,
                   profil=SimpleNamespace(stundenprofil_export_kwh=slots),
                   om_stundenprofil_kwh=slots, om_vollstaendig=True)
    return KanonPrognose(tage=[tag], rest_heute_kwh=7.3, ist_bisher_kwh=13.2,
                         heute_rollend_kwh=20.5, skalar_fallback=None)


def _solcast():
    """Solcast wie im Live-Pfad: Heute stündlich, Morgen/Übermorgen nur als Tageswert."""
    stunden = [round(max(0.0, 2.1 - 0.33 * abs(h - 12.5)), 2) for h in range(24)]
    return SimpleNamespace(
        daily_kwh=18.6, daily_p10_kwh=12.1, daily_p90_kwh=23.3, hourly_kw=stunden,
        tage_voraus=[{"datum": _iso(1), "kwh": 24.4}, {"datum": _iso(2), "kwh": 9.7}],
    )


def _sfml_ohne_forecast():
    """SFML mit Tageswerten, ohne ``forecast``- und ``hours``-Attribut."""
    werte = {"heute_kwh": 17.4, "morgen_kwh": 22.2, "uebermorgen_kwh": 30.1, "genauigkeit_30d": 91.2}
    return SimpleNamespace(gefunden=True, wert=werte.get, attribut=lambda rolle: None)


def _sfml_mit_forecast():
    """SFML mit evcc-``forecast`` über drei Tage (Wh je Stunde) — jeder Tag hat ein Profil."""
    eintraege = []
    for i in range(3):
        for h in range(7, 19):
            start = f"{_iso(i)}T{h:02d}:00:00+01:00"
            ende = f"{_iso(i)}T{h + 1:02d}:00:00+01:00"
            eintraege.append({"start": start, "end": ende, "value": 1500.0})
    werte = {"heute_kwh": 18.0, "morgen_kwh": 18.0, "uebermorgen_kwh": 18.0, "genauigkeit_30d": 91.2}
    return SimpleNamespace(
        gefunden=True, wert=werte.get,
        attribut=lambda rolle: eintraege if rolle == "stundenprofil" else None,
    )


@pytest.fixture
def naehte(monkeypatch):
    import backend.services.ha_state_service as hss
    import backend.services.mqtt_inbound_service as mis
    import backend.services.prognose_discovery as pdisc
    import backend.services.prognose_kanon as pk
    import backend.services.solcast_service as scs
    import backend.services.verbrauchsprognose_heute as vph

    stand = {"solcast": _solcast(), "sfml": _sfml_ohne_forecast()}

    async def _lade(anlage, gruppen, cache_key):  # noqa: ARG001
        return (_om(), None, True)

    async def _keins(*a, **k):  # noqa: ARG001
        return None

    async def _kanon_f(*a, **k):  # noqa: ARG001
        return _kanon()

    async def _wahl(*a, **k):  # noqa: ARG001
        return vph.ProfilWahl()

    async def _solcast_f(anlage):  # noqa: ARG001
        return stand["solcast"]

    async def _disc(integration):  # noqa: ARG001
        return stand["sfml"]

    class _HA:
        is_available = True

        async def get_sensor_states_batch(self, ids):  # noqa: ARG002
            return {}

    monkeypatch.setattr(live_wetter_antwort, "date", _FesterTag)
    monkeypatch.setattr(live_wetter, "_lade_forecast_gecached", _lade)
    monkeypatch.setattr(live_wetter, "_get_lernfaktor", _keins)
    monkeypatch.setattr(live_wetter, "_speichere_prognose", lambda *a, **k: _keins())
    monkeypatch.setattr(pk, "kanon_tagesprognose", _kanon_f)
    monkeypatch.setattr(vph, "waehle_verbrauchsprofil", _wahl)
    monkeypatch.setattr(hss, "get_ha_state_service", lambda: _HA())
    monkeypatch.setattr(pdisc, "discover_prognose_sensoren", _disc)
    monkeypatch.setattr(mis, "get_mqtt_inbound_service", lambda: None)
    monkeypatch.setattr(scs, "get_solcast_forecast", _solcast_f)
    return stand


async def _http(db, quelle: str) -> dict:
    anlage = Anlage(anlagenname="N-695", leistung_kwp=10.0, latitude=53.87, longitude=10.68)
    anlage.prognose_quelle = quelle
    db.add(anlage)
    await db.flush()

    app = FastAPI()
    app.include_router(live_wetter.router, prefix="/api/live")

    async def _db():
        yield db

    app.dependency_overrides[get_db] = _db
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(f"/api/live/{anlage.id}/wetter")
    assert resp.status_code == 200, resp.text
    return resp.json()


async def test_solcast_folgetage_tragen_den_vm_nm_vermerk(db, naehte):
    """Der Fall der Analyse: Kopfzahl Solcast (24,4 · 9,7), kein Solcast-Profil für die Folgetage."""
    res = await _http(db, "solcast")
    tage = res["prognose_quelle_tage"]

    assert [t["kwh"] for t in tage] == [18.6, 24.4, 9.7]
    assert [t["rueckfall"] for t in tage] == [None, None, None]
    assert [t["vm_kwh"] is None for t in tage] == [False, True, True]
    assert [t.get("vm_nm_rueckfall") for t in tage] == [None, "eedc", "eedc"], (
        "Morgen/Übermorgen: Tageszahl aus Solcast, VM/NM kommen in der Kachel aus dem "
        "eedc-Kanon — die Antwort muss es je Teilwert sagen (N-695, #401-Symptom)."
    )


async def test_sfml_ohne_forecast_an_allen_tagen(db, naehte):
    """Klasse wie N-695: SFML ohne Stundenprofil-Attribut — an keinem Tag VM/NM aus SFML."""
    res = await _http(db, "sfml")
    tage = res["prognose_quelle_tage"]

    assert [t["kwh"] for t in tage] == [17.4, 22.2, 30.1]
    assert [t.get("vm_nm_rueckfall") for t in tage] == ["eedc", "eedc", "eedc"]


async def test_sfml_mit_forecast_traegt_keinen_vermerk(db, naehte):
    """Gegenfall: hat die Quelle für jeden Tag ein Profil, kommen VM/NM aus ihr — kein Vermerk."""
    naehte["sfml"] = _sfml_mit_forecast()
    res = await _http(db, "sfml")
    tage = res["prognose_quelle_tage"]

    assert all(t["vm_kwh"] is not None for t in tage)
    assert [t.get("vm_nm_rueckfall") for t in tage] == [None, None, None]


async def test_eedc_hat_keine_quellen_tage(db, naehte):
    """eedc: kein Feld zu beschriften — der Kanon gilt für alle Zahlen."""
    res = await _http(db, "eedc")
    assert res["prognose_quelle_tage"] is None
