"""
Shelly Energy Meter Connector.

Verbindet sich über die lokale REST API mit Shelly 3EM (Gen1) und
Shelly Pro 3EM (Gen2) Energiemessgeräten und liest kumulative
Grid-Import/Export Zählerstände aus.

Endpoints Gen1 (Shelly 3EM):
- GET /status → emeters[0..2].total / total_returned (Wh)
- GET /shelly → Geräteinfo

Endpoints Gen2 (Shelly Pro 3EM):
- GET /rpc/EMData.GetStatus?id=0 → total_act / total_act_ret (kWh)
- GET /shelly → Geräteinfo

Besonderheiten:
- Gen1: Werte in Wh (werden zu kWh konvertiert)
- Gen2: Werte bereits in kWh
- Authentifizierung optional (Gen1: Digest, Gen2: Basic)
- Reiner Smart Meter → nur netzbezug/einspeisung, keine PV/Batterie

HINWEIS: Dieser Connector wurde anhand der Shelly API-Dokumentation und
der aioshelly-Bibliothek erstellt, aber noch nicht mit echten Geräten
verifiziert (getestet=False).
"""

import logging
from datetime import datetime, timezone
from typing import Optional

import aiohttp

from .base import DeviceConnector, ConnectorInfo, MeterSnapshot, ConnectionTestResult
from .registry import register_connector

logger = logging.getLogger(__name__)


async def _fetch_json(
    session: aiohttp.ClientSession, url: str, timeout: int = 10
) -> Optional[dict]:
    """Holt JSON von der Shelly API."""
    try:
        async with session.get(
            url, timeout=aiohttp.ClientTimeout(total=timeout)
        ) as resp:
            if resp.status == 401:
                return {"_auth_error": True}
            if resp.status != 200:
                return None
            return await resp.json(content_type=None)
    except Exception as e:
        logger.warning("Shelly API request failed for %s: %s", url, e)
        return None


def _detect_generation(shelly_info: dict) -> str:
    """Erkennt ob Gen1 oder Gen2 Shelly-Gerät."""
    # Gen2 hat "gen" Feld, Gen1 hat "type" Feld
    if shelly_info.get("gen", 0) >= 2:
        return "gen2"
    if "type" in shelly_info:
        return "gen1"
    # Fallback: Gen2 hat "model" statt "type"
    if "model" in shelly_info and "type" not in shelly_info:
        return "gen2"
    return "gen1"


@register_connector
class ShellyEMConnector(DeviceConnector):
    """Connector für Shelly 3EM und Pro 3EM Energy Meter."""

    def info(self) -> ConnectorInfo:
        return ConnectorInfo(
            id="shelly_em",
            name="Shelly 3EM / Pro 3EM",
            hersteller="Shelly (Allterco)",
            beschreibung=(
                "Direktverbindung zu Shelly 3EM (Gen1) und Shelly Pro 3EM (Gen2) "
                "Energiemessgeräten. Liest kumulative Grid-Import und Export Zähler "
                "aus. Ideal als externer Smart Meter am Netzanschlusspunkt."
            ),
            anleitung=(
                "1. IP-Adresse des Shelly Geräts im lokalen Netzwerk ermitteln\n"
                "   (z.B. über Shelly App oder Router)\n"
                "2. Prüfen ob das Gerät erreichbar ist: http://<IP>/shelly\n"
                "3. Falls Authentifizierung aktiviert: Benutzername 'admin' und Passwort eingeben\n"
                "4. Ohne Authentifizierung: Felder leer lassen"
            ),
            getestet=False,
        )

    async def test_connection(
        self, host: str, username: str, password: str
    ) -> ConnectionTestResult:
        """Testet die Verbindung zum Shelly Energy Meter."""
        base_url = f"http://{host}"

        try:
            auth = None
            if username and password:
                auth = aiohttp.BasicAuth(username or "admin", password)

            async with aiohttp.ClientSession(auth=auth) as session:
                # Geräteinfo abrufen
                shelly_info = await _fetch_json(session, f"{base_url}/shelly")
                if not shelly_info:
                    return ConnectionTestResult(
                        erfolg=False,
                        fehler=f"Keine Antwort von {host}. Ist die IP korrekt und das Gerät erreichbar?",
                    )

                if shelly_info.get("_auth_error"):
                    return ConnectionTestResult(
                        erfolg=False,
                        fehler="Authentifizierung erforderlich. Bitte Benutzername und Passwort eingeben.",
                    )

                generation = _detect_generation(shelly_info)
                geraet_name = shelly_info.get("name") or shelly_info.get("hostname") or f"Shelly ({host})"
                geraet_typ = shelly_info.get("type") or shelly_info.get("model") or "Shelly EM"
                firmware = shelly_info.get("fw") or shelly_info.get("fw_id")

                sensoren: list[str] = []

                if generation == "gen1":
                    snapshot, sensoren = await self._read_gen1(session, base_url)
                else:
                    snapshot, sensoren = await self._read_gen2(session, base_url)

                return ConnectionTestResult(
                    erfolg=True,
                    geraet_name=geraet_name,
                    geraet_typ=f"{geraet_typ} ({generation.upper()})",
                    firmware=str(firmware) if firmware else None,
                    verfuegbare_sensoren=sensoren,
                    aktuelle_werte=snapshot,
                )

        except aiohttp.ClientError as e:
            return ConnectionTestResult(
                erfolg=False,
                fehler=f"Verbindungsfehler: {str(e)}",
            )
        except Exception as e:
            logger.exception("Fehler beim Shelly-Verbindungstest")
            return ConnectionTestResult(
                erfolg=False,
                fehler=f"Unerwarteter Fehler: {str(e)}",
            )

    async def read_meters(
        self, host: str, username: str, password: str
    ) -> MeterSnapshot:
        """Liest aktuelle kumulative Zählerstände vom Shelly Energy Meter."""
        base_url = f"http://{host}"

        auth = None
        if username and password:
            auth = aiohttp.BasicAuth(username or "admin", password)

        async with aiohttp.ClientSession(auth=auth) as session:
            shelly_info = await _fetch_json(session, f"{base_url}/shelly")
            generation = _detect_generation(shelly_info) if shelly_info else "gen1"

            if generation == "gen1":
                snapshot, _ = await self._read_gen1(session, base_url)
            else:
                snapshot, _ = await self._read_gen2(session, base_url)

            return snapshot

    async def _read_gen1(
        self, session: aiohttp.ClientSession, base_url: str
    ) -> tuple[MeterSnapshot, list[str]]:
        """Liest Gen1 Shelly 3EM via /status Endpoint."""
        now = datetime.now(timezone.utc).isoformat()
        sensoren: list[str] = []

        data = await _fetch_json(session, f"{base_url}/status")
        if not data or "emeters" not in data:
            return MeterSnapshot(timestamp=now), sensoren

        emeters = data["emeters"]
        total_import_wh = 0.0
        total_export_wh = 0.0

        for i, em in enumerate(emeters):
            if not isinstance(em, dict) or not em.get("is_valid", True):
                continue

            t = em.get("total", 0)
            tr = em.get("total_returned", 0)
            total_import_wh += t
            total_export_wh += tr
            power = em.get("power", 0)
            sensoren.append(f"L{i+1}: Import {t/1000:.1f} kWh, Export {tr/1000:.1f} kWh, aktuell {power:.0f} W")

        total_power = data.get("total_power")
        if total_power is not None:
            sensoren.append(f"Gesamtleistung: {total_power:.0f} W")

        return MeterSnapshot(
            timestamp=now,
            netzbezug_kwh=round(total_import_wh / 1000.0, 3),
            einspeisung_kwh=round(total_export_wh / 1000.0, 3),
        ), sensoren

    async def _read_gen2(
        self, session: aiohttp.ClientSession, base_url: str
    ) -> tuple[MeterSnapshot, list[str]]:
        """Liest Gen2 Shelly Pro 3EM via /rpc/EMData.GetStatus Endpoint."""
        now = datetime.now(timezone.utc).isoformat()
        sensoren: list[str] = []

        data = await _fetch_json(session, f"{base_url}/rpc/EMData.GetStatus?id=0")
        if not data:
            return MeterSnapshot(timestamp=now), sensoren

        # Gen2 liefert direkt kWh
        total_import = data.get("total_act")
        total_export = data.get("total_act_ret")

        # Per-Phase Sensoren
        for phase, label in [("a", "L1"), ("b", "L2"), ("c", "L3")]:
            imp = data.get(f"{phase}_total_act_energy")
            exp = data.get(f"{phase}_total_act_ret_energy")
            if imp is not None:
                sensoren.append(f"{label}: Import {imp:.1f} kWh, Export {exp:.1f} kWh")

        if total_import is not None:
            sensoren.append(f"Gesamt: Import {total_import:.1f} kWh, Export {total_export:.1f} kWh")

        # Aktuelle Leistung aus EM.GetStatus
        em_status = await _fetch_json(session, f"{base_url}/rpc/EM.GetStatus?id=0")
        if em_status:
            total_power = em_status.get("total_act_power")
            if total_power is not None:
                sensoren.append(f"Gesamtleistung: {total_power:.0f} W")

        return MeterSnapshot(
            timestamp=now,
            netzbezug_kwh=round(total_import, 3) if total_import is not None else None,
            einspeisung_kwh=round(total_export, 3) if total_export is not None else None,
        ), sensoren
