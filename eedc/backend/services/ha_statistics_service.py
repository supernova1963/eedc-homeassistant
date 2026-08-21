"""
HA Statistics Service - Liest historische Daten aus der Home Assistant Langzeitstatistik.

Ermöglicht:
- Monatswerte aus HA-Langzeitstatistiken abrufen
- Alle verfügbaren Monate seit Installationsdatum ermitteln
- MQTT-Startwerte basierend auf historischen Daten initialisieren

Die HA-Datenbank enthält in der `statistics` Tabelle stündliche Aggregationen
für Sensoren mit `has_sum=True` (typisch für kWh-Zähler).

**Drei gleichwertige Transporte, eine Quelle** (Reihenfolge = Vorrang):

1. `HA_RECORDER_DB_URL` — externer Recorder (MariaDB/MySQL), per SQL.
2. Recorder-**Datei** `/config/home-assistant_v2.db` — im Add-on eingehängt, per SQL.
3. **WebSocket** `recorder/statistics_during_period` — braucht weder Datei noch
   DB-Zugang, nur die HA-Verbindung samt Token (`services/ha_statistics_ws.py`).

Die beiden SQL-Wege behalten den Vorrang, wo sie verfügbar sind: sie sind
synchron, gehen nicht übers Netz und lesen gebündelt. Fehlt beides, trägt der
WebSocket-Weg **dieselbe** Quelle — er liest `sum` · `state` · `mean` · `min` ·
`max` aus derselben Recorder-Statistik, nur über HAs API statt über die Tabelle.
Für den Standalone-Container neben einer HA-Instanz ist er der einzige Weg zur
Historie; vorher entstanden Tageswerte dort ausschließlich aus eedcs eigenen
5-Minuten-Snapshots, also ab Installation vorwärts.

⚠ **Was auch der WebSocket-Weg nicht kann:** weiter zurückreichen als HA selbst.
Die LTS beginnt mit der Existenz des Sensors. Für die Zeit davor bleibt der
Datei-Import die Antwort.
"""

import logging
import time
from contextlib import contextmanager
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Optional, NamedTuple

from pydantic import BaseModel
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from backend.core.config import settings
from backend.core.berechnungen.slot_konvention import lts_boundary_index

if TYPE_CHECKING:  # pragma: no cover — nur für die Typprüfung
    from backend.services.ha_statistics_ws import HAStatisticsWebsocket

logger = logging.getLogger(__name__)

# Pfad zur HA-Datenbank (im Add-on Container)
HA_DB_PATH = Path("/config/home-assistant_v2.db")

# Lokaler Entwicklungsmodus - alternativer Pfad
HA_DB_PATH_LOCAL = Path("/home/gernot/ha-db/home-assistant_v2.db")  # Falls kopiert für Tests


class SensorMonatswert(BaseModel):
    """Monatswert für einen einzelnen Sensor."""
    sensor_id: str
    start_wert: float
    end_wert: float
    differenz: float
    einheit: str = "kWh"


class MonatswertResponse(BaseModel):
    """Alle Monatswerte für einen bestimmten Monat."""
    jahr: int
    monat: int
    monat_name: str
    sensoren: list[SensorMonatswert]
    abfrage_zeitpunkt: datetime


class VerfuegbarerMonat(BaseModel):
    """Ein verfügbarer Monat mit Daten."""
    jahr: int
    monat: int
    monat_name: str
    hat_daten: bool = True


class AlleMonateResponse(BaseModel):
    """Übersicht aller verfügbaren Monate."""
    erstes_datum: date
    letztes_datum: date
    anzahl_monate: int
    monate: list[VerfuegbarerMonat]


class SensorMeta(NamedTuple):
    """Metadata eines Sensors aus statistics_meta."""
    id: int
    unit: Optional[str]
    has_sum: bool


# Konvertierungsfaktoren nach kWh
_ENERGY_UNIT_TO_KWH: dict[str, float] = {
    "kWh": 1.0,
    "Wh": 0.001,
    "MWh": 1000.0,
    "GWh": 1_000_000.0,
}

# statistics_short_term-Slotlänge (HA-Recorder schreibt 5-Min-Aggregate).
SHORT_TERM_SLOT = 5


def _unix(dt: datetime) -> float:
    """Lokale naive `datetime` → Unix-Timestamp, wie ihn HA in `start_ts` führt.

    **Warum das an jeder Filter-Stelle stehen muss:** der Recorder-Index heißt
    `(metadata_id, start_ts)`. Sobald die Spalte in einer Funktion steckt —
    `FROM_UNIXTIME(start_ts) >= :von` bzw. `datetime(start_ts,'unixepoch',
    'localtime')` — kann weder MariaDB noch SQLite den Zeitbereich über den
    Index eingrenzen: gelesen werden **alle** Zeilen des Sensors, die Funktion
    läuft je Zeile, danach wird sortiert. Vergleicht man stattdessen den rohen
    Timestamp, greift der Index.

    Nebenwirkung, bewusst in Kauf genommen: `FROM_UNIXTIME` rechnet in der
    **Session-Zeitzone der Datenbank**, `mktime` in der des eedc-Prozesses.
    Standen die beiden auseinander (MariaDB auf UTC, Container auf
    Europe/Berlin), lieferten die Monats-Queries bisher einen um den
    Zonen-Versatz verschobenen Ausschnitt. Ab jetzt gilt durchgehend die
    Zeitzone von eedc — dieselbe, in der die Aufrufer ihre Grenzen bilden.
    """
    return dt.timestamp()


def _monatsgrenzen_ts(jahr: int, monat: int) -> tuple[float, float]:
    """(Beginn, Ende) eines Monats als Unix-Timestamps; Ende exklusiv."""
    start = datetime(jahr, monat, 1)
    ende = datetime(jahr + 1, 1, 1) if monat == 12 else datetime(jahr, monat + 1, 1)
    return _unix(start), _unix(ende)


def _snap_to_slot(dt: datetime, slot_minuten: int) -> datetime:
    """Rundet einen Zeitstempel auf das nächste Slot-Raster (Sekunden=0).

    HA-`start_ts` liegen i. d. R. exakt auf der 5-Min-Grenze, können aber durch
    Recorder-Latenz minimal driften (z. B. H:00:01). Das Snapping garantiert
    exakte Schlüssel, damit das Delta ``sum@t − sum@(t−5min)`` den Vorgänger-Slot
    sicher findet.
    """
    basis = dt.replace(second=0, microsecond=0)
    rest = basis.minute % slot_minuten
    gerundet = basis - timedelta(minutes=rest)
    if rest * 2 >= slot_minuten:  # aufrunden ab Hälfte
        gerundet += timedelta(minutes=slot_minuten)
    return gerundet


class HAStatisticsService:
    """Service für Zugriff auf HA-Langzeitstatistiken (SQLite oder MariaDB)."""

    MONAT_NAMEN = [
        "", "Januar", "Februar", "März", "April", "Mai", "Juni",
        "Juli", "August", "September", "Oktober", "November", "Dezember"
    ]

    # Kurz genug, dass ein nachgetragenes `state_class` zeitnah wirkt.
    _META_CACHE_TTL = 300

    def __init__(self):
        self._engine: Optional[Engine] = None
        self._is_mysql: bool = False
        self._initialized: bool = False
        # statistic_id → (zeitpunkt, SensorMeta). Nur Treffer, siehe get_metadata.
        self._meta_cache: dict[str, tuple[float, SensorMeta]] = {}
        # WebSocket-Transport (dritter Weg, nur ohne DB-Zugang) — siehe
        # `setze_ha_verbindung`. Die Ersatz-IDs füllen `SensorMeta.id`, das dort
        # keine Entsprechung hat: die WS-Antwort ist bereits nach statistic_id
        # geschlüsselt, aber der übrige Code erwartet das Feld.
        self._ws_client: Optional["HAStatisticsWebsocket"] = None
        self._ws_ersatz_ids: dict[str, int] = {}
        self._ws_status: Optional[tuple[float, bool]] = None

    def setze_ha_verbindung(self, api_url: Optional[str], token: Optional[str]) -> None:
        """Meldet die aktive HA-Verbindung für den WebSocket-Transport.

        Gerufen beim Start und bei jeder Änderung der HA-Verbindung (siehe
        `api/routes/ha_remote.py`). Ohne DB-Zugang wird daraus der dritte
        Transport; mit DB-Zugang bleibt es folgenlos, weil SQL den Vorrang hat.

        ⚠ Der Service kann die Verbindung **nicht selbst** nachschlagen:
        `resolve_ha_connection` ist async und braucht eine DB-Session, während
        hier jede Methode synchron ist. Ihn aus dem WS-Brücken-Thread heraus zu
        rufen wäre die falsche Antwort — aiosqlite-Verbindungen sind an ihren
        Event-Loop gebunden. Deshalb wird die Verbindung hereingereicht.
        """
        alt = self._ws_client
        if alt is not None:
            alt.schliessen()
        self._ws_client = None
        self._ws_status = None
        self._meta_cache.clear()
        if api_url and token:
            from backend.services.ha_statistics_ws import HAStatisticsWebsocket

            self._ws_client = HAStatisticsWebsocket(api_url, token)
        # Erneut auflösen: ohne DB kann sich die Verfügbarkeit gerade geändert haben.
        self._initialized = False

    @property
    def _ws(self) -> Optional["HAStatisticsWebsocket"]:
        """Der WS-Transport — nur wenn keine Datenbank erreichbar ist.

        Die Reihenfolge steht hier und nirgends sonst: erst SQL, dann WebSocket.
        """
        self._init_engine()
        if self._engine is not None:
            return None
        return self._ws_client

    def _init_engine(self) -> None:
        """Initialisiert die SQLAlchemy Engine (einmalig)."""
        if self._initialized:
            return
        self._initialized = True

        # Priorität: Konfigurierte MariaDB URL → SQLite-Datei
        if settings.ha_recorder_db_url:
            url = settings.ha_recorder_db_url
            # Auto-Treiber-Mapping: SQLAlchemy will bei `mysql://...` das
            # C-Modul `MySQLdb` (mysqlclient) laden, das im Add-on-Image nicht
            # installiert ist. Nur `pymysql` ist enthalten (siehe requirements.txt).
            # Anwender tragen aber natürlich `mysql://user:pass@host/db` ein
            # (wie es die HA-Recorder-Doku zeigt) und bekamen dann
            # `ModuleNotFoundError: No module named 'MySQLdb'` (#251 FrodoVDR).
            # Diese Schreibweisen werden auf den vorhandenen Treiber umgebogen.
            if url.startswith("mysql://"):
                url = "mysql+pymysql://" + url[len("mysql://"):]
            elif url.startswith("mariadb://"):
                url = "mariadb+pymysql://" + url[len("mariadb://"):]
            try:
                self._engine = create_engine(
                    url,
                    pool_pre_ping=True,
                    pool_recycle=3600,
                )
                self._is_mysql = "mysql" in url or "mariadb" in url
                # Verbindungstest
                with self._engine.connect() as conn:
                    conn.execute(text("SELECT 1"))
                logger.info(
                    f"HA Recorder DB verbunden: "
                    f"{'MariaDB/MySQL' if self._is_mysql else 'extern'}"
                )
                return
            except Exception as e:
                logger.warning(f"HA Recorder DB Verbindung fehlgeschlagen: {type(e).__name__}: {e}")
                self._engine = None

        # Fallback: SQLite-Datei
        db_path = None
        if HA_DB_PATH.exists():
            db_path = HA_DB_PATH
        elif HA_DB_PATH_LOCAL.exists():
            db_path = HA_DB_PATH_LOCAL
            logger.info("Verwende lokale HA-Datenbank-Kopie für Tests")

        if db_path:
            self._engine = create_engine(
                f"sqlite:///{db_path}",
                connect_args={"timeout": 30},
            )
            self._is_mysql = False

    def _ws_verfuegbar(self) -> bool:
        """Antwortet der WebSocket-Transport? Ergebnis wird kurz gemerkt.

        Ohne dieses Merken zahlte **jeder** `is_available`-Aufruf einen
        Verbindungsversuch — bei nicht erreichbarer HA also je Aufruf den
        vollen Verbindungs-Timeout. `is_available` steht am Anfang fast jeder
        Lesemethode.
        """
        client = self._ws_client
        if client is None:
            return False
        jetzt = time.monotonic()
        gemerkt = self._ws_status
        if gemerkt is not None and (jetzt - gemerkt[0]) < self._META_CACHE_TTL:
            return gemerkt[1]
        erreichbar = client.erreichbar()
        self._ws_status = (jetzt, erreichbar)
        return erreichbar

    @property
    def is_available(self) -> bool:
        """Prüft ob die HA-Langzeitstatistik erreichbar ist — per DB **oder** WebSocket."""
        self._init_engine()
        if self._engine is not None:
            return True
        return self._ws_verfuegbar()

    @property
    def db_path(self) -> Optional[str]:
        """Gibt den DB-Pfad/URL bzw. die WS-Adresse für Status-Anzeige zurück."""
        self._init_engine()
        if self._engine is None:
            # Ohne Datenbank ist die Herkunft die HA-API — und sie zu benennen
            # ist der Unterschied zwischen „nicht verfügbar" und „anderer Weg".
            if self._ws_verfuegbar() and self._ws_client is not None:
                return self._ws_client.ws_url
            return None
        url = str(self._engine.url)
        # Passwort maskieren
        if "@" in url:
            # mysql+pymysql://user:pass@host/db → mysql+pymysql://user:***@host/db
            prefix, rest = url.split("@", 1)
            if ":" in prefix.rsplit("/", 1)[-1]:
                base = prefix.rsplit(":", 1)[0]
                url = f"{base}:***@{rest}"
        return url

    @property
    def backend_type(self) -> str:
        """Gibt den genutzten Transport zurück."""
        if not self.is_available:
            return "nicht verfügbar"
        if self._engine is None:
            return "HA-WebSocket"
        return "MariaDB/MySQL" if self._is_mysql else "SQLite"

    def count_statistics_sensors(self) -> int:
        """Zählt die Anzahl der Sensoren in statistics_meta."""
        if not self.is_available:
            return 0
        ws = self._ws
        if ws is not None:
            try:
                return len(ws.metadaten())
            except Exception:
                return 0
        try:
            with self._engine.connect() as conn:
                result = conn.execute(text("SELECT COUNT(*) FROM statistics_meta"))
                row = result.fetchone()
                return row[0] if row else 0
        except Exception:
            return 0

    # ------------------------------------------------------------------
    # Zeilen-Beschaffung — die einzige Stelle, an der sich die Transporte
    # unterscheiden. Alles darüber (Einheitenumrechnung, Boundary-Index,
    # Slot-Konvention, Delta-Bildung) rechnet auf demselben Ergebnis.
    # ------------------------------------------------------------------

    def _ws_zeilen(
        self,
        sensor_ids: list[str],
        ts_von: float,
        ts_bis: float,
        *,
        short_term: bool = False,
        types: Optional[list[str]] = None,
    ) -> dict[str, list[dict]]:
        """Statistik-Zeilen über den WebSocket-Transport.

        `ts_von`/`ts_bis` sind dieselben Unix-Sekunden, mit denen die SQL-Pfade
        gegen `start_ts` filtern — die WS-Antwort wird auf genau diese Größe
        zurückgerechnet. Deshalb bleibt jede Nachverarbeitung identisch.

        Das Fenster ist beidseitig **inklusiv** wie die SQL-Varianten mit
        `<= :ts_bis`: HA schließt `end_time` aus, also wird eine Slotlänge
        aufgeschlagen und danach exakt beschnitten.
        """
        ws = self._ws
        if ws is None or not sensor_ids:
            return {}
        period = "5minute" if short_term else "hour"
        schritt = SHORT_TERM_SLOT * 60 if short_term else 3600
        # ⚠ Ein Netzfehler wird **nicht** hier zu einem leeren Ergebnis gemacht.
        # „Keine Zeilen“ und „nicht gefragt werden können“ sind zwei Lagen: wer
        # sie gleichsetzt, liefert dem Aufrufer eine Null, wo eine Lücke ist —
        # genau die Klasse, die den Hausverbrauch schon einmal still auf 0
        # gezogen hat. Die Lesemethoden fangen die Ausnahme dort, wo sie auch
        # einen SQL-Fehler fangen, und liefern dann ihren eigenen Leerwert.
        roh = ws.statistiken(
            sensor_ids,
            datetime.fromtimestamp(ts_von),
            datetime.fromtimestamp(ts_bis + schritt),
            period=period,
            types=types or ["sum", "state", "mean", "min", "max"],
        )
        return {
            sid: [z for z in zeilen if ts_von <= z["start_ts"] <= ts_bis]
            for sid, zeilen in roh.items()
        }

    @contextmanager
    def _verbindung(self):
        """Datenbank-Verbindung — oder `None`, wenn über WebSocket gelesen wird.

        Damit bleibt die Form `with self._verbindung() as conn:` in allen
        Lesemethoden erhalten; `conn is None` heißt „nimm den WS-Zweig".
        """
        if self._engine is not None:
            with self._engine.connect() as conn:
                yield conn
        else:
            yield None

    def _ws_flachzeilen(
        self,
        sensor_ids: list[str],
        ts_von: float,
        ts_bis: float,
        *,
        felder: tuple[str, ...],
        short_term: bool = False,
    ) -> list[tuple]:
        """WS-Zeilen in der Tupel-Form der SQL-Abfragen mit `JOIN statistics_meta`.

        Liefert `(statistic_id, start_ts, *felder, unit_of_measurement)`, sortiert
        nach Sensor und Zeit — dasselbe, was `SELECT sm.statistic_id, s.start_ts,
        …, sm.unit_of_measurement … ORDER BY sm.statistic_id, s.start_ts` ergibt.
        So bleibt die auswertende Schleife für beide Transporte dieselbe.
        """
        zeilen = self._ws_zeilen(
            sensor_ids, ts_von, ts_bis, short_term=short_term, types=list(felder),
        )
        ergebnis: list[tuple] = []
        for sensor_id in sorted(zeilen):
            meta = self._ws_meta(sensor_id)
            unit = meta.unit if meta else None
            for zeile in zeilen[sensor_id]:
                ergebnis.append(
                    (sensor_id, zeile["start_ts"], *(zeile.get(f) for f in felder), unit)
                )
        return ergebnis

    def _ws_meta(self, sensor_id: str) -> Optional[SensorMeta]:
        """`SensorMeta` aus den WS-Metadaten — Gegenstück zu `statistics_meta`."""
        ws = self._ws
        if ws is None:
            return None
        try:
            alle = ws.metadaten()
        except Exception as e:  # noqa: BLE001
            logger.warning("HA-Statistik-Metadaten nicht abrufbar: %s", e)
            return None
        eintrag = alle.get(sensor_id)
        if eintrag is None:
            return None
        # `metadata_id` gibt es über die API nicht — die Antwort ist bereits nach
        # statistic_id geschlüsselt. Eine stabile Ersatz-Nummer hält die
        # bestehenden Rückwärts-Zuordnungen (`meta_id_to_sensor`) am Leben.
        ersatz = self._ws_ersatz_ids.setdefault(sensor_id, len(self._ws_ersatz_ids) + 1)
        return SensorMeta(id=ersatz, unit=eintrag.unit, has_sum=eintrag.has_sum)

    # `_ts_to_datetime` / `_ts_to_date` sind hier bewusst **nicht** mehr
    # vorhanden. Sie erzeugten `FROM_UNIXTIME(start_ts)` bzw.
    # `datetime(start_ts,'unixepoch','localtime')` — und jede WHERE-Bedingung,
    # die damit gebaut wurde, verlor den Index auf `start_ts` (siehe `_unix`).
    # Zeitgrenzen werden in Python zu Unix-Timestamps gerechnet und roh
    # verglichen; für die Rückrichtung genügt `datetime.fromtimestamp`.

    def get_metadata(self, conn, sensor_id: str) -> Optional[SensorMeta]:
        """
        Ermittelt metadata_id und unit_of_measurement für einen Sensor.

        Args:
            conn: SQLAlchemy Connection
            sensor_id: HA Entity-ID (z.B. "sensor.pv_erzeugung")

        Returns:
            SensorMeta oder None wenn Sensor nicht in statistics

        Gefundene Sensoren werden `_META_CACHE_TTL` lang gemerkt. Der
        Snapshot-Job ruft diese Auflösung je Zähler und Lauf auf, unmittelbar
        vor der eigentlichen Wertabfrage — das war je Wert eine zweite
        Rundreise zur Datenbank. Sie war nie teuer (Unique-Index auf einer
        kleinen Tabelle), aber sie war überflüssig.

        **Nicht gemerkt wird ein Fehlschlag.** Ein Sensor taucht in
        `statistics_meta` genau dann auf, wenn der Anwender `state_class`
        nachträgt — und dann soll der Daten-Checker das beim nächsten Lauf
        sehen und nicht erst nach Ablauf eines Caches. Aus demselben Grund ist
        der TTL kurz: `unit_of_measurement` und `has_sum` derselben Entity
        können sich durch genau solche Korrekturen ändern.
        """
        jetzt = time.monotonic()
        gemerkt = self._meta_cache.get(sensor_id)
        if gemerkt is not None and (jetzt - gemerkt[0]) < self._META_CACHE_TTL:
            return gemerkt[1]

        # Ohne Datenbank steht `conn` auf None — dann kommt die Auskunft aus
        # `recorder/list_statistic_ids` statt aus `statistics_meta`.
        if conn is None:
            meta_ws = self._ws_meta(sensor_id)
            if meta_ws is None:
                logger.debug(f"Sensor '{sensor_id}' nicht in der HA-Statistik gefunden")
                return None
            self._meta_cache[sensor_id] = (jetzt, meta_ws)
            return meta_ws

        result = conn.execute(
            text(
                "SELECT id, unit_of_measurement, has_sum "
                "FROM statistics_meta WHERE statistic_id = :sid"
            ),
            {"sid": sensor_id}
        )
        row = result.fetchone()
        if not row:
            logger.debug(f"Sensor '{sensor_id}' nicht in statistics_meta gefunden")
            return None
        meta = SensorMeta(id=row[0], unit=row[1], has_sum=bool(row[2]))
        self._meta_cache[sensor_id] = (jetzt, meta)
        return meta

    def filter_valid_sensor_ids(self, sensor_ids: list[str]) -> tuple[list[str], list[str]]:
        """
        Prüft welche Sensor-IDs tatsächlich in statistics_meta vorhanden sind.

        Returns:
            (valid_ids, missing_ids)
        """
        valid, missing = [], []
        with self._verbindung() as conn:
            for sid in sensor_ids:
                if self.get_metadata(conn, sid):
                    valid.append(sid)
                else:
                    missing.append(sid)
        return valid, missing

    def filter_summen_faehige_sensor_ids(
        self, sensor_ids: list[str],
    ) -> tuple[list[str], list[str], list[str]]:
        """Teilt Sensor-IDs nach ihrer Eignung als **Energie-Zähler** auf.

        Schärfer als `filter_valid_sensor_ids`: dort genügt ein Eintrag in
        `statistics_meta`. Für kWh-/Counter-Felder reicht das nicht — ohne
        `has_sum` überspringt `get_hourly_kwh_deltas_for_day` **jede Zeile**
        des Sensors (`continue`), er fehlt danach im Ergebnis, und Tages- wie
        Stundenwerte bleiben leer.

        Von außen ist dieser Zustand nicht von „Sensor gar nicht zugeordnet"
        zu unterscheiden: HA legt auch für `state_class: measurement` eine
        `statistics_meta`-Zeile an (mean/min/max), nur eben ohne Summen-Spalte.
        Ein Prüfer, der nur die Existenz abfragt, meldet deshalb „alles in
        Ordnung", während Cockpit/Tag auf 0 steht — Forum simon42 #89667/44,
        Gerätefamilie bitShake/Tasmota, wo `state_class` von Hand nachgetragen
        wird und `measurement` statt `total_increasing` der bekannte Griff
        daneben ist.

        `filter_valid_sensor_ids` bleibt bewusst unverändert — der Live-Backfill
        (`energie_profil/backfill.py`) prüft damit **W-Sensoren**, die
        korrekterweise kein `has_sum` haben.

        Returns:
            (mit_sum, ohne_sum, fehlend) — Reihenfolge der Eingabe bleibt erhalten.
        """
        mit_sum: list[str] = []
        ohne_sum: list[str] = []
        fehlend: list[str] = []
        with self._verbindung() as conn:
            for sid in sensor_ids:
                meta = self.get_metadata(conn, sid)
                if meta is None:
                    fehlend.append(sid)
                elif meta.has_sum:
                    mit_sum.append(sid)
                else:
                    ohne_sum.append(sid)
        return mit_sum, ohne_sum, fehlend

    def get_sensor_monatswert(
        self,
        conn,
        meta: SensorMeta,
        sensor_id: str,
        jahr: int,
        monat: int
    ) -> Optional[SensorMonatswert]:
        """
        Ermittelt den Monatswert für einen Sensor.

        Bevorzugt MAX(sum) - MIN(sum) (HA's eigene reset-bereinigte Kumulation
        für total_increasing-Sensoren — funktioniert auch bei Tagesreset-
        Zählern und Mehrfach-Resets im Monat). Fallback auf MAX(state) - MIN(state)
        wenn `sum` nicht verfügbar (z.B. measurement-Sensoren ohne has_sum).

        Hintergrund: state-Differenz war früher der einzige Pfad, liefert aber
        bei Tagesreset-Zählern fälschlich die größte Tagessumme im Monat statt
        der Monatssumme (Discussion #131). HA's `sum`-Spalte wird automatisch
        bei jedem Reset um den vorigen Endwert weitergeführt — exakt das, was
        das HA-Energy-Dashboard intern auch nutzt.

        Werte werden automatisch nach kWh konvertiert (Wh, MWh, etc.).
        """
        ts_start, ts_ende = _monatsgrenzen_ts(jahr, monat)

        if conn is None:
            # Ohne Datenbank rechnet Python die vier Aggregate — `period=month`
            # taugt hier NICHT: HA liefert dort den Wert am Perioden-**Ende**,
            # gebraucht wird aber MAX−MIN **innerhalb** des Monats. Ein anderer
            # Bezugspunkt wäre eine andere Zahl, nicht dieselbe über ein anderes
            # Kabel.
            zeilen = self._ws_zeilen(
                [sensor_id], ts_start, ts_ende - 1, types=["sum", "state"],
            ).get(sensor_id, [])
            states = [z["state"] for z in zeilen if z["state"] is not None]
            sums = [z["sum"] for z in zeilen if z["sum"] is not None]
            if not states and not sums:
                return None
            state_min = min(states) if states else None
            state_max = max(states) if states else None
            sum_min = min(sums) if sums else None
            sum_max = max(sums) if sums else None
        else:
            result = conn.execute(
                text("""
                    SELECT
                        MIN(state) as state_min,
                        MAX(state) as state_max,
                        MIN(sum)   as sum_min,
                        MAX(sum)   as sum_max
                    FROM statistics
                    WHERE metadata_id = :mid
                    AND start_ts >= :start
                    AND start_ts < :end
                """),
                {"mid": meta.id, "start": ts_start, "end": ts_ende}
            )

            row = result.fetchone()
            if not row or (row[0] is None and row[2] is None):
                return None

            state_min, state_max, sum_min, sum_max = row[0], row[1], row[2], row[3]

        # Bevorzugt sum-basiert (reset-bereinigt), Fallback state-basiert
        if sum_min is not None and sum_max is not None:
            start_wert = sum_min
            end_wert = sum_max
        else:
            start_wert = state_min
            end_wert = state_max
        differenz = end_wert - start_wert

        # Einheiten-Konvertierung nach kWh
        faktor = _ENERGY_UNIT_TO_KWH.get(meta.unit, 1.0) if meta.unit else 1.0
        if faktor != 1.0:
            logger.info(f"Sensor {sensor_id}: Konvertiere {meta.unit} → kWh (Faktor {faktor})")
            start_wert *= faktor
            end_wert *= faktor
            differenz *= faktor

        return SensorMonatswert(
            sensor_id=sensor_id,
            start_wert=round(start_wert, 3),
            end_wert=round(end_wert, 3),
            differenz=round(differenz, 2)
        )

    def get_monatswerte(
        self,
        sensor_ids: list[str],
        jahr: int,
        monat: int
    ) -> MonatswertResponse:
        """Holt Monatswerte für mehrere Sensoren."""
        if not self.is_available:
            raise RuntimeError("HA-Datenbank nicht verfügbar")

        sensoren: list[SensorMonatswert] = []

        with self._verbindung() as conn:
            for sensor_id in sensor_ids:
                meta = self.get_metadata(conn, sensor_id)
                if meta is None:
                    logger.warning(f"Sensor {sensor_id} nicht in HA statistics gefunden")
                    continue

                wert = self.get_sensor_monatswert(conn, meta, sensor_id, jahr, monat)
                if wert:
                    sensoren.append(wert)

        return MonatswertResponse(
            jahr=jahr,
            monat=monat,
            monat_name=self.MONAT_NAMEN[monat],
            sensoren=sensoren,
            abfrage_zeitpunkt=datetime.now()
        )

    def get_verfuegbare_monate(self, sensor_ids: list[str]) -> AlleMonateResponse:
        """Ermittelt alle Monate mit verfügbaren Daten."""
        if not self.is_available:
            raise RuntimeError("HA-Datenbank nicht verfügbar")

        with self._verbindung() as conn:
            # Metadata-IDs ermitteln
            metadata_ids = []
            nicht_gefunden = []
            for sensor_id in sensor_ids:
                meta = self.get_metadata(conn, sensor_id)
                if meta:
                    metadata_ids.append(meta.id)
                else:
                    nicht_gefunden.append(sensor_id)

            if nicht_gefunden:
                logger.warning(
                    f"Sensoren nicht in HA statistics_meta gefunden: {nicht_gefunden}. "
                    f"Ist der HA Recorder auf diese Datenbank konfiguriert?"
                )

            if not metadata_ids:
                raise ValueError(
                    f"Keiner der zugeordneten Sensoren ({', '.join(sensor_ids)}) wurde in der "
                    f"HA-Datenbank gefunden. Bitte prüfen: Ist der HA Recorder auf diese "
                    f"Datenbank konfiguriert (configuration.yaml → recorder → db_url)?"
                )

            if conn is None:
                grenzen = self._ws_zeitraum(
                    [sid for sid in sensor_ids if sid not in nicht_gefunden]
                )
                if grenzen is None:
                    raise ValueError(
                        "Sensoren in der HA-Statistik gefunden, aber keine Messwerte vorhanden"
                    )
                row_grenzen = grenzen
                return self._monatsliste(row_grenzen[0], row_grenzen[1])

            # Zeitraum ermitteln — IN-Klausel mit benannten Parametern
            params = {f"id_{i}": mid for i, mid in enumerate(metadata_ids)}
            placeholders = ", ".join(f":id_{i}" for i in range(len(metadata_ids)))

            # Ein Aggregat statt zweier sortierter Abfragen. `ORDER BY start_ts
            # LIMIT 1` über eine IN-Liste kann den Index `(metadata_id,
            # start_ts)` nicht zum Sortieren nutzen — er ist je metadata_id
            # sortiert, nicht darüber hinweg —, also sortierte die Datenbank
            # zweimal alle Zeilen aller beteiligten Sensoren. MIN/MAX auf der
            # rohen Spalte liest der Optimizer aus dem Index.
            result = conn.execute(
                text(f"""
                    SELECT MIN(start_ts) as erstes, MAX(start_ts) as letztes
                    FROM statistics
                    WHERE metadata_id IN ({placeholders})
                """),
                params
            )
            row_grenzen = result.fetchone()

            if not row_grenzen or row_grenzen[0] is None or row_grenzen[1] is None:
                raise ValueError(
                    f"Sensoren in statistics_meta gefunden, aber keine Messwerte in der "
                    f"statistics-Tabelle vorhanden"
                )

            return self._monatsliste(row_grenzen[0], row_grenzen[1])

    def _monatsliste(self, erstes_ts: float, letztes_ts: float) -> AlleMonateResponse:
        """Baut die Monatsliste aus erstem und letztem Messzeitpunkt.

        Bewusst gemeinsam für beide Transporte: welche Monate als „verfügbar"
        gelten und dass der laufende Monat draußen bleibt, ist eine fachliche
        Festlegung — sie darf nicht davon abhängen, über welches Kabel die
        Grenzen kamen.
        """
        erstes = datetime.fromtimestamp(erstes_ts).date()
        letztes = datetime.fromtimestamp(letztes_ts).date()

        # Aktuellen (unvollständigen) Monat ausschließen
        today = date.today()
        first_of_current_month = date(today.year, today.month, 1)
        if letztes >= first_of_current_month:
            # Auf Vormonat begrenzen
            if first_of_current_month.month == 1:
                letztes = date(first_of_current_month.year - 1, 12, 1)
            else:
                letztes = date(first_of_current_month.year, first_of_current_month.month - 1, 1)

        # Alle Monate im Zeitraum generieren
        monate: list[VerfuegbarerMonat] = []
        current = date(erstes.year, erstes.month, 1)
        end = date(letztes.year, letztes.month, 1)

        while current <= end:
            monate.append(VerfuegbarerMonat(
                jahr=current.year,
                monat=current.month,
                monat_name=self.MONAT_NAMEN[current.month]
            ))
            if current.month == 12:
                current = date(current.year + 1, 1, 1)
            else:
                current = date(current.year, current.month + 1, 1)

        return AlleMonateResponse(
            erstes_datum=erstes,
            letztes_datum=letztes,
            anzahl_monate=len(monate),
            monate=monate
        )

    def _ws_zeitraum(self, sensor_ids: list[str]) -> Optional[tuple[float, float]]:
        """Erster und letzter Messzeitpunkt über den WebSocket-Transport.

        `MIN/MAX(start_ts)` hat über die API kein Gegenstück. Statt die ganze
        Historie stündlich zu laden (Jahre × 8760 Zeilen je Sensor) wird sie
        **monatsweise** abgefragt — leere Monate liefern nichts, belegte je eine
        Zeile. Für den ersten und den letzten belegten Monat folgt eine
        tagesgenaue Abfrage, damit `erstes_datum`/`letztes_datum` denselben
        Tag nennen wie der SQL-Weg und nicht nur den Monatsersten.
        """
        ws = self._ws
        if ws is None or not sensor_ids:
            return None
        # 2015 ist großzügig unterhalb jeder HA-Installation; leere Monate
        # kosten nichts, weil HA sie gar nicht erst zurückgibt.
        anfang = datetime(2015, 1, 1)
        ende = datetime.now() + timedelta(days=1)
        try:
            monate = ws.statistiken(sensor_ids, anfang, ende, "month", ["sum", "state"])
        except Exception as e:  # noqa: BLE001
            logger.warning("HA-Statistik-Zeitraum nicht ermittelbar: %s", e)
            return None
        starts = [z["start_ts"] for zeilen in monate.values() for z in zeilen]
        if not starts:
            return None

        def _tagesgenau(monats_ts: float, letzter: bool) -> float:
            """Ersten bzw. letzten belegten Tag innerhalb eines Monats finden."""
            monats_start = datetime.fromtimestamp(monats_ts).replace(
                day=1, hour=0, minute=0, second=0, microsecond=0,
            )
            naechster = (monats_start + timedelta(days=32)).replace(day=1)
            try:
                tage = ws.statistiken(sensor_ids, monats_start, naechster, "day", ["sum", "state"])
            except Exception:  # noqa: BLE001 — Monatsanfang ist ein brauchbarer Rückfall
                return monats_ts
            treffer = [z["start_ts"] for zeilen in tage.values() for z in zeilen]
            if not treffer:
                return monats_ts
            return max(treffer) if letzter else min(treffer)

        return _tagesgenau(min(starts), letzter=False), _tagesgenau(max(starts), letzter=True)

    def get_alle_monatswerte(
        self,
        sensor_ids: list[str],
        ab_datum: Optional[date] = None
    ) -> list[MonatswertResponse]:
        """Holt Monatswerte für alle verfügbaren Monate."""
        verfuegbar = self.get_verfuegbare_monate(sensor_ids)

        ergebnisse: list[MonatswertResponse] = []
        for monat_info in verfuegbar.monate:
            if ab_datum:
                monat_start = date(monat_info.jahr, monat_info.monat, 1)
                if monat_start < ab_datum:
                    continue

            werte = self.get_monatswerte(sensor_ids, monat_info.jahr, monat_info.monat)
            if werte.sensoren:
                ergebnisse.append(werte)

        return ergebnisse

    def get_hourly_sensor_data(
        self,
        sensor_ids: list[str],
        von: date,
        bis: date,
    ) -> dict[str, dict[str, dict[int, float]]]:
        """
        Holt stündliche Mittelwerte (mean) für Leistungs- und SoC-Sensoren.

        Geeignet für Backfill des Energieprofils aus HA Long-Term Statistics.
        Nur für Sensoren mit has_mean=True (W, kW, %).
        kWh-Zähler (has_sum) werden übersprungen (nur für Monatswerte geeignet).

        Args:
            sensor_ids: HA Entity-IDs
            von: Startdatum (inklusiv)
            bis: Enddatum (inklusiv)

        Returns:
            {entity_id: {datum_iso: {stunde_0_23: kW_oder_prozent}}}

        Einheitenumrechnung:
            W   → kW (/ 1000)
            kW  → kW (unverändert)
            %   → % (unverändert, für SoC-Sensoren)
            kWh → wird übersprungen (Zähler, kein Leistungssensor)
        """
        if not self.is_available or not sensor_ids:
            return {}

        import time as time_module
        from datetime import time, timedelta

        von_dt = datetime.combine(von, time.min)
        bis_dt = datetime.combine(bis + timedelta(days=1), time.min)
        ts_von = time_module.mktime(von_dt.timetuple())
        ts_bis = time_module.mktime(bis_dt.timetuple())

        params: dict = {f"id_{i}": sid for i, sid in enumerate(sensor_ids)}
        placeholders = ", ".join(f":id_{i}" for i in range(len(sensor_ids)))
        params["ts_von"] = ts_von
        params["ts_bis"] = ts_bis

        result: dict[str, dict[str, dict[int, float]]] = {}

        try:
            with self._verbindung() as conn:
                if conn is None:
                    rows = self._ws_flachzeilen(
                        sensor_ids, ts_von, ts_bis - 1, felder=("mean",),
                    )
                else:
                    rows = conn.execute(
                        text(f"""
                            SELECT sm.statistic_id, s.start_ts, s.mean, sm.unit_of_measurement
                            FROM statistics s
                            JOIN statistics_meta sm ON s.metadata_id = sm.id
                            WHERE sm.statistic_id IN ({placeholders})
                              AND s.start_ts >= :ts_von
                              AND s.start_ts < :ts_bis
                              AND s.mean IS NOT NULL
                            ORDER BY sm.statistic_id, s.start_ts
                        """),
                        params
                    )
                for row in rows:
                    entity_id: str = row[0]
                    start_ts: float = row[1]
                    mean: float = row[2]
                    unit: Optional[str] = row[3]
                    if mean is None:
                        continue

                    # Energie-Zähler sind für Leistungsprofile ungeeignet
                    if unit in ("kWh", "Wh", "MWh"):
                        continue

                    # Lokalzeit aus Unix-Timestamp (kein CONVERT_TZ nötig)
                    dt = datetime.fromtimestamp(start_ts)
                    datum_iso = dt.date().isoformat()
                    hour = dt.hour

                    # Einheitenumrechnung → kW
                    if unit == "W":
                        kw = mean / 1000.0
                    elif unit in ("kW", "%"):
                        kw = mean
                    else:
                        # Unbekannte Einheit → als W behandeln (konservativ)
                        logger.debug(f"Unbekannte Einheit '{unit}' für {entity_id}, behandle als W")
                        kw = mean / 1000.0

                    if entity_id not in result:
                        result[entity_id] = {}
                    if datum_iso not in result[entity_id]:
                        result[entity_id][datum_iso] = {}
                    result[entity_id][datum_iso][hour] = kw

        except Exception as e:
            logger.warning(f"get_hourly_sensor_data Fehler: {type(e).__name__}: {e}")

        return result

    def get_hourly_minmax_sensor_data(
        self,
        sensor_ids: list[str],
        von: date,
        bis: date,
    ) -> dict[str, dict[str, dict[int, dict[str, float]]]]:
        """
        Etappe 5 (v3.31.0): Liest stündliche Min/Max für Leistungssensoren.

        HA-Recorder schreibt für `has_mean=True`-Sensoren neben `mean` auch
        `min` und `max` pro Stunde — die im 5-Sekunden-State-Bucket
        beobachteten Extremwerte. Genau die richtige Quelle für
        Tages-Peak-Werte (peak_pv_kw, peak_netzbezug_kw, peak_einspeisung_kw),
        ohne dass eedc Leistungen über 10-Min-Mittel selbst rekonstruieren muss.

        Filter und Einheitenumrechnung sind identisch zu
        `get_hourly_sensor_data()`: kWh-Counter werden übersprungen, W→kW.

        Args:
            sensor_ids: HA Entity-IDs der Leistungssensoren
            von: Startdatum (inklusiv)
            bis: Enddatum (inklusiv)

        Returns:
            {entity_id: {datum_iso: {stunde_0_23: {"min": kW, "max": kW}}}}
        """
        if not self.is_available or not sensor_ids:
            return {}

        import time as time_module
        from datetime import time

        von_dt = datetime.combine(von, time.min)
        bis_dt = datetime.combine(bis + timedelta(days=1), time.min)
        ts_von = time_module.mktime(von_dt.timetuple())
        ts_bis = time_module.mktime(bis_dt.timetuple())

        params: dict = {f"id_{i}": sid for i, sid in enumerate(sensor_ids)}
        placeholders = ", ".join(f":id_{i}" for i in range(len(sensor_ids)))
        params["ts_von"] = ts_von
        params["ts_bis"] = ts_bis

        result: dict[str, dict[str, dict[int, dict[str, float]]]] = {}

        try:
            with self._verbindung() as conn:
                if conn is None:
                    rows = self._ws_flachzeilen(
                        sensor_ids, ts_von, ts_bis - 1, felder=("min", "max"),
                    )
                else:
                    rows = conn.execute(
                        text(f"""
                            SELECT sm.statistic_id, s.start_ts, s.min, s.max, sm.unit_of_measurement
                            FROM statistics s
                            JOIN statistics_meta sm ON s.metadata_id = sm.id
                            WHERE sm.statistic_id IN ({placeholders})
                              AND s.start_ts >= :ts_von
                              AND s.start_ts < :ts_bis
                              AND (s.min IS NOT NULL OR s.max IS NOT NULL)
                            ORDER BY sm.statistic_id, s.start_ts
                        """),
                        params,
                    )
                for row in rows:
                    entity_id: str = row[0]
                    start_ts: float = row[1]
                    min_v = row[2]
                    max_v = row[3]
                    unit: Optional[str] = row[4]

                    if min_v is None and max_v is None:
                        continue
                    if unit in ("kWh", "Wh", "MWh"):
                        continue

                    if unit == "W":
                        skala = 1 / 1000.0
                    elif unit in ("kW", "%"):
                        skala = 1.0
                    else:
                        skala = 1 / 1000.0  # konservativ — wie get_hourly_sensor_data

                    dt = datetime.fromtimestamp(start_ts)
                    datum_iso = dt.date().isoformat()
                    hour = dt.hour

                    bucket = result.setdefault(entity_id, {}).setdefault(datum_iso, {})
                    slot: dict[str, float] = {}
                    if min_v is not None:
                        slot["min"] = float(min_v) * skala
                    if max_v is not None:
                        slot["max"] = float(max_v) * skala
                    if slot:
                        bucket[hour] = slot
        except Exception as e:
            logger.warning(f"get_hourly_minmax_sensor_data Fehler: {type(e).__name__}: {e}")

        return result

    def get_hourly_mean_for_day(
        self,
        sensor_id: str,
        datum: date,
    ) -> tuple[dict[int, float], Optional[str]]:
        """
        Etappe 5 (v3.31.0): Stunden-Mean roh + Einheit für einen Sensor und Tag.

        Im Gegensatz zu `get_hourly_sensor_data()` (das W→kW konvertiert und
        unbekannte Einheiten konservativ /1000 nimmt) werden hier rohe
        Mean-Werte zurückgegeben. Der Aufrufer kennt den Anwendungsfall
        besser (z. B. Strompreis-Skalierung EUR/kWh → cent/kWh) und kann
        seine eigene Faktor-Logik anwenden.

        Args:
            sensor_id: HA Entity-ID des Sensors
            datum: Der Tag (0..23 Stundenmittel)

        Returns:
            ({stunde_0_23: roher_mean}, unit_of_measurement)
            Leere Slots + None wenn Sensor unbekannt oder keine Daten.
        """
        if not self.is_available:
            return {}, None

        import time as time_module
        from datetime import time

        von_dt = datetime.combine(datum, time.min)
        bis_dt = datetime.combine(datum + timedelta(days=1), time.min)
        ts_von = time_module.mktime(von_dt.timetuple())
        ts_bis = time_module.mktime(bis_dt.timetuple())

        slots: dict[int, float] = {}
        unit: Optional[str] = None

        try:
            with self._verbindung() as conn:
                meta = self.get_metadata(conn, sensor_id)
                if not meta:
                    return {}, None
                unit = meta.unit

                if conn is None:
                    rows = [
                        (z["start_ts"], z["mean"])
                        for z in self._ws_zeilen(
                            [sensor_id], ts_von, ts_bis - 1, types=["mean"],
                        ).get(sensor_id, [])
                        if z["mean"] is not None
                    ]
                else:
                    rows = conn.execute(
                        text(
                            "SELECT start_ts, mean FROM statistics "
                            "WHERE metadata_id = :mid "
                            "AND start_ts >= :ts_von "
                            "AND start_ts < :ts_bis "
                            "AND mean IS NOT NULL "
                            "ORDER BY start_ts"
                        ),
                        {"mid": meta.id, "ts_von": ts_von, "ts_bis": ts_bis},
                    )
                for row in rows:
                    start_ts = row[0]
                    mean = row[1]
                    dt = datetime.fromtimestamp(start_ts)
                    if dt.date() != datum:
                        continue
                    slots[dt.hour] = float(mean)
        except Exception as e:
            logger.warning(f"get_hourly_mean_for_day Fehler: {type(e).__name__}: {e}")
            return {}, unit

        return slots, unit

    def get_monatsanfang_wert(
        self,
        sensor_id: str,
        jahr: int,
        monat: int
    ) -> Optional[float]:
        """
        Holt den Zählerstand am Monatsanfang.

        Nützlich für MQTT-Startwert-Initialisierung.
        """
        if not self.is_available:
            return None

        ts_start, ts_ende = _monatsgrenzen_ts(jahr, monat)

        with self._verbindung() as conn:
            meta = self.get_metadata(conn, sensor_id)
            if not meta:
                return None

            if conn is None:
                states = [
                    z["state"]
                    for z in self._ws_zeilen(
                        [sensor_id], ts_start, ts_ende - 1, types=["state"],
                    ).get(sensor_id, [])
                    if z["state"] is not None
                ]
                if not states:
                    return None
                wert = min(states)
            else:
                result = conn.execute(
                    text("""
                        SELECT MIN(state) as start_wert
                        FROM statistics
                        WHERE metadata_id = :mid
                        AND start_ts >= :start
                        AND start_ts < :end
                    """),
                    {"mid": meta.id, "start": ts_start, "end": ts_ende}
                )

                row = result.fetchone()
                if not row or row[0] is None:
                    return None

                wert = row[0]
            faktor = _ENERGY_UNIT_TO_KWH.get(meta.unit, 1.0) if meta.unit else 1.0
            if faktor != 1.0:
                wert *= faktor
            return round(wert, 3)

    def get_value_at(
        self,
        sensor_id: str,
        zeitpunkt: datetime,
        toleranz_minuten: int = 120,
        short_term: bool = False,
        als_stand: bool = False,
    ) -> Optional[float]:
        """
        Holt den kumulativen Zählerstand zu einem bestimmten Zeitpunkt.

        HA-Statistics-Konvention: Eine Zeile bei `start_ts=X` enthält state und
        sum AM ENDE der Periode (X+period_length). Beispiel für hourly:
        `state(start_ts=11:00)` ist der Zählerstand um 12:00 Uhr. Für 5-Min
        short_term entsprechend +5 Min. Quelle: HA-Recorder-Doku
        "last value of the period".

        Wir wollen den Wert AT `zeitpunkt` → suchen die Zeile, deren
        Perioden-Ende ≈ `zeitpunkt` ist, also `start_ts ≈ zeitpunkt - period`.

        Bevorzugt wird `sum` (reset-bereinigt — funktioniert auch bei
        Tagesreset-Zählern, wo `state` nach Mitternacht zurück springt),
        Fallback auf `state` wenn sum NULL ist (measurement-Sensoren ohne
        has_sum).

        ⚑ **Ausnahme `als_stand=True` (F-58):** Dann wird `state` gelesen und
        **nie** `sum`. Das ist kein Sonderweg, sondern die andere Hälfte
        derselben Regel: `sum` ist eine **Menge** (Verbrauchssumme seit
        Aufzeichnungsbeginn), `state` ist der **Stand**. Wer einen Zählerstand
        über den Mengen-Zweig holt, bekommt eine Zahl, die mit dem Zähler
        nichts zu tun hat — gemeldet an einem Wasserzähler, der 47,360 m³
        zeigte, während eedc 90 anzeigte. Wer eine Menge über den Stand-Zweig
        holt, bekommt bei einem Tagesreset-Zähler den Tageswert. **Beide
        Richtungen sind falsch, deshalb entscheidet das Feld** — der Marker
        steht in `field_definitions.STAND_FELDER`, nicht hier.

        Zweck: Self-Healing-Lookup für SensorSnapshot-Tabelle bei Lücken
        (z.B. Scheduler-Ausfall, Vollbackfill historischer Tage).

        Args:
            sensor_id: HA Entity-ID des kumulativen Zählers
            zeitpunkt: Zielzeitpunkt (lokale Zeit) — gemeint ist der Wert AT
                diesem Moment, nicht "innerhalb der Periode, die bei
                zeitpunkt beginnt".
            toleranz_minuten: Max. Abweichung des gefundenen Perioden-Endes
                von `zeitpunkt` (beidseitig).
            short_term: Wenn True → liest aus statistics_short_term (5-Min-
                Slots, Retention ~10–14 Tage). Sonst aus statistics (Hourly,
                dauerhaft). Für Live-Snapshot-5-Min-Pfad (Phase 1) gesetzt.

        Returns:
            Zählerstand in kWh oder None wenn kein Datenpunkt im Fenster.

        History:
            v3.25.9 fix: Off-by-one-Stunde-Bug behoben (Befund 2026-05-01,
            Snapshot-Werte waren systematisch um 1h nach hinten verschoben,
            weil get_value_at den state der Zeile bei `start_ts ≈ zeitpunkt`
            zurückgab — das ist Wert am Ende der NÄCHSTEN Periode). Existierte
            seit v3.19 (Snapshot-Rework, Issue #135), maskiert durch
            Tagessummen-Symmetrie und HA-:05-Latenz.
        """
        if not self.is_available:
            return None

        period = timedelta(minutes=5) if short_term else timedelta(hours=1)
        target = zeitpunkt - period
        ts_target = _unix(target)
        ts_von = ts_target - toleranz_minuten * 60
        ts_bis = ts_target + toleranz_minuten * 60
        table = "statistics_short_term" if short_term else "statistics"

        with self._verbindung() as conn:
            meta = self.get_metadata(conn, sensor_id)
            if not meta:
                return None

            if conn is None:
                # Dieselbe Wahl wie `ORDER BY ABS(start_ts - :target) LIMIT 1`,
                # nur in Python: die Zeile mit dem geringsten Abstand zum
                # gesuchten Perioden-Ende.
                kandidaten = self._ws_zeilen(
                    [sensor_id], ts_von, ts_bis,
                    short_term=short_term, types=["sum", "state"],
                ).get(sensor_id, [])
                if not kandidaten:
                    return None
                naechste = min(kandidaten, key=lambda z: abs(z["start_ts"] - ts_target))
                row = (naechste["sum"], naechste["state"])
                return self._value_at_wert(row, meta, als_stand=als_stand)

            # Filter UND Sortierung auf dem rohen `start_ts`: beides lief vorher
            # über `FROM_UNIXTIME`/`datetime(...)` und schloss damit den Index
            # `(metadata_id, start_ts)` für den Zeitbereich aus — die Datenbank
            # las die gesamte Historie des Sensors und sortierte sie per
            # Filesort, um genau eine Zeile zu behalten. Das ist der Pfad, den
            # der Snapshot-Job je Zähler stündlich (bei aktivem 5-Min-Snapshot
            # alle fünf Minuten) betritt.
            result = conn.execute(
                text(f"""
                    SELECT sum, state
                    FROM {table}
                    WHERE metadata_id = :mid
                      AND start_ts >= :von
                      AND start_ts <= :bis
                    ORDER BY ABS(start_ts - :target)
                    LIMIT 1
                """),
                {
                    "mid": meta.id,
                    "target": ts_target,
                    "von": ts_von,
                    "bis": ts_bis,
                }
            )
            row = result.fetchone()
            if not row:
                return None
            return self._value_at_wert(row, meta, als_stand=als_stand)

    def _value_at_wert(
        self, row, meta: SensorMeta, als_stand: bool = False
    ) -> Optional[float]:
        """Wählt aus `(sum, state)` den gültigen Wert.

        Gemeinsam für beide Transporte: welche Spalte gilt und wann gar nichts
        geliefert werden darf, ist eine fachliche Regel — die Antwort darf
        nicht davon abhängen, woher die Zeile kam.
        """
        if als_stand:
            # F-58: Ein **Stand** steht in `state`, immer. Kein `sum`-Vorzug,
            # kein `sum`-Fallback — die Summe ist eine andere Größe, und sie
            # käme hier still und plausibel aussehend heraus.
            #
            # ⚠ **Und keine Einheiten-Umrechnung.** Der Energie-Zweig unten
            # rechnet Wh/MWh nach kWh; ein Zählerstand wird grundsätzlich nicht
            # umgerechnet (Modell §3, `services/zaehlerstaende.py`) — die
            # Einheit steht in den Stammdaten des Geräts und dient der Anzeige.
            # Ein Gaszähler, der in „MWh" meldet, soll seinen Stand zeigen und
            # nicht das Tausendfache davon.
            #
            # Der Energie-Zweig unten würde einen Wasserzähler zusätzlich ganz
            # verwerfen: ohne `has_sum` verlangt er eine Einheit aus
            # `_ENERGY_UNIT_TO_KWH`, und „m³" steht dort nicht.
            wert = row[1]
            return None if wert is None else round(wert, 3)
        # Bei kumulativen Energiezählern (has_sum=True) ausschließlich
        # `sum` verwenden — niemals auf `state` zurückfallen.
        # `sum` ist HAs reset-bereinigte Lifetime-Summe; `state` kann
        # daneben eine andere Größe sein (z. B. Tageswert eines
        # utility_meter-Sensors). Mischt man beide, entstehen
        # Counter-Spikes von der Größenordnung des Lifetime-Werts,
        # sobald ein Slot `sum=NULL` hat (z. B. nach HA-Restart bevor
        # `recompile_statistics` lief). Bei `sum=NULL` lieber `None`
        # zurückgeben — der Aufrufer interpoliert (sensor_snapshot
        # _service._fill_gaps_linear).
        if meta.has_sum:
            wert = row[0]
        else:
            # Power-Sensor (kW/W) ohne `sum` darf nicht als kumulative
            # Energie ausgegeben werden — `state` ist die momentane
            # Leistung, keine kWh (#200 rcmcronny).
            if not meta.unit or meta.unit not in _ENERGY_UNIT_TO_KWH:
                return None
            wert = row[0] if row[0] is not None else row[1]
        if wert is None:
            return None

        faktor = _ENERGY_UNIT_TO_KWH.get(meta.unit, 1.0) if meta.unit else 1.0
        if faktor != 1.0:
            wert *= faktor
        return round(wert, 3)

    def get_hourly_kwh_deltas_for_day(
        self,
        sensor_ids: list[str],
        datum: date,
    ) -> dict[str, dict[int, Optional[float]]]:
        """
        Etappe 4 (v3.31.0): Liest stündliche kWh-Deltas direkt aus
        HA-LTS-Statistics für einen Tag — ohne sensor_snapshots-Zwischenschritt.

        Pro Sensor 24 Stunden-Deltas in **Backward-Konvention** (#144/#297):
        Slot h = Energie im Intervall [h-1, h) — dasselbe Slot-Raster wie
        BoundaryRange.for_hourly_slots (Snapshot-Pfad) und die Prognosequellen.
        Symmetrie über alle Pfade: tests/test_slot_konvention_quellen.py.

        HA-Statistics-Konvention (empirisch belegt 2026-06-04 gegen Live-HA):
        state/sum bei start_ts=H ist der Counter-Stand AM ENDE der Periode,
        also Zähler um (H+1):00. Mit Zähler(k) := Counter um k:00 gilt
        Zähler(k) = sum @ start_ts=(k-1); der Boundary-Index kommt aus
        `lts_boundary_index` (slot_konvention.py). Für Slot h (Energie [h-1, h)):
            end   = Zähler(h)    = sum @ start_ts=(h-1)
            start = Zähler(h-1)  = sum @ start_ts=(h-2)
            delta = end - start

        Boundary-Spezialfälle:
            - Slot 0:  [23:00 Vortag, 00:00 heute)  → Zähler(0) − Zähler(-1)
            - Slot 23: [22:00 heute, 23:00 heute)   → Zähler(23) − Zähler(22)

        HISTORIE: Bis v3.3x labelte dieser Pfad FORWARD (Slot h = [h, h+1)),
        während Prognosen + Snapshot-Pfad backward waren → IST erschien im
        Stundenvergleich 1 h zu früh (Rainer/Gernot, 2026-06-04). Der
        Symmetrie-Test deckte nur den Snapshot-Pfad ab und blieb grün.

        Verwendet die `sum`-Spalte (HA-recompile-bereinigte Lifetime-Summe,
        reset-tolerant). Fallback auf `state` nur für Sensoren ohne has_sum
        (keine Energie-Counter — wird im Energie-Pfad ignoriert).

        Bei Counter-Resets in der Mitte des Tages (negative Deltas): das
        Plausibility-Cap aus snapshot/plausibility.py greift im Aufrufer
        (Schritt 4) — diese Funktion liefert das Roh-Delta einschliesslich
        Vorzeichen, damit der Aufrufer kategorisierte Cap-Entscheidungen
        treffen kann.

        Args:
            sensor_ids: HA Entity-IDs der kumulativen kWh-Counter
            datum: Der Tag (Slots 0..23)

        Returns:
            {entity_id: {slot_h: kwh_delta_or_None}}
            None pro Slot bei Lücke (fehlende Boundary in Statistics).
            entity_id fehlt im Result, wenn der Sensor in statistics_meta
            nicht gefunden wurde oder keine Daten im Zeitraum hat.
        """
        if not self.is_available or not sensor_ids:
            return {}

        import time as time_module

        # Backward (#144): Slot h = Zähler(h) − Zähler(h-1) = Energie [h-1, h).
        # Wir brauchen Zählerstände an den Stunden -1..23 (23:00 Vortag … 23:00
        # heute). Zähler(k) = sum @ start_ts=(k-1) → die Rows reichen von
        # start_ts=22:00 Vortag bis 22:00 heute. (Vor dem Backward-Fix lag das
        # Fenster eine Stunde später, was die Forward-Fehlbeschriftung zementierte.)
        # 5-Min-Polster gegen Boundary-Drift (start_ts=H:00:01 statt H:00:00).
        boundary_start = datetime.combine(datum - timedelta(days=1), datetime.min.time()).replace(hour=22)
        boundary_end = datetime.combine(datum, datetime.min.time()).replace(hour=22)
        ts_von = time_module.mktime((boundary_start - timedelta(minutes=5)).timetuple())
        ts_bis = time_module.mktime((boundary_end + timedelta(minutes=5)).timetuple())

        params: dict = {f"id_{i}": sid for i, sid in enumerate(sensor_ids)}
        placeholders = ", ".join(f":id_{i}" for i in range(len(sensor_ids)))
        params["ts_von"] = ts_von
        params["ts_bis"] = ts_bis

        # Per-Sensor: {boundary_hour_index: counter_value_in_kwh}
        # boundary_hour_index = Zähler(k):00, k = Stunden-Offset ab 00:00 heute:
        #  -1 = 23:00 Vortag (= sum @ start_ts=22:00 Vortag), 0 = 00:00 heute,
        #  …, 23 = 23:00 heute. Index via lts_boundary_index (SoT/Symmetrie-Test).
        per_sensor_boundaries: dict[str, dict[int, float]] = {sid: {} for sid in sensor_ids}

        try:
            with self._verbindung() as conn:
                # Metadaten laden (faktor, has_sum)
                meta_by_id: dict[str, SensorMeta] = {}
                for sid in sensor_ids:
                    m = self.get_metadata(conn, sid)
                    if m:
                        meta_by_id[sid] = m

                if not meta_by_id:
                    return {}

                meta_id_to_sensor: dict[int, str] = {m.id: sid for sid, m in meta_by_id.items()}

                if conn is None:
                    rows = [
                        (meta_by_id[sid].id, z["start_ts"], z["sum"], z["state"])
                        for sid, zeilen in self._ws_zeilen(
                            list(meta_by_id), ts_von, ts_bis, types=["sum", "state"],
                        ).items()
                        if sid in meta_by_id
                        for z in zeilen
                    ]
                else:
                    placeholders_meta = ", ".join(f":mid_{i}" for i in range(len(meta_by_id)))
                    meta_params: dict = {
                        f"mid_{i}": m.id for i, m in enumerate(meta_by_id.values())
                    }
                    rows = conn.execute(
                        text(f"""
                            SELECT metadata_id, start_ts, sum, state
                            FROM statistics
                            WHERE metadata_id IN ({placeholders_meta})
                              AND start_ts >= :ts_von
                              AND start_ts <= :ts_bis
                            ORDER BY metadata_id, start_ts
                        """),
                        {**meta_params, "ts_von": ts_von, "ts_bis": ts_bis},
                    )
                for row in rows:
                    metadata_id = row[0]
                    start_ts = row[1]
                    sum_val = row[2]
                    state_val = row[3]
                    sid = meta_id_to_sensor.get(metadata_id)
                    if not sid:
                        continue
                    meta = meta_by_id[sid]

                    # Counter-Wert in kWh
                    if meta.has_sum:
                        if sum_val is None:
                            continue  # NULL → Lücke, Caller interpoliert oder verwirft
                        raw = sum_val
                    else:
                        # Nicht-Energie-Sensor — wird im Aufrufer durch
                        # _categorize_counter ohnehin ausgefiltert (Power-Sensor
                        # liefert keine Energie-Kategorie). Defensiv überspringen.
                        continue

                    faktor = _ENERGY_UNIT_TO_KWH.get(meta.unit, 1.0) if meta.unit else 1.0
                    wert_kwh = raw * faktor

                    # start_ts=H → Counter am Ende von H = Zähler(H+1):00.
                    # Boundary-Index (Stunden-Offset ab 00:00 heute, -1..24) aus
                    # der SoT-Helper-Funktion — DST-robust, Symmetrie-getestet.
                    dt = datetime.fromtimestamp(start_ts)
                    b_idx = lts_boundary_index(dt, datum)
                    if b_idx < -1 or b_idx > 24:
                        continue  # Außerhalb relevanter Boundary-Range
                    per_sensor_boundaries[sid][b_idx] = wert_kwh

        except Exception as e:
            logger.warning(f"get_hourly_kwh_deltas_for_day Fehler: {type(e).__name__}: {e}")
            return {}

        # Backward (#144): Slot h = Zähler(h) − Zähler(h-1) = Energie [h-1, h).
        # Slot 0 = [23:00 Vortag, 00:00 heute) → boundary[0] − boundary[-1].
        result: dict[str, dict[int, Optional[float]]] = {}
        for sid, boundaries in per_sensor_boundaries.items():
            if not boundaries:
                continue  # Sensor hatte keine Daten — wird im Aufrufer als Lücke behandelt
            slots: dict[int, Optional[float]] = {}
            for h in range(24):
                start = boundaries.get(h - 1)
                end = boundaries.get(h)
                if start is None or end is None:
                    slots[h] = None
                else:
                    slots[h] = round(end - start, 3)
            result[sid] = slots

        return result

    def get_short_term_5min_for_day(
        self,
        sensor_ids: list[str],
        datum: date,
        bis: Optional[datetime] = None,
    ) -> dict[str, dict]:
        """Liest `statistics_short_term` (5-Min-Granularität) für einen Tag.

        Speist die Live-Tagesverlauf-Kurve im Add-on-Modus aus derselben
        SoT-Familie wie die Heute-kWh-Kacheln (`safe_get_tages_kwh`), damit
        Kurven-Integral und Kachel deckungsgleich sind (Konsistenz-, kein
        Genauigkeitsfall). short_term hat ~10–14 Tage Retention — reicht für
        den Tagesverlauf.

        Pro Sensor werden ZWEI Bausteine geliefert:
          - ``counter_deltas`` (nur `has_sum`-Sensoren, kWh-Zähler): 5-Min-Delta
            ``sum@t − sum@(t−5min)`` je Slot-Beginn ``t`` (= Energie im Intervall
            ``[t, t+5min)``). `sum` ist HAs reset-bereinigte Lifetime-Summe
            ([[feedback_ha_statistics_aggregation]] — MAX(sum)−MIN(sum) statt
            state). Telescoping über den Tag ⇒ Σ = Tages-Zähler-Delta.
          - ``means``: roher `mean` (Statistics-Einheit, i. d. R. W/kW) je
            Slot-Beginn — für reine Power-Sensoren ohne kWh-Pendant.

        HA-Konvention: `sum`/`mean` bei ``start_ts=t`` gehören zum 5-Min-Intervall
        ``[t, t+5min)``; `sum` ist der Zählerstand am ENDE (= Zähler bei
        ``t+5min``). Delta für Slot ``[t, t+5min)`` = ``sum@t − sum@(t−5min)``.

        Args:
            sensor_ids: HA Entity-IDs (kWh-Zähler und/oder Power-Sensoren).
            datum: Der Tag (lokale Zeit).
            bis: Obergrenze (z. B. ``now`` für heute); Default = Tagesende.

        Returns:
            ``{sensor_id: {"has_sum": bool, "unit": str|None,
                           "counter_deltas": {slot_dt: kwh_delta},
                           "means": {slot_dt: mean_native}}}``
            Sensoren ohne Treffer in `statistics_meta`/`short_term` fehlen.
        """
        if not self.is_available or not sensor_ids:
            return {}

        import time as time_module

        tag_start = datetime.combine(datum, datetime.min.time())
        # 5-Min-Vorlauf: für das Delta von Slot 00:00 brauchen wir den
        # Zählerstand bei 00:00 (= sum @ start_ts=23:55 Vortag).
        win_start = tag_start - timedelta(minutes=SHORT_TERM_SLOT)
        win_end = (bis or (tag_start + timedelta(days=1))) + timedelta(minutes=SHORT_TERM_SLOT)
        ts_von = time_module.mktime(win_start.timetuple())
        ts_bis = time_module.mktime(win_end.timetuple())

        slot = timedelta(minutes=SHORT_TERM_SLOT)
        result: dict[str, dict] = {}

        try:
            with self._verbindung() as conn:
                meta_by_id: dict[str, SensorMeta] = {}
                for sid in sensor_ids:
                    m = self.get_metadata(conn, sid)
                    if m:
                        meta_by_id[sid] = m
                if not meta_by_id:
                    return {}

                meta_id_to_sensor: dict[int, str] = {m.id: sid for sid, m in meta_by_id.items()}

                if conn is None:
                    # `period=5minute` ist das Gegenstück zu
                    # `statistics_short_term` — inklusive derselben Reichweite:
                    # HA hält beide nur für die Recorder-Aufbewahrung vor
                    # (gemessen ~12 Tage), danach bleibt nur die Stundenebene.
                    rows = [
                        (meta_by_id[sid].id, z["start_ts"], z["sum"], z["mean"])
                        for sid, zeilen in self._ws_zeilen(
                            list(meta_by_id), ts_von, ts_bis,
                            short_term=True, types=["sum", "mean"],
                        ).items()
                        if sid in meta_by_id
                        for z in zeilen
                    ]
                else:
                    placeholders = ", ".join(f":mid_{i}" for i in range(len(meta_by_id)))
                    meta_params: dict = {
                        f"mid_{i}": m.id for i, m in enumerate(meta_by_id.values())
                    }
                    rows = conn.execute(
                        text(f"""
                            SELECT metadata_id, start_ts, sum, mean
                            FROM statistics_short_term
                            WHERE metadata_id IN ({placeholders})
                              AND start_ts >= :ts_von
                              AND start_ts <= :ts_bis
                            ORDER BY metadata_id, start_ts
                        """),
                        {**meta_params, "ts_von": ts_von, "ts_bis": ts_bis},
                    )

                # Pro Sensor: {slot_beginn_dt: sum_kwh} und {slot_beginn_dt: mean}.
                sum_by_slot: dict[str, dict[datetime, float]] = {sid: {} for sid in meta_by_id}
                means_by_slot: dict[str, dict[datetime, float]] = {sid: {} for sid in meta_by_id}

                for row in rows:
                    sid = meta_id_to_sensor.get(row[0])
                    if not sid:
                        continue
                    meta = meta_by_id[sid]
                    slot_dt = _snap_to_slot(datetime.fromtimestamp(row[1]), SHORT_TERM_SLOT)
                    if meta.has_sum and row[2] is not None:
                        faktor = _ENERGY_UNIT_TO_KWH.get(meta.unit, 1.0) if meta.unit else 1.0
                        sum_by_slot[sid][slot_dt] = row[2] * faktor
                    if row[3] is not None:
                        means_by_slot[sid][slot_dt] = row[3]

                for sid, meta in meta_by_id.items():
                    sbs = sum_by_slot[sid]
                    deltas: dict[datetime, float] = {}
                    for t, wert in sbs.items():
                        prev = sbs.get(t - slot)
                        if prev is not None:
                            deltas[t] = round(wert - prev, 4)
                    result[sid] = {
                        "has_sum": meta.has_sum,
                        "unit": meta.unit,
                        "counter_deltas": deltas,
                        "means": means_by_slot[sid],
                    }

        except Exception as e:
            logger.warning(f"get_short_term_5min_for_day Fehler: {type(e).__name__}: {e}")
            return {}

        return result


# Singleton
_ha_statistics_service: Optional[HAStatisticsService] = None


def get_ha_statistics_service() -> HAStatisticsService:
    """Gibt die Singleton-Instanz zurück."""
    global _ha_statistics_service
    if _ha_statistics_service is None:
        _ha_statistics_service = HAStatisticsService()
    return _ha_statistics_service
