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
    vorgabe: str = ""


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
    #: P-433-2b K4: Investitionstypen, an deren Gerät die Datenquellen-Fläche den Knopf zeigt (`MqttPreset.typen`).
    typen: list[str] = Field(default_factory=list)
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
    #: P-433-2b K4 (K4-8): ersetzte aktive Gateway-Zeilen derselben `(anlage, ziel_key)`.
    ersetzt: int = 0
    #: Felder, deren Quelle auf «Gateway» gesetzt wurde, und die `ziel_key` ohne Feld der Fläche (Zeile ohne Quelle).
    quelle_gesetzt: int = 0
    ohne_feld: list[str] = Field(default_factory=list)


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
            typen=list(p.typen),
            variablen=[
                PresetVariableResponse(
                    key=v.key, label=v.label,
                    placeholder=v.placeholder, hinweis=v.hinweis, vorgabe=v.vorgabe,
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
async def apply_preset(req: ApplyPresetRequest, db: AsyncSession = Depends(get_db, scope="function")):
    """Preset anwenden: Generiert Mappings und speichert sie in der DB.

    P-433-2b K4 (K4-8, D-K4-1): **ersetzt statt zu doppeln** — vorher aktive Zeilen derselben ``(anlage, ziel_key)``
    werden über den einen Löschweg (``entferne_gateway_zeile``, N-561) entfernt (``ersetzt``) — und setzt danach die
    Quelle jedes gemappten Feldes auf ``mqtt_gateway`` (``datenquellen.setze_gateway_quellen``, dieselbe Schreibform wie
    ``set_feld_quelle``). Legt nur an; Zeilen editieren bleibt der Gateway-Picker.
    """
    from sqlalchemy import select
    from sqlalchemy.orm.attributes import flag_modified

    from backend.api.routes.datenquellen import setze_gateway_quellen
    from backend.api.routes.mqtt_gateway import _reload_gateway, entferne_gateway_zeile
    from backend.models.anlage import Anlage
    from backend.services.datenquellen_resolver import ziel_key_ohne_namen

    try:
        mapping_dicts = generate_mappings(req.preset_id, req.anlage_id, req.variablen, req.investition_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    anlage = (await db.execute(select(Anlage).where(Anlage.id == req.anlage_id))).scalar_one_or_none()
    if anlage is None:
        raise HTTPException(status_code=404, detail="Anlage nicht gefunden")

    # Dasselbe Feld in beiden Schreibweisen (Picker mit Namensteil, Preset in ID-Form) ist dieselbe Zeile.
    ziele = {ziel_key_ohne_namen(md["ziel_key"]) for md in mapping_dicts}
    alte = [mid for mid, zk in (await db.execute(select(MqttGatewayMapping.id, MqttGatewayMapping.ziel_key).where(
        MqttGatewayMapping.anlage_id == req.anlage_id, MqttGatewayMapping.aktiv.is_(True),
    ))).all() if ziel_key_ohne_namen(zk) in ziele]
    for mapping_id in alte:
        await entferne_gateway_zeile(db, mapping_id)

    neue = [_gateway_zeile(md) for md in mapping_dicts]
    db.add_all(neue)
    await db.flush()
    gesetzt, ohne_feld = await setze_gateway_quellen(db, anlage, neue)
    flag_modified(anlage, "sensor_mapping")
    await db.commit()

    reload_result = await _reload_gateway(db)
    logger.info("Preset '%s' angewendet: %d Mappings erstellt, %d ersetzt, Quelle an %d Feldern, reload=%s",
                req.preset_id, len(neue), len(alte), gesetzt, reload_result.get("reloaded"))

    return ApplyPresetResponse(
        preset_id=req.preset_id, erstellt=len(neue), mappings=mapping_dicts,
        ersetzt=len(alte), quelle_gesetzt=gesetzt, ohne_feld=ohne_feld,
    )


def _gateway_zeile(md: dict) -> MqttGatewayMapping:
    return MqttGatewayMapping(
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
