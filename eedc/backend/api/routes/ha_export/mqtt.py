"""HA-Export — MQTT Discovery.

POST /api/mqtt/test · POST /api/mqtt/publish/{anlage_id} · DELETE /api/mqtt/remove/{anlage_id}
"""
# Reiner Umzug aus `api/routes/ha_export.py` (18.09.2026, Vorlage 8 des Refactorings grosser Dateien):
# Code 1:1 uebernommen, kein Verhaltenswechsel. Die Fassade `__init__.py` haengt den Router ein und exportiert
# die Namen weiter, die Aufrufer und Tests bisher aus dem Modul importierten.

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional
from backend.core.exceptions import not_found
from backend.api.deps import get_db
from backend.models.anlage import Anlage
from backend.services.activity_service import log_activity
from backend.services.mqtt_client import MQTTClient
from backend.services.ha_mqtt_sync import publish_anlage_sensors
from backend.services.mqtt_broker_settings import resolve_broker_config
from backend.api.routes.ha_export.schemas import MQTTConfigRequest

router = APIRouter()


# =============================================================================
# MQTT Endpoints
# =============================================================================

@router.post("/mqtt/test")
async def test_mqtt_connection(
    config: Optional[MQTTConfigRequest] = None,
    db: AsyncSession = Depends(get_db, scope="function"),
):
    """Testet die MQTT-Verbindung zum Broker (gemeinsamer Broker, B7-5)."""
    mqtt_config = await resolve_broker_config(
        db,
        config.host if config else None,
        config.port if config else None,
        config.username if config else None,
        config.password if config else None,
    )

    client = MQTTClient(mqtt_config)
    result = await client.test_connection()

    return result

@router.post("/mqtt/publish/{anlage_id}")
async def publish_sensors_mqtt(
    anlage_id: int,
    config: Optional[MQTTConfigRequest] = None,
    db: AsyncSession = Depends(get_db, scope="function")
):
    """
    Publiziert alle Sensoren einer Anlage via MQTT Discovery.

    Die Sensoren erscheinen automatisch in Home Assistant unter
    dem Device "eedc - {Anlagenname}".
    """
    # Anlage laden
    result = await db.execute(
        select(Anlage).where(Anlage.id == anlage_id)
    )
    anlage = result.scalar_one_or_none()

    if not anlage:
        raise not_found("Anlage")

    # Broker-Config: Override-Felder aus dem Request, sonst gemeinsamer Broker
    # (DB-Broker-Block → ENV, #655/B7-5).
    mqtt_config = await resolve_broker_config(
        db,
        config.host if config else None,
        config.port if config else None,
        config.username if config else None,
        config.password if config else None,
    )

    # Zentraler Outbound-Pfad — identisch zum Auto-Publish (#655); ohne Open-Meteo-Jitter, der
    # Anwender wartet auf diese Antwort (N-531).
    pub = await publish_anlage_sensors(db, anlage, mqtt_config, skip_jitter=True)

    if not pub["available"]:
        raise HTTPException(
            status_code=503,
            detail="MQTT nicht verfügbar. Bitte aiomqtt installieren: pip install aiomqtt"
        )
    if pub["no_data"]:
        raise HTTPException(
            status_code=404,
            detail="Keine Monatsdaten vorhanden"
        )

    fehl = f", {pub['failed']} fehlgeschlagen" if pub["failed"] else ""
    # Fehlergründe in die Activity aufnehmen (#655: „X fehlgeschlagen" ohne Grund hilft nicht).
    grund = f" — z. B. {'; '.join(pub['errors'])}" if pub.get("errors") else ""
    await log_activity(
        kategorie="ha_export",
        aktion="MQTT-Sensoren publiziert",
        erfolg=pub["failed"] == 0,
        details=f"{pub['success']}/{pub['total']} Sensoren für {anlage.anlagenname}{fehl}{grund}",
        anlage_id=anlage.id,
        db=db,
    )

    return {
        "message": f"Sensoren für {anlage.anlagenname} publiziert",
        "anlage_id": anlage.id,
        "total": pub["total"],
        "success": pub["success"],
        "failed": pub["failed"],
        "errors": pub["errors"],
    }

@router.delete("/mqtt/remove/{anlage_id}")
async def remove_sensors_mqtt(
    anlage_id: int,
    config: Optional[MQTTConfigRequest] = None,
    db: AsyncSession = Depends(get_db, scope="function")
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
        raise not_found("Anlage")

    # B7-5: baute den MQTTConfig bisher von Hand aus ENV und umging damit den
    # Resolver — genau der Broker-Mismatch aus #655 (Remove traf einen anderen
    # Broker als Publish). Jetzt der gemeinsame Weg.
    mqtt_config = await resolve_broker_config(
        db,
        config.host if config else None,
        config.port if config else None,
        config.username if config else None,
        config.password if config else None,
    )

    client = MQTTClient(mqtt_config)

    if not client.is_available:
        raise HTTPException(
            status_code=503,
            detail="MQTT nicht verfügbar"
        )

    # ── Vollstaendig entfernen (#400) ────────────────────────────────────────
    #
    # ⛔ **Hier stand bis zum 28.08.2026 eine Liste aus drei Sensorgruppen**
    # (`ANLAGE_SENSOREN + PROGNOSE_SENSOREN + PREIS_SENSOREN`) — 34 von 44
    # anlagenweiten Definitionen und **kein einziger** geraetebezogener. Der Knopf
    # meldete dabei „erfolgreich, 34 entfernt". Wer aufraeumen wollte, behielt die
    # Investitions-, Speicher- und Status-Sensoren sowie alles, was seit dem
    # 27.08. je Geraet publiziert wird — und hielt es fuer geloescht.
    #
    # *Eine handgepflegte Liste neben einem wachsenden Publisher veraltet
    # zwangslaeufig; sie sagt nur nie, dass sie es getan hat.* Jetzt zaehlt
    # `belegte_sensor_eintraege` dieselbe Belegung auf, die der Publisher
    # beschreibt, und `remove_sensors` nimmt je Sensor **alle drei** retained
    # Topics zurueck (Config, Wert, Attribute).
    from backend.services.ha_mqtt_sync import belegte_sensor_eintraege

    # ── Bestandsgetrieben statt definitionsgetrieben (S2, 21.09.2026) ───────
    #
    # `belegte_sensor_eintraege` kennt die **heutigen** Definitionen. Was eedc
    # frueher publiziert hat, kennt nur der Broker: die MWD-Startwerte als
    # `homeassistant/number/eedc_*` (bis `77c6e211^`, 13.03.2026) liegen bei
    # jeder Installation von vorher bis heute retained auf dem Broker, und die
    # In-App-Hilfe beschrieb sie weiter als Weg zu den Startwerten. Mit
    # `anlage_id_bestand` fragt das Entfernen zusaetzlich den Bestand ab — nur
    # unter dem eigenen Praefix — und raeumt ihn mit.
    eintraege = await belegte_sensor_eintraege(db, anlage)
    ergebnis = await client.remove_sensors(eintraege, anlage_id_bestand=anlage.id)

    if ergebnis["fehler"]:
        raise HTTPException(
            status_code=502,
            detail=f"Entfernen fehlgeschlagen: {ergebnis['fehler']}",
        )

    await log_activity(
        kategorie="ha_export",
        aktion="MQTT-Sensoren entfernt",
        erfolg=True,
        details=(
            f"{ergebnis['sensoren']} Sensorstellen / {ergebnis['topics']} Topics "
            f"für {anlage.anlagenname}"
            # Die Altlast steht ausdruecklich daneben: sie ist der Teil, den
            # der Anwender nicht erwartet hat, und genau deshalb der, von dem
            # er erfahren soll.
            + (f" (davon {len(ergebnis.get('altlast_topics') or [])} aus "
               f"früheren Versionen)" if ergebnis.get("altlast_topics") else "")
        ),
        anlage_id=anlage.id,
        db=db,
    )

    return {
        "message": f"Sensoren für {anlage.anlagenname} entfernt",
        "anlage_id": anlage.id,
        "removed": ergebnis["sensoren"],
        "topics": ergebnis["topics"],
        "altlast_topics": ergebnis.get("altlast_topics") or [],
    }
