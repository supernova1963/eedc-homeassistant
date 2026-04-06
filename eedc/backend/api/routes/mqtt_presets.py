"""
MQTT Gateway Presets API — Geräte-Presets auflisten und anwenden.

Endpoints unter /api/live/mqtt/gateway/presets/...
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_db
from backend.models.mqtt_gateway_mapping import MqttGatewayMapping
from backend.services.mqtt_presets import list_presets, get_preset, generate_mappings

logger = logging.getLogger(__name__)

router = APIRouter()


# ─── Pydantic Models ─────────────────────────────────────────────────

class PresetVariableResponse(BaseModel):
    key: str
    label: str
    placeholder: str
    hinweis: str


class PresetMappingResponse(BaseModel):
    topic_template: str
    ziel_key: str
    beschreibung: str
    payload_typ: str
    json_pfad: Optional[str]
    faktor: float
    invertieren: bool


class PresetResponse(BaseModel):
    id: str
    name: str
    hersteller: str
    gruppe: str
    beschreibung: str
    anleitung: str
    erfordert_investition: bool
    variablen: list[PresetVariableResponse]
    mappings: list[PresetMappingResponse]


class ApplyPresetRequest(BaseModel):
    preset_id: str = Field(..., min_length=1)
    anlage_id: int
    variablen: dict[str, str] = Field(default_factory=dict)
    investition_id: Optional[int] = None


class ApplyPresetResponse(BaseModel):
    preset_id: str
    erstellt: int
    mappings: list[dict]


# ─── Endpoints ───────────────────────────────────────────────────────

@router.get("/mqtt/gateway/presets", response_model=list[PresetResponse])
async def get_presets():
    """Alle verfügbaren Geräte-Presets."""
    presets = list_presets()
    return [
        PresetResponse(
            id=p.id,
            name=p.name,
            hersteller=p.hersteller,
            gruppe=p.gruppe,
            beschreibung=p.beschreibung,
            anleitung=p.anleitung,
            erfordert_investition=p.erfordert_investition,
            variablen=[
                PresetVariableResponse(
                    key=v.key, label=v.label,
                    placeholder=v.placeholder, hinweis=v.hinweis,
                ) for v in p.variablen
            ],
            mappings=[
                PresetMappingResponse(
                    topic_template=m.topic_template,
                    ziel_key=m.ziel_key,
                    beschreibung=m.beschreibung,
                    payload_typ=m.payload_typ,
                    json_pfad=m.json_pfad,
                    faktor=m.faktor,
                    invertieren=m.invertieren,
                ) for m in p.mappings
            ],
        )
        for p in presets
    ]


@router.post("/mqtt/gateway/presets/apply", response_model=ApplyPresetResponse)
async def apply_preset(req: ApplyPresetRequest, db: AsyncSession = Depends(get_db)):
    """Preset anwenden: Generiert Mappings und speichert sie in der DB."""
    try:
        mapping_dicts = generate_mappings(req.preset_id, req.anlage_id, req.variablen, req.investition_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    created = []
    for md in mapping_dicts:
        db_mapping = MqttGatewayMapping(
            anlage_id=md["anlage_id"],
            quell_topic=md["quell_topic"],
            ziel_key=md["ziel_key"],
            payload_typ=md["payload_typ"],
            json_pfad=md.get("json_pfad"),
            array_index=md.get("array_index"),
            faktor=md.get("faktor", 1.0),
            offset=md.get("offset", 0.0),
            invertieren=md.get("invertieren", False),
            aktiv=md.get("aktiv", True),
            beschreibung=md.get("beschreibung"),
            preset_id=md.get("preset_id"),
        )
        db.add(db_mapping)
        created.append(md)

    await db.commit()

    # Gateway hot-reload
    from backend.api.routes.mqtt_gateway import _reload_gateway
    reload_result = await _reload_gateway(db)
    logger.info("Preset '%s' angewendet: %d Mappings erstellt, reload=%s",
                req.preset_id, len(created), reload_result.get("reloaded"))

    return ApplyPresetResponse(
        preset_id=req.preset_id,
        erstellt=len(created),
        mappings=created,
    )
