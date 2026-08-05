"""Deye/Solarman: Server-Region und `bearer`-Präfix (#349, OliS2811).

Der Melder konnte den Cloud-Import nicht einrichten und nannte zwei
Verdachtsmomente. Am Code gemessen:

- **Region — bestätigt.** Der Host stand als Konstante `api.solarmanpv.com`
  (China) im Modul; ein europäisches Konto lebt auf `globalapi.solarmanpv.com`.
- **SHA256-Hash — widerlegt.** Das Passwort ging bereits als kleingeschriebener
  Hex-Digest raus; der Test hält das fest, damit es nicht „mit repariert" wird.

Dazu ein Defekt, der nicht im Issue stand: der `Authorization`-Header ging
**ohne** `bearer`-Präfix raus, das die Open API verlangt. Der Token wurde also
geholt und jeder fachliche Aufruf danach abgelehnt — auf beiden Regionen.

Und die Fehlerursache erreichte den Anwender nie: `_get_token` gab für
HTTP-Fehler, fachliche Ablehnung und Exception gleichermaßen `None` zurück,
die Oberfläche riet („Bitte appId, appSecret … prüfen").
"""

from __future__ import annotations

import hashlib
import json

import httpx
import pytest

from backend.services.cloud_import import deye_solarman
from backend.services.cloud_import.deye_solarman import (
    API_HOSTS,
    DEFAULT_REGION,
    DeyeSolarmanProvider,
    _auth_header,
    _resolve_host,
)

CREDS = {
    "app_id": "202301234567",
    "app_secret": "SECRET",
    "email": "olli@example.org",
    "password": "geheim",
    "station_id": "12345",
}


def _mock_httpx(monkeypatch, handler):
    """Ersetzt `httpx.AsyncClient` durch einen Client auf MockTransport.

    Der Provider baut seinen Client selbst (`httpx.AsyncClient(timeout=15)`),
    deshalb wird die Klasse getauscht statt ein Client hineingereicht.
    """

    class _Client(httpx.AsyncClient):
        def __init__(self, *args, **kwargs):
            kwargs.pop("timeout", None)
            super().__init__(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(deye_solarman.httpx, "AsyncClient", _Client)


def _json(payload: dict, status: int = 200) -> httpx.Response:
    return httpx.Response(status, json=payload)


TOKEN_OK = {"success": True, "body": {"access_token": "TKN"}}
STATION_OK = {
    "success": True,
    "body": {"name": "Ollis Anlage", "installedCapacity": 9.8},
}


# --- Metadaten ---------------------------------------------------------------

def test_region_feld_existiert_und_ist_ein_select():
    info = DeyeSolarmanProvider().info()
    by_id = {f.id: f for f in info.credential_fields}

    assert "region" in by_id, "ohne Regionsfeld ist ein EU-Konto nicht erreichbar"
    region = by_id["region"]
    assert region.type == "select"
    assert region.required is True
    assert [o["value"] for o in region.options] == ["global", "cn"]


def test_erste_option_ist_der_backend_default():
    """Der Wizard belegt ein Select mit `options[0].value` vor.

    Wichen Default und erste Option voneinander ab, schlüge das Formular still
    eine andere Region vor, als das Backend ohne Feld annimmt.
    """
    info = DeyeSolarmanProvider().info()
    region = next(f for f in info.credential_fields if f.id == "region")
    assert region.options[0]["value"] == DEFAULT_REGION


# --- Host-Auflösung ----------------------------------------------------------

@pytest.mark.parametrize(
    "region,erwartet",
    [
        ("global", "https://globalapi.solarmanpv.com"),
        ("cn", "https://api.solarmanpv.com"),
        (None, API_HOSTS[DEFAULT_REGION]),        # Bestand von vor #349
        ("", API_HOSTS[DEFAULT_REGION]),
        ("mars", API_HOSTS[DEFAULT_REGION]),      # unbekannter Wert
        ("  global  ", "https://globalapi.solarmanpv.com"),
    ],
)
def test_resolve_host(region, erwartet):
    creds = dict(CREDS)
    if region is not None:
        creds["region"] = region
    assert _resolve_host(creds) == erwartet


def test_auth_header_traegt_bearer_praefix():
    assert _auth_header("TKN") == {"Authorization": "bearer TKN"}


# --- Verbindungstest: Host + Header ------------------------------------------

async def test_ohne_region_spricht_der_test_den_globalen_host(monkeypatch):
    gesehen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        gesehen.append(str(request.url))
        if request.url.path.endswith("/token"):
            return _json(TOKEN_OK)
        return _json(STATION_OK)

    _mock_httpx(monkeypatch, handler)
    result = await DeyeSolarmanProvider().test_connection(dict(CREDS))

    assert result.erfolg is True
    assert all(u.startswith("https://globalapi.solarmanpv.com") for u in gesehen), gesehen


async def test_region_cn_spricht_den_chinesischen_host(monkeypatch):
    gesehen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        gesehen.append(str(request.url))
        if request.url.path.endswith("/token"):
            return _json(TOKEN_OK)
        return _json(STATION_OK)

    _mock_httpx(monkeypatch, handler)
    await DeyeSolarmanProvider().test_connection({**CREDS, "region": "cn"})

    assert all(u.startswith("https://api.solarmanpv.com") for u in gesehen), gesehen


async def test_stationsabruf_sendet_bearer(monkeypatch):
    kopfzeilen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return _json(TOKEN_OK)
        kopfzeilen["auth"] = request.headers.get("authorization", "")
        return _json(STATION_OK)

    _mock_httpx(monkeypatch, handler)
    result = await DeyeSolarmanProvider().test_connection(dict(CREDS))

    assert result.erfolg is True
    assert kopfzeilen["auth"] == "bearer TKN"


async def test_passwort_geht_als_kleiner_sha256_hex_digest(monkeypatch):
    """Gegenprobe: die zweite Vermutung aus #349 war am Code schon erfüllt."""
    gesendet: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            gesendet.update(json.loads(request.content))
            return _json(TOKEN_OK)
        return _json(STATION_OK)

    _mock_httpx(monkeypatch, handler)
    await DeyeSolarmanProvider().test_connection(dict(CREDS))

    assert gesendet["password"] == hashlib.sha256(b"geheim").hexdigest()
    assert gesendet["password"] == gesendet["password"].lower()


# --- Fehlertransparenz -------------------------------------------------------

async def test_tokenfehler_nennt_die_meldung_der_api(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return _json({"success": False, "msg": "auth invalid", "code": "A0001"})

    _mock_httpx(monkeypatch, handler)
    result = await DeyeSolarmanProvider().test_connection(dict(CREDS))

    assert result.erfolg is False
    assert "auth invalid" in result.fehler
    assert "A0001" in result.fehler
    # Der Host gehört dazu: bei falscher Region ist er die eigentliche Antwort.
    assert "globalapi.solarmanpv.com" in result.fehler


async def test_stationsfehler_nennt_die_meldung_der_api(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return _json(TOKEN_OK)
        return _json({"success": False, "msg": "station not found", "code": "S9"})

    _mock_httpx(monkeypatch, handler)
    result = await DeyeSolarmanProvider().test_connection(dict(CREDS))

    assert result.erfolg is False
    assert "station not found" in result.fehler
    # Der Code gehört dazu — er ist das, was man beim Hersteller nachschlägt.
    assert "S9" in result.fehler


async def test_http_fehler_nennt_status_und_koerper(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return _json(TOKEN_OK)
        return httpx.Response(403, text="Forbidden by region")

    _mock_httpx(monkeypatch, handler)
    result = await DeyeSolarmanProvider().test_connection(dict(CREDS))

    assert result.erfolg is False
    assert "403" in result.fehler
    assert "Forbidden by region" in result.fehler


# --- Import ------------------------------------------------------------------

async def test_import_sendet_bearer_an_die_gewaehlte_region(monkeypatch):
    gesehen: list[str] = []
    kopfzeilen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        gesehen.append(str(request.url))
        if request.url.path.endswith("/token"):
            return _json(TOKEN_OK)
        kopfzeilen.append(request.headers.get("authorization", ""))
        return _json({
            "success": True,
            "body": {"stationDataItems": [
                {"year": 2026, "month": 3, "generationValue": 412.5},
            ]},
        })

    _mock_httpx(monkeypatch, handler)
    result = await DeyeSolarmanProvider().fetch_monthly_data(
        {**CREDS, "region": "cn"}, 2026, 3, 2026, 3
    )

    assert [(m.jahr, m.monat, m.pv_erzeugung_kwh) for m in result] == [(2026, 3, 412.5)]
    assert kopfzeilen == ["bearer TKN"]
    assert all(u.startswith("https://api.solarmanpv.com") for u in gesehen), gesehen


async def test_zeitraum_zerfaellt_in_vorwaerts_laufende_bloecke(monkeypatch):
    """Die Blockrechnung darf kein Fenster erzeugen, das vor sich selbst endet.

    Bis #349 verlor `block_end_y` bei jedem Startmonat ≠ Januar ein Jahr: aus
    „ab Juni 2025, zwölf Monate" wurde als Blockende **Mai 2025**. Der
    Fortschaltschritt setzte `current` damit auf denselben Monat zurück — die
    Schleife lief endlos und befragte pro Runde die Hersteller-API. Ohne den
    `bearer`-Fix wäre nie ein Aufruf bis hierher gekommen.
    """
    fenster: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return _json(TOKEN_OK)
        koerper = json.loads(request.content)
        fenster.append((koerper["startTime"], koerper["endTime"]))
        return _json({"success": True, "body": {"stationDataItems": []}})

    _mock_httpx(monkeypatch, handler)
    await DeyeSolarmanProvider().fetch_monthly_data(
        dict(CREDS), 2025, 6, 2026, 6
    )

    assert fenster == [("2025-06-01", "2026-05-28"), ("2026-06-01", "2026-06-28")]
    for start, ende in fenster:
        assert start <= ende, f"Fenster endet vor seinem Anfang: {start} → {ende}"


async def test_import_ohne_ein_einziges_ergebnis_wirft_mit_grund(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return _json(TOKEN_OK)
        return _json({"success": False, "msg": "no permission for station"})

    _mock_httpx(monkeypatch, handler)
    with pytest.raises(Exception) as exc:
        await DeyeSolarmanProvider().fetch_monthly_data(dict(CREDS), 2026, 1, 2026, 3)

    assert "no permission for station" in str(exc.value)


async def test_teilergebnis_bleibt_erhalten_und_wirft_nicht(monkeypatch):
    """Gegenprobe: bricht die API erst im zweiten Block ab, zählt das Geholte."""
    aufrufe = {"history": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return _json(TOKEN_OK)
        aufrufe["history"] += 1
        if aufrufe["history"] == 1:
            return _json({
                "success": True,
                "body": {"stationDataItems": [
                    {"year": 2025, "month": 6, "generationValue": 500.0},
                ]},
            })
        return _json({"success": False, "msg": "rate limit"})

    _mock_httpx(monkeypatch, handler)
    result = await DeyeSolarmanProvider().fetch_monthly_data(
        dict(CREDS), 2025, 6, 2026, 6
    )

    assert [(m.jahr, m.monat) for m in result] == [(2025, 6)]


async def test_tokenfehler_beim_import_nennt_den_grund(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="appId unknown")

    _mock_httpx(monkeypatch, handler)
    with pytest.raises(Exception) as exc:
        await DeyeSolarmanProvider().fetch_monthly_data(dict(CREDS), 2026, 1, 2026, 1)

    assert "appId unknown" in str(exc.value)
