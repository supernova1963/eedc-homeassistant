"""Energy-Dashboard-Vorschläge (#197) im Setup-Wizard — die Route hängt an der Verbindung, nicht am Add-on.

**Fall (Triage 3.11.2026, B2):** `/api/sensor-mapping` war nur mit `SUPERVISOR_TOKEN` gemountet. Im Standalone mit
«externe HA-Instanz: Ja» rief der Integrations-Schritt `/suggest` und bekam den SPA-Fallback (HTML, HTTP 200) — der
Client verwarf ihn und blieb bei «Vorschläge werden geladen …». Der Remote-Zweig der Route (WebSocket
`energy/get_prefs`, D2) war damit unerreichbar. Bauform wie N-237 (`test_n237_lts_import_ohne_supervisor.py`): der
Router ist immer gemountet, die Route prüft die Verbindung selbst.

**Dazu P4:** mehrere Solar-Quellen im Energie-Dashboard ergeben keinen `pv_gesamt`-Vorschlag mehr (vorher gewann
still die letzte); der Wizard nennt den Weg über die Datenquellen.

Vorbild: `test_n156_ha_wege_ohne_supervisor.py`. ⚠ Diese Proben laufen ohne Supervisor-Token (Normalfall im Testlauf);
der Add-on-Fall wird am `settings`-Objekt gestellt und wieder abgebaut.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

import pytest
from fastapi.testclient import TestClient

from backend.api.routes import sensor_mapping as sm
from backend.main import app
from backend.models import Anlage
from backend.services import ha_energy_service as hes

PREFS = {
    "energy_sources": [
        {"type": "grid",
         "flow_from": [{"stat_energy_from": "sensor.netzbezug"}],
         "flow_to": [{"stat_energy_to": "sensor.einspeisung"}]},
        {"type": "solar", "stat_energy_from": "sensor.pv"},
    ],
    "device_consumption": [],
}


@pytest.fixture
def route_session(monkeypatch, db):
    """Die Route öffnet ihre eigene Sitzung (`get_session`) — hier die der Probe."""
    @asynccontextmanager
    async def _fake():
        yield db

    monkeypatch.setattr(sm, "get_session", _fake)
    return db


async def _anlage(db) -> int:
    a = Anlage(anlagenname="Wizard", leistung_kwp=10.0)
    db.add(a)
    await db.commit()
    return a.id


def test_kein_supervisor_token_im_testlauf():
    """Vorbedingung — sonst prüften die Standalone-Proben den falschen Fall."""
    assert not os.environ.get("SUPERVISOR_TOKEN")


def test_suggest_route_ist_ohne_supervisor_gemountet():
    """Geprüft an der Registrierung, nicht am Antwort-Code: der HTML-Fallback liefert ebenfalls 200."""
    pfade = {r.path for r in app.routes if hasattr(r, "path")}
    assert "/api/sensor-mapping/{anlage_id}/suggest" in pfade


def test_ohne_verbindung_json_statt_html():
    """Standalone ohne HA-Verbindung: ein sachliches `available=False`, kein SPA-Fallback, kein 500."""
    with TestClient(app) as client:
        antwort = client.get("/api/sensor-mapping/1/suggest")
    assert antwort.status_code == 200, antwort.text
    assert antwort.headers["content-type"].startswith("application/json"), antwort.headers["content-type"]
    assert antwort.json()["available"] is False


async def test_standalone_mit_remote_ha_liefert_vorschlaege(db, route_session, monkeypatch):
    """Der Remote-Zweig (D2) ist erreichbar: Verbindung per Long-Lived-Token ⇒ Prefs per WebSocket."""
    anlage_id = await _anlage(db)
    aufrufe: list = []

    async def verbindung(session):
        return ("http://ha.example:8123/api", "langlebiger-token", "ha_connector")

    async def remote(basis_url, token):
        aufrufe.append((basis_url, token))
        return hes._suggestions_aus_prefs(PREFS)

    monkeypatch.setattr("backend.services.ha_connection.resolve_ha_connection", verbindung)
    monkeypatch.setattr(hes, "get_ha_energy_suggestions_remote", remote)

    antwort = await sm.get_ha_energy_suggest(anlage_id)

    assert aufrufe == [("http://ha.example:8123", "langlebiger-token")]
    assert antwort.available is True
    assert antwort.basis == {"netzbezug": "sensor.netzbezug", "einspeisung": "sensor.einspeisung",
                             "pv_gesamt": "sensor.pv"}


async def test_standalone_ohne_verbindung_ruft_keinen_websocket(db, route_session, monkeypatch):
    anlage_id = await _anlage(db)

    async def keine(session):
        return (None, None, None)

    async def remote(basis_url, token):  # pragma: no cover — darf nicht laufen
        raise AssertionError("ohne Verbindung kein WebSocket")

    monkeypatch.setattr("backend.services.ha_connection.resolve_ha_connection", keine)
    monkeypatch.setattr(hes, "get_ha_energy_suggestions_remote", remote)

    antwort = await sm.get_ha_energy_suggest(anlage_id)
    assert antwort.available is False
    assert antwort.reason_unavailable == "standalone"


async def test_addon_liest_die_supervisor_datei_wie_bisher(db, route_session, monkeypatch):
    """Supervisor-Fall unverändert: Datei-Prefs, kein Remote-Aufruf."""
    anlage_id = await _anlage(db)

    async def remote(basis_url, token):  # pragma: no cover
        raise AssertionError("im Add-on kein Remote-Weg")

    monkeypatch.setattr(hes.settings, "supervisor_token", "supervisor")
    monkeypatch.setattr(hes, "_read_energy_file", lambda: {"data": PREFS})
    monkeypatch.setattr(hes, "get_ha_energy_suggestions_remote", remote)

    antwort = await sm.get_ha_energy_suggest(anlage_id)

    assert antwort.available is True
    assert antwort.basis == {"netzbezug": "sensor.netzbezug", "einspeisung": "sensor.einspeisung",
                             "pv_gesamt": "sensor.pv"}


# ─── P4: mehrere Solar-Quellen ⇒ kein pv_gesamt-Vorschlag ─────────────────────────────────────────────────────────

def test_eine_solar_quelle_wird_pv_gesamt():
    s = hes._suggestions_aus_prefs(PREFS)
    assert ("pv_gesamt", "sensor.pv") in {(e.feld, e.entity_id) for e in s.energy_sources}


def test_mehrere_solar_quellen_kein_pv_gesamt_vorschlag():
    """Zwei Wechselrichter + Balkonkraftwerk sind Teilmengen, kein Anlagenzähler — vorher gewann still die letzte."""
    prefs = {**PREFS, "energy_sources": PREFS["energy_sources"] + [
        {"type": "solar", "stat_energy_from": "sensor.pv_west"},
        {"type": "solar", "stat_energy_from": "sensor.bkw"},
    ]}
    s = hes._suggestions_aus_prefs(prefs)
    felder = {e.feld for e in s.energy_sources}
    assert "pv_gesamt" not in felder
    assert felder == {"netzbezug", "einspeisung"}, "Netz bleibt unverändert"
