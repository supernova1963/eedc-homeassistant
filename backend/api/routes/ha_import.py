"""
Home Assistant Import Routes

HINWEIS: Diese Datei wurde in v0.9.9 stark vereinfacht.

Die komplexe HA-Integration (YAML-Generator, Template-Sensoren, Automations)
wurde entfernt zugunsten einer Standalone-fokussierten Architektur.

EEDC funktioniert primär ohne Home Assistant:
- Monatsdaten per CSV-Import oder manuelles Formular erfassen
- Optional: MQTT Export für berechnete KPIs nach HA

Was bleibt:
- Basis-Endpunkte für eventuelle zukünftige HA-Integration
- Investitions-Feld-Definitionen (werden auch für CSV-Template genutzt)
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_db
from backend.models.anlage import Anlage
from backend.models.investition import Investition

logger = logging.getLogger(__name__)

router = APIRouter()


# =============================================================================
# Pydantic Schemas (vereinfacht)
# =============================================================================

class SensorFeld(BaseModel):
    """Ein erwartetes Feld für einen Investitionstyp."""
    key: str
    label: str
    unit: str
    required: bool = False
    optional: bool = False
    hint: str | None = None


class InvestitionMitFeldern(BaseModel):
    """Investition mit den erwarteten Feldern für Monatsdaten."""
    id: int
    bezeichnung: str
    typ: str
    felder: list[SensorFeld]


# =============================================================================
# Feld-Definitionen pro Investitionstyp
# =============================================================================

def get_felder_fuer_typ(typ: str, parameter: dict | None = None) -> list[SensorFeld]:
    """
    Gibt die erwarteten Felder für einen Investitionstyp zurück.

    Diese Definitionen werden verwendet für:
    - CSV-Template Generierung
    - Monatsdaten-Formular
    """

    if typ == "e-auto":
        felder = [
            SensorFeld(key="km_gefahren", label="Gefahrene km", unit="km"),
            SensorFeld(key="verbrauch_kwh", label="Verbrauch", unit="kWh", optional=True),
            SensorFeld(key="ladung_pv_kwh", label="Ladung aus PV", unit="kWh"),
            SensorFeld(key="ladung_netz_kwh", label="Ladung aus Netz", unit="kWh"),
            SensorFeld(key="ladung_extern_kwh", label="Externe Ladung", unit="kWh", optional=True, hint="Öffentliche Ladesäulen"),
            SensorFeld(key="ladung_extern_euro", label="Externe Kosten", unit="€", optional=True),
        ]
        if parameter and (parameter.get("nutzt_v2h") or parameter.get("v2h_faehig")):
            felder.append(SensorFeld(key="v2h_entladung_kwh", label="V2H Entladung", unit="kWh", optional=True))
        return felder

    elif typ == "speicher":
        felder = [
            SensorFeld(key="ladung_kwh", label="Ladung", unit="kWh", required=True),
            SensorFeld(key="entladung_kwh", label="Entladung", unit="kWh", required=True),
        ]
        if parameter and parameter.get("arbitrage_faehig"):
            felder.extend([
                SensorFeld(key="speicher_ladung_netz_kwh", label="Netzladung", unit="kWh", optional=True, hint="Arbitrage"),
                SensorFeld(key="speicher_ladepreis_cent", label="Ø Ladepreis", unit="ct/kWh", optional=True),
            ])
        return felder

    elif typ == "wallbox":
        return [
            SensorFeld(key="ladung_kwh", label="Heimladung", unit="kWh", required=True),
            SensorFeld(key="ladevorgaenge", label="Ladevorgänge", unit="Anzahl", optional=True),
        ]

    elif typ == "waermepumpe":
        return [
            SensorFeld(key="stromverbrauch_kwh", label="Stromverbrauch", unit="kWh", required=True),
            SensorFeld(key="heizenergie_kwh", label="Heizenergie", unit="kWh", optional=True),
            SensorFeld(key="warmwasser_kwh", label="Warmwasser", unit="kWh", optional=True),
        ]

    elif typ == "pv-module":
        return [
            SensorFeld(key="pv_erzeugung_kwh", label="Erzeugung", unit="kWh", required=True),
        ]

    elif typ == "balkonkraftwerk":
        felder = [
            SensorFeld(key="pv_erzeugung_kwh", label="Erzeugung", unit="kWh", required=True),
        ]
        if parameter and parameter.get("hat_speicher"):
            felder.extend([
                SensorFeld(key="speicher_ladung_kwh", label="Speicher Ladung", unit="kWh", optional=True),
                SensorFeld(key="speicher_entladung_kwh", label="Speicher Entladung", unit="kWh", optional=True),
            ])
        return felder

    elif typ == "sonstiges":
        kategorie = parameter.get("kategorie", "erzeuger") if parameter else "erzeuger"
        if kategorie == "erzeuger":
            return [SensorFeld(key="erzeugung_kwh", label="Erzeugung", unit="kWh", required=True)]
        elif kategorie == "verbraucher":
            return [SensorFeld(key="verbrauch_kwh", label="Verbrauch", unit="kWh", required=True)]
        elif kategorie == "speicher":
            return [
                SensorFeld(key="ladung_kwh", label="Ladung", unit="kWh"),
                SensorFeld(key="entladung_kwh", label="Entladung", unit="kWh"),
            ]

    return []


# =============================================================================
# Endpoints
# =============================================================================

@router.get("/investitionen/{anlage_id}", response_model=list[InvestitionMitFeldern])
async def get_investitionen_mit_feldern(
    anlage_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Gibt alle aktiven Investitionen einer Anlage mit den erwarteten Feldern zurück.

    Wird verwendet für:
    - CSV-Template Generierung
    - Monatsdaten-Formular
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
        InvestitionMitFeldern(
            id=inv.id,
            bezeichnung=inv.bezeichnung,
            typ=inv.typ,
            felder=get_felder_fuer_typ(inv.typ, inv.parameter),
        )
        for inv in investitionen
    ]
