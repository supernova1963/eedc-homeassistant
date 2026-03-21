"""
HA Statistics Service - Liest historische Daten aus der Home Assistant Datenbank.

Ermöglicht:
- Monatswerte aus HA-Langzeitstatistiken abrufen
- Alle verfügbaren Monate seit Installationsdatum ermitteln
- MQTT-Startwerte basierend auf historischen Daten initialisieren

Die HA-Datenbank enthält in der `statistics` Tabelle stündliche Aggregationen
für Sensoren mit `has_sum=True` (typisch für kWh-Zähler).
"""

import sqlite3
import logging
from datetime import datetime, date
from pathlib import Path
from typing import Optional, NamedTuple
from pydantic import BaseModel

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
    """Service für Zugriff auf HA-Langzeitstatistiken."""

    MONAT_NAMEN = [
        "", "Januar", "Februar", "März", "April", "Mai", "Juni",
        "Juli", "August", "September", "Oktober", "November", "Dezember"
    ]

    def __init__(self):
        self._db_path: Optional[Path] = None

    @property
    def db_path(self) -> Optional[Path]:
        """Gibt den Pfad zur HA-Datenbank zurück, falls verfügbar."""
        if self._db_path is not None:
            return self._db_path

        # Priorität: HA-Addon Pfad, dann lokaler Test-Pfad
        if HA_DB_PATH.exists():
            self._db_path = HA_DB_PATH
        elif HA_DB_PATH_LOCAL.exists():
            self._db_path = HA_DB_PATH_LOCAL
            logger.info("Verwende lokale HA-Datenbank-Kopie für Tests")
        else:
            self._db_path = None

        return self._db_path

    @property
    def is_available(self) -> bool:
        """Prüft ob die HA-Datenbank verfügbar ist."""
        return self.db_path is not None

    def _get_connection(self) -> sqlite3.Connection:
        """Erstellt eine Datenbankverbindung."""
        if not self.is_available:
            raise RuntimeError("HA-Datenbank nicht verfügbar")

        conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        return conn

    def get_metadata(self, conn: sqlite3.Connection, sensor_id: str) -> Optional[SensorMeta]:
        """
        Ermittelt metadata_id und unit_of_measurement für einen Sensor.

        Args:
            conn: Datenbankverbindung
            sensor_id: HA Entity-ID (z.B. "sensor.pv_erzeugung")

        Returns:
            SensorMeta oder None wenn Sensor nicht in statistics
        """
        cursor = conn.execute(
            "SELECT id, unit_of_measurement FROM statistics_meta WHERE statistic_id = ?",
            (sensor_id,)
        )
        row = cursor.fetchone()
        return SensorMeta(id=row["id"], unit=row["unit_of_measurement"]) if row else None

    def get_sensor_monatswert(
        self,
        conn: sqlite3.Connection,
        meta: SensorMeta,
        sensor_id: str,
        jahr: int,
        monat: int
    ) -> Optional[SensorMonatswert]:
        """
        Ermittelt den Monatswert für einen Sensor.

        Die Differenz zwischen MAX(state) und MIN(state) im Monat
        ergibt den Verbrauch/Erzeugung für diesen Monat.
        Werte werden automatisch nach kWh konvertiert (Wh, MWh, etc.).

        Args:
            conn: Datenbankverbindung
            meta: SensorMeta mit ID und Einheit
            sensor_id: Original sensor_id für Response
            jahr: Jahr
            monat: Monat (1-12)

        Returns:
            SensorMonatswert oder None wenn keine Daten
        """
        # Monatsanfang und -ende berechnen
        start_datum = f"{jahr:04d}-{monat:02d}-01"
        if monat == 12:
            end_datum = f"{jahr + 1:04d}-01-01"
        else:
            end_datum = f"{jahr:04d}-{monat + 1:02d}-01"

        cursor = conn.execute("""
            SELECT
                MIN(state) as start_wert,
                MAX(state) as end_wert
            FROM statistics
            WHERE metadata_id = ?
            AND datetime(start_ts, 'unixepoch', 'localtime') >= ?
            AND datetime(start_ts, 'unixepoch', 'localtime') < ?
        """, (meta.id, start_datum, end_datum))

        row = cursor.fetchone()
        if not row or row["start_wert"] is None:
            return None

        start_wert = row["start_wert"]
        end_wert = row["end_wert"]
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
        """
        Holt Monatswerte für mehrere Sensoren.

        Args:
            sensor_ids: Liste von HA Entity-IDs
            jahr: Jahr
            monat: Monat (1-12)

        Returns:
            MonatswertResponse mit allen Sensorwerten
        """
        if not self.is_available:
            raise RuntimeError("HA-Datenbank nicht verfügbar")

        sensoren: list[SensorMonatswert] = []

        with self._get_connection() as conn:
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
        """
        Ermittelt alle Monate mit verfügbaren Daten.

        Args:
            sensor_ids: Liste von HA Entity-IDs (mindestens einer muss Daten haben)

        Returns:
            AlleMonateResponse mit Liste aller verfügbaren Monate
        """
        if not self.is_available:
            raise RuntimeError("HA-Datenbank nicht verfügbar")

        with self._get_connection() as conn:
            # Metadata-IDs ermitteln
            metadata_ids = []
            for sensor_id in sensor_ids:
                meta = self.get_metadata(conn, sensor_id)
                if meta:
                    metadata_ids.append(meta.id)

            if not metadata_ids:
                raise ValueError("Keine der angegebenen Sensoren hat Statistik-Daten")

            # Zeitraum ermitteln
            placeholders = ",".join("?" * len(metadata_ids))
            cursor = conn.execute(f"""
                SELECT
                    date(MIN(start_ts), 'unixepoch', 'localtime') as erstes_datum,
                    date(MAX(start_ts), 'unixepoch', 'localtime') as letztes_datum
                FROM statistics
                WHERE metadata_id IN ({placeholders})
            """, metadata_ids)

            row = cursor.fetchone()
            erstes = datetime.strptime(row["erstes_datum"], "%Y-%m-%d").date()
            letztes = datetime.strptime(row["letztes_datum"], "%Y-%m-%d").date()

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
                # Nächster Monat
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
        """
        Holt Monatswerte für alle verfügbaren Monate.

        Args:
            sensor_ids: Liste von HA Entity-IDs
            ab_datum: Optional - nur Monate ab diesem Datum

        Returns:
            Liste von MonatswertResponse für jeden Monat
        """
        verfuegbar = self.get_verfuegbare_monate(sensor_ids)

        ergebnisse: list[MonatswertResponse] = []
        for monat_info in verfuegbar.monate:
            # Filter nach ab_datum
            if ab_datum:
                monat_start = date(monat_info.jahr, monat_info.monat, 1)
                if monat_start < ab_datum:
                    continue

            werte = self.get_monatswerte(sensor_ids, monat_info.jahr, monat_info.monat)
            if werte.sensoren:  # Nur Monate mit Daten
                ergebnisse.append(werte)

        return ergebnisse

    def get_monatsanfang_wert(
        self,
        sensor_id: str,
        jahr: int,
        monat: int
    ) -> Optional[float]:
        """
        Holt den Zählerstand am Monatsanfang.

        Nützlich für MQTT-Startwert-Initialisierung.

        Args:
            sensor_id: HA Entity-ID
            jahr: Jahr
            monat: Monat

        Returns:
            Zählerstand am Monatsanfang oder None
        """
        if not self.is_available:
            return None

        start_datum = f"{jahr:04d}-{monat:02d}-01"
        if monat == 12:
            end_datum = f"{jahr + 1:04d}-01-01"
        else:
            end_datum = f"{jahr:04d}-{monat + 1:02d}-01"

        with self._get_connection() as conn:
            meta = self.get_metadata(conn, sensor_id)
            if not meta:
                return None

            cursor = conn.execute("""
                SELECT MIN(state) as start_wert
                FROM statistics
                WHERE metadata_id = ?
                AND datetime(start_ts, 'unixepoch', 'localtime') >= ?
                AND datetime(start_ts, 'unixepoch', 'localtime') < ?
            """, (meta.id, start_datum, end_datum))

            row = cursor.fetchone()
            if not row or row["start_wert"] is None:
                return None

            wert = row["start_wert"]
            # Einheiten-Konvertierung nach kWh
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
