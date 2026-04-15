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
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.attributes import flag_modified

from backend.core.database import get_db, async_session_maker
from backend.core.field_definitions import (
    BASIS_FELDER, OPTIONALE_FELDER, INVESTITION_FELDER,
    get_felder_fuer_investition, get_felder_fuer_sonstiges,
)

logger = logging.getLogger(__name__)
from backend.models.anlage import Anlage
from backend.models.monatsdaten import Monatsdaten
from backend.models.investition import Investition, InvestitionMonatsdaten
from backend.services.vorschlag_service import VorschlagService, Vorschlag, VorschlagQuelle, PlausibilitaetsWarnung
from backend.services.ha_mqtt_sync import get_ha_mqtt_sync_service
from backend.services.ha_state_service import get_ha_state_service
from backend.services.mqtt_inbound_service import get_mqtt_inbound_service
from backend.core.config import HA_INTEGRATION_AVAILABLE
from backend.api.routes.strompreise import lade_tarife_fuer_anlage
from backend.services.activity_service import log_activity


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
    aktueller_text: Optional[str] = None  # Für Textfelder wie Beschreibung, Notizen
    quelle: Optional[str] = None  # ha_sensor, snapshot, manuell, berechnet
    vorschlaege: list[VorschlagResponse] = []
    warnungen: list[WarnungResponse] = []
    strategie: Optional[str] = None  # Aus sensor_mapping
    sensor_id: Optional[str] = None  # Wenn strategie=sensor
    typ: str = "number"  # number oder text


class InvestitionStatus(BaseModel):
    """Status einer Investition im Monatsabschluss."""
    id: int
    typ: str
    bezeichnung: str
    felder: list[FeldStatus]
    kategorie: Optional[str] = None          # Für Typ "sonstiges": erzeuger/verbraucher/speicher
    sonstige_positionen: list[dict] = []     # Strukturierte Erträge & Ausgaben


class MonatsabschlussResponse(BaseModel):
    """Vollständiger Status für einen Monat."""
    anlage_id: int
    anlage_name: str
    jahr: int
    monat: int
    ist_abgeschlossen: bool
    ha_mapping_konfiguriert: bool
    connector_konfiguriert: bool = False
    cloud_import_konfiguriert: bool = False
    mqtt_inbound_konfiguriert: bool = False
    portal_import_vorhanden: bool = False
    datenquelle: Optional[str] = None  # "portal_import", "cloud_import", "mqtt_inbound", "manual", etc.

    # Basis-Felder (Zählerdaten)
    basis_felder: list[FeldStatus]

    # Optionale Felder (Sonderkosten, Notizen - nicht aus HA)
    optionale_felder: list[FeldStatus] = []

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
    sonstige_positionen: Optional[list[dict]] = None  # Strukturierte Erträge & Ausgaben


class MonatsabschlussInput(BaseModel):
    """Eingabedaten für den Monatsabschluss."""
    # Basis-Zählerdaten
    # HINWEIS: direktverbrauch_kwh wird automatisch berechnet (PV-Erzeugung - Einspeisung)
    einspeisung_kwh: Optional[float] = None
    netzbezug_kwh: Optional[float] = None
    globalstrahlung_kwh_m2: Optional[float] = None
    sonnenstunden: Optional[float] = None
    durchschnittstemperatur: Optional[float] = None

    # Optionale manuelle Felder (nicht aus HA)
    netzbezug_durchschnittspreis_cent: Optional[float] = None
    sonderkosten_euro: Optional[float] = None
    sonderkosten_beschreibung: Optional[str] = None
    notizen: Optional[str] = None

    # Investitionen
    investitionen: list[InvestitionWerte] = []

    # Datenquelle (z.B. "mqtt_inbound", "cloud_import", "ha_statistics")
    datenquelle: Optional[str] = None


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

# BASIS_FELDER, OPTIONALE_FELDER, INVESTITION_FELDER werden aus
# backend.core.field_definitions importiert (Single Source of Truth)


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

    # Connector-Status und Monatswerte berechnen
    connector_config = anlage.connector_config
    connector_konfiguriert = bool(connector_config and connector_config.get("connector_id"))
    cloud_config = (connector_config or {}).get("cloud_import", {})
    cloud_import_konfiguriert = bool(cloud_config and cloud_config.get("provider_id"))
    connector_delta: Optional[dict] = None
    connector_inv_verteilung: dict[int, dict[str, float]] = {}

    if connector_konfiguriert:
        from backend.api.routes.connector import _calc_month_delta, _distribute_by_param
        snapshots = connector_config.get("meter_snapshots", {})
        if snapshots:
            connector_delta = _calc_month_delta(snapshots, jahr, monat)
            # PV auf Module verteilen
            if connector_delta:
                pv_kwh = connector_delta.get("pv_erzeugung_kwh")
                if pv_kwh is not None and pv_kwh > 0:
                    pv_module = [i for i in anlage.investitionen if i.typ == "pv-module"]
                    if pv_module:
                        for inv, anteil in _distribute_by_param(pv_module, pv_kwh, "leistung_kwp"):
                            connector_inv_verteilung.setdefault(inv.id, {})["pv_erzeugung_kwh"] = anteil
                # Batterie auf Speicher verteilen
                for bat_feld, inv_feld in [
                    ("batterie_ladung_kwh", "ladung_kwh"),
                    ("batterie_entladung_kwh", "entladung_kwh"),
                ]:
                    bat_val = connector_delta.get(bat_feld)
                    if bat_val is not None and bat_val > 0:
                        speicher = [i for i in anlage.investitionen if i.typ == "speicher"]
                        if speicher:
                            for inv, anteil in _distribute_by_param(speicher, bat_val, "kapazitaet_kwh"):
                                connector_inv_verteilung.setdefault(inv.id, {})[inv_feld] = anteil

    # MQTT Inbound Energy-Daten sammeln
    mqtt_energy: dict[str, float] = {}
    mqtt_inv_energy: dict[int, dict[str, float]] = {}  # inv_id → {feld: wert}
    mqtt_svc = get_mqtt_inbound_service()
    if mqtt_svc:
        energy = mqtt_svc.cache.get_energy_data(anlage.id)
        if energy:
            # Basis-Felder
            basis_map = {
                "einspeisung_kwh": "einspeisung_kwh",
                "netzbezug_kwh": "netzbezug_kwh",
            }
            for mqtt_key, feld_name in basis_map.items():
                val = energy.get(mqtt_key)
                if val is not None and val > 0:
                    mqtt_energy[feld_name] = round(val, 1)

            # Investitions-Felder: inv/{inv_id}/{key}
            for mqtt_key, val in energy.items():
                if not mqtt_key.startswith("inv/") or val is None or val <= 0:
                    continue
                parts = mqtt_key.split("/", 2)  # ["inv", "3", "ladung_kwh"]
                if len(parts) == 3:
                    try:
                        inv_id = int(parts[1])
                        mqtt_inv_energy.setdefault(inv_id, {})[parts[2]] = round(val, 1)
                    except ValueError:
                        pass

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

    # HA Statistics Service für Sensor-Vorschläge
    ha_stats_werte: dict[str, float] = {}  # sensor_id → differenz
    if HA_INTEGRATION_AVAILABLE:
        import asyncio
        from backend.services.ha_statistics_service import get_ha_statistics_service
        ha_stats_svc = get_ha_statistics_service()
        if ha_stats_svc.is_available:
            # Alle sensor_ids aus dem Mapping sammeln
            all_sensor_ids = []
            for cfg in basis_mapping.values():
                if cfg and cfg.get("strategie") == "sensor" and cfg.get("sensor_id"):
                    all_sensor_ids.append(cfg["sensor_id"])
            for inv_cfg in inv_mappings.values():
                if isinstance(inv_cfg, dict):
                    for fcfg in inv_cfg.get("felder", inv_cfg).values():
                        if isinstance(fcfg, dict) and fcfg.get("strategie") == "sensor" and fcfg.get("sensor_id"):
                            all_sensor_ids.append(fcfg["sensor_id"])
            if all_sensor_ids:
                try:
                    stats_result = await asyncio.to_thread(ha_stats_svc.get_monatswerte, all_sensor_ids, jahr, monat)
                    ha_stats_werte = {s.sensor_id: s.differenz for s in stats_result.sensoren if s.differenz is not None}
                except Exception:
                    logger.warning("HA Statistics DB nicht erreichbar für Monatsabschluss-Vorschläge")

    # Datenquelle des Monats ermitteln
    datenquelle = getattr(monatsdaten, "datenquelle", None) if monatsdaten else None

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

        # Quelle bestimmen
        quelle = None
        if aktueller_wert is not None:
            quelle = datenquelle if datenquelle else "manuell"

        # Vorschläge holen (historische Daten)
        vorschlaege = await vorschlag_service.get_vorschlaege(
            anlage_id, feld, jahr, monat
        )

        # Bei konfiguriertem Sensor: HA Statistics Wert als Vorschlag hinzufügen
        if strategie == "sensor" and sensor_id and sensor_id in ha_stats_werte:
            stats_wert = ha_stats_werte[sensor_id]
            if stats_wert > 0:
                vorschlaege.insert(0, Vorschlag(
                    wert=round(stats_wert, 1),
                    quelle=VorschlagQuelle.HA_STATISTICS,
                    konfidenz=92,
                    beschreibung="Aus HA-Statistik (Recorder-DB)",
                ))

        # Connector-Vorschlag einfügen
        if connector_delta and feld in connector_delta:
            conn_wert = connector_delta[feld]
            if conn_wert is not None and conn_wert > 0:
                vorschlaege.insert(0, Vorschlag(
                    wert=round(conn_wert, 1),
                    quelle=VorschlagQuelle.LOCAL_CONNECTOR,
                    konfidenz=90,
                    beschreibung="Vom Wechselrichter (Zählerstand-Differenz)",
                ))

        # MQTT Inbound-Vorschlag einfügen (Konfidenz 91)
        if feld in mqtt_energy:
            vorschlaege.insert(0, Vorschlag(
                wert=mqtt_energy[feld],
                quelle=VorschlagQuelle.MQTT_INBOUND,
                konfidenz=91,
                beschreibung="Aus MQTT Energy-Topics (Monatswerte)",
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
            quelle=quelle,
            vorschlaege=[_vorschlag_to_response(v) for v in vorschlaege],
            warnungen=[_warnung_to_response(w) for w in warnungen],
            strategie=strategie,
            sensor_id=sensor_id,
        ))

    # Dynamischer Tarif: Durchschnittspreis-Feld bedingt hinzufügen
    tarife = await lade_tarife_fuer_anlage(db, anlage_id)
    allgemein_tarif = tarife.get("allgemein")
    if allgemein_tarif and allgemein_tarif.vertragsart == "dynamisch":
        feld = "netzbezug_durchschnittspreis_cent"
        aktueller_wert = getattr(monatsdaten, feld, None) if monatsdaten else None

        # HA-Sensor-Vorschlag: Direktes Lesen (kein MWD)
        strompreis_vorschlaege: list[VorschlagResponse] = []
        strompreis_mapping = basis_mapping.get("strompreis", {})
        strompreis_strategie = strompreis_mapping.get("strategie") if strompreis_mapping else None
        strompreis_sensor_id = strompreis_mapping.get("sensor_id") if strompreis_mapping else None

        if strompreis_strategie == "sensor" and strompreis_sensor_id:
            ha_state_svc = get_ha_state_service()
            sensor_wert = await ha_state_svc.get_sensor_state(strompreis_sensor_id)
            if sensor_wert is not None:
                strompreis_vorschlaege.append(VorschlagResponse(
                    wert=round(sensor_wert, 2),
                    quelle="ha_sensor",
                    konfidenz=90,
                    beschreibung="Aus HA-Sensor (Ø Strompreis)",
                ))

        basis_felder.append(FeldStatus(
            feld=feld,
            label="Ø Strompreis",
            einheit="ct/kWh",
            aktueller_wert=aktueller_wert,
            quelle="manuell" if aktueller_wert else None,
            vorschlaege=strompreis_vorschlaege,
            warnungen=[],
            strategie=strompreis_strategie,
            sensor_id=strompreis_sensor_id,
        ))

    # Investitionen aufbereiten
    investitionen_status: list[InvestitionStatus] = []
    for inv in anlage.investitionen:
        # Felder für diese Investition auflösen (Bedingungen berücksichtigen)
        felder_config = get_felder_fuer_investition(inv.typ, inv.parameter, anlage_investitionen=anlage.investitionen)
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

        # Mapping für diese Investition - beachte die verschachtelte Struktur {"felder": {...}}
        inv_mapping_raw = inv_mappings.get(str(inv.id), {})
        inv_mapping = inv_mapping_raw.get("felder", inv_mapping_raw) if isinstance(inv_mapping_raw, dict) else {}

        felder: list[FeldStatus] = []
        for feld_config in felder_config:
            feld = feld_config["feld"]
            aktueller_wert = verbrauch_daten.get(feld)

            # Mapping-Info
            feld_mapping = inv_mapping.get(feld, {})
            strategie = feld_mapping.get("strategie") if feld_mapping else None
            sensor_id = feld_mapping.get("sensor_id") if feld_mapping else None

            # Vorschläge holen (historische Daten)
            vorschlaege = await vorschlag_service.get_vorschlaege(
                anlage_id, feld, jahr, monat, investition_id=inv.id
            )

            # Bei konfiguriertem Sensor: HA Statistics Wert als Vorschlag hinzufügen
            if strategie == "sensor" and sensor_id and sensor_id in ha_stats_werte:
                stats_wert = ha_stats_werte[sensor_id]
                if stats_wert > 0:
                    vorschlaege.insert(0, Vorschlag(
                        wert=round(stats_wert, 1),
                        quelle=VorschlagQuelle.HA_STATISTICS,
                        konfidenz=92,
                        beschreibung="Aus HA-Statistik (Recorder-DB)",
                    ))

            # Connector-Vorschlag einfügen (verteilte Werte)
            inv_conn_values = connector_inv_verteilung.get(inv.id, {})
            if feld in inv_conn_values:
                conn_wert = inv_conn_values[feld]
                if conn_wert > 0:
                    vorschlaege.insert(0, Vorschlag(
                        wert=round(conn_wert, 1),
                        quelle=VorschlagQuelle.LOCAL_CONNECTOR,
                        konfidenz=90,
                        beschreibung="Vom Wechselrichter (Zählerstand-Differenz)",
                    ))

            # MQTT Inbound-Vorschlag einfügen (Konfidenz 91)
            mqtt_inv_values = mqtt_inv_energy.get(inv.id, {})
            if feld in mqtt_inv_values:
                vorschlaege.insert(0, Vorschlag(
                    wert=mqtt_inv_values[feld],
                    quelle=VorschlagQuelle.MQTT_INBOUND,
                    konfidenz=91,
                    beschreibung="Aus MQTT Energy-Topics (Monatswerte)",
                ))

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
                quelle=(datenquelle or "manuell") if aktueller_wert is not None else None,
                vorschlaege=[_vorschlag_to_response(v) for v in vorschlaege],
                warnungen=[_warnung_to_response(w) for w in warnungen],
                strategie=strategie,
                sensor_id=sensor_id,
            ))

        # sonstige_positionen aus verbrauch_daten lesen (für alle Typen)
        inv_sonstige_pos = []
        if verbrauch_daten and isinstance(verbrauch_daten.get("sonstige_positionen"), list):
            inv_sonstige_pos = verbrauch_daten["sonstige_positionen"]

        # Kategorie nur für Typ "sonstiges" relevant
        inv_kategorie = (inv.parameter or {}).get("kategorie") if inv.typ == "sonstiges" else None

        investitionen_status.append(InvestitionStatus(
            id=inv.id,
            typ=inv.typ,
            bezeichnung=inv.bezeichnung,
            felder=felder,
            kategorie=inv_kategorie,
            sonstige_positionen=inv_sonstige_pos,
        ))

    # Optionale Felder aufbereiten (manuelle Eingaben, nicht aus HA)
    optionale_felder: list[FeldStatus] = []
    for feld_config in OPTIONALE_FELDER:
        feld = feld_config["feld"]
        feld_typ = feld_config.get("typ", "number")

        if feld_typ == "text":
            aktueller_text = getattr(monatsdaten, feld, None) if monatsdaten else None
            optionale_felder.append(FeldStatus(
                feld=feld,
                label=feld_config["label"],
                einheit=feld_config["einheit"],
                aktueller_text=aktueller_text,
                quelle="manuell" if aktueller_text else None,
                typ="text",
            ))
        else:
            aktueller_wert = getattr(monatsdaten, feld, None) if monatsdaten else None
            optionale_felder.append(FeldStatus(
                feld=feld,
                label=feld_config["label"],
                einheit=feld_config["einheit"],
                aktueller_wert=aktueller_wert,
                quelle="manuell" if aktueller_wert is not None else None,
                typ="number",
            ))

    return MonatsabschlussResponse(
        anlage_id=anlage_id,
        anlage_name=anlage.anlagenname,
        jahr=jahr,
        monat=monat,
        ist_abgeschlossen=monatsdaten is not None,
        ha_mapping_konfiguriert=bool(sensor_mapping),
        connector_konfiguriert=connector_konfiguriert,
        cloud_import_konfiguriert=cloud_import_konfiguriert,
        mqtt_inbound_konfiguriert=bool(mqtt_energy or mqtt_inv_energy),
        portal_import_vorhanden=datenquelle == "portal_import",
        datenquelle=datenquelle,
        basis_felder=basis_felder,
        optionale_felder=optionale_felder,
        investitionen=investitionen_status,
    )


class CloudMonatswertFeld(BaseModel):
    feld: str
    label: str
    wert: float
    einheit: str


class CloudMonatswerteResponse(BaseModel):
    basis: list[CloudMonatswertFeld]
    investitionen: list[dict]


@router.post("/{anlage_id}/{jahr}/{monat}/cloud-fetch", response_model=CloudMonatswerteResponse)
async def fetch_cloud_monatswerte(
    anlage_id: int,
    jahr: int,
    monat: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Ruft Monatswerte für einen einzelnen Monat aus der Cloud-API ab.
    Verwendet gespeicherte Credentials. Gibt Werte zurück ohne in DB zu schreiben.
    """
    result = await db.execute(
        select(Anlage)
        .options(selectinload(Anlage.investitionen))
        .where(Anlage.id == anlage_id)
    )
    anlage = result.scalar_one_or_none()
    if not anlage:
        raise HTTPException(status_code=404, detail="Anlage nicht gefunden")

    config = (anlage.connector_config or {}).get("cloud_import", {})
    provider_id = config.get("provider_id")
    credentials = config.get("credentials", {})
    if not provider_id or not credentials:
        raise HTTPException(status_code=400, detail="Keine Cloud-Import Credentials konfiguriert")

    from backend.services.cloud_import import get_provider
    try:
        provider = get_provider(provider_id)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unbekannter Cloud-Provider: {provider_id}")

    try:
        months = await provider.fetch_monthly_data(credentials, jahr, monat, jahr, monat)
    except Exception as e:
        await log_activity(
            kategorie="cloud_fetch",
            aktion=f"Cloud-Fetch für {monat:02d}/{jahr} fehlgeschlagen",
            erfolg=False,
            details=str(e),
            anlage_id=anlage_id,
        )
        raise HTTPException(status_code=400, detail=f"Cloud-Abruf fehlgeschlagen: {str(e)}")

    if not months:
        raise HTTPException(status_code=404, detail="Keine Daten für diesen Monat in der Cloud gefunden")

    month_data = months[0]

    # Basis-Felder
    basis: list[CloudMonatswertFeld] = []
    for feld, label, einheit in [
        ("einspeisung_kwh", "Einspeisung", "kWh"),
        ("netzbezug_kwh", "Netzbezug", "kWh"),
    ]:
        val = getattr(month_data, feld, None)
        if val is not None:
            basis.append(CloudMonatswertFeld(feld=feld, label=label, wert=round(val, 1), einheit=einheit))

    # Investitionen: PV auf Module, Batterie auf Speicher verteilen
    inv_result: list[dict] = []
    from backend.api.routes.connector import _distribute_by_param

    pv_kwh = getattr(month_data, "pv_erzeugung_kwh", None)
    if pv_kwh and pv_kwh > 0:
        pv_module = [i for i in anlage.investitionen if i.typ == "pv-module"]
        if pv_module:
            for inv, anteil in _distribute_by_param(pv_module, pv_kwh, "leistung_kwp"):
                inv_result.append({
                    "investition_id": inv.id,
                    "bezeichnung": inv.bezeichnung,
                    "typ": inv.typ,
                    "felder": [{"feld": "pv_erzeugung_kwh", "label": "PV Erzeugung", "wert": round(anteil, 1), "einheit": "kWh"}],
                })

    for cloud_feld, inv_feld, label in [
        ("batterie_ladung_kwh", "ladung_kwh", "Ladung"),
        ("batterie_entladung_kwh", "entladung_kwh", "Entladung"),
    ]:
        bat_val = getattr(month_data, cloud_feld, None)
        if bat_val and bat_val > 0:
            speicher = [i for i in anlage.investitionen if i.typ == "speicher"]
            if speicher:
                for inv, anteil in _distribute_by_param(speicher, bat_val, "kapazitaet_kwh"):
                    existing = next((r for r in inv_result if r["investition_id"] == inv.id), None)
                    if existing:
                        existing["felder"].append({"feld": inv_feld, "label": label, "wert": round(anteil, 1), "einheit": "kWh"})
                    else:
                        inv_result.append({
                            "investition_id": inv.id,
                            "bezeichnung": inv.bezeichnung,
                            "typ": inv.typ,
                            "felder": [{"feld": inv_feld, "label": label, "wert": round(anteil, 1), "einheit": "kWh"}],
                        })

    await log_activity(
        kategorie="cloud_fetch",
        aktion=f"Cloud-Daten für {monat:02d}/{jahr} abgerufen",
        erfolg=True,
        details=f"Provider: {provider_id}, {len(basis)} Basis-Felder, {len(inv_result)} Investitionen",
        anlage_id=anlage_id,
    )

    return CloudMonatswerteResponse(basis=basis, investitionen=inv_result)


async def _post_save_hintergrund(
    anlage_id: int,
    jahr: int,
    monat: int,
    monatsdaten_dict: dict,
    community_auto_share: bool,
    community_hash: str | None,
) -> None:
    """MQTT-Publish, Energie-Profil Rollup und Community Auto-Share im Hintergrund."""
    from datetime import timedelta
    from sqlalchemy import update as sql_update
    from backend.services.energie_profil_service import (
        rollup_month, backfill_range, resolve_and_backfill_from_statistics,
    )

    # 1. MQTT Publish
    mqtt_sync = get_ha_mqtt_sync_service()
    try:
        await mqtt_sync.publish_final_month_data(anlage_id, jahr, monat, monatsdaten_dict)
    except Exception as e:
        logger.warning(f"MQTT-Publish fehlgeschlagen: {type(e).__name__}: {e}")

    # 2. Energie-Profil: Closing-Month-Backfill + Rollup + einmaliger Auto-Vollbackfill
    async with async_session_maker() as db:
        result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
        anlage = result.scalar_one_or_none()
        if anlage is None:
            return

        erster_tag = date(jahr, monat, 1)
        letzter_tag = date(jahr + 1, 1, 1) - timedelta(days=1) if monat == 12 \
            else date(jahr, monat + 1, 1) - timedelta(days=1)

        try:
            backfill_count = await backfill_range(anlage, erster_tag, letzter_tag, db)
            if backfill_count > 0:
                await db.commit()
            await rollup_month(anlage_id, jahr, monat, db)
            await db.commit()
        except Exception as e:
            logger.warning(f"Energie-Profil Rollup fehlgeschlagen: {type(e).__name__}: {e}")

        # Einmaliger Auto-Vollbackfill aus HA Long-Term Statistics. Läuft genau einmal
        # pro Anlage beim ersten Monatsabschluss nach Upgrade. Doppelläufe mit dem
        # Closing-Month-Backfill oben sind idempotent durch skip_existing in
        # backfill_from_statistics. Flag wird IMMER gesetzt — auch bei Fehler — sonst
        # Endlos-Retry bei defekter HA-DB.
        if not anlage.vollbackfill_durchgefuehrt:
            try:
                backfill = await resolve_and_backfill_from_statistics(
                    anlage, db, bis=letzter_tag,
                )
                if backfill.missing_eids:
                    logger.warning(
                        f"Auto-Vollbackfill Anlage {anlage_id}: "
                        f"{len(backfill.missing_eids)} Sensor(en) ignoriert: {backfill.missing_eids}"
                    )
                if backfill.status == "ok":
                    logger.info(
                        f"Auto-Vollbackfill Anlage {anlage_id}: "
                        f"{backfill.geschrieben}/{backfill.verarbeitet} Tage von "
                        f"{backfill.von} bis {backfill.bis}"
                    )
                else:
                    logger.info(f"Auto-Vollbackfill Anlage {anlage_id} übersprungen: {backfill.detail}")
            except Exception as e:
                logger.warning(f"Auto-Vollbackfill Anlage {anlage_id} Fehler: {type(e).__name__}: {e}")
                await db.rollback()

            # Direktes UPDATE statt ORM-Attribut: robust gegen abgebrochene Session
            await db.execute(
                sql_update(Anlage)
                .where(Anlage.id == anlage_id)
                .values(vollbackfill_durchgefuehrt=True)
            )
            await db.commit()

    # 3. Community Auto-Share
    if community_auto_share:
        async with async_session_maker() as db:
            try:
                from backend.services.community_service import prepare_community_data, COMMUNITY_SERVER_URL
                import httpx
                share_data = await prepare_community_data(db, anlage_id)
                if share_data and share_data.get("monatswerte"):
                    async with httpx.AsyncClient(timeout=15.0) as client:
                        resp = await client.post(f"{COMMUNITY_SERVER_URL}/api/submit", json=share_data)
                        if resp.status_code == 200:
                            result_data = resp.json()
                            if result_data.get("anlage_hash") and not community_hash:
                                result2 = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
                                anlage_obj = result2.scalar_one_or_none()
                                if anlage_obj:
                                    anlage_obj.community_hash = result_data["anlage_hash"]
                                    await db.commit()
                            logger.info(f"Auto-Share für Anlage {anlage_id} erfolgreich")
                        else:
                            logger.warning(f"Auto-Share HTTP {resp.status_code}: {resp.text[:200]}")
            except Exception as e:
                logger.warning(f"Auto-Share fehlgeschlagen: {type(e).__name__}: {e}")


@router.post("/{anlage_id}/{jahr}/{monat}", response_model=MonatsabschlussResult)
async def save_monatsabschluss(
    anlage_id: int,
    jahr: int,
    monat: int,
    daten: MonatsabschlussInput,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """
    Speichert Monatsdaten.

    Ablauf:
    1. Validierung + Plausibilitätsprüfung
    2. Speichern in Monatsdaten + InvestitionMonatsdaten
    3. Optional: Startwerte für nächsten Monat auf MQTT publizieren
    """
    logger.info(
        f"Monatsabschluss speichern: Anlage {anlage_id}, {monat:02d}/{jahr}, "
        f"Basis: einspeisung={daten.einspeisung_kwh}, netzbezug={daten.netzbezug_kwh}, "
        f"Investitionen: {len(daten.investitionen)} Stück"
    )
    for inv_w in daten.investitionen:
        logger.info(
            f"  Investition {inv_w.investition_id}: "
            f"{len(inv_w.felder)} Felder [{', '.join(f'{f.feld}={f.wert}' for f in inv_w.felder)}]"
        )

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
    if daten.netzbezug_durchschnittspreis_cent is not None:
        monatsdaten.netzbezug_durchschnittspreis_cent = daten.netzbezug_durchschnittspreis_cent
    if daten.sonderkosten_euro is not None:
        monatsdaten.sonderkosten_euro = daten.sonderkosten_euro
    if daten.sonderkosten_beschreibung is not None:
        monatsdaten.sonderkosten_beschreibung = daten.sonderkosten_beschreibung
    if daten.notizen is not None:
        monatsdaten.notizen = daten.notizen
    if daten.datenquelle:
        monatsdaten.datenquelle = daten.datenquelle

    try:
        await db.flush()
    except Exception as e:
        logger.error(f"Monatsabschluss flush Monatsdaten fehlgeschlagen: {type(e).__name__}: {e}")
        raise HTTPException(status_code=500, detail=f"Fehler beim Speichern der Monatsdaten: {e}")
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
                jahr=jahr,
                monat=monat,
                verbrauch_daten={},
            )
            db.add(imd)

        # Felder in verbrauch_daten speichern
        verbrauch_daten = imd.verbrauch_daten or {}
        for feld_wert in inv_werte.felder:
            verbrauch_daten[feld_wert.feld] = feld_wert.wert

        # Sonstige Positionen (Erträge & Ausgaben) speichern
        if inv_werte.sonstige_positionen is not None:
            gueltige = [
                p for p in inv_werte.sonstige_positionen
                if isinstance(p, dict) and p.get("betrag", 0) > 0 and str(p.get("bezeichnung", "")).strip()
            ]
            verbrauch_daten["sonstige_positionen"] = gueltige

        imd.verbrauch_daten = verbrauch_daten
        flag_modified(imd, "verbrauch_daten")

        try:
            await db.flush()
        except Exception as e:
            logger.error(f"Monatsabschluss flush Investition {inv_werte.investition_id} fehlgeschlagen: {type(e).__name__}: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Fehler beim Speichern der Investition {inv_werte.investition_id}: {e}"
            )
        inv_ids.append(imd.id)

    try:
        await db.commit()
    except Exception as e:
        logger.error(f"Monatsabschluss commit fehlgeschlagen: {type(e).__name__}: {e}")
        raise HTTPException(status_code=500, detail=f"Fehler beim Commit: {e}")

    # MQTT, Energie-Profil Rollup und Community Auto-Share im Hintergrund
    background_tasks.add_task(
        _post_save_hintergrund,
        anlage_id=anlage_id,
        jahr=jahr,
        monat=monat,
        monatsdaten_dict={
            "jahr": jahr,
            "monat": monat,
            "einspeisung_kwh": daten.einspeisung_kwh,
            "netzbezug_kwh": daten.netzbezug_kwh,
        },
        community_auto_share=bool(anlage.community_auto_share),
        community_hash=anlage.community_hash,
    )

    await log_activity(
        kategorie="monatsabschluss",
        aktion=f"Monatsabschluss {MONAT_NAMEN[monat]} {jahr} gespeichert",
        erfolg=True,
        anlage_id=anlage_id,
    )

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
        ha_mapping_konfiguriert=bool(sensor_mapping),
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
