"""
PVGIS API Routes

Integration mit der PVGIS API der EU für PV-Ertragsprognosen.
https://re.jrc.ec.europa.eu/pvg_tools/en/

PVGIS liefert:
- Monatliche PV-Ertragserwartungen basierend auf Standort und Anlagenparametern
- Historische Strahlungsdaten
- Optimale Neigung/Ausrichtung

Struktur:
- PV-Module werden als Investitionen vom Typ "pv-module" erfasst
- Jedes Modul hat eigene Ausrichtung, Neigung und Leistung
- PVGIS Prognose kann pro Modul oder für die gesamte Anlage abgerufen werden
- Die Gesamt-Prognose ist die Summe aller PV-Module
"""

from typing import Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field
import httpx

from backend.api.deps import get_db
from backend.models.anlage import Anlage
from backend.models.investition import Investition, InvestitionTyp
from backend.models.pvgis_prognose import PVGISPrognose as PVGISPrognoseModel, PVGISMonatsprognose

# =============================================================================
# PVGIS API Constants
# =============================================================================

PVGIS_BASE_URL = "https://re.jrc.ec.europa.eu/api/v5_2"

# Standard-Werte für Deutschland
DEFAULT_LOSSES = 14  # Systemverluste in % (Kabel, Wechselrichter, etc.)
DEFAULT_AZIMUTH = 0  # 0 = Süd, -90 = Ost, 90 = West
DEFAULT_TILT = 35    # Typische Dachneigung in Deutschland


# =============================================================================
# Pydantic Schemas
# =============================================================================

class PVGISMonthlyData(BaseModel):
    """Monatliche Ertragsdaten von PVGIS."""
    monat: int = Field(..., ge=1, le=12)
    e_m: float = Field(..., description="Monatlicher Ertrag in kWh")
    h_m: float = Field(..., description="Globale Einstrahlung auf Modulebene kWh/m²")
    sd_m: float = Field(..., description="Standardabweichung kWh")


class PVModulPrognose(BaseModel):
    """PVGIS Prognose für ein einzelnes PV-Modul."""
    investition_id: int
    bezeichnung: str
    leistung_kwp: float
    ausrichtung: str
    ausrichtung_grad: float
    neigung_grad: float
    jahresertrag_kwh: float
    spezifischer_ertrag_kwh_kwp: float
    monatsdaten: list[PVGISMonthlyData]


class PVGISPrognose(BaseModel):
    """Vollständige PVGIS Prognose für eine Anlage (Summe aller PV-Module)."""
    anlage_id: int
    anlage_name: str

    # Standortdaten (von Anlage)
    latitude: float
    longitude: float

    # Gesamt-Ergebnisse
    gesamt_leistung_kwp: float
    jahresertrag_kwh: float
    spezifischer_ertrag_kwh_kwp: float = Field(..., description="kWh pro kWp")

    # Monatliche Summen
    monatsdaten: list[PVGISMonthlyData]

    # Detail pro PV-Modul
    module: list[PVModulPrognose]

    # Systemparameter
    system_losses: float = Field(..., description="Systemverluste in %")

    # Metadata
    abgerufen_am: datetime
    pvgis_version: str = "5.2"


class GespeichertePrognoseResponse(BaseModel):
    """Response für gespeicherte Prognose."""
    id: int
    anlage_id: int
    abgerufen_am: datetime
    jahresertrag_kwh: float
    spezifischer_ertrag_kwh_kwp: float
    neigung_grad: float
    ausrichtung_grad: float
    ist_aktiv: bool

    class Config:
        from_attributes = True


# =============================================================================
# Router
# =============================================================================

router = APIRouter()


def ausrichtung_zu_azimut(ausrichtung: Optional[str]) -> float:
    """
    Konvertiert Ausrichtungstext zu PVGIS Azimut.

    PVGIS Azimut: 0 = Süd, -90 = Ost, 90 = West, 180/-180 = Nord
    """
    if not ausrichtung:
        return DEFAULT_AZIMUTH

    ausrichtung_lower = ausrichtung.lower()

    mapping = {
        "süd": 0, "s": 0, "south": 0,
        "südost": -45, "so": -45, "southeast": -45,
        "ost": -90, "o": -90, "east": -90,
        "nordost": -135, "no": -135, "northeast": -135,
        "nord": 180, "n": 180, "north": 180,
        "nordwest": 135, "nw": 135, "northwest": 135,
        "west": 90, "w": 90,
        "südwest": 45, "sw": 45, "southwest": 45,
        # Ost-West Anlagen (Mittelwert)
        "ost-west": 0, "ow": 0, "o-w": 0, "east-west": 0,
    }

    for key, value in mapping.items():
        if key in ausrichtung_lower:
            return value

    return DEFAULT_AZIMUTH


def _azimut_zu_richtung(azimut: float) -> str:
    """Konvertiert Azimut-Grad zu Himmelsrichtung."""
    if -22.5 <= azimut < 22.5:
        return "Süd"
    elif 22.5 <= azimut < 67.5:
        return "Südwest"
    elif 67.5 <= azimut < 112.5:
        return "West"
    elif 112.5 <= azimut < 157.5:
        return "Nordwest"
    elif azimut >= 157.5 or azimut < -157.5:
        return "Nord"
    elif -157.5 <= azimut < -112.5:
        return "Nordost"
    elif -112.5 <= azimut < -67.5:
        return "Ost"
    elif -67.5 <= azimut < -22.5:
        return "Südost"
    return "Süd"


async def fetch_pvgis_data(
    latitude: float,
    longitude: float,
    peak_power: float,
    tilt: float,
    azimuth: float,
    losses: float = DEFAULT_LOSSES
) -> dict:
    """
    Ruft Daten von der PVGIS API ab.

    Args:
        latitude: Breitengrad
        longitude: Längengrad
        peak_power: Installierte Leistung in kWp
        tilt: Modulneigung in Grad
        azimuth: Azimut (0=Süd)
        losses: Systemverluste in %

    Returns:
        dict: PVGIS Antwort

    Raises:
        HTTPException: Bei API-Fehlern
    """
    params = {
        "lat": latitude,
        "lon": longitude,
        "peakpower": peak_power,
        "angle": tilt,
        "aspect": azimuth,
        "loss": losses,
        "outputformat": "json",
        "pvtechchoice": "crystSi",  # Kristallines Silizium (Standard)
        "mountingplace": "building",  # Dachanlage
    }

    url = f"{PVGIS_BASE_URL}/PVcalc"

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except httpx.TimeoutException:
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="PVGIS API Timeout - bitte erneut versuchen"
            )
        except httpx.HTTPStatusError as e:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"PVGIS API Fehler: {e.response.status_code}"
            )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"PVGIS Anfrage fehlgeschlagen: {str(e)}"
            )


@router.get("/prognose/{anlage_id}", response_model=PVGISPrognose)
async def get_pvgis_prognose(
    anlage_id: int,
    system_losses: float = DEFAULT_LOSSES,
    db: AsyncSession = Depends(get_db)
):
    """
    Holt PVGIS Ertragsprognose für eine Anlage.

    Summiert die Prognosen aller PV-Module (Investitionen vom Typ "pv-module").
    Verwendet die Koordinaten der Anlage und die Ausrichtung/Neigung jedes Moduls.

    Args:
        anlage_id: ID der Anlage
        system_losses: Systemverluste in % (Standard: 14)

    Returns:
        PVGISPrognose: Monatliche Ertragsprognose für alle Module
    """
    # Anlage laden
    result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    anlage = result.scalar_one_or_none()

    if not anlage:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Anlage mit ID {anlage_id} nicht gefunden"
        )

    # Koordinaten prüfen
    if not anlage.latitude or not anlage.longitude:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Anlage hat keine Geokoordinaten. Bitte latitude/longitude in den Stammdaten ergänzen."
        )

    # PV-Module (Investitionen) laden
    result = await db.execute(
        select(Investition)
        .where(Investition.anlage_id == anlage_id)
        .where(Investition.typ == InvestitionTyp.PV_MODULE.value)
        .where(Investition.aktiv == True)
    )
    pv_module = result.scalars().all()

    if not pv_module:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Keine PV-Module für diese Anlage gefunden. Bitte zuerst PV-Module als Investitionen anlegen."
        )

    # Prognose für jedes Modul abrufen
    module_prognosen: list[PVModulPrognose] = []
    gesamt_monatsdaten: dict[int, dict] = {m: {"e_m": 0.0, "h_m": 0.0, "sd_m": 0.0} for m in range(1, 13)}
    gesamt_jahresertrag = 0.0
    gesamt_leistung = 0.0

    for modul in pv_module:
        if not modul.leistung_kwp or modul.leistung_kwp <= 0:
            continue  # Modul ohne Leistung überspringen

        tilt = modul.neigung_grad if modul.neigung_grad is not None else DEFAULT_TILT
        azimuth = ausrichtung_zu_azimut(modul.ausrichtung)

        # PVGIS API aufrufen
        pvgis_data = await fetch_pvgis_data(
            latitude=anlage.latitude,
            longitude=anlage.longitude,
            peak_power=modul.leistung_kwp,
            tilt=tilt,
            azimuth=azimuth,
            losses=system_losses
        )

        # Ergebnis parsen
        outputs = pvgis_data.get("outputs", {})
        monthly = outputs.get("monthly", {}).get("fixed", [])
        totals = outputs.get("totals", {}).get("fixed", {})

        # Monatsdaten extrahieren
        modul_monatsdaten = []
        for m in monthly:
            monat = m["month"]
            e_m = round(m["E_m"], 2)
            h_m = round(m["H(i)_m"], 2)
            sd_m = round(m["SD_m"], 2)

            modul_monatsdaten.append(PVGISMonthlyData(
                monat=monat,
                e_m=e_m,
                h_m=h_m,
                sd_m=sd_m
            ))

            # Zu Gesamt addieren
            gesamt_monatsdaten[monat]["e_m"] += e_m
            gesamt_monatsdaten[monat]["h_m"] = h_m  # Einstrahlung ist gleich für alle Module am Standort
            gesamt_monatsdaten[monat]["sd_m"] += sd_m

        # Jahreswerte
        jahresertrag = totals.get("E_y", 0)
        spezifischer_ertrag = jahresertrag / modul.leistung_kwp if modul.leistung_kwp > 0 else 0

        module_prognosen.append(PVModulPrognose(
            investition_id=modul.id,
            bezeichnung=modul.bezeichnung,
            leistung_kwp=modul.leistung_kwp,
            ausrichtung=modul.ausrichtung or _azimut_zu_richtung(azimuth),
            ausrichtung_grad=azimuth,
            neigung_grad=tilt,
            jahresertrag_kwh=round(jahresertrag, 2),
            spezifischer_ertrag_kwh_kwp=round(spezifischer_ertrag, 2),
            monatsdaten=modul_monatsdaten
        ))

        gesamt_jahresertrag += jahresertrag
        gesamt_leistung += modul.leistung_kwp

    # Gesamt-Monatsdaten zusammenstellen
    gesamt_monatsdaten_list = [
        PVGISMonthlyData(
            monat=m,
            e_m=round(gesamt_monatsdaten[m]["e_m"], 2),
            h_m=round(gesamt_monatsdaten[m]["h_m"], 2),
            sd_m=round(gesamt_monatsdaten[m]["sd_m"], 2)
        )
        for m in range(1, 13)
    ]

    spezifischer_ertrag_gesamt = gesamt_jahresertrag / gesamt_leistung if gesamt_leistung > 0 else 0

    return PVGISPrognose(
        anlage_id=anlage.id,
        anlage_name=anlage.anlagenname,
        latitude=anlage.latitude,
        longitude=anlage.longitude,
        gesamt_leistung_kwp=round(gesamt_leistung, 2),
        jahresertrag_kwh=round(gesamt_jahresertrag, 2),
        spezifischer_ertrag_kwh_kwp=round(spezifischer_ertrag_gesamt, 2),
        monatsdaten=gesamt_monatsdaten_list,
        module=module_prognosen,
        system_losses=system_losses,
        abgerufen_am=datetime.utcnow()
    )


@router.get("/modul/{investition_id}")
async def get_pvgis_modul_prognose(
    investition_id: int,
    system_losses: float = DEFAULT_LOSSES,
    db: AsyncSession = Depends(get_db)
):
    """
    Holt PVGIS Ertragsprognose für ein einzelnes PV-Modul.

    Args:
        investition_id: ID der PV-Modul-Investition
        system_losses: Systemverluste in %

    Returns:
        dict: Prognose für das Modul
    """
    # Investition laden
    result = await db.execute(
        select(Investition).where(Investition.id == investition_id)
    )
    modul = result.scalar_one_or_none()

    if not modul:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Investition mit ID {investition_id} nicht gefunden"
        )

    if modul.typ != InvestitionTyp.PV_MODULE.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Investition ist kein PV-Modul (Typ: {modul.typ})"
        )

    if not modul.leistung_kwp or modul.leistung_kwp <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="PV-Modul hat keine Leistung (kWp) definiert"
        )

    # Anlage für Koordinaten laden
    result = await db.execute(
        select(Anlage).where(Anlage.id == modul.anlage_id)
    )
    anlage = result.scalar_one_or_none()

    if not anlage or not anlage.latitude or not anlage.longitude:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Anlage hat keine Geokoordinaten"
        )

    tilt = modul.neigung_grad if modul.neigung_grad is not None else DEFAULT_TILT
    azimuth = ausrichtung_zu_azimut(modul.ausrichtung)

    # PVGIS API aufrufen
    pvgis_data = await fetch_pvgis_data(
        latitude=anlage.latitude,
        longitude=anlage.longitude,
        peak_power=modul.leistung_kwp,
        tilt=tilt,
        azimuth=azimuth,
        losses=system_losses
    )

    outputs = pvgis_data.get("outputs", {})
    monthly = outputs.get("monthly", {}).get("fixed", [])
    totals = outputs.get("totals", {}).get("fixed", {})

    monatsdaten = [
        {
            "monat": m["month"],
            "e_m": round(m["E_m"], 2),
            "h_m": round(m["H(i)_m"], 2),
            "sd_m": round(m["SD_m"], 2)
        }
        for m in monthly
    ]

    jahresertrag = totals.get("E_y", 0)
    spezifischer_ertrag = jahresertrag / modul.leistung_kwp if modul.leistung_kwp > 0 else 0

    return {
        "investition_id": modul.id,
        "bezeichnung": modul.bezeichnung,
        "leistung_kwp": modul.leistung_kwp,
        "ausrichtung": modul.ausrichtung or _azimut_zu_richtung(azimuth),
        "ausrichtung_grad": azimuth,
        "neigung_grad": tilt,
        "jahresertrag_kwh": round(jahresertrag, 2),
        "spezifischer_ertrag_kwh_kwp": round(spezifischer_ertrag, 2),
        "monatsdaten": monatsdaten,
        "system_losses": system_losses,
        "standort": {
            "latitude": anlage.latitude,
            "longitude": anlage.longitude
        },
        "abgerufen_am": datetime.utcnow().isoformat()
    }


@router.get("/optimum/{anlage_id}")
async def get_pvgis_optimum(
    anlage_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Ermittelt die optimale Neigung und Ausrichtung für den Standort.

    Args:
        anlage_id: ID der Anlage (für Koordinaten)

    Returns:
        dict: Optimale Parameter für maximalen Jahresertrag
    """
    result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    anlage = result.scalar_one_or_none()

    if not anlage:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Anlage mit ID {anlage_id} nicht gefunden"
        )

    if not anlage.latitude or not anlage.longitude:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Anlage hat keine Geokoordinaten."
        )

    # PVGIS mit optimalem Winkel (1 kWp Referenz)
    params = {
        "lat": anlage.latitude,
        "lon": anlage.longitude,
        "peakpower": 1.0,  # Referenz 1 kWp
        "loss": DEFAULT_LOSSES,
        "outputformat": "json",
        "pvtechchoice": "crystSi",
        "mountingplace": "building",
        "optimalangles": 1,  # Optimale Winkel berechnen
    }

    url = f"{PVGIS_BASE_URL}/PVcalc"

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"PVGIS API Fehler: {str(e)}"
            )

    inputs = data.get("inputs", {}).get("mounting_system", {}).get("fixed", {})
    outputs = data.get("outputs", {}).get("totals", {}).get("fixed", {})

    optimal_tilt = inputs.get("slope", {}).get("value", DEFAULT_TILT)
    optimal_azimuth = inputs.get("azimuth", {}).get("value", DEFAULT_AZIMUTH)
    optimal_ertrag_pro_kwp = outputs.get("E_y", 0)

    return {
        "anlage_id": anlage.id,
        "anlage_name": anlage.anlagenname,
        "standort": {
            "latitude": anlage.latitude,
            "longitude": anlage.longitude
        },
        "optimal": {
            "neigung_grad": round(optimal_tilt, 1),
            "azimut_grad": round(optimal_azimuth, 1),
            "azimut_richtung": _azimut_zu_richtung(optimal_azimuth),
            "spezifischer_ertrag_kwh_kwp": round(optimal_ertrag_pro_kwp, 2)
        },
        "hinweis": "Die optimale Ausrichtung bezieht sich auf eine nach Süden ausgerichtete, freistehende Anlage. Dachneigung und -ausrichtung sind oft vorgegeben."
    }


# =============================================================================
# Speichern und Laden von Prognosen
# =============================================================================

@router.post("/prognose/{anlage_id}/speichern", response_model=GespeichertePrognoseResponse)
async def speichere_pvgis_prognose(
    anlage_id: int,
    system_losses: float = DEFAULT_LOSSES,
    db: AsyncSession = Depends(get_db)
):
    """
    Ruft PVGIS Prognose ab und speichert sie in der Datenbank.

    Deaktiviert vorherige aktive Prognosen für diese Anlage.

    Args:
        anlage_id: ID der Anlage
        system_losses: Systemverluste in %

    Returns:
        GespeichertePrognoseResponse: Die gespeicherte Prognose
    """
    # Prognose abrufen
    prognose = await get_pvgis_prognose(
        anlage_id=anlage_id,
        system_losses=system_losses,
        db=db
    )

    # Vorherige aktive Prognosen deaktivieren
    result = await db.execute(
        select(PVGISPrognoseModel)
        .where(PVGISPrognoseModel.anlage_id == anlage_id)
        .where(PVGISPrognoseModel.ist_aktiv == True)
    )
    for alte_prognose in result.scalars().all():
        alte_prognose.ist_aktiv = False

    # Monatswerte als JSON vorbereiten
    monatswerte = [
        {"monat": m.monat, "e_m": m.e_m, "h_m": m.h_m, "sd_m": m.sd_m}
        for m in prognose.monatsdaten
    ]

    # Gewichtete Durchschnittswerte für Speicherung berechnen
    gesamt_neigung = 0.0
    gesamt_azimut = 0.0
    for modul in prognose.module:
        gewicht = modul.leistung_kwp / prognose.gesamt_leistung_kwp if prognose.gesamt_leistung_kwp > 0 else 0
        gesamt_neigung += modul.neigung_grad * gewicht
        gesamt_azimut += modul.ausrichtung_grad * gewicht

    # Neue Prognose erstellen
    neue_prognose = PVGISPrognoseModel(
        anlage_id=anlage_id,
        latitude=prognose.latitude,
        longitude=prognose.longitude,
        neigung_grad=round(gesamt_neigung, 1),
        ausrichtung_grad=round(gesamt_azimut, 1),
        system_losses=prognose.system_losses,
        jahresertrag_kwh=prognose.jahresertrag_kwh,
        spezifischer_ertrag_kwh_kwp=prognose.spezifischer_ertrag_kwh_kwp,
        monatswerte=monatswerte,
        ist_aktiv=True
    )

    db.add(neue_prognose)
    await db.flush()

    # Normalisierte Monatsprognosen erstellen
    for m in prognose.monatsdaten:
        monats_prognose = PVGISMonatsprognose(
            prognose_id=neue_prognose.id,
            monat=m.monat,
            ertrag_kwh=m.e_m,
            einstrahlung_kwh_m2=m.h_m,
            standardabweichung_kwh=m.sd_m
        )
        db.add(monats_prognose)

    await db.flush()
    await db.refresh(neue_prognose)

    return neue_prognose


@router.get("/prognose/{anlage_id}/gespeichert", response_model=list[GespeichertePrognoseResponse])
async def liste_gespeicherte_prognosen(
    anlage_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Listet alle gespeicherten Prognosen für eine Anlage auf.
    """
    result = await db.execute(
        select(PVGISPrognoseModel)
        .where(PVGISPrognoseModel.anlage_id == anlage_id)
        .order_by(PVGISPrognoseModel.abgerufen_am.desc())
    )
    return result.scalars().all()


@router.get("/prognose/{anlage_id}/aktiv")
async def get_aktive_prognose(
    anlage_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Gibt die aktive Prognose für eine Anlage zurück.
    """
    result = await db.execute(
        select(PVGISPrognoseModel)
        .where(PVGISPrognoseModel.anlage_id == anlage_id)
        .where(PVGISPrognoseModel.ist_aktiv == True)
        .order_by(PVGISPrognoseModel.abgerufen_am.desc())
        .limit(1)
    )
    prognose = result.scalar_one_or_none()

    if not prognose:
        return None

    return {
        "id": prognose.id,
        "anlage_id": prognose.anlage_id,
        "abgerufen_am": prognose.abgerufen_am,
        "latitude": prognose.latitude,
        "longitude": prognose.longitude,
        "neigung_grad": prognose.neigung_grad,
        "ausrichtung_grad": prognose.ausrichtung_grad,
        "ausrichtung_richtung": _azimut_zu_richtung(prognose.ausrichtung_grad),
        "system_losses": prognose.system_losses,
        "jahresertrag_kwh": prognose.jahresertrag_kwh,
        "spezifischer_ertrag_kwh_kwp": prognose.spezifischer_ertrag_kwh_kwp,
        "monatswerte": prognose.monatswerte
    }


@router.put("/prognose/{prognose_id}/aktivieren")
async def aktiviere_prognose(
    prognose_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Aktiviert eine gespeicherte Prognose.
    """
    result = await db.execute(
        select(PVGISPrognoseModel).where(PVGISPrognoseModel.id == prognose_id)
    )
    prognose = result.scalar_one_or_none()

    if not prognose:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Prognose mit ID {prognose_id} nicht gefunden"
        )

    # Andere Prognosen der Anlage deaktivieren
    result = await db.execute(
        select(PVGISPrognoseModel)
        .where(PVGISPrognoseModel.anlage_id == prognose.anlage_id)
        .where(PVGISPrognoseModel.ist_aktiv == True)
    )
    for alte_prognose in result.scalars().all():
        alte_prognose.ist_aktiv = False

    prognose.ist_aktiv = True
    await db.flush()

    return {"message": "Prognose aktiviert", "id": prognose_id}


@router.delete("/prognose/{prognose_id}")
async def loesche_prognose(
    prognose_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Löscht eine gespeicherte Prognose.
    """
    result = await db.execute(
        select(PVGISPrognoseModel).where(PVGISPrognoseModel.id == prognose_id)
    )
    prognose = result.scalar_one_or_none()

    if not prognose:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Prognose mit ID {prognose_id} nicht gefunden"
        )

    await db.delete(prognose)
    return {"message": "Prognose gelöscht", "id": prognose_id}
