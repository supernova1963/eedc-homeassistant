"""
EEDC Konfiguration

Lädt Einstellungen aus Umgebungsvariablen.
Diese werden vom run.sh Script aus der Home Assistant Konfiguration gesetzt.
"""

import os
from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """
    Anwendungs-Einstellungen.

    Werte werden aus Umgebungsvariablen geladen.
    Defaults sind für lokale Entwicklung gedacht.
    """

    # Datenbank
    database_url: str = "sqlite+aiosqlite:////data/eedc.db"

    @property
    def database_path(self) -> Path:
        """Extrahiert den Dateipfad aus der Database URL."""
        # sqlite+aiosqlite:////data/eedc.db -> /data/eedc.db
        path = self.database_url.replace("sqlite+aiosqlite://", "")
        return Path(path)

    # Logging
    log_level: str = "info"

    # Home Assistant Supervisor Token (automatisch gesetzt)
    supervisor_token: str | None = os.environ.get("SUPERVISOR_TOKEN")

    # Home Assistant Sensor Mappings
    ha_sensor_pv: str = os.environ.get("HA_SENSOR_PV", "")
    ha_sensor_einspeisung: str = os.environ.get("HA_SENSOR_EINSPEISUNG", "")
    ha_sensor_netzbezug: str = os.environ.get("HA_SENSOR_NETZBEZUG", "")
    ha_sensor_batterie_ladung: str = os.environ.get("HA_SENSOR_BATTERIE_LADUNG", "")
    ha_sensor_batterie_entladung: str = os.environ.get("HA_SENSOR_BATTERIE_ENTLADUNG", "")

    # API URLs
    ha_api_url: str = "http://supervisor/core/api"
    pvgis_api_url: str = "https://re.jrc.ec.europa.eu/api/v5_2"
    open_meteo_api_url: str = "https://api.open-meteo.com/v1"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


# Singleton Instance
settings = Settings()
