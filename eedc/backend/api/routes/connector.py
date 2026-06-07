"""
Connector API Routes.

Endpoints für die direkte Verbindung zu Wechselrichtern/Energiemanagement-Systemen
über deren lokale REST-API.
"""

import base64
import ipaddress
import logging
import socket
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.attributes import flag_modified

from backend.core.exceptions import not_found
from backend.api.deps import get_db
from backend.models.anlage import Anlage
from backend.models.investition import Investition
from backend.services.connectors import list_connectors, get_connector
from backend.services.activity_service import log_activity

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


class ConnectorMappingRequest(BaseModel):
    """Request zum Zuordnen der Mess-Kategorien zu Investitionen.

    `field_inv_map`: {"pv": inv_id, "speicher": inv_id, "wallbox": inv_id}.
    Ein Wert von `null` entfernt die Zuordnung der Kategorie. Grid
    (Einspeisung/Netzbezug) ist anlagenweit und nicht zuordenbar.
    """
    field_inv_map: dict[str, Optional[int]]


# Mess-Kategorie → erlaubte Investitions-Typen (Validierung der Zuordnung).
_KATEGORIE_TYPEN = {
    "pv": {"pv-module", "balkonkraftwerk"},
    "speicher": {"speicher"},
    "wallbox": {"wallbox"},
}


# =============================================================================
# Helper
# =============================================================================

def _encode_password(password: str) -> str:
    """Base64-Encoding für Passwort-Speicherung."""
    return base64.b64encode(password.encode()).decode()


def _decode_password(encoded: str) -> str:
    """Base64-Decoding für Passwort."""
    return base64.b64decode(encoded.encode()).decode()


def _extract_hostname(host: str) -> Optional[str]:
    """Extrahiert den reinen Hostnamen aus einer URL oder einem Bare-Host-String.

    `https://192.168.1.50:80/api` → `192.168.1.50`
    `192.168.1.50:80` → `192.168.1.50`
    `wechselrichter.lan` → `wechselrichter.lan`
    """
    if not host:
        return None
    parsed = urlparse(host if "://" in host else f"//{host}", scheme="")
    return parsed.hostname


def _validate_connector_host(host: str) -> None:
    """Defense-in-Depth: blockt SSRF-Ziele bevor der Connector requestet.

    Erlaubt: Public-IPs, private LAN-Bereiche (10/8, 172.16/12, 192.168/16) und
    DNS-Namen, die auf solche Adressen auflösen. Geblockt:

      - Loopback (`127.0.0.0/8`, `::1`)
      - Link-local (`169.254.0.0/16`, `fe80::/10`) — schließt Cloud-Metadata-Endpoints ein
      - Multicast (`224.0.0.0/4`, `ff00::/8`)
      - Unspecified (`0.0.0.0`, `::`)
      - Reserviert (`240.0.0.0/4`)

    DNS-Rebinding: alle aus `getaddrinfo` zurückgegebenen Adressen werden geprüft
    — wenn ein Hostname auf eine geblockte Adresse auflöst, schlägt die
    Validierung fehl.

    Raises HTTPException(400) bei Verstoß.
    """
    hostname = _extract_hostname(host)
    if not hostname:
        raise HTTPException(status_code=400, detail="Host fehlt oder ungültig.")

    try:
        addrinfo = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Host nicht auflösbar: {hostname} ({exc})",
        )

    seen_addresses: set[str] = set()
    for family, _socktype, _proto, _canonname, sockaddr in addrinfo:
        ip_str = sockaddr[0]
        if ip_str in seen_addresses:
            continue
        seen_addresses.add(ip_str)
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            continue
        if (
            ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_unspecified
            or ip.is_reserved
        ):
            logger.warning(
                "Connector-Host blockiert (SSRF-Schutz): hostname=%s, resolved=%s",
                hostname, ip_str,
            )
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Ziel-Host nicht erlaubt: {hostname} → {ip_str} "
                    f"(Loopback/Link-local/Metadata-Endpunkte sind aus "
                    f"Sicherheitsgründen ausgeschlossen)."
                ),
            )


async def _get_anlage(anlage_id: int, db: AsyncSession) -> Anlage:
    """Lädt eine Anlage oder wirft 404."""
    result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    anlage = result.scalar_one_or_none()
    if not anlage:
        raise not_found("Anlage")
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

    _validate_connector_host(req.host)
    result = await connector.test_connection(req.host, req.username, req.password)
    await log_activity(
        kategorie="connector_test",
        aktion=f"Verbindungstest {req.connector_id} → {req.host}",
        erfolg=result.erfolg,
        details=result.fehler if not result.erfolg else f"Gerät: {result.geraet_name}",
        details_json={"connector_id": req.connector_id, "host": req.host},
    )
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

    _validate_connector_host(req.host)

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
    await log_activity(
        kategorie="connector_setup",
        aktion=f"Connector '{req.connector_id}' eingerichtet",
        erfolg=True,
        details=f"Gerät: {test_result.geraet_name}, SN: {test_result.seriennummer}",
        anlage_id=anlage_id,
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
        "field_inv_map": config.get("field_inv_map", {}),
    }


@router.put("/mapping/{anlage_id}")
async def set_connector_mapping(
    anlage_id: int,
    req: ConnectorMappingRequest,
    db: AsyncSession = Depends(get_db),
):
    """Ordnet die Mess-Kategorien des Connectors Investitionen zu.

    Speichert `field_inv_map` in der `connector_config` und lädt die
    Connector-Bridge heiß neu, damit die Energie-Schleife sofort
    per-Investition publisht.
    """
    result = await db.execute(
        select(Anlage)
        .options(selectinload(Anlage.investitionen))
        .where(Anlage.id == anlage_id)
    )
    anlage = result.scalar_one_or_none()
    if not anlage:
        raise not_found("Anlage")

    config = anlage.connector_config
    if not config:
        raise HTTPException(status_code=400, detail="Kein Connector konfiguriert")

    inv_by_id = {inv.id: inv for inv in anlage.investitionen}
    clean_map: dict[str, int] = {}
    for kategorie, inv_id in req.field_inv_map.items():
        if kategorie not in _KATEGORIE_TYPEN:
            raise HTTPException(
                status_code=400,
                detail=f"Unbekannte Kategorie: {kategorie}",
            )
        if inv_id is None:
            continue  # Zuordnung entfernen
        inv = inv_by_id.get(inv_id)
        if not inv:
            raise HTTPException(
                status_code=400,
                detail=f"Investition {inv_id} gehört nicht zu dieser Anlage",
            )
        if inv.typ not in _KATEGORIE_TYPEN[kategorie]:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Investition {inv_id} ({inv.typ}) passt nicht zur "
                    f"Kategorie '{kategorie}'"
                ),
            )
        clean_map[kategorie] = inv_id

    config["field_inv_map"] = clean_map
    anlage.connector_config = config
    flag_modified(anlage, "connector_config")
    await db.commit()

    # Bridge heiß neu laden, damit die neue Zuordnung sofort greift
    await _reload_bridge(db)

    await log_activity(
        kategorie="connector_setup",
        aktion="Connector-Zuordnung gespeichert",
        erfolg=True,
        details_json=clean_map,
        anlage_id=anlage_id,
    )

    return {"erfolg": True, "field_inv_map": clean_map}


async def _reload_bridge(db: AsyncSession) -> None:
    """Lädt die Connector-Bridge mit aktuellen Targets neu (falls aktiv)."""
    try:
        from backend.services.connector_mqtt_bridge import (
            get_connector_mqtt_bridge,
            build_targets_from_db,
        )

        bridge = get_connector_mqtt_bridge()
        if not bridge:
            return
        targets = await build_targets_from_db(db)
        await bridge.reload(targets)
    except Exception as e:
        logger.warning("Connector-Bridge Reload nach Mapping-Änderung fehlgeschlagen: %s", e)


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
        await log_activity(
            kategorie="connector_fetch",
            aktion="Zählerstand-Abruf fehlgeschlagen",
            erfolg=False,
            details=f"{type(e).__name__}: {str(e)}",
            anlage_id=anlage_id,
        )
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

    await log_activity(
        kategorie="connector_fetch",
        aktion="Zählerstand abgelesen",
        erfolg=True,
        details_json=snapshot.to_dict(),
        anlage_id=anlage_id,
    )

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
        raise not_found("Anlage")

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

    # Explizite Kategorie→Investition-Zuordnung (gleiche SoT wie die MQTT-Bridge).
    # Ist eine Kategorie zugeordnet, geht der ganze Wert auf diese eine
    # Investition — sonst greift die proportionale kWp-/Kapazitäts-Verteilung.
    field_inv_map = config.get("field_inv_map") or {}

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
            verteilung = _mapped_or_distribute(
                field_inv_map, "pv", pv_module, pv_kwh, "leistung_kwp"
            )
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
                for inv, anteil in _mapped_or_distribute(field_inv_map, "speicher", speicher, bat_ladung, "kapazitaet_kwh"):
                    felder_per_speicher.setdefault(inv.id, {"inv": inv, "felder": []})
                    felder_per_speicher[inv.id]["felder"].append(
                        {"feld": "ladung_kwh", "label": "Ladung", "wert": anteil, "einheit": "kWh"}
                    )
            if bat_entladung is not None and bat_entladung > 0:
                for inv, anteil in _mapped_or_distribute(field_inv_map, "speicher", speicher, bat_entladung, "kapazitaet_kwh"):
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
        "wallbox_ladung_kwh",
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


def _mapped_or_distribute(
    field_inv_map: dict,
    kategorie: str,
    candidates: list,
    total: float,
    param_key: str,
) -> list[tuple]:
    """Verteilt `total` — respektiert die explizite Kategorie-Zuordnung.

    Ist `kategorie` in `field_inv_map` einer Investition aus `candidates`
    zugeordnet, geht der ganze Wert auf diese eine Investition (gleiche
    Zuordnungs-SoT wie die MQTT-Energie-Bridge). Sonst proportionale
    Verteilung nach `param_key` (kWp / Kapazität).
    """
    mapped_id = field_inv_map.get(kategorie)
    if mapped_id is not None:
        target = next((i for i in candidates if i.id == mapped_id), None)
        if target is not None:
            return [(target, round(total, 2))]
    return _distribute_by_param(candidates, total, param_key)


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
    # Spalte hat Vorrang vor parameter-JSON (#229 JanKgh: leistung_kwp ist
    # bei vielen Anlagen als Tabellen-Spalte gepflegt, nicht im parameter)
    from backend.utils.investition_value import get_inv_value
    total_param = sum(get_inv_value(inv, param_key) for inv in investitionen)

    result = []
    for inv in investitionen:
        inv_param = get_inv_value(inv, param_key)
        if total_param > 0:
            anteil = round(total * inv_param / total_param, 2)
        else:
            anteil = round(total / len(investitionen), 2)
        result.append((inv, anteil))
    return result
