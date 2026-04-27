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
            try:
                self._engine = create_engine(
                    settings.ha_recorder_db_url,
                    pool_pre_ping=True,
                    pool_recycle=3600,
                )
                self._is_mysql = "mysql" in settings.ha_recorder_db_url
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
            text("SELECT id, unit_of_measurement FROM statistics_meta WHERE statistic_id = :sid"),
            {"sid": sensor_id}
        )
        row = result.fetchone()
        if not row:
            logger.debug(f"Sensor '{sensor_id}' nicht in statistics_meta gefunden")
            return None
        return SensorMeta(id=row[0], unit=row[1])

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
    ) -> Optional[float]:
        """
        Holt den kumulativen Zählerstand zu einem bestimmten Zeitpunkt.

        HA Statistics speichert stündliche Snapshots mit state = Zählerstand
        am Stundenanfang. Sucht die nächstgelegene Zeile innerhalb
        ±toleranz_minuten und gibt deren state (in kWh) zurück.

        Zweck: Self-Healing-Lookup für SensorSnapshot-Tabelle bei Lücken
        (z.B. Scheduler-Ausfall, Vollbackfill historischer Tage).

        Args:
            sensor_id: HA Entity-ID des kumulativen Zählers
            zeitpunkt: Zielzeitpunkt (lokale Zeit)
            toleranz_minuten: Max. Abweichung von zeitpunkt (beidseitig)

        Returns:
            Zählerstand in kWh oder None wenn kein Datenpunkt im Fenster.
        """
        if not self.is_available:
            return None

        von = zeitpunkt - timedelta(minutes=toleranz_minuten)
        bis = zeitpunkt + timedelta(minutes=toleranz_minuten)
        ts_expr = self._ts_to_datetime("start_ts")

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
                    SELECT state
                    FROM statistics
                    WHERE metadata_id = :mid
                      AND {ts_expr} >= :von
                      AND {ts_expr} <= :bis
                    ORDER BY {order_expr}
                    LIMIT 1
                """),
                {
                    "mid": meta.id,
                    "target": zeitpunkt,
                    "von": von,
                    "bis": bis,
                }
            )
            row = result.fetchone()
            if not row or row[0] is None:
                return None

            wert = row[0]
            faktor = _ENERGY_UNIT_TO_KWH.get(meta.unit, 1.0) if meta.unit else 1.0
            if faktor != 1.0:
                wert *= faktor
            return round(wert, 3)


# Singleton
_ha_statistics_service: Optional[HAStatisticsService] = None


def get_ha_statistics_service() -> HAStatisticsService:
    """Gibt die Singleton-Instanz zurück."""
    global _ha_statistics_service
    if _ha_statistics_service is None:
        _ha_statistics_service = HAStatisticsService()
    return _ha_statistics_service
