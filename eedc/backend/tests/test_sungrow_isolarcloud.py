"""Tests für den Sungrow iSolarCloud Cloud-Import-Provider (#287).

Deckt ab:
- Provider-Metadaten (Felder, Pflicht/Optional, Registrierung).
- AppKey-Resolver (A+B-Strategie nach #287): Default aus GoSungrow-Stand,
  optionales User-Feld mit Whitespace/None-Toleranz.
- Header-Aufbau (`x-access-key` parametrisiert, `sys_code: 901`).
- Hilfsfunktionen `_safe_float` / `_extract_kwh` für die robusten
  Feldname-Varianten zwischen Hybrid- und PV-only-Anlagen.
"""

from __future__ import annotations

from backend.services.cloud_import import get_provider, list_providers
from backend.services.cloud_import.sungrow_isolarcloud import (
    DEFAULT_APPKEY,
    SungrowISolarCloudProvider,
    _extract_kwh,
    _make_headers,
    _resolve_appkey,
    _safe_float,
)


# --- Provider-Metadaten + Registry ------------------------------------------

def test_info_metadaten():
    info = SungrowISolarCloudProvider().info()
    assert info.id == "sungrow_isolarcloud"
    assert info.hersteller == "Sungrow"
    # Provider ist noch nicht mit echtem Gerät verifiziert (detlefh68 als
    # Tester offen — #287).
    assert info.getestet is False

    by_id = {f.id: f for f in info.credential_fields}
    assert set(by_id) == {"account", "password", "region", "appkey"}
    # account/password/region: Pflichtfelder für den Reverse-API-Pfad.
    assert by_id["account"].required is True
    assert by_id["password"].required is True
    assert by_id["password"].type == "password"
    assert by_id["region"].required is True
    # appkey ist der Power-User-Override für die Sungrow-AppKey-Rotation.
    assert by_id["appkey"].required is False


def test_provider_ist_registriert():
    provider = get_provider("sungrow_isolarcloud")
    assert isinstance(provider, SungrowISolarCloudProvider)
    assert "sungrow_isolarcloud" in {p.id for p in list_providers()}


def test_region_options_decken_eu_und_global_ab():
    info = SungrowISolarCloudProvider().info()
    region = next(f for f in info.credential_fields if f.id == "region")
    werte = {opt["value"] for opt in region.options}
    # EU ist der für deutsche Anwender relevante Default-Pfad.
    assert {"eu", "global"}.issubset(werte)


# --- AppKey-Resolver --------------------------------------------------------

def test_default_appkey_entspricht_gosungrow_stand():
    # Regression-Schutz: Wenn jemand den Default ohne Doku-Update ändert,
    # schlägt der Test fehl und zwingt zur Recherche der aktuellen Quelle.
    # Stand 2026-05: GoSungrow v3.0.7 (Sep 2023, seit ~2 Jahren stabil).
    assert DEFAULT_APPKEY == "93D72E60331ABDCDC7B39ADC2D1F32B3"


def test_resolve_appkey_ohne_user_wert_nutzt_default():
    assert _resolve_appkey({}) == DEFAULT_APPKEY
    assert _resolve_appkey({"appkey": None}) == DEFAULT_APPKEY
    assert _resolve_appkey({"appkey": ""}) == DEFAULT_APPKEY


def test_resolve_appkey_whitespace_zaehlt_als_leer():
    # Anwender pflegt Whitespace-only (z. B. durch versehentliches
    # Leerzeichen-Copy aus Browser) → Default greift, nicht der leere Wert.
    # Bezug: feedback_credential_whitespace.md.
    assert _resolve_appkey({"appkey": "   "}) == DEFAULT_APPKEY
    assert _resolve_appkey({"appkey": "\t\n"}) == DEFAULT_APPKEY


def test_resolve_appkey_user_wert_gewinnt_und_wird_getrimmt():
    assert _resolve_appkey({"appkey": "CUSTOMKEY"}) == "CUSTOMKEY"
    # Umgebende Whitespace wird abgeschnitten — sonst rejected die API mit
    # `Illegal c-access-key` aus reinen Trim-Gründen.
    assert _resolve_appkey({"appkey": "  CUSTOMKEY  "}) == "CUSTOMKEY"


# --- Header-Aufbau ----------------------------------------------------------

def test_make_headers_setzt_resolved_appkey():
    headers = _make_headers("MYKEY")
    assert headers["x-access-key"] == "MYKEY"
    # `sys_code: 901` ist die in den Reverse-Clients dokumentierte
    # Sungrow-System-ID — fehlt sie, antwortet die API mit Auth-Fehler.
    assert headers["sys_code"] == "901"
    assert headers["Content-Type"] == "application/json"
    assert headers["Accept"] == "application/json"


def test_make_headers_unterscheidet_default_und_user():
    default_headers = _make_headers(_resolve_appkey({}))
    user_headers = _make_headers(_resolve_appkey({"appkey": "ALT"}))
    assert default_headers["x-access-key"] == DEFAULT_APPKEY
    assert user_headers["x-access-key"] == "ALT"


# --- _safe_float -----------------------------------------------------------

def test_safe_float_sentinels_werden_zu_none():
    # iSolarCloud liefert mehrere Sentinel-Werte für „kein Wert"; alle
    # müssen einheitlich auf None mappen, sonst landen 0-/Müll-Zahlen in
    # ParsedMonthData.
    assert _safe_float(None) is None
    assert _safe_float("") is None
    assert _safe_float("--") is None
    assert _safe_float("null") is None


def test_safe_float_negative_werden_zu_none():
    # Negative kWh-Werte sind in Monatsaggregaten immer ein Datenfehler.
    assert _safe_float(-1.0) is None
    assert _safe_float("-5.2") is None


def test_safe_float_gueltige_werte_kommen_durch():
    assert _safe_float(0) == 0.0
    assert _safe_float("12.34") == 12.34
    assert _safe_float(100) == 100.0


def test_safe_float_unparsbar_wird_zu_none():
    assert _safe_float("nicht eine zahl") is None
    assert _safe_float([]) is None


# --- _extract_kwh ----------------------------------------------------------

def test_extract_kwh_erster_treffer_gewinnt():
    # Hybrid-Anlagen liefern `p83022`, PV-only-Anlagen `total_pv_energy`
    # — beide Pfade müssen denselben kWh-Wert produzieren.
    data = {"p83022": "100.5", "total_pv_energy": "999"}
    assert _extract_kwh(data, "p83022", "total_pv_energy") == 100.5


def test_extract_kwh_faellt_auf_naechsten_schluessel_durch():
    data = {"p83022": "--", "total_pv_energy": "42.0"}
    # `p83022` ist Sentinel → nächster Schlüssel zieht.
    assert _extract_kwh(data, "p83022", "total_pv_energy") == 42.0


def test_extract_kwh_alle_leer_liefert_none():
    data = {"p83022": None, "total_pv_energy": "null"}
    assert _extract_kwh(data, "p83022", "total_pv_energy") is None


def test_extract_kwh_unbekannte_schluessel_liefern_none():
    # Wenn die API ein unbekanntes Feldname-Schema benutzt, fällt der
    # Wert sauber durch — kein Crash, ParsedMonthData kriegt None.
    assert _extract_kwh({"andere_keys": 100}, "p83022", "total_pv_energy") is None
