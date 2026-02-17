"""
Monatsabschluss API Routes.

Endpoints für den Monatsabschluss-Wizard:
- Vorschläge und Status für Monatsdaten
- Speichern mit Plausibilitätsprüfung
- MQTT-Integration
"""

import logging
from datetime import date, datetime
from typing import Optional, Any
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.attributes import flag_modified

from backend.core.database import get_db

logger = logging.getLogger(__name__)
from backend.models.anlage import Anlage
from backend.models.monatsdaten import Monatsdaten
from backend.models.investition import Investition, InvestitionMonatsdaten
from backend.services.vorschlag_service import VorschlagService, Vorschlag, VorschlagQuelle, PlausibilitaetsWarnung
from backend.services.ha_mqtt_sync import get_ha_mqtt_sync_service
from backend.services.ha_state_service import get_ha_state_service


router = APIRouter(prefix="/monatsabschluss", tags=["Monatsabschluss"])


# =============================================================================
# Pydantic Models
# =============================================================================

class VorschlagResponse(BaseModel):
    """Vorschlag für einen Feldwert."""
    wert: float
    quelle: str
    konfidenz: int
    beschreibung: str
    details: Optional[dict] = None


class WarnungResponse(BaseModel):
    """Plausibilitätswarnung."""
    typ: str
    schwere: str
    meldung: str
    details: Optional[dict] = None


class FeldStatus(BaseModel):
    """Status eines einzelnen Feldes."""
    feld: str
    label: str
    einheit: str
    aktueller_wert: Optional[float] = None
    quelle: Optional[str] = None  # ha_sensor, snapshot, manuell, berechnet
    vorschlaege: list[VorschlagResponse] = []
    warnungen: list[WarnungResponse] = []
    strategie: Optional[str] = None  # Aus sensor_mapping
    sensor_id: Optional[str] = None  # Wenn strategie=sensor


class InvestitionStatus(BaseModel):
    """Status einer Investition im Monatsabschluss."""
    id: int
    typ: str
    bezeichnung: str
    felder: list[FeldStatus]


class MonatsabschlussResponse(BaseModel):
    """Vollständiger Status für einen Monat."""
    anlage_id: int
    anlage_name: str
    jahr: int
    monat: int
    ist_abgeschlossen: bool
    ha_mapping_konfiguriert: bool

    # Basis-Felder (Zählerdaten)
    basis_felder: list[FeldStatus]

    # Investition-Felder
    investitionen: list[InvestitionStatus]


class FeldWert(BaseModel):
    """Wert für ein Feld."""
    feld: str
    wert: float


class InvestitionWerte(BaseModel):
    """Werte für eine Investition."""
    investition_id: int
    felder: list[FeldWert]


class MonatsabschlussInput(BaseModel):
    """Eingabedaten für den Monatsabschluss."""
    # Basis-Zählerdaten
    # HINWEIS: direktverbrauch_kwh wird automatisch berechnet (PV-Erzeugung - Einspeisung)
    einspeisung_kwh: Optional[float] = None
    netzbezug_kwh: Optional[float] = None
    globalstrahlung_kwh_m2: Optional[float] = None
    sonnenstunden: Optional[float] = None
    durchschnittstemperatur: Optional[float] = None
    sonderkosten_euro: Optional[float] = None
    sonderkosten_beschreibung: Optional[str] = None

    # Investitionen
    investitionen: list[InvestitionWerte] = []


class MonatsabschlussResult(BaseModel):
    """Ergebnis des Monatsabschlusses."""
    success: bool
    message: str
    monatsdaten_id: Optional[int] = None
    investition_monatsdaten_ids: list[int] = []
    warnungen: list[WarnungResponse] = []


class NaechsterMonatResponse(BaseModel):
    """Nächster unvollständiger Monat."""
    anlage_id: int
    anlage_name: str
    jahr: int
    monat: int
    monat_name: str
    ha_mapping_konfiguriert: bool


# =============================================================================
# Hilfsfunktionen
# =============================================================================

MONAT_NAMEN = [
    "", "Januar", "Februar", "März", "April", "Mai", "Juni",
    "Juli", "August", "September", "Oktober", "November", "Dezember"
]

# Basis-Felder Konfiguration
# HINWEIS: direktverbrauch_kwh wird berechnet (PV-Erzeugung - Einspeisung), daher NICHT hier
BASIS_FELDER = [
    {"feld": "einspeisung_kwh", "label": "Einspeisung", "einheit": "kWh", "mapping_key": "einspeisung"},
    {"feld": "netzbezug_kwh", "label": "Netzbezug", "einheit": "kWh", "mapping_key": "netzbezug"},
    {"feld": "globalstrahlung_kwh_m2", "label": "Globalstrahlung", "einheit": "kWh/m²", "mapping_key": "globalstrahlung"},
    {"feld": "sonnenstunden", "label": "Sonnenstunden", "einheit": "h", "mapping_key": "sonnenstunden"},
    {"feld": "durchschnittstemperatur", "label": "Ø Temperatur", "einheit": "°C", "mapping_key": "temperatur"},
]

# Investition-Felder nach Typ
INVESTITION_FELDER = {
    "pv-module": [
        {"feld": "pv_erzeugung_kwh", "label": "PV Erzeugung", "einheit": "kWh"},
    ],
    "speicher": [
        {"feld": "ladung_kwh", "label": "Ladung", "einheit": "kWh"},
        {"feld": "entladung_kwh", "label": "Entladung", "einheit": "kWh"},
        {"feld": "ladung_netz_kwh", "label": "Netzladung", "einheit": "kWh"},
    ],
    "waermepumpe": [
        {"feld": "stromverbrauch_kwh", "label": "Stromverbrauch", "einheit": "kWh"},
        {"feld": "heizenergie_kwh", "label": "Heizenergie", "einheit": "kWh"},
        {"feld": "warmwasser_kwh", "label": "Warmwasser", "einheit": "kWh"},
    ],
    "e-auto": [
        {"feld": "ladung_pv_kwh", "label": "Ladung PV", "einheit": "kWh"},
        {"feld": "ladung_netz_kwh", "label": "Ladung Netz", "einheit": "kWh"},
        {"feld": "km_gefahren", "label": "Gefahrene km", "einheit": "km"},
        {"feld": "v2h_entladung_kwh", "label": "V2H Entladung", "einheit": "kWh"},
    ],
    "wallbox": [
        {"feld": "ladung_kwh", "label": "Ladung gesamt", "einheit": "kWh"},
    ],
    "balkonkraftwerk": [
        {"feld": "pv_erzeugung_kwh", "label": "PV Erzeugung", "einheit": "kWh"},
        {"feld": "eigenverbrauch_kwh", "label": "Eigenverbrauch", "einheit": "kWh"},
    ],
}


def _vorschlag_to_response(v: Vorschlag) -> VorschlagResponse:
    """Konvertiert Vorschlag zu Response-Model."""
    return VorschlagResponse(
        wert=v.wert,
        quelle=v.quelle.value,
        konfidenz=v.konfidenz,
        beschreibung=v.beschreibung,
        details=v.details,
    )


def _warnung_to_response(w: PlausibilitaetsWarnung) -> WarnungResponse:
    """Konvertiert Warnung zu Response-Model."""
    return WarnungResponse(
        typ=w.typ,
        schwere=w.schwere,
        meldung=w.meldung,
        details=w.details,
    )


# =============================================================================
# API Endpoints
# =============================================================================

@router.get("/{anlage_id}/{jahr}/{monat}", response_model=MonatsabschlussResponse)
async def get_monatsabschluss(
    anlage_id: int,
    jahr: int,
    monat: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Gibt Status aller Felder für einen Monat zurück.

    Enthält:
    - Aktuelle Werte (falls vorhanden)
    - Vorschläge für fehlende/leere Felder
    - Plausibilitätswarnungen
    - Mapping-Informationen
    """
    # Anlage laden
    result = await db.execute(
        select(Anlage)
        .options(selectinload(Anlage.investitionen))
        .where(Anlage.id == anlage_id)
    )
    anlage = result.scalar_one_or_none()
    if not anlage:
        raise HTTPException(status_code=404, detail="Anlage nicht gefunden")

    vorschlag_service = VorschlagService(db)
    sensor_mapping = anlage.sensor_mapping or {}
    basis_mapping = sensor_mapping.get("basis", {})
    inv_mappings = sensor_mapping.get("investitionen", {})

    # Bestehende Monatsdaten laden
    md_result = await db.execute(
        select(Monatsdaten)
        .where(and_(
            Monatsdaten.anlage_id == anlage_id,
            Monatsdaten.jahr == jahr,
            Monatsdaten.monat == monat,
        ))
    )
    monatsdaten = md_result.scalar_one_or_none()

    # HA State Service für MQTT-Sensor-Vorschläge
    ha_state_service = get_ha_state_service()

    # Basis-Felder aufbereiten
    basis_felder: list[FeldStatus] = []
    for feld_config in BASIS_FELDER:
        feld = feld_config["feld"]
        aktueller_wert = getattr(monatsdaten, feld, None) if monatsdaten else None

        # Mapping-Info - verwende mapping_key aus der Konfiguration
        mapping_key = feld_config.get("mapping_key", feld)
        mapping_info = basis_mapping.get(mapping_key, {})
        strategie = mapping_info.get("strategie") if mapping_info else None
        sensor_id = mapping_info.get("sensor_id") if mapping_info else None

        # Vorschläge holen (historische Daten)
        vorschlaege = await vorschlag_service.get_vorschlaege(
            anlage_id, feld, jahr, monat
        )

        # Bei konfiguriertem Sensor: MQTT-Monatssensor-Wert als Vorschlag hinzufügen
        if strategie == "sensor" and sensor_mapping.get("mqtt_setup_complete"):
            mwd_wert = await ha_state_service.get_mwd_sensor_value(anlage_id, mapping_key)
            if mwd_wert is not None:
                # Als höchste Konfidenz einfügen (kommt aus Live-Sensor)
                vorschlaege.insert(0, Vorschlag(
                    wert=round(mwd_wert, 1),
                    quelle=VorschlagQuelle.HA_SENSOR,
                    konfidenz=95,
                    beschreibung="Aus HA-Sensor (aktueller Monatswert)",
                ))

        # Warnungen prüfen (nur wenn Wert vorhanden)
        warnungen = []
        if aktueller_wert is not None:
            warnungen = await vorschlag_service.pruefe_plausibilitaet(
                anlage_id, feld, aktueller_wert, jahr, monat
            )

        basis_felder.append(FeldStatus(
            feld=feld,
            label=feld_config["label"],
            einheit=feld_config["einheit"],
            aktueller_wert=aktueller_wert,
            quelle="manuell" if aktueller_wert is not None else None,
            vorschlaege=[_vorschlag_to_response(v) for v in vorschlaege],
            warnungen=[_warnung_to_response(w) for w in warnungen],
            strategie=strategie,
            sensor_id=sensor_id,
        ))

    # Investitionen aufbereiten
    investitionen_status: list[InvestitionStatus] = []
    for inv in anlage.investitionen:
        felder_config = INVESTITION_FELDER.get(inv.typ, [])
        if not felder_config:
            continue

        # InvestitionMonatsdaten laden
        imd_result = await db.execute(
            select(InvestitionMonatsdaten)
            .where(and_(
                InvestitionMonatsdaten.investition_id == inv.id,
                InvestitionMonatsdaten.jahr == jahr,
                InvestitionMonatsdaten.monat == monat,
            ))
        )
        imd = imd_result.scalar_one_or_none()
        verbrauch_daten = imd.verbrauch_daten if imd else {}

        # Mapping für diese Investition
        inv_mapping = inv_mappings.get(str(inv.id), {})

        felder: list[FeldStatus] = []
        for feld_config in felder_config:
            feld = feld_config["feld"]
            aktueller_wert = verbrauch_daten.get(feld)

            # Mapping-Info
            feld_mapping = inv_mapping.get(feld, {})
            strategie = feld_mapping.get("strategie") if feld_mapping else None
            sensor_id = feld_mapping.get("sensor_id") if feld_mapping else None

            # Vorschläge holen
            vorschlaege = await vorschlag_service.get_vorschlaege(
                anlage_id, feld, jahr, monat, investition_id=inv.id
            )

            # Warnungen prüfen
            warnungen = []
            if aktueller_wert is not None:
                warnungen = await vorschlag_service.pruefe_plausibilitaet(
                    anlage_id, feld, aktueller_wert, jahr, monat, inv.id
                )

            felder.append(FeldStatus(
                feld=feld,
                label=feld_config["label"],
                einheit=feld_config["einheit"],
                aktueller_wert=aktueller_wert,
                quelle="manuell" if aktueller_wert is not None else None,
                vorschlaege=[_vorschlag_to_response(v) for v in vorschlaege],
                warnungen=[_warnung_to_response(w) for w in warnungen],
                strategie=strategie,
                sensor_id=sensor_id,
            ))

        investitionen_status.append(InvestitionStatus(
            id=inv.id,
            typ=inv.typ,
            bezeichnung=inv.bezeichnung,
            felder=felder,
        ))

    return MonatsabschlussResponse(
        anlage_id=anlage_id,
        anlage_name=anlage.anlagenname,
        jahr=jahr,
        monat=monat,
        ist_abgeschlossen=monatsdaten is not None,
        ha_mapping_konfiguriert=sensor_mapping.get("mqtt_setup_complete", False),
        basis_felder=basis_felder,
        investitionen=investitionen_status,
    )


@router.post("/{anlage_id}/{jahr}/{monat}", response_model=MonatsabschlussResult)
async def save_monatsabschluss(
    anlage_id: int,
    jahr: int,
    monat: int,
    daten: MonatsabschlussInput,
    db: AsyncSession = Depends(get_db),
):
    """
    Speichert Monatsdaten.

    Ablauf:
    1. Validierung + Plausibilitätsprüfung
    2. Speichern in Monatsdaten + InvestitionMonatsdaten
    3. Optional: Startwerte für nächsten Monat auf MQTT publizieren
    """
    # Anlage laden
    result = await db.execute(
        select(Anlage).where(Anlage.id == anlage_id)
    )
    anlage = result.scalar_one_or_none()
    if not anlage:
        raise HTTPException(status_code=404, detail="Anlage nicht gefunden")

    vorschlag_service = VorschlagService(db)
    alle_warnungen: list[WarnungResponse] = []

    # Plausibilität prüfen
    for feld in ["einspeisung_kwh", "netzbezug_kwh"]:
        wert = getattr(daten, feld, None)
        if wert is not None:
            warnungen = await vorschlag_service.pruefe_plausibilitaet(
                anlage_id, feld, wert, jahr, monat
            )
            alle_warnungen.extend([_warnung_to_response(w) for w in warnungen])

    # Monatsdaten erstellen oder aktualisieren
    md_result = await db.execute(
        select(Monatsdaten)
        .where(and_(
            Monatsdaten.anlage_id == anlage_id,
            Monatsdaten.jahr == jahr,
            Monatsdaten.monat == monat,
        ))
    )
    monatsdaten = md_result.scalar_one_or_none()

    if not monatsdaten:
        monatsdaten = Monatsdaten(
            anlage_id=anlage_id,
            jahr=jahr,
            monat=monat,
        )
        db.add(monatsdaten)

    # Basis-Felder setzen
    if daten.einspeisung_kwh is not None:
        monatsdaten.einspeisung_kwh = daten.einspeisung_kwh
    if daten.netzbezug_kwh is not None:
        monatsdaten.netzbezug_kwh = daten.netzbezug_kwh
    # direktverbrauch_kwh wird automatisch berechnet (PV-Erzeugung - Einspeisung)
    # und nicht manuell eingegeben
    if daten.globalstrahlung_kwh_m2 is not None:
        monatsdaten.globalstrahlung_kwh_m2 = daten.globalstrahlung_kwh_m2
    if daten.sonnenstunden is not None:
        monatsdaten.sonnenstunden = daten.sonnenstunden
    if daten.durchschnittstemperatur is not None:
        monatsdaten.durchschnittstemperatur = daten.durchschnittstemperatur
    if daten.sonderkosten_euro is not None:
        monatsdaten.sonderkosten_euro = daten.sonderkosten_euro
    if daten.sonderkosten_beschreibung is not None:
        monatsdaten.sonderkosten_beschreibung = daten.sonderkosten_beschreibung

    await db.flush()
    monatsdaten_id = monatsdaten.id

    # Investition-Monatsdaten speichern
    inv_ids: list[int] = []
    for inv_werte in daten.investitionen:
        # Bestehenden Datensatz suchen oder neu erstellen
        imd_result = await db.execute(
            select(InvestitionMonatsdaten)
            .where(and_(
                InvestitionMonatsdaten.investition_id == inv_werte.investition_id,
                InvestitionMonatsdaten.jahr == jahr,
                InvestitionMonatsdaten.monat == monat,
            ))
        )
        imd = imd_result.scalar_one_or_none()

        if not imd:
            imd = InvestitionMonatsdaten(
                investition_id=inv_werte.investition_id,
                monatsdaten_id=monatsdaten_id,
                jahr=jahr,
                monat=monat,
                verbrauch_daten={},
            )
            db.add(imd)

        # Felder in verbrauch_daten speichern
        verbrauch_daten = imd.verbrauch_daten or {}
        for feld_wert in inv_werte.felder:
            verbrauch_daten[feld_wert.feld] = feld_wert.wert

        imd.verbrauch_daten = verbrauch_daten
        flag_modified(imd, "verbrauch_daten")

        await db.flush()
        inv_ids.append(imd.id)

    await db.commit()

    # Optional: MQTT Monatsdaten publizieren
    mqtt_sync = get_ha_mqtt_sync_service()
    try:
        monatsdaten_dict = {
            "jahr": jahr,
            "monat": monat,
            "einspeisung_kwh": daten.einspeisung_kwh,
            "netzbezug_kwh": daten.netzbezug_kwh,
        }
        await mqtt_sync.publish_final_month_data(anlage_id, jahr, monat, monatsdaten_dict)
    except Exception as e:
        # MQTT-Fehler nicht als Fatal behandeln
        logger.warning(f"MQTT-Publish fehlgeschlagen: {e}")

    return MonatsabschlussResult(
        success=True,
        message=f"Monatsdaten für {MONAT_NAMEN[monat]} {jahr} gespeichert",
        monatsdaten_id=monatsdaten_id,
        investition_monatsdaten_ids=inv_ids,
        warnungen=alle_warnungen,
    )


@router.get("/naechster/{anlage_id}", response_model=Optional[NaechsterMonatResponse])
async def get_naechster_monat(
    anlage_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Findet den nächsten unvollständigen Monat.

    Rückgabe:
    - Nächster Monat nach dem letzten vollständigen
    - Oder aktueller Monat wenn vergangen und nicht vollständig
    """
    # Anlage laden
    result = await db.execute(
        select(Anlage).where(Anlage.id == anlage_id)
    )
    anlage = result.scalar_one_or_none()
    if not anlage:
        raise HTTPException(status_code=404, detail="Anlage nicht gefunden")

    heute = date.today()

    # Letzten vollständigen Monat finden
    md_result = await db.execute(
        select(Monatsdaten)
        .where(Monatsdaten.anlage_id == anlage_id)
        .order_by(Monatsdaten.jahr.desc(), Monatsdaten.monat.desc())
        .limit(1)
    )
    letzter = md_result.scalar_one_or_none()

    if letzter:
        # Nächster Monat nach dem letzten
        if letzter.monat == 12:
            naechster_jahr = letzter.jahr + 1
            naechster_monat = 1
        else:
            naechster_jahr = letzter.jahr
            naechster_monat = letzter.monat + 1
    else:
        # Kein Monat vorhanden - vorherigen Monat vorschlagen
        if heute.month == 1:
            naechster_jahr = heute.year - 1
            naechster_monat = 12
        else:
            naechster_jahr = heute.year
            naechster_monat = heute.month - 1

    # Nur zurückgeben wenn Monat in der Vergangenheit liegt
    monat_ende = date(naechster_jahr, naechster_monat + 1 if naechster_monat < 12 else 1, 1)
    if naechster_monat == 12:
        monat_ende = date(naechster_jahr + 1, 1, 1)

    if heute < monat_ende:
        # Monat ist noch nicht vorbei
        return None

    sensor_mapping = anlage.sensor_mapping or {}

    return NaechsterMonatResponse(
        anlage_id=anlage_id,
        anlage_name=anlage.anlagenname,
        jahr=naechster_jahr,
        monat=naechster_monat,
        monat_name=MONAT_NAMEN[naechster_monat],
        ha_mapping_konfiguriert=sensor_mapping.get("mqtt_setup_complete", False),
    )


@router.get("/historie/{anlage_id}")
async def get_monatsabschluss_historie(
    anlage_id: int,
    limit: int = 12,
    db: AsyncSession = Depends(get_db),
):
    """
    Gibt Historie der letzten Monatsabschlüsse zurück.

    Returns:
        Liste der letzten {limit} Monatsdaten
    """
    result = await db.execute(
        select(Monatsdaten)
        .where(Monatsdaten.anlage_id == anlage_id)
        .order_by(Monatsdaten.jahr.desc(), Monatsdaten.monat.desc())
        .limit(limit)
    )
    monatsdaten = result.scalars().all()

    return [
        {
            "id": md.id,
            "jahr": md.jahr,
            "monat": md.monat,
            "monat_name": MONAT_NAMEN[md.monat],
            "einspeisung_kwh": md.einspeisung_kwh,
            "netzbezug_kwh": md.netzbezug_kwh,
        }
        for md in monatsdaten
    ]
