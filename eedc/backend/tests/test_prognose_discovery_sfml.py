"""Discovery-Tests für SFMLs Stundenprofil-Attribut (#110 „A").

Die SFML-Discovery liest jetzt nicht mehr nur die State-Skalare (Tages-kWh),
sondern trägt für den evcc-Sensor das ``forecast``-Attribut (mehrtägiges
Stundenprofil) und für ``prognose_heute`` das ``hours``-Attribut (24 h Fallback)
mit — damit der Live-/Vergleich-Pfad SFMLs echte Kurvenform nutzen kann statt
SFMLs Tagessumme über die OpenMeteo-GTI-Form zu „schmieren".
"""

from __future__ import annotations

import httpx

import backend.services.prognose_discovery as disc


class _FakeResp:
    status_code = 200

    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class _FakeClient:
    def __init__(self, payload):
        self._payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, *args, **kwargs):
        return _FakeResp(self._payload)


class _FakeHA:
    is_available = True
    api_url = "http://ha.local/api"
    token = "tok"


def _patch_ha(monkeypatch, states):
    # Kein `HA_INTEGRATION_AVAILABLE`-Patch mehr: die Discovery gatet seit
    # N-156 nicht mehr auf den Supervisor-Token, sondern auf die Erreichbarkeit
    # des `HAStateService` (unten gefakt). Ein Patch auf ein Symbol, das die
    # Funktion nicht mehr liest, hätte nur Sicherheit vorgetäuscht.
    monkeypatch.setattr(
        "backend.services.ha_state_service.get_ha_state_service",
        lambda: _FakeHA(),
    )
    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: _FakeClient(states))
    disc.invalidate_cache()


async def test_evcc_forecast_attribut_wird_mitgenommen(monkeypatch):
    states = [
        {
            "entity_id": "sensor.solar_forecast_ml_evcc_solar_prognose",
            "state": "69 slots",
            "attributes": {
                "friendly_name": "Solar Forecast ML evcc",
                "forecast": [
                    {"start": "2026-06-06T12:00:00", "end": "2026-06-06T13:00:00", "value": 5000},
                ],
            },
        },
        {
            "entity_id": "sensor.prognose_heute",
            "state": "42.0",
            "attributes": {"unit_of_measurement": "kWh", "hours": {"13:00": 8.139}},
        },
    ]
    _patch_ha(monkeypatch, states)

    result = await disc.discover_prognose_sensoren("sfml")

    assert result.gefunden
    assert result.wert("heute_kwh") == 42.0
    # Stundenprofil-Rolle trägt die rohe forecast-Liste
    forecast = result.attribut("stundenprofil")
    assert isinstance(forecast, list) and forecast[0]["value"] == 5000
    # prognose_heute trägt das hours-Dict als Fallback-Attribut
    assert result.attribut("heute_kwh") == {"13:00": 8.139}


async def test_hours_fallback_ohne_evcc(monkeypatch):
    # Kein evcc-Sensor → stundenprofil-Rolle fehlt, hours bleibt als Fallback.
    states = [
        {
            "entity_id": "sensor.prognose_heute",
            "state": "30.0",
            "attributes": {"unit_of_measurement": "kWh", "hours": {"12:00": 5.0}},
        },
    ]
    _patch_ha(monkeypatch, states)

    result = await disc.discover_prognose_sensoren("sfml")

    assert result.gefunden
    assert result.attribut("stundenprofil") is None
    assert result.attribut("heute_kwh") == {"12:00": 5.0}


async def test_kein_attribut_bleibt_none(monkeypatch):
    # Skalar-Rollen ohne Profil-Attribut tragen attribut=None (z.B. Genauigkeit).
    states = [
        {
            "entity_id": "sensor.solar_forecast_ml_genauigkeit_30_tage",
            "state": "92.5",
            "attributes": {"unit_of_measurement": "%"},
        },
    ]
    _patch_ha(monkeypatch, states)

    result = await disc.discover_prognose_sensoren("sfml")

    assert result.attribut("genauigkeit_30d") is None
    assert result.wert("genauigkeit_30d") == 92.5
