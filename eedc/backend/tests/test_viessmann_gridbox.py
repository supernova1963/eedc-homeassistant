"""Tests für den Viessmann-GridBox-/gridX-Cloud-Import-Provider (#410).

Deckt ab:
- Provider-Metadaten (Felder, Registrierung, `getestet=False`).
- Die Auth0-Umstellung, die gridX selbst gemeldet hat (#410, alexmsenger/@grid-x):
  Audience = API-Basis statt `my.gridx`, Bearer = `access_token` statt `id_token`.
- Den Rückfall auf den `id_token`, wenn Auth0 keinen `access_token` liefert —
  samt Warnung, damit der abgekündigte Weg nicht still weiterläuft.
- Den Fehlerpfad: der Grund von Auth0 erreicht die Oberfläche, statt durch die
  pauschale Behauptung „E-Mail/Passwort prüfen" ersetzt zu werden.

⚠ Der echte Login ist lokal NICHT verifizierbar (kein GridBox-Konto) — genau wie
bei Anker SOLIX vor Johnnys Gegentest. Diese Proben sichern deshalb die
*Form* der Anfrage und die *Auswertung* der Antwort, nicht ihre Annahme durch
gridX. Die Angabe zur neuen Auth stammt von gridX selbst; die umgesetzte
Referenz ist `markusschultheis/gridx-homeassistant` (released 2026-08-30).
"""

from __future__ import annotations

import json
import logging

import httpx
import pytest

from backend.services.cloud_import import get_provider, list_providers
from backend.services.cloud_import.viessmann_gridbox import (
    API_BASE,
    AUTH0_AUDIENCE,
    AUTH0_CLIENT_ID,
    AUTH0_REALM,
    ViessmannGridBoxProvider,
    _auth_fehlertext,
    _get_token,
)

_ECHTER_ASYNC_CLIENT = httpx.AsyncClient


def _mock_transport(monkeypatch, handler):
    """`httpx.AsyncClient` durch einen echten Client mit MockTransport ersetzen.

    Der Provider baut seinen Client selbst, ein `client`-Argument gibt es nicht
    (anders als bei Anker SOLIX). Der echte Client bleibt darunter erhalten,
    damit `Response.json()`/`status_code` unverändert die echte httpx-Semantik
    haben — eine handgeschriebene Attrappe würde genau die prüfen, die sie
    selbst definiert.
    """
    def factory(*_a, **_kw):
        return _ECHTER_ASYNC_CLIENT(transport=httpx.MockTransport(handler))

    monkeypatch.setattr(httpx, "AsyncClient", factory)


# --- Provider-Metadaten + Registry ------------------------------------------

def test_info_metadaten():
    info = ViessmannGridBoxProvider().info()
    # Die ID bleibt `viessmann_gridbox`: sie steht im Provenance-Vokabular
    # (`core/source_priority.py`), in gespeicherten `connector_config`-Quellen
    # und in jeder geschriebenen Provenance-Zeile. Änderbar ist nur die Anzeige.
    assert info.id == "viessmann_gridbox"
    assert info.hersteller == "gridX"
    # Kein Gegentest an einem echten Gerät — kein bekannter Nutzer (Gernot,
    # 2026-09-07). Die Kennzeichnung „(*) Ungetestet" in der Auswahl hängt daran.
    assert info.getestet is False

    by_id = {f.id: f for f in info.credential_fields}
    assert set(by_id) == {"username", "password", "system_id"}
    assert by_id["password"].type == "password"
    assert by_id["system_id"].required is False


def test_provider_ist_registriert():
    provider = get_provider("viessmann_gridbox")
    assert isinstance(provider, ViessmannGridBoxProvider)
    assert "viessmann_gridbox" in {p.id for p in list_providers()}


# --- #410: die Auth0-Umstellung ---------------------------------------------

def test_audience_ist_die_api_basis():
    # gridX' Anforderung lautet wörtlich „the audience needs to match the
    # actual API". Die Kopplung an API_BASE ist deshalb der Gegenstand der
    # Regel, nicht nur ihr heutiger Wert.
    assert AUTH0_AUDIENCE == API_BASE
    assert AUTH0_AUDIENCE == "https://api.gridx.de"
    # Der abgekündigte Wert darf nicht zurückkehren.
    assert AUTH0_AUDIENCE != "my.gridx"


@pytest.mark.asyncio
async def test_login_payload_traegt_die_neue_audience(monkeypatch):
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["payload"] = json.loads(request.content)
        return httpx.Response(200, json={"access_token": "AT", "id_token": "IT"})

    _mock_transport(monkeypatch, handler)
    await _get_token("name@example.com", "geheim")

    assert captured["url"] == "https://gridx.eu.auth0.com/oauth/token"
    payload = captured["payload"]
    assert payload["audience"] == "https://api.gridx.de"
    assert payload["client_id"] == AUTH0_CLIENT_ID
    assert payload["realm"] == AUTH0_REALM
    assert payload["grant_type"].endswith("password-realm")


@pytest.mark.asyncio
async def test_token_ist_der_access_token_nicht_der_id_token(monkeypatch):
    # Die eine Probe, die wirklich unterscheidet: Auth0 liefert BEIDE Felder.
    # Wer den id_token zurückgibt, fällt hier auf — und nur hier.
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"access_token": "ACCESS-123", "id_token": "ID-456"},
        )

    _mock_transport(monkeypatch, handler)
    token, fehler = await _get_token("name@example.com", "geheim")

    assert token == "ACCESS-123"
    assert token != "ID-456"
    assert fehler is None


@pytest.mark.asyncio
async def test_ohne_access_token_rueckfall_auf_id_token_mit_warnung(
    monkeypatch, caplog,
):
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"id_token": "ID-456"})

    _mock_transport(monkeypatch, handler)
    with caplog.at_level(logging.WARNING):
        token, fehler = await _get_token("name@example.com", "geheim")

    assert token == "ID-456"
    assert fehler is None
    # Der abgekündigte Weg darf nicht still wirken — sonst erfährt niemand
    # davon, bis gridX die Gnadenfrist beendet.
    assert any("access_token" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_ohne_jeden_token_nennt_den_grund(monkeypatch):
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"token_type": "Bearer"})

    _mock_transport(monkeypatch, handler)
    token, fehler = await _get_token("name@example.com", "geheim")

    assert token is None
    assert fehler and "access_token" in fehler


# --- #410 / Fehlerpfad: der Grund statt einer Behauptung ---------------------

def test_auth_fehlertext_reicht_auth0_begruendung_durch():
    resp = httpx.Response(
        403,
        json={"error": "invalid_request", "error_description": "Service not found: my.gridx"},
    )
    text = _auth_fehlertext(resp)
    assert "403" in text
    assert "Service not found: my.gridx" in text


def test_auth_fehlertext_ohne_json_bleibt_bei_der_nummer():
    resp = httpx.Response(502, text="<html>bad gateway</html>")
    assert _auth_fehlertext(resp) == "HTTP 502"


@pytest.mark.asyncio
async def test_test_connection_nennt_den_grund_statt_das_passwort(monkeypatch):
    # Regression zu #410: Vorher meldete eedc JEDEN Fehlschlag als
    # „E-Mail/Passwort prüfen" — auch wenn Realm oder Audience abgelehnt
    # wurden und die Zugangsdaten stimmten.
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401,
            json={"error": "invalid_grant", "error_description": "Wrong email or password."},
        )

    _mock_transport(monkeypatch, handler)
    result = await ViessmannGridBoxProvider().test_connection(
        {"username": "name@example.com", "password": "geheim"},
    )

    assert result.erfolg is False
    assert "Wrong email or password." in result.fehler
    assert "401" in result.fehler


def test_anleitung_nennt_den_lebenden_anmeldeweg():
    # Die GridBox ist zum 31.12.2025 samt Daten zu E.ON Home gewechselt; der
    # Viessmann-Realm ist abgeschaltet. Bis #410 wies eedc den Anwender an
    # `mygridbox.viessmann.com` — eine Adresse, an der er sich nicht mehr
    # anmelden kann, während der Fehlschlag ihm sein Passwort vorwarf.
    info = ViessmannGridBoxProvider().info()
    text = f"{info.name} {info.beschreibung} {info.anleitung}"
    assert "eon.gridx.de/login" in text
    assert "mygridbox" not in text
    # Beide Namen müssen auffindbar bleiben — der Anwender sucht nach dem,
    # was auf seinem Gerät steht.
    assert "Viessmann" in info.name and "E.ON Home" in info.name
