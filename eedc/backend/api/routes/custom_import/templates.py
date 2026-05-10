"""
Custom-Import — Templates-Slice.

GET    /templates           — Liste gespeicherter Mapping-Templates
POST   /templates/{name}    — Template speichern/aktualisieren
DELETE /templates/{name}    — Template löschen
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from backend.api.deps import get_db
from backend.models.settings import Settings

from ._shared import SETTINGS_KEY, MappingConfig

router = APIRouter()


# ─── Models ──────────────────────────────────────────────────────────────────

class TemplateInfo(BaseModel):
    name: str
    mapping: MappingConfig


class TemplateListResponse(BaseModel):
    templates: list[TemplateInfo]


# ─── Endpoints ────────────────────────────────────────────────────────────────


@router.get("/templates", response_model=TemplateListResponse)
async def get_templates(db: AsyncSession = Depends(get_db)):
    """Gespeicherte Mapping-Templates abrufen."""
    result = await db.execute(select(Settings).where(Settings.key == SETTINGS_KEY))
    setting = result.scalar_one_or_none()

    templates = []
    if setting and setting.value:
        for name, mapping_data in setting.value.items():
            try:
                config = MappingConfig(**mapping_data)
                templates.append(TemplateInfo(name=name, mapping=config))
            except Exception:
                pass

    return TemplateListResponse(templates=templates)


@router.post("/templates/{name}")
async def save_template(
    name: str,
    mapping: MappingConfig,
    db: AsyncSession = Depends(get_db),
):
    """Mapping-Template speichern."""
    if not name.strip():
        raise HTTPException(400, "Template-Name darf nicht leer sein.")

    result = await db.execute(select(Settings).where(Settings.key == SETTINGS_KEY))
    setting = result.scalar_one_or_none()

    if setting:
        templates = dict(setting.value) if setting.value else {}
    else:
        setting = Settings(key=SETTINGS_KEY, value={})
        db.add(setting)
        templates = {}

    templates[name.strip()] = mapping.model_dump()
    setting.value = templates

    flag_modified(setting, "value")
    await db.flush()

    return {"erfolg": True, "message": f"Template '{name}' gespeichert."}


@router.delete("/templates/{name}")
async def delete_template(
    name: str,
    db: AsyncSession = Depends(get_db),
):
    """Mapping-Template löschen."""
    result = await db.execute(select(Settings).where(Settings.key == SETTINGS_KEY))
    setting = result.scalar_one_or_none()

    if not setting or not setting.value or name not in setting.value:
        raise HTTPException(404, f"Template '{name}' nicht gefunden.")

    templates = dict(setting.value)
    del templates[name]
    setting.value = templates

    flag_modified(setting, "value")
    await db.flush()

    return {"erfolg": True, "message": f"Template '{name}' gelöscht."}
