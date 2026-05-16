"""
HA Statistics Service - Liest historische Daten aus der Home Assistant Datenbank.

Ermöglicht:
- Monatswerte aus HA-Langzeitstatistiken abrufen
- Alle verfügbaren Monate seit Installationsdatum ermitteln
- MQTT-Startwerte basierend auf historischen Daten initialisieren

Die HA-Datenbank enthält in der `statistics` Tabelle stündliche Aggregationen
für Sensoren mit `has_sum=True` (typisch für kWh-Zähler).

Unterstützt SQLite (Standard) und MariaDB/MySQL (über ha_recorder_db_url).
"""

import logging
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Optional, NamedTuple

from pydantic import BaseModel
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from backend.core.config import settings

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


class HAStatisticsService:
    """Service für Zugriff auf HA-Langzeitstatistiken (SQLite oder MariaDB)."""

    MONAT_NAMEN = [
        "", "Januar", "Februar", "März", "April", "Mai", "Juni",
        "Juli", "August", "September", "Oktober", "November", "Dezember"
    ]

    def __init__(self):
        self._engine: Optional[Engine] = None
        self._is_mysql: bool = False
        self._initialized: bool = False

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

    @property
    def is_available(self) -> bool:
        """Prüft ob die HA-Datenbank verfügbar ist."""
        self._init_engine()
        return self._engine is not None

    @property
    def db_path(self) -> Optional[str]:
        """Gibt den DB-Pfad/URL für Status-Anzeige zurück."""
        self._init_engine()
        if self._engine is None:
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
        """Gibt den Datenbank-Typ zurück."""
        if not self.is_available:
            return "nicht verfügbar"
        return "MariaDB/MySQL" if self._is_mysql else "SQLite"

    def count_statistics_sensors(self) -> int:
        """Zählt die Anzahl der Sensoren in statistics_meta."""
        if not self.is_available:
            return 0
        try:
            with self._engine.connect() as conn:
                result = conn.execute(text("SELECT COUNT(*) FROM statistics_meta"))
                row = result.fetchone()
                return row[0] if row else 0
        except Exception:
            return 0

    def _ts_to_datetime(self, col: str) -> str:
        """Gibt den DB-spezifischen Ausdruck für Unix-Timestamp → Datetime."""
        if self._is_mysql:
            # FROM_UNIXTIME liefert bereits Session-Timezone, kein CONVERT_TZ nötig
            # (CONVERT_TZ kann NULL liefern wenn Timezone-Tabellen nicht geladen sind)
            return f"FROM_UNIXTIME({col})"
        return f"datetime({col}, 'unixepoch', 'localtime')"

    def _ts_to_date(self, col: str) -> str:
        """Gibt den DB-spezifischen Ausdruck für Unix-Timestamp → Date."""
        if self._is_mysql:
            return f"DATE(FROM_UNIXTIME({col}))"
        return f"date({col}, 'unixepoch', 'localtime')"

    def get_metadata(self, conn, sensor_id: str) -> Optional[SensorMeta]:
        """
        Ermittelt metadata_id und unit_of_measurement für einen Sensor.

        Args:
            conn: SQLAlchemy Connection
            sensor_id: HA Entity-ID (z.B. "sensor.pv_erzeugung")

        Returns:
            SensorMeta oder None wenn Sensor nicht in statistics
        """
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
        return SensorMeta(id=row[0], unit=row[1], has_sum=bool(row[2]))

    def filter_valid_sensor_ids(self, sensor_ids: list[str]) -> tuple[list[str], list[str]]:
        """
        Prüft welche Sensor-IDs tatsächlich in statistics_meta vorhanden sind.

        Returns:
            (valid_ids, missing_ids)
        """
        valid, missing = [], []
        with self._engine.connect() as conn:
            for sid in sensor_ids:
                if self.get_metadata(conn, sid):
                    valid.append(sid)
                else:
                    missing.append(sid)
        return valid, missing

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
        start_datum = f"{jahr:04d}-{monat:02d}-01"
        if monat == 12:
            end_datum = f"{jahr + 1:04d}-01-01"
        else:
            end_datum = f"{jahr:04d}-{monat + 1:02d}-01"

        ts_expr = self._ts_to_datetime("start_ts")

        result = conn.execute(
            text(f"""
                SELECT
                    MIN(state) as state_min,
                    MAX(state) as state_max,
                    MIN(sum)   as sum_min,
                    MAX(sum)   as sum_max
                FROM statistics
                WHERE metadata_id = :mid
                AND {ts_expr} >= :start
                AND {ts_expr} < :end
            """),
            {"mid": meta.id, "start": start_datum, "end": end_datum}
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

        with self._engine.connect() as conn:
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

        with self._engine.connect() as conn:
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

            # Zeitraum ermitteln — IN-Klausel mit benannten Parametern
            params = {f"id_{i}": mid for i, mid in enumerate(metadata_ids)}
            placeholders = ", ".join(f":id_{i}" for i in range(len(metadata_ids)))
            ts_date = self._ts_to_date("MIN(start_ts)")
            ts_date_max = self._ts_to_date("MAX(start_ts)")

            # MIN/MAX erst ermitteln, dann Datumsfunktion anwenden
            result = conn.execute(
                text(f"""
                    SELECT
                        {self._ts_to_date('start_ts')} as datum
                    FROM statistics
                    WHERE metadata_id IN ({placeholders})
                    ORDER BY start_ts ASC
                    LIMIT 1
                """),
                params
            )
            row_first = result.fetchone()

            result = conn.execute(
                text(f"""
                    SELECT
                        {self._ts_to_date('start_ts')} as datum
                    FROM statistics
                    WHERE metadata_id IN ({placeholders})
                    ORDER BY start_ts DESC
                    LIMIT 1
                """),
                params
            )
            row_last = result.fetchone()

            if not row_first or not row_last or row_first[0] is None or row_last[0] is None:
                raise ValueError(
                    f"Sensoren in statistics_meta gefunden, aber keine Messwerte in der "
                    f"statistics-Tabelle vorhanden"
                )

            erstes = datetime.strptime(str(row_first[0]), "%Y-%m-%d").date()
            letztes = datetime.strptime(str(row_last[0]), "%Y-%m-%d").date()

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
            with self._engine.connect() as conn:
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
            with self._engine.connect() as conn:
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
            with self._engine.connect() as conn:
                meta = self.get_metadata(conn, sensor_id)
                if not meta:
                    return {}, None
                unit = meta.unit

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

        start_datum = f"{jahr:04d}-{monat:02d}-01"
        if monat == 12:
            end_datum = f"{jahr + 1:04d}-01-01"
        else:
            end_datum = f"{jahr:04d}-{monat + 1:02d}-01"

        ts_expr = self._ts_to_datetime("start_ts")

        with self._engine.connect() as conn:
            meta = self.get_metadata(conn, sensor_id)
            if not meta:
                return None

            result = conn.execute(
                text(f"""
                    SELECT MIN(state) as start_wert
                    FROM statistics
                    WHERE metadata_id = :mid
                    AND {ts_expr} >= :start
                    AND {ts_expr} < :end
                """),
                {"mid": meta.id, "start": start_datum, "end": end_datum}
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
        von = target - timedelta(minutes=toleranz_minuten)
        bis = target + timedelta(minutes=toleranz_minuten)
        ts_expr = self._ts_to_datetime("start_ts")
        table = "statistics_short_term" if short_term else "statistics"

        if self._is_mysql:
            order_expr = f"ABS(TIMESTAMPDIFF(SECOND, {ts_expr}, :target))"
        else:
            order_expr = f"ABS(julianday({ts_expr}) - julianday(:target))"

        with self._engine.connect() as conn:
            meta = self.get_metadata(conn, sensor_id)
            if not meta:
                return None

            result = conn.execute(
                text(f"""
                    SELECT sum, state
                    FROM {table}
                    WHERE metadata_id = :mid
                      AND {ts_expr} >= :von
                      AND {ts_expr} <= :bis
                    ORDER BY {order_expr}
                    LIMIT 1
                """),
                {
                    "mid": meta.id,
                    "target": target,
                    "von": von,
                    "bis": bis,
                }
            )
            row = result.fetchone()
            if not row:
                return None

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

        Pro Sensor 24 Stunden-Deltas: Slot h = Energie zwischen H:00 und
        (H+1):00, berechnet als Counter-Differenz nach HA-Statistics-Konvention.

        HA-Statistics-Konvention (siehe get_value_at-Docstring): state/sum bei
        start_ts=H ist der Counter-Stand AM ENDE der Periode (H+1). Für
        Slot h (Energie im Intervall [H, H+1)) gilt damit:
            end   = state at start_ts=H        (= Counter um H+1:00)
            start = state at start_ts=(H-1)    (= Counter um H:00)
            delta = end - start

        Boundary-Spezialfälle:
            - Slot 0: end = state at start_ts=00:00 heute,
                      start = state at start_ts=23:00 vortag
            - Slot 23: end = state at start_ts=23:00 heute,
                       start = state at start_ts=22:00 heute

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

        # Wir brauchen 25 Boundaries: start_ts=23:00 vortag bis start_ts=23:00 heute.
        # SQL-Range: ein 5-Min-Sicherheitspolster auf beiden Seiten gegen
        # Boundary-Drift (manche HA-Versionen haben start_ts=H:00:01 statt H:00:00).
        boundary_start = datetime.combine(datum - timedelta(days=1), datetime.min.time()).replace(hour=23)
        boundary_end = datetime.combine(datum, datetime.min.time()).replace(hour=23)
        ts_von = time_module.mktime((boundary_start - timedelta(minutes=5)).timetuple())
        ts_bis = time_module.mktime((boundary_end + timedelta(minutes=5)).timetuple())

        params: dict = {f"id_{i}": sid for i, sid in enumerate(sensor_ids)}
        placeholders = ", ".join(f":id_{i}" for i in range(len(sensor_ids)))
        params["ts_von"] = ts_von
        params["ts_bis"] = ts_bis

        # Per-Sensor: {boundary_hour_index: counter_value_in_kwh}
        # boundary_hour_index: 0 = 00:00 heute (= state at start_ts=23:00 vortag),
        # 1 = 01:00 heute (= state at start_ts=00:00 heute), ..., 24 = 00:00 folgetag (= state at start_ts=23:00 heute)
        per_sensor_boundaries: dict[str, dict[int, float]] = {sid: {} for sid in sensor_ids}

        try:
            with self._engine.connect() as conn:
                # Metadaten laden (faktor, has_sum)
                meta_by_id: dict[str, SensorMeta] = {}
                for sid in sensor_ids:
                    m = self.get_metadata(conn, sid)
                    if m:
                        meta_by_id[sid] = m

                if not meta_by_id:
                    return {}

                placeholders_meta = ", ".join(f":mid_{i}" for i in range(len(meta_by_id)))
                meta_params: dict = {f"mid_{i}": m.id for i, m in enumerate(meta_by_id.values())}
                meta_id_to_sensor: dict[int, str] = {m.id: sid for sid, m in meta_by_id.items()}

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

                    # start_ts=H → Counter am Ende von H = (H+1):00.
                    # Mappe auf Boundary-Hour-Index 0..24 (0 = 00:00 heute).
                    dt = datetime.fromtimestamp(start_ts)
                    boundary_dt = dt + timedelta(hours=1)
                    if boundary_dt.date() == datum:
                        b_idx = boundary_dt.hour  # 1..23
                    elif boundary_dt.date() == datum + timedelta(days=1) and boundary_dt.hour == 0:
                        b_idx = 24
                    elif boundary_dt.date() == datum and boundary_dt.hour == 0:
                        b_idx = 0
                    elif boundary_dt.date() == datum - timedelta(days=1) and boundary_dt.hour == 23:
                        # Vortag-Stunde 23 → Boundary am Ende = 00:00 heute, das ist b_idx=0
                        # Aber durch die +1h-Logik kommt das eigentlich nie hier rein
                        continue
                    else:
                        continue  # Außerhalb relevanter Boundary-Range
                    per_sensor_boundaries[sid][b_idx] = wert_kwh

        except Exception as e:
            logger.warning(f"get_hourly_kwh_deltas_for_day Fehler: {type(e).__name__}: {e}")
            return {}

        # Stunden-Deltas berechnen: Slot h = boundary[h+1] - boundary[h]
        result: dict[str, dict[int, Optional[float]]] = {}
        for sid, boundaries in per_sensor_boundaries.items():
            if not boundaries:
                continue  # Sensor hatte keine Daten — wird im Aufrufer als Lücke behandelt
            slots: dict[int, Optional[float]] = {}
            for h in range(24):
                start = boundaries.get(h)
                end = boundaries.get(h + 1)
                if start is None or end is None:
                    slots[h] = None
                else:
                    slots[h] = round(end - start, 3)
            result[sid] = slots

        return result


# Singleton
_ha_statistics_service: Optional[HAStatisticsService] = None


def get_ha_statistics_service() -> HAStatisticsService:
    """Gibt die Singleton-Instanz zurück."""
    global _ha_statistics_service
    if _ha_statistics_service is None:
        _ha_statistics_service = HAStatisticsService()
    return _ha_statistics_service
