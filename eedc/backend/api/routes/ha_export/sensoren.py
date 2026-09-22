"""HA-Export — die REST-Sichten.

GET /api/sensors · GET /api/sensors/{anlage_id} · GET /api/yaml/{anlage_id} · GET /api/definitions
"""
# Reiner Umzug aus `api/routes/ha_export.py` (18.09.2026, Vorlage 8 des Refactorings grosser Dateien):
# Code 1:1 uebernommen, kein Verhaltenswechsel. Die Fassade `__init__.py` haengt den Router ein und exportiert
# die Namen weiter, die Aufrufer und Tests bisher aus dem Modul importierten.

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional
from backend.core.exceptions import not_found
from backend.api.deps import get_db
from backend.api.routes.strompreise import lade_tarife_fuer_anlage
from backend.models.anlage import Anlage
from backend.models.investition import Investition
from backend.services.ha_sensors_export import get_all_sensor_definitions
from backend.services.mqtt_client import MQTTClient
from backend.api.routes.ha_export.anlage_sensoren import calculate_anlage_sensors
from backend.api.routes.ha_export.emob import _load_emob_pool_ctx
from backend.api.routes.ha_export.investition_sensoren import calculate_investition_sensors
from backend.api.routes.ha_export.schemas import AnlageExport, FullExportResponse, HAYamlSnippet, InvestitionExport, SensorExportItem

router = APIRouter()


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
        # Anlage-Sensoren berechnen — ohne Open-Meteo-Jitter (N-531): HA fragt diese Sicht per REST mit
        # 10 s Timeout ab; bis zu 30 s Wartezeit bei kaltem Cache hiessen einmal je Stunde „nicht verfügbar".
        # S3: ein Fenster-Kontext je Anlage, an alle Geraete weitergereicht.
        _kontext: dict = {}
        sensor_values = await calculate_anlage_sensors(
            db, anlage, skip_jitter=True, kontext_out=_kontext,
        )

        sensors = [
            SensorExportItem.von_sensorwert(sv)
            for sv in sensor_values
            if sv.value is not None  # B5/X-3: leer nur für MQTT (Zustand „unbekannt")
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

        # Strompreis für Investitions-Berechnungen — SoT statt Handquery
        # (N-200, dieselbe Begründung wie in `calculate_anlage_sensors`:
        # die Handquery verlor `gueltig_bis` und den `verwendung`-Filter und
        # las damit einen ausgelaufenen oder einen WP-/Wallbox-Spezialtarif
        # als allgemeinen Netzbezugspreis).
        strompreis = (await lade_tarife_fuer_anlage(db, anlage.id))["allgemein"]

        # Phase 2a: Emob-Pool-Kontext der Anlage einmalig bauen, damit die
        # per-Device-E-Auto-Sensoren bei evcc-Setups den km-anteiligen
        # Wallbox-Pool sehen (statt leerer E-Auto-IMD).
        emob_ctx = await _load_emob_pool_ctx(db, investitionen)

        # #398: der aktuelle Betriebsmodus je Wärmepumpe, einmal je Anlage
        # erhoben (eigener 60-s-Takt im Service, s. `betriebsmodus_live.py`).
        from backend.services.betriebsmodus_live import lade_betriebsmodus_live
        modus_map = await lade_betriebsmodus_live(db, anlage)

        for inv in investitionen:
            inv_sensors = await calculate_investition_sensors(
                db, inv, strompreis, emob_ctx, modus_map,
                fenster_ctx=_kontext.get("fenster"),
            )
            inv_sensor_items = [
                SensorExportItem.von_sensorwert(sv)
                for sv in inv_sensors
                if sv.value is not None  # B5/X-3: leer nur für MQTT (Zustand „unbekannt")
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
        raise not_found("Anlage")

    sensor_values = await calculate_anlage_sensors(db, anlage, skip_jitter=True)   # N-531: On-Demand ohne Jitter

    sensors = [
        SensorExportItem.von_sensorwert(sv)
        for sv in sensor_values
        if sv.value is not None  # B5/X-3: leer nur für MQTT (Zustand „unbekannt")
    ]

    return AnlageExport(
        anlage_id=anlage.id,
        anlage_name=anlage.anlagenname,
        sensors=sensors
    )

@router.get("/yaml/{anlage_id}", response_model=HAYamlSnippet)
async def get_ha_yaml_snippet(
    anlage_id: int,
    request: Request,
    host: Optional[str] = None,
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
        raise not_found("Anlage")

    sensor_values = await calculate_anlage_sensors(db, anlage, skip_jitter=True)   # N-531: On-Demand ohne Jitter

    # Erreichbaren Host bestimmen: expliziter ?host=-Override → Request-Host
    # (direkter Aufruf, z. B. 192.168.1.10:8099) → Platzhalter. Hinter
    # HA-Ingress zeigt der Request-Host auf den HA-Proxy — der ist für die
    # rest-Integration nicht nutzbar, dort bleibt nur der Platzhalter.
    # HA wertet in `rest: resource:` KEINE Templates aus; das frühere
    # `{{ eedc_addon_host }}` erzeugte 1:1 eingefügt eine ungültige URL und
    # damit gar keine Entitäten (rapahl 2026-06-10).
    ist_ingress = "x-ingress-path" in request.headers
    request_host = request.headers.get("host", "")
    if host:
        eedc_host = host if ":" in host else f"{host}:8099"
    elif request_host and not ist_ingress:
        eedc_host = request_host
    else:
        eedc_host = "<EEDC-IP>:8099"
    host_ist_platzhalter = eedc_host.startswith("<")

    # YAML generieren
    yaml_lines = [
        "# eedc Sensoren für Home Assistant (REST-Integration)",
        "# Füge dies in deine configuration.yaml ein und starte Home Assistant neu.",
    ]
    if host_ist_platzhalter:
        yaml_lines += [
            "# WICHTIG: <EEDC-IP> unten durch die Adresse ersetzen, unter der dein",
            "#          eedc direkt erreichbar ist (z. B. 192.168.1.10:8099).",
        ]
    yaml_lines += [
        "# Add-on-Hinweis: Port 8099 muss in den Add-on-Netzwerkeinstellungen",
        "# freigegeben sein, sonst kann Home Assistant diesen Endpunkt nicht erreichen.",
        "",
        "rest:",
        f'  - resource: "http://{eedc_host}/api/ha/export/sensors/{anlage_id}"',
        "    scan_interval: 3600  # Alle Stunde aktualisieren",
        "    sensor:",
    ]

    for sv in sensor_values:
        sensor = sv.definition
        safe_name = sensor.key.replace("_", " ").title()
        yaml_lines.append(f'      - name: "eedc {safe_name}"')
        yaml_lines.append(f'        unique_id: "eedc_{anlage_id}_{sensor.key}"')
        yaml_lines.append(f'        value_template: "{{{{ value_json.sensors | selectattr(\'key\', \'eq\', \'{sensor.key}\') | map(attribute=\'value\') | first }}}}"')
        if sensor.unit:
            yaml_lines.append(f'        unit_of_measurement: "{sensor.unit}"')
        if sensor.device_class:
            yaml_lines.append(f'        device_class: "{sensor.device_class}"')
        if sensor.state_class:
            yaml_lines.append(f'        state_class: "{sensor.state_class}"')
        yaml_lines.append("")

    yaml = "\n".join(yaml_lines)

    if host_ist_platzhalter:
        hinweis = (
            "eedc läuft hinter Ingress: Bitte <EEDC-IP> durch die direkte Adresse "
            "ersetzen und im HA-Add-on Port 8099 in den Netzwerk-Einstellungen freigeben."
        )
    else:
        hinweis = (
            f"Host {eedc_host} wurde aus deiner Aufruf-Adresse übernommen. "
            "Im HA-Add-on muss Port 8099 in den Netzwerk-Einstellungen freigegeben sein."
        )

    return HAYamlSnippet(
        yaml=yaml,
        sensor_count=len(sensor_values),
        hinweis=hinweis
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
            }
            for s in definitions
        ]
    }
