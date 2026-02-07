"""
Home Assistant Sensor Export API.

Ermöglicht das Exportieren von EEDC-KPIs als HA-Sensoren.
Unterstützt zwei Methoden:
1. REST API - HA liest Werte über rest platform
2. MQTT Discovery - Native HA-Entitäten via MQTT Auto-Discovery
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional, Any
import os

from backend.api.deps import get_db
from backend.models.anlage import Anlage
from backend.models.monatsdaten import Monatsdaten
from backend.models.investition import Investition
from backend.models.strompreis import Strompreis
from backend.services.ha_sensors_export import (
    SensorDefinition, SensorValue, SensorCategory,
    ANLAGE_SENSOREN, INVESTITION_SENSOREN, E_AUTO_SENSOREN,
    WAERMEPUMPE_SENSOREN, SPEICHER_SENSOREN,
    get_all_sensor_definitions
)
from backend.services.mqtt_client import MQTTClient, MQTTConfig

router = APIRouter(prefix="/ha/export", tags=["HA Export"])


# =============================================================================
# Pydantic Models
# =============================================================================

class MQTTConfigRequest(BaseModel):
    """MQTT-Broker Konfiguration."""
    host: str = "core-mosquitto"
    port: int = 1883
    username: Optional[str] = None
    password: Optional[str] = None


class SensorExportItem(BaseModel):
    """Einzelner Sensor im Export."""
    key: str
    name: str
    value: Any
    unit: str
    icon: str
    category: str
    formel: str
    berechnung: Optional[str] = None
    device_class: Optional[str] = None
    state_class: Optional[str] = None


class AnlageExport(BaseModel):
    """Export für eine Anlage."""
    anlage_id: int
    anlage_name: str
    sensors: list[SensorExportItem]


class InvestitionExport(BaseModel):
    """Export für eine Investition."""
    investition_id: int
    bezeichnung: str
    typ: str
    sensors: list[SensorExportItem]


class FullExportResponse(BaseModel):
    """Vollständiger Export aller Sensoren."""
    anlagen: list[AnlageExport]
    investitionen: list[InvestitionExport]
    sensor_count: int
    mqtt_available: bool


class HAYamlSnippet(BaseModel):
    """YAML-Snippet für HA configuration.yaml."""
    yaml: str
    sensor_count: int
    hinweis: str


class MQTTConfigResponse(BaseModel):
    """MQTT-Konfiguration aus Add-on Optionen."""
    enabled: bool
    host: str
    port: int
    username: str
    password: str  # Wird als Maske zurückgegeben wenn gesetzt
    auto_publish: bool
    publish_interval_minutes: int


# =============================================================================
# Hilfsfunktionen für Berechnungen
# =============================================================================

async def calculate_anlage_sensors(
    db: AsyncSession,
    anlage: Anlage
) -> list[SensorValue]:
    """Berechnet alle Sensor-Werte für eine Anlage."""
    # Monatsdaten laden
    result = await db.execute(
        select(Monatsdaten).where(Monatsdaten.anlage_id == anlage.id)
    )
    monatsdaten = result.scalars().all()

    if not monatsdaten:
        return []

    # Strompreis laden (aktuellster)
    result = await db.execute(
        select(Strompreis)
        .where(Strompreis.anlage_id == anlage.id)
        .order_by(Strompreis.gueltig_ab.desc())
        .limit(1)
    )
    strompreis = result.scalar_one_or_none()

    # Investitionen laden für ROI-Berechnung
    result = await db.execute(
        select(Investition)
        .where(Investition.anlage_id == anlage.id)
        .where(Investition.aktiv == True)
    )
    investitionen = result.scalars().all()

    # Summen berechnen
    pv_erzeugung = sum(m.pv_erzeugung_kwh or (m.einspeisung_kwh + (m.eigenverbrauch_kwh or 0)) for m in monatsdaten)
    direktverbrauch = sum(m.direktverbrauch_kwh or 0 for m in monatsdaten)
    eigenverbrauch = sum(m.eigenverbrauch_kwh or 0 for m in monatsdaten)
    einspeisung = sum(m.einspeisung_kwh for m in monatsdaten)
    netzbezug = sum(m.netzbezug_kwh for m in monatsdaten)
    gesamtverbrauch = sum(m.gesamtverbrauch_kwh or 0 for m in monatsdaten)

    # Speicher-Summen
    batterie_ladung = sum(m.batterie_ladung_kwh or 0 for m in monatsdaten)
    batterie_entladung = sum(m.batterie_entladung_kwh or 0 for m in monatsdaten)

    # Quoten
    autarkie = (eigenverbrauch / gesamtverbrauch * 100) if gesamtverbrauch > 0 else 0
    ev_quote = (eigenverbrauch / pv_erzeugung * 100) if pv_erzeugung > 0 else 0
    spez_ertrag = (pv_erzeugung / anlage.leistung_kwp) if anlage.leistung_kwp else 0

    # Finanzen
    einspeise_erloes = 0
    ev_ersparnis = 0
    if strompreis:
        einspeise_erloes = einspeisung * strompreis.einspeiseverguetung_cent_kwh / 100
        ev_ersparnis = eigenverbrauch * strompreis.netzbezug_arbeitspreis_cent_kwh / 100
    netto_ertrag = einspeise_erloes + ev_ersparnis

    # CO2
    co2_ersparnis = pv_erzeugung * 0.38  # kg CO2/kWh

    # Investitions-KPIs berechnen
    investition_gesamt = sum(i.anschaffungskosten_gesamt or 0 for i in investitionen)
    alternativ_gesamt = sum(i.anschaffungskosten_alternativ or 0 for i in investitionen)
    relevante_kosten = investition_gesamt - alternativ_gesamt

    # Jahresersparnis aus Monatsdaten berechnen (annualisiert)
    anzahl_monate = len(monatsdaten)
    if anzahl_monate > 0:
        jahres_ersparnis = (netto_ertrag / anzahl_monate) * 12
    else:
        jahres_ersparnis = 0

    # ROI und Amortisation
    roi_prozent = None
    amortisation_jahre = None
    if relevante_kosten > 0 and jahres_ersparnis > 0:
        roi_prozent = (jahres_ersparnis / relevante_kosten) * 100
        amortisation_jahre = relevante_kosten / jahres_ersparnis

    # Speicher-KPIs berechnen
    speicher_effizienz = None
    speicher_zyklen = None

    # Speicher-Kapazität aus Investitionen ermitteln
    speicher_kapazitaet = 0
    for inv in investitionen:
        if inv.typ == 'speicher' and inv.parameter:
            kap = inv.parameter.get('kapazitaet_kwh') or inv.parameter.get('nutzbare_kapazitaet_kwh')
            if kap:
                speicher_kapazitaet += float(kap)

    if batterie_ladung > 0:
        speicher_effizienz = (batterie_entladung / batterie_ladung) * 100
    if speicher_kapazitaet > 0 and batterie_entladung > 0:
        speicher_zyklen = batterie_entladung / speicher_kapazitaet

    # Sensor-Werte erstellen
    sensor_values = []

    # Energie-Sensoren
    for sensor in ANLAGE_SENSOREN:
        value = None
        berechnung = None

        if sensor.key == "pv_erzeugung_gesamt_kwh":
            value = round(pv_erzeugung, 1)
            berechnung = f"Summe aus {len(monatsdaten)} Monaten"
        elif sensor.key == "direktverbrauch_gesamt_kwh":
            value = round(direktverbrauch, 1)
            berechnung = f"PV direkt verbraucht (ohne Speicher)"
        elif sensor.key == "eigenverbrauch_gesamt_kwh":
            value = round(eigenverbrauch, 1)
        elif sensor.key == "einspeisung_gesamt_kwh":
            value = round(einspeisung, 1)
        elif sensor.key == "netzbezug_gesamt_kwh":
            value = round(netzbezug, 1)
        elif sensor.key == "gesamtverbrauch_kwh":
            value = round(gesamtverbrauch, 1)
            berechnung = f"{eigenverbrauch:.0f} + {netzbezug:.0f}"
        elif sensor.key == "autarkie_prozent":
            value = round(autarkie, 1)
            berechnung = f"{eigenverbrauch:.0f} ÷ {gesamtverbrauch:.0f} × 100"
        elif sensor.key == "eigenverbrauch_quote_prozent":
            value = round(ev_quote, 1)
            berechnung = f"{eigenverbrauch:.0f} ÷ {pv_erzeugung:.0f} × 100"
        elif sensor.key == "spezifischer_ertrag_kwh_kwp":
            value = round(spez_ertrag, 0) if anlage.leistung_kwp else None
            if anlage.leistung_kwp:
                berechnung = f"{pv_erzeugung:.0f} ÷ {anlage.leistung_kwp:.1f}"
        elif sensor.key == "netto_ertrag_euro":
            value = round(netto_ertrag, 2)
            berechnung = f"{einspeise_erloes:.2f} + {ev_ersparnis:.2f}"
        elif sensor.key == "einspeise_erloes_euro":
            value = round(einspeise_erloes, 2)
            if strompreis:
                berechnung = f"{einspeisung:.0f} × {strompreis.einspeiseverguetung_cent_kwh:.2f} ct/kWh"
        elif sensor.key == "eigenverbrauch_ersparnis_euro":
            value = round(ev_ersparnis, 2)
            if strompreis:
                berechnung = f"{eigenverbrauch:.0f} × {strompreis.netzbezug_arbeitspreis_cent_kwh:.2f} ct/kWh"
        elif sensor.key == "co2_ersparnis_kg":
            value = round(co2_ersparnis, 1)
            berechnung = f"{pv_erzeugung:.0f} × 0.38"

        if value is not None:
            sensor_values.append(SensorValue(
                definition=sensor,
                value=value,
                berechnung=berechnung
            ))

    # Investitions-Sensoren
    for sensor in INVESTITION_SENSOREN:
        value = None
        berechnung = None

        if sensor.key == "investition_gesamt_euro":
            if investition_gesamt > 0:
                value = round(investition_gesamt, 2)
                berechnung = f"Summe aus {len(investitionen)} Investitionen"
        elif sensor.key == "jahres_ersparnis_euro":
            if jahres_ersparnis > 0:
                value = round(jahres_ersparnis, 2)
                berechnung = f"({netto_ertrag:.2f} ÷ {anzahl_monate}) × 12"
        elif sensor.key == "roi_prozent":
            if roi_prozent is not None:
                value = round(roi_prozent, 1)
                berechnung = f"{jahres_ersparnis:.2f} ÷ {relevante_kosten:.2f} × 100"
        elif sensor.key == "amortisation_jahre":
            if amortisation_jahre is not None:
                value = round(amortisation_jahre, 1)
                berechnung = f"{relevante_kosten:.2f} ÷ {jahres_ersparnis:.2f}"

        if value is not None:
            sensor_values.append(SensorValue(
                definition=sensor,
                value=value,
                berechnung=berechnung
            ))

    # Speicher-Sensoren (nur wenn Speicher vorhanden)
    if speicher_kapazitaet > 0 or batterie_ladung > 0:
        for sensor in SPEICHER_SENSOREN:
            value = None
            berechnung = None

            if sensor.key == "speicher_zyklen":
                if speicher_zyklen is not None:
                    value = round(speicher_zyklen, 0)
                    berechnung = f"{batterie_entladung:.0f} ÷ {speicher_kapazitaet:.1f}"
            elif sensor.key == "speicher_effizienz_prozent":
                if speicher_effizienz is not None:
                    value = round(speicher_effizienz, 1)
                    berechnung = f"{batterie_entladung:.0f} ÷ {batterie_ladung:.0f} × 100"

            if value is not None:
                sensor_values.append(SensorValue(
                    definition=sensor,
                    value=value,
                    berechnung=berechnung
                ))

    return sensor_values


async def calculate_investition_sensors(
    db: AsyncSession,
    investition: Investition,
    strompreis: Optional[Strompreis]
) -> list[SensorValue]:
    """Berechnet Sensor-Werte für eine Investition basierend auf Typ."""
    # TODO: Investitions-Monatsdaten laden und auswerten
    # Vorerst nur Basis-Daten aus dem ROI-Dashboard

    sensor_values = []

    # ROI-Basisdaten
    if investition.anschaffungskosten_gesamt:
        for sensor in INVESTITION_SENSOREN:
            if sensor.key == "investition_gesamt_euro":
                sensor_values.append(SensorValue(
                    definition=sensor,
                    value=investition.anschaffungskosten_gesamt,
                    berechnung=None
                ))

    return sensor_values


# =============================================================================
# API Endpoints
# =============================================================================

@router.get("/mqtt/config", response_model=MQTTConfigResponse)
async def get_mqtt_config():
    """
    Gibt die MQTT-Konfiguration aus den Add-on Optionen zurück.

    Diese Werte werden in der HA Add-on Konfiguration gesetzt und
    können im Frontend für die MQTT-Einstellungen vorausgefüllt werden.
    """
    from backend.core.config import settings

    # Passwort als Maske zurückgeben wenn gesetzt
    password_masked = "••••••" if settings.mqtt_password else ""

    return MQTTConfigResponse(
        enabled=settings.mqtt_enabled,
        host=settings.mqtt_host,
        port=settings.mqtt_port,
        username=settings.mqtt_username,
        password=password_masked,
        auto_publish=settings.mqtt_auto_publish,
        publish_interval_minutes=settings.mqtt_publish_interval,
    )


@router.get("/sensors", response_model=FullExportResponse)
async def get_all_sensors(db: AsyncSession = Depends(get_db)):
    """
    Gibt alle EEDC-Sensoren mit aktuellen Werten zurück.

    Dieser Endpoint kann von HA über die `rest` Platform abgefragt werden
    oder dient als Übersicht für die MQTT-Konfiguration.
    """
    # Anlagen laden
    result = await db.execute(select(Anlage))
    anlagen = result.scalars().all()

    anlagen_exports = []
    investitionen_exports = []
    total_sensors = 0

    for anlage in anlagen:
        # Anlage-Sensoren berechnen
        sensor_values = await calculate_anlage_sensors(db, anlage)

        sensors = [
            SensorExportItem(
                key=sv.definition.key,
                name=sv.definition.name,
                value=sv.value,
                unit=sv.definition.unit,
                icon=sv.definition.icon,
                category=sv.definition.category.value,
                formel=sv.definition.formel,
                berechnung=sv.berechnung,
                device_class=sv.definition.device_class,
                state_class=sv.definition.state_class,
            )
            for sv in sensor_values
        ]

        if sensors:
            anlagen_exports.append(AnlageExport(
                anlage_id=anlage.id,
                anlage_name=anlage.anlagenname,
                sensors=sensors
            ))
            total_sensors += len(sensors)

        # Investitionen dieser Anlage laden
        result = await db.execute(
            select(Investition).where(Investition.anlage_id == anlage.id)
        )
        investitionen = result.scalars().all()

        # Strompreis für Investitions-Berechnungen
        result = await db.execute(
            select(Strompreis)
            .where(Strompreis.anlage_id == anlage.id)
            .order_by(Strompreis.gueltig_ab.desc())
            .limit(1)
        )
        strompreis = result.scalar_one_or_none()

        for inv in investitionen:
            inv_sensors = await calculate_investition_sensors(db, inv, strompreis)
            inv_sensor_items = [
                SensorExportItem(
                    key=sv.definition.key,
                    name=sv.definition.name,
                    value=sv.value,
                    unit=sv.definition.unit,
                    icon=sv.definition.icon,
                    category=sv.definition.category.value,
                    formel=sv.definition.formel,
                    berechnung=sv.berechnung,
                    device_class=sv.definition.device_class,
                    state_class=sv.definition.state_class,
                )
                for sv in inv_sensors
            ]

            if inv_sensor_items:
                investitionen_exports.append(InvestitionExport(
                    investition_id=inv.id,
                    bezeichnung=inv.bezeichnung,
                    typ=inv.typ,
                    sensors=inv_sensor_items
                ))
                total_sensors += len(inv_sensor_items)

    # MQTT-Verfügbarkeit prüfen
    mqtt_client = MQTTClient()

    return FullExportResponse(
        anlagen=anlagen_exports,
        investitionen=investitionen_exports,
        sensor_count=total_sensors,
        mqtt_available=mqtt_client.is_available
    )


@router.get("/sensors/{anlage_id}", response_model=AnlageExport)
async def get_anlage_sensors(
    anlage_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Gibt Sensoren für eine spezifische Anlage zurück."""
    result = await db.execute(
        select(Anlage).where(Anlage.id == anlage_id)
    )
    anlage = result.scalar_one_or_none()

    if not anlage:
        raise HTTPException(status_code=404, detail="Anlage nicht gefunden")

    sensor_values = await calculate_anlage_sensors(db, anlage)

    sensors = [
        SensorExportItem(
            key=sv.definition.key,
            name=sv.definition.name,
            value=sv.value,
            unit=sv.definition.unit,
            icon=sv.definition.icon,
            category=sv.definition.category.value,
            formel=sv.definition.formel,
            berechnung=sv.berechnung,
            device_class=sv.definition.device_class,
            state_class=sv.definition.state_class,
        )
        for sv in sensor_values
    ]

    return AnlageExport(
        anlage_id=anlage.id,
        anlage_name=anlage.anlagenname,
        sensors=sensors
    )


@router.get("/yaml/{anlage_id}", response_model=HAYamlSnippet)
async def get_ha_yaml_snippet(
    anlage_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Generiert ein YAML-Snippet für die HA configuration.yaml.

    Dieses Snippet kann in die HA-Konfiguration kopiert werden,
    um die EEDC-Sensoren über die REST-Platform einzubinden.
    """
    result = await db.execute(
        select(Anlage).where(Anlage.id == anlage_id)
    )
    anlage = result.scalar_one_or_none()

    if not anlage:
        raise HTTPException(status_code=404, detail="Anlage nicht gefunden")

    sensor_values = await calculate_anlage_sensors(db, anlage)

    # YAML generieren
    yaml_lines = [
        "# EEDC Sensoren für Home Assistant",
        "# Füge dies in deine configuration.yaml ein",
        "",
        "rest:",
        f'  - resource: "http://{{{{ eedc_addon_host }}}}:8099/api/ha/export/sensors/{anlage_id}"',
        "    scan_interval: 3600  # Alle Stunde aktualisieren",
        "    sensor:",
    ]

    for sv in sensor_values:
        sensor = sv.definition
        safe_name = sensor.key.replace("_", " ").title()
        yaml_lines.append(f'      - name: "EEDC {safe_name}"')
        yaml_lines.append(f'        unique_id: "eedc_{anlage_id}_{sensor.key}"')
        yaml_lines.append(f'        value_template: "{{{{ value_json.sensors | selectattr(\'key\', \'eq\', \'{sensor.key}\') | map(attribute=\'value\') | first }}}}"')
        yaml_lines.append(f'        unit_of_measurement: "{sensor.unit}"')
        if sensor.device_class:
            yaml_lines.append(f'        device_class: "{sensor.device_class}"')
        if sensor.state_class:
            yaml_lines.append(f'        state_class: "{sensor.state_class}"')
        yaml_lines.append("")

    yaml = "\n".join(yaml_lines)

    return HAYamlSnippet(
        yaml=yaml,
        sensor_count=len(sensor_values),
        hinweis="Ersetze {{ eedc_addon_host }} mit der IP deines HA oder nutze 'homeassistant.local'"
    )


@router.get("/definitions")
async def get_sensor_definitions():
    """Gibt alle verfügbaren Sensor-Definitionen zurück."""
    definitions = get_all_sensor_definitions()

    return {
        "count": len(definitions),
        "sensors": [
            {
                "key": s.key,
                "name": s.name,
                "unit": s.unit,
                "icon": s.icon,
                "category": s.category.value,
                "formel": s.formel,
                "device_class": s.device_class,
                "state_class": s.state_class,
                "enabled_by_default": s.enabled_by_default,
            }
            for s in definitions
        ]
    }


# =============================================================================
# MQTT Endpoints
# =============================================================================

@router.post("/mqtt/test")
async def test_mqtt_connection(config: Optional[MQTTConfigRequest] = None):
    """Testet die MQTT-Verbindung zum Broker."""
    mqtt_config = MQTTConfig(
        host=config.host if config else os.environ.get("MQTT_HOST", "core-mosquitto"),
        port=config.port if config else int(os.environ.get("MQTT_PORT", "1883")),
        username=config.username if config else os.environ.get("MQTT_USER"),
        password=config.password if config else os.environ.get("MQTT_PASSWORD"),
    )

    client = MQTTClient(mqtt_config)
    result = await client.test_connection()

    return result


@router.post("/mqtt/publish/{anlage_id}")
async def publish_sensors_mqtt(
    anlage_id: int,
    config: Optional[MQTTConfigRequest] = None,
    db: AsyncSession = Depends(get_db)
):
    """
    Publiziert alle Sensoren einer Anlage via MQTT Discovery.

    Die Sensoren erscheinen automatisch in Home Assistant unter
    dem Device "EEDC - {Anlagenname}".
    """
    # Anlage laden
    result = await db.execute(
        select(Anlage).where(Anlage.id == anlage_id)
    )
    anlage = result.scalar_one_or_none()

    if not anlage:
        raise HTTPException(status_code=404, detail="Anlage nicht gefunden")

    # MQTT Client konfigurieren
    mqtt_config = MQTTConfig(
        host=config.host if config else os.environ.get("MQTT_HOST", "core-mosquitto"),
        port=config.port if config else int(os.environ.get("MQTT_PORT", "1883")),
        username=config.username if config else os.environ.get("MQTT_USER"),
        password=config.password if config else os.environ.get("MQTT_PASSWORD"),
    )

    client = MQTTClient(mqtt_config)

    if not client.is_available:
        raise HTTPException(
            status_code=503,
            detail="MQTT nicht verfügbar. Bitte aiomqtt installieren: pip install aiomqtt"
        )

    # Sensoren berechnen
    sensor_values = await calculate_anlage_sensors(db, anlage)

    if not sensor_values:
        raise HTTPException(
            status_code=404,
            detail="Keine Monatsdaten vorhanden"
        )

    # Via MQTT publizieren
    result = await client.publish_all_sensors(
        sensor_values,
        anlage.id,
        anlage.anlagenname
    )

    return {
        "message": f"Sensoren für {anlage.anlagenname} publiziert",
        "anlage_id": anlage.id,
        **result
    }


@router.delete("/mqtt/remove/{anlage_id}")
async def remove_sensors_mqtt(
    anlage_id: int,
    config: Optional[MQTTConfigRequest] = None,
    db: AsyncSession = Depends(get_db)
):
    """
    Entfernt alle EEDC-Sensoren einer Anlage aus Home Assistant.

    Die Sensoren werden aus dem MQTT Discovery entfernt und
    verschwinden aus HA.
    """
    # Anlage laden
    result = await db.execute(
        select(Anlage).where(Anlage.id == anlage_id)
    )
    anlage = result.scalar_one_or_none()

    if not anlage:
        raise HTTPException(status_code=404, detail="Anlage nicht gefunden")

    # MQTT Client konfigurieren
    mqtt_config = MQTTConfig(
        host=config.host if config else os.environ.get("MQTT_HOST", "core-mosquitto"),
        port=config.port if config else int(os.environ.get("MQTT_PORT", "1883")),
        username=config.username if config else os.environ.get("MQTT_USER"),
        password=config.password if config else os.environ.get("MQTT_PASSWORD"),
    )

    client = MQTTClient(mqtt_config)

    if not client.is_available:
        raise HTTPException(
            status_code=503,
            detail="MQTT nicht verfügbar"
        )

    # Alle Anlage-Sensoren entfernen
    removed = 0
    for sensor in ANLAGE_SENSOREN:
        if await client.remove_sensor(sensor, anlage.id):
            removed += 1

    return {
        "message": f"Sensoren für {anlage.anlagenname} entfernt",
        "anlage_id": anlage.id,
        "removed": removed
    }
