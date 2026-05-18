"""
Akzeptanztest: Cloud-Credentials-Maskierung in GET /credentials/{anlage_id}.

Vor dem Fix maskierte der Endpoint nur drei Felder hartcodiert
(`secret_key`, `password`, `token`). Provider-spezifische Geheimnisse wie
`api_key` (SolarEdge), `app_secret` (Deye Solarman), `access_key_value`
(Fronius Solar.web) oder `system_code` (Huawei FusionSolar) blieben Klartext.

Der Fix nutzt zwei Mechanismen:
  1. Provider-aware: Felder mit `CredentialField(type="password")` werden
     maskiert (Quelle der Wahrheit pro Provider).
  2. Heuristik-Fallback für unbekannte/entfernte Provider: Substring-Match
     im Key auf `secret`, `password`, `token`, `api_key`, `access_key`,
     `private_key`, `app_secret`, `client_secret`, `system_code`.

Identifier (`username`, `email`, `site_id`, `region`, ...) bleiben lesbar.

Self-contained:

    eedc/backend/venv/bin/python eedc/backend/tests/test_cloud_credentials_maskierung.py
"""

from __future__ import annotations

import sys
import traceback
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[2]  # eedc/
sys.path.insert(0, str(_BACKEND_ROOT))

from backend.api.routes.cloud_import import _maskiere_credentials  # noqa: E402


# ----------------------------------------------------------------------------
# Provider-aware Maskierung (type="password")
# ----------------------------------------------------------------------------

def test_solaredge_api_key_wird_maskiert() -> None:
    """Tom-HA-Hinweis: SolarEdge api_key war vorher Klartext, jetzt maskiert."""
    creds = {"api_key": "abc123secret", "site_id": "1234567"}
    result = _maskiere_credentials(creds, provider_id="solaredge")
    assert result["api_key"] == "***", f"api_key sollte maskiert sein, got {result}"
    assert result["site_id"] == "1234567", "site_id ist kein Geheimnis, bleibt Klartext"


def test_deye_app_secret_wird_maskiert() -> None:
    """Deye Solarman: app_secret (type=password) + app_id (type=text)."""
    creds = {"app_id": "12345", "app_secret": "top-secret-app", "email": "user@example.com", "password": "abc"}
    result = _maskiere_credentials(creds, provider_id="deye_solarman")
    assert result["app_secret"] == "***"
    assert result["password"] == "***"
    assert result["app_id"] == "12345"
    assert result["email"] == "user@example.com"


def test_fronius_access_key_value_wird_maskiert() -> None:
    """Fronius Solar.web: access_key_value ist Password-Feld, access_key_id ist Identifier."""
    creds = {"access_key_id": "ID-PUBLIC-ABC", "access_key_value": "geheim", "pv_system_id": "sys-1"}
    result = _maskiere_credentials(creds, provider_id="fronius_solarweb")
    assert result["access_key_value"] == "***"
    assert result["access_key_id"] == "***", "access_key Substring-Heuristik schlägt auch hier zu (defense)"
    assert result["pv_system_id"] == "sys-1"


def test_huawei_system_code_wird_maskiert() -> None:
    """Huawei FusionSolar: system_code ist Password-Typ."""
    creds = {"username": "user@example.com", "system_code": "PWD123", "station_code": "STA456"}
    result = _maskiere_credentials(creds, provider_id="huawei_fusionsolar")
    assert result["system_code"] == "***"
    assert result["username"] == "user@example.com"
    assert result["station_code"] == "STA456"


# ----------------------------------------------------------------------------
# Heuristik-Fallback (unbekannter Provider)
# ----------------------------------------------------------------------------

def test_unbekannter_provider_maskiert_sensible_keys_per_heuristik() -> None:
    """Wenn Provider nicht aufgelöst werden kann, Substring-Heuristik schützt."""
    creds = {
        "api_key": "abc",
        "client_secret": "geheim",
        "private_key": "-----BEGIN RSA",
        "bearer_token": "eyJ...",
        "username": "u",
        "endpoint": "https://api.example.com",
    }
    result = _maskiere_credentials(creds, provider_id="nonexistent-provider-id")
    assert result["api_key"] == "***"
    assert result["client_secret"] == "***"
    assert result["private_key"] == "***"
    assert result["bearer_token"] == "***", "Substring 'token' matched"
    assert result["username"] == "u"
    assert result["endpoint"] == "https://api.example.com"


def test_kein_provider_id_immer_noch_heuristik() -> None:
    """provider_id=None: Heuristik schützt weiterhin."""
    creds = {"password": "secret123", "username": "u"}
    result = _maskiere_credentials(creds, provider_id=None)
    assert result["password"] == "***"
    assert result["username"] == "u"


# ----------------------------------------------------------------------------
# Identifier bleiben lesbar
# ----------------------------------------------------------------------------

def test_identifier_bleiben_klartext() -> None:
    """username/email/site_id/region/server/endpoint sind keine Geheimnisse."""
    creds = {
        "username": "alice",
        "email": "alice@example.com",
        "site_id": "12345",
        "station_id": "98765",
        "plant_id": "55",
        "region": "eu1",
        "server": "https://api.example.com",
        "account": "acc-1",
    }
    result = _maskiere_credentials(creds, provider_id="growatt")
    for key in ("username", "email", "site_id", "station_id", "plant_id", "region", "server", "account"):
        if key in result:
            assert result[key] != "***", f"{key} sollte Klartext sein, ist maskiert"


# ----------------------------------------------------------------------------
# Empty/None werden weggelassen
# ----------------------------------------------------------------------------

def test_leere_werte_werden_weggelassen() -> None:
    """None und leere Strings tauchen nicht im Output auf — sauberer fürs Frontend."""
    creds = {"api_key": "abc", "site_id": None, "username": ""}
    result = _maskiere_credentials(creds, provider_id="solaredge")
    assert "site_id" not in result
    assert "username" not in result
    assert result["api_key"] == "***"


def test_leere_credentials_dict_liefert_leeres_dict() -> None:
    result = _maskiere_credentials({}, provider_id="solaredge")
    assert result == {}


# ----------------------------------------------------------------------------
# Runner
# ----------------------------------------------------------------------------

ALLE_TESTS = [
    test_solaredge_api_key_wird_maskiert,
    test_deye_app_secret_wird_maskiert,
    test_fronius_access_key_value_wird_maskiert,
    test_huawei_system_code_wird_maskiert,
    test_unbekannter_provider_maskiert_sensible_keys_per_heuristik,
    test_kein_provider_id_immer_noch_heuristik,
    test_identifier_bleiben_klartext,
    test_leere_werte_werden_weggelassen,
    test_leere_credentials_dict_liefert_leeres_dict,
]


def main() -> int:
    fehler = 0
    for fn in ALLE_TESTS:
        try:
            fn()
            print(f"PASS  {fn.__name__}")
        except Exception:  # noqa: BLE001
            fehler += 1
            print(f"FAIL  {fn.__name__}")
            traceback.print_exc()
    if fehler:
        print(f"\n{fehler} Tests fehlgeschlagen.")
        return 1
    print(f"\nAlle {len(ALLE_TESTS)} Tests grün.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
