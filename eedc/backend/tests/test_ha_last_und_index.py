"""Wächter + Regressionen: was eedc Home Assistant an Last zumutet.

Auslöser (2026-08-03): Meldungen aus Discord, die HA-Oberfläche werde
unbedienbar, seit eedc als Add-on läuft — als externe Docker-Instanz laufe
alles normal. Die Vermutung im Kanal lautete „zu häufige MariaDB-Abfragen".
Die Erhebung fand drei Klassen, und die genannte war die kleinste:

1. **Voll-Dump statt gezieltem Abruf.** `GET /api/states` liefert *alle*
   Entities inklusive Attribute. Auf einer Instanz mit 3457 Entities gemessen:
   ~2,4 MB je Abruf. Das Live-Cockpit pollte das alle 5 s, um daraus rund
   zwanzig Sensoren zu filtern — und im Add-on läuft jedes Paket zusätzlich
   durch den Ingress-Proxy, also ein zweites Mal durch den Event-Loop von HA.
2. **Nicht index-fähige Recorder-Queries.** `FROM_UNIXTIME(start_ts) >= :von`
   schließt den Index `(metadata_id, start_ts)` für den Zeitbereich aus.
3. **Synchrone DB-Aufrufe im Event-Loop von eedc** — die erklären „eedc
   selbst ist träge", unabhängig von HA.

Die Tests hier sind überwiegend **Wächter**: sie greifen auch an Stellen, die
es heute noch nicht gibt. Die Verhaltensbelege für die Zeitgrenzen selbst
stehen in `test_ha_lts_monatswerte_lookup.py` (Monatsschnitt, Toleranzfenster,
Off-by-one) und liefen unverändert durch — das Ergebnis ändert sich nicht, nur
der Weg dorthin.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_EEDC_ROOT = Path(__file__).resolve().parents[2]  # eedc/

from backend.services import ha_state_service  # noqa: E402
from backend.services.ha_state_service import (  # noqa: E402
    HAStateService,
    fetch_selected_states,
)
from backend.tests.quellbaum import produktivbaum  # noqa: E402

_BACKEND = _EEDC_ROOT / "backend"


# ── Testdoppel für httpx ──────────────────────────────────────────────

class _Antwort:
    def __init__(self, daten: dict | None, status: int = 200):
        self.status_code = status
        self._daten = daten

    def json(self):
        return self._daten


class _FakeClient:
    """Zeichnet jede angefragte URL auf und beantwortet sie aus `bestand`."""

    aufrufe: list[str] = []
    bestand: dict[str, dict] = {}

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def get(self, url, headers=None, params=None):
        type(self).aufrufe.append(url)
        eid = url.rsplit("/states/", 1)[-1]
        daten = type(self).bestand.get(eid)
        if daten is None:
            return _Antwort(None, status=404)
        return _Antwort(daten)


@pytest.fixture
def fake_http(monkeypatch):
    """Ersetzt httpx.AsyncClient und leert den Modul-Cache."""
    _FakeClient.aufrufe = []
    _FakeClient.bestand = {}
    ha_state_service._state_cache.clear()
    monkeypatch.setattr(ha_state_service.httpx, "AsyncClient", _FakeClient)
    yield _FakeClient
    ha_state_service._state_cache.clear()


def _sensor(state: str, einheit: str | None = "W") -> dict:
    attrs = {"unit_of_measurement": einheit} if einheit is not None else {}
    return {"state": state, "attributes": attrs}


# ── 1. Gezielter States-Abruf statt Voll-Dump ─────────────────────────

async def test_abruf_fragt_nur_die_gebrauchten_entities(fake_http):
    """Der Voll-Dump `/api/states` darf nicht mehr vorkommen.

    Das ist der Kern des Befunds: nicht *wie oft* abgefragt wird, sondern
    *wieviel* je Abfrage über den Draht geht.
    """
    fake_http.bestand = {
        "sensor.pv": _sensor("1234"),
        "sensor.netz": _sensor("-500"),
    }

    ergebnis = await fetch_selected_states(
        "http://supervisor/core/api", "token", ["sensor.pv", "sensor.netz"]
    )

    assert ergebnis["sensor.pv"]["state"] == "1234"
    assert ergebnis["sensor.netz"]["state"] == "-500"
    assert sorted(fake_http.aufrufe) == [
        "http://supervisor/core/api/states/sensor.netz",
        "http://supervisor/core/api/states/sensor.pv",
    ]
    # Kein Aufruf endet auf dem nackten Sammel-Endpunkt.
    assert not any(u.endswith("/states") for u in fake_http.aufrufe)


async def test_zweiter_poll_innerhalb_des_ttl_fragt_nicht_erneut(fake_http):
    """Zwei versetzt pollende Tabs sollen sich den Abruf teilen.

    Ohne den Cache multiplizierte jeder offene Live-Tab die Last auf HA — der
    5-s-Takt gilt je Tab, nicht je Anlage.
    """
    fake_http.bestand = {"sensor.pv": _sensor("1234")}

    await fetch_selected_states("http://ha", "token", ["sensor.pv"])
    assert len(fake_http.aufrufe) == 1

    await fetch_selected_states("http://ha", "token", ["sensor.pv"])
    assert len(fake_http.aufrufe) == 1, "zweiter Abruf ging trotz TTL an HA"


async def test_getrennte_verbindungen_teilen_den_cache_nicht(fake_http):
    """Supervisor und Remote-HA sind zwei Instanzen — der Cache trennt sie."""
    fake_http.bestand = {"sensor.pv": _sensor("1234")}

    await fetch_selected_states("http://supervisor/core/api", "t", ["sensor.pv"])
    await fetch_selected_states("http://fern:8123/api", "t", ["sensor.pv"])

    assert len(fake_http.aufrufe) == 2


async def test_ein_unerreichbarer_sensor_nimmt_die_anderen_nicht_mit(fake_http):
    """Vorher gab ein Fehler das ganze Batch als leer zurück — alle Kacheln
    standen auf „—", obwohl nur ein Sensor fehlte."""
    fake_http.bestand = {"sensor.pv": _sensor("1234")}  # sensor.weg fehlt

    ergebnis = await fetch_selected_states(
        "http://ha", "token", ["sensor.pv", "sensor.weg"]
    )

    assert ergebnis["sensor.pv"]["state"] == "1234"
    assert ergebnis["sensor.weg"] is None


async def test_einheiten_cache_haelt_auch_sensoren_ohne_einheit(fake_http, monkeypatch):
    """Ein einziger Sensor ohne `unit_of_measurement` legte den 1h-TTL lahm.

    Gemerkt wurde vorher nur, wer eine Einheit hatte (`if unit:`). Wer keine
    hatte, stand damit dauerhaft auf der Fehlliste — und die Fehlliste löste
    den Neuabruf aus. Ergebnis: der Voll-Dump lief bei **jedem** Aufruf, der
    Cache war wirkungslos. Genau solche Sensoren gibt es (Roh-Counter ohne
    `state_class`, siehe `feedback_ha_lts_keine_zeitmaschine`).
    """
    svc = HAStateService()
    monkeypatch.setattr(svc, "api_url", "http://ha")
    monkeypatch.setattr(svc, "token", "token")
    fake_http.bestand = {
        "sensor.mit": _sensor("1", einheit="kWh"),
        "sensor.ohne": _sensor("2", einheit=None),
    }

    erste = await svc.get_sensor_units(["sensor.mit", "sensor.ohne"])
    assert erste == {"sensor.mit": "kWh"}  # Vertrag unverändert: nur belegte
    abrufe_nach_erstem = len(fake_http.aufrufe)

    # Den kurzlebigen States-Cache leeren: `get_sensor_units` wird im
    # Minutenabstand gerufen, da ist er längst abgelaufen. Ohne diesen Schritt
    # fängt er den zweiten Abruf ab und der Test wird stumm — genau so ist er
    # bei der Rot-Verifikation zuerst durchgefallen, ohne etwas zu belegen.
    ha_state_service._state_cache.clear()

    zweite = await svc.get_sensor_units(["sensor.mit", "sensor.ohne"])
    assert zweite == erste
    assert len(fake_http.aufrufe) == abrufe_nach_erstem, (
        "der Sensor ohne Einheit hat den Cache erneut entwertet"
    )


async def test_einheiten_kommen_auch_auf_frisch_gestarteter_box(fake_http, monkeypatch):
    """`time.monotonic()` zählt ab Systemstart — nicht ab 1970.

    Der leere Cache wurde über einen Default-Zeitstempel `0.0` geprüft:
    `now - 0.0 >= 3600` ist auf einer Box, die seit weniger als einer Stunde
    läuft, **falsch**. Damit galt „noch nie geholt" als „gerade erst geholt",
    es wurde nichts abgerufen, und `get_sensor_units` lieferte die erste
    Betriebsstunde lang `{}` — für Live-Historie, Energieprofil und
    Daten-Checker heißt das: keine Einheit, also keine kW/kWh-Unterscheidung.

    Der Test hält die Uhr klein und ist damit **unabhängig von der Laufzeit der
    Maschine, auf der er läuft**. Genau daran hing der Vorgänger: auf einem
    Rechner mit Tagen an Uptime grün, auf einem frischen CI-Runner rot.
    """
    monkeypatch.setattr(ha_state_service.time, "monotonic", lambda: 42.0)
    svc = HAStateService()
    monkeypatch.setattr(svc, "api_url", "http://ha")
    monkeypatch.setattr(svc, "token", "token")
    fake_http.bestand = {"sensor.zaehler": _sensor("1", einheit="kWh")}

    assert await svc.get_sensor_units(["sensor.zaehler"]) == {"sensor.zaehler": "kWh"}


# ── 2. Recorder-Queries bleiben index-fähig ───────────────────────────

def _sql_literale(pfad: Path) -> list[str]:
    """Alle an `text(...)` übergebenen SQL-Strings einer Datei.

    F-Strings werden aus ihren konstanten Teilen zusammengesetzt; die
    eingesetzten Platzhalter (`{table}`, `{placeholders}`) tragen keine
    Zeitfunktionen und fehlen deshalb folgenlos.
    """
    baum = ast.parse(pfad.read_text())
    raus: list[str] = []
    for knoten in ast.walk(baum):
        if not (isinstance(knoten, ast.Call) and isinstance(knoten.func, ast.Name)):
            continue
        if knoten.func.id != "text" or not knoten.args:
            continue
        arg = knoten.args[0]
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            raus.append(arg.value)
        elif isinstance(arg, ast.JoinedStr):
            raus.append("".join(
                t.value for t in arg.values
                if isinstance(t, ast.Constant) and isinstance(t.value, str)
            ))
    return raus


def test_keine_zeitfunktion_um_start_ts_in_recorder_queries():
    """`start_ts` wird roh verglichen — sonst ist der Index wirkungslos.

    Der Recorder indiziert `(metadata_id, start_ts)`. Steht die Spalte in einer
    Funktion, kann die Datenbank den Zeitbereich nicht über den Index
    eingrenzen: sie liest die **gesamte** Historie des Sensors, wendet die
    Funktion je Zeile an und sortiert anschließend. `get_value_at` betrat
    diesen Pfad je Zähler stündlich, bei aktivem 5-Min-Snapshot alle fünf
    Minuten.

    Wächter, nicht Regression: er greift auch für eine Query, die es heute
    noch nicht gibt.
    """
    verboten = ("FROM_UNIXTIME", "unixepoch")
    treffer = [
        (sql.strip()[:80], wort)
        for sql in _sql_literale(_BACKEND / "services" / "ha_statistics_service.py")
        for wort in verboten
        if wort in sql
    ]
    assert not treffer, (
        "Zeitfunktion um eine Spalte in einer Recorder-Query — der Index auf "
        f"start_ts ist damit wirkungslos: {treffer}"
    )


def test_zeitgrenzen_helfer_rechnet_lokale_wanduhrzeit_um():
    """`_unix` muss dieselbe Zone treffen wie die Aufrufer.

    Die Grenzen entstehen als naive lokale `datetime` (Monatserster,
    Snapshot-Stunde). Wird daraus ein Timestamp, muss er dieselbe Wanduhrzeit
    meinen — sonst verschiebt sich der Monatsschnitt.
    """
    import time as time_module
    from datetime import datetime

    from backend.services.ha_statistics_service import _monatsgrenzen_ts, _unix

    grenze = datetime(2026, 5, 1, 0, 0)
    assert _unix(grenze) == time_module.mktime(grenze.timetuple())

    start, ende = _monatsgrenzen_ts(2026, 12)
    assert start == _unix(datetime(2026, 12, 1))
    assert ende == _unix(datetime(2027, 1, 1)), "Jahreswechsel falsch gerechnet"


# ── 3. Kein blockierender Recorder-Aufruf im Event-Loop ───────────────

# Synchrone Methoden des HAStatisticsService, die in einem `async def` nur
# über `asyncio.to_thread` aufgerufen werden dürfen. Direkt aufgerufen halten
# sie den Event-Loop von eedc an — und damit **jede** parallele Anfrage.
_RECORDER_METHODEN = {
    "count_statistics_sensors", "filter_summen_faehige_sensor_ids",
    "filter_valid_sensor_ids", "get_alle_monatswerte",
    "get_hourly_kwh_deltas_for_day", "get_hourly_mean_for_day",
    "get_hourly_minmax_sensor_data", "get_hourly_sensor_data",
    "get_monatsanfang_wert", "get_monatswerte", "get_sensor_monatswert",
    "get_short_term_5min_for_day", "get_value_at", "get_verfuegbare_monate",
}

# Bestand vom 2026-08-03, als der Wächter scharf gestellt wurde. **Diese Liste
# darf nur schrumpfen.** Sie ist die einzige Buchung der Restschuld — wer sie
# verlängert, baut den Fehler neu ein, den dieses Paket entfernt hat.
#
# Bewusst NICHT mitgebaut, weil der Auftrag die getakteten Jobs meinte
# (`snapshot/writer.py`, alle 5 min bzw. stündlich) und eine Ausweitung ohne
# Auftrag genau das ist, was das Fund-Register verhindern soll:
#   • `api/routes/ha_statistics.py` — Import/Vorschau, vom Anwender ausgelöst
#     und einmalig; blockiert für die Dauer der Anfrage.
#   • `snapshot/lts_aggregator.py` — Tages-Aggregation.
#   • `snapshot/reader.py` · `snapshot/reaggregator.py` — Self-Healing und
#     Reparatur-Werkbank. Der Reparatur-Pfad ist der unangenehmste Rest: er
#     läuft über Tage × Sensoren und hält den Loop entsprechend lange.
_NOCH_NICHT_ENTKOPPELT = {
    ("api/routes/ha_statistics.py", "count_statistics_sensors"),
    ("api/routes/ha_statistics.py", "get_monatswerte"),
    ("api/routes/ha_statistics.py", "get_verfuegbare_monate"),
    ("api/routes/ha_statistics.py", "get_alle_monatswerte"),
    ("api/routes/ha_statistics.py", "get_monatsanfang_wert"),
    ("services/snapshot/lts_aggregator.py", "get_hourly_kwh_deltas_for_day"),
    ("services/snapshot/reader.py", "get_value_at"),
    ("services/snapshot/reaggregator.py", "get_value_at"),
}
_RESTSCHULD_OBERGRENZE = 14


def _blockierende_aufrufe() -> list[tuple[str, int, str, str]]:
    """(Datei, Zeile, Methode, umgebende async-Funktion) für jeden Direktaufruf.

    Ein über `asyncio.to_thread(svc.get_value_at, ...)` gereichter Name ist
    kein `Call` und taucht hier korrekt nicht auf.
    """
    treffer: list[tuple[str, int, str, str]] = []
    for datei in produktivbaum():
        rel, baum = datei.rel, datei.baum
        for fn in ast.walk(baum):
            if not isinstance(fn, ast.AsyncFunctionDef):
                continue
            for aufruf in ast.walk(fn):
                if (
                    isinstance(aufruf, ast.Call)
                    and isinstance(aufruf.func, ast.Attribute)
                    and aufruf.func.attr in _RECORDER_METHODEN
                ):
                    treffer.append((rel, aufruf.lineno, aufruf.func.attr, fn.name))
    return treffer


def test_snapshot_jobs_blockieren_den_event_loop_nicht():
    """Die getakteten Snapshot-Jobs sind entkoppelt.

    `snapshot/writer.py` läuft stündlich (:05 und :55) und — bei aktivem
    5-Min-Snapshot — alle fünf Minuten, je Anlage über alle gemappten Zähler.
    Jede dieser Abfragen hielt vorher den Event-Loop an, während eedc
    gleichzeitig Anfragen bedienen sollte.
    """
    verstoesse = [t for t in _blockierende_aufrufe() if t[0].startswith("services/snapshot/writer.py")]
    assert not verstoesse, (
        f"blockierender Recorder-Aufruf im Snapshot-Job: {verstoesse}"
    )


def test_restschuld_blockierender_aufrufe_waechst_nicht():
    """Der Rest ist gezählt, nicht vergessen — und darf nur kleiner werden."""
    treffer = _blockierende_aufrufe()
    assert len(treffer) <= _RESTSCHULD_OBERGRENZE, (
        f"{len(treffer)} blockierende Recorder-Aufrufe, erlaubt sind "
        f"{_RESTSCHULD_OBERGRENZE}. Neu hinzugekommen: "
        f"{[t for t in treffer if (t[0], t[2]) not in _NOCH_NICHT_ENTKOPPELT]}"
    )

    unbekannt = {(d, m) for d, _, m, _ in treffer} - _NOCH_NICHT_ENTKOPPELT
    assert not unbekannt, (
        f"neue Datei/Methode mit blockierendem Recorder-Aufruf: {unbekannt}"
    )
