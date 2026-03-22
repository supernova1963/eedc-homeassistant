"""
MQTT Gateway API — Topic-Mapping CRUD + Status + Test.

Endpoints unter /api/live/mqtt/gateway/...
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_db
from backend.models.mqtt_gateway_mapping import MqttGatewayMapping
from backend.services.mqtt_gateway_service import (
    GatewayMapping,
    get_mqtt_gateway_service,
    transform_payload,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ─── Pydantic Models ─────────────────────────────────────────────────

class MappingCreate(BaseModel):
    anlage_id: int
    quell_topic: str = Field(..., min_length=1, max_length=500)
    ziel_key: str = Field(..., min_length=1, max_length=200)
    payload_typ: str = Field(default="plain", pattern=r"^(plain|json|json_array)$")
    json_pfad: Optional[str] = None
    array_index: Optional[int] = None
    faktor: float = 1.0
    offset: float = 0.0
    invertieren: bool = False
    aktiv: bool = True
    beschreibung: Optional[str] = None


class MappingUpdate(BaseModel):
    quell_topic: Optional[str] = None
    ziel_key: Optional[str] = None
    payload_typ: Optional[str] = None
    json_pfad: Optional[str] = None
    array_index: Optional[int] = None
    faktor: Optional[float] = None
    offset: Optional[float] = None
    invertieren: Optional[bool] = None
    aktiv: Optional[bool] = None
    beschreibung: Optional[str] = None


class MappingResponse(BaseModel):
    id: int
    anlage_id: int
    quell_topic: str
    ziel_key: str
    payload_typ: str
    json_pfad: Optional[str]
    array_index: Optional[int]
    faktor: float
    offset: float
    invertieren: bool
    aktiv: bool
    beschreibung: Optional[str]
    erstellt_am: str


class TestTopicRequest(BaseModel):
    topic: str = Field(..., min_length=1)
    timeout_s: int = Field(default=10, ge=1, le=30)


class TestTopicResponse(BaseModel):
    empfangen: bool
    payload_raw: Optional[str] = None
    payload_typ_erkannt: Optional[str] = None
    wert: Optional[float] = None
    wartezeit_s: Optional[float] = None
    fehler: Optional[str] = None


class TransformTestRequest(BaseModel):
    payload: str
    payload_typ: str = "plain"
    json_pfad: Optional[str] = None
    array_index: Optional[int] = None
    faktor: float = 1.0
    offset: float = 0.0
    invertieren: bool = False


# ─── Helper ──────────────────────────────────────────────────────────

def _db_to_response(m: MqttGatewayMapping) -> dict:
    return {
        "id": m.id,
        "anlage_id": m.anlage_id,
        "quell_topic": m.quell_topic,
        "ziel_key": m.ziel_key,
        "payload_typ": m.payload_typ,
        "json_pfad": m.json_pfad,
        "array_index": m.array_index,
        "faktor": m.faktor,
        "offset": m.offset,
        "invertieren": m.invertieren,
        "aktiv": m.aktiv,
        "beschreibung": m.beschreibung,
        "erstellt_am": m.erstellt_am.isoformat() if m.erstellt_am else "",
    }


def _db_to_gateway_mapping(m: MqttGatewayMapping) -> GatewayMapping:
    return GatewayMapping(
        id=m.id,
        anlage_id=m.anlage_id,
        quell_topic=m.quell_topic,
        ziel_key=m.ziel_key,
        payload_typ=m.payload_typ or "plain",
        json_pfad=m.json_pfad,
        array_index=m.array_index,
        faktor=m.faktor if m.faktor is not None else 1.0,
        offset=m.offset if m.offset is not None else 0.0,
        invertieren=bool(m.invertieren),
    )


async def _reload_gateway(db: AsyncSession) -> dict:
    """Lädt alle aktiven Mappings und reloaded den Gateway-Service."""
    svc = get_mqtt_gateway_service()
    if not svc:
        return {"reloaded": False, "grund": "Gateway-Service nicht initialisiert (MQTT nicht aktiv?)"}

    result = await db.execute(
        select(MqttGatewayMapping).where(MqttGatewayMapping.aktiv == True)
    )
    db_mappings = result.scalars().all()
    gw_mappings = [_db_to_gateway_mapping(m) for m in db_mappings]

    started = await svc.reload(gw_mappings)
    return {
        "reloaded": True,
        "aktiv": started,
        "mappings_geladen": len(gw_mappings),
    }


# ─── CRUD Endpoints ──────────────────────────────────────────────────

@router.get("/mqtt/gateway/mappings")
async def list_mappings(
    anlage_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
):
    """Alle Gateway-Mappings auflisten."""
    query = select(MqttGatewayMapping)
    if anlage_id is not None:
        query = query.where(MqttGatewayMapping.anlage_id == anlage_id)
    query = query.order_by(MqttGatewayMapping.anlage_id, MqttGatewayMapping.quell_topic)

    result = await db.execute(query)
    mappings = result.scalars().all()
    return [_db_to_response(m) for m in mappings]


@router.post("/mqtt/gateway/mappings", status_code=201)
async def create_mapping(
    data: MappingCreate,
    db: AsyncSession = Depends(get_db),
):
    """Neues Gateway-Mapping anlegen."""
    mapping = MqttGatewayMapping(
        anlage_id=data.anlage_id,
        quell_topic=data.quell_topic,
        ziel_key=data.ziel_key,
        payload_typ=data.payload_typ,
        json_pfad=data.json_pfad,
        array_index=data.array_index,
        faktor=data.faktor,
        offset=data.offset,
        invertieren=data.invertieren,
        aktiv=data.aktiv,
        beschreibung=data.beschreibung,
        erstellt_am=datetime.utcnow(),
    )
    db.add(mapping)
    await db.flush()
    await db.refresh(mapping)

    # Gateway hot-reload
    reload_result = await _reload_gateway(db)

    return {
        "mapping": _db_to_response(mapping),
        "gateway": reload_result,
    }


@router.put("/mqtt/gateway/mappings/{mapping_id}")
async def update_mapping(
    mapping_id: int,
    data: MappingUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Bestehendes Mapping bearbeiten."""
    result = await db.execute(
        select(MqttGatewayMapping).where(MqttGatewayMapping.id == mapping_id)
    )
    mapping = result.scalar_one_or_none()
    if not mapping:
        raise HTTPException(404, "Mapping nicht gefunden")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(mapping, field, value)

    await db.flush()
    await db.refresh(mapping)

    reload_result = await _reload_gateway(db)

    return {
        "mapping": _db_to_response(mapping),
        "gateway": reload_result,
    }


@router.delete("/mqtt/gateway/mappings/{mapping_id}")
async def delete_mapping(
    mapping_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Mapping löschen."""
    result = await db.execute(
        select(MqttGatewayMapping).where(MqttGatewayMapping.id == mapping_id)
    )
    mapping = result.scalar_one_or_none()
    if not mapping:
        raise HTTPException(404, "Mapping nicht gefunden")

    await db.delete(mapping)
    await db.flush()

    reload_result = await _reload_gateway(db)

    return {
        "geloescht": True,
        "gateway": reload_result,
    }


# ─── Status + Reload ─────────────────────────────────────────────────

@router.get("/mqtt/gateway/status")
async def get_gateway_status():
    """Status und Statistiken des Gateway-Service."""
    svc = get_mqtt_gateway_service()
    if not svc:
        return {
            "verfuegbar": False,
            "aktiv": False,
            "grund": "MQTT nicht aktiviert oder kein Gateway konfiguriert",
        }
    status = svc.get_status()
    status["verfuegbar"] = True
    return status


@router.post("/mqtt/gateway/reload")
async def reload_gateway(db: AsyncSession = Depends(get_db)):
    """Hot-Reload: Mappings neu laden und Service neu starten."""
    return await _reload_gateway(db)


# ─── Test-Endpoints ──────────────────────────────────────────────────

@router.post("/mqtt/gateway/test-topic")
async def test_topic(data: TestTopicRequest):
    """Subscribt kurz auf ein Topic und zeigt den empfangenen Payload.

    Nützlich um zu prüfen ob ein Topic Daten liefert bevor man ein Mapping erstellt.
    """
    try:
        import aiomqtt
    except ImportError:
        raise HTTPException(500, "aiomqtt nicht installiert")

    svc = get_mqtt_gateway_service()
    if not svc:
        # Fallback: MQTT-Inbound-Config nutzen
        from backend.services.mqtt_inbound_service import get_mqtt_inbound_service
        inbound = get_mqtt_inbound_service()
        if not inbound:
            raise HTTPException(400, "Kein MQTT-Service aktiv")
        host, port = inbound.host, inbound.port
        username, password = inbound.username, inbound.password
    else:
        host, port = svc.host, svc.port
        username, password = svc.username, svc.password

    start_time = asyncio.get_event_loop().time()

    try:
        import json as json_mod

        received_payload = None
        async with aiomqtt.Client(
            hostname=host,
            port=port,
            username=username,
            password=password,
            identifier=f"eedc-test-{int(start_time)}",
        ) as client:
            await client.subscribe(data.topic)

            try:
                async with asyncio.timeout(data.timeout_s):
                    async for message in client.messages:
                        received_payload = message.payload.decode("utf-8", errors="replace") if isinstance(message.payload, bytes) else str(message.payload)
                        break
            except asyncio.TimeoutError:
                pass

        elapsed = asyncio.get_event_loop().time() - start_time

        if received_payload is None:
            return TestTopicResponse(
                empfangen=False,
                wartezeit_s=round(elapsed, 1),
                fehler=f"Kein Payload nach {data.timeout_s}s empfangen",
            )

        # Payload-Typ erkennen
        payload_typ = "plain"
        try:
            parsed = json_mod.loads(received_payload)
            if isinstance(parsed, list):
                payload_typ = "json_array"
            elif isinstance(parsed, dict):
                payload_typ = "json"
        except (ValueError, TypeError):
            pass

        # Wert extrahieren (bei plain)
        wert = None
        try:
            wert = float(received_payload.strip())
        except ValueError:
            pass

        return TestTopicResponse(
            empfangen=True,
            payload_raw=received_payload[:2000],
            payload_typ_erkannt=payload_typ,
            wert=wert,
            wartezeit_s=round(elapsed, 1),
        )

    except Exception as e:
        return TestTopicResponse(
            empfangen=False,
            fehler=f"Verbindungsfehler: {e}",
        )


@router.post("/mqtt/gateway/test-transform")
async def test_transform(data: TransformTestRequest):
    """Testet die Payload-Transformation ohne ein Mapping zu erstellen."""
    wert = transform_payload(
        data.payload,
        data.payload_typ,
        data.json_pfad,
        data.array_index,
        data.faktor,
        data.offset,
        data.invertieren,
    )
    if wert is None:
        return {
            "erfolg": False,
            "fehler": "Transformation fehlgeschlagen — Payload konnte nicht extrahiert/konvertiert werden",
        }
    return {
        "erfolg": True,
        "wert": round(wert, 4),
        "ziel_payload": str(round(wert, 2)),
    }
