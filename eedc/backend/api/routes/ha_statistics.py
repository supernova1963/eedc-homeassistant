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
from collections import Counter
from dataclasses import dataclass
from datetime import date
from typing import Optional, Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified
from pydantic import BaseModel

from backend.core.exceptions import bad_request, ha_db_unavailable, not_found
from backend.api.deps import get_db
from backend.services.activity_service import log_activity
from backend.core.field_definitions import FELD_LABELS as _FELD_LABELS_REGISTRY
from backend.core.field_definitions import basis_feld_key, ist_zaehler_differenz_feld
from backend.models.anlage import Anlage
from backend.models.monatsdaten import Monatsdaten
from backend.models.investition import Investition, InvestitionMonatsdaten
from backend.services.ha_statistics_service import (
    get_ha_statistics_service,
    MonatswertResponse,
    AlleMonateResponse,
    SensorMonatswert,
)
from backend.services.import_hauszaehler import warnung_monate_ohne_zaehlerwerte, warnung_pv_gesamt_ohne_zaehlerzeile
from backend.services.monatswert_deckel import deckel_je_sensor
from backend.core.berechnungen.erzeuger_traeger import erzeuger_traeger
from backend.core.berechnungen.pv_verteilung import QUELLE_GEMESSEN
from backend.core.field_definitions import get_pv_erzeugung_kwh
from backend.core.zahlenformat import fmt_zahl
from backend.services.pv_monatswerte import (
    bkw_ohne_eigenen_wert,
    eigene_bkw_erzeugung_kwh,
    lade_pv_je_monat,
    pv_summe_je_monat,
)
from backend.api.routes.ha_statistics_import import ImportBilanz, ha_geraetewerte, importiere_monat

logger = logging.getLogger(__name__)

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
#
# N-622 (04.10.2026): `pv_gesamt` fehlte hier seit v2.5.3 — `/monatswerte` lieferte
# den Anlagen-PV-Zähler als `feld: "pv_gesamt"`, das Formular „Aus HA laden" sucht
# die Spalte `pv_erzeugung_kwh` und blieb leer (N-534 wirkte für PV nie). Der Wert
# ist das Anlagen-Aggregat (ADR-002/P7): das Formular zeigt ihn als eigene Zeile,
# gespeichert wird nur, was der Anwender dort stehen lässt. Einzige Leser dieser
# Tabelle: `map_sensor_values_to_fields` für `/monatswerte` und `/alle-monatswerte`.
# =============================================================================

MAPPING_KEY_TO_DB_FELD = {
    "einspeisung": "einspeisung_kwh",
    "netzbezug": "netzbezug_kwh",
    "pv_gesamt": "pv_erzeugung_kwh",
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
    # N-622 (Härtung): nur Zählerfelder — dieselbe Regel wie Monatsabschluss-Vorschlag,
    # Import-Vorschau und Sammelimport (`ist_zaehler_differenz_feld`). Der Wert ist eine
    # Zählerdifferenz (MAX−MIN); bei einem Preis-Sensor (`basis.strompreis`, Geräte-Feld
    # `speicher_ladepreis_cent`) wäre er die Monatsspanne und landete im Formular.
    # Innengeräte-Keys (`…_kwh-3`) werden über `basis_feld_key` aufgelöst, damit sie
    # hier nicht still herausfallen.
    basis = sensor_mapping.get("basis", {})
    for mapping_key, config in basis.items():
        if not ist_zaehler_differenz_feld(mapping_key):
            continue
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
            if not ist_zaehler_differenz_feld(basis_feld_key(feld)):
                continue
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
        # HA-Bauform E4a-2 (Umschaltstelle 3, B-2): Kanal-Δ der Bilanz-Sensoren, wenn ihre Spiegel den
        # Kalendermonat alle voll decken (ohne Deckel); sonst bleibt der HA-Leser.
        from backend.services.kanal.bilanz_leser import monatswerte_mit_kanaelen
        (response,) = await monatswerte_mit_kanaelen(db, anlage_id, [response], monate=[(jahr, monat)])
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
        # HA-Bauform E4a-2 (Umschaltstelle 3, B-2): Kanal-Δ der Bilanz-Sensoren, wenn ihre Spiegel den
        # Kalendermonat alle voll decken (ohne Deckel); sonst bleibt der HA-Leser.
        from backend.services.kanal.bilanz_leser import monatswerte_mit_kanaelen
        raw_responses = await monatswerte_mit_kanaelen(db, anlage_id, raw_responses)
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
    #: N-658: „Σ Geräte − Anlagenzähler" (HA), wenn die Differenz der PV unter dem Messpunkt-Vertrag
    #: Wandlungsverluste ist — dann kein Konflikt, nur ein Hinweis im `grund`. Sonst `None`.
    wandlungsverluste_kwh: Optional[float] = None


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
    #: N-240: Sachverhalte, die kein Fehler sind, aber Folgen haben — Monate, in denen nur
    #: Gerätewerte entstanden (keine Zählerzeile), und seit HA-Bauform E4b Monate, deren
    #: PV-Gesamtzähler mangels Zählerzeile nicht gespeichert wurde.
    #: Getrennt von `fehler`, weil der Lauf erfolgreich war: `erfolg` bleibt True.
    warnungen: list[str] = []


# =============================================================================
# Import Preview Endpoint
# =============================================================================

def _sind_wandlungsverluste(
    *, verluste_kwh: float, geraete_kwh: float, nur_eigene_werte: bool, bkw_kwh: float, aktive: list,
) -> bool:
    """N-658: Ist „lokale PV − HA-Anlagenzähler" eines Monats ein Wechselrichterverlust, den der Layer bewertet?

    Dieselbe Frage wie ``pv_verteilung.wandlungsverluste_grund`` (Messpunkt-Vertrag, N-588): ja, wenn die lokale
    Summe größer ist (Σ Geräte > Anlagenzähler), ganz aus eigenen Gerätewerten besteht (ii′ — sonst ist sie der
    gespeicherte Anlagenwert selbst) und der Vertrag keinen Grund nennt — kein DC-Speicher (iii), höchstens
    ``WANDLUNGSVERLUSTE_SCHWELLE_PROZENT`` (iv), Balkonkraftwerk nicht außerhalb (v). Bis 10.10.2026 stand jede
    solche Differenz als „Konflikt" da — nach jedem korrekten Import (F13a: 630 gegen 594, Δ 36). Σ Geräte <
    Anlagenzähler bleibt ein Konflikt. ``bkw_kwh``: Σ der eigenen Werte der Balkonkraftwerke des Monats (Eingang (v));
    ``aktive``: die im Monat aktiven Investitionen (Eingang (iii)).
    """
    from backend.core.berechnungen.pv_verteilung import wandlungsverluste_grund
    from backend.services.kanal.bilanz_leser import _dc_grund

    if verluste_kwh <= 0 or not nur_eigene_werte:
        return False
    return wandlungsverluste_grund(
        verluste_kwh=verluste_kwh, strings_kwh=geraete_kwh, bkw_kwh=bkw_kwh,
        dc_grund=_dc_grund(aktive, lambda _inv: True),
    ) is None


@dataclass(frozen=True)
class _VorschauKontext:
    """Was die Vorschau einmal je Anfrage lädt und je Monat nur liest (RF-5)."""
    anlage: Anlage
    investitionen: dict          # str(inv.id) -> Investition
    vorhandene_md: dict          # (jahr, monat) -> Monatsdaten
    vorhandene_imd: dict         # (inv_id, jahr, monat) -> InvestitionMonatsdaten
    pv_summen: dict              # (jahr, monat) -> lokale PV-Summe oder None
    pv_nur_eigene_werte: set     # N-658, s. `_lokale_pv_summen`


async def _lokale_pv_summen(
    db: AsyncSession, anlage: Anlage, anlage_id: int, investitionen: dict, vorhandene_imd: dict,
) -> tuple[dict, set]:
    # N-533: der lokale PV-Gesamtwert je Monat für den Vergleich mit dem Anlagen-Zähler
    # (`basis.pv_gesamt`) — über die P7-Auflösung (`lade_pv_je_monat`), nicht über die
    # Rohspalte: Messwerte je Modul plus Aggregat-Lückenfüllung, `None` bei Unvollständigkeit.
    pv_summen: dict[tuple[int, int], Optional[float]] = {}
    #: N-658: Monate, deren lokale PV-Summe ganz aus eigenen Gerätewerten besteht — kein Modul und kein
    #: Balkonkraftwerk trägt dort einen Anteil am Anlagenwert. Nur dort ist „Σ Geräte − Anlagenzähler" eine
    #: Aussage über Wandlungsverluste (Messpunkt-Vertrag (ii′), `pv_verteilung.wandlungsverluste_grund`);
    #: mit einem Anteil ist die lokale Summe der gespeicherte Anlagenwert selbst.
    pv_nur_eigene_werte: set[tuple[int, int]] = set()
    if not ((anlage.sensor_mapping.get("basis") or {}).get("pv_gesamt") or {}).get("sensor_id"):
        return pv_summen, pv_nur_eigene_werte
    pv_module_der_anlage = [inv for inv in investitionen.values() if inv.typ == "pv-module"]
    # N-621: in einem Monat mit gespeichertem Anlagenwert teilen sich die Module den Rest mit den
    # Balkonkraftwerken ohne eigenen Wert — deren Anteil gehört zur lokalen Zahl wie in den
    # Monats-Fakten (`pv_kwh = Module + BKW-Wert + BKW-Anteil`). Ohne ihn fiele die Modul-Summe um
    # den Anteil, und ein übereinstimmender Monat stünde als Konflikt da (gemessen: Anlagenwert 1000,
    # Süd 550, West und BKW ohne Wert ⇒ lokal 925 statt 1000).
    vorschau_bkw_anteile: dict = {}
    pv_monate = await lade_pv_je_monat(
        db, anlage_id, pv_module_der_anlage, investitionen=list(investitionen.values()),
        bkw_anteile=vorschau_bkw_anteile,
    )
    pv_summen = pv_summe_je_monat(pv_monate)
    pv_nur_eigene_werte = {
        key for key, werte in pv_monate.items()
        if all(w.quelle == QUELLE_GEMESSEN for w in werte.values()) and not vorschau_bkw_anteile.get(key)
    }
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
        }) + sum(vorschau_bkw_anteile.get((j, m), {}).values())

    # N-629: Monate OHNE aktives `pv-module` (eine Anlage nur mit Balkonkraftwerk) haben in der
    # Modul-Auflösung keinen Eintrag — lokal ist dort, was die Balkonkraftwerke tragen: ihre eigenen
    # Werte plus ihr Anteil am gespeicherten Anlagenwert, über dieselben Helfer wie oben (P11-Selektor).
    # Bis 04.10.2026 galt ein solcher abgeschlossener Monat als „fehlt lokal“ und wurde zum Import
    # vorgeschlagen. ⚠ Monate MIT Modul bleiben bei `pv_summe_je_monat`: eine Modul-Lücke ohne
    # Anlagenwert bleibt „fehlt lokal → importieren“ (der Import schließt sie) — nicht die
    # Anzeige-Summe der Monats-Fakten, die dort seit N-626 eine Teilsumme trägt.
    for (j, m) in sorted(
        {(jj, mm) for (_i, jj, mm) in vorhandene_imd} | set(vorschau_bkw_anteile)
    ):
        if (j, m) in pv_summen:
            continue
        aktive = [inv for inv in investitionen.values() if inv.ist_aktiv_im_monat(j, m)]
        if any(inv.typ == "pv-module" for inv in aktive):
            continue
        daten = {
            inv.id: vorhandene_imd[(inv.id, j, m)].verbrauch_daten
            for inv in aktive if (inv.id, j, m) in vorhandene_imd
        }
        ohne_wert = {inv.id for inv in bkw_ohne_eigenen_wert(aktive, daten)}
        # Träger der Erzeugung über den P11-Selektor — ohne Modul im Monat sind das alle BKW.
        mit_wert = [
            inv for inv in erzeuger_traeger(aktive)
            if inv.typ == "balkonkraftwerk" and inv.id not in ohne_wert
        ]
        anteile = vorschau_bkw_anteile.get((j, m), {})
        if mit_wert or anteile:
            pv_summen[(j, m)] = eigene_bkw_erzeugung_kwh(aktive, daten) + sum(anteile.values())
            if not anteile:
                pv_nur_eigene_werte.add((j, m))
    return pv_summen, pv_nur_eigene_werte


def _ha_basis_werte(sensor_mapping: dict, ha_monat) -> dict:
    # HA-Werte extrahieren (Basis)
    ha_basis_werte = {}
    for sensor in ha_monat.sensoren:
        # Sensor-ID zu Feld-Name mappen
        for basis_feld, basis_config in (sensor_mapping.get("basis") or {}).items():
            # `basis` trägt neben den Zählern auch den Strompreis-Sensor;
            # dessen Monats-Differenz ist eine Preis-Spreizung, kein Wert.
            if not ist_zaehler_differenz_feld(basis_feld):
                continue
            if basis_config and basis_config.get("sensor_id") == sensor.sensor_id:
                ha_basis_werte[basis_feld] = sensor.differenz
    return ha_basis_werte


def _ha_inv_werte(sensor_mapping: dict, ha_monat) -> dict[str, dict]:
    # Investitions-Werte pro Investition sammeln
    # inv_id -> {feld: wert}
    # Nur Zählerfelder — s. Import-Pfad weiter unten. Die Vorschau
    # muss dieselbe Menge zeigen wie der Import schreibt, sonst
    # steht dort ein Wert, der nie ankommt. N-666: Innengeräte-Keys
    # (`…_kwh-3`) über `basis_feld_key` — wie „Aus HA laden" (N-622).
    # RF-5: beide lesen die Gerätewerte über denselben Helfer (`ha_statistics_import.py::ha_geraetewerte`).
    sensor_values = {s.sensor_id: s.differenz for s in ha_monat.sensoren}
    return {
        inv_id: ha_geraetewerte(inv_config.get("felder", {}), sensor_values)
        for inv_id, inv_config in (sensor_mapping.get("investitionen") or {}).items()
    }


def _vergleiche_investitionen(ktx: _VorschauKontext, ha_inv_werte: dict, jahr: int, monat: int) -> tuple[list, bool]:
    # Investitionen-Vergleich erstellen
    inv_status_liste: list[InvestitionImportStatus] = []
    inv_hat_abweichung = False

    for inv_id_str, ha_felder in ha_inv_werte.items():
        if not ha_felder:
            continue

        inv = ktx.investitionen.get(inv_id_str)
        if not inv:
            # Verwaister sensor_mapping-Eintrag (Investition gelöscht) → überspringen
            continue

        # Vorhandene Werte für diese Investition
        imd = ktx.vorhandene_imd.get((inv.id, jahr, monat))
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
            investition_id=inv.id,
            bezeichnung=inv.bezeichnung,
            typ=inv.typ,
            ha_werte=ha_mit_labels,
            vorhandene_werte=vorh_mit_labels,
            hat_abweichung=hat_abw
        ))
    return inv_status_liste, inv_hat_abweichung


def _bkw_eigene_werte_kwh(ktx: _VorschauKontext, aktive: list, jahr: int, monat: int) -> float:
    """Σ der eigenen PV-Werte der im Monat aktiven Balkonkraftwerke — Eingang (v) von `_sind_wandlungsverluste`."""
    return sum(
        get_pv_erzeugung_kwh(ktx.vorhandene_imd[(inv.id, jahr, monat)].verbrauch_daten or {})
        for inv in aktive
        if inv.typ == "balkonkraftwerk" and (inv.id, jahr, monat) in ktx.vorhandene_imd
    )


def _bewerte_basis(
    ktx: _VorschauKontext, ha_basis_werte: dict, vorhandene_werte: dict, jahr: int, monat: int,
) -> tuple[list[str], list[str], Optional[float]]:
    # Daten existieren mit Werten — Abweichung? N-533 (Frank85): JEDES
    # Basis-Zählerfeld des Mappings zählt, nicht nur Einspeisung und
    # Netzbezug. Ein Feld mit HA-Wert und ohne lokalen Wert (der
    # Anlagen-PV-Zähler bei 40 Monaten) ist kein „stimmt überein“,
    # sondern ein Import — vorher ging genau das im Δ-Vergleich der
    # zwei Zählerfelder unter, und der Monat blieb ohne PV.
    fehlende: list[str] = []
    abweichende: list[str] = []
    wandlungsverluste: Optional[float] = None
    for feld, ha_wert in ha_basis_werte.items():
        if ha_wert is None:
            continue
        vorh = vorhandene_werte.get(feld)
        label = FELD_LABELS.get(feld, feld)
        if vorh is None:
            fehlende.append(label)
        elif abs(ha_wert - vorh) >= 1:
            aktive = [inv for inv in ktx.investitionen.values() if inv.ist_aktiv_im_monat(jahr, monat)]
            if feld == "pv_gesamt" and _sind_wandlungsverluste(
                verluste_kwh=vorh - ha_wert, geraete_kwh=vorh,
                nur_eigene_werte=(jahr, monat) in ktx.pv_nur_eigene_werte, aktive=aktive,
                bkw_kwh=_bkw_eigene_werte_kwh(ktx, aktive, jahr, monat),
            ):
                wandlungsverluste = vorh - ha_wert
                continue
            abweichende.append(f"{label} {abs(ha_wert - vorh):.1f}")
    return fehlende, abweichende, wandlungsverluste


def _entscheide_aktion(
    fehlende: list[str], abweichende: list[str], inv_hat_abweichung: bool, verluste_hinweis: Optional[str],
) -> tuple[str, str]:
    if not fehlende and not abweichende and not inv_hat_abweichung:
        grund = "Daten stimmen überein (Δ < 1)"
        if verluste_hinweis:
            grund = f"Daten stimmen überein · {verluste_hinweis}"
        return "ueberspringen", grund
    if abweichende or inv_hat_abweichung:
        grund_teile = []
        if abweichende:
            grund_teile.append("Basis: " + ", ".join(abweichende))
        if fehlende:
            grund_teile.append("fehlt lokal: " + ", ".join(fehlende))
        if inv_hat_abweichung:
            grund_teile.append("Komponenten-Werte weichen ab")
        if verluste_hinweis:
            grund_teile.append(verluste_hinweis)
        return "konflikt", " | ".join(grund_teile)
    grund = "Fehlt lokal: " + ", ".join(fehlende)
    if verluste_hinweis:
        grund += f" · {verluste_hinweis}"
    return "importieren", grund


def _vorschau_monat(ktx: _VorschauKontext, ha_monat) -> MonatImportStatus:
    jahr = ha_monat.jahr
    monat = ha_monat.monat
    ha_basis_werte = _ha_basis_werte(ktx.anlage.sensor_mapping, ha_monat)
    ha_inv_werte = _ha_inv_werte(ktx.anlage.sensor_mapping, ha_monat)

    # Prüfen ob Monatsdaten existieren
    md = ktx.vorhandene_md.get((jahr, monat))

    inv_status_liste, inv_hat_abweichung = _vergleiche_investitionen(ktx, ha_inv_werte, jahr, monat)
    investitionen_status = inv_status_liste if inv_status_liste else None

    # Anzeige-Versionen mit Labels (detLAN #187/1: Roh-Keys "einspeisung"
    # → "Einspeisung"). Raw-Variante bleibt für interne Vergleichs-Logik.
    ha_basis_anzeige = {FELD_LABELS.get(k, k): v for k, v in ha_basis_werte.items()}

    if md is None:
        # Keine Daten vorhanden → Importieren
        return MonatImportStatus(
            jahr=jahr,
            monat=monat,
            monat_name=ha_monat.monat_name,
            aktion="importieren",
            grund="Keine Monatsdaten vorhanden",
            ha_werte=ha_basis_anzeige,
            vorhandene_werte=None,
            investitionen=investitionen_status
        )

    # Daten existieren - prüfen ob leer oder mit Werten
    vorhandene_werte = {
        "einspeisung": md.einspeisung_kwh,
        "netzbezug": md.netzbezug_kwh,
    }
    if "pv_gesamt" in ha_basis_werte:
        # N-533: sonst stünde „Vorhanden –“ neben einem HA-Wert, ohne jede Folge.
        vorhandene_werte["pv_gesamt"] = ktx.pv_summen.get((jahr, monat))
    vorhandene_anzeige = {FELD_LABELS.get(k, k): v for k, v in vorhandene_werte.items()}

    # Sind die Basis-Werte leer (0 oder sehr klein)?
    basis_leer = (
        (md.einspeisung_kwh or 0) < 0.1 and
        (md.netzbezug_kwh or 0) < 0.1
    )

    if basis_leer:
        # Daten existieren aber sind leer → Importieren
        return MonatImportStatus(
            jahr=jahr,
            monat=monat,
            monat_name=ha_monat.monat_name,
            aktion="importieren",
            grund="Monatsdaten vorhanden aber leer",
            ha_werte=ha_basis_anzeige,
            vorhandene_werte=vorhandene_anzeige,
            investitionen=investitionen_status
        )

    fehlende, abweichende, wandlungsverluste = _bewerte_basis(ktx, ha_basis_werte, vorhandene_werte, jahr, monat)
    # N-658: eine Differenz, die Wandlungsverluste IST, ist kein Konflikt — sie steht als Hinweis daneben.
    verluste_hinweis = (
        f"Wandlungsverluste {fmt_zahl(wandlungsverluste, 1)} kWh (Anlagenzähler nach dem Wechselrichter)"
        if wandlungsverluste is not None else None
    )
    aktion, grund = _entscheide_aktion(fehlende, abweichende, inv_hat_abweichung, verluste_hinweis)
    return MonatImportStatus(
        jahr=jahr,
        monat=monat,
        monat_name=ha_monat.monat_name,
        aktion=aktion,
        grund=grund,
        ha_werte=ha_basis_anzeige,
        vorhandene_werte=vorhandene_anzeige,
        investitionen=investitionen_status,
        wandlungsverluste_kwh=round(wandlungsverluste, 1) if wandlungsverluste is not None else None,
    )


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
        # HA-Bauform E4a-2 (Umschaltstelle 3, B-2): Kanal-Δ der Bilanz-Sensoren, wenn ihre Spiegel den
        # Kalendermonat alle voll decken (ohne Deckel); sonst bleibt der HA-Leser.
        from backend.services.kanal.bilanz_leser import monatswerte_mit_kanaelen
        ha_monate = await monatswerte_mit_kanaelen(db, anlage_id, ha_monate)
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

    pv_summen, pv_nur_eigene_werte = await _lokale_pv_summen(db, anlage, anlage_id, investitionen, vorhandene_imd)
    ktx = _VorschauKontext(anlage, investitionen, vorhandene_md, vorhandene_imd, pv_summen, pv_nur_eigene_werte)

    # Jeden Monat analysieren
    monate_status: list[MonatImportStatus] = [_vorschau_monat(ktx, ha_monat) for ha_monat in ha_monate]
    anzahl_je_aktion = Counter(m.aktion for m in monate_status)

    return ImportVorschauResponse(
        anlage_id=anlage.id,
        anlage_name=anlage.anlagenname,
        anzahl_monate=len(monate_status),
        anzahl_importieren=anzahl_je_aktion["importieren"],
        anzahl_ueberspringen=anzahl_je_aktion["ueberspringen"],
        anzahl_konflikte=anzahl_je_aktion["konflikt"],
        monate=monate_status
    )


# =============================================================================
# Import Execute Endpoint
# =============================================================================

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

    # Zähler, Fehler und die beiden Warn-Sammellisten (N-240, E4b H-A1) — `ha_statistics_import.py::ImportBilanz`.
    bilanz = ImportBilanz()
    # Zählerlücken wie HA (Vorlage §10): dieselbe Monatsregel wie die Vorschau.
    _deckel = deckel_je_sensor(anlage, (await db.execute(
        select(Investition).where(Investition.anlage_id == anlage_id)
    )).scalars().all())

    for monat_req in request.monate:
        jahr = monat_req.jahr
        monat = monat_req.monat

        try:
            # HA-Werte für diesen Monat holen
            ha_response = service.get_monatswerte(
                sensor_ids, jahr, monat, deckel_je_sensor=_deckel,
            )
            # HA-Bauform E4a-2 (Umschaltstelle 3, B-2): Kanal-Δ der Bilanz-Sensoren, wenn ihre Spiegel den
            # Kalendermonat alle voll decken (ohne Deckel); sonst bleibt der HA-Leser.
            from backend.services.kanal.bilanz_leser import monatswerte_mit_kanaelen
            (ha_response,) = await monatswerte_mit_kanaelen(db, anlage_id, [ha_response], monate=[(jahr, monat)])

            # Was der Monat schreibt (Zählerzeile, Gerätewerte, Warnlisten, Zähler): `importiere_monat`.
            await importiere_monat(
                db, anlage_id, sensor_mapping, monat_req, ha_response, request.ueberschreiben, bilanz,
            )

        except Exception as e:
            bilanz.fehler.append(f"{jahr}/{monat:02d}: {str(e)}")

    await db.commit()

    await log_activity(
        kategorie="ha_statistics",
        aktion=f"HA-Import: {bilanz.importiert} Monate",
        erfolg=len(bilanz.fehler) == 0,
        details=f"Importiert: {bilanz.importiert}, Übersprungen: {bilanz.uebersprungen}" + (f", Fehler: {len(bilanz.fehler)}" if bilanz.fehler else ""),
        anlage_id=anlage_id,
        db=db,
    )

    warnungen = [w for w in (
        warnung_monate_ohne_zaehlerwerte(bilanz.monate_ohne_zaehlerwerte),
        warnung_pv_gesamt_ohne_zaehlerzeile(bilanz.pv_ohne_zeile_monate),
    ) if w]
    return ImportResultat(
        erfolg=len(bilanz.fehler) == 0,
        importiert=bilanz.importiert,
        uebersprungen=bilanz.uebersprungen,
        ueberschrieben=bilanz.ueberschrieben,
        fehler=bilanz.fehler,
        warnungen=warnungen,
    )
