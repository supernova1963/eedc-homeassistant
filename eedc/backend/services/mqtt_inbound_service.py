"""
MQTT Inbound Service — Empfängt Live-Leistungsdaten via MQTT.

Universelle Datenbrücke: Jedes Smarthome-System (HA, ioBroker, FHEM, openHAB,
Node-RED) kann Live-Werte auf EEDC-Topics publishen.

Topic-Struktur (mit sprechenden Namen):
  eedc/{id}_{anlagename}/live/einspeisung_w
  eedc/{id}_{anlagename}/live/netzbezug_w
  eedc/{id}_{anlagename}/live/strompreis_ct          (dynamischer Strompreis, ct/kWh)
  eedc/{id}_{anlagename}/live/inv/{id}_{name}/leistung_w
  eedc/{id}_{anlagename}/live/inv/{id}_{name}/soc

  eedc/{id}_{anlagename}/energy/einspeisung_kwh
  eedc/{id}_{anlagename}/energy/inv/{id}_{name}/{key}

  eedc/{id}_{anlagename}/live/inv/{id}_{name}/betriebsmodus   (Zustand: Kanon-Wort oder Code 0…5)

  Beispiel: eedc/1_Meine_PV_Anlage/live/inv/3_BYD_HVS/leistung_w
  Die numerische ID am Anfang jedes Segments ist die DB-ID, der Name ist optional.

**Zustandsfelder (HA-Bauform §9, Standalone-Gleichstand S1, 25.10.2026).** Ein Live-Feld, das
die Registry als Zustand führt (`ist_zustand_feld`, heute der Betriebsmodus samt Innengeräte-Suffix),
landet als **roher, getrimmter String** im Cache — gedeutet wird er erst im Kanon
(`core/betriebsmodus.normalisiere_betriebsmodus`), nie hier. Jedes andere Feld bleibt `float(payload)`;
ein String darauf wird verworfen wie bisher. Dazu führt der Cache je Gerät die **Haltezeit je
Kanon-Modus** seit dem letzten Abschluss (`ZustandsFenster`, Halteregel je Nachricht wie HA für
on-change-Publisher); der 5-Minuten-Snapshot schließt das Fenster ab (`modus_anteile_abschliessen`).
Ein Verbindungskennzeichen (`verbunden`) sagt dem Snapshot, ob der Broker gerade lebt: ohne
Verbindung entsteht keine Snapshot-Zeile (die Stunde bleibt Lücke statt eines eingefrorenen Werts),
beim Reconnect beginnen die Fenster neu.

**Integrator für Zahlenfelder (HA-Bauform §9, Standalone-Gleichstand S2, G3).** Je Live-Key führt der
Cache ein `MittelFenster` (Integral, Beginn, Minimum, Maximum): jede Nachricht addiert
`wert_alt × (jetzt − seit)` — dieselbe Halteregel je Nachricht wie beim Modus und wie HA für einen
on-change-Publisher. Der 5-Minuten-Snapshot schließt die Fenster ab (`mittel_abschliessen`) und
schreibt je Key das zeitgewichtete Mittel mit Minimum und Maximum; eine taktende Wärmepumpe
(3 min 2000 W, 3 min 0 W) ergibt so 1000 W statt einer Punktprobe 0 oder 2000. Der Momentanwert
im Cache (`_live`) bleibt, wie er ist — Live-Bild und Live-Leistung lesen ihn, nicht das Fenster.
"""

import asyncio
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Union

from backend.core.betriebsmodus import MODUS_FELD_KEY, modus_aus_zustaenden
from backend.core.field_definitions import basis_feld_key, ist_zustand_feld
from backend.services.activity_service import log_activity

logger = logging.getLogger(__name__)

try:
    import aiomqtt
    MQTT_AVAILABLE = True
except ImportError:
    MQTT_AVAILABLE = False


# Topic-Pattern: eedc/{id}_{name}/live/{key} oder eedc/{id}_{name}/live/inv/{id}_{name}/{key}
# Die ID ist numerisch, der _name-Teil ist optional (für Lesbarkeit)
_TOPIC_RE = re.compile(
    r"^eedc/(\d+)(?:_[^/]*)?/(live|energy)/"
    r"(?:inv/(\d+)(?:_[^/]*)*/)?(.+)$"
)


#: Ein Live-Wert im Cache: eine Zahl, oder bei einem Zustandsfeld der rohe String (HA-Bauform §9).
LiveWert = Union[float, str]


@dataclass
class ZustandsFenster:
    """Haltezeit je Kanon-Modus **eines Geräts** seit dem letzten Abschluss (HA-Bauform §9, E-SG-3 für Zustände).

    Halteregel je Nachricht: ein Modus gilt bis zur nächsten Nachricht — HAs Semantik für einen
    on-change-Publisher. ``modus is None`` (kein verwertbarer Zustand, widersprüchliche Suffix-Topics)
    zählt keine Zeit: der Anteil bezieht sich auf die Fensterlänge, das Ungesehene bleibt offen — wie
    der HA-Verlauf (`_get_betriebsmodus_history`: Verweildauer ÷ Stundenlänge).

    Die Zahlenseite derselben Form ist `MittelFenster` (Standalone-Gleichstand S2).
    """

    beginn: float
    seit: float
    modus: Optional[str] = None
    haltezeit: dict[str, float] = field(default_factory=dict)

    def _halten(self, jetzt: float) -> None:
        if self.modus is not None and jetzt > self.seit:
            self.haltezeit[self.modus] = self.haltezeit.get(self.modus, 0.0) + (jetzt - self.seit)
        self.seit = max(self.seit, jetzt)

    def neuer_modus(self, modus: Optional[str], jetzt: float) -> None:
        """Der bisherige Modus hielt bis ``jetzt``; ab hier gilt ``modus``."""
        self._halten(jetzt)
        self.modus = modus

    def abschliessen(self, jetzt: float) -> dict[str, float]:
        """Anteil je Modus am Fenster ``[beginn, jetzt)`` (0–1); danach beginnt das nächste Fenster bei ``jetzt``."""
        self._halten(jetzt)
        laenge = jetzt - self.beginn
        anteile = (
            {m: min(1.0, s / laenge) for m, s in self.haltezeit.items() if s > 0}
            if laenge > 0 else {}
        )
        self.haltezeit = {}
        self.beginn = jetzt
        return anteile


@dataclass
class MittelFenster:
    """Integral, Minimum und Maximum **eines Live-Zahlenwerts** seit dem letzten Abschluss (HA-Bauform §9, G3).

    Halteregel je Nachricht: ein Wert gilt bis zur nächsten Nachricht — dieselbe Form wie `ZustandsFenster`.
    Über einen Abschluss hinweg hält der letzte Wert weiter (ein on-change-Publisher, der um 22:00 einmal
    «0» schickt, ergibt jede Stunde der Nacht 0); erst ein Verbindungsverlust leert die Fenster.
    """

    beginn: float
    seit: float
    wert: float
    integral: float = 0.0
    minimum: float = field(init=False)
    maximum: float = field(init=False)

    def __post_init__(self) -> None:
        self.minimum = self.maximum = self.wert

    def _halten(self, jetzt: float) -> None:
        if jetzt > self.seit:
            self.integral += self.wert * (jetzt - self.seit)
            self.seit = jetzt

    def neuer_wert(self, wert: float, jetzt: float) -> None:
        """Der bisherige Wert hielt bis ``jetzt``; ab hier gilt ``wert``."""
        self._halten(jetzt)
        self.wert = wert
        self.minimum = min(self.minimum, wert)
        self.maximum = max(self.maximum, wert)

    def abschliessen(self, jetzt: float) -> Optional[tuple[float, float, float]]:
        """``(mittel, minimum, maximum)`` des Fensters ``[beginn, jetzt)``; danach beginnt das nächste bei ``jetzt``
        mit dem gehaltenen Wert. ``None``, wenn das Fenster keine Länge hat (Nachricht im selben Augenblick)."""
        self._halten(jetzt)
        laenge = jetzt - self.beginn
        ergebnis = None
        if laenge > 0:
            # Ein Fenster mit einem einzigen Wert liefert ihn wörtlich (keine Rundung aus Σ w·Δt / Δt).
            mittel = self.wert if self.minimum == self.maximum else self.integral / laenge
            ergebnis = (mittel, self.minimum, self.maximum)
        self.beginn = self.seit = jetzt
        self.integral = 0.0
        self.minimum = self.maximum = self.wert
        return ergebnis


def _adresse(topic: str) -> Optional[tuple[int, str, Optional[str], str]]:
    """Topic → ``(anlage_id, kategorie, inv_id, key)`` oder ``None`` für ein fremdes Topic."""
    m = _TOPIC_RE.match(topic)
    if not m:
        return None
    return int(m.group(1)), m.group(2), m.group(3), m.group(4)


def _wert_aus_payload(ist_zustand: bool, payload, topic: str) -> Optional[LiveWert]:
    """Payload → Cache-Wert: roher getrimmter String bei einem Zustandsfeld, sonst ``float``.

    ``None`` heißt verwerfen — ein leerer Zustand (gelöschter retained-Wert) wie eine Zahl, die keine ist.
    """
    if ist_zustand:
        roh = str(payload).strip() if payload is not None else ""
        return roh or None
    try:
        return float(payload)
    except (ValueError, TypeError):
        logger.debug("MQTT-Inbound: ungültiger Payload '%s' auf %s", payload, topic)
        return None


class MqttInboundCache:
    """
    In-Memory-Cache für empfangene MQTT-Werte.

    Struktur:
      _live[anlage_id]["basis"][key] = (wert, timestamp)
      _live[anlage_id]["inv"][inv_id][key] = (wert, timestamp)   # wert: float, bei Zustand der rohe String
      _energy[anlage_id][key] = (wert, timestamp)
      _modus_fenster[(anlage_id, inv_id)] = ZustandsFenster       # Haltezeit je Modus (HA-Bauform §9)
      _mittel_fenster[(anlage_id, inv_id|None, key)] = MittelFenster # Integral je Zahlen-Key (HA-Bauform §9, G3)
    """

    def __init__(self):
        self._live: dict[int, dict] = {}
        self._energy: dict[int, dict[str, tuple[float, datetime]]] = {}
        self._message_count = 0
        self._last_message_at: Optional[datetime] = None
        self._modus_fenster: dict[tuple[int, str], ZustandsFenster] = {}
        self._mittel_fenster: dict[tuple[int, Optional[str], str], MittelFenster] = {}
        #: Lebt die Verbindung zum Broker? True nach dem Subscribe, False nach einem Verbindungsverlust
        #: (E-SG-9). Ohne Verbindung schreibt der Snapshot keine Zeile.
        self.verbunden: bool = False

    def on_message(self, topic: str, payload: str, *, jetzt: Optional[float] = None) -> None:
        """Verarbeitet eine eingehende MQTT-Nachricht.

        ``jetzt`` (Unix-Sekunden) nur für Proben — sonst die Uhr beim Empfang.
        """
        adresse = _adresse(topic)
        if adresse is None:
            return
        anlage_id, category, inv_id, key = adresse
        ist_zustand = category == "live" and bool(inv_id) and ist_zustand_feld(key)
        wert = _wert_aus_payload(ist_zustand, payload, topic)
        if wert is None:
            return

        now = datetime.now()
        self._message_count += 1
        self._last_message_at = now

        if category == "live":
            self._live_ablegen(anlage_id, inv_id, key, wert, now)
            t = time.time() if jetzt is None else jetzt
            if not ist_zustand:
                self._mittel_fortschreiben(anlage_id, inv_id, key, float(wert), t)
            elif basis_feld_key(key) == MODUS_FELD_KEY:
                self._modus_fortschreiben(anlage_id, inv_id, t)
        elif category == "energy":
            if anlage_id not in self._energy:
                self._energy[anlage_id] = {}
            self._energy[anlage_id][f"inv/{inv_id}/{key}" if inv_id else key] = (wert, now)

    def _live_ablegen(self, anlage_id: int, inv_id: Optional[str], key: str, wert: LiveWert, now: datetime) -> None:
        cache = self._live.setdefault(anlage_id, {"basis": {}, "inv": {}})
        if inv_id:
            cache["inv"].setdefault(inv_id, {})[key] = (wert, now)
        else:
            cache["basis"][key] = (wert, now)

    def _modus_fortschreiben(self, anlage_id: int, inv_id: str, jetzt: float) -> None:
        """Der Modus des Geräts nach dieser Nachricht — über ALLE seine Modus-Keys (N-340, `modus_aus_zustaenden`)."""
        werte = self.get_live_inv(anlage_id, inv_id)
        modus = modus_aus_zustaenden(werte)
        fenster = self._modus_fenster.get((anlage_id, inv_id))
        if fenster is None:
            self._modus_fenster[(anlage_id, inv_id)] = ZustandsFenster(beginn=jetzt, seit=jetzt, modus=modus)
        else:
            fenster.neuer_modus(modus, jetzt)

    def _mittel_fortschreiben(self, anlage_id: int, inv_id: Optional[str], key: str, wert: float, jetzt: float) -> None:
        """Das Integral dieses Keys: der alte Wert hielt bis ``jetzt``, ab hier gilt ``wert`` (G3)."""
        schluessel = (anlage_id, inv_id or None, key)
        fenster = self._mittel_fenster.get(schluessel)
        if fenster is None:
            self._mittel_fenster[schluessel] = MittelFenster(beginn=jetzt, seit=jetzt, wert=wert)
        else:
            fenster.neuer_wert(wert, jetzt)

    def mittel_abschliessen(self, jetzt: Optional[float] = None) -> dict[int, dict]:
        """Schließt jedes Zahlen-Fenster bei ``jetzt`` ab:
        ``{anlage_id: {"basis": {key: (mittel, min, max)}, "inv": {inv_id: {key: (mittel, min, max)}}}}``.

        Der Aufrufer ist der 5-Minuten-Snapshot; ohne Verbindung fragt er nicht. Ein Fenster ohne Länge fehlt.
        """
        t = time.time() if jetzt is None else jetzt
        out: dict[int, dict] = {}
        for (anlage_id, inv_id, key), fenster in self._mittel_fenster.items():
            ergebnis = fenster.abschliessen(t)
            if ergebnis is None:
                continue
            ziel = out.setdefault(anlage_id, {"basis": {}, "inv": {}})
            if inv_id is None:
                ziel["basis"][key] = ergebnis
            else:
                ziel["inv"].setdefault(inv_id, {})[key] = ergebnis
        return out

    def modus_anteile_abschliessen(self, jetzt: Optional[float] = None) -> dict[int, dict[str, dict[str, float]]]:
        """Schließt jedes Modus-Fenster bei ``jetzt`` ab: ``{anlage_id: {inv_id: {modus: anteil}}}``.

        Der Aufrufer ist der 5-Minuten-Snapshot (`mqtt_live_history_service`); ohne Verbindung fragt er
        nicht. Ein Fenster ohne gezählte Zeit (kein verwertbarer Zustand) fehlt in der Rückgabe.
        """
        t = time.time() if jetzt is None else jetzt
        out: dict[int, dict[str, dict[str, float]]] = {}
        for (anlage_id, inv_id), fenster in self._modus_fenster.items():
            anteile = fenster.abschliessen(t)
            if anteile:
                out.setdefault(anlage_id, {})[inv_id] = anteile
        return out

    def verbinden(self) -> None:
        """Nach dem Subscribe: Verbindung lebt; Modus- und Zahlen-Fenster beginnen neu (E-SG-9)."""
        self._modus_fenster.clear()
        self._mittel_fenster.clear()
        self.verbunden = True

    def trennen(self) -> None:
        """Nach einem Verbindungsverlust oder Stopp: keine Snapshot-Zeilen, bis die Verbindung zurück ist."""
        self.verbunden = False
        self._modus_fenster.clear()
        self._mittel_fenster.clear()

    def get_live_basis(self, anlage_id: int) -> dict[str, float]:
        """Gibt Basis-Live-Werte zurück (einspeisung_w, netzbezug_w)."""
        cache = self._live.get(anlage_id, {})
        basis = cache.get("basis", {})
        return {k: v[0] for k, v in basis.items()}

    def get_live_inv(self, anlage_id: int, inv_id: str) -> dict[str, LiveWert]:
        """Gibt Live-Werte für eine Investition zurück (leistung_w, soc; Zustandsfelder als roher String)."""
        cache = self._live.get(anlage_id, {})
        inv_data = cache.get("inv", {}).get(inv_id, {})
        return {k: v[0] for k, v in inv_data.items()}

    def get_all_live_inv(self, anlage_id: int) -> dict[str, dict[str, LiveWert]]:
        """Gibt Live-Werte für alle Investitionen zurück (Zustandsfelder als roher String, HA-Bauform §9)."""
        cache = self._live.get(anlage_id, {})
        inv_data = cache.get("inv", {})
        return {
            inv_id: {k: v[0] for k, v in values.items()}
            for inv_id, values in inv_data.items()
        }

    def get_energy_data(self, anlage_id: int) -> dict[str, float]:
        """Gibt Energy-Werte zurück (einspeisung_kwh, netzbezug_kwh, inv/...)."""
        cache = self._energy.get(anlage_id, {})
        return {k: v[0] for k, v in cache.items()}

    def get_all_energy_raw(self) -> dict[int, dict[str, tuple[float, datetime]]]:
        """Gibt alle Energy-Daten mit Timestamps zurück (für History-Snapshots)."""
        return self._energy

    def get_all_live_raw(self) -> dict[int, dict]:
        """Gibt alle Live-Daten zurück (für Power-Snapshots).

        Struktur: {anlage_id: {"basis": {key: (val, ts)}, "inv": {inv_id: {key: (val, ts)}}}}
        """
        return self._live

    def has_data(self, anlage_id: int) -> bool:
        """Prüft ob MQTT-Daten für eine Anlage vorliegen."""
        cache = self._live.get(anlage_id, {})
        return bool(cache.get("basis") or cache.get("inv"))

    def clear_cache(self, anlage_id: Optional[int] = None) -> int:
        """Löscht Cache-Daten. Gibt Anzahl gelöschter Einträge zurück."""
        if anlage_id is not None:
            count = 0
            for schluessel in [s for s in self._modus_fenster if s[0] == anlage_id]:
                del self._modus_fenster[schluessel]
            for schluessel in [s for s in self._mittel_fenster if s[0] == anlage_id]:
                del self._mittel_fenster[schluessel]
            if anlage_id in self._live:
                live = self._live.pop(anlage_id)
                count += len(live.get("basis", {}))
                count += sum(len(v) for v in live.get("inv", {}).values())
            if anlage_id in self._energy:
                count += len(self._energy.pop(anlage_id))
            return count
        # Alle löschen
        count = 0
        for data in self._live.values():
            count += len(data.get("basis", {}))
            count += sum(len(v) for v in data.get("inv", {}).values())
        for data in self._energy.values():
            count += len(data)
        self._live.clear()
        self._energy.clear()
        self._modus_fenster.clear()
        self._mittel_fenster.clear()
        self._message_count = 0
        self._last_message_at = None
        return count

    def get_status(self) -> dict:
        """Gibt Status-Informationen zurück."""
        anlagen_mit_daten = [
            aid for aid, data in self._live.items()
            if data.get("basis") or data.get("inv")
        ]
        return {
            "verfuegbar": MQTT_AVAILABLE,
            "empfangene_nachrichten": self._message_count,
            "letzte_nachricht": self._last_message_at.isoformat() if self._last_message_at else None,
            "anlagen_mit_daten": anlagen_mit_daten,
        }


class MqttInboundService:
    """
    Managed den MQTT-Subscriber für Inbound-Daten.

    Startet einen Background-Task der auf eedc/+/live/# und eedc/+/energy/#
    subscribt und den Cache befüllt.
    """

    def __init__(self, host: str, port: int,
                 username: Optional[str] = None,
                 password: Optional[str] = None):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.cache = MqttInboundCache()
        self._task: Optional[asyncio.Task] = None
        self._running = False

    async def start(self) -> bool:
        """Startet den MQTT-Subscriber als Background-Task."""
        if not MQTT_AVAILABLE:
            logger.warning("MQTT-Inbound: aiomqtt nicht installiert")
            return False

        if self._running:
            return True

        self._running = True
        self._task = asyncio.create_task(self._subscribe_loop())
        logger.info("MQTT-Inbound: Subscriber gestartet (%s:%d)", self.host, self.port)
        await log_activity(
            kategorie="mqtt",
            aktion="MQTT-Inbound gestartet",
            erfolg=True,
            details=f"Broker: {self.host}:{self.port}",
        )
        return True

    async def stop(self) -> None:
        """Stoppt den MQTT-Subscriber."""
        self._running = False
        self.cache.trennen()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("MQTT-Inbound: Subscriber gestoppt")

    async def _subscribe_loop(self) -> None:
        """Subscribe-Loop mit Auto-Reconnect."""
        while self._running:
            try:
                async with aiomqtt.Client(
                    hostname=self.host,
                    port=self.port,
                    username=self.username,
                    password=self.password,
                ) as client:
                    await client.subscribe("eedc/+/live/#")
                    await client.subscribe("eedc/+/energy/#")
                    logger.info("MQTT-Inbound: Subscribed auf eedc/+/live/# und eedc/+/energy/#")
                    self.cache.verbinden()

                    async for message in client.messages:
                        if not self._running:
                            break
                        topic = str(message.topic)
                        payload = message.payload.decode("utf-8", errors="replace") if isinstance(message.payload, bytes) else str(message.payload)
                        self.cache.on_message(topic, payload)

            except asyncio.CancelledError:
                self.cache.trennen()
                break
            except Exception as e:
                self.cache.trennen()
                if self._running:
                    logger.warning("MQTT-Inbound: Verbindung verloren (%s), Reconnect in 10s...", e)
                    await log_activity(
                        kategorie="mqtt",
                        aktion="MQTT-Inbound Verbindung verloren",
                        erfolg=False,
                        details=f"{type(e).__name__}: {e}",
                    )
                    await asyncio.sleep(10)

    def get_status(self) -> dict:
        """Gibt den Status des Services + Cache zurück."""
        status = self.cache.get_status()
        status["subscriber_aktiv"] = self._running
        status["broker"] = f"{self.host}:{self.port}"
        return status


# Singleton
_mqtt_inbound_service: Optional[MqttInboundService] = None


def get_mqtt_inbound_service() -> Optional[MqttInboundService]:
    """Gibt die Singleton-Instanz zurück (None wenn nicht initialisiert)."""
    return _mqtt_inbound_service


def init_mqtt_inbound_service(
    host: str, port: int,
    username: Optional[str] = None,
    password: Optional[str] = None,
) -> MqttInboundService:
    """Erstellt und speichert die Singleton-Instanz."""
    global _mqtt_inbound_service
    _mqtt_inbound_service = MqttInboundService(host, port, username, password)
    return _mqtt_inbound_service
