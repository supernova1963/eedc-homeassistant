"""
MQTT Gateway Presets API — Geräte-Presets auflisten und anwenden.

Endpoints unter /api/live/mqtt/gateway/presets/...
"""

import logging
from datetime import datetime
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


class GrundRequest(BaseModel):
    """Sensorwechsel (Weg B): die Antwort auf eine fragepflichtige Änderung je Zählerschlüssel — ``fortsetzung`` oder
    ``loeschen``."""
    grund: str
    #: U2 Lauf b (F9): «Der neue Sensor zählt ab» je Schlüssel — gilt nur bei «bleiben» zwischen zwei HA-Sensoren mit
    #: Überlappung; ein Preset setzt MQTT-Quellen, eine Angabe hier lehnt die Route deshalb mit 422 ab.
    zaehlt_ab: Optional[datetime] = None


class ApplyPresetRequest(BaseModel):
    preset_id: str = Field(..., min_length=1)
    anlage_id: int
    variablen: dict[str, str] = Field(default_factory=dict)
    investition_id: Optional[int] = None
    #: Grund je Zählerschlüssel (``inv:<id>:<feld>`` / ``basis:<feld>``) — ohne ihn lehnt «Anwenden» eine fragepflichtige
    #: Änderung mit 422 ab; der Client fragt vorher über ``…/apply/pruefen``.
    gruende: dict[str, GrundRequest] = Field(default_factory=dict)


class ApplyPresetResponse(BaseModel):
    preset_id: str
    erstellt: int
    mappings: list[dict]
    #: P-433-2b K4 (K4-8): ersetzte aktive Gateway-Zeilen derselben `(anlage, ziel_key)`.
    ersetzt: int = 0
    #: Felder, deren Quelle auf «Gateway» gesetzt wurde, und die `ziel_key` ohne Feld der Fläche (Zeile ohne Quelle).
    quelle_gesetzt: int = 0
    ohne_feld: list[str] = Field(default_factory=list)
    #: Sensorwechsel mit Grund: je Korrektur der Hintergrund-Lauf (``lauf``, ``sensor_key``, ``tage_neu`` …).
    korrektur: list[dict] = Field(default_factory=list)


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


async def _wende_preset_an(db: AsyncSession, req: ApplyPresetRequest):
    """Die Änderung des Presets (in der Sitzung, ohne Commit) — dieselbe für «Anwenden» und «Prüfen» (Vorschau = Lauf).

    P-433-2b K4 (K4-8, D-K4-1): **ersetzt statt zu doppeln** — vorher aktive Zeilen derselben ``(anlage, ziel_key)``
    werden über den einen Löschweg (``entferne_gateway_zeile``, N-561) entfernt (``ersetzt``) — und setzt danach die
    Quelle jedes gemappten Feldes auf ``mqtt_gateway`` (``datenquellen.setze_gateway_quellen``, dieselbe Schreibform wie
    ``set_feld_quelle``). Returns: ``(anlage, vorher, mapping_dicts, neue, alte, gesetzt, ohne_feld)``.
    """
    from sqlalchemy import select
    from sqlalchemy.orm.attributes import flag_modified

    from backend.api.routes.datenquellen import setze_gateway_quellen
    from backend.api.routes.mqtt_gateway import entferne_gateway_zeile
    from backend.models.anlage import Anlage
    from backend.services.datenquellen_resolver import ziel_key_ohne_namen
    from backend.services.zuordnung_wechsel.verzeichnen import momentaufnahme

    try:
        mapping_dicts = generate_mappings(req.preset_id, req.anlage_id, req.variablen, req.investition_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    anlage = (await db.execute(select(Anlage).where(Anlage.id == req.anlage_id))).scalar_one_or_none()
    if anlage is None:
        raise HTTPException(status_code=404, detail="Anlage nicht gefunden")

    wirksam_vorher = await momentaufnahme(db, anlage)  # Sensorwechsel mit Grund: vor dem Ersetzen der Zeilen (W2)
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
    return anlage, wirksam_vorher, mapping_dicts, neue, alte, gesetzt, ohne_feld


def _gruende_zulaessig(req: ApplyPresetRequest) -> None:
    """Ein unbekannter Grund ist ein Fehler des Aufrufers (400) — wie an der Feld-Route (Bauplan §11 Nr. 54)."""
    from backend.services.zuordnung_wechsel import abfrage

    for g in req.gruende.values():
        if g.grund not in abfrage.GRUENDE:
            raise HTTPException(status_code=400, detail=f"Unbekannter Grund: {g.grund}")


def _zaehlt_ab(req: ApplyPresetRequest) -> Optional[dict[str, datetime]]:
    """«Der neue Sensor zählt ab» je Schlüssel (Preset je Schlüssel, U2 Lauf b) — nur die angegebenen."""
    werte = {k: g.zaehlt_ab for k, g in req.gruende.items() if g.zaehlt_ab is not None}
    return werte or None


async def _labels_der_schluessel(db: AsyncSession, anlage) -> dict[str, str]:
    """Anwender-Bezeichnung je Zählerschlüssel (über die Feld-Labels der Fläche)."""
    from backend.api.routes.datenquellen import _feld_labels
    from backend.services.snapshot.keys import _energy_field_id_to_sensor_key

    return {k: label for fid, label in (await _feld_labels(db, anlage)).items()
            if (k := _energy_field_id_to_sensor_key(fid)) is not None}


@router.post("/mqtt/gateway/presets/apply/pruefen")
async def pruefe_preset(req: ApplyPresetRequest, db: AsyncSession = Depends(get_db, scope="function")):
    """Prüft «Preset anwenden», **bevor** der Client sendet (Sensorwechsel mit Grund, Bauplan B-2; schreibt nichts).

    Derselbe Body wie ``…/apply``; die Route macht dieselbe Änderung, fragt ``zuordnung_wechsel/abfrage.pruefe`` und rollt
    zurück. Antwort: ``grund_erforderlich`` und je Schlüssel mit eigenen Werten, dessen wirksame Quelle wechselt, eine Zeile
    wie bei ``…/felder/{feld}/quelle/pruefen``.
    """
    from backend.services.zuordnung_wechsel import abfrage

    _gruende_zulaessig(req)
    try:
        anlage, vorher, *_ = await _wende_preset_an(db, req)
        try:
            fragen = await abfrage.pruefe(db, anlage, vorher, await abfrage.lade_wirksame_quellen(db, anlage),
                                          zaehlt_ab=_zaehlt_ab(req))
        except abfrage.GrundFehlt as e:
            raise HTTPException(status_code=422, detail=str(e))
        labels = await _labels_der_schluessel(db, anlage)
        felder = [abfrage.antwort(f, labels.get(f.sensor_key, f.sensor_key)) for f in fragen]
    finally:
        await db.rollback()
    return {"grund_erforderlich": any(z["grund_erforderlich"] for z in felder), "felder": felder}


@router.post("/mqtt/gateway/presets/apply", response_model=ApplyPresetResponse)
async def apply_preset(req: ApplyPresetRequest, db: AsyncSession = Depends(get_db, scope="function")):
    """Preset anwenden: Generiert Mappings und speichert sie in der DB (``_wende_preset_an``).

    Sensorwechsel mit Grund (Bauplan B-2, Sitzung 3b): eine fragepflichtige Änderung braucht ``gruende[schlüssel]`` —
    ohne ihn **422**; «bleiben» bzw. «löschen» wie an der Feld-Route (``zuordnung_wechsel/abfrage.vollziehe``).
    """
    from backend.api.routes.mqtt_gateway import _reload_gateway
    from backend.services.activity_service import log_activity
    from backend.services.zuordnung_wechsel import abfrage
    from backend.services.zuordnung_wechsel.korrektur import KorrekturNichtStartbar

    _gruende_zulaessig(req)
    anlage, wirksam_vorher, mapping_dicts, neue, alte, gesetzt, ohne_feld = await _wende_preset_an(db, req)
    labels = await _labels_der_schluessel(db, anlage)
    gruende = {k: g.grund for k, g in req.gruende.items()}
    try:
        vollzug = await abfrage.vollziehe(db, anlage, wirksam_vorher, gruende, labels=labels, zaehlt_ab=_zaehlt_ab(req))
    except (abfrage.GrundFehlt, KorrekturNichtStartbar) as e:
        raise HTTPException(status_code=422, detail=str(e))
    zusatz = abfrage.aktivitaet_text(vollzug, labels)
    if zusatz:
        await log_activity(kategorie="sensor_mapping", aktion=f"Preset angewendet: {req.preset_id}",
                           details=f"{anlage.anlagenname} · {zusatz}", anlage_id=req.anlage_id, db=db)
    await db.commit()
    await abfrage.nach_dem_commit(vollzug)

    reload_result = await _reload_gateway(db)
    logger.info("Preset '%s' angewendet: %d Mappings erstellt, %d ersetzt, Quelle an %d Feldern, reload=%s",
                req.preset_id, len(neue), len(alte), gesetzt, reload_result.get("reloaded"))

    return ApplyPresetResponse(
        preset_id=req.preset_id, erstellt=len(neue), mappings=mapping_dicts,
        ersetzt=len(alte), quelle_gesetzt=gesetzt, ohne_feld=ohne_feld, korrektur=vollzug.zusammenfassung(labels),
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
