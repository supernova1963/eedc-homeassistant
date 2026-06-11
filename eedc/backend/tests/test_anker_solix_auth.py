"""Tests für den Anker SOLIX Cloud-Import-Provider — ECDH+AES-Login (#328).

Deckt ab:
- Provider-Metadaten (Felder, Registrierung, getestet=True seit Johnny-Gegentest #328).
- Krypto-Bausteine deterministisch: ECDH-Shared-Secret (P-256), AES-256-CBC-
  Passwort-Verschlüsselung (IV = Secret[:16], PKCS7, Base64), gtoken=MD5(user_id).
- Login-Payload-Aufbau (enc=0, Public-Key unkomprimiert hex, kein MD5²-Legacy).
- Header-Aufbau (`app-name: anker_power`, `x-auth-token`, `gtoken`).
- Credential-Trim (feedback_credential_whitespace).
- Monats-Fenster TAG-INKLUSIV (feedback_cloud_api_fenster_semantik, EcoFlow-Lehre).
- Fehlerpfade: HTTP 401/429, Anker-Fehlercodes → klare UI-Meldung.
- Voller Login-Flow gegen gemockten HTTP-Transport.

Der echte Login ist lokal NICHT verifizierbar (kein Anker-Konto) — die
Verifikation läuft über Johnnys Gegentest nach dem Release.
"""

from __future__ import annotations

import base64
import hashlib
import json

import httpx
import pytest
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from backend.services.cloud_import import anker_solix, get_provider, list_providers
from backend.services.cloud_import.anker_solix import (
    ANKER_SERVER_PUBLIC_KEY_HEX,
    AnkerSolixProvider,
    _auth_headers,
    _build_login_payload,
    _check_response,
    _compute_shared_secret,
    _default_headers,
    _encrypt_password,
    _generate_ecdh_keypair,
    _get_energy_analysis,
    _gtoken,
    _login,
    _month_window,
    _parse_month_response,
    _public_key_hex,
    _safe_float,
    _trimmed_credentials,
)


# --- Provider-Metadaten + Registry ------------------------------------------

def test_info_metadaten():
    info = AnkerSolixProvider().info()
    assert info.id == "anker_solix"
    assert info.hersteller == "Anker"
    # Validiert am echten Gerät (Johnny_1993, #328, 2026-06-11).
    assert info.getestet is True

    by_id = {f.id: f for f in info.credential_fields}
    assert set(by_id) == {"email", "password", "server"}
    assert by_id["password"].type == "password"


def test_provider_ist_registriert():
    provider = get_provider("anker_solix")
    assert isinstance(provider, AnkerSolixProvider)
    assert "anker_solix" in {p.id for p in list_providers()}


# --- ECDH-Schlüsselaustausch -------------------------------------------------

def test_server_public_key_format():
    # Unkomprimiertes X9.62-Format: 0x04 + 32 Byte X + 32 Byte Y = 65 Byte.
    raw = bytes.fromhex(ANKER_SERVER_PUBLIC_KEY_HEX)
    assert len(raw) == 65
    assert raw[0] == 0x04
    # Muss ein gültiger Punkt auf P-256 sein, sonst wirft from_encoded_point.
    ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), raw)


def test_public_key_hex_format():
    private_key = _generate_ecdh_keypair()
    hex_key = _public_key_hex(private_key)
    # 65 Byte hex-kodiert = 130 Zeichen, Prefix 04 (unkomprimiert).
    assert len(hex_key) == 130
    assert hex_key.startswith("04")


def test_shared_secret_deterministisch():
    # Festes Schlüsselpaar → Shared Secret mit dem Anker-Server-Key ist
    # reproduzierbar. Pinnt den ECDH-Pfad gegen stille Algorithmus-Drift.
    private_key = ec.derive_private_key(0x1234567890ABCDEF, ec.SECP256R1())
    secret = _compute_shared_secret(private_key)
    assert len(secret) == 32
    assert secret.hex() == (
        "3c6731158b7f24267c7fde2c86f2f7ccfd39cdf456ce239afbfb5c90d0a14ce4"
    )


def test_shared_secret_symmetrisch():
    # ECDH-Grundeigenschaft: beide Seiten berechnen dasselbe Secret.
    client_key = _generate_ecdh_keypair()
    server_key = _generate_ecdh_keypair()
    server_pub_hex = _public_key_hex(server_key)
    vom_client = _compute_shared_secret(client_key, server_pub_hex)
    vom_server = server_key.exchange(ec.ECDH(), client_key.public_key())
    assert vom_client == vom_server


# --- AES-Passwort-Verschlüsselung --------------------------------------------

def test_encrypt_password_deterministisch():
    # Bekanntes Secret → bekanntes Chiffrat. Schlägt fehl, wenn jemand IV,
    # Padding oder Encoding ändert — genau das würde den Anker-Login brechen.
    secret = bytes(range(32))
    assert _encrypt_password("geheim123", secret) == "Z6fqgCFc1Rg10GrqOUr23w=="


def test_encrypt_password_roundtrip():
    # Gegenprobe: Entschlüsseln mit AES-256-CBC (IV = Secret[:16]) + PKCS7
    # liefert das Klartext-Passwort zurück.
    secret = hashlib.sha256(b"testsecret").digest()
    encrypted = _encrypt_password("MeinPasswort!äöü", secret)
    cipher = Cipher(algorithms.AES(secret), modes.CBC(secret[:16]))
    decryptor = cipher.decryptor()
    unpadder = padding.PKCS7(128).unpadder()
    decrypted = decryptor.update(base64.b64decode(encrypted)) + decryptor.finalize()
    plain = unpadder.update(decrypted) + unpadder.finalize()
    assert plain.decode("utf-8") == "MeinPasswort!äöü"


def test_gtoken_ist_md5_der_user_id():
    assert _gtoken("user123") == hashlib.md5(b"user123").hexdigest()


# --- Login-Payload ------------------------------------------------------------

def test_login_payload_aufbau():
    private_key = _generate_ecdh_keypair()
    payload = _build_login_payload("name@example.com", "geheim", private_key)

    assert payload["enc"] == 0
    assert payload["email"] == "name@example.com"
    assert payload["client_secret_info"]["public_key"] == _public_key_hex(private_key)
    # transaction = Unix-Timestamp in ms als String
    assert payload["transaction"].isdigit()
    assert isinstance(payload["time_zone"], int)

    # Passwort ist verschlüsselt — weder Klartext noch das alte MD5²-Schema.
    legacy_md5 = hashlib.md5(
        hashlib.md5(b"geheim").hexdigest().encode()
    ).hexdigest()
    assert payload["password"] != "geheim"
    assert payload["password"] != legacy_md5
    # Base64-dekodierbar und AES-Block-aligned.
    assert len(base64.b64decode(payload["password"])) % 16 == 0


# --- Header-Aufbau -------------------------------------------------------------

def test_default_headers_pflichtfelder():
    headers = _default_headers()
    # `app-name: anker_power` ist Pflicht — ohne lehnt die API ab.
    assert headers["App-Name"] == "anker_power"
    assert headers["Model-Type"] == "DESKTOP"
    assert headers["Os-Type"] == "android"
    # Timezone im Anker-Format 'GMT+01:00'
    assert headers["Timezone"].startswith("GMT")


def test_auth_headers_token_und_gtoken():
    headers = _auth_headers("TOKEN123", "user-42")
    assert headers["x-auth-token"] == "TOKEN123"
    # gtoken ist MD5(user_id) — NICHT mehr das auth_token (Alt-Schema).
    assert headers["gtoken"] == hashlib.md5(b"user-42").hexdigest()
    assert headers["gtoken"] != "TOKEN123"


# --- Credential-Trim ------------------------------------------------------------

def test_credentials_werden_getrimmt():
    # Copy-Paste aus Portalen bringt Whitespace mit — die API meldet dann
    # „falsches Passwort". Bezug: feedback_credential_whitespace.md.
    email, password, server = _trimmed_credentials(
        {"email": "  name@example.com\n", "password": "\tgeheim ", "server": " eu "}
    )
    assert email == "name@example.com"
    assert password == "geheim"
    assert server == "eu"


def test_credentials_fehlende_werte_werden_leer():
    email, password, server = _trimmed_credentials({})
    assert email == ""
    assert password == ""
    assert server == "eu"  # Default-Region


# --- Monats-Fenster (tag-inklusiv) ----------------------------------------------

def test_month_window_ist_tag_inklusiv():
    # Die Anker-API liefert BEIDE Randtage mit (EcoFlow-Lehre: halboffenes
    # Fenster angenommen → Import zu hoch). end muss der letzte Monatstag
    # sein, nicht der 1. des Folgemonats.
    assert _month_window(2026, 1) == ("2026-01-01", "2026-01-31")
    assert _month_window(2026, 4) == ("2026-04-01", "2026-04-30")
    assert _month_window(2026, 12) == ("2026-12-01", "2026-12-31")


def test_month_window_schaltjahr():
    assert _month_window(2024, 2) == ("2024-02-01", "2024-02-29")
    assert _month_window(2023, 2) == ("2023-02-01", "2023-02-28")


# --- Fehlerpfade ------------------------------------------------------------------

def test_check_response_401_klare_meldung():
    with pytest.raises(Exception, match="Zugangsdaten"):
        _check_response(401, {}, "Anker-Login fehlgeschlagen")


def test_check_response_429_rate_limit():
    with pytest.raises(Exception, match="Zu viele Anfragen"):
        _check_response(429, {}, "Energiedaten abrufen fehlgeschlagen")


def test_check_response_bekannter_api_code_mit_hinweis():
    # 26108 = InvalidCredentials → Anwender-taugliche Meldung statt Roh-Code.
    with pytest.raises(Exception, match="E-Mail oder Passwort"):
        _check_response(
            200, {"code": 26108, "msg": "incorrect password"}, "Anker-Login"
        )


def test_check_response_unbekannter_code_mit_msg():
    # Unbekannte Codes reichen die API-msg durch — kein silent except.
    with pytest.raises(Exception, match=r"strange error \(Code 77777\)"):
        _check_response(200, {"code": 77777, "msg": "strange error"}, "Kontext")


def test_check_response_erfolg_liefert_data():
    data = _check_response(200, {"code": 0, "data": {"x": 1}}, "Kontext")
    assert data == {"x": 1}


# --- Monats-Parsing ------------------------------------------------------------------

def _solar_response() -> dict:
    """energy_analysis-Response devType solar_production."""
    return {
        "power": [
            {"time": "2026-04-01", "value": "3.67"},
            {"time": "2026-04-02", "value": "3.29"},
            {"time": "2026-04-03", "value": "0.55"},
        ],
        # power_unit behauptet 'wh', Werte sind aber kWh (API-Eigenheit)
        "power_unit": "wh",
        "solar_to_grid_total": "1.50",
        "solar_to_home_total": "4.00",
        "solar_to_battery_total": "2.01",
        "solar_total": "7.51",
    }


def _home_response() -> dict:
    """energy_analysis-Response devType home_usage (Netzbezug + Entladung)."""
    return {
        "grid_to_home_total": "5.20",
        "battery_to_home_total": "3.11",
    }


def _battery_response() -> dict:
    """energy_analysis-Response devType solarbank (Netz-Ladung der Batterie)."""
    return {
        "grid_to_battery_total": "0.50",
    }


def test_parse_month_summiert_tageswerte():
    result = _parse_month_response(
        _solar_response(), _home_response(), _battery_response(), 2026, 4
    )
    assert result is not None
    assert result.jahr == 2026
    assert result.monat == 4
    assert result.pv_erzeugung_kwh == 7.51  # 3.67 + 3.29 + 0.55
    assert result.einspeisung_kwh == 1.50
    # #328: Netzbezug aus home_usage.grid_to_home_total
    assert result.netzbezug_kwh == 5.20
    # #328: Ladung = solar_to_battery (2.01) + grid_to_battery (0.50)
    assert result.batterie_ladung_kwh == 2.51
    # #328: Entladung = home_usage.battery_to_home_total
    assert result.batterie_entladung_kwh == 3.11
    # Eigenverbrauch = solar_to_home + solar_to_battery
    assert result.eigenverbrauch_kwh == 6.01


def test_parse_month_eigenverbrauch_fallback_pv_minus_einspeisung():
    solar = _solar_response()
    solar["solar_to_home_total"] = ""
    solar["solar_to_battery_total"] = ""
    result = _parse_month_response(solar, _home_response(), {}, 2026, 4)
    assert result.eigenverbrauch_kwh == 6.01  # 7.51 − 1.50


def test_parse_month_pv_fallback_auf_solar_total():
    solar = _solar_response()
    solar["power"] = []
    result = _parse_month_response(solar, {}, {}, 2026, 4)
    assert result.pv_erzeugung_kwh == 7.51


def test_parse_month_nur_solar_ohne_home_und_battery():
    """home_usage/solarbank dürfen fehlen (Anlage ohne Speicher/Netzbezug)."""
    result = _parse_month_response(_solar_response(), {}, {}, 2026, 4)
    assert result is not None
    assert result.pv_erzeugung_kwh == 7.51
    assert result.netzbezug_kwh is None
    # Ladung nur aus solar_to_battery, Entladung unbekannt
    assert result.batterie_ladung_kwh == 2.01
    assert result.batterie_entladung_kwh is None


def test_parse_month_leere_response_liefert_none():
    assert _parse_month_response({}, {}, {}, 2026, 4) is None
    assert _parse_month_response(
        {"power": [], "solar_total": ""}, {}, {}, 2026, 4
    ) is None


# --- _safe_float -----------------------------------------------------------------------

def test_safe_float_sentinels_und_negative():
    assert _safe_float(None) is None
    assert _safe_float("") is None
    assert _safe_float("null") is None
    assert _safe_float(-1.0) is None
    assert _safe_float("12.34") == 12.34
    assert _safe_float(0) == 0.0


# --- Voller Login-Flow gegen gemockten Transport ------------------------------------------

@pytest.mark.asyncio
async def test_login_flow_gemockt():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "code": 0,
                "msg": "success!",
                "data": {"auth_token": "TOKEN-ABC", "user_id": "uid-007"},
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        token, user_id = await _login(
            client, "https://ankerpower-api-eu.anker.com",
            "name@example.com", "geheim",
        )

    assert token == "TOKEN-ABC"
    assert user_id == "uid-007"
    assert captured["url"].endswith("/passport/login")
    payload = captured["payload"]
    # ECDH-Public-Key wird mitgeschickt, Passwort verschlüsselt (kein MD5²).
    assert len(payload["client_secret_info"]["public_key"]) == 130
    assert payload["enc"] == 0
    assert payload["password"] != "geheim"
    assert len(payload["password"]) != 32  # MD5-Hex wäre exakt 32 Zeichen


@pytest.mark.asyncio
async def test_energy_analysis_retry_bei_429(monkeypatch):
    """#328: transienter 429 → gestaffelter Retry, kein Bereich-Verlust."""
    # Retry-Delays auf 0 → kein echtes Warten im Test (delay=0 → kein sleep).
    monkeypatch.setattr(anker_solix, "RATE_LIMIT_RETRY_DELAYS_S", (0.0, 0.0))
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, json={"code": 429, "msg": "too many"})
        return httpx.Response(200, json={"code": 0, "data": {"solar_total": "5.0"}})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        result = await _get_energy_analysis(
            client, "https://ankerpower-api-eu.anker.com",
            "tok", "uid", "site", "2025-08-01", "2025-08-31",
            dev_type="solarbank",
        )
    assert calls["n"] == 2  # 1× 429, dann Erfolg
    assert result == {"solar_total": "5.0"}


@pytest.mark.asyncio
async def test_energy_analysis_429_dauerhaft_wirft(monkeypatch):
    """Bleibt es bei 429, wird nach allen Retries die klare Meldung geworfen."""
    monkeypatch.setattr(anker_solix, "RATE_LIMIT_RETRY_DELAYS_S", (0.0, 0.0))
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(429, json={"code": 429, "msg": "too many"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(Exception, match="429"):
            await _get_energy_analysis(
                client, "https://ankerpower-api-eu.anker.com",
                "tok", "uid", "site", "2025-08-01", "2025-08-31",
            )
    assert calls["n"] == 3  # Erstversuch + 2 Retries


@pytest.mark.asyncio
async def test_login_flow_falsches_passwort():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"code": 26108, "msg": "incorrect password"}
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(Exception, match="E-Mail oder Passwort"):
            await _login(
                client, "https://ankerpower-api-eu.anker.com",
                "name@example.com", "falsch",
            )
