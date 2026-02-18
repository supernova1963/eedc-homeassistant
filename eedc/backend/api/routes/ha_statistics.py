"""
HA Statistics API Routes

Endpoints für den Zugriff auf Home Assistant Langzeitstatistiken.

Ermöglicht:
- Monatswerte für einen bestimmten Monat abrufen
- Alle verfügbaren Monate ermitteln
- Bulk-Import aller historischen Monatswerte
- MQTT-Startwerte initialisieren
"""

from datetime import date
from typing import Optional, Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified
from pydantic import BaseModel

from backend.api.deps import get_db
from backend.models.anlage import Anlage
from backend.models.monatsdaten import Monatsdaten
from backend.models.investition import Investition, InvestitionMonatsdaten
from backend.services.ha_statistics_service import (
    get_ha_statistics_service,
    MonatswertResponse,
    AlleMonateResponse,
    SensorMonatswert,
)

router = APIRouter()


# =============================================================================
# Response Models
# =============================================================================

class MappedMonatswert(BaseModel):
    """Monatswert mit EEDC-Feld-Zuordnung."""
    feld: str
    feld_label: str
    sensor_id: str
    start_wert: float
    end_wert: float
    differenz: float
    einheit: str = "kWh"


class AnlagenMonatswertResponse(BaseModel):
    """Monatswerte für eine Anlage mit Feld-Zuordnung."""
    anlage_id: int
    anlage_name: str
    jahr: int
    monat: int
    monat_name: str
    basis: list[MappedMonatswert]
    investitionen: dict[str, list[MappedMonatswert]]  # investition_id -> felder


class VerfuegbareMonate(BaseModel):
    """Verfügbare Monate für eine Anlage."""
    anlage_id: int
    anlage_name: str
    erstes_datum: date
    letztes_datum: date
    anzahl_monate: int
    monate: list[dict]  # [{"jahr": 2024, "monat": 10, "monat_name": "Oktober"}, ...]


class StatusResponse(BaseModel):
    """Status der HA-Statistics-Integration."""
    verfuegbar: bool
    db_pfad: Optional[str]
    hinweis: str


# =============================================================================
# Feld-Labels für bessere Lesbarkeit
# =============================================================================

FELD_LABELS = {
    # Basis
    "einspeisung": "Einspeisung",
    "netzbezug": "Netzbezug",
    "pv_gesamt": "PV Erzeugung Gesamt",
    # PV-Module
    "pv_erzeugung_kwh": "PV Erzeugung",
    # Speicher
    "ladung_kwh": "Ladung",
    "entladung_kwh": "Entladung",
    "ladung_netz_kwh": "Ladung aus Netz",
    # E-Auto
    "ladung_pv_kwh": "Ladung PV",
    "km_gefahren": "Kilometer",
    "v2h_entladung_kwh": "V2H Entladung",
    # Wärmepumpe
    "stromverbrauch_kwh": "Stromverbrauch",
    "heizenergie_kwh": "Heizenergie",
    "warmwasser_kwh": "Warmwasser",
}


# =============================================================================
# Helper Functions
# =============================================================================

async def get_anlage_with_mapping(db: AsyncSession, anlage_id: int) -> Anlage:
    """Holt Anlage und prüft ob sensor_mapping vorhanden."""
    result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    anlage = result.scalar_one_or_none()

    if not anlage:
        raise HTTPException(status_code=404, detail=f"Anlage {anlage_id} nicht gefunden")

    if not anlage.sensor_mapping:
        raise HTTPException(
            status_code=400,
            detail="Keine Sensor-Zuordnung konfiguriert. Bitte zuerst Sensoren zuordnen."
        )

    return anlage


def extract_sensor_ids_from_mapping(sensor_mapping: dict) -> list[str]:
    """Extrahiert alle sensor_ids aus dem Mapping."""
    sensor_ids = []

    # Basis-Sensoren
    basis = sensor_mapping.get("basis", {})
    for feld, config in basis.items():
        if config and config.get("strategie") == "sensor" and config.get("sensor_id"):
            sensor_ids.append(config["sensor_id"])

    # Investitions-Sensoren
    investitionen = sensor_mapping.get("investitionen", {})
    for inv_id, inv_config in investitionen.items():
        felder = inv_config.get("felder", {})
        for feld, config in felder.items():
            if config and config.get("strategie") == "sensor" and config.get("sensor_id"):
                sensor_ids.append(config["sensor_id"])

    return sensor_ids


def map_sensor_values_to_fields(
    sensor_mapping: dict,
    sensoren: list[SensorMonatswert]
) -> tuple[list[MappedMonatswert], dict[str, list[MappedMonatswert]]]:
    """
    Ordnet Sensorwerte den EEDC-Feldern zu.

    Returns:
        Tuple von (basis_felder, investitions_felder)
    """
    # Sensor-Werte als Dict für schnellen Zugriff
    sensor_values = {s.sensor_id: s for s in sensoren}

    basis_felder: list[MappedMonatswert] = []
    inv_felder: dict[str, list[MappedMonatswert]] = {}

    # Basis-Felder
    basis = sensor_mapping.get("basis", {})
    for feld, config in basis.items():
        if config and config.get("strategie") == "sensor":
            sensor_id = config.get("sensor_id")
            if sensor_id and sensor_id in sensor_values:
                sv = sensor_values[sensor_id]
                basis_felder.append(MappedMonatswert(
                    feld=feld,
                    feld_label=FELD_LABELS.get(feld, feld),
                    sensor_id=sensor_id,
                    start_wert=sv.start_wert,
                    end_wert=sv.end_wert,
                    differenz=sv.differenz,
                    einheit=sv.einheit
                ))

    # Investitions-Felder
    investitionen = sensor_mapping.get("investitionen", {})
    for inv_id, inv_config in investitionen.items():
        felder = inv_config.get("felder", {})
        inv_felder[inv_id] = []

        for feld, config in felder.items():
            if config and config.get("strategie") == "sensor":
                sensor_id = config.get("sensor_id")
                if sensor_id and sensor_id in sensor_values:
                    sv = sensor_values[sensor_id]
                    inv_felder[inv_id].append(MappedMonatswert(
                        feld=feld,
                        feld_label=FELD_LABELS.get(feld, feld),
                        sensor_id=sensor_id,
                        start_wert=sv.start_wert,
                        end_wert=sv.end_wert,
                        differenz=sv.differenz,
                        einheit=sv.einheit
                    ))

    return basis_felder, inv_felder


# =============================================================================
# Endpoints
# =============================================================================

@router.get("/status", response_model=StatusResponse)
async def get_ha_statistics_status():
    """
    Prüft ob HA-Statistik-Abfrage verfügbar ist.

    Returns:
        Status der Integration
    """
    service = get_ha_statistics_service()

    if service.is_available:
        return StatusResponse(
            verfuegbar=True,
            db_pfad=str(service.db_path),
            hinweis="HA-Datenbank verfügbar. Statistik-Abfragen möglich."
        )
    else:
        return StatusResponse(
            verfuegbar=False,
            db_pfad=None,
            hinweis="HA-Datenbank nicht gefunden. Nur im HA-Addon verfügbar."
        )


@router.get("/monatswerte/{anlage_id}/{jahr}/{monat}", response_model=AnlagenMonatswertResponse)
async def get_monatswerte(
    anlage_id: int,
    jahr: int,
    monat: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Holt Monatswerte für einen bestimmten Monat aus HA-Statistiken.

    Args:
        anlage_id: ID der Anlage
        jahr: Jahr (z.B. 2024)
        monat: Monat (1-12)

    Returns:
        Monatswerte für alle gemappten Sensoren
    """
    if monat < 1 or monat > 12:
        raise HTTPException(status_code=400, detail="Monat muss zwischen 1 und 12 liegen")

    service = get_ha_statistics_service()
    if not service.is_available:
        raise HTTPException(
            status_code=503,
            detail="HA-Datenbank nicht verfügbar. Diese Funktion ist nur im HA-Addon nutzbar."
        )

    anlage = await get_anlage_with_mapping(db, anlage_id)
    sensor_ids = extract_sensor_ids_from_mapping(anlage.sensor_mapping)

    if not sensor_ids:
        raise HTTPException(
            status_code=400,
            detail="Keine Sensor-Zuordnungen mit Strategie 'sensor' gefunden."
        )

    # Werte aus HA-DB holen
    try:
        response = service.get_monatswerte(sensor_ids, jahr, monat)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fehler bei DB-Abfrage: {e}")

    # Auf EEDC-Felder mappen
    basis_felder, inv_felder = map_sensor_values_to_fields(
        anlage.sensor_mapping,
        response.sensoren
    )

    return AnlagenMonatswertResponse(
        anlage_id=anlage.id,
        anlage_name=anlage.anlagenname,
        jahr=jahr,
        monat=monat,
        monat_name=response.monat_name,
        basis=basis_felder,
        investitionen=inv_felder
    )


@router.get("/verfuegbare-monate/{anlage_id}", response_model=VerfuegbareMonate)
async def get_verfuegbare_monate(
    anlage_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Ermittelt alle Monate mit verfügbaren HA-Statistik-Daten.

    Args:
        anlage_id: ID der Anlage

    Returns:
        Liste aller Monate mit Daten
    """
    service = get_ha_statistics_service()
    if not service.is_available:
        raise HTTPException(
            status_code=503,
            detail="HA-Datenbank nicht verfügbar. Diese Funktion ist nur im HA-Addon nutzbar."
        )

    anlage = await get_anlage_with_mapping(db, anlage_id)
    sensor_ids = extract_sensor_ids_from_mapping(anlage.sensor_mapping)

    if not sensor_ids:
        raise HTTPException(
            status_code=400,
            detail="Keine Sensor-Zuordnungen mit Strategie 'sensor' gefunden."
        )

    try:
        response = service.get_verfuegbare_monate(sensor_ids)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fehler bei DB-Abfrage: {e}")

    return VerfuegbareMonate(
        anlage_id=anlage.id,
        anlage_name=anlage.anlagenname,
        erstes_datum=response.erstes_datum,
        letztes_datum=response.letztes_datum,
        anzahl_monate=response.anzahl_monate,
        monate=[
            {
                "jahr": m.jahr,
                "monat": m.monat,
                "monat_name": m.monat_name
            }
            for m in response.monate
        ]
    )


@router.get("/alle-monatswerte/{anlage_id}", response_model=list[AnlagenMonatswertResponse])
async def get_alle_monatswerte(
    anlage_id: int,
    ab_jahr: Optional[int] = Query(None, description="Nur Monate ab diesem Jahr"),
    ab_monat: Optional[int] = Query(None, description="Nur Monate ab diesem Monat (mit ab_jahr)"),
    db: AsyncSession = Depends(get_db)
):
    """
    Holt alle verfügbaren Monatswerte aus HA-Statistiken.

    Ideal für:
    - Initialbefüllung bei neuer Installation
    - Nachträgliche Korrektur fehlender Monate
    - Bulk-Import historischer Daten

    Args:
        anlage_id: ID der Anlage
        ab_jahr: Optional - nur Monate ab diesem Jahr
        ab_monat: Optional - nur Monate ab diesem Monat (erfordert ab_jahr)

    Returns:
        Liste aller Monatswerte
    """
    service = get_ha_statistics_service()
    if not service.is_available:
        raise HTTPException(
            status_code=503,
            detail="HA-Datenbank nicht verfügbar. Diese Funktion ist nur im HA-Addon nutzbar."
        )

    anlage = await get_anlage_with_mapping(db, anlage_id)
    sensor_ids = extract_sensor_ids_from_mapping(anlage.sensor_mapping)

    if not sensor_ids:
        raise HTTPException(
            status_code=400,
            detail="Keine Sensor-Zuordnungen mit Strategie 'sensor' gefunden."
        )

    # Ab-Datum berechnen
    ab_datum = None
    if ab_jahr:
        ab_datum = date(ab_jahr, ab_monat or 1, 1)

    try:
        raw_responses = service.get_alle_monatswerte(sensor_ids, ab_datum)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fehler bei DB-Abfrage: {e}")

    # Auf EEDC-Felder mappen
    ergebnisse = []
    for raw in raw_responses:
        basis_felder, inv_felder = map_sensor_values_to_fields(
            anlage.sensor_mapping,
            raw.sensoren
        )

        ergebnisse.append(AnlagenMonatswertResponse(
            anlage_id=anlage.id,
            anlage_name=anlage.anlagenname,
            jahr=raw.jahr,
            monat=raw.monat,
            monat_name=raw.monat_name,
            basis=basis_felder,
            investitionen=inv_felder
        ))

    return ergebnisse


@router.get("/monatsanfang/{anlage_id}/{jahr}/{monat}")
async def get_monatsanfang_werte(
    anlage_id: int,
    jahr: int,
    monat: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Holt die Zählerstände am Monatsanfang.

    Nützlich für die Initialisierung der MQTT-Startwerte.

    Args:
        anlage_id: ID der Anlage
        jahr: Jahr
        monat: Monat (1-12)

    Returns:
        Dict mit Zählerständen pro Sensor
    """
    if monat < 1 or monat > 12:
        raise HTTPException(status_code=400, detail="Monat muss zwischen 1 und 12 liegen")

    service = get_ha_statistics_service()
    if not service.is_available:
        raise HTTPException(
            status_code=503,
            detail="HA-Datenbank nicht verfügbar. Diese Funktion ist nur im HA-Addon nutzbar."
        )

    anlage = await get_anlage_with_mapping(db, anlage_id)
    sensor_ids = extract_sensor_ids_from_mapping(anlage.sensor_mapping)

    startwerte = {}
    for sensor_id in sensor_ids:
        wert = service.get_monatsanfang_wert(sensor_id, jahr, monat)
        if wert is not None:
            startwerte[sensor_id] = wert

    return {
        "anlage_id": anlage.id,
        "anlage_name": anlage.anlagenname,
        "jahr": jahr,
        "monat": monat,
        "startwerte": startwerte
    }


# =============================================================================
# Import Models
# =============================================================================

class MonatImportStatus(BaseModel):
    """Status eines Monats für den Import."""
    jahr: int
    monat: int
    monat_name: str
    aktion: Literal["importieren", "ueberspringen", "ueberschreiben", "konflikt"]
    grund: str
    ha_werte: dict  # {"einspeisung": 123.4, "netzbezug": 56.7, ...}
    vorhandene_werte: Optional[dict] = None  # Falls Daten existieren


class ImportVorschauResponse(BaseModel):
    """Vorschau für den Import mit Konflikt-Erkennung."""
    anlage_id: int
    anlage_name: str
    anzahl_monate: int
    anzahl_importieren: int
    anzahl_ueberspringen: int
    anzahl_konflikte: int
    monate: list[MonatImportStatus]


class ImportRequest(BaseModel):
    """Request für den Import."""
    monate: list[dict]  # [{"jahr": 2024, "monat": 11}, ...]
    ueberschreiben: bool = False  # Auch vorhandene Daten überschreiben


class ImportResultat(BaseModel):
    """Ergebnis des Imports."""
    erfolg: bool
    importiert: int
    uebersprungen: int
    ueberschrieben: int
    fehler: list[str]


# =============================================================================
# Import Preview Endpoint
# =============================================================================

@router.get("/import-vorschau/{anlage_id}", response_model=ImportVorschauResponse)
async def get_import_vorschau(
    anlage_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Erstellt eine Vorschau für den Import mit Konflikt-Erkennung.

    Prüft für jeden Monat:
    - Existieren bereits Monatsdaten?
    - Haben die existierenden Daten Werte oder sind sie leer?
    - Gibt es Abweichungen zwischen HA und EEDC?

    Returns:
        Vorschau mit Aktions-Empfehlungen pro Monat
    """
    service = get_ha_statistics_service()
    if not service.is_available:
        raise HTTPException(
            status_code=503,
            detail="HA-Datenbank nicht verfügbar. Diese Funktion ist nur im HA-Addon nutzbar."
        )

    anlage = await get_anlage_with_mapping(db, anlage_id)
    sensor_ids = extract_sensor_ids_from_mapping(anlage.sensor_mapping)

    if not sensor_ids:
        raise HTTPException(
            status_code=400,
            detail="Keine Sensor-Zuordnungen mit Strategie 'sensor' gefunden."
        )

    # Alle HA-Monatswerte holen
    try:
        ha_monate = service.get_alle_monatswerte(sensor_ids)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fehler bei DB-Abfrage: {e}")

    # Alle existierenden Monatsdaten laden
    result = await db.execute(
        select(Monatsdaten).where(Monatsdaten.anlage_id == anlage_id)
    )
    vorhandene_md = {(md.jahr, md.monat): md for md in result.scalars().all()}

    # Alle existierenden InvestitionMonatsdaten laden
    inv_result = await db.execute(
        select(Investition).where(Investition.anlage_id == anlage_id)
    )
    investitionen = {str(inv.id): inv for inv in inv_result.scalars().all()}

    imd_result = await db.execute(
        select(InvestitionMonatsdaten).where(
            InvestitionMonatsdaten.investition_id.in_([int(i) for i in investitionen.keys()])
        )
    )
    vorhandene_imd = {}
    for imd in imd_result.scalars().all():
        key = (imd.investition_id, imd.jahr, imd.monat)
        vorhandene_imd[key] = imd

    # Jeden Monat analysieren
    monate_status: list[MonatImportStatus] = []
    anzahl_importieren = 0
    anzahl_ueberspringen = 0
    anzahl_konflikte = 0

    for ha_monat in ha_monate:
        jahr = ha_monat.jahr
        monat = ha_monat.monat

        # HA-Werte extrahieren
        ha_werte = {}
        for sensor in ha_monat.sensoren:
            # Sensor-ID zu Feld-Name mappen
            for basis_feld, basis_config in (anlage.sensor_mapping.get("basis") or {}).items():
                if basis_config and basis_config.get("sensor_id") == sensor.sensor_id:
                    ha_werte[basis_feld] = sensor.differenz

        # Investitions-Werte
        for inv_id, inv_config in (anlage.sensor_mapping.get("investitionen") or {}).items():
            felder = inv_config.get("felder", {})
            for feld, feld_config in felder.items():
                if feld_config and feld_config.get("sensor_id"):
                    for sensor in ha_monat.sensoren:
                        if sensor.sensor_id == feld_config["sensor_id"]:
                            ha_werte[f"inv_{inv_id}_{feld}"] = sensor.differenz

        # Prüfen ob Monatsdaten existieren
        md = vorhandene_md.get((jahr, monat))

        if md is None:
            # Keine Daten vorhanden → Importieren
            monate_status.append(MonatImportStatus(
                jahr=jahr,
                monat=monat,
                monat_name=ha_monat.monat_name,
                aktion="importieren",
                grund="Keine Monatsdaten vorhanden",
                ha_werte=ha_werte,
                vorhandene_werte=None
            ))
            anzahl_importieren += 1
        else:
            # Daten existieren - prüfen ob leer oder mit Werten
            vorhandene_werte = {
                "einspeisung": md.einspeisung_kwh,
                "netzbezug": md.netzbezug_kwh,
            }

            # Sind die Basis-Werte leer (0 oder sehr klein)?
            basis_leer = (
                (md.einspeisung_kwh or 0) < 0.1 and
                (md.netzbezug_kwh or 0) < 0.1
            )

            if basis_leer:
                # Daten existieren aber sind leer → Importieren
                monate_status.append(MonatImportStatus(
                    jahr=jahr,
                    monat=monat,
                    monat_name=ha_monat.monat_name,
                    aktion="importieren",
                    grund="Monatsdaten vorhanden aber leer",
                    ha_werte=ha_werte,
                    vorhandene_werte=vorhandene_werte
                ))
                anzahl_importieren += 1
            else:
                # Daten existieren mit Werten - Konflikt!
                # Prüfen ob große Abweichung
                ha_einspeisung = ha_werte.get("einspeisung", 0)
                ha_netzbezug = ha_werte.get("netzbezug", 0)

                abweichung_einspeisung = abs(ha_einspeisung - (md.einspeisung_kwh or 0))
                abweichung_netzbezug = abs(ha_netzbezug - (md.netzbezug_kwh or 0))

                if abweichung_einspeisung < 1 and abweichung_netzbezug < 1:
                    # Sehr geringe Abweichung → Überspringen
                    monate_status.append(MonatImportStatus(
                        jahr=jahr,
                        monat=monat,
                        monat_name=ha_monat.monat_name,
                        aktion="ueberspringen",
                        grund=f"Daten stimmen überein (Δ < 1 kWh)",
                        ha_werte=ha_werte,
                        vorhandene_werte=vorhandene_werte
                    ))
                    anzahl_ueberspringen += 1
                else:
                    # Abweichung → Konflikt
                    monate_status.append(MonatImportStatus(
                        jahr=jahr,
                        monat=monat,
                        monat_name=ha_monat.monat_name,
                        aktion="konflikt",
                        grund=f"Abweichung: Einspeisung {abweichung_einspeisung:.1f} kWh, Netzbezug {abweichung_netzbezug:.1f} kWh",
                        ha_werte=ha_werte,
                        vorhandene_werte=vorhandene_werte
                    ))
                    anzahl_konflikte += 1

    return ImportVorschauResponse(
        anlage_id=anlage.id,
        anlage_name=anlage.anlagenname,
        anzahl_monate=len(monate_status),
        anzahl_importieren=anzahl_importieren,
        anzahl_ueberspringen=anzahl_ueberspringen,
        anzahl_konflikte=anzahl_konflikte,
        monate=monate_status
    )


# =============================================================================
# Import Execute Endpoint
# =============================================================================

@router.post("/import/{anlage_id}", response_model=ImportResultat)
async def import_ha_statistics(
    anlage_id: int,
    request: ImportRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Importiert HA-Statistik-Daten in EEDC Monatsdaten.

    Args:
        anlage_id: ID der Anlage
        request.monate: Liste der zu importierenden Monate
        request.ueberschreiben: Auch vorhandene Daten überschreiben

    Returns:
        Import-Statistik
    """
    service = get_ha_statistics_service()
    if not service.is_available:
        raise HTTPException(
            status_code=503,
            detail="HA-Datenbank nicht verfügbar."
        )

    anlage = await get_anlage_with_mapping(db, anlage_id)
    sensor_mapping = anlage.sensor_mapping
    sensor_ids = extract_sensor_ids_from_mapping(sensor_mapping)

    importiert = 0
    uebersprungen = 0
    ueberschrieben = 0
    fehler = []

    for monat_req in request.monate:
        jahr = monat_req["jahr"]
        monat = monat_req["monat"]

        try:
            # HA-Werte für diesen Monat holen
            ha_response = service.get_monatswerte(sensor_ids, jahr, monat)

            # Sensor-Werte zu Dict mappen
            sensor_values = {s.sensor_id: s.differenz for s in ha_response.sensoren}

            # Basis-Werte extrahieren
            einspeisung = None
            netzbezug = None

            basis_mapping = sensor_mapping.get("basis", {})
            if basis_mapping.get("einspeisung", {}).get("sensor_id"):
                einspeisung = sensor_values.get(basis_mapping["einspeisung"]["sensor_id"])
            if basis_mapping.get("netzbezug", {}).get("sensor_id"):
                netzbezug = sensor_values.get(basis_mapping["netzbezug"]["sensor_id"])

            # Monatsdaten laden oder erstellen
            result = await db.execute(
                select(Monatsdaten).where(
                    and_(
                        Monatsdaten.anlage_id == anlage_id,
                        Monatsdaten.jahr == jahr,
                        Monatsdaten.monat == monat
                    )
                )
            )
            md = result.scalar_one_or_none()

            if md is None:
                # Neu erstellen
                md = Monatsdaten(
                    anlage_id=anlage_id,
                    jahr=jahr,
                    monat=monat,
                    einspeisung_kwh=einspeisung or 0,
                    netzbezug_kwh=netzbezug or 0,
                    datenquelle="ha_statistics"
                )
                db.add(md)
                importiert += 1
            else:
                # Existiert - prüfen ob überschreiben
                hat_werte = (md.einspeisung_kwh or 0) > 0.1 or (md.netzbezug_kwh or 0) > 0.1

                if hat_werte and not request.ueberschreiben:
                    uebersprungen += 1
                    continue

                # Überschreiben
                if einspeisung is not None:
                    md.einspeisung_kwh = einspeisung
                if netzbezug is not None:
                    md.netzbezug_kwh = netzbezug
                md.datenquelle = "ha_statistics"

                if hat_werte:
                    ueberschrieben += 1
                else:
                    importiert += 1

            # InvestitionMonatsdaten verarbeiten
            inv_mapping = sensor_mapping.get("investitionen", {})
            for inv_id_str, inv_config in inv_mapping.items():
                inv_id = int(inv_id_str)
                felder = inv_config.get("felder", {})

                # Werte aus HA extrahieren
                inv_werte = {}
                for feld, feld_config in felder.items():
                    if feld_config and feld_config.get("sensor_id"):
                        sensor_id = feld_config["sensor_id"]
                        if sensor_id in sensor_values:
                            inv_werte[feld] = sensor_values[sensor_id]

                if not inv_werte:
                    continue

                # InvestitionMonatsdaten laden oder erstellen
                imd_result = await db.execute(
                    select(InvestitionMonatsdaten).where(
                        and_(
                            InvestitionMonatsdaten.investition_id == inv_id,
                            InvestitionMonatsdaten.jahr == jahr,
                            InvestitionMonatsdaten.monat == monat
                        )
                    )
                )
                imd = imd_result.scalar_one_or_none()

                if imd is None:
                    imd = InvestitionMonatsdaten(
                        investition_id=inv_id,
                        jahr=jahr,
                        monat=monat,
                        verbrauch_daten=inv_werte
                    )
                    db.add(imd)
                else:
                    # Merge mit existierenden Daten
                    if imd.verbrauch_daten is None:
                        imd.verbrauch_daten = {}

                    for feld, wert in inv_werte.items():
                        # Nur überschreiben wenn leer oder explizit gewünscht
                        vorhandener_wert = imd.verbrauch_daten.get(feld)
                        if vorhandener_wert is None or vorhandener_wert == 0 or request.ueberschreiben:
                            imd.verbrauch_daten[feld] = wert

                    flag_modified(imd, "verbrauch_daten")

        except Exception as e:
            fehler.append(f"{jahr}/{monat:02d}: {str(e)}")

    await db.commit()

    return ImportResultat(
        erfolg=len(fehler) == 0,
        importiert=importiert,
        uebersprungen=uebersprungen,
        ueberschrieben=ueberschrieben,
        fehler=fehler
    )
