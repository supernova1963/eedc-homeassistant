"""
HA MQTT Sync Service.

Synchronisiert Monatsdaten zwischen Home Assistant und EEDC via MQTT.
Erstellt automatisch die benötigten MQTT Entities für die Monatswert-Berechnung.
"""

import os
from datetime import datetime
from typing import Optional, Any
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.models.anlage import Anlage
from backend.models.investition import Investition
from backend.services.mqtt_client import MQTTClient, MQTTConfig
from backend.core.database import get_session


def _get_mqtt_config_from_env() -> MQTTConfig:
    """Lädt MQTT-Konfiguration aus Umgebungsvariablen."""
    return MQTTConfig(
        host=os.environ.get("MQTT_HOST", "core-mosquitto"),
        port=int(os.environ.get("MQTT_PORT", "1883")),
        username=os.environ.get("MQTT_USER") or None,
        password=os.environ.get("MQTT_PASSWORD") or None,
    )


@dataclass
class SetupResult:
    """Ergebnis des Sensor-Setups."""
    success: bool
    message: str
    created_sensors: int
    errors: list[str]


@dataclass
class RolloverResult:
    """Ergebnis des Monatswechsels."""
    success: bool
    message: str
    updated_fields: int
    errors: list[str]


# Mapping von EEDC-Feldern zu Display-Namen und Icons
FELD_CONFIG = {
    # Basis-Sensoren
    "einspeisung": {
        "name": "Einspeisung",
        "icon_start": "mdi:transmission-tower-export",
        "icon_monat": "mdi:transmission-tower-export",
    },
    "netzbezug": {
        "name": "Netzbezug",
        "icon_start": "mdi:transmission-tower-import",
        "icon_monat": "mdi:transmission-tower-import",
    },
    "pv_gesamt": {
        "name": "PV Erzeugung",
        "icon_start": "mdi:solar-power",
        "icon_monat": "mdi:solar-power",
    },
    # Investition-Felder: PV-Module
    "pv_erzeugung_kwh": {
        "name": "PV Erzeugung",
        "icon_start": "mdi:solar-panel-large",
        "icon_monat": "mdi:solar-panel-large",
    },
    # Investition-Felder: Speicher
    "ladung_kwh": {
        "name": "Speicher Ladung",
        "icon_start": "mdi:battery-charging",
        "icon_monat": "mdi:battery-charging",
    },
    "entladung_kwh": {
        "name": "Speicher Entladung",
        "icon_start": "mdi:battery-arrow-down",
        "icon_monat": "mdi:battery-arrow-down",
    },
    "ladung_netz_kwh": {
        "name": "Speicher Netzladung",
        "icon_start": "mdi:battery-sync",
        "icon_monat": "mdi:battery-sync",
    },
    # Investition-Felder: Wärmepumpe
    "stromverbrauch_kwh": {
        "name": "WP Stromverbrauch",
        "icon_start": "mdi:heat-pump",
        "icon_monat": "mdi:heat-pump",
    },
    "heizenergie_kwh": {
        "name": "Heizenergie",
        "icon_start": "mdi:radiator",
        "icon_monat": "mdi:radiator",
    },
    "warmwasser_kwh": {
        "name": "Warmwasser",
        "icon_start": "mdi:water-boiler",
        "icon_monat": "mdi:water-boiler",
    },
    # Investition-Felder: E-Auto/Wallbox
    "ladung_pv_kwh": {
        "name": "E-Auto Ladung PV",
        "icon_start": "mdi:ev-station",
        "icon_monat": "mdi:ev-station",
    },
    "ladung_netz_kwh": {
        "name": "E-Auto Ladung Netz",
        "icon_start": "mdi:ev-plug-type2",
        "icon_monat": "mdi:ev-plug-type2",
    },
    "v2h_entladung_kwh": {
        "name": "V2H Entladung",
        "icon_start": "mdi:car-electric",
        "icon_monat": "mdi:car-electric",
    },
}


class HAMqttSyncService:
    """Synchronisiert Monatsdaten zwischen HA und EEDC via MQTT."""

    def __init__(self, mqtt_client: Optional[MQTTClient] = None):
        if mqtt_client:
            self.mqtt = mqtt_client
        else:
            # MQTT-Konfiguration aus Umgebungsvariablen laden
            config = _get_mqtt_config_from_env()
            self.mqtt = MQTTClient(config)

    async def setup_sensors_for_anlage(
        self,
        anlage: Anlage,
    ) -> SetupResult:
        """
        Erstellt alle MQTT Entities für eine Anlage basierend auf dem Sensor-Mapping.

        Für jeden Eintrag im Mapping mit Strategie "sensor" werden erstellt:
        - number.eedc_{anlage}_mwd_{feld}_start
        - sensor.eedc_{anlage}_mwd_{feld}_monat

        Args:
            anlage: Anlage mit sensor_mapping

        Returns:
            SetupResult mit Statistiken
        """
        if not anlage.sensor_mapping:
            return SetupResult(
                success=False,
                message="Kein Sensor-Mapping konfiguriert",
                created_sensors=0,
                errors=["sensor_mapping ist leer"]
            )

        mapping = anlage.sensor_mapping
        errors: list[str] = []
        created = 0

        # Basis-Sensoren
        basis = mapping.get("basis", {})
        for feld, config in basis.items():
            if config and config.get("strategie") == "sensor" and config.get("sensor_id"):
                success = await self._create_mwd_sensor_pair(
                    anlage_id=anlage.id,
                    anlage_name=anlage.anlagenname,
                    feld=feld,
                    source_sensor=config["sensor_id"],
                )
                if success:
                    created += 1
                else:
                    errors.append(f"Fehler bei Basis-Sensor {feld}")

        # Investition-Sensoren - lade Investitionen für die Namen
        inv_namen: dict[str, str] = {}
        async with get_session() as session:
            result = await session.execute(
                select(Investition).where(Investition.anlage_id == anlage.id)
            )
            for inv in result.scalars().all():
                inv_namen[str(inv.id)] = inv.bezeichnung

        investitionen = mapping.get("investitionen", {})
        for inv_id, inv_config in investitionen.items():
            # inv_config hat Struktur {"felder": {...}} - extrahiere die Felder
            if isinstance(inv_config, dict):
                felder = inv_config.get("felder", inv_config)  # Fallback auf inv_config selbst
            else:
                felder = {}

            # Investitionsname für eindeutige Entity-Namen
            inv_name = inv_namen.get(inv_id, f"Inv{inv_id}")

            for feld, config in felder.items():
                if config and config.get("strategie") == "sensor" and config.get("sensor_id"):
                    # Eindeutiger Key mit Investition-ID
                    feld_key = f"inv{inv_id}_{feld}"
                    success = await self._create_mwd_sensor_pair(
                        anlage_id=anlage.id,
                        anlage_name=anlage.anlagenname,
                        feld=feld_key,
                        source_sensor=config["sensor_id"],
                        display_feld=feld,
                        investition_name=inv_name,
                    )
                    if success:
                        created += 1
                    else:
                        errors.append(f"Fehler bei Investition {inv_id} Sensor {feld}")

        return SetupResult(
            success=len(errors) == 0,
            message=f"{created} Sensor-Paare erstellt" if created > 0 else "Keine Sensoren erstellt",
            created_sensors=created,
            errors=errors
        )

    async def _create_mwd_sensor_pair(
        self,
        anlage_id: int,
        anlage_name: str,
        feld: str,
        source_sensor: str,
        display_feld: Optional[str] = None,
        investition_name: Optional[str] = None,
    ) -> bool:
        """
        Erstellt ein Sensor-Paar (number + calculated sensor) für ein Feld.

        Args:
            anlage_id: ID der Anlage
            anlage_name: Name der Anlage
            feld: EEDC-Feld-Key (kann inv{id}_{feld} sein)
            source_sensor: HA-Quell-Sensor
            display_feld: Optionaler Feld-Name für Display (sonst = feld)
            investition_name: Name der Investition für eindeutige Entity-Namen

        Returns:
            True wenn beide Entities erstellt wurden
        """
        display = display_feld or feld
        config = FELD_CONFIG.get(display, {
            "name": display.replace("_", " ").title(),
            "icon_start": "mdi:counter",
            "icon_monat": "mdi:chart-line",
        })

        # Bei Investitionen: Name der Investition zum Display-Namen hinzufügen
        # z.B. "BYD HVS 12.8 Ladung" statt nur "Speicher Ladung"
        if investition_name:
            # Extrahiere sinnvollen Suffix aus config name
            # "Speicher Ladung" -> "Ladung", "E-Auto Ladung Netz" -> "Ladung Netz"
            name_parts = config['name'].split()
            # Entferne Präfixe wie "Speicher", "E-Auto", "WP"
            prefixes = ["Speicher", "E-Auto", "WP"]
            suffix_parts = [p for p in name_parts if p not in prefixes]
            suffix = " ".join(suffix_parts) if suffix_parts else name_parts[-1]
            display_name = f"{investition_name} {suffix}"
        else:
            display_name = config['name']

        start_key = f"mwd_{feld}_start"
        monat_key = f"mwd_{feld}_monat"

        # 1. Number Entity für Startwert
        number_ok = await self.mqtt.publish_number_discovery(
            key=start_key,
            name=f"EEDC {display_name} Monatsanfang",
            anlage_id=anlage_id,
            anlage_name=anlage_name,
            unit="kWh",
            icon=config["icon_start"],
        )

        if not number_ok:
            return False

        # 2. Calculated Sensor für Monatswert
        sensor_ok = await self.mqtt.publish_calculated_sensor(
            key=monat_key,
            name=f"EEDC {display_name} Monat",
            anlage_id=anlage_id,
            anlage_name=anlage_name,
            source_sensor=source_sensor,
            start_number_key=start_key,
            unit="kWh",
            icon=config["icon_monat"],
        )

        return sensor_ok

    async def trigger_month_rollover(
        self,
        anlage: Anlage,
        jahr: int,
        monat: int,
        zaehlerstaende: dict[str, float],
    ) -> RolloverResult:
        """
        Führt Monatswechsel durch: Publiziert neue Startwerte auf MQTT.

        Wird am 1. des Monats aufgerufen (oder manuell im Wizard).

        Args:
            anlage: Anlage
            jahr: Jahr des neuen Monats
            monat: Monat des neuen Monats
            zaehlerstaende: Dict mit aktuellen Zählerständen {feld: wert}

        Returns:
            RolloverResult mit Statistiken
        """
        if not anlage.sensor_mapping:
            return RolloverResult(
                success=False,
                message="Kein Sensor-Mapping konfiguriert",
                updated_fields=0,
                errors=["sensor_mapping ist leer"]
            )

        errors: list[str] = []
        updated = 0

        for feld, wert in zaehlerstaende.items():
            start_key = f"mwd_{feld}_start"
            success = await self.mqtt.update_month_start_value(
                anlage_id=anlage.id,
                key=start_key,
                wert=wert,
            )
            if success:
                updated += 1
            else:
                errors.append(f"Fehler bei {feld}")

        return RolloverResult(
            success=len(errors) == 0,
            message=f"{updated} Startwerte aktualisiert für {monat:02d}/{jahr}",
            updated_fields=updated,
            errors=errors
        )

    async def publish_final_month_data(
        self,
        anlage_id: int,
        jahr: int,
        monat: int,
        daten: dict[str, Any],
    ) -> bool:
        """
        Publiziert finale Monatsdaten auf MQTT (retained).

        Args:
            anlage_id: ID der Anlage
            jahr: Jahr
            monat: Monat
            daten: Monatsdaten

        Returns:
            True wenn erfolgreich
        """
        return await self.mqtt.publish_monatsdaten(
            anlage_id=anlage_id,
            jahr=jahr,
            monat=monat,
            daten=daten,
        )

    async def remove_sensors_for_anlage(
        self,
        anlage: Anlage,
    ) -> dict:
        """
        Entfernt alle MQTT Entities einer Anlage.

        Args:
            anlage: Anlage mit sensor_mapping

        Returns:
            Dict mit Statistiken
        """
        if not anlage.sensor_mapping:
            return {"success": 0, "failed": 0}

        keys_to_remove: list[str] = []

        # Basis-Sensoren
        basis = anlage.sensor_mapping.get("basis", {})
        for feld, config in basis.items():
            if config and config.get("strategie") == "sensor":
                keys_to_remove.append(feld)

        # Investition-Sensoren
        investitionen = anlage.sensor_mapping.get("investitionen", {})
        for inv_id, inv_config in investitionen.items():
            # inv_config hat Struktur {"felder": {...}} - extrahiere die Felder
            if isinstance(inv_config, dict):
                felder = inv_config.get("felder", inv_config)  # Fallback auf inv_config selbst
            else:
                felder = {}
            for feld, config in felder.items():
                if config and config.get("strategie") == "sensor":
                    keys_to_remove.append(f"inv{inv_id}_{feld}")

        return await self.mqtt.remove_mwd_sensors(anlage.id, keys_to_remove)


# Singleton-Instanz
_ha_mqtt_sync_service: Optional[HAMqttSyncService] = None


def get_ha_mqtt_sync_service() -> HAMqttSyncService:
    """Gibt die Singleton-Instanz des Services zurück."""
    global _ha_mqtt_sync_service
    if _ha_mqtt_sync_service is None:
        _ha_mqtt_sync_service = HAMqttSyncService()
    return _ha_mqtt_sync_service
