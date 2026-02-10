"""
Home Assistant Import Routes

Ermöglicht den automatisierten Import von Monatsdaten aus Home Assistant.
Generiert YAML-Konfiguration für HA Template-Sensoren und Utility Meter.

v0.9.8: Sensor-Auswahl aus HA mit Vorschlägen basierend auf state_class: total_increasing
"""

import logging
from datetime import date
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_db
from backend.models.anlage import Anlage
from backend.models.investition import Investition, InvestitionTyp, InvestitionMonatsdaten
from backend.models.monatsdaten import Monatsdaten
from backend.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()


# =============================================================================
# Pydantic Schemas
# =============================================================================

class SensorFeld(BaseModel):
    """Ein erwartetes Feld für einen Investitionstyp."""
    key: str
    label: str
    unit: str
    required: bool = False
    hint: str | None = None
    # v0.9.9: Erweiterte Optionen
    optional: bool = False  # Kann "nicht erfassen" gewählt werden
    berechenbar: bool = False  # Kann aus anderen Sensoren berechnet werden
    berechnung_formel: str | None = None  # z.B. "evcc_solar_percent" für EVCC-Berechnung
    manuell_only: bool = False  # Nur manuelle Eingabe möglich (z.B. externe Kosten)


class InvestitionMitSensorFeldern(BaseModel):
    """Investition mit den erwarteten Sensor-Feldern."""
    id: int
    bezeichnung: str
    typ: str
    felder: list[SensorFeld]
    parameter: dict | None = None


class FeldMapping(BaseModel):
    """Mapping-Konfiguration für ein einzelnes Feld."""
    typ: str = Field(
        ...,
        description="Art des Mappings: 'sensor', 'berechnet', 'nicht_erfassen', 'manuell'"
    )
    sensor: str | None = Field(None, description="Sensor-ID bei typ='sensor'")
    # Für berechnete Felder (typ='berechnet')
    formel: str | None = Field(None, description="Formel-ID: 'evcc_solar_pv', 'evcc_solar_netz', 'verbrauch_aus_km'")
    quell_sensoren: dict[str, str] | None = Field(None, description="Quell-Sensoren für Berechnung")


class SensorMapping(BaseModel):
    """Zuordnung von HA-Sensoren zu Investitions-Feldern."""
    investition_id: int
    mappings: dict[str, str | FeldMapping] = Field(
        ...,
        description="Mapping von Feldname zu Sensor-ID oder FeldMapping-Objekt"
    )


class SensorMappingRequest(BaseModel):
    """Request zum Speichern der Sensor-Zuordnungen."""
    mappings: list[SensorMapping]


class MonatsdatenImportRequest(BaseModel):
    """Request für den Import von Monatsdaten aus HA."""
    jahr: int = Field(..., ge=2000, le=2100)
    monat: int = Field(..., ge=1, le=12)
    # Basis-Monatsdaten
    einspeisung_kwh: float = Field(..., ge=0)
    netzbezug_kwh: float = Field(..., ge=0)
    pv_erzeugung_kwh: float | None = Field(None, ge=0)
    # Optionale Wetterdaten
    globalstrahlung_kwh_m2: float | None = Field(None, ge=0)
    sonnenstunden: float | None = Field(None, ge=0)
    # Investitions-Daten (pro investition_id)
    investitionen: dict[str, dict] | None = Field(
        None,
        description="Daten pro Investition: {'1': {'km_gefahren': 1200, 'verbrauch_kwh': 216}}"
    )


class ImportResult(BaseModel):
    """Ergebnis eines Imports."""
    erfolg: bool
    monatsdaten_id: int | None = None
    investitionen_importiert: int = 0
    fehler: list[str] = []
    hinweise: list[str] = []


class HASensor(BaseModel):
    """Ein Sensor aus Home Assistant."""
    entity_id: str
    friendly_name: str | None = None
    state_class: str | None = None
    unit_of_measurement: str | None = None
    device_class: str | None = None


class HASensorsResponse(BaseModel):
    """Antwort mit HA-Sensoren."""
    sensoren: list[HASensor]
    ha_url: str | None = None
    connected: bool = False
    fehler: str | None = None


class BasisSensorMapping(BaseModel):
    """Zuordnung der Basis-Sensoren (Einspeisung, Netzbezug, PV)."""
    einspeisung: str | None = None
    netzbezug: str | None = None
    pv_erzeugung: str | None = None


class AnlageSensorMappingRequest(BaseModel):
    """Request zum Speichern aller Sensor-Zuordnungen einer Anlage."""
    basis: BasisSensorMapping
    investitionen: list[SensorMapping]


# =============================================================================
# Feld-Definitionen pro Investitionstyp
# =============================================================================

def get_felder_fuer_typ(typ: str, parameter: dict | None = None) -> list[SensorFeld]:
    """
    Gibt die erwarteten Felder für einen Investitionstyp zurück.

    v0.9.9: Erweitert um optionale Felder, berechenbare Felder und manuelle Eingaben.
    """

    if typ == "e-auto":
        felder = [
            SensorFeld(
                key="km_gefahren",
                label="Gefahrene km",
                unit="km",
                hint="Tacho/Odometer Sensor"
            ),
            SensorFeld(
                key="verbrauch_kwh",
                label="Verbrauch",
                unit="kWh",
                optional=True,
                berechenbar=True,
                berechnung_formel="verbrauch_aus_ladung_km",
                hint="Optional: Wird aus Ladung/km berechnet wenn leer"
            ),
            SensorFeld(
                key="ladung_pv_kwh",
                label="Ladung aus PV",
                unit="kWh",
                berechenbar=True,
                berechnung_formel="evcc_solar_pv",
                hint="EVCC: Gesamt × Solar%"
            ),
            SensorFeld(
                key="ladung_netz_kwh",
                label="Ladung aus Netz",
                unit="kWh",
                berechenbar=True,
                berechnung_formel="evcc_solar_netz",
                hint="EVCC: Gesamt × (100 - Solar%)"
            ),
            SensorFeld(
                key="ladung_extern_kwh",
                label="Externe Ladung",
                unit="kWh",
                optional=True,
                manuell_only=True,
                hint="Öffentliche Ladesäulen - nur manuelle Eingabe"
            ),
            SensorFeld(
                key="ladung_extern_euro",
                label="Externe Kosten",
                unit="€",
                optional=True,
                manuell_only=True,
                hint="Kosten öffentliches Laden - nur manuelle Eingabe"
            ),
        ]
        # V2H wenn aktiviert
        if parameter and (parameter.get("nutzt_v2h") or parameter.get("v2h_faehig")):
            felder.append(SensorFeld(
                key="v2h_entladung_kwh",
                label="V2H Entladung",
                unit="kWh",
                optional=True
            ))
        return felder

    elif typ == "speicher":
        felder = [
            SensorFeld(key="ladung_kwh", label="Ladung", unit="kWh", required=True),
            SensorFeld(key="entladung_kwh", label="Entladung", unit="kWh", required=True),
        ]
        # Arbitrage wenn aktiviert
        if parameter and parameter.get("arbitrage_faehig"):
            felder.extend([
                SensorFeld(
                    key="speicher_ladung_netz_kwh",
                    label="Netzladung",
                    unit="kWh",
                    optional=True,
                    hint="Arbitrage - Ladung aus Netz"
                ),
                SensorFeld(
                    key="speicher_ladepreis_cent",
                    label="Ø Ladepreis",
                    unit="ct/kWh",
                    optional=True,
                    manuell_only=True,
                    hint="Arbitrage - nur manuelle Eingabe"
                ),
            ])
        return felder

    elif typ == "wallbox":
        return [
            SensorFeld(key="ladung_kwh", label="Heimladung", unit="kWh", required=True),
            SensorFeld(
                key="ladevorgaenge",
                label="Ladevorgänge",
                unit="Anzahl",
                optional=True,
                hint="EVCC: sensor.evcc_charging_sessions (Counter)"
            ),
        ]

    elif typ == "waermepumpe":
        return [
            SensorFeld(key="stromverbrauch_kwh", label="Stromverbrauch", unit="kWh", required=True),
            SensorFeld(
                key="heizenergie_kwh",
                label="Heizenergie",
                unit="kWh",
                optional=True,
                hint="Falls von WP geliefert"
            ),
            SensorFeld(
                key="warmwasser_kwh",
                label="Warmwasser",
                unit="kWh",
                optional=True,
                hint="Falls getrennt erfasst"
            ),
        ]

    elif typ == "pv-module":
        return [
            SensorFeld(key="pv_erzeugung_kwh", label="Erzeugung", unit="kWh", required=True),
        ]

    elif typ == "balkonkraftwerk":
        felder = [
            SensorFeld(key="pv_erzeugung_kwh", label="Erzeugung", unit="kWh", required=True),
        ]
        # Speicher wenn vorhanden
        if parameter and parameter.get("hat_speicher"):
            felder.extend([
                SensorFeld(key="speicher_ladung_kwh", label="Speicher Ladung", unit="kWh", optional=True),
                SensorFeld(key="speicher_entladung_kwh", label="Speicher Entladung", unit="kWh", optional=True),
            ])
        return felder

    elif typ == "sonstiges":
        kategorie = parameter.get("kategorie", "erzeuger") if parameter else "erzeuger"
        if kategorie == "erzeuger":
            return [
                SensorFeld(key="erzeugung_kwh", label="Erzeugung", unit="kWh", required=True),
            ]
        elif kategorie == "verbraucher":
            return [
                SensorFeld(key="verbrauch_kwh", label="Verbrauch", unit="kWh", required=True),
            ]
        elif kategorie == "speicher":
            return [
                SensorFeld(key="ladung_kwh", label="Ladung", unit="kWh"),
                SensorFeld(key="entladung_kwh", label="Entladung", unit="kWh"),
            ]

    return []


# =============================================================================
# Berechnungsformeln
# =============================================================================

BERECHNUNGS_FORMELN = {
    "evcc_solar_pv": {
        "beschreibung": "EVCC: Ladung PV = Gesamt-Ladung × Solar-Anteil%",
        "quell_sensoren": ["evcc_total_charged", "evcc_solar_percentage"],
        "template": "{{ (states('{evcc_total_charged}') | float(0)) * (states('{evcc_solar_percentage}') | float(0)) / 100 }}",
    },
    "evcc_solar_netz": {
        "beschreibung": "EVCC: Ladung Netz = Gesamt-Ladung × (100 - Solar-Anteil%)",
        "quell_sensoren": ["evcc_total_charged", "evcc_solar_percentage"],
        "template": "{{ (states('{evcc_total_charged}') | float(0)) * (100 - (states('{evcc_solar_percentage}') | float(0))) / 100 }}",
    },
    "verbrauch_aus_ladung_km": {
        "beschreibung": "Verbrauch = (Ladung PV + Ladung Netz + Extern) / km × 100",
        "quell_sensoren": ["ladung_pv", "ladung_netz", "ladung_extern", "km_gefahren"],
        "template": "{{ ((states('{ladung_pv}') | float(0)) + (states('{ladung_netz}') | float(0)) + (states('{ladung_extern}') | float(0))) / (states('{km_gefahren}') | float(1)) * 100 }}",
        "hinweis": "Ergebnis in kWh/100km"
    },
}


# =============================================================================
# HA-Sensor Keywords für Vorschläge
# =============================================================================

SENSOR_KEYWORDS = {
    # Basis-Sensoren
    "einspeisung": ["grid_export", "einspeisung", "feed_in", "export", "einspeisen"],
    "netzbezug": ["grid_import", "netzbezug", "grid_consumption", "import", "bezug", "grid_power_in"],
    "pv_erzeugung": ["pv_energy", "solar_energy", "pv_erzeugung", "solar_production", "pv_power", "solar_yield"],
    # Speicher
    "ladung_kwh": ["battery_charge", "batterie_ladung", "battery_in", "speicher_ladung", "charge_energy"],
    "entladung_kwh": ["battery_discharge", "batterie_entladung", "battery_out", "speicher_entladung", "discharge_energy"],
    # E-Auto
    "km_gefahren": ["odometer", "km", "mileage", "distance", "kilometer"],
    "verbrauch_kwh": ["car_consumption", "ev_consumption", "car_energy", "fahrzeug_verbrauch"],
    "ladung_pv_kwh": ["car_pv_charge", "ev_solar", "solar_charge"],
    "ladung_netz_kwh": ["car_grid_charge", "ev_grid", "grid_charge"],
    # Wärmepumpe
    "stromverbrauch_kwh": ["heat_pump_energy", "wp_strom", "heatpump_consumption", "waermepumpe_strom"],
    "heizenergie_kwh": ["heating_energy", "heizung", "heating_output"],
    "warmwasser_kwh": ["dhw_energy", "warmwasser", "hot_water"],
    # Wallbox
    "wallbox_ladung": ["wallbox_energy", "charger_energy", "evse_energy", "ladestation"],
}


def _match_sensor_score(entity_id: str, friendly_name: str | None, keywords: list[str]) -> int:
    """Berechnet einen Match-Score für einen Sensor basierend auf Keywords."""
    score = 0
    search_text = f"{entity_id} {friendly_name or ''}".lower()

    for keyword in keywords:
        if keyword.lower() in search_text:
            score += 10
            # Exakter Match im entity_id ist besser
            if keyword.lower() in entity_id.lower():
                score += 5

    return score


# =============================================================================
# Endpoints
# =============================================================================

@router.get("/ha-sensors", response_model=HASensorsResponse)
async def get_ha_sensors(
    filter_total_increasing: bool = Query(True, description="Nur Sensoren mit state_class: total_increasing"),
    filter_energy: bool = Query(True, description="Nur Energie-Sensoren (kWh, Wh, km)"),
    include_percentage: bool = Query(False, description="Auch Prozent-Sensoren einschließen (für EVCC Solar%)"),
    include_counter: bool = Query(False, description="Auch Counter-Sensoren einschließen (für Ladevorgänge)"),
):
    """
    Ruft verfügbare Sensoren aus Home Assistant ab.

    Nutzt die HA REST API über den Supervisor oder direkte URL.
    Filtert standardmäßig nach state_class: total_increasing für Utility Meter.

    v0.9.9: Erweiterte Filter für EVCC-Kompatibilität (Prozent, Counter).
    """
    sensoren: list[HASensor] = []
    ha_url = None
    fehler = None

    # HA API URLs versuchen (Supervisor > Local > Config)
    ha_urls = [
        "http://supervisor/core/api",  # HA Supervisor (Add-on)
        "http://homeassistant.local:8123/api",  # mDNS
        "http://localhost:8123/api",  # Lokal
    ]

    # Falls HA URL in Settings konfiguriert
    if hasattr(settings, 'ha_url') and settings.ha_url:
        ha_urls.insert(0, f"{settings.ha_url}/api")

    # HA Token aus Umgebung oder Settings
    import os
    ha_token = os.environ.get("SUPERVISOR_TOKEN") or os.environ.get("HA_TOKEN")
    if hasattr(settings, 'ha_token') and settings.ha_token:
        ha_token = settings.ha_token

    if not ha_token:
        return HASensorsResponse(
            sensoren=[],
            connected=False,
            fehler="Kein HA-Token konfiguriert. Bitte SUPERVISOR_TOKEN oder HA_TOKEN setzen."
        )

    headers = {
        "Authorization": f"Bearer {ha_token}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        for url in ha_urls:
            try:
                response = await client.get(f"{url}/states", headers=headers)
                if response.status_code == 200:
                    ha_url = url.replace("/api", "")
                    states = response.json()

                    for state in states:
                        entity_id = state.get("entity_id", "")

                        # Nur Sensoren
                        if not entity_id.startswith("sensor."):
                            continue

                        attributes = state.get("attributes", {})
                        state_class = attributes.get("state_class")
                        unit = attributes.get("unit_of_measurement", "")
                        device_class = attributes.get("device_class")
                        friendly_name = attributes.get("friendly_name")

                        # Filter: state_class
                        valid_state_class = False
                        if filter_total_increasing:
                            if state_class == "total_increasing":
                                valid_state_class = True
                            elif include_counter and state_class == "total":
                                # Counter wie charging_sessions haben oft state_class: total
                                valid_state_class = True
                            elif include_percentage and state_class == "measurement":
                                # Prozent-Sensoren haben oft state_class: measurement
                                valid_state_class = True
                        else:
                            valid_state_class = True

                        if not valid_state_class:
                            continue

                        # Filter: Einheiten
                        if filter_energy:
                            energy_units = ["kWh", "Wh", "MWh", "km", "mi"]
                            percentage_units = ["%"]
                            counter_units = ["", None]  # Counter haben oft keine Einheit

                            valid_unit = unit in energy_units
                            if include_percentage and unit in percentage_units:
                                valid_unit = True
                            if include_counter and (unit in counter_units or "session" in entity_id.lower()):
                                valid_unit = True

                            if not valid_unit:
                                continue

                        sensoren.append(HASensor(
                            entity_id=entity_id,
                            friendly_name=friendly_name,
                            state_class=state_class,
                            unit_of_measurement=unit,
                            device_class=device_class,
                        ))

                    # Sortieren nach entity_id
                    sensoren.sort(key=lambda s: s.entity_id)
                    break

            except httpx.RequestError as e:
                logger.debug(f"HA API nicht erreichbar unter {url}: {e}")
                continue
            except Exception as e:
                logger.warning(f"Fehler beim Abrufen der HA-Sensoren von {url}: {e}")
                continue
        else:
            fehler = "Home Assistant nicht erreichbar. Bitte prüfen Sie die Verbindung."

    return HASensorsResponse(
        sensoren=sensoren,
        ha_url=ha_url,
        connected=len(sensoren) > 0,
        fehler=fehler if not sensoren else None,
    )


@router.get("/ha-sensors/all")
async def get_all_ha_sensors():
    """
    Ruft ALLE Sensoren aus HA ab (ohne Filter).

    Nützlich für die Auswahl von Spezial-Sensoren wie EVCC Solar%.
    """
    return await get_ha_sensors(
        filter_total_increasing=False,
        filter_energy=False,
        include_percentage=True,
        include_counter=True,
    )


@router.get("/berechnungs-formeln")
async def get_berechnungs_formeln():
    """
    Gibt alle verfügbaren Berechnungsformeln zurück.

    Diese können für berechnete Felder verwendet werden.
    """
    return {
        "formeln": BERECHNUNGS_FORMELN,
        "hinweis": "Quell-Sensoren müssen als Template-Sensoren oder direkt konfiguriert werden"
    }


@router.get("/ha-sensors/suggestions/{anlage_id}")
async def get_sensor_suggestions(
    anlage_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Gibt Sensor-Vorschläge für alle Felder einer Anlage zurück.

    Basiert auf Keyword-Matching der verfügbaren HA-Sensoren.
    """
    # HA-Sensoren abrufen
    ha_response = await get_ha_sensors(filter_total_increasing=True, filter_energy=True)

    if not ha_response.connected:
        return {
            "connected": False,
            "fehler": ha_response.fehler,
            "basis": {},
            "investitionen": {},
        }

    # Investitionen laden
    result = await db.execute(
        select(Investition)
        .where(Investition.anlage_id == anlage_id)
        .where(Investition.aktiv == True)
    )
    investitionen = result.scalars().all()

    # Basis-Vorschläge
    basis_suggestions = {}
    for key in ["einspeisung", "netzbezug", "pv_erzeugung"]:
        keywords = SENSOR_KEYWORDS.get(key, [])
        best_match = None
        best_score = 0

        for sensor in ha_response.sensoren:
            score = _match_sensor_score(sensor.entity_id, sensor.friendly_name, keywords)
            if score > best_score:
                best_score = score
                best_match = sensor.entity_id

        basis_suggestions[key] = {
            "vorschlag": best_match,
            "score": best_score,
            "alle_sensoren": [s.entity_id for s in ha_response.sensoren],
        }

    # Investitions-Vorschläge
    inv_suggestions = {}
    for inv in investitionen:
        inv_suggestions[str(inv.id)] = {
            "bezeichnung": inv.bezeichnung,
            "typ": inv.typ,
            "felder": {},
        }

        fields = get_felder_fuer_typ(inv.typ, inv.parameter)
        inv_name_lower = inv.bezeichnung.lower()

        for feld in fields:
            keywords = SENSOR_KEYWORDS.get(feld.key, [])
            # Investitions-Name als zusätzliches Keyword
            keywords = keywords + [inv_name_lower]

            best_match = None
            best_score = 0

            for sensor in ha_response.sensoren:
                score = _match_sensor_score(sensor.entity_id, sensor.friendly_name, keywords)
                # Bonus wenn Investitions-Name im Sensor vorkommt
                if inv_name_lower in sensor.entity_id.lower() or inv_name_lower in (sensor.friendly_name or "").lower():
                    score += 20

                if score > best_score:
                    best_score = score
                    best_match = sensor.entity_id

            inv_suggestions[str(inv.id)]["felder"][feld.key] = {
                "vorschlag": best_match,
                "score": best_score,
            }

    return {
        "connected": True,
        "ha_url": ha_response.ha_url,
        "sensor_count": len(ha_response.sensoren),
        "basis": basis_suggestions,
        "investitionen": inv_suggestions,
    }


@router.post("/sensor-mapping-complete/{anlage_id}")
async def save_complete_sensor_mapping(
    anlage_id: int,
    request: AnlageSensorMappingRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Speichert alle Sensor-Zuordnungen für eine Anlage (Basis + Investitionen).

    Die Mappings werden gespeichert in:
    - Anlage.ha_sensor_mapping (Basis-Sensoren)
    - Investition.parameter['ha_sensors'] (pro Investition)
    """
    # Anlage laden und Basis-Mapping speichern
    result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    anlage = result.scalar_one_or_none()

    if not anlage:
        raise HTTPException(status_code=404, detail=f"Anlage {anlage_id} nicht gefunden")

    # Basis-Mapping in Anlage speichern (neues Feld oder JSON in existing field)
    # Wir nutzen ein JSON-Feld oder erweitern das Modell
    # Für jetzt: Speichern in einem neuen Attribut das wir später hinzufügen
    # Alternativ: In der ersten Investition oder separater Tabelle

    # Investitions-Mappings speichern
    from sqlalchemy.orm.attributes import flag_modified

    for mapping in request.investitionen:
        result = await db.execute(
            select(Investition)
            .where(Investition.id == mapping.investition_id)
            .where(Investition.anlage_id == anlage_id)
        )
        inv = result.scalar_one_or_none()

        if not inv:
            raise HTTPException(
                status_code=404,
                detail=f"Investition {mapping.investition_id} nicht gefunden"
            )

        # JSON-Feld aktualisieren
        if inv.parameter is None:
            inv.parameter = {}

        # Neues Dict erstellen, um SQLAlchemy dirty-tracking auszulösen
        new_parameter = dict(inv.parameter)
        new_parameter["ha_sensors"] = mapping.mappings
        inv.parameter = new_parameter

        # Explizit als geändert markieren (für JSON-Felder nötig)
        flag_modified(inv, "parameter")

    await db.commit()

    return {
        "status": "ok",
        "message": f"Sensor-Mappings für Anlage {anlage_id} gespeichert",
        "basis_mapping": request.basis.model_dump(),
        "investitionen_count": len(request.investitionen),
    }


@router.get("/investitionen/{anlage_id}", response_model=list[InvestitionMitSensorFeldern])
async def get_investitionen_mit_feldern(
    anlage_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Gibt alle aktiven Investitionen einer Anlage mit den erwarteten Sensor-Feldern zurück.

    Diese Felder werden benötigt für:
    - Sensor-Zuordnung im Frontend
    - YAML-Generierung für Utility Meter
    """
    # Anlage prüfen
    result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail=f"Anlage {anlage_id} nicht gefunden")

    # Aktive Investitionen laden
    result = await db.execute(
        select(Investition)
        .where(Investition.anlage_id == anlage_id)
        .where(Investition.aktiv == True)
        .order_by(Investition.typ, Investition.bezeichnung)
    )
    investitionen = result.scalars().all()

    return [
        InvestitionMitSensorFeldern(
            id=inv.id,
            bezeichnung=inv.bezeichnung,
            typ=inv.typ,
            felder=get_felder_fuer_typ(inv.typ, inv.parameter),
            parameter=inv.parameter,
        )
        for inv in investitionen
    ]


@router.post("/sensor-mapping/{anlage_id}")
async def save_sensor_mapping(
    anlage_id: int,
    request: SensorMappingRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Speichert die Sensor-Zuordnungen für Investitionen.

    Die Mappings werden in Investition.parameter['ha_sensors'] gespeichert.
    """
    for mapping in request.mappings:
        result = await db.execute(
            select(Investition)
            .where(Investition.id == mapping.investition_id)
            .where(Investition.anlage_id == anlage_id)
        )
        inv = result.scalar_one_or_none()

        if not inv:
            raise HTTPException(
                status_code=404,
                detail=f"Investition {mapping.investition_id} nicht gefunden"
            )

        # Sensor-Mapping in Parameter speichern
        if inv.parameter is None:
            inv.parameter = {}
        inv.parameter["ha_sensors"] = mapping.mappings

    await db.commit()

    return {"status": "ok", "message": f"{len(request.mappings)} Mappings gespeichert"}


@router.get("/yaml/{anlage_id}")
async def generate_yaml(
    anlage_id: int,
    einspeisung_sensor: str = Query(None, description="Sensor-ID für Einspeisung"),
    netzbezug_sensor: str = Query(None, description="Sensor-ID für Netzbezug"),
    pv_sensor: str = Query(None, description="Sensor-ID für PV-Erzeugung"),
    db: AsyncSession = Depends(get_db)
):
    """
    Generiert YAML-Konfiguration für Home Assistant.

    v0.9.8: Nutzt die übergebenen oder gespeicherten Sensor-IDs statt Platzhalter.

    Beinhaltet:
    - Utility Meter für monatliche Aggregation
    - REST Command für EEDC Import
    - Automation für monatlichen Import
    """
    from backend.services.ha_yaml_generator import generate_ha_yaml

    # Anlage laden
    result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    anlage = result.scalar_one_or_none()

    if not anlage:
        raise HTTPException(status_code=404, detail=f"Anlage {anlage_id} nicht gefunden")

    # Investitionen laden
    result = await db.execute(
        select(Investition)
        .where(Investition.anlage_id == anlage_id)
        .where(Investition.aktiv == True)
    )
    investitionen = list(result.scalars().all())

    # Basis-Sensor-Mapping zusammenstellen
    basis_sensors = {
        "einspeisung": einspeisung_sensor,
        "netzbezug": netzbezug_sensor,
        "pv_erzeugung": pv_sensor,
    }

    yaml_content = generate_ha_yaml(anlage, investitionen, basis_sensors)

    # Prüfen ob noch Platzhalter vorhanden sind
    has_placeholders = "sensor.DEIN_" in yaml_content or "# TODO:" in yaml_content

    hinweise = []
    if has_placeholders:
        hinweise.append("⚠️ Es sind noch Platzhalter vorhanden - bitte Sensoren zuordnen")
    hinweise.extend([
        "Diese YAML-Konfiguration in configuration.yaml einfügen",
        "Home Assistant danach neu starten",
        "Utility Meter werden monatlich zurückgesetzt",
        "Automation sendet Daten am 1. jeden Monats um 00:05",
    ])

    return {
        "anlage_id": anlage_id,
        "anlage_name": anlage.anlagenname,
        "yaml": yaml_content,
        "has_placeholders": has_placeholders,
        "hinweise": hinweise,
    }


@router.post("/from-ha/{anlage_id}", response_model=ImportResult)
async def import_from_ha(
    anlage_id: int,
    request: MonatsdatenImportRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Importiert Monatsdaten aus Home Assistant.

    Dieser Endpoint wird von einer HA-Automation aufgerufen.
    Unterstützt sowohl Basis-Monatsdaten als auch Investitions-Monatsdaten.
    """
    fehler: list[str] = []
    hinweise: list[str] = []
    investitionen_count = 0

    # Anlage prüfen
    result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    anlage = result.scalar_one_or_none()

    if not anlage:
        return ImportResult(erfolg=False, fehler=[f"Anlage {anlage_id} nicht gefunden"])

    # Prüfen ob Monatsdaten bereits existieren
    result = await db.execute(
        select(Monatsdaten)
        .where(Monatsdaten.anlage_id == anlage_id)
        .where(Monatsdaten.jahr == request.jahr)
        .where(Monatsdaten.monat == request.monat)
    )
    existing = result.scalar_one_or_none()

    if existing:
        # Update
        existing.einspeisung_kwh = request.einspeisung_kwh
        existing.netzbezug_kwh = request.netzbezug_kwh
        if request.pv_erzeugung_kwh is not None:
            existing.pv_erzeugung_kwh = request.pv_erzeugung_kwh
        if request.globalstrahlung_kwh_m2 is not None:
            existing.globalstrahlung_kwh_m2 = request.globalstrahlung_kwh_m2
        if request.sonnenstunden is not None:
            existing.sonnenstunden = request.sonnenstunden
        existing.datenquelle = "ha_import"

        # Berechnete Felder aktualisieren
        pv = existing.pv_erzeugung_kwh or 0
        einsp = existing.einspeisung_kwh or 0
        batt_ladung = existing.batterie_ladung_kwh or 0
        batt_entladung = existing.batterie_entladung_kwh or 0

        existing.direktverbrauch_kwh = max(0, pv - einsp - batt_ladung)
        existing.eigenverbrauch_kwh = existing.direktverbrauch_kwh + batt_entladung
        existing.gesamtverbrauch_kwh = existing.eigenverbrauch_kwh + request.netzbezug_kwh

        monatsdaten_id = existing.id
        hinweise.append(f"Monatsdaten {request.monat}/{request.jahr} aktualisiert")
    else:
        # Neu erstellen
        pv = request.pv_erzeugung_kwh or 0
        direktverbrauch = max(0, pv - request.einspeisung_kwh)

        md = Monatsdaten(
            anlage_id=anlage_id,
            jahr=request.jahr,
            monat=request.monat,
            einspeisung_kwh=request.einspeisung_kwh,
            netzbezug_kwh=request.netzbezug_kwh,
            pv_erzeugung_kwh=request.pv_erzeugung_kwh,
            direktverbrauch_kwh=direktverbrauch,
            eigenverbrauch_kwh=direktverbrauch,
            gesamtverbrauch_kwh=direktverbrauch + request.netzbezug_kwh,
            globalstrahlung_kwh_m2=request.globalstrahlung_kwh_m2,
            sonnenstunden=request.sonnenstunden,
            datenquelle="ha_import",
        )
        db.add(md)
        await db.flush()
        monatsdaten_id = md.id
        hinweise.append(f"Monatsdaten {request.monat}/{request.jahr} erstellt")

    # Investitions-Monatsdaten importieren
    if request.investitionen:
        for inv_id_str, daten in request.investitionen.items():
            try:
                inv_id = int(inv_id_str)

                # Investition prüfen
                result = await db.execute(
                    select(Investition)
                    .where(Investition.id == inv_id)
                    .where(Investition.anlage_id == anlage_id)
                )
                inv = result.scalar_one_or_none()

                if not inv:
                    fehler.append(f"Investition {inv_id} nicht gefunden")
                    continue

                # Existierende InvestitionMonatsdaten prüfen
                result = await db.execute(
                    select(InvestitionMonatsdaten)
                    .where(InvestitionMonatsdaten.investition_id == inv_id)
                    .where(InvestitionMonatsdaten.jahr == request.jahr)
                    .where(InvestitionMonatsdaten.monat == request.monat)
                )
                existing_imd = result.scalar_one_or_none()

                if existing_imd:
                    # Merge mit existierenden Daten
                    existing_imd.verbrauch_daten = {**existing_imd.verbrauch_daten, **daten}
                else:
                    # Neu erstellen
                    imd = InvestitionMonatsdaten(
                        investition_id=inv_id,
                        jahr=request.jahr,
                        monat=request.monat,
                        verbrauch_daten=daten,
                    )
                    db.add(imd)

                investitionen_count += 1

            except ValueError as e:
                fehler.append(f"Ungültige Investitions-ID: {inv_id_str}")
            except Exception as e:
                fehler.append(f"Fehler bei Investition {inv_id_str}: {str(e)}")

    await db.commit()

    logger.info(
        f"HA-Import für Anlage {anlage_id}: {request.monat}/{request.jahr} - "
        f"{investitionen_count} Investitionen importiert"
    )

    return ImportResult(
        erfolg=len(fehler) == 0,
        monatsdaten_id=monatsdaten_id,
        investitionen_importiert=investitionen_count,
        fehler=fehler,
        hinweise=hinweise,
    )
