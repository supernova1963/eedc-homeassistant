"""Themen-Kacheln (4.2.0, Bauplan TH-E1 §1.2) — die sechs Routen der Themen je Gerät, am Präfix der Datenquellen.

Ein **Thema** gehört zu einem Gerät mit Block «Überblick» (`utils/investition_filter.py:UEBERBLICK_TYPEN`) und trägt
**Einträge** — je eine frei gewählte HA-Entität bzw. ein MQTT-Topic. Die Quelle eines Eintrags setzt die bestehende
Quellen-Route (`datenquellen.set_feld_quelle`, Feld-ID ``inv_thema_<inv>_<e>``); hier stehen nur Anlegen,
Umbenennen, Verschieben und Entfernen. Store und Regeln: `services/themen_store.py`.

Eigenes Modul statt `datenquellen.py`, damit die Fläche (1 900 Zeilen) nicht weiter wächst; dasselbe Präfix
(``/api/datenquellen``, `main.py`). Die fünf Routen an einem Thema tragen das Gerät als Pflicht-Query-Parameter
``investition_id`` (Kennungen sind nur je Gerät eindeutig; ohne ⇒ 422, Thema nicht an diesem Gerät ⇒ 404). Jede Schreibroute schreibt `log_activity` in ihrer Sitzung (N-532) und antwortet
mit der Themen-Gruppe des Geräts in der Form von ``GET /felder`` (`_themen_gruppe`).
"""

from __future__ import annotations

import copy
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_db
from backend.api.routes.datenquellen import (
    QUELLEN_HA,
    QUELLEN_KEY,
    _ha_states_detail,
    _quellen_map,
    _themen_gruppe,
)
from backend.models.anlage import Anlage
from backend.models.investition import Investition
from backend.services import themen_store as store
from backend.services.activity_service import log_activity
from backend.services.mqtt_topic_registry import build_expected_topics
from backend.utils.investition_filter import UEBERBLICK_TYPEN

router = APIRouter()

_KATEGORIE = "sensor_mapping"


class ThemaAnlegenRequest(BaseModel):
    investition_id: int
    name: Optional[str] = None


class ThemaAendernRequest(BaseModel):
    name: Optional[str] = None
    position: Optional[int] = None


class EintragAnlegenRequest(BaseModel):
    label: Optional[str] = None


class EintragAendernRequest(BaseModel):
    label: Optional[str] = None
    position: Optional[int] = None


# ── Laden und Antworten ───────────────────────────────────────────────────────

async def _lade_anlage(db: AsyncSession, anlage_id: int) -> Anlage:
    anlage = (await db.execute(select(Anlage).where(Anlage.id == anlage_id))).scalar_one_or_none()
    if anlage is None:
        raise HTTPException(status_code=404, detail="Anlage nicht gefunden")
    return anlage


async def _lade_geraet(db: AsyncSession, anlage: Anlage, investition_id: int) -> Investition:
    """Das Gerät der Anlage — 404 ohne, 400 für einen Typ ohne Block «Überblick»."""
    inv = (await db.execute(
        select(Investition).where(Investition.id == investition_id, Investition.anlage_id == anlage.id)
    )).scalar_one_or_none()
    if inv is None:
        raise HTTPException(status_code=404, detail="Gerät nicht gefunden")
    if inv.typ not in UEBERBLICK_TYPEN:
        raise HTTPException(
            status_code=400, detail="Themen gibt es nur an Wärmepumpe, Wallbox und E-Auto (Geräte mit «Überblick»).",
        )
    return inv


async def _geraet_mit_thema(db: AsyncSession, anlage: Anlage, investition_id: int, t_id: str) -> Investition:
    """Das Gerät ``investition_id`` — und das Thema ``t_id`` muss **an diesem Gerät** stehen, sonst 404.

    Die Kennungen ``t<n>``/``e<n>`` zählen je Gerät ab 1 (`themen_store.naechste_id`); zwei Geräte tragen also beide
    ``t1``. Darum nennt jede Schreibroute das Gerät als Pflicht-Query-Parameter (Nachlauf 4.2.0, H2), statt das Gerät
    aus der Kennung zu erraten."""
    inv = await _lade_geraet(db, anlage, investition_id)
    if not any(t["id"] == t_id for t in store.lade_themen(anlage.sensor_mapping, inv.id)["liste"]):
        raise HTTPException(status_code=404, detail="Thema nicht gefunden")
    return inv


async def _antwort(db: AsyncSession, anlage: Anlage, inv: Investition) -> dict:
    """Die Themen-Gruppe des Geräts wie in ``GET /felder`` — mit Werten (HA-Detail, Inbound-Cache)."""
    from backend.models.mqtt_gateway_mapping import MqttGatewayMapping
    from backend.services.mqtt_inbound_service import get_mqtt_inbound_service

    quellen = _quellen_map(anlage)
    ha_entities = {
        v["entity_id"] for fid, v in quellen.items()
        if (store.eintrag_von_feld_id(fid) or (None,))[0] == inv.id and isinstance(v, dict)
        and v.get("quelle") in QUELLEN_HA and v.get("entity_id")
    }
    ha_detail = await _ha_states_detail(db, ha_entities)
    gw_rows = (await db.execute(
        select(MqttGatewayMapping).where(MqttGatewayMapping.anlage_id == anlage.id)
    )).scalars().all()
    topics = {
        "_".join(str(x) for x in e["match_key"]): e["topic"]
        for e in await build_expected_topics(db, anlage, investitionen=[inv]) if e.get("abschnitt") == "themen"
    }
    svc = get_mqtt_inbound_service()
    themen = _themen_gruppe(
        anlage, inv, quellen, ha_detail, svc.cache if svc else None, {m.id: m.quell_topic for m in gw_rows}, topics,
    )
    return {"investition_id": inv.id, "themen": themen}


async def _speichern(db: AsyncSession, anlage: Anlage, mapping: dict, aktion: str, details: str, inv: Investition):
    """Mapping zurückschreiben (`flag_modified`), protokollieren (N-532), committen, Themen-Gruppe zurück."""
    from sqlalchemy.orm.attributes import flag_modified

    anlage.sensor_mapping = mapping
    flag_modified(anlage, "sensor_mapping")
    await log_activity(
        kategorie=_KATEGORIE, aktion=aktion, details=f"{anlage.anlagenname} · {inv.bezeichnung}: {details}",
        details_json={"investition_id": inv.id}, anlage_id=anlage.id, db=db,
    )
    await db.commit()
    return await _antwort(db, anlage, inv)


async def _quellen_raeumen(db: AsyncSession, mapping: dict, feld_ids: list[str]) -> None:
    """Die Quellen entfernter Einträge aus ``quellen`` (in-place, wie das Aufräumen beim Löschen eines Geräts,
    `investitionen/crud.py::_raeume_feld_ablagen`) — samt ihrer Gateway-Zeile und Reload über denselben Weg
    (`_entferne_gateway_zeilen`, N-561). Eine Themen-Quelle hat keinen Teil in der klassischen Struktur."""
    from backend.api.routes.investitionen.crud import _entferne_gateway_zeilen

    quellen = mapping.get(QUELLEN_KEY)
    if not isinstance(quellen, dict):
        return
    gateway_ids = []
    for fid in feld_ids:
        eintrag = quellen.pop(fid, None)
        if isinstance(eintrag, dict) and eintrag.get("mapping_id") is not None:
            gateway_ids.append(eintrag["mapping_id"])
    await _entferne_gateway_zeilen(db, gateway_ids)


def _schreib(fn, *args):
    """Store-Aufruf mit den Fehlern der Route: Eingabe ⇒ 400, unbekannt ⇒ 404."""
    try:
        return fn(*args)
    except store.ThemenFehler as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except store.ThemaNichtGefunden as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


# ── Routen ────────────────────────────────────────────────────────────────────

@router.post("/{anlage_id}/themen")
async def thema_anlegen(anlage_id: int, body: ThemaAnlegenRequest, db: AsyncSession = Depends(get_db, scope="function")):
    """Legt ein Thema am Gerät an (ohne Namen «Thema n»)."""
    anlage = await _lade_anlage(db, anlage_id)
    inv = await _lade_geraet(db, anlage, body.investition_id)
    mapping = copy.deepcopy(anlage.sensor_mapping or {})
    thema = _schreib(store.thema_anlegen, mapping, inv.id, body.name)
    return await _speichern(db, anlage, mapping, "Thema angelegt", f"Thema «{thema['name']}» angelegt", inv)


@router.patch("/{anlage_id}/themen/{t_id}")
async def thema_aendern(
    anlage_id: int, t_id: str, investition_id: int, body: ThemaAendernRequest,
    db: AsyncSession = Depends(get_db, scope="function"),
):
    """Benennt ein Thema um und/oder verschiebt es (``position`` 0-basiert, geklemmt)."""
    anlage = await _lade_anlage(db, anlage_id)
    inv = await _geraet_mit_thema(db, anlage, investition_id, t_id)
    mapping = copy.deepcopy(anlage.sensor_mapping or {})
    alt = next(t["name"] for t in store.lade_themen(mapping, inv.id)["liste"] if t["id"] == t_id)
    texte = []
    if body.name is not None:
        neu = _schreib(store.thema_umbenennen, mapping, inv.id, t_id, body.name)["name"]
        texte.append(f"Thema «{alt}» umbenannt in «{neu}»")
    if body.position is not None:
        thema = _schreib(store.thema_verschieben, mapping, inv.id, t_id, body.position)
        texte.append(f"Thema «{thema['name']}» verschoben")
    return await _speichern(db, anlage, mapping, "Thema geändert", " · ".join(texte) or f"Thema «{alt}»", inv)


@router.delete("/{anlage_id}/themen/{t_id}")
async def thema_entfernen(
    anlage_id: int, t_id: str, investition_id: int, db: AsyncSession = Depends(get_db, scope="function"),
):
    """Entfernt ein Thema samt Einträgen — je Eintrag die Quelle und die Gateway-Zeile."""
    anlage = await _lade_anlage(db, anlage_id)
    inv = await _geraet_mit_thema(db, anlage, investition_id, t_id)
    mapping = copy.deepcopy(anlage.sensor_mapping or {})
    thema, feld_ids = _schreib(store.thema_entfernen, mapping, inv.id, t_id)
    await _quellen_raeumen(db, mapping, feld_ids)
    return await _speichern(db, anlage, mapping, "Thema entfernt", f"Thema «{thema['name']}» entfernt", inv)


@router.post("/{anlage_id}/themen/{t_id}/eintraege")
async def eintrag_anlegen(
    anlage_id: int, t_id: str, investition_id: int, body: EintragAnlegenRequest,
    db: AsyncSession = Depends(get_db, scope="function"),
):
    """Legt einen Eintrag ohne Quelle an (ohne Label «Eintrag n»)."""
    anlage = await _lade_anlage(db, anlage_id)
    inv = await _geraet_mit_thema(db, anlage, investition_id, t_id)
    mapping = copy.deepcopy(anlage.sensor_mapping or {})
    eintrag = _schreib(store.eintrag_anlegen, mapping, inv.id, t_id, body.label)
    return await _speichern(db, anlage, mapping, "Themen-Eintrag angelegt", f"Eintrag «{eintrag['label']}» angelegt", inv)


@router.patch("/{anlage_id}/themen/{t_id}/eintraege/{e_id}")
async def eintrag_aendern(
    anlage_id: int, t_id: str, e_id: str, investition_id: int, body: EintragAendernRequest,
    db: AsyncSession = Depends(get_db, scope="function"),
):
    """Benennt einen Eintrag um und/oder verschiebt ihn im Thema."""
    anlage = await _lade_anlage(db, anlage_id)
    inv = await _geraet_mit_thema(db, anlage, investition_id, t_id)
    mapping = copy.deepcopy(anlage.sensor_mapping or {})
    treffer = store.finde_eintrag(mapping, inv.id, e_id)
    if treffer is None or treffer[0]["id"] != t_id:
        raise HTTPException(status_code=404, detail="Eintrag nicht gefunden")
    alt = treffer[1]["label"]
    texte = []
    if body.label is not None:
        neu = _schreib(store.eintrag_umbenennen, mapping, inv.id, t_id, e_id, body.label)["label"]
        texte.append(f"Eintrag «{alt}» umbenannt in «{neu}»")
    if body.position is not None:
        eintrag = _schreib(store.eintrag_verschieben, mapping, inv.id, t_id, e_id, body.position)
        texte.append(f"Eintrag «{eintrag['label']}» verschoben")
    return await _speichern(db, anlage, mapping, "Themen-Eintrag geändert", " · ".join(texte) or f"Eintrag «{alt}»", inv)


@router.delete("/{anlage_id}/themen/{t_id}/eintraege/{e_id}")
async def eintrag_entfernen(
    anlage_id: int, t_id: str, e_id: str, investition_id: int, db: AsyncSession = Depends(get_db, scope="function"),
):
    """Entfernt einen Eintrag samt Quelle und Gateway-Zeile."""
    anlage = await _lade_anlage(db, anlage_id)
    inv = await _geraet_mit_thema(db, anlage, investition_id, t_id)
    mapping = copy.deepcopy(anlage.sensor_mapping or {})
    eintrag, feld_id = _schreib(store.eintrag_entfernen, mapping, inv.id, t_id, e_id)
    await _quellen_raeumen(db, mapping, [feld_id])
    return await _speichern(db, anlage, mapping, "Themen-Eintrag entfernt", f"Eintrag «{eintrag['label']}» entfernt", inv)
