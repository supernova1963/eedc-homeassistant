"""HA-Langzeitstatistik über die WebSocket-API — der zweite **Transport**.

Was hier NICHT passiert: eine zweite Quelle erschließen. `recorder/statistics_
during_period` liefert exakt die Spalten, die `ha_statistics_service.py` sonst
per SQL aus `statistics`/`statistics_short_term` liest — `sum` · `state` ·
`mean` · `min` · `max` je `5minute|hour|day|month`. Aggregator, Rücksetzer-
Behandlung, Boundary- und Slot-Konvention bleiben deshalb unberührt: sie sehen
dieselben Zahlen, nur über ein anderes Kabel.

**Warum das gebaut wurde.** Wer eedc als eigenen Container neben Home Assistant
betreibt (Standalone, Long-Lived-Token), hatte bis hierher **keinen** Zugriff
auf die Langzeitstatistik: `HAStatisticsService` kennt nur die Recorder-**Datei**
(`/config/home-assistant_v2.db`) bzw. `HA_RECORDER_DB_URL`. Ohne einen der
beiden entstehen Tageswerte ausschließlich aus eedcs eigenen 5-Minuten-
Snapshots — also ab Installation vorwärts, nie rückwärts. Der Umweg über
`/config:ro` trägt zudem nur, wenn eedc und HA auf **demselben Host** laufen
**und** HA läuft (eine WAL-Datenbank braucht auch als Leser eine schreibbare
`-shm`), und bei MariaDB-Recorder gar nicht.

**Die Grenze, die bleibt:** die LTS reicht nur so weit zurück, wie der Sensor in
HA existiert. Für alles davor ist der Datei-Import die Antwort, nicht dieser Weg.

Gemessen am 2026-08-05 gegen eine Live-HA (1773 statistic_ids):
  · `list_statistic_ids`                      1773 IDs / 0,07 s
  · `hour`, 125 lebende Zähler, 2 Tage        0,22 s
  · `hour`, 8 IDs, 1 Jahr                     4,97 MB / 22,2 s
  · `day`,  8 IDs, 1 Jahr                     209 KB / 15,9 s
  · `5minute`, 1 ID, 16 Tage                  3050 Slots / 0,89 s
Ein Backfill über ein Jahr ist damit einmalig teuer und im laufenden Betrieb
(Fenster von Stunden) billig. Blockweise lesen hält den Speicher klein.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from datetime import datetime
from typing import Any, NamedTuple, Optional

logger = logging.getLogger(__name__)

# Ein Jahr `hour` × 8 Sensoren brauchte gemessen 22,2 s. Der Vollbackfill liest
# blockweise (monatsweise), trotzdem großzügig — ein Abbruch mitten im Backfill
# kostet mehr als ein paar Sekunden Warten.
_BEFEHL_TIMEOUT = 120.0
_VERBINDUNGS_TIMEOUT = 15.0


class WsSensorMeta(NamedTuple):
    """Metadaten eines Statistik-Sensors — das Gegenstück zu `statistics_meta`.

    `statistics_meta.unit_of_measurement` heißt in der WS-Antwort
    `statistics_unit_of_measurement`. Danebensteht `display_unit_of_measurement`
    (was die Oberfläche anzeigt) — für eine Rechnung ist ausschließlich die
    Statistik-Einheit richtig, denn in ihr sind die Werte gespeichert.
    """

    unit: Optional[str]
    has_sum: bool
    has_mean: bool


class HAStatistikNichtErreichbar(RuntimeError):
    """HA antwortet nicht, lehnt den Token ab oder kennt den Recorder nicht."""


class _BrueckenLoop:
    """Ein Event-Loop in einem Hintergrund-Thread — die sync→async-Brücke.

    `HAStatisticsService` ist durchgehend **synchron** (20 Lesemethoden), seine
    Aufrufer sind fast alle `async def` (Snapshot-Writer, LTS-Aggregator,
    Cockpit-Routen). Ein `asyncio.run()` in einer dieser sync-Methoden würde
    deshalb mit „cannot be called from a running event loop" abbrechen, und die
    Methoden `async` zu machen hieße, jeden der Aufrufer anzufassen.

    Also läuft der WS-Verkehr in einem **eigenen** Loop in einem eigenen Thread;
    die sync-Methode legt ihre Coroutine dort ab und wartet auf das Ergebnis.
    Der Thread ist ein Daemon und lebt so lange wie der Prozess.

    ⚠ Bewusst ein **eigener** Loop und nicht der der Anwendung: aiosqlite-
    Verbindungen sind an den Loop gebunden, in dem sie entstanden sind. Aus
    diesem Thread wird deshalb **nie** die eedc-Datenbank angefasst — er spricht
    ausschließlich mit Home Assistant.
    """

    def __init__(self) -> None:
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._start_lock = threading.Lock()

    def _sicherstellen(self) -> asyncio.AbstractEventLoop:
        with self._start_lock:
            if self._loop is not None and self._thread is not None and self._thread.is_alive():
                return self._loop
            loop = asyncio.new_event_loop()
            thread = threading.Thread(
                target=self._laufen, args=(loop,), name="eedc-ha-ws", daemon=True,
            )
            thread.start()
            self._loop = loop
            self._thread = thread
            return loop

    @staticmethod
    def _laufen(loop: asyncio.AbstractEventLoop) -> None:
        asyncio.set_event_loop(loop)
        loop.run_forever()

    def ausfuehren(self, coro, timeout: float):
        """Führt eine Coroutine im Brücken-Loop aus und wartet synchron."""
        loop = self._sicherstellen()
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return future.result(timeout=timeout)


_bruecke = _BrueckenLoop()


class HAStatisticsWebsocket:
    """Ein WS-Client auf `recorder/*`, synchron benutzbar.

    Die Verbindung wird **gehalten**, nicht je Abfrage neu aufgebaut: der
    Snapshot-Job fragt je Zähler und Lauf einen Wert ab (bei aktivem
    5-Min-Snapshot alle fünf Minuten), und ein Handshake je Wert wäre teurer
    als die Abfrage selbst. Bricht sie weg, baut der nächste Aufruf sie neu auf.
    """

    def __init__(self, base_url: str, token: str) -> None:
        self._ws_url = self._ws_adresse(base_url)
        self._token = token
        self._ws: Any = None
        self._befehls_id = 0
        self._lock = asyncio.Lock()
        self._meta_cache: Optional[dict[str, WsSensorMeta]] = None

    @property
    def ws_url(self) -> str:
        """Die angesprochene WebSocket-Adresse — für Statusanzeigen."""
        return self._ws_url

    @staticmethod
    def _ws_adresse(base_url: str) -> str:
        """`http(s)://host:8123` oder `.../api` → `ws(s)://host:8123/api/websocket`.

        `resolve_ha_connection` liefert die URL **mit** `/api`-Suffix; die
        Supervisor-Variante zeigt auf `http://supervisor/core/api`. Beide Formen
        landen hier auf demselben Endpunkt.
        """
        url = (base_url or "").strip().rstrip("/")
        if url.endswith("/api"):
            url = url[: -len("/api")]
        if url.startswith("https://"):
            url = "wss://" + url[len("https://"):]
        elif url.startswith("http://"):
            url = "ws://" + url[len("http://"):]
        return url + "/api/websocket"

    # ---------------------------------------------------------------- Transport

    async def _verbinden(self) -> Any:
        if self._ws is not None:
            return self._ws
        import websockets

        ws = await websockets.connect(
            self._ws_url,
            open_timeout=_VERBINDUNGS_TIMEOUT,
            close_timeout=5,
            # Ein Jahr `hour` über acht Sensoren maß 4,97 MB — die Vorgabe von
            # websockets (1 MB) würde die Antwort verwerfen.
            max_size=128 * 1024 * 1024,
            ping_interval=20,
        )
        hallo = json.loads(await asyncio.wait_for(ws.recv(), timeout=_VERBINDUNGS_TIMEOUT))
        if hallo.get("type") != "auth_required":
            await ws.close()
            raise HAStatistikNichtErreichbar(
                f"Unerwartete Begrüßung von {self._ws_url}: {hallo.get('type')}"
            )
        await ws.send(json.dumps({"type": "auth", "access_token": self._token}))
        antwort = json.loads(await asyncio.wait_for(ws.recv(), timeout=_VERBINDUNGS_TIMEOUT))
        if antwort.get("type") != "auth_ok":
            await ws.close()
            raise HAStatistikNichtErreichbar("Home Assistant hat den Token abgelehnt")
        self._ws = ws
        self._befehls_id = 0
        return ws

    async def _befehl(self, payload: dict) -> Any:
        """Sendet einen Befehl und liefert sein `result`. Ein Versuch Neuaufbau."""
        async with self._lock:
            for versuch in (1, 2):
                try:
                    ws = await self._verbinden()
                    self._befehls_id += 1
                    eigene_id = self._befehls_id
                    await ws.send(json.dumps({**payload, "id": eigene_id}))
                    while True:
                        roh = await asyncio.wait_for(ws.recv(), timeout=_BEFEHL_TIMEOUT)
                        nachricht = json.loads(roh)
                        if nachricht.get("id") != eigene_id:
                            continue  # Antwort auf einen anderen Befehl
                        if not nachricht.get("success"):
                            fehler = (nachricht.get("error") or {}).get("message", "unbekannt")
                            raise HAStatistikNichtErreichbar(
                                f"{payload.get('type')} abgelehnt: {fehler}"
                            )
                        return nachricht.get("result")
                except HAStatistikNichtErreichbar:
                    raise
                except Exception as e:  # noqa: BLE001 — Netz/Timeout/Abbruch
                    await self._schliessen()
                    if versuch == 2:
                        raise HAStatistikNichtErreichbar(
                            f"{payload.get('type')} fehlgeschlagen: {type(e).__name__}: {e}"
                        ) from e
                    logger.debug("WS-Verbindung weg, baue neu auf: %s", type(e).__name__)
        raise HAStatistikNichtErreichbar("unerreichbar")  # pragma: no cover

    async def _schliessen(self) -> None:
        ws, self._ws = self._ws, None
        if ws is not None:
            try:
                await ws.close()
            except Exception:  # noqa: BLE001 — beim Aufräumen ist jeder Fehler egal
                pass

    # ------------------------------------------------------------------ Abfragen

    def metadaten(self, erneuern: bool = False) -> dict[str, WsSensorMeta]:
        """Alle Statistik-Sensoren — das Gegenstück zu `statistics_meta`.

        Wird gecacht: die Liste kostet zwar nur ~0,07 s, wird aber je Sensor und
        Abfrage gebraucht. `erneuern=True` erzwingt eine frische Abfrage — der
        aufrufende Service hält seinerseits einen kurzen TTL, damit ein
        nachgetragenes `state_class` zeitnah wirkt.
        """
        if self._meta_cache is not None and not erneuern:
            return self._meta_cache
        roh = _bruecke.ausfuehren(
            self._befehl({"type": "recorder/list_statistic_ids"}), _BEFEHL_TIMEOUT,
        ) or []
        metadaten = {
            eintrag["statistic_id"]: WsSensorMeta(
                # Die Statistik-Einheit, nicht die Anzeige-Einheit: in ihr sind
                # die Werte gespeichert, und nur sie darf eine Rechnung skalieren.
                unit=eintrag.get("statistics_unit_of_measurement"),
                has_sum=bool(eintrag.get("has_sum")),
                has_mean=bool(eintrag.get("has_mean")),
            )
            for eintrag in roh
            if eintrag.get("statistic_id")
        }
        self._meta_cache = metadaten
        return metadaten

    def statistiken(
        self,
        sensor_ids: list[str],
        von: datetime,
        bis: datetime,
        period: str = "hour",
        types: Optional[list[str]] = None,
    ) -> dict[str, list[dict]]:
        """Statistik-Zeilen je Sensor.

        Args:
            sensor_ids: HA-Entity-IDs.
            von / bis: **lokale, naive** Zeitpunkte — dieselbe Form, in der der
                DB-Pfad rechnet. Sie werden hier mit der Zeitzone des Systems
                versehen, weil HA ISO-Zeitstempel mit Offset erwartet.
            period: `5minute` · `hour` · `day` · `month`.
            types: Teilmenge von `sum` · `state` · `mean` · `min` · `max`.

        Returns:
            `{sensor_id: [{"start_ts": float, "sum": .., "state": .., "mean": ..,
            "min": .., "max": ..}]}` — aufsteigend nach `start_ts`.

        `start_ts` ist bewusst dieselbe Größe wie die gleichnamige Spalte der
        Recorder-Tabelle (Unix-Sekunden, lokal interpretiert): damit passen
        `lts_boundary_index` und die Slot-Konvention ohne eine einzige
        Fallunterscheidung auf beide Transporte.
        """
        if not sensor_ids:
            return {}
        roh = _bruecke.ausfuehren(
            self._befehl({
                "type": "recorder/statistics_during_period",
                "start_time": von.astimezone().isoformat(),
                "end_time": bis.astimezone().isoformat(),
                "statistic_ids": list(sensor_ids),
                "period": period,
                "types": types or ["sum", "state", "mean", "min", "max"],
            }),
            _BEFEHL_TIMEOUT,
        ) or {}

        ergebnis: dict[str, list[dict]] = {}
        for sensor_id, zeilen in roh.items():
            umgesetzt = []
            for zeile in zeilen or []:
                start = zeile.get("start")
                if start is None:
                    continue
                umgesetzt.append({
                    # HA liefert Millisekunden seit Epoch, die Recorder-Spalte
                    # trägt Sekunden.
                    "start_ts": float(start) / 1000.0,
                    "sum": zeile.get("sum"),
                    "state": zeile.get("state"),
                    "mean": zeile.get("mean"),
                    "min": zeile.get("min"),
                    "max": zeile.get("max"),
                })
            umgesetzt.sort(key=lambda z: z["start_ts"])
            ergebnis[sensor_id] = umgesetzt
        return ergebnis

    def erreichbar(self) -> bool:
        """Einmalige Probe: Token akzeptiert und Recorder antwortet?

        Bewusst ein **echter** Aufruf und keine Existenz-Prüfung. Der SQLite-Zweig
        des DB-Backends nennt sich verfügbar, sobald die Datei da ist — ob sie
        lesbar ist, stellt sich erst beim ersten `SELECT` heraus, und bis dahin
        meldet eedc „HA-Statistics als Source-of-Truth aktiv" und liefert leere
        Ergebnisse. Dieser Weg macht denselben Fehler nicht.
        """
        try:
            return bool(self.metadaten())
        except Exception as e:  # noqa: BLE001 — jede Fehlerklasse heißt „nicht verfügbar"
            logger.info("HA-Statistik über WebSocket nicht erreichbar: %s", e)
            return False

    def schliessen(self) -> None:
        """Verbindung aufgeben (Konfigurationswechsel, Tests)."""
        try:
            _bruecke.ausfuehren(self._schliessen(), 10.0)
        except Exception:  # noqa: BLE001
            pass
        self._ws = None
        self._meta_cache = None
