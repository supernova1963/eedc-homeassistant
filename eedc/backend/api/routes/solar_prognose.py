"""
Solar-Prognose API Routes

Direkte PV-Ertragsprognose basierend auf Open-Meteo Solar API.
Nutzt GTI (Global Tilted Irradiance) für geneigte PV-Module.
"""

from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_db
from backend.models.anlage import Anlage
from backend.models.investition import Investition
from backend.models.pvgis_prognose import PVGISPrognose
from backend.services.solar_forecast_service import (
    get_solar_prognose,
    get_multi_string_prognose,
    PVStringConfig,
    DEFAULT_SYSTEM_LOSSES,
)

router = APIRouter()


# =============================================================================
# Pydantic Schemas
# =============================================================================

class SolarPrognoseTagSchema(BaseModel):
    """Prognose für einen Tag."""
    datum: str
    pv_ertrag_kwh: float
    gti_kwh_m2: float = Field(description="Global Tilted Irradiance")
    ghi_kwh_m2: float = Field(description="Global Horizontal Irradiance (Vergleich)")
    sonnenstunden: float
    temperatur_max_c: float | None
    temperatur_min_c: float | None
    bewoelkung_prozent: int | None
    niederschlag_mm: float | None
    schnee_cm: float | None


class StringPrognoseSchema(BaseModel):
    """Prognose für einen einzelnen String."""
    name: str
    kwp: float
    neigung: int
    ausrichtung: int
    summe_kwh: float
    durchschnitt_kwh_tag: float
    tageswerte: List[dict]


class SolarPrognoseResponse(BaseModel):
    """Response für Solar-Prognose."""
    anlage_id: int
    anlagenname: str
    kwp_gesamt: float
    neigung: int = Field(description="Durchschnittliche/Haupt-Neigung in Grad")
    ausrichtung: int = Field(description="Durchschnittliche/Haupt-Ausrichtung (0=Süd)")
    system_losses_prozent: float
    prognose_zeitraum: dict
    summe_kwh: float
    durchschnitt_kwh_tag: float
    tageswerte: List[SolarPrognoseTagSchema]
    string_prognosen: List[StringPrognoseSchema] | None = Field(
        None, description="Prognosen pro String (falls mehrere Ausrichtungen)"
    )
    datenquelle: str
    abgerufen_am: str
    hinweise: List[str] = []


# =============================================================================
# Endpoints
# =============================================================================

@router.get("/{anlage_id}", response_model=SolarPrognoseResponse)
async def get_solar_prognose_endpoint(
    anlage_id: int,
    tage: int = Query(default=7, ge=1, le=16, description="Anzahl Tage (1-16)"),
    pro_string: bool = Query(
        default=False,
        description="Separate Prognose pro PV-String (bei unterschiedlichen Ausrichtungen)"
    ),
    db: AsyncSession = Depends(get_db)
):
    """
    PV-Ertragsprognose basierend auf Open-Meteo Solar API mit GTI.

    Verwendet:
    - GTI (Global Tilted Irradiance) für geneigte Module
    - Neigung und Ausrichtung aus PV-Modul-Konfiguration
    - Systemverluste aus PVGIS-Einstellungen

    Args:
        anlage_id: ID der Anlage
        tage: Anzahl Vorhersagetage (1-16)
        pro_string: Separate Prognose pro String bei unterschiedlichen Ausrichtungen

    Returns:
        SolarPrognoseResponse: Detaillierte PV-Ertragsprognose
    """
    # Anlage laden
    result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    anlage = result.scalar_one_or_none()

    if not anlage:
        raise HTTPException(status_code=404, detail="Anlage nicht gefunden")

    if not anlage.latitude or not anlage.longitude:
        raise HTTPException(
            status_code=400,
            detail="Anlage hat keine Koordinaten. Bitte Standort konfigurieren."
        )

    # PV-Module laden
    result = await db.execute(
        select(Investition).where(
            Investition.anlage_id == anlage_id,
            Investition.typ == "pv-module",
            Investition.aktiv == True
        )
    )
    pv_module = result.scalars().all()

    # Balkonkraftwerke laden
    result = await db.execute(
        select(Investition).where(
            Investition.anlage_id == anlage_id,
            Investition.typ == "balkonkraftwerk",
            Investition.aktiv == True
        )
    )
    balkonkraftwerke = result.scalars().all()

    alle_pv = list(pv_module) + list(balkonkraftwerke)

    if not alle_pv:
        raise HTTPException(
            status_code=400,
            detail="Keine PV-Module oder Balkonkraftwerke konfiguriert."
        )

    # System-Verluste aus PVGIS laden (falls vorhanden)
    result = await db.execute(
        select(PVGISPrognose).where(
            PVGISPrognose.anlage_id == anlage_id,
            PVGISPrognose.ist_aktiv == True
        )
    )
    pvgis = result.scalar_one_or_none()
    system_losses = (
        pvgis.system_losses / 100 if pvgis and pvgis.system_losses
        else DEFAULT_SYSTEM_LOSSES
    )

    # String-Konfigurationen erstellen
    strings: List[PVStringConfig] = []
    hinweise: List[str] = []

    for pv in alle_pv:
        kwp = pv.leistung_kwp or 0
        if kwp <= 0:
            continue

        # Neigung und Ausrichtung aus Parameter
        params = pv.parameter or {}
        neigung = params.get("neigung_grad") or params.get("neigung") or 35
        ausrichtung = params.get("ausrichtung_grad") or params.get("ausrichtung") or 0

        # Ausrichtung konvertieren falls als Text
        if isinstance(ausrichtung, str):
            ausrichtung_map = {
                "sued": 0, "süd": 0, "s": 0,
                "ost": -90, "o": -90, "e": -90,
                "west": 90, "w": 90,
                "nord": 180, "n": 180,
                "suedost": -45, "südost": -45, "so": -45, "se": -45,
                "suedwest": 45, "südwest": 45, "sw": 45,
                "nordost": -135, "no": -135, "ne": -135,
                "nordwest": 135, "nw": 135,
            }
            ausrichtung = ausrichtung_map.get(ausrichtung.lower(), 0)

        strings.append(PVStringConfig(
            name=pv.bezeichnung or f"String {pv.id}",
            kwp=kwp,
            neigung=int(neigung),
            ausrichtung=int(ausrichtung),
        ))

    if not strings:
        raise HTTPException(
            status_code=400,
            detail="Keine PV-Module mit gültiger Leistung gefunden."
        )

    # Prüfe ob unterschiedliche Ausrichtungen
    unique_orientations = set((s.neigung, s.ausrichtung) for s in strings)
    has_multiple_orientations = len(unique_orientations) > 1

    if has_multiple_orientations and not pro_string:
        hinweise.append(
            f"Anlage hat {len(unique_orientations)} verschiedene Ausrichtungen. "
            "Für genauere Prognose 'pro_string=true' verwenden."
        )

    # Prognose berechnen
    if pro_string and has_multiple_orientations:
        # Separate Prognose pro String
        multi_result = await get_multi_string_prognose(
            latitude=anlage.latitude,
            longitude=anlage.longitude,
            strings=strings,
            days=tage,
            system_losses=system_losses,
        )

        if not multi_result:
            raise HTTPException(
                status_code=503,
                detail="Solar-Prognose konnte nicht abgerufen werden."
            )

        # Aggregierte Tageswerte erstellen
        string_prognosen = multi_result["string_prognosen"]
        tageswerte = []

        if string_prognosen:
            # Tage aus erstem String
            first_string = string_prognosen[0]["tageswerte"]
            for i, day in enumerate(first_string):
                total_ertrag = sum(
                    sp["tageswerte"][i]["pv_ertrag_kwh"]
                    for sp in string_prognosen
                    if i < len(sp["tageswerte"])
                )
                total_gti = sum(
                    sp["tageswerte"][i]["gti_kwh_m2"]
                    for sp in string_prognosen
                    if i < len(sp["tageswerte"])
                ) / len(string_prognosen)  # Durchschnitt

                tageswerte.append(SolarPrognoseTagSchema(
                    datum=day["datum"],
                    pv_ertrag_kwh=round(total_ertrag, 2),
                    gti_kwh_m2=round(total_gti, 2),
                    ghi_kwh_m2=0,  # Nicht für jeden String verfügbar
                    sonnenstunden=0,
                    temperatur_max_c=None,
                    temperatur_min_c=None,
                    bewoelkung_prozent=None,
                    niederschlag_mm=None,
                    schnee_cm=None,
                ))

        return SolarPrognoseResponse(
            anlage_id=anlage_id,
            anlagenname=anlage.anlagenname or f"Anlage {anlage_id}",
            kwp_gesamt=multi_result["kwp_gesamt"],
            neigung=multi_result["neigung_durchschnitt"],
            ausrichtung=multi_result["ausrichtung_durchschnitt"],
            system_losses_prozent=round(system_losses * 100, 1),
            prognose_zeitraum={
                "von": tageswerte[0].datum if tageswerte else None,
                "bis": tageswerte[-1].datum if tageswerte else None,
            },
            summe_kwh=multi_result["summe_kwh"],
            durchschnitt_kwh_tag=multi_result["durchschnitt_kwh_tag"],
            tageswerte=tageswerte,
            string_prognosen=[
                StringPrognoseSchema(**sp) for sp in string_prognosen
            ],
            datenquelle=multi_result["datenquelle"],
            abgerufen_am=multi_result["abgerufen_am"],
            hinweise=hinweise,
        )

    else:
        # Aggregierte Prognose (gewichtete Durchschnittswerte)
        total_kwp = sum(s.kwp for s in strings)
        avg_neigung = int(sum(s.neigung * s.kwp for s in strings) / total_kwp)
        avg_ausrichtung = int(sum(s.ausrichtung * s.kwp for s in strings) / total_kwp)

        prognose = await get_solar_prognose(
            latitude=anlage.latitude,
            longitude=anlage.longitude,
            kwp=total_kwp,
            neigung=avg_neigung,
            ausrichtung=avg_ausrichtung,
            days=tage,
            system_losses=system_losses,
        )

        if not prognose:
            raise HTTPException(
                status_code=503,
                detail="Solar-Prognose konnte nicht abgerufen werden."
            )

        return SolarPrognoseResponse(
            anlage_id=anlage_id,
            anlagenname=anlage.anlagenname or f"Anlage {anlage_id}",
            kwp_gesamt=prognose.kwp_gesamt,
            neigung=prognose.neigung,
            ausrichtung=prognose.ausrichtung,
            system_losses_prozent=prognose.system_losses_prozent,
            prognose_zeitraum=prognose.prognose_zeitraum,
            summe_kwh=prognose.summe_kwh,
            durchschnitt_kwh_tag=prognose.durchschnitt_kwh_tag,
            tageswerte=[
                SolarPrognoseTagSchema(
                    datum=t.datum,
                    pv_ertrag_kwh=t.pv_ertrag_kwh,
                    gti_kwh_m2=t.gti_kwh_m2,
                    ghi_kwh_m2=t.ghi_kwh_m2,
                    sonnenstunden=t.sonnenstunden,
                    temperatur_max_c=t.temperatur_max_c,
                    temperatur_min_c=t.temperatur_min_c,
                    bewoelkung_prozent=t.bewoelkung_prozent,
                    niederschlag_mm=t.niederschlag_mm,
                    schnee_cm=t.schnee_cm,
                )
                for t in prognose.tageswerte
            ],
            string_prognosen=None,
            datenquelle=prognose.datenquelle,
            abgerufen_am=prognose.abgerufen_am,
            hinweise=hinweise,
        )
