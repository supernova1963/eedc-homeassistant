"""
Sensor-Mapping API Routes — **nur noch die HA-Energy-Vorschläge (#197).**

Von den ursprünglich sechs Endpunkten ist einer übrig: ``GET /{anlage_id}/suggest``,
der einzige mit lebendem Client (Setup-Wizard, ``IntegrationStep.tsx``).

**Die fünf anderen sind am 2026-08-13 stillgelegt** (Fund N-241): Lesen, Speichern,
Löschen, Status und die Sensor-Liste des Alt-Wizards. Ihre Oberfläche ist mit dem
IA-V4-Flip gefallen; die Zuordnung läuft seither über ``routes/datenquellen.py``.

Der Grund ist nicht Aufräumen, sondern eine **zweite Schreibtür**: ``POST /{anlage_id}``
schrieb weiter auf ``Anlage.sensor_mapping``, ohne den Historie-Hinweis auszulösen, den
``datenquellen.py`` seit Konzept #192 B zeigt („deine Zuordnung ist neu, die gespeicherte
Historie nicht"). Wer die Alt-Route noch traf — Alt-Client aus dem Browser-Cache, eigenes
Script —, änderte seine Zuordnung stumm. Eine zweite Kopie des Hinweises hätte die Klasse
verdoppelt statt sie aufzulösen.

Wer die alten Wege sucht: ``/api/datenquellen/{id}/felder`` (lesen · speichern),
``/api/datenquellen/{id}/ha/sensoren`` (Sensor-Liste).
"""

import logging
from enum import Enum
from typing import Optional, Any

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.exceptions import not_found
from backend.core.database import get_session
from backend.core.field_definitions import get_felder_fuer_investition
from backend.models.anlage import Anlage
from backend.services.ha_energy_service import (
    DeviceConsumptionCandidate,
    get_ha_energy_suggestions,
)
from backend.models.investition import Investition

logger = logging.getLogger(__name__)


# =============================================================================
# Enums und Schemas
# =============================================================================

class StrategieTyp(str, Enum):
    """Verfügbare Schätzungsstrategien für Feldwerte.

    Datenchecker-Achse A1 (v3.39.0): auf `sensor` + `keine` reduziert. Die
    früheren Werte `kwp_verteilung`/`ev_quote`/`cop_berechnung`/`manuell` waren
    Dead Code — nur `sensor` wird in den Aggregatoren ausgewertet (Vergleich
    `== "sensor"` als String), der Rest lieferte nie Daten und war eine
    Anwender-Falle. Bestandswerte werden beim Startup auf `keine` migriert
    (`_migrate_sensor_mapping_strategien_clear`, Hard-Precondition vor der
    Enum-Reduktion, sonst scheitert das Pydantic-Parsen jeder gespeicherten
    `FeldMapping`-JSON mit altem Strategie-Wert).
    """
    SENSOR = "sensor"               # Direkter HA-Sensor
    KEINE = "keine"                 # Kein Sensor (manuell im Wizard / bewusst leer)


class FeldMapping(BaseModel):
    """Mapping für ein einzelnes Feld."""
    strategie: StrategieTyp
    sensor_id: Optional[str] = None  # Bei strategie=sensor
    parameter: Optional[dict[str, Any]] = None  # Zusätzliche Parameter

    class Config:
        use_enum_values = True


class BasisMapping(BaseModel):
    """Mapping für die Basis-Sensoren (Zähler)."""
    einspeisung: Optional[FeldMapping] = None
    netzbezug: Optional[FeldMapping] = None
    pv_gesamt: Optional[FeldMapping] = None  # Optional, für kWp-Verteilung
    strompreis: Optional[FeldMapping] = None  # Ø Strompreis bei dyn. Tarif (direktes Lesen, kein MWD)
    live: Optional[dict[str, Optional[str]]] = None  # Live-Sensoren: {einspeisung_w: entity_id, netzbezug_w: entity_id}
    live_invert: Optional[dict[str, bool]] = None  # Vorzeichen invertieren: {einspeisung_w: true}


class InvestitionFelder(BaseModel):
    """Felder-Mapping für eine Investition."""
    felder: dict[str, FeldMapping]
    live: Optional[dict[str, Optional[str]]] = None  # Live-Sensoren: {leistung_w: entity_id, soc: entity_id}
    live_invert: Optional[dict[str, bool]] = None  # Vorzeichen invertieren: {leistung_w: true}


class SolcastConfigRequest(BaseModel):
    """Optionale Solcast-Konfiguration."""
    modus: str  # "ha_auto" oder "api"
    api_key: Optional[str] = None
    resource_ids: Optional[list] = None
    tier: Optional[str] = "free"


class SensorMappingRequest(BaseModel):
    """Request zum Speichern des Sensor-Mappings."""
    basis: BasisMapping
    investitionen: dict[str, InvestitionFelder] = Field(
        default_factory=dict,
        description="Key = Investition-ID als String"
    )
    solcast_config: Optional[SolcastConfigRequest] = None


class InvestitionInfo(BaseModel):
    """Informationen zu einer Investition für den Wizard."""
    id: int
    typ: str
    bezeichnung: str
    erwartete_felder: list[str]
    kwp: Optional[float] = None  # Für PV-Module
    cop: Optional[float] = None  # Für Wärmepumpen
    parameter: Optional[dict] = None  # Investitions-Parameter (für Frontend-Logik)


class SensorMappingResponse(BaseModel):
    """Response mit aktuellem Mapping und verfügbaren Investitionen."""
    anlage_id: int
    anlage_name: str
    mapping: Optional[dict[str, Any]] = None
    investitionen: list[InvestitionInfo] = []
    gesamt_kwp: float = 0.0


class HASensorInfo(BaseModel):
    """Home Assistant Sensor für Dropdown-Auswahl."""
    entity_id: str
    friendly_name: Optional[str] = None
    unit: Optional[str] = None
    device_class: Optional[str] = None
    state: Optional[str] = None
    # True wenn der Sensor `state_class` gesetzt hat — Voraussetzung dafür,
    # dass HA ihn in die Long-Term-Statistics-Tabelle aufnimmt. Sensoren
    # ohne state_class fehlen dort und liefern für kWh-Monatsabschluss /
    # Vollbackfill keine Daten (Counter-Felder via Snapshot-Service sind
    # davon nicht betroffen).
    has_statistics: bool = False


class SetupResult(BaseModel):
    """Ergebnis des MQTT-Setup."""
    success: bool
    message: str
    created_sensors: int = 0
    errors: list[str] = []


# Erwartete Felder werden aus field_definitions.INVESTITION_FELDER abgeleitet —
# kein hardcodierter Block mehr. Neue Felder nur in field_definitions eintragen.


def _is_int_state(state_value: Optional[str]) -> bool:
    """True wenn der State-String als Ganzzahl parsebar ist (Counter-Heuristik)."""
    if state_value is None or state_value in ("unknown", "unavailable", ""):
        return False
    try:
        int(state_value)
        return True
    except (ValueError, TypeError):
        return False


# =============================================================================
# Router
# =============================================================================

router = APIRouter()


async def _get_anlage(anlage_id: int, session: AsyncSession) -> Anlage:
    """Hilfsfunktion zum Laden einer Anlage."""
    result = await session.execute(
        select(Anlage).where(Anlage.id == anlage_id)
    )
    anlage = result.scalar_one_or_none()
    if not anlage:
        raise not_found("Anlage", anlage_id)
    return anlage



# =============================================================================
# HA-Energy Auto-Vorbefüllung (#197 Olli0103)
# =============================================================================

# Mapping device_consumption-Typ → Default-Investitions-Feld.
# Wenn das Feld in get_felder_fuer_investition(...) für die konkrete Investition
# nicht existiert (z.B. Wärmepumpe mit getrennte_strommessung=true), wird der
# Vorschlag stillschweigend verworfen — der User pflegt im Wizard manuell.
_DEFAULT_FELD_FUER_TYP: dict[str, str] = {
    "wallbox": "ladung_kwh",
    "waermepumpe": "stromverbrauch_kwh",
    "e-auto": "verbrauch_kwh",
}


class HAEnergyInvestitionSuggestion(BaseModel):
    """Vorgeschlagenes Sensor-Mapping für eine konkrete Investition."""
    inv_id: int
    typ: str
    bezeichnung: str
    feld: str
    sensor_id: str
    source_name: Optional[str] = None  # HA-Energy-Anzeigename (für Banner)


class HAEnergySuggestResponse(BaseModel):
    """Antwort des /suggest-Endpoints."""
    available: bool
    reason_unavailable: Optional[str] = None
    # Basis-Felder als {feld_name: entity_id} — Frontend setzt direkt FeldMapping
    # mit strategie="sensor" + sensor_id.
    basis: dict[str, str] = {}
    # Pro Investition (key=inv_id als String) ein Vorschlag {feld_name: entity_id}
    investitionen: dict[str, dict[str, str]] = {}
    # Roh-Liste aller device_consumption-Einträge — auch die ohne Heuristik-Match,
    # damit der User im Banner sieht, was HA-Energy noch kennt.
    device_consumption_raw: list[DeviceConsumptionCandidate] = []
    # Aggregierte Per-Investition-Liste für die Banner-Anzeige.
    investition_matches: list[HAEnergyInvestitionSuggestion] = []


@router.get("/{anlage_id}/suggest", response_model=HAEnergySuggestResponse)
async def get_ha_energy_suggest(anlage_id: int):
    """
    Liefert Auto-Vorbefüllungs-Vorschläge aus der HA-Energiekonfiguration.

    Add-on-only: liest `/config/.storage/core.energy`. Auf Standalone-Setups
    wird `available=False` zurückgegeben — Frontend zeigt dann keinen Banner.
    """
    suggestions = get_ha_energy_suggestions()

    # D2 (2026-07-18): Standalone mit konfigurierter Remote-HA → Energy-Prefs
    # über den einmaligen WebSocket-Call holen (LL-Token); sonst wie bisher.
    if not suggestions.available and suggestions.reason_unavailable == "standalone":
        from backend.services.ha_connection import resolve_ha_connection
        from backend.services.ha_energy_service import get_ha_energy_suggestions_remote

        async with get_session() as session:
            api_url, token, kind = await resolve_ha_connection(session)
        if api_url and token and kind == "ha_connector":
            # api_url endet auf /api — die WS-Funktion braucht die Basis-URL.
            basis_url = api_url[:-4] if api_url.endswith("/api") else api_url
            suggestions = await get_ha_energy_suggestions_remote(basis_url, token)

    if not suggestions.available:
        return HAEnergySuggestResponse(
            available=False,
            reason_unavailable=suggestions.reason_unavailable,
        )

    async with get_session() as session:
        await _get_anlage(anlage_id, session)

        inv_result = await session.execute(
            select(Investition)
            .where(Investition.anlage_id == anlage_id)
            .order_by(Investition.id)
        )
        investitionen = list(inv_result.scalars().all())

    basis_map: dict[str, str] = {src.feld: src.entity_id for src in suggestions.energy_sources}
    inv_map: dict[str, dict[str, str]] = {}
    matches: list[HAEnergyInvestitionSuggestion] = []

    # 1. Batterie → Speicher-Investition (erste aktive Speicher-Investition wählen)
    if suggestions.battery and (suggestions.battery.ladung_entity or suggestions.battery.entladung_entity):
        speicher = next((i for i in investitionen if i.typ == "speicher"), None)
        if speicher:
            felder_keys = {f["feld"] for f in get_felder_fuer_investition(speicher.typ, speicher.parameter)}
            entry: dict[str, str] = {}
            if suggestions.battery.ladung_entity and "ladung_kwh" in felder_keys:
                entry["ladung_kwh"] = suggestions.battery.ladung_entity
                matches.append(HAEnergyInvestitionSuggestion(
                    inv_id=speicher.id,
                    typ=speicher.typ,
                    bezeichnung=speicher.bezeichnung,
                    feld="ladung_kwh",
                    sensor_id=suggestions.battery.ladung_entity,
                ))
            if suggestions.battery.entladung_entity and "entladung_kwh" in felder_keys:
                entry["entladung_kwh"] = suggestions.battery.entladung_entity
                matches.append(HAEnergyInvestitionSuggestion(
                    inv_id=speicher.id,
                    typ=speicher.typ,
                    bezeichnung=speicher.bezeichnung,
                    feld="entladung_kwh",
                    sensor_id=suggestions.battery.entladung_entity,
                ))
            if entry:
                inv_map[str(speicher.id)] = entry

    # 2. device_consumption → Wallbox / Wärmepumpe / E-Auto (jeweils erste aktive)
    used_inv_ids: set[int] = set()  # eine HA-Quelle nicht doppelt zuordnen
    for cand in suggestions.device_consumption:
        if not cand.suggested_inv_typ:
            continue
        target_typ = cand.suggested_inv_typ
        feld = _DEFAULT_FELD_FUER_TYP.get(target_typ)
        if not feld:
            continue
        inv = next(
            (i for i in investitionen if i.typ == target_typ and i.id not in used_inv_ids),
            None,
        )
        if not inv:
            continue
        felder_keys = {f["feld"] for f in get_felder_fuer_investition(inv.typ, inv.parameter)}
        if feld not in felder_keys:
            # z.B. Wärmepumpe mit getrennte_strommessung — `stromverbrauch_kwh`
            # existiert dann nicht. User muss manuell mappen.
            continue
        used_inv_ids.add(inv.id)
        inv_map.setdefault(str(inv.id), {})[feld] = cand.entity_id
        matches.append(HAEnergyInvestitionSuggestion(
            inv_id=inv.id,
            typ=inv.typ,
            bezeichnung=inv.bezeichnung,
            feld=feld,
            sensor_id=cand.entity_id,
            source_name=cand.name,
        ))

    return HAEnergySuggestResponse(
        available=True,
        basis=basis_map,
        investitionen=inv_map,
        device_consumption_raw=suggestions.device_consumption,
        investition_matches=matches,
    )


