"""
sonnen Batterie Connector.

Verbindet sich über die lokale REST API v2 mit sonnenBatterie Speichersystemen
und liest kumulative PV-Erzeugung sowie Momentanwerte aus.

Endpoints:
- GET /api/v2/status → Momentanwerte (kein Auth nötig)
- GET /api/v2/powermeter → Kumulative kWh für PV und Verbrauch
- GET /api/v2/battery → Batterie-Info (Zyklen, SoC)

Besonderheiten:
- Auth via 'Auth-Token' Header (Token aus sonnen Dashboard → Software-Integration)
- /api/v2/status ist ohne Auth zugänglich
- Kumulative kWh nur für PV-Erzeugung und Verbrauch vorhanden
- Grid-Import/Export und Batterie-Ladung/Entladung NICHT als kumulative Zähler
  verfügbar (nur Momentanleistung in W)

HINWEIS: Dieser Connector wurde anhand der sonnen API v2 und der
HA sonnenbatterie-Integration erstellt, aber noch nicht mit echten
Speichern verifiziert (getestet=False).
"""

import logging
from datetime import datetime, timezone
from typing import Optional

import aiohttp

from .base import DeviceConnector, ConnectorInfo, MeterSnapshot, ConnectionTestResult, LiveSnapshot
from .registry import register_connector

logger = logging.getLogger(__name__)


async def _fetch_json(
    session: aiohttp.ClientSession, url: str, headers: Optional[dict] = None,
    timeout: int = 10
) -> Optional[dict | list]:
    """Holt JSON von der sonnen API."""
    try:
        async with session.get(
            url, headers=headers, timeout=aiohttp.ClientTimeout(total=timeout)
        ) as resp:
            if resp.status == 401:
                return {"_auth_error": True}
            if resp.status != 200:
                return None
            return await resp.json(content_type=None)
    except Exception as e:
        logger.warning("sonnen API request failed for %s: %s", url, e)
        return None


def _find_meter(powermeter_data, direction: str) -> Optional[dict]:
    """Findet einen Powermeter-Eintrag nach Direction ('production' oder 'consumption').

    Powermeter kann als Liste oder Dict kommen (Firmware-abhängig).
    """
    if isinstance(powermeter_data, dict):
        powermeter_data = list(powermeter_data.values())
    if not isinstance(powermeter_data, list):
        return None

    for entry in powermeter_data:
        if isinstance(entry, dict) and entry.get("direction") == direction:
            return entry
    return None


@register_connector
class SonnenBatterieConnector(DeviceConnector):
    """Connector für sonnenBatterie Speichersysteme."""

    def info(self) -> ConnectorInfo:
        return ConnectorInfo(
            id="sonnen_batterie",
            name="sonnenBatterie",
            hersteller="sonnen",
            beschreibung=(
                "Direktverbindung zu sonnenBatterie Speichersystemen (eco, 10, hybrid) "
                "über die lokale REST API v2. Liest PV-Erzeugung (kumulativ) sowie "
                "aktuelle Leistungswerte (PV, Netz, Batterie, Verbrauch) aus."
            ),
            anleitung=(
                "1. IP-Adresse der sonnenBatterie im lokalen Netzwerk ermitteln\n"
                "2. sonnen Dashboard öffnen: http://<IP>/\n"
                "3. Unter 'Software-Integration' den API-Token kopieren\n"
                "4. Benutzername: leer lassen\n"
                "5. Passwort: Den API-Token eintragen\n"
                "6. Hinweis: Grid-Import/Export sind nur als Momentanleistung verfügbar,\n"
                "   nicht als kumulative kWh-Zähler"
            ),
            getestet=False,
        )

    async def test_connection(
        self, host: str, username: str, password: str
    ) -> ConnectionTestResult:
        """Testet die Verbindung zur sonnenBatterie."""
        base_url = f"http://{host}"
        auth_headers = {"Auth-Token": password} if password else {}

        try:
            async with aiohttp.ClientSession() as session:
                # Status (kein Auth nötig)
                status = await _fetch_json(session, f"{base_url}/api/v2/status")
                if not status:
                    return ConnectionTestResult(
                        erfolg=False,
                        fehler=f"Keine Antwort von {host}. Ist die IP korrekt und die Batterie erreichbar?",
                    )

                sensoren: list[str] = []
                production_w = status.get("Production_W")
                consumption_w = status.get("Consumption_W")
                grid_w = status.get("GridFeedIn_W")
                pac_w = status.get("Pac_total_W")
                usoc = status.get("USOC")
                system_status = status.get("SystemStatus")

                if production_w is not None:
                    sensoren.append(f"PV Leistung: {production_w:.0f} W")
                if consumption_w is not None:
                    sensoren.append(f"Verbrauch: {consumption_w:.0f} W")
                if grid_w is not None:
                    grid_dir = "Einspeisung" if grid_w > 0 else "Netzbezug"
                    sensoren.append(f"Netz: {abs(grid_w):.0f} W ({grid_dir})")
                if pac_w is not None:
                    bat_dir = "Entladung" if pac_w > 0 else "Ladung"
                    sensoren.append(f"Batterie: {abs(pac_w):.0f} W ({bat_dir})")
                if usoc is not None:
                    sensoren.append(f"Ladestand (USOC): {usoc}%")
                if system_status:
                    sensoren.append(f"System: {system_status}")

                # Powermeter (Auth nötig)
                powermeter = await _fetch_json(
                    session, f"{base_url}/api/v2/powermeter", headers=auth_headers
                )

                pv_kwh = None
                if powermeter and not isinstance(powermeter, dict) or (
                    isinstance(powermeter, dict) and "_auth_error" not in powermeter
                ):
                    prod_meter = _find_meter(powermeter, "production")
                    if prod_meter:
                        pv_kwh = prod_meter.get("kwh_imported")
                        if pv_kwh is not None:
                            sensoren.append(f"PV Erzeugung gesamt: {pv_kwh:.1f} kWh")

                    cons_meter = _find_meter(powermeter, "consumption")
                    if cons_meter:
                        cons_kwh = cons_meter.get("kwh_imported")
                        if cons_kwh is not None:
                            sensoren.append(f"Verbrauch gesamt: {cons_kwh:.1f} kWh")
                elif isinstance(powermeter, dict) and powermeter.get("_auth_error"):
                    sensoren.append("⚠ Powermeter: Auth-Token ungültig oder fehlt")

                # Batterie-Info (Auth nötig)
                battery = await _fetch_json(
                    session, f"{base_url}/api/v2/battery", headers=auth_headers
                )
                if battery and isinstance(battery, dict) and "_auth_error" not in battery:
                    cycles = battery.get("cyclecount")
                    if cycles is not None:
                        sensoren.append(f"Batterie-Zyklen: {int(cycles)}")

                snapshot = MeterSnapshot(
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    pv_erzeugung_kwh=round(pv_kwh, 3) if pv_kwh is not None else None,
                )

                return ConnectionTestResult(
                    erfolg=True,
                    geraet_name=f"sonnenBatterie ({host})",
                    geraet_typ="sonnenBatterie",
                    verfuegbare_sensoren=sensoren,
                    aktuelle_werte=snapshot,
                )

        except aiohttp.ClientError as e:
            return ConnectionTestResult(
                erfolg=False,
                fehler=f"Verbindungsfehler: {str(e)}",
            )
        except Exception as e:
            logger.exception("Fehler beim sonnenBatterie-Verbindungstest")
            return ConnectionTestResult(
                erfolg=False,
                fehler=f"Unerwarteter Fehler: {str(e)}",
            )

    async def read_meters(
        self, host: str, username: str, password: str
    ) -> MeterSnapshot:
        """Liest aktuelle kumulative Zählerstände von der sonnenBatterie."""
        base_url = f"http://{host}"
        auth_headers = {"Auth-Token": password} if password else {}
        now = datetime.now(timezone.utc).isoformat()

        async with aiohttp.ClientSession() as session:
            powermeter = await _fetch_json(
                session, f"{base_url}/api/v2/powermeter", headers=auth_headers
            )

            pv_kwh = None
            if powermeter:
                prod_meter = _find_meter(powermeter, "production")
                if prod_meter:
                    pv_kwh = prod_meter.get("kwh_imported")

            return MeterSnapshot(
                timestamp=now,
                pv_erzeugung_kwh=round(pv_kwh, 3) if pv_kwh is not None else None,
            )

    async def read_live(
        self, host: str, username: str, password: str
    ) -> Optional[LiveSnapshot]:
        """Liest aktuelle Leistungswerte von der sonnenBatterie."""
        base_url = f"http://{host}"
        now = datetime.now(timezone.utc).isoformat()

        try:
            async with aiohttp.ClientSession() as session:
                # /api/v2/status ist ohne Auth zugänglich
                status = await _fetch_json(session, f"{base_url}/api/v2/status")
                if not status or isinstance(status, list):
                    return None

                snap = LiveSnapshot(timestamp=now)

                production_w = status.get("Production_W")
                if production_w is not None:
                    snap.leistung_w = round(production_w, 1)

                grid_w = status.get("GridFeedIn_W")
                if grid_w is not None:
                    # Positiv = Einspeisung, Negativ = Netzbezug
                    if grid_w >= 0:
                        snap.einspeisung_w = round(grid_w, 1)
                        snap.netzbezug_w = 0
                    else:
                        snap.netzbezug_w = round(abs(grid_w), 1)
                        snap.einspeisung_w = 0

                pac_w = status.get("Pac_total_W")
                if pac_w is not None:
                    # Positiv = Entladung, Negativ = Ladung
                    if pac_w >= 0:
                        snap.batterie_entladung_w = round(pac_w, 1)
                    else:
                        snap.batterie_ladung_w = round(abs(pac_w), 1)

                soc = status.get("USOC")
                if soc is not None:
                    snap.soc = round(soc, 1)

                return snap
        except Exception as e:
            logger.warning("sonnenBatterie read_live fehlgeschlagen: %s", e)
            return None
