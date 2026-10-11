"""N-696: liefert die gewählte Quelle Solcast für heute nichts, gilt eedc — mit Hinweis.

⛔ **Der Defekt:** ``prognose_router.resolve_prognose_quelle`` wählt Solcast mit
HA-Verbindung (bzw. API-Token), ohne zu prüfen, ob Daten kommen. Lieferte
``get_solcast_forecast`` nichts, fiel ``_pv_prognose_aktiv`` STILL auf den
eedc-Wert zurück: die Antwort trug ``prognose_quelle: "solcast"``, die
eedc-Zahl als Heute-Wert ohne ``rueckfall``, kein ``prognose_quelle_hinweis``
— die Kachel zeigte die eedc-Prognose unter „Solar-Aussicht (Solcast)" (Analyse
§C2). Für SFML gab es genau diesen Rückfall längst, mit Hinweis.

**Was jetzt gilt** (HANDBUCH_PROGNOSEN §2.3: „fällt eedc auf die eedc-Quelle
zurück und zeigt einen Hinweistext"; eine Regel für beide Fremdquellen, ein Ort
``live_wetter_antwort._pq_nach_abruf``): Quelle ``eedc``, Hinweis „Solcast
liefert aktuell keine Daten, eedc-Prognose aktiv.", die Zahlen sind die des
Kanons (Tageswert, Rest, rollend), keine Quellen-Tage.

Gestellt wie ``test_n689_live_wetter_antwortmodell.py``; über HTTP.
Schwesterdateien: ``test_n695_live_wetter_vm_nm_quelle.py``, Frontend
``components/live/SolarAussichtTeilwerte.test.tsx``.
"""
from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI

from backend.api.deps import get_db
from backend.api.routes import live_wetter
from backend.models import Anlage

pytestmark = pytest.mark.asyncio

TAG = "2026-03-10"
SOLCAST_HINWEIS = "Solcast liefert aktuell keine Daten, eedc-Prognose aktiv."
SFML_HINWEIS = "SFML liefert aktuell keine Daten, eedc-Prognose aktiv."


def _om() -> dict:
    times = [f"{TAG}T{h:02d}:00" for h in range(24)]
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
                  "sunrise": [f"{TAG}T06:40"], "sunset": [f"{TAG}T18:10"]},
    }


def _kanon():
    from backend.services.prognose_kanon import KanonPrognose, KanonTag
    slots = [round(max(0.0, 2.6 - 0.37 * abs(h - 12.5)), 3) for h in range(24)]
    tag = KanonTag(datum=TAG, om_kwh=19.9, eedc_kwh=21.4, vm_kwh=9.9, nm_kwh=11.4,
                   profil=SimpleNamespace(stundenprofil_export_kwh=slots),
                   om_stundenprofil_kwh=slots, om_vollstaendig=True)
    return KanonPrognose(tage=[tag], rest_heute_kwh=7.3, ist_bisher_kwh=13.2,
                         heute_rollend_kwh=20.5, skalar_fallback=None)


def _solcast(daily_kwh=18.6):
    stunden = [round(max(0.0, 2.1 - 0.33 * abs(h - 12.5)), 2) for h in range(24)]
    return SimpleNamespace(daily_kwh=daily_kwh, daily_p10_kwh=12.1, daily_p90_kwh=23.3,
                           hourly_kw=stunden, tage_voraus=[])


@pytest.fixture
def naehte(monkeypatch):
    import backend.services.ha_state_service as hss
    import backend.services.mqtt_inbound_service as mis
    import backend.services.prognose_discovery as pdisc
    import backend.services.prognose_kanon as pk
    import backend.services.solcast_service as scs
    import backend.services.verbrauchsprognose_heute as vph

    stand = {"solcast": None, "sfml": SimpleNamespace(gefunden=False), "gespeichert": []}

    async def _lade(anlage, gruppen, cache_key):  # noqa: ARG001
        return (_om(), None, True)

    async def _keins(*a, **k):  # noqa: ARG001
        return None

    def _speichere(*a, **k):
        stand["gespeichert"].append(k)
        return _keins()

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

    monkeypatch.setattr(live_wetter, "_lade_forecast_gecached", _lade)
    monkeypatch.setattr(live_wetter, "_get_lernfaktor", _keins)
    monkeypatch.setattr(live_wetter, "_speichere_prognose", _speichere)
    monkeypatch.setattr(pk, "kanon_tagesprognose", _kanon_f)
    monkeypatch.setattr(vph, "waehle_verbrauchsprofil", _wahl)
    monkeypatch.setattr(hss, "get_ha_state_service", lambda: _HA())
    monkeypatch.setattr(pdisc, "discover_prognose_sensoren", _disc)
    monkeypatch.setattr(mis, "get_mqtt_inbound_service", lambda: None)
    monkeypatch.setattr(scs, "get_solcast_forecast", _solcast_f)
    return stand


async def _http(db, quelle: str) -> dict:
    anlage = Anlage(anlagenname="N-696", leistung_kwp=10.0, latitude=53.87, longitude=10.68)
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


@pytest.mark.parametrize("solcast, warum", [
    (None, "Solcast-Abruf liefert nichts"),
    (_solcast(daily_kwh=None), "Solcast-Objekt ohne Tageswert"),
])
async def test_solcast_ohne_daten_faellt_mit_hinweis_auf_eedc(db, naehte, solcast, warum):
    naehte["solcast"] = solcast
    res = await _http(db, "solcast")

    assert res["prognose_quelle"] == "eedc", (
        f"{warum}: die Antwort trägt weiter „solcast\" — die Kachel zeigt die eedc-Zahl "
        "unter „Solar-Aussicht (Solcast)\" ohne Vermerk (N-696)."
    )
    assert res["prognose_quelle_hinweis"] == SOLCAST_HINWEIS
    # Die Zahlen sind die der eedc-Quelle — Tageswert, Rest und rollend aus dem Kanon.
    assert res["pv_prognose_kwh"] == pytest.approx(21.4)
    assert res["pv_prognose_rest_kwh"] == pytest.approx(7.3)
    assert res["pv_prognose_heute_rollend_kwh"] == pytest.approx(20.5)
    assert res["prognose_quelle_tage"] is None


async def test_solcast_mit_daten_bleibt_solcast(db, naehte):
    """Gegenfall: Solcast liefert — Quelle Solcast, kein Hinweis, Heute aus Solcast."""
    naehte["solcast"] = _solcast()
    res = await _http(db, "solcast")

    assert res["prognose_quelle"] == "solcast"
    assert res["prognose_quelle_hinweis"] is None
    assert res["pv_prognose_kwh"] == pytest.approx(18.6)
    assert res["prognose_quelle_tage"][0]["kwh"] == pytest.approx(18.6)


async def test_sfml_rueckfall_unveraendert_und_solcast_wird_weiter_mitgeschrieben(db, naehte):
    """Der SFML-Rückfall steht jetzt hinter dem Solcast-Abruf (eine Stelle für beide):
    derselbe Hinweis wie vorher, und Solcast wird für die Persistenz weiter gelesen."""
    naehte["solcast"] = _solcast()
    res = await _http(db, "sfml")

    assert res["prognose_quelle"] == "eedc"
    assert res["prognose_quelle_hinweis"] == SFML_HINWEIS
    assert res["pv_prognose_kwh"] == pytest.approx(21.4)
    assert naehte["gespeichert"] and naehte["gespeichert"][0]["solcast_kwh"] == pytest.approx(18.6)
