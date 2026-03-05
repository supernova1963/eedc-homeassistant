"""
Connector API Routes.

Endpoints für die direkte Verbindung zu Wechselrichtern/Energiemanagement-Systemen
über deren lokale REST-API.
"""

import base64
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.attributes import flag_modified

from backend.api.deps import get_db
from backend.models.anlage import Anlage
from backend.models.investition import Investition
from backend.services.connectors import list_connectors, get_connector

logger = logging.getLogger(__name__)

router = APIRouter()


# =============================================================================
# Schemas
# =============================================================================

class ConnectorTestRequest(BaseModel):
    """Request für Verbindungstest."""
    connector_id: str
    host: str
    username: str = "User"
    password: str


class ConnectorSetupRequest(BaseModel):
    """Request zum Einrichten eines Connectors."""
    connector_id: str
    host: str
    username: str = "User"
    password: str


# =============================================================================
# Helper
# =============================================================================

def _encode_password(password: str) -> str:
    """Base64-Encoding für Passwort-Speicherung."""
    return base64.b64encode(password.encode()).decode()


def _decode_password(encoded: str) -> str:
    """Base64-Decoding für Passwort."""
    return base64.b64decode(encoded.encode()).decode()


async def _get_anlage(anlage_id: int, db: AsyncSession) -> Anlage:
    """Lädt eine Anlage oder wirft 404."""
    result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    anlage = result.scalar_one_or_none()
    if not anlage:
        raise HTTPException(status_code=404, detail="Anlage nicht gefunden")
    return anlage


# =============================================================================
# Endpoints
# =============================================================================

@router.get("")
async def get_connectors():
    """Verfügbare Connector-Typen auflisten."""
    return [c.to_dict() for c in list_connectors()]


@router.post("/test")
async def test_connection(req: ConnectorTestRequest):
    """
    Verbindung zu einem Gerät testen (ohne zu speichern).

    Gibt Geräteinfo, verfügbare Sensoren und aktuelle Zählerstände zurück.
    """
    try:
        connector = get_connector(req.connector_id)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unbekannter Connector: {req.connector_id}")

    result = await connector.test_connection(req.host, req.username, req.password)
    return result.to_dict()


@router.post("/setup/{anlage_id}")
async def setup_connector(
    anlage_id: int,
    req: ConnectorSetupRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Connector für eine Anlage einrichten und initialen Snapshot speichern.
    """
    anlage = await _get_anlage(anlage_id, db)

    try:
        connector = get_connector(req.connector_id)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unbekannter Connector: {req.connector_id}")

    # Verbindung testen + initialen Snapshot holen
    test_result = await connector.test_connection(req.host, req.username, req.password)
    if not test_result.erfolg:
        raise HTTPException(
            status_code=400,
            detail=f"Verbindung fehlgeschlagen: {test_result.fehler}",
        )

    # Connector-Config erstellen
    now = datetime.now(timezone.utc).isoformat()
    config: dict = {
        "connector_id": req.connector_id,
        "host": req.host,
        "username": req.username,
        "password": _encode_password(req.password),
        "geraet_name": test_result.geraet_name,
        "geraet_typ": test_result.geraet_typ,
        "seriennummer": test_result.seriennummer,
        "firmware": test_result.firmware,
        "auto_fetch_enabled": False,
        "meter_snapshots": {},
        "last_fetch": now,
    }

    # Initialen Snapshot speichern
    if test_result.aktuelle_werte:
        config["meter_snapshots"][now] = test_result.aktuelle_werte.to_dict()

    anlage.connector_config = config
    flag_modified(anlage, "connector_config")

    logger.info(
        f"Connector '{req.connector_id}' für Anlage {anlage_id} eingerichtet "
        f"(Gerät: {test_result.geraet_name}, SN: {test_result.seriennummer})"
    )

    return {
        "erfolg": True,
        "geraet_name": test_result.geraet_name,
        "seriennummer": test_result.seriennummer,
        "aktuelle_werte": test_result.aktuelle_werte.to_dict() if test_result.aktuelle_werte else None,
    }


@router.get("/status/{anlage_id}")
async def get_connector_status(
    anlage_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Connector-Status und gespeicherte Snapshots einer Anlage."""
    anlage = await _get_anlage(anlage_id, db)

    config = anlage.connector_config
    if not config:
        return {"configured": False}

    # Passwort nie an Frontend senden
    snapshots = config.get("meter_snapshots", {})

    return {
        "configured": True,
        "connector_id": config.get("connector_id"),
        "host": config.get("host"),
        "username": config.get("username"),
        "geraet_name": config.get("geraet_name"),
        "geraet_typ": config.get("geraet_typ"),
        "seriennummer": config.get("seriennummer"),
        "firmware": config.get("firmware"),
        "auto_fetch_enabled": config.get("auto_fetch_enabled", False),
        "last_fetch": config.get("last_fetch"),
        "snapshot_count": len(snapshots),
        "latest_snapshot": _get_latest_snapshot(snapshots),
    }


@router.post("/fetch/{anlage_id}")
async def fetch_meters(
    anlage_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Zählerstand manuell vom Gerät ablesen.

    Speichert neuen Snapshot und berechnet Differenz zum vorherigen Snapshot.
    """
    anlage = await _get_anlage(anlage_id, db)

    config = anlage.connector_config
    if not config:
        raise HTTPException(status_code=400, detail="Kein Connector konfiguriert")

    connector_id = config.get("connector_id")
    try:
        connector = get_connector(connector_id)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unbekannter Connector: {connector_id}")

    host = config.get("host")
    username = config.get("username", "User")
    password = _decode_password(config.get("password", ""))

    # Zählerstand lesen
    try:
        snapshot = await connector.read_meters(host, username, password)
    except Exception as e:
        logger.exception(f"Fehler beim Auslesen: {e}")
        raise HTTPException(
            status_code=502,
            detail=f"Fehler beim Auslesen: {type(e).__name__}: {str(e)}",
        )

    # Snapshot speichern
    now = datetime.now(timezone.utc).isoformat()
    snapshots = config.get("meter_snapshots", {})

    # Differenz zum letzten Snapshot berechnen
    prev_snapshot = _get_latest_snapshot(snapshots)
    differenz = None
    if prev_snapshot:
        differenz = _calc_difference(prev_snapshot, snapshot.to_dict())

    snapshots[now] = snapshot.to_dict()
    config["meter_snapshots"] = snapshots
    config["last_fetch"] = now

    anlage.connector_config = config
    flag_modified(anlage, "connector_config")

    return {
        "snapshot": snapshot.to_dict(),
        "differenz": differenz,
        "timestamp": now,
    }


@router.delete("/{anlage_id}")
async def remove_connector(
    anlage_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Connector-Konfiguration einer Anlage entfernen."""
    anlage = await _get_anlage(anlage_id, db)

    if not anlage.connector_config:
        raise HTTPException(status_code=400, detail="Kein Connector konfiguriert")

    anlage.connector_config = None
    flag_modified(anlage, "connector_config")

    logger.info(f"Connector für Anlage {anlage_id} entfernt")

    return {"erfolg": True}


@router.get("/monatswerte/{anlage_id}/{jahr}/{monat}")
async def get_connector_monatswerte(
    anlage_id: int,
    jahr: int,
    monat: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Berechnet Monatswerte aus Connector-Snapshots.

    Findet zwei Snapshots die den Monat umrahmen und berechnet die Differenz.
    Verteilt System-Level-Werte auf Investitionen (PV-Module nach kWp,
    Speicher nach Kapazität).

    Returns:
        Format kompatibel mit HA-Statistics Monatswerte (basis + investitionen).
    """
    result = await db.execute(
        select(Anlage)
        .options(selectinload(Anlage.investitionen))
        .where(Anlage.id == anlage_id)
    )
    anlage = result.scalar_one_or_none()
    if not anlage:
        raise HTTPException(status_code=404, detail="Anlage nicht gefunden")

    config = anlage.connector_config
    if not config:
        raise HTTPException(status_code=400, detail="Kein Connector konfiguriert")

    snapshots = config.get("meter_snapshots", {})
    if not snapshots:
        raise HTTPException(status_code=404, detail="Keine Snapshots vorhanden")

    # Snapshots die den Monat umrahmen finden
    diff = _calc_month_delta(snapshots, jahr, monat)
    if not diff:
        raise HTTPException(
            status_code=404,
            detail=f"Nicht genügend Snapshots für {monat:02d}/{jahr}. "
            "Mindestens ein Snapshot vor und einer nach dem Monatsbeginn nötig."
        )

    # System-Level-Werte auf Investitionen verteilen
    basis_felder = []
    investitionen_felder = []

    # Basis-Felder (direkt auf Monatsdaten)
    for feld, label in [
        ("einspeisung_kwh", "Einspeisung"),
        ("netzbezug_kwh", "Netzbezug"),
    ]:
        if feld in diff:
            basis_felder.append({
                "feld": feld,
                "label": label,
                "wert": diff[feld],
                "einheit": "kWh",
            })

    # PV-Erzeugung auf Module verteilen
    pv_kwh = diff.get("pv_erzeugung_kwh")
    if pv_kwh is not None and pv_kwh > 0:
        pv_module = [i for i in anlage.investitionen if i.typ == "pv-module"]
        if pv_module:
            verteilung = _distribute_by_param(pv_module, pv_kwh, "leistung_kwp")
            for inv, anteil in verteilung:
                investitionen_felder.append({
                    "investition_id": inv.id,
                    "bezeichnung": inv.bezeichnung,
                    "typ": inv.typ,
                    "felder": [{"feld": "pv_erzeugung_kwh", "label": "PV Erzeugung", "wert": anteil, "einheit": "kWh"}],
                })

    # Batterie auf Speicher verteilen
    bat_ladung = diff.get("batterie_ladung_kwh")
    bat_entladung = diff.get("batterie_entladung_kwh")
    if (bat_ladung is not None and bat_ladung > 0) or (bat_entladung is not None and bat_entladung > 0):
        speicher = [i for i in anlage.investitionen if i.typ == "speicher"]
        if speicher:
            felder_per_speicher: dict[int, list] = {}
            if bat_ladung is not None and bat_ladung > 0:
                for inv, anteil in _distribute_by_param(speicher, bat_ladung, "kapazitaet_kwh"):
                    felder_per_speicher.setdefault(inv.id, {"inv": inv, "felder": []})
                    felder_per_speicher[inv.id]["felder"].append(
                        {"feld": "ladung_kwh", "label": "Ladung", "wert": anteil, "einheit": "kWh"}
                    )
            if bat_entladung is not None and bat_entladung > 0:
                for inv, anteil in _distribute_by_param(speicher, bat_entladung, "kapazitaet_kwh"):
                    felder_per_speicher.setdefault(inv.id, {"inv": inv, "felder": []})
                    felder_per_speicher[inv.id]["felder"].append(
                        {"feld": "entladung_kwh", "label": "Entladung", "wert": anteil, "einheit": "kWh"}
                    )
            for data in felder_per_speicher.values():
                inv = data["inv"]
                # Prüfen ob bereits ein Eintrag für diese Investition existiert
                existing = next((i for i in investitionen_felder if i["investition_id"] == inv.id), None)
                if existing:
                    existing["felder"].extend(data["felder"])
                else:
                    investitionen_felder.append({
                        "investition_id": inv.id,
                        "bezeichnung": inv.bezeichnung,
                        "typ": inv.typ,
                        "felder": data["felder"],
                    })

    return {
        "basis": basis_felder,
        "investitionen": investitionen_felder,
    }


# =============================================================================
# Helper Functions
# =============================================================================

def _get_latest_snapshot(snapshots: dict) -> Optional[dict]:
    """Gibt den neuesten Snapshot zurück (nach Timestamp sortiert)."""
    if not snapshots:
        return None
    latest_key = max(snapshots.keys())
    return snapshots[latest_key]


def _calc_difference(prev: dict, current: dict) -> dict:
    """Berechnet die Differenz zwischen zwei kumulativen Snapshots (in kWh)."""
    fields = [
        "pv_erzeugung_kwh",
        "einspeisung_kwh",
        "netzbezug_kwh",
        "batterie_ladung_kwh",
        "batterie_entladung_kwh",
    ]
    diff: dict = {}
    for field in fields:
        curr_val = current.get(field)
        prev_val = prev.get(field)
        if curr_val is not None and prev_val is not None:
            diff[field] = round(curr_val - prev_val, 2)
    return diff


def _calc_month_delta(snapshots: dict, jahr: int, monat: int) -> Optional[dict]:
    """Berechnet die Monatsdifferenz aus verfügbaren Snapshots.

    Sucht den letzten Snapshot VOR dem Monat als Start und den letzten
    Snapshot IM Monat (oder den ersten danach) als Ende.

    Returns:
        Dict mit Felddifferenzen oder None wenn nicht genug Snapshots.
    """
    from datetime import datetime as dt

    monat_start = dt(jahr, monat, 1)
    if monat == 12:
        monat_ende = dt(jahr + 1, 1, 1)
    else:
        monat_ende = dt(jahr, monat + 1, 1)

    # Snapshots sortiert mit Timestamps
    sorted_snaps = []
    for ts_str, snap in snapshots.items():
        try:
            ts = dt.fromisoformat(ts_str.replace("Z", "+00:00")).replace(tzinfo=None)
            sorted_snaps.append((ts, snap))
        except (ValueError, TypeError):
            continue

    sorted_snaps.sort(key=lambda x: x[0])
    if len(sorted_snaps) < 2:
        return None

    # Start-Snapshot: letzter VOR dem Monat, oder erster im Monat
    start_snap = None
    for ts, snap in sorted_snaps:
        if ts < monat_start:
            start_snap = snap
        elif ts <= monat_ende and start_snap is None:
            start_snap = snap
            break

    # End-Snapshot: letzter IM Monat, oder erster danach
    end_snap = None
    for ts, snap in sorted_snaps:
        if monat_start <= ts < monat_ende:
            end_snap = snap  # Letzter im Monat
        elif ts >= monat_ende and end_snap is None:
            end_snap = snap
            break

    if not start_snap or not end_snap or start_snap is end_snap:
        return None

    return _calc_difference(start_snap, end_snap)


def _distribute_by_param(
    investitionen: list,
    total: float,
    param_key: str,
) -> list[tuple]:
    """Verteilt einen Gesamtwert proportional auf Investitionen nach Parameter.

    Args:
        investitionen: Liste von Investition-Objekten
        total: Zu verteilender Gesamtwert
        param_key: Schlüssel im parameter-Dict (z.B. "leistung_kwp", "kapazitaet_kwh")

    Returns:
        Liste von (Investition, anteil) Tupeln
    """
    total_param = sum(
        (inv.parameter or {}).get(param_key, 0) or 0
        for inv in investitionen
    )

    result = []
    for inv in investitionen:
        inv_param = (inv.parameter or {}).get(param_key, 0) or 0
        if total_param > 0:
            anteil = round(total * inv_param / total_param, 2)
        else:
            anteil = round(total / len(investitionen), 2)
        result.append((inv, anteil))
    return result
