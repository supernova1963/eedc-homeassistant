"""
HA Statistics API Routes

Endpoints für den Zugriff auf Home Assistant Langzeitstatistiken.

Ermöglicht:
- Monatswerte für einen bestimmten Monat abrufen
- Alle verfügbaren Monate ermitteln
- Bulk-Import aller historischen Monatswerte
- MQTT-Startwerte initialisieren
"""

import logging
from datetime import date
from typing import Optional, Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified
from pydantic import BaseModel

from backend.core.exceptions import bad_request, ha_db_unavailable, not_found
from backend.api.deps import get_db
from backend.services.activity_service import log_activity
from backend.core.field_definitions import FELD_LABELS as _FELD_LABELS_REGISTRY
from backend.core.field_definitions import ist_heimlade_mengen_feld, ist_zaehler_differenz_feld
from backend.models.anlage import Anlage
from backend.models.monatsdaten import Monatsdaten
from backend.models.investition import Investition, InvestitionMonatsdaten
from backend.services.ha_statistics_service import (
    get_ha_statistics_service,
    MonatswertResponse,
    AlleMonateResponse,
    SensorMonatswert,
)
from backend.services.import_hauszaehler import warnung_monate_ohne_zaehlerwerte
from backend.services.monatswert_deckel import deckel_je_sensor
from backend.core.berechnungen.erzeuger_traeger import erzeuger_traeger
from backend.core.berechnungen.pv_verteilung import PvModul, QUELLE_GEMESSEN, resolve_pv_je_modul
from backend.services.pv_monatswerte import eigene_bkw_erzeugung_kwh, lade_pv_je_monat, pv_summe_je_monat
from backend.core.investition_kennwerte import get_pv_kwp
from backend.services.provenance import ABGELEITET_KWP_ANTEIL
from backend.services.provenance import (
    seed_provenance,
    write_json_subkey_with_provenance,
    write_with_provenance,
)

logger = logging.getLogger(__name__)

# HA Long-Term Statistics ist eine externe autoritative Quelle
# (Source `external:ha_statistics`, Stufe 2). Manuelle Form-Werte (Stufe 1)
# überleben den Import strukturell — der Resolver weist HA-Stats-
# Schreibversuche auf manual:form-Felder mit rejected_lower_priority ab.
_HA_STATS_SOURCE = "external:ha_statistics"
_HA_STATS_WRITER = "ha_statistics_import"

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


class InvestitionMitFelder(BaseModel):
    """Investition mit zugehörigen Feld-Werten."""
    investition_id: int
    bezeichnung: str
    typ: str
    felder: list[MappedMonatswert]


class AnlagenMonatswertResponse(BaseModel):
    """Monatswerte für eine Anlage mit Feld-Zuordnung."""
    anlage_id: int
    anlage_name: str
    jahr: int
    monat: int
    monat_name: str
    basis: list[MappedMonatswert]
    investitionen: list[InvestitionMitFelder]  # Liste von Investitionen mit Feldern


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
    db_typ: Optional[str] = None
    anzahl_sensoren: Optional[int] = None
    hinweis: str


# =============================================================================
# Mapping: sensor_mapping-Key → DB-Feldname (für Monatsabschluss-Kompatibilität)
# sensor_mapping nutzt Kurzformen ("einspeisung"), DB hat "einspeisung_kwh"
# =============================================================================

MAPPING_KEY_TO_DB_FELD = {
    "einspeisung": "einspeisung_kwh",
    "netzbezug": "netzbezug_kwh",
    "globalstrahlung": "globalstrahlung_kwh_m2",
    "sonnenstunden": "sonnenstunden",
    "temperatur": "durchschnittstemperatur",
}


# =============================================================================
# Feld-Labels für bessere Lesbarkeit
# =============================================================================

# FELD_LABELS aus field_definitions-Registry abgeleitet — kein hardcodierter Block mehr.
FELD_LABELS = _FELD_LABELS_REGISTRY


# =============================================================================
# Helper Functions
# =============================================================================

async def get_anlage_with_mapping(db: AsyncSession, anlage_id: int) -> Anlage:
    """Holt Anlage und prüft ob sensor_mapping vorhanden."""
    result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    anlage = result.scalar_one_or_none()

    if not anlage:
        raise not_found("Anlage", anlage_id)

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
    sensoren: list[SensorMonatswert],
    investitionen_db: dict[int, "Investition"] = None
) -> tuple[list[MappedMonatswert], list[InvestitionMitFelder]]:
    """
    Ordnet Sensorwerte den EEDC-Feldern zu.

    Args:
        sensor_mapping: Sensor-Mapping der Anlage
        sensoren: Sensor-Monatswerte aus HA
        investitionen_db: Dict von Investition-ID zu Investition-Objekt

    Returns:
        Tuple von (basis_felder, investitions_liste)
    """
    # Sensor-Werte als Dict für schnellen Zugriff
    sensor_values = {s.sensor_id: s for s in sensoren}

    basis_felder: list[MappedMonatswert] = []
    inv_liste: list[InvestitionMitFelder] = []

    # Basis-Felder
    basis = sensor_mapping.get("basis", {})
    for mapping_key, config in basis.items():
        if config and config.get("strategie") == "sensor":
            sensor_id = config.get("sensor_id")
            if sensor_id and sensor_id in sensor_values:
                sv = sensor_values[sensor_id]
                # mapping_key ("einspeisung") → DB-Feldname ("einspeisung_kwh")
                db_feld = MAPPING_KEY_TO_DB_FELD.get(mapping_key, mapping_key)
                basis_felder.append(MappedMonatswert(
                    feld=db_feld,
                    feld_label=FELD_LABELS.get(mapping_key, mapping_key),
                    sensor_id=sensor_id,
                    start_wert=sv.start_wert,
                    end_wert=sv.end_wert,
                    differenz=sv.differenz,
                    einheit=sv.einheit
                ))

    # Investitions-Felder
    investitionen = sensor_mapping.get("investitionen", {})
    for inv_id_str, inv_config in investitionen.items():
        inv_id = int(inv_id_str)
        felder_config = inv_config.get("felder", {})
        felder: list[MappedMonatswert] = []

        for feld, config in felder_config.items():
            if config and config.get("strategie") == "sensor":
                sensor_id = config.get("sensor_id")
                if sensor_id and sensor_id in sensor_values:
                    sv = sensor_values[sensor_id]
                    felder.append(MappedMonatswert(
                        feld=feld,
                        feld_label=FELD_LABELS.get(feld, feld),
                        sensor_id=sensor_id,
                        start_wert=sv.start_wert,
                        end_wert=sv.end_wert,
                        differenz=sv.differenz,
                        einheit=sv.einheit
                    ))

        # Investitions-Metadaten aus DB holen
        bezeichnung = f"Investition {inv_id}"
        typ = ""
        if investitionen_db and inv_id in investitionen_db:
            inv = investitionen_db[inv_id]
            bezeichnung = inv.bezeichnung or bezeichnung
            typ = inv.typ or ""

        if felder:  # Nur hinzufügen wenn Felder vorhanden
            inv_liste.append(InvestitionMitFelder(
                investition_id=inv_id,
                bezeichnung=bezeichnung,
                typ=typ,
                felder=felder
            ))

    return basis_felder, inv_liste


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
        anzahl = service.count_statistics_sensors()
        db_typ = service.backend_type
        if anzahl == 0:
            hinweis = (
                f"HA-Datenbank verbunden ({db_typ}), aber keine Statistik-Daten gefunden. "
                f"Ist der HA Recorder auf diese Datenbank konfiguriert?"
            )
        else:
            hinweis = f"HA-Datenbank verbunden ({db_typ}), {anzahl} Sensoren mit Statistik-Daten."
        return StatusResponse(
            verfuegbar=True,
            db_pfad=str(service.db_path),
            db_typ=db_typ,
            anzahl_sensoren=anzahl,
            hinweis=hinweis,
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
        raise bad_request("Monat muss zwischen 1 und 12 liegen")

    service = get_ha_statistics_service()
    if not service.is_available:
        raise ha_db_unavailable()

    anlage = await get_anlage_with_mapping(db, anlage_id)
    sensor_ids = extract_sensor_ids_from_mapping(anlage.sensor_mapping)

    if not sensor_ids:
        raise HTTPException(
            status_code=400,
            detail="Keine Sensor-Zuordnungen mit Strategie 'sensor' gefunden."
        )

    # Investitionen für Metadaten laden
    inv_result = await db.execute(
        select(Investition).where(Investition.anlage_id == anlage_id)
    )
    investitionen_db = {inv.id: inv for inv in inv_result.scalars().all()}

    # Werte aus HA-DB holen
    try:
        response = service.get_monatswerte(
            sensor_ids, jahr, monat,
            deckel_je_sensor=deckel_je_sensor(anlage, investitionen_db.values()),
        )
    except Exception as e:
        await log_activity(
            kategorie="ha_statistics",
            aktion=f"Monatswerte {monat:02d}/{jahr} fehlgeschlagen",
            erfolg=False,
            details=f"{type(e).__name__}: {e}",
            anlage_id=anlage_id,
            db=db,
        )
        raise HTTPException(status_code=500, detail=f"Fehler bei DB-Abfrage: {e}")

    # Auf EEDC-Felder mappen
    basis_felder, inv_liste = map_sensor_values_to_fields(
        anlage.sensor_mapping,
        response.sensoren,
        investitionen_db
    )

    return AnlagenMonatswertResponse(
        anlage_id=anlage.id,
        anlage_name=anlage.anlagenname,
        jahr=jahr,
        monat=monat,
        monat_name=response.monat_name,
        basis=basis_felder,
        investitionen=inv_liste
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
        raise ha_db_unavailable()

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
        raise ha_db_unavailable()

    anlage = await get_anlage_with_mapping(db, anlage_id)
    sensor_ids = extract_sensor_ids_from_mapping(anlage.sensor_mapping)

    if not sensor_ids:
        raise HTTPException(
            status_code=400,
            detail="Keine Sensor-Zuordnungen mit Strategie 'sensor' gefunden."
        )

    # Investitionen für Metadaten laden
    inv_result = await db.execute(
        select(Investition).where(Investition.anlage_id == anlage_id)
    )
    investitionen_db = {inv.id: inv for inv in inv_result.scalars().all()}

    # Ab-Datum berechnen
    ab_datum = None
    if ab_jahr:
        ab_datum = date(ab_jahr, ab_monat or 1, 1)

    try:
        raw_responses = service.get_alle_monatswerte(
            sensor_ids, ab_datum,
            deckel_je_sensor=deckel_je_sensor(anlage, investitionen_db.values()),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"HA-Statistik-Abfrage fehlgeschlagen: {type(e).__name__}: {e}")
        raise HTTPException(status_code=500, detail=f"Fehler bei DB-Abfrage: {e}")

    # Auf EEDC-Felder mappen
    ergebnisse = []
    for raw in raw_responses:
        basis_felder, inv_liste = map_sensor_values_to_fields(
            anlage.sensor_mapping,
            raw.sensoren,
            investitionen_db
        )

        ergebnisse.append(AnlagenMonatswertResponse(
            anlage_id=anlage.id,
            anlage_name=anlage.anlagenname,
            jahr=raw.jahr,
            monat=raw.monat,
            monat_name=raw.monat_name,
            basis=basis_felder,
            investitionen=inv_liste
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
        raise bad_request("Monat muss zwischen 1 und 12 liegen")

    service = get_ha_statistics_service()
    if not service.is_available:
        raise ha_db_unavailable()

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

class InvestitionImportStatus(BaseModel):
    """Status einer Investition im Import-Vergleich."""
    investition_id: int
    bezeichnung: str
    typ: str
    ha_werte: dict  # {"pv_erzeugung_kwh": 123.4, ...}
    vorhandene_werte: dict  # {"pv_erzeugung_kwh": 100.0, ...}
    hat_abweichung: bool


class MonatImportStatus(BaseModel):
    """Status eines Monats für den Import."""
    jahr: int
    monat: int
    monat_name: str
    aktion: Literal["importieren", "ueberspringen", "ueberschreiben", "konflikt"]
    grund: str
    ha_werte: dict  # {"einspeisung": 123.4, "netzbezug": 56.7, ...}
    vorhandene_werte: Optional[dict] = None  # Falls Daten existieren
    investitionen: Optional[list[InvestitionImportStatus]] = None  # Komponenten-Vergleich


class ImportVorschauResponse(BaseModel):
    """Vorschau für den Import mit Konflikt-Erkennung."""
    anlage_id: int
    anlage_name: str
    anzahl_monate: int
    anzahl_importieren: int
    anzahl_ueberspringen: int
    anzahl_konflikte: int
    monate: list[MonatImportStatus]


class MonatFeldAuswahl(BaseModel):
    """Auswahl der zu importierenden Felder für einen Monat."""
    jahr: int
    monat: int
    # Basis-Felder: Liste der Feld-Namen die importiert werden sollen
    basis_felder: Optional[list[str]] = None  # None = alle, [] = keine
    # Investitions-Felder: Dict von inv_id -> Liste der Feld-Namen
    investition_felder: Optional[dict[str, list[str]]] = None  # None = alle, {} = keine


class ImportRequest(BaseModel):
    """Request für den Import."""
    monate: list[MonatFeldAuswahl]  # Detaillierte Auswahl pro Monat
    ueberschreiben: bool = False  # Auch vorhandene Daten überschreiben


class ImportResultat(BaseModel):
    """Ergebnis des Imports."""
    erfolg: bool
    importiert: int
    uebersprungen: int
    ueberschrieben: int
    fehler: list[str]
    #: N-240: Sachverhalte, die kein Fehler sind, aber Folgen haben — heute genau
    #: einer: Monate, in denen nur Gerätewerte entstanden (keine Zählerzeile).
    #: Getrennt von `fehler`, weil der Lauf erfolgreich war: `erfolg` bleibt True.
    warnungen: list[str] = []


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
        raise ha_db_unavailable()

    anlage = await get_anlage_with_mapping(db, anlage_id)
    sensor_ids = extract_sensor_ids_from_mapping(anlage.sensor_mapping)

    if not sensor_ids:
        raise HTTPException(
            status_code=400,
            detail="Keine Sensor-Zuordnungen mit Strategie 'sensor' gefunden."
        )

    # Alle HA-Monatswerte holen — Zählerlücken wie HA (Vorlage §10): der Monat
    # verwirft, was die Stunden verwerfen (Rücksprung; Deckel für PV/Einspeisung).
    _deckel = deckel_je_sensor(anlage, (await db.execute(
        select(Investition).where(Investition.anlage_id == anlage_id)
    )).scalars().all())
    try:
        ha_monate = service.get_alle_monatswerte(sensor_ids, deckel_je_sensor=_deckel)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"HA-Statistik-Abfrage fehlgeschlagen: {type(e).__name__}: {e}")
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

    # N-533: der lokale PV-Gesamtwert je Monat für den Vergleich mit dem Anlagen-Zähler
    # (`basis.pv_gesamt`) — über die P7-Auflösung (`lade_pv_je_monat`), nicht über die
    # Rohspalte: Messwerte je Modul plus Aggregat-Lückenfüllung, `None` bei Unvollständigkeit.
    pv_summen: dict[tuple[int, int], Optional[float]] = {}
    if ((anlage.sensor_mapping.get("basis") or {}).get("pv_gesamt") or {}).get("sensor_id"):
        pv_module_der_anlage = [inv for inv in investitionen.values() if inv.typ == "pv-module"]
        pv_summen = pv_summe_je_monat(await lade_pv_je_monat(
            db, anlage_id, pv_module_der_anlage, investitionen=list(investitionen.values()),
        ))
        # N-611: der Anlagen-PV-Zähler misst ALLE PV-Quellen — verglichen wird er deshalb mit
        # Module + eigenem Wert der selbst tragenden Balkonkraftwerke, also mit derselben Zahl,
        # die die Monats-Fakten nennen (`pv_kwh = Module + BKW`). Nur Module verglichen, meldete
        # die Vorschau nach jedem korrekten Import einen Konflikt in Höhe des BKW-Werts. Ein
        # unvollständiger Monat (`None`) bleibt „fehlt lokal“ — ein BKW-Wert macht ihn nicht voll.
        for (j, m), summe in pv_summen.items():
            if summe is None:
                continue
            aktive = [inv for inv in investitionen.values() if inv.ist_aktiv_im_monat(j, m)]
            pv_summen[(j, m)] = summe + eigene_bkw_erzeugung_kwh(aktive, {
                inv.id: vorhandene_imd[(inv.id, j, m)].verbrauch_daten
                for inv in aktive if (inv.id, j, m) in vorhandene_imd
            })

    # Jeden Monat analysieren
    monate_status: list[MonatImportStatus] = []
    anzahl_importieren = 0
    anzahl_ueberspringen = 0
    anzahl_konflikte = 0

    for ha_monat in ha_monate:
        jahr = ha_monat.jahr
        monat = ha_monat.monat

        # HA-Werte extrahieren (Basis)
        ha_basis_werte = {}
        for sensor in ha_monat.sensoren:
            # Sensor-ID zu Feld-Name mappen
            for basis_feld, basis_config in (anlage.sensor_mapping.get("basis") or {}).items():
                # `basis` trägt neben den Zählern auch den Strompreis-Sensor;
                # dessen Monats-Differenz ist eine Preis-Spreizung, kein Wert.
                if not ist_zaehler_differenz_feld(basis_feld):
                    continue
                if basis_config and basis_config.get("sensor_id") == sensor.sensor_id:
                    ha_basis_werte[basis_feld] = sensor.differenz

        # Investitions-Werte pro Investition sammeln
        ha_inv_werte: dict[str, dict] = {}  # inv_id -> {feld: wert}
        for inv_id, inv_config in (anlage.sensor_mapping.get("investitionen") or {}).items():
            felder = inv_config.get("felder", {})
            ha_inv_werte[inv_id] = {}
            for feld, feld_config in felder.items():
                # Nur Zählerfelder — s. Import-Pfad weiter unten. Die Vorschau
                # muss dieselbe Menge zeigen wie der Import schreibt, sonst
                # steht dort ein Wert, der nie ankommt.
                if not ist_zaehler_differenz_feld(feld):
                    continue
                if feld_config and feld_config.get("sensor_id"):
                    for sensor in ha_monat.sensoren:
                        if sensor.sensor_id == feld_config["sensor_id"]:
                            ha_inv_werte[inv_id][feld] = sensor.differenz

        # Prüfen ob Monatsdaten existieren
        md = vorhandene_md.get((jahr, monat))

        # Investitionen-Vergleich erstellen
        inv_status_liste: list[InvestitionImportStatus] = []
        inv_hat_abweichung = False

        for inv_id_str, ha_felder in ha_inv_werte.items():
            if not ha_felder:
                continue

            inv = investitionen.get(inv_id_str)
            if not inv:
                # Verwaister sensor_mapping-Eintrag (Investition gelöscht) → überspringen
                continue
            inv_id = inv.id
            bezeichnung = inv.bezeichnung
            typ = inv.typ

            # Vorhandene Werte für diese Investition
            imd = vorhandene_imd.get((inv_id, jahr, monat))
            vorh_felder = {}
            if imd and imd.verbrauch_daten:
                vorh_felder = {k: v for k, v in imd.verbrauch_daten.items() if v is not None}

            # Abweichung prüfen (mit Labels für Anzeige)
            ha_mit_labels = {FELD_LABELS.get(k, k): v for k, v in ha_felder.items()}
            vorh_mit_labels = {FELD_LABELS.get(k, k): vorh_felder.get(k) for k in ha_felder.keys()}

            hat_abw = False
            for feld, ha_wert in ha_felder.items():
                vorh_wert = vorh_felder.get(feld, 0) or 0
                if abs(ha_wert - vorh_wert) >= 1:
                    hat_abw = True
                    inv_hat_abweichung = True
                    break

            inv_status_liste.append(InvestitionImportStatus(
                investition_id=inv_id,
                bezeichnung=bezeichnung,
                typ=typ,
                ha_werte=ha_mit_labels,
                vorhandene_werte=vorh_mit_labels,
                hat_abweichung=hat_abw
            ))

        # Anzeige-Versionen mit Labels (detLAN #187/1: Roh-Keys "einspeisung"
        # → "Einspeisung"). Raw-Variante bleibt für interne Vergleichs-Logik.
        ha_basis_anzeige = {FELD_LABELS.get(k, k): v for k, v in ha_basis_werte.items()}

        if md is None:
            # Keine Daten vorhanden → Importieren
            monate_status.append(MonatImportStatus(
                jahr=jahr,
                monat=monat,
                monat_name=ha_monat.monat_name,
                aktion="importieren",
                grund="Keine Monatsdaten vorhanden",
                ha_werte=ha_basis_anzeige,
                vorhandene_werte=None,
                investitionen=inv_status_liste if inv_status_liste else None
            ))
            anzahl_importieren += 1
        else:
            # Daten existieren - prüfen ob leer oder mit Werten
            vorhandene_werte = {
                "einspeisung": md.einspeisung_kwh,
                "netzbezug": md.netzbezug_kwh,
            }
            if "pv_gesamt" in ha_basis_werte:
                # N-533: sonst stünde „Vorhanden –“ neben einem HA-Wert, ohne jede Folge.
                vorhandene_werte["pv_gesamt"] = pv_summen.get((jahr, monat))
            vorhandene_anzeige = {FELD_LABELS.get(k, k): v for k, v in vorhandene_werte.items()}

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
                    ha_werte=ha_basis_anzeige,
                    vorhandene_werte=vorhandene_anzeige,
                    investitionen=inv_status_liste if inv_status_liste else None
                ))
                anzahl_importieren += 1
            else:
                # Daten existieren mit Werten — Abweichung? N-533 (Frank85): JEDES
                # Basis-Zählerfeld des Mappings zählt, nicht nur Einspeisung und
                # Netzbezug. Ein Feld mit HA-Wert und ohne lokalen Wert (der
                # Anlagen-PV-Zähler bei 40 Monaten) ist kein „stimmt überein“,
                # sondern ein Import — vorher ging genau das im Δ-Vergleich der
                # zwei Zählerfelder unter, und der Monat blieb ohne PV.
                fehlende: list[str] = []
                abweichende: list[str] = []
                for feld, ha_wert in ha_basis_werte.items():
                    if ha_wert is None:
                        continue
                    vorh = vorhandene_werte.get(feld)
                    label = FELD_LABELS.get(feld, feld)
                    if vorh is None:
                        fehlende.append(label)
                    elif abs(ha_wert - vorh) >= 1:
                        abweichende.append(f"{label} {abs(ha_wert - vorh):.1f}")

                if not fehlende and not abweichende and not inv_hat_abweichung:
                    aktion, grund = "ueberspringen", "Daten stimmen überein (Δ < 1)"
                    anzahl_ueberspringen += 1
                elif abweichende or inv_hat_abweichung:
                    grund_teile = []
                    if abweichende:
                        grund_teile.append("Basis: " + ", ".join(abweichende))
                    if fehlende:
                        grund_teile.append("fehlt lokal: " + ", ".join(fehlende))
                    if inv_hat_abweichung:
                        grund_teile.append("Komponenten-Werte weichen ab")
                    aktion, grund = "konflikt", " | ".join(grund_teile)
                    anzahl_konflikte += 1
                else:
                    aktion, grund = "importieren", "Fehlt lokal: " + ", ".join(fehlende)
                    anzahl_importieren += 1
                monate_status.append(MonatImportStatus(
                    jahr=jahr,
                    monat=monat,
                    monat_name=ha_monat.monat_name,
                    aktion=aktion,
                    grund=grund,
                    ha_werte=ha_basis_anzeige,
                    vorhandene_werte=vorhandene_anzeige,
                    investitionen=inv_status_liste if inv_status_liste else None
                ))

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

async def _verteile_anlagen_pv(
    db: AsyncSession, anlage_id: int, jahr: int, monat: int, pv_gesamt: float, *, ueberschreiben: bool,
) -> bool:
    """Schreibt den Anlagen-PV-Zähler eines Monats als Modulwerte (N-533).

    Dieselbe Regel wie der Monatsabschluss (`monatsabschluss/views.py`, `_mapped_or_distribute`)
    und die Leseseite (`resolve_pv_je_modul`, ADR-002/P7): Module mit eigenem Messwert behalten
    ihn, der Rest des Zählers geht nach kWp auf die Module ohne Messwert. Genau ein Empfänger
    bekommt den Wert als Messung ohne Marke; ab zwei Empfängern trägt jeder Anteil
    ``ABGELEITET_KWP_ANTEIL`` — der Daten-Checker klassifiziert den Monat dann als „verteilt“,
    nicht als „fehlt“. Liefert True, wenn mindestens ein Modulwert geschrieben wurde.

    **N-611 — der Zähler misst alle PV-Quellen.** Rest = Zähler − Σ gemessene Module − Σ eigene
    Werte der selbst tragenden Balkonkraftwerke, nie unter 0 (`eigene_bkw_erzeugung_kwh`, dieselbe
    Zahl wie auf der Leseseite). Bis dahin landete der BKW-Wert als Anteil in den Modulwerten und
    stand danach in `pv_kwh = Module + BKW` ein zweites Mal. Empfänger bleiben nur die Module:
    ein BKW ohne eigenen Wert bekommt keinen Anteil (der Zählerwert selbst wird nicht gespeichert,
    P7 — die Familie geht an HA-Bauform S1).
    """
    inv_result = await db.execute(
        select(Investition).where(
            and_(
                Investition.anlage_id == anlage_id,
                Investition.typ.in_(("pv-module", "balkonkraftwerk")),
            )
        )
    )
    # ADR-002/P11: erst der Zeitfilter, dann der Selektor — ein BKW, das in diesem Monat an
    # Modul-Kinder abgetreten hat, steht schon in deren Werten und mindert den Zähler nicht.
    aktive = erzeuger_traeger(
        [inv for inv in inv_result.scalars().all() if inv.ist_aktiv_im_monat(jahr, monat)]
    )
    module = [inv for inv in aktive if inv.typ == "pv-module"]
    if not module:
        return False
    imd_result = await db.execute(
        select(InvestitionMonatsdaten).where(
            and_(
                InvestitionMonatsdaten.investition_id.in_([inv.id for inv in aktive]),
                InvestitionMonatsdaten.jahr == jahr,
                InvestitionMonatsdaten.monat == monat,
            )
        )
    )
    imd_map = {imd.investition_id: imd for imd in imd_result.scalars().all()}
    bkw_eigen = eigene_bkw_erzeugung_kwh(
        aktive, {inv_id: imd.verbrauch_daten for inv_id, imd in imd_map.items()},
    )
    # Was gemessen ist, sagt die P7-Auflösung — nicht die Rohspalte: ein gespeicherter
    # Wert mit Zerlegungsmarke (#352) ist eine Lücke, die neu verteilt wird.
    lokal = (await lade_pv_je_monat(db, anlage_id, module, jahr)).get((jahr, monat), {})

    def _gemessen(inv_id: int) -> Optional[float]:
        modulwert = lokal.get(inv_id)
        if modulwert is None or modulwert.quelle != QUELLE_GEMESSEN:
            return None
        return modulwert.pv_erzeugung_kwh

    pv_module = [PvModul(inv.id, get_pv_kwp(inv), _gemessen(inv.id)) for inv in module]
    aufgeloest = resolve_pv_je_modul(aggregat_kwh=max(0.0, pv_gesamt - bkw_eigen), module=pv_module)
    luecken = [inv for inv in module if _gemessen(inv.id) is None]
    if not luecken:
        return False
    marke = ABGELEITET_KWP_ANTEIL if len(luecken) > 1 else None
    geschrieben = False
    for inv in luecken:
        modulwert = aufgeloest[inv.id]
        wert = round(modulwert.pv_erzeugung_kwh, 2)
        imd = imd_map.get(inv.id)
        if imd is None:
            imd = InvestitionMonatsdaten(
                investition_id=inv.id, jahr=jahr, monat=monat,
                verbrauch_daten={"pv_erzeugung_kwh": wert},
            )
            db.add(imd)
            await db.flush()
            seed_provenance(
                imd, source=_HA_STATS_SOURCE, writer=_HA_STATS_WRITER,
                json_subkeys={"verbrauch_daten": ["pv_erzeugung_kwh"]},
                abgeleitet_je_subkey={"pv_erzeugung_kwh": marke} if marke else None,
            )
            geschrieben = True
            continue
        if imd.verbrauch_daten is None:
            imd.verbrauch_daten = {}
        vorhanden = imd.verbrauch_daten.get("pv_erzeugung_kwh")
        if vorhanden is None or vorhanden == 0 or ueberschreiben:
            res = await write_json_subkey_with_provenance(
                db, imd, "verbrauch_daten", "pv_erzeugung_kwh", wert,
                source=_HA_STATS_SOURCE, writer=_HA_STATS_WRITER, abgeleitet=marke,
            )
            if res.applied:
                geschrieben = True
    return geschrieben


@router.post("/import/{anlage_id}", response_model=ImportResultat)
async def import_ha_statistics(
    anlage_id: int,
    request: ImportRequest,
    db: AsyncSession = Depends(get_db, scope="function")
):
    """
    Importiert HA-Statistik-Daten in EEDC Monatsdaten.

    Unterstützt selektiven Import:
    - basis_felder: Liste der zu importierenden Basis-Felder (None = alle)
    - investition_felder: Dict von inv_id -> Feld-Liste (None = alle)

    Args:
        anlage_id: ID der Anlage
        request.monate: Liste der zu importierenden Monate mit Feld-Auswahl
        request.ueberschreiben: Auch vorhandene Daten überschreiben

    Returns:
        Import-Statistik
    """
    service = get_ha_statistics_service()
    if not service.is_available:
        raise ha_db_unavailable()

    anlage = await get_anlage_with_mapping(db, anlage_id)
    sensor_mapping = anlage.sensor_mapping
    sensor_ids = extract_sensor_ids_from_mapping(sensor_mapping)

    importiert = 0
    uebersprungen = 0
    ueberschrieben = 0
    fehler = []
    # Zählerlücken wie HA (Vorlage §10): dieselbe Monatsregel wie die Vorschau.
    _deckel = deckel_je_sensor(anlage, (await db.execute(
        select(Investition).where(Investition.anlage_id == anlage_id)
    )).scalars().all())
    # N-240: Monate, die nur Gerätewerte bekommen haben — gesammelt statt je
    # Monat gemeldet, sonst stünde derselbe Satz zwölfmal im Ergebnis.
    monate_ohne_zaehlerwerte: list[tuple[int, int]] = []

    for monat_req in request.monate:
        jahr = monat_req.jahr
        monat = monat_req.monat
        basis_felder_auswahl = monat_req.basis_felder  # None = alle, [] = keine
        inv_felder_auswahl = monat_req.investition_felder  # None = alle, {} = keine

        try:
            # HA-Werte für diesen Monat holen
            ha_response = service.get_monatswerte(
                sensor_ids, jahr, monat, deckel_je_sensor=_deckel,
            )

            # Sensor-Werte zu Dict mappen
            sensor_values = {s.sensor_id: s.differenz for s in ha_response.sensoren}

            # Basis-Werte extrahieren (nur wenn nicht explizit ausgeschlossen)
            einspeisung = None
            netzbezug = None
            basis_importiert = False

            # Prüfen ob Basis-Felder importiert werden sollen.
            # basis_felder_auswahl kann raw Keys ("einspeisung") ODER Labels
            # ("Einspeisung") enthalten, je nachdem was die Vorschau geliefert hat.
            def _basis_aktiv(raw_key: str) -> bool:
                if basis_felder_auswahl is None:
                    return True
                label = FELD_LABELS.get(raw_key, raw_key)
                return raw_key in basis_felder_auswahl or label in basis_felder_auswahl

            import_einspeisung = _basis_aktiv("einspeisung")
            import_netzbezug = _basis_aktiv("netzbezug")

            basis_mapping = sensor_mapping.get("basis", {})
            if import_einspeisung and basis_mapping.get("einspeisung", {}).get("sensor_id"):
                einspeisung = sensor_values.get(basis_mapping["einspeisung"]["sensor_id"])
            if import_netzbezug and basis_mapping.get("netzbezug", {}).get("sensor_id"):
                netzbezug = sensor_values.get(basis_mapping["netzbezug"]["sensor_id"])

            # Monatsdaten laden oder erstellen — nur wenn Basis-Felder importiert
            # werden UND tatsächlich ein Zählerwert vorliegt.
            #
            # ⚠ **Die zweite Bedingung ist neu (13.08., N-240) und korrigiert eine
            # erfundene Messung.** Ohne sie legte der Import bei aktiven, aber
            # NICHT zugeordneten Basis-Feldern eine Zeile mit `0/0` an (an echten
            # Objekten gemessen): eine Einspeisung und ein Netzbezug von exakt
            # null, die niemand gemessen hat — und die der Plausibilitäts-Check
            # prompt als „beide 0" meldete. `is not None` statt truthiness, damit
            # ein echt gemessener 0-Wert weiterhin durchkommt.
            hat_zaehlerwert = (
                (import_einspeisung and einspeisung is not None)
                or (import_netzbezug and netzbezug is not None)
            )
            if hat_zaehlerwert:
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
                    # Neu erstellen — fresh row, kein Hierarchie-Konflikt möglich
                    md = Monatsdaten(
                        anlage_id=anlage_id,
                        jahr=jahr,
                        monat=monat,
                        einspeisung_kwh=einspeisung if import_einspeisung else 0,
                        netzbezug_kwh=netzbezug if import_netzbezug else 0,
                        datenquelle="ha_statistics"
                    )
                    db.add(md)
                    await db.flush()
                    fresh_fields = [
                        f for f in ("einspeisung_kwh", "netzbezug_kwh")
                        if (f == "einspeisung_kwh" and import_einspeisung)
                        or (f == "netzbezug_kwh" and import_netzbezug)
                    ]
                    if fresh_fields:
                        seed_provenance(
                            md, source=_HA_STATS_SOURCE, writer=_HA_STATS_WRITER,
                            fields=fresh_fields,
                        )
                    basis_importiert = True
                else:
                    # Existiert - selektiv via Resolver. Manuelle Werte (manual:form,
                    # Stufe 1) gewinnen automatisch gegen HA-Stats (Stufe 2).
                    # Das `ueberschreiben`-Flag steuert nur die Same-Source-Logik
                    # bei bereits importierten HA-Stats-Werten.
                    hat_einspeisung = (md.einspeisung_kwh or 0) > 0.1
                    hat_netzbezug = (md.netzbezug_kwh or 0) > 0.1

                    if import_einspeisung and einspeisung is not None:
                        if not hat_einspeisung or request.ueberschreiben:
                            result = await write_with_provenance(
                                db, md, "einspeisung_kwh", einspeisung,
                                source=_HA_STATS_SOURCE, writer=_HA_STATS_WRITER,
                            )
                            if result.applied:
                                basis_importiert = True

                    if import_netzbezug and netzbezug is not None:
                        if not hat_netzbezug or request.ueberschreiben:
                            result = await write_with_provenance(
                                db, md, "netzbezug_kwh", netzbezug,
                                source=_HA_STATS_SOURCE, writer=_HA_STATS_WRITER,
                            )
                            if result.applied:
                                basis_importiert = True

                    if basis_importiert:
                        md.datenquelle = "ha_statistics"

            # InvestitionMonatsdaten verarbeiten
            inv_mapping = sensor_mapping.get("investitionen", {})
            inv_importiert = False

            # Gültige Investitions-IDs laden (verwaiste Mapping-Einträge ignorieren)
            inv_result = await db.execute(
                select(Investition.id, Investition.typ).where(Investition.anlage_id == anlage_id)
            )
            # N-555: der Typ je Investition für die Heimlade-Regel unten (Regel 4).
            inv_typ_je_id = {str(r[0]): r[1] for r in inv_result.all()}
            gueltige_inv_ids = set(inv_typ_je_id)

            for inv_id_str, inv_config in inv_mapping.items():
                if inv_id_str not in gueltige_inv_ids:
                    continue  # Verwaister sensor_mapping-Eintrag
                inv_id = int(inv_id_str)

                # Prüfen ob diese Investition importiert werden soll
                if inv_felder_auswahl is not None:
                    if inv_id_str not in inv_felder_auswahl:
                        continue  # Diese Investition überspringen
                    erlaubte_felder = inv_felder_auswahl[inv_id_str]
                    if not erlaubte_felder:
                        continue  # Keine Felder für diese Investition
                else:
                    erlaubte_felder = None  # Alle Felder

                felder = inv_config.get("felder", {})

                # Werte aus HA extrahieren (nur erlaubte Felder)
                inv_werte = {}
                for feld, feld_config in felder.items():
                    # Nur importieren wenn Feld erlaubt
                    # erlaubte_felder kann raw Keys ("pv_erzeugung_kwh") ODER Labels ("PV Erzeugung") enthalten
                    if erlaubte_felder is not None:
                        feld_label = FELD_LABELS.get(feld, feld)
                        if feld not in erlaubte_felder and feld_label not in erlaubte_felder:
                            continue

                    # `sensor_values` sind Zählerdifferenzen (MAX−MIN). Bei
                    # einem Preis-/Kosten-Feld wäre das die Monats-Spreizung —
                    # und die landete hier persistent in `verbrauch_daten`.
                    if not ist_zaehler_differenz_feld(feld):
                        continue

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
                    await db.flush()
                    if inv_werte:
                        seed_provenance(
                            imd, source=_HA_STATS_SOURCE, writer=_HA_STATS_WRITER,
                            json_subkeys={"verbrauch_daten": list(inv_werte.keys())},
                        )
                    inv_importiert = True
                else:
                    # Merge mit existierenden Daten — Per-Sub-Key durch Resolver.
                    # manual:form-Sub-Keys überleben den Import (Hierarchie greift).
                    if imd.verbrauch_daten is None:
                        imd.verbrauch_daten = {}

                    for feld, wert in inv_werte.items():
                        vorhandener_wert = imd.verbrauch_daten.get(feld)
                        # N-555 Regel 4 (E1 eng): bei einem Heimlade-Mengenfeld ist
                        # eine gespeicherte 0 ein Wert („die Wallbox hat nicht
                        # geladen") und wird — wie jeder andere Wert — nur mit
                        # „überschreiben" ersetzt. Überall sonst gilt die 0 weiter
                        # als leer (PV-Module: eine eingefrorene Quelle ergäbe 0).
                        leer = vorhandener_wert is None or (
                            vorhandener_wert == 0
                            and not ist_heimlade_mengen_feld(inv_typ_je_id.get(inv_id_str), feld)
                        )
                        if leer or request.ueberschreiben:
                            result = await write_json_subkey_with_provenance(
                                db, imd, "verbrauch_daten", feld, wert,
                                source=_HA_STATS_SOURCE, writer=_HA_STATS_WRITER,
                            )
                            if result.applied:
                                inv_importiert = True

            # N-533: der Anlagen-PV-Zähler (`basis.pv_gesamt`) — bis 19.09.2026 stand er
            # in der Vorschau und wurde beim Import nirgendwohin geschrieben. Jetzt wie der
            # Monatsabschluss und der Tagespfad: nach kWp auf die aktiven PV-Module ohne
            # eigenen Messwert verteilen, als Zerlegung gekennzeichnet (P7: Messwerte je
            # Modul haben Vorrang, der Zähler füllt nur die Lücken).
            pv_gesamt = None
            if _basis_aktiv("pv_gesamt") and basis_mapping.get("pv_gesamt", {}).get("sensor_id"):
                pv_gesamt = sensor_values.get(basis_mapping["pv_gesamt"]["sensor_id"])
            if pv_gesamt is not None:
                if await _verteile_anlagen_pv(
                    db, anlage_id, jahr, monat, pv_gesamt, ueberschreiben=request.ueberschreiben,
                ):
                    inv_importiert = True

            # N-240: Gerätewerte angekommen, aber keine Zählerzeile für den Monat
            # — der Zustand aus #349, hier auf dem HA-Weg. Geprüft wird die
            # ZEILE, nicht die Zuordnung: existiert sie aus einem früheren Lauf
            # oder aus dem Monatsabschluss, ist alles in Ordnung.
            if inv_importiert and not hat_zaehlerwert:
                vorhandene = await db.execute(
                    select(Monatsdaten.id).where(
                        and_(
                            Monatsdaten.anlage_id == anlage_id,
                            Monatsdaten.jahr == jahr,
                            Monatsdaten.monat == monat,
                        )
                    )
                )
                if vorhandene.scalar_one_or_none() is None:
                    monate_ohne_zaehlerwerte.append((jahr, monat))

            # Zähler aktualisieren
            if basis_importiert or inv_importiert:
                importiert += 1
            else:
                uebersprungen += 1

        except Exception as e:
            fehler.append(f"{jahr}/{monat:02d}: {str(e)}")

    await db.commit()

    await log_activity(
        kategorie="ha_statistics",
        aktion=f"HA-Import: {importiert} Monate",
        erfolg=len(fehler) == 0,
        details=f"Importiert: {importiert}, Übersprungen: {uebersprungen}" + (f", Fehler: {len(fehler)}" if fehler else ""),
        anlage_id=anlage_id,
        db=db,
    )

    warnung = warnung_monate_ohne_zaehlerwerte(monate_ohne_zaehlerwerte)
    return ImportResultat(
        erfolg=len(fehler) == 0,
        importiert=importiert,
        uebersprungen=uebersprungen,
        ueberschrieben=ueberschrieben,
        fehler=fehler,
        warnungen=[warnung] if warnung else [],
    )
