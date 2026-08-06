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

**Nachtrag 06.08.2026 (F-4) — beide Fixes trugen ins Leere.** OliS2811 meldete
nach dem Release von v4.0.9, dass der Import weiterhin scheitert, und legte
einen funktionierenden Referenz-Request daneben. Ursache: der Token wurde aus
einer `body`-Hülle gelesen, die Solarman nicht sendet. Es gab also nie einen
Token, den man mit `bearer` hätte senden können.
⚠ **Dieser Test war daran mitschuldig** — seine Fixture hatte die `body`-Hülle
selbst erfunden und damit die Annahme des Produktionscodes gegen sich selbst
geprüft. Woher die Formen jetzt stammen, steht bei den Fixtures.
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
    _nutzlast,
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


# ⚠ WOHER DIESE FORM STAMMT — die Frage, an der #349 gescheitert ist.
#
# Bis 05.08.2026 stand hier `{"success": True, "body": {"access_token": "TKN"}}`.
# Diese `body`-Hülle war **erfunden**: keine Quelle, nur die Annahme des
# Produktionscodes, gegen sich selbst geprüft. Die sieben rot verifizierten
# Proben von #349 liefen deshalb grün gegen eine API-Form, die es nicht gibt —
# und der Import scheiterte beim Melder trotzdem weiter.
#
# Die flache Form ist dreifach belegt: OliS2811s funktionierender
# Referenz-Request (#349-Kommentar 05.08.2026: `success: true` UND
# `access_token` als Geschwister), `mpepping/solarman-mqtt` und
# `hareeshmu/solarman` — beide lesen `data["access_token"]` flach.
TOKEN_OK = {"success": True, "requestId": "abc-123", "access_token": "TKN"}
STATION_OK = {"success": True, "name": "Ollis Anlage", "installedCapacity": 9.8}

# Die alte, erfundene Form. Sie steht hier NICHT als Beleg, sondern damit die
# Toleranz gegen sie geprüft ist: für `/station/*` liegt kein direkter Beleg
# vor, und der Provider soll an einer abweichenden Verpackung nicht scheitern.
TOKEN_OK_IN_BODY = {"success": True, "body": {"access_token": "TKN"}}


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
            "stationDataItems": [
                {"year": 2026, "month": 3, "generationValue": 412.5},
            ],
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
        return _json({"success": True, "stationDataItems": []})

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
                "stationDataItems": [
                    {"year": 2025, "month": 6, "generationValue": 500.0},
                ],
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


# --- Antwortform (F-4, OliS2811 05.08.2026) ----------------------------------

def test_nutzlast_liest_flach_und_body_fuellt_nur_luecken():
    """Einheiten-Beleg für die Vorrang-Regel aus `_nutzlast`."""
    assert _nutzlast({"success": True, "access_token": "FLACH"})["access_token"] == "FLACH"
    assert _nutzlast({"success": True, "body": {"access_token": "TIEF"}})["access_token"] == "TIEF"

    # Beide belegt ⇒ die flache Form gewinnt, sie ist die belegte.
    gemischt = {"success": True, "access_token": "FLACH", "body": {"access_token": "TIEF"}}
    assert _nutzlast(gemischt)["access_token"] == "FLACH"

    # `body` als Nicht-Objekt darf die Antwort nicht zerlegen.
    assert _nutzlast({"success": True, "body": None, "x": 1})["x"] == 1


async def test_token_steht_flach_neben_success(monkeypatch):
    """DER Beleg für F-4: genau diese Form liefert Solarman.

    Vor dem Fix las der Provider `data["body"]["access_token"]` — bei einer
    flachen Antwort also `None`. Der Verbindungstest schlug damit fehl, obwohl
    die Authentifizierung gelungen war.
    """
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return _json(TOKEN_OK)
        return _json(STATION_OK)

    _mock_httpx(monkeypatch, handler)
    result = await DeyeSolarmanProvider().test_connection(dict(CREDS))

    assert result.erfolg is True, result.fehler


async def test_die_von_olli_gemeldete_meldung_erscheint_bei_flacher_antwort_nicht(monkeypatch):
    """Regression auf den Wortlaut aus seinem #349-Kommentar.

    „Global + Klartext → Antwort enthielt keinen access_token" — dieser Satz
    war der Beweis, dass die Auth gelingt und nur das Auslesen scheitert.
    """
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return _json(TOKEN_OK)
        return _json(STATION_OK)

    _mock_httpx(monkeypatch, handler)
    result = await DeyeSolarmanProvider().test_connection(dict(CREDS))

    assert "access_token" not in (result.fehler or "")


async def test_token_in_einer_body_huelle_wird_weiterhin_akzeptiert(monkeypatch):
    """Toleranz-Gegenprobe: eine abweichende Verpackung darf nicht scheitern.

    Für `/station/*` liegt kein direkter Beleg der Form vor — deshalb wird die
    ungemessene Annahme nicht gegen eine andere getauscht, sondern beides
    gelesen.
    """
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return _json(TOKEN_OK_IN_BODY)
        return _json(STATION_OK)

    _mock_httpx(monkeypatch, handler)
    result = await DeyeSolarmanProvider().test_connection(dict(CREDS))

    assert result.erfolg is True, result.fehler


async def test_stammdaten_der_anlage_werden_flach_gelesen(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return _json(TOKEN_OK)
        return _json(STATION_OK)

    _mock_httpx(monkeypatch, handler)
    result = await DeyeSolarmanProvider().test_connection(dict(CREDS))

    assert result.geraet_name == "Ollis Anlage"
    assert "9.8 kWp" in result.verfuegbare_daten


async def test_monatswerte_werden_flach_gelesen(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return _json(TOKEN_OK)
        return _json({
            "success": True,
            "stationDataItems": [
                {"year": 2026, "month": 3, "generationValue": 412.5},
            ],
        })

    _mock_httpx(monkeypatch, handler)
    result = await DeyeSolarmanProvider().fetch_monthly_data(dict(CREDS), 2026, 3, 2026, 3)

    assert [(m.jahr, m.monat, m.pv_erzeugung_kwh) for m in result] == [(2026, 3, 412.5)]


async def test_tokenanfrage_sendet_language_en(monkeypatch):
    """Deckungsgleich mit dem Request, von dem belegt ist, dass er durchgeht."""
    gesehen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            gesehen.append(str(request.url))
            return _json(TOKEN_OK)
        return _json(STATION_OK)

    _mock_httpx(monkeypatch, handler)
    await DeyeSolarmanProvider().test_connection(dict(CREDS))

    assert gesehen, "keine Token-Anfrage gesehen"
    assert "language=en" in gesehen[0]
    assert "appId=202301234567" in gesehen[0]
