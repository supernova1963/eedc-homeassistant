"""Daten-Checker: eedc und Home Assistant in verschiedenen Zeitzonen (N-161).

eedc führt zwei Zeitwelten nebeneinander: 28 Backend-Stellen rechnen hart in
``ZoneInfo("Europe/Berlin")``, 85 nehmen die Systemzeit (``date.today()``).
Steht der Container auf der HA-Zeitzone, sind beide deckungsgleich. Steht er auf
UTC — dem Docker-Default ohne ``TZ`` —, driften sie **an der Tageskante**, also
genau dort, wo Tageszeilen entstehen. Gesetzt wird ``TZ`` im ganzen Projekt an
**einer** Stelle (``docker-compose.yml``); im Add-on steht dazu nichts.

Der Check meldet das, statt es zu heilen ([[feedback_kein_grosser_heiler_knopf]]).

**Warum Offset und nicht Zonenname:** Wien, Zürich und Amsterdam teilen sich
Berlins Offset. Ein Namensvergleich meldete dort einen Fehler, den es nicht
gibt.

⚠ **Woher die HA-Antwortform stammt** ([[feedback_fixture_fremde_api_braucht_quelle]],
Lehre aus F-4/#349): ``{"time_zone": "Europe/Berlin"}`` ist **nicht** geraten,
sondern am 2026-08-06 gegen eine echte Instanz gemessen —
``GET http://<ha>:8123/api/config`` mit Long-Lived-Token liefert ``time_zone``
als Feld der obersten Ebene. Derselbe Lauf hat den Check zweimal gegen diese
Instanz ausgeführt: bei gleicher Zeitzone schweigt er, mit simuliertem
UTC-Container meldet er „2 Stunden Unterschied". Eine nachgebaute
Hersteller-Antwort ohne Quelle prüft sonst nur die eigene Annahme gegen sich
selbst.

**Hermetik** ([[feedback_tests_ci_hermetisch]] — „auch die Uhr"): Der eigene
Offset wird nie als absolute Zahl gesetzt, sondern **relativ zur HA-Zone**
konstruiert. Sonst hinge das Ergebnis an der Sommerzeit: Berlin steht im Juli
auf UTC+2, im Januar auf UTC+1, und ein Test, der „2 Stunden Unterschied"
erwartet, wäre im Winter rot.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import httpx
import pytest

from backend.models.anlage import Anlage
from backend.services import ha_connection
from backend.services.daten_checker import CheckKategorie, CheckSeverity, DatenChecker
from backend.services.daten_checker import datenquelle as dq_mod


def _berlin_offset() -> timedelta:
    """Berlins Offset **jetzt** — Bezugspunkt für alle relativen Erwartungen."""
    return datetime.now(ZoneInfo("Europe/Berlin")).utcoffset()


def _ha_antwortet(monkeypatch, payload: dict, status: int = 200) -> None:
    """`httpx.AsyncClient` im Check-Modul durch MockTransport ersetzen."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/config")
        assert request.headers.get("Authorization") == "Bearer TOKEN"
        return httpx.Response(status, json=payload)

    class _Client(httpx.AsyncClient):
        def __init__(self, *args, **kwargs):
            kwargs.pop("timeout", None)
            super().__init__(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(dq_mod, "httpx", httpx)
    monkeypatch.setattr(dq_mod.httpx, "AsyncClient", _Client)


def _ha_verbindung(monkeypatch, *, kind: str | None) -> None:
    """`resolve_ha_connection` festlegen — `kind=None` heißt: keine Verbindung."""

    async def _resolve(_db):
        if kind is None:
            return (None, None, None)
        return ("http://ha.local:8123/api", "TOKEN", kind)

    monkeypatch.setattr(ha_connection, "resolve_ha_connection", _resolve)


def _eigener_offset(monkeypatch, offset: timedelta) -> None:
    monkeypatch.setattr(dq_mod, "_lokaler_utc_offset", lambda: offset)


async def _befunde(monkeypatch) -> list:
    checker = DatenChecker(db=object())
    return await checker._check_zeitzone_ha(Anlage(anlagenname="T"))


# ── Der Fall, für den der Check gebaut ist ─────────────────────────────────

async def test_abweichender_offset_wird_als_warnung_gemeldet(monkeypatch):
    _ha_verbindung(monkeypatch, kind=ha_connection.HA_CONNECTOR)
    _ha_antwortet(monkeypatch, {"time_zone": "Europe/Berlin"})
    _eigener_offset(monkeypatch, _berlin_offset() + timedelta(hours=2))

    befunde = await _befunde(monkeypatch)

    assert len(befunde) == 1
    b = befunde[0]
    assert b.kategorie == CheckKategorie.ZEITZONE_ABWEICHUNG.value
    assert b.schwere == CheckSeverity.WARNING.value
    assert "2 Stunden" in b.meldung
    assert "Europe/Berlin" in b.details
    # Der Hinweis muss auflösbar sein — Daten-Checker-Doktrin (P-6).
    assert b.link
    # Und er darf nicht behaupten, gespeicherte Tage würden mit repariert.
    assert "Bereits gespeicherte Tage ändern sich davon nicht" in b.details


async def test_container_auf_utc_wird_erkannt(monkeypatch):
    """Der reale Auslöser: Docker ohne `TZ` läuft auf UTC.

    Die Stundenzahl bleibt bewusst ungeprüft — sie ist im Sommer 2, im Winter 1.
    """
    _ha_verbindung(monkeypatch, kind=ha_connection.HA_CONNECTOR)
    _ha_antwortet(monkeypatch, {"time_zone": "Europe/Berlin"})
    _eigener_offset(monkeypatch, timedelta(0))

    befunde = await _befunde(monkeypatch)

    assert len(befunde) == 1
    assert "UTC+0" in befunde[0].details


# ── Die Fälle, in denen er schweigen muss ──────────────────────────────────

async def test_gleicher_offset_schweigt(monkeypatch):
    _ha_verbindung(monkeypatch, kind=ha_connection.HA_APP)
    _ha_antwortet(monkeypatch, {"time_zone": "Europe/Berlin"})
    _eigener_offset(monkeypatch, _berlin_offset())

    assert await _befunde(monkeypatch) == []


async def test_gleicher_offset_bei_anderem_zonennamen_schweigt(monkeypatch):
    """Wien ist nicht Berlin, aber es ist dieselbe Uhrzeit — kein Befund.

    Genau der Fehlalarm, den ein Namensvergleich erzeugt hätte.
    """
    _ha_verbindung(monkeypatch, kind=ha_connection.HA_APP)
    _ha_antwortet(monkeypatch, {"time_zone": "Europe/Vienna"})
    _eigener_offset(monkeypatch, _berlin_offset())

    assert await _befunde(monkeypatch) == []


async def test_ohne_ha_verbindung_wird_gar_nicht_erst_gefragt(monkeypatch):
    """Standalone ohne HA: nichts zu vergleichen, nichts zu tun — und **kein**
    HTTP-Versuch.

    ⚠ Zwei Fassungen blieben bei der Rot-Verifikation **stumm**, beide aus einem
    eigenen Grund:
    1. „Ergebnis leer" allein genügt nicht — ohne den Verbindungs-Guard läuft
       der Check in einen echten Netzwerkfehler und liefert ebenfalls `[]`:
       grün aus dem falschen Grund, mit einem echten Verbindungsversuch im
       Testlauf.
    2. Ein Client, der beim Bauen `AssertionError` wirft, hilft auch nicht — das
       breite `except Exception` des Checks (dort richtig: ein Check darf die
       Seite nicht killen) verschluckt ihn und liefert wieder `[]`.

    Deshalb **zählt** dieser Test den Aufruf, statt ihn zu sprengen: die
    Feststellung passiert außerhalb der Reichweite des Catch.
    """
    _ha_verbindung(monkeypatch, kind=None)
    aufrufe: list[str] = []

    class _Zaehlend(httpx.AsyncClient):
        def __init__(self, *args, **kwargs):
            aufrufe.append("gebaut")
            kwargs.pop("timeout", None)
            super().__init__(**kwargs)

    monkeypatch.setattr(dq_mod.httpx, "AsyncClient", _Zaehlend)

    assert await _befunde(monkeypatch) == []
    assert aufrufe == [], "ohne HA-Verbindung darf kein HTTP-Client gebaut werden"


async def test_ha_nicht_erreichbar_schweigt(monkeypatch):
    _ha_verbindung(monkeypatch, kind=ha_connection.HA_APP)
    _ha_antwortet(monkeypatch, {"error": "nope"}, status=503)
    _eigener_offset(monkeypatch, timedelta(0))

    assert await _befunde(monkeypatch) == []


async def test_unbekannte_zeitzone_schweigt(monkeypatch):
    """HA meldet etwas, das die Zonendatenbank nicht kennt ⇒ nichts behaupten."""
    _ha_verbindung(monkeypatch, kind=ha_connection.HA_APP)
    _ha_antwortet(monkeypatch, {"time_zone": "Mars/Olympus_Mons"})
    _eigener_offset(monkeypatch, timedelta(0))

    assert await _befunde(monkeypatch) == []


# ── Der Weg hängt am Betriebsmodus ─────────────────────────────────────────

async def test_addon_bekommt_den_addon_weg(monkeypatch):
    _ha_verbindung(monkeypatch, kind=ha_connection.HA_APP)
    _ha_antwortet(monkeypatch, {"time_zone": "Europe/Berlin"})
    _eigener_offset(monkeypatch, _berlin_offset() + timedelta(hours=3))

    details = (await _befunde(monkeypatch))[0].details

    assert "Add-on" in details
    assert "docker-compose" not in details


async def test_standalone_bekommt_die_umgebungsvariable(monkeypatch):
    _ha_verbindung(monkeypatch, kind=ha_connection.HA_CONNECTOR)
    _ha_antwortet(monkeypatch, {"time_zone": "Europe/Berlin"})
    _eigener_offset(monkeypatch, _berlin_offset() + timedelta(hours=3))

    details = (await _befunde(monkeypatch))[0].details

    assert "TZ=Europe/Berlin" in details
    assert "docker-compose.yml" in details
    assert "Add-on" not in details


# ── Formatierung ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("offset,erwartet", [
    (timedelta(0), "UTC+0"),
    (timedelta(hours=2), "UTC+2"),
    (timedelta(hours=-3), "UTC-3"),
    (timedelta(hours=5, minutes=30), "UTC+5:30"),
    (timedelta(hours=-3, minutes=-30), "UTC-3:30"),
])
def test_offset_text(offset, erwartet):
    """Halbe Stunden gibt es wirklich (Indien, Neufundland) — kein „UTC+5,5“."""
    assert dq_mod._offset_text(offset) == erwartet


def test_lokaler_offset_liefert_etwas():
    """Die Funktion, die im Test gesetzt wird, muss ungesetzt auch tragen."""
    assert isinstance(dq_mod._lokaler_utc_offset(), timedelta)


async def test_halbstunden_versatz_wird_lesbar_gemeldet(monkeypatch):
    """Indien gegen Berlin: 3,5 Stunden — die Zahl darf nicht ganzzahlig runden."""
    _ha_verbindung(monkeypatch, kind=ha_connection.HA_APP)
    _ha_antwortet(monkeypatch, {"time_zone": "Europe/Berlin"})
    _eigener_offset(monkeypatch, _berlin_offset() + timedelta(hours=3, minutes=30))

    assert "3,5 Stunden" in (await _befunde(monkeypatch))[0].meldung


def test_check_ist_in_check_anlage_eingehaengt():
    """Ohne diesen Beleg wäre der ganze Check unsichtbar löschbar.

    Alle Proben oben rufen `_check_zeitzone_ha` **direkt** auf — sie blieben
    grün, wenn die Zeile in `check_anlage` fehlte und der Anwender den Befund
    nie zu sehen bekäme. Quelltext-Prüfung wie in
    `test_konformitaet_prognose_felder.py`: `check_anlage` selbst zu fahren
    verlangt eine DB und alle übrigen Checks.
    """
    from pathlib import Path
    import backend.services.daten_checker as paket

    quelle = Path(paket.__file__).read_text(encoding="utf-8")
    assert "self._check_zeitzone_ha(anlage)" in quelle
