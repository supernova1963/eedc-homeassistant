"""
EEDC Konfiguration

Lädt Einstellungen aus Umgebungsvariablen.
Diese werden vom run.sh Script aus der Home Assistant Konfiguration gesetzt.
"""

import os
from pathlib import Path
from pydantic_settings import BaseSettings

# =============================================================================
# Zentrale Versionskonfiguration
# =============================================================================
APP_VERSION = "1.1.0-beta.1"
APP_NAME = "eedc"
APP_FULL_NAME = "Energie Effizienz Data Center"


def get_default_database_url() -> str:
    """Gibt den Standard-Datenbankpfad zurück."""
    # In HA Add-on: /data existiert
    if Path("/data").exists():
        return "sqlite+aiosqlite:////data/eedc.db"
    # Lokale Entwicklung: data/ im eedc-Verzeichnis
    local_data = Path(__file__).parent.parent.parent / "data"
    local_data.mkdir(exist_ok=True)
    return f"sqlite+aiosqlite:///{local_data}/eedc.db"


class Settings(BaseSettings):
    """
    Anwendungs-Einstellungen.

    Werte werden aus Umgebungsvariablen geladen.
    Defaults sind für lokale Entwicklung gedacht.
    """

    # Datenbank
    database_url: str = get_default_database_url()

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

    # MQTT Export Settings
    mqtt_enabled: bool = os.environ.get("MQTT_ENABLED", "").lower() == "true"
    mqtt_host: str = os.environ.get("MQTT_HOST", "core-mosquitto")
    mqtt_port: int = int(os.environ.get("MQTT_PORT", "1883"))
    mqtt_username: str = os.environ.get("MQTT_USER", "")
    mqtt_password: str = os.environ.get("MQTT_PASSWORD", "")
    mqtt_auto_publish: bool = os.environ.get("MQTT_AUTO_PUBLISH", "").lower() == "true"
    mqtt_publish_interval: int = int(os.environ.get("MQTT_PUBLISH_INTERVAL", "60"))

    # Wetterdienst-Einstellungen
    # Provider: "auto", "open-meteo", "brightsky", "open-meteo-solar"
    wetter_provider: str = os.environ.get("WETTER_PROVIDER", "auto")

    # Bright Sky API (DWD-Daten als REST-API)
    brightsky_api_url: str = "https://api.brightsky.dev"
    brightsky_enabled: bool = os.environ.get("BRIGHTSKY_ENABLED", "true").lower() == "true"

    # Open-Meteo Solar API (GTI + PV-Prognose)
    open_meteo_solar_enabled: bool = os.environ.get("OPEN_METEO_SOLAR_ENABLED", "true").lower() == "true"
    open_meteo_solar_api_url: str = "https://api.open-meteo.com/v1/forecast"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


# Singleton Instance
settings = Settings()
