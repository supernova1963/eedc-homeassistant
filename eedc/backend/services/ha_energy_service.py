"""
HA Energy Service — liest die Home-Assistant-Energiekonfiguration und liefert
Mapping-Vorschläge für die Auto-Vorbefüllung im Sensor-Mapping-Wizard (#197).

Quelle: `/config/.storage/core.energy` (nur im HA-Add-on verfügbar).
Auf Standalone-Installationen wird `available=False` zurückgegeben — das
Frontend blendet den Banner dann aus.
"""

import json
import logging
from pathlib import Path
from typing import Optional

from pydantic import BaseModel

from backend.core.config import settings

logger = logging.getLogger(__name__)

HA_ENERGY_PATH = Path("/config/.storage/core.energy")


class EnergySourceSuggestion(BaseModel):
    """Vorschlag für einen Basis-Sensor (Einspeisung/Netzbezug/PV)."""
    feld: str  # "einspeisung" | "netzbezug" | "pv_gesamt"
    entity_id: str


class BatterySuggestion(BaseModel):
    """Batterie-Sensoren aus HA-Energy → mappen auf Speicher-Investition."""
    ladung_entity: Optional[str] = None       # stat_energy_to (vom Hausnetz in den Akku)
    entladung_entity: Optional[str] = None    # stat_energy_from (aus dem Akku ins Hausnetz)


class DeviceConsumptionCandidate(BaseModel):
    """Ein device_consumption-Eintrag aus HA-Energy mit Heuristik-Match."""
    entity_id: str
    name: Optional[str] = None  # User-vergebener Anzeigename in HA-Energy
    suggested_inv_typ: Optional[str] = None  # "wallbox" | "waermepumpe" | "e-auto" | None


class HAEnergySuggestions(BaseModel):
    """Ergebnis des HA-Energy-Reads."""
    available: bool
    energy_sources: list[EnergySourceSuggestion] = []
    battery: Optional[BatterySuggestion] = None
    device_consumption: list[DeviceConsumptionCandidate] = []
    reason_unavailable: Optional[str] = None


# Substring-Tokens für die Typ-Erkennung. Erster Treffer gewinnt — Reihenfolge
# matters: spezifische Wallbox-Marken vor generischem "charger", e-auto vor
# Wallbox damit "tesla" (= Auto) nicht durch "charger" (= Wallbox) überstimmt
# wird.
#
# Bewusst tolerant: der User sieht im Wizard-Banner welcher Sensor wohin
# vorgeschlagen wurde und kann jeden Vorschlag manuell korrigieren oder
# zurücksetzen (#197 Olli0103, Reset-Knopf wirkt nur auf HA-Energy-Vorschläge).
_TYP_TOKENS: dict[str, list[str]] = {
    "e-auto": [
        "e-auto", "eauto", "e_auto",
        "electric_vehicle", "ev_car", "ev_fahrzeug",
        "tesla", "polestar", "ioniq", "enyaq",
        "id.3", "id.4", "id.5", "id.7", "id_3", "id_4", "id_5", "id_7",
        "model_3", "model_y", "model_s", "model_x",
    ],
    "wallbox": [
        "wallbox",
        "go-echarger", "go_echarger", "goe_charger", "go-e-charger", "goecharger",
        "openwb", "open_wb",
        "keba", "zappi", "cfos", "evse", "easee",
        "charger",  # generisch, deshalb am Ende
    ],
    "waermepumpe": [
        "waermepumpe", "wärmepumpe", "heatpump", "heat_pump", "heat-pump",
        "nibe", "daikin", "vaillant", "weishaupt", "viessmann", "stiebel",
        "buderus", "lambda_wp", "ait_lwd",
    ],
}


def _detect_inv_typ(entity_id: str, name: Optional[str]) -> Optional[str]:
    """Heuristik: device_consumption → Investitions-Typ via Substring-Match."""
    haystack = (entity_id + " " + (name or "")).lower()
    for typ, tokens in _TYP_TOKENS.items():
        for tok in tokens:
            if tok in haystack:
                return typ
    return None


def _read_energy_file() -> Optional[dict]:
    """Read+parse aus HA_ENERGY_PATH — dynamisch nachgeschlagen für Testbarkeit."""
    path = HA_ENERGY_PATH
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("HA-Energy-Konfiguration nicht lesbar (%s): %s", path, e)
        return None


def get_ha_energy_suggestions() -> HAEnergySuggestions:
    """Liest HA-Energy-Konfig (Supervisor-Datei) und liefert Vorschläge."""
    if not settings.supervisor_token:
        return HAEnergySuggestions(
            available=False,
            reason_unavailable="standalone",
        )

    raw = _read_energy_file()
    if raw is None:
        return HAEnergySuggestions(
            available=False,
            reason_unavailable="HA-Energy-Konfiguration nicht gefunden",
        )

    return _suggestions_aus_prefs(raw.get("data") or {})


def _suggestions_aus_prefs(data: dict) -> HAEnergySuggestions:
    """Gemeinsames Parsing der Energy-Prefs — Supervisor-Datei (`data`-Teil von
    core.energy) und Remote-WS (`energy/get_prefs`-Result) haben dieselbe Form."""
    sources = data.get("energy_sources") or []
    devices = data.get("device_consumption") or []

    suggestions: list[EnergySourceSuggestion] = []
    battery: Optional[BatterySuggestion] = None

    for src in sources:
        typ = src.get("type")
        if typ == "grid":
            for entry in (src.get("flow_from") or []):
                ent = entry.get("stat_energy_from")
                if ent:
                    suggestions.append(EnergySourceSuggestion(feld="netzbezug", entity_id=ent))
                    break  # nur erstes Pärchen — Multi-Tarif manuell pflegen
            for entry in (src.get("flow_to") or []):
                ent = entry.get("stat_energy_to")
                if ent:
                    suggestions.append(EnergySourceSuggestion(feld="einspeisung", entity_id=ent))
                    break
        elif typ == "solar":
            ent = src.get("stat_energy_from")
            if ent:
                suggestions.append(EnergySourceSuggestion(feld="pv_gesamt", entity_id=ent))
        elif typ == "battery":
            # Erste Batterie-Quelle gewinnt — bei mehreren Speichern pflegt der User manuell
            if battery is None:
                battery = BatterySuggestion(
                    ladung_entity=src.get("stat_energy_to"),
                    entladung_entity=src.get("stat_energy_from"),
                )

    candidates: list[DeviceConsumptionCandidate] = []
    for dev in devices:
        ent = dev.get("stat_consumption")
        if not ent:
            continue
        nm = dev.get("name")
        candidates.append(DeviceConsumptionCandidate(
            entity_id=ent,
            name=nm,
            suggested_inv_typ=_detect_inv_typ(ent, nm),
        ))

    return HAEnergySuggestions(
        available=True,
        energy_sources=suggestions,
        battery=battery,
        device_consumption=candidates,
    )


async def get_ha_energy_suggestions_remote(base_url: str, token: str) -> HAEnergySuggestions:
    """D2 (2026-07-18): Energy-Dashboard-Prefs über eine Remote-HA-Instanz.

    Die Prefs liegen NICHT hinter REST — einziger Weg ist die WebSocket-API
    (`energy/get_prefs`). Einmaliger One-Shot-Call mit LL-Token-Auth; jede
    Fehlerklasse degradiert weich zu available=False (kein Blocker im Wizard).
    """
    import asyncio

    import websockets

    ws_url = base_url.rstrip("/")
    if ws_url.startswith("https://"):
        ws_url = "wss://" + ws_url[len("https://"):]
    elif ws_url.startswith("http://"):
        ws_url = "ws://" + ws_url[len("http://"):]
    ws_url += "/api/websocket"

    async def _empfange(ws) -> dict:
        return json.loads(await asyncio.wait_for(ws.recv(), timeout=10))

    try:
        async with websockets.connect(ws_url, open_timeout=10, close_timeout=5) as ws:
            await _empfange(ws)  # auth_required
            await ws.send(json.dumps({"type": "auth", "access_token": token}))
            auth = await _empfange(ws)
            if auth.get("type") != "auth_ok":
                return HAEnergySuggestions(
                    available=False, reason_unavailable="Remote-HA: Token abgelehnt",
                )
            await ws.send(json.dumps({"id": 1, "type": "energy/get_prefs"}))
            while True:
                msg = await _empfange(ws)
                if msg.get("id") == 1 and msg.get("type") == "result":
                    break
    except Exception as e:  # noqa: BLE001 — Netz/TLS/Timeout → weiche Degradation
        logger.info("Remote-Energy-Prefs nicht erreichbar: %s", e)
        return HAEnergySuggestions(
            available=False, reason_unavailable="Remote-HA nicht erreichbar",
        )

    if not msg.get("success"):
        return HAEnergySuggestions(
            available=False,
            reason_unavailable="Energy-Dashboard in der Remote-HA nicht konfiguriert",
        )
    return _suggestions_aus_prefs(msg.get("result") or {})
