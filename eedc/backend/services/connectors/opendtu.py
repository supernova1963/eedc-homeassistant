"""
OpenDTU / AhoyDTU Connector.

Verbindet sich über die lokale REST API mit OpenDTU oder AhoyDTU Gateways
für Hoymiles Micro-Wechselrichter und liest kumulative PV-Erträge aus.

Endpoints OpenDTU:
- GET /api/livedata/status → total.YieldTotal.v (kWh)
- GET /api/system/status → System-Info

Endpoints AhoyDTU:
- GET /api/inverter/list → Wechselrichter-Liste
- GET /api/inverter/id/{N} → Live-Daten mit ch[0][6] = YieldTotal (kWh)

Besonderheiten:
- Standardmäßig keine Authentifizierung im Readonly-Modus
- Beide DTU-Typen werden automatisch erkannt
- Nur PV-Erzeugung (kein Grid/Batterie – Micro-Inverter haben das nicht)

HINWEIS: Dieser Connector wurde anhand des OpenDTU und AhoyDTU Quellcodes
erstellt, aber noch nicht mit echten DTU-Gateways verifiziert (getestet=False).
"""

import logging
from datetime import datetime, timezone
from typing import Optional

import aiohttp

from .base import DeviceConnector, ConnectorInfo, MeterSnapshot, ConnectionTestResult, LiveSnapshot
from .registry import register_connector

logger = logging.getLogger(__name__)


async def _fetch_json(
    session: aiohttp.ClientSession, url: str, timeout: int = 10
) -> Optional[dict]:
    """Holt JSON von der DTU API."""
    try:
        async with session.get(
            url, timeout=aiohttp.ClientTimeout(total=timeout)
        ) as resp:
            if resp.status != 200:
                return None
            return await resp.json(content_type=None)
    except Exception as e:
        logger.warning("DTU API request failed for %s: %s", url, e)
        return None


def _get_nested(data: dict, *keys, default=None):
    """Sicherer Zugriff auf verschachtelte dict-Keys."""
    current = data
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key, default)
        if current is default:
            return default
    return current


@register_connector
class OpenDTUConnector(DeviceConnector):
    """Connector für OpenDTU und AhoyDTU Gateways (Hoymiles Micro-Inverter)."""

    def info(self) -> ConnectorInfo:
        return ConnectorInfo(
            id="opendtu",
            name="OpenDTU / AhoyDTU (Hoymiles)",
            hersteller="Hoymiles (via OpenDTU/AhoyDTU)",
            beschreibung=(
                "Verbindung zu OpenDTU oder AhoyDTU Gateways für Hoymiles "
                "Micro-Wechselrichter (HM-300/600/800/1500, HMS, HMT). "
                "Liest den kumulativen PV-Gesamtertrag aus. Ideal für "
                "Balkonkraftwerke und kleine PV-Anlagen."
            ),
            anleitung=(
                "1. IP-Adresse des DTU-Gateways (ESP32) im lokalen Netzwerk ermitteln\n"
                "2. Prüfen ob die Web-Oberfläche erreichbar ist: http://<IP>/\n"
                "3. Standard: Keine Authentifizierung nötig (Readonly-Modus)\n"
                "4. Falls Passwort gesetzt: Benutzername 'admin' und Passwort eingeben\n"
                "5. Unterstützt sowohl OpenDTU als auch AhoyDTU automatisch"
            ),
            getestet=False,
        )

    async def test_connection(
        self, host: str, username: str, password: str
    ) -> ConnectionTestResult:
        """Testet die Verbindung zum DTU-Gateway."""
        base_url = f"http://{host}"

        try:
            auth = None
            if username and password:
                auth = aiohttp.BasicAuth(username or "admin", password)

            async with aiohttp.ClientSession(auth=auth) as session:
                # OpenDTU erkennen
                dtu_type, result = await self._try_opendtu(session, base_url)
                if result:
                    return result

                # AhoyDTU versuchen
                dtu_type, result = await self._try_ahoydtu(session, base_url)
                if result:
                    return result

                return ConnectionTestResult(
                    erfolg=False,
                    fehler=(
                        f"Kein OpenDTU oder AhoyDTU unter {host} gefunden. "
                        "Ist die IP korrekt und das Gateway erreichbar?"
                    ),
                )

        except aiohttp.ClientError as e:
            return ConnectionTestResult(
                erfolg=False,
                fehler=f"Verbindungsfehler: {str(e)}",
            )
        except Exception as e:
            logger.exception("Fehler beim DTU-Verbindungstest")
            return ConnectionTestResult(
                erfolg=False,
                fehler=f"Unerwarteter Fehler: {str(e)}",
            )

    async def _try_opendtu(
        self, session: aiohttp.ClientSession, base_url: str
    ) -> tuple[str, Optional[ConnectionTestResult]]:
        """Versucht OpenDTU-Endpunkte."""
        data = await _fetch_json(session, f"{base_url}/api/livedata/status")
        if not data or "inverters" not in data:
            return "opendtu", None

        sensoren: list[str] = []
        inverters = data.get("inverters", [])

        # Gesamtwerte
        total = data.get("total", {})
        yield_total = _get_nested(total, "YieldTotal", "v")
        yield_day = _get_nested(total, "YieldDay", "v")
        power = _get_nested(total, "Power", "v")

        if yield_total is not None:
            sensoren.append(f"PV Gesamt: {yield_total:.2f} kWh")
        if yield_day is not None:
            sensoren.append(f"PV Heute: {yield_day:.0f} Wh")
        if power is not None:
            sensoren.append(f"Aktuelle Leistung: {power:.0f} W")

        # Per-Inverter Info
        for inv in inverters:
            name = inv.get("name", "Unbekannt")
            serial = inv.get("serial", "")
            reachable = inv.get("reachable", False)
            producing = inv.get("producing", False)
            status = "produziert" if producing else ("erreichbar" if reachable else "nicht erreichbar")
            sensoren.append(f"WR {name} ({serial}): {status}")

        # System-Info
        sys_info = await _fetch_json(session, f"{base_url}/api/system/status")
        hostname = None
        firmware = None
        if sys_info:
            hostname = sys_info.get("hostname")
            firmware = sys_info.get("git_hash") or sys_info.get("pioenv")

        snapshot = MeterSnapshot(
            timestamp=datetime.now(timezone.utc).isoformat(),
            pv_erzeugung_kwh=round(yield_total, 3) if yield_total is not None else None,
        )

        return "opendtu", ConnectionTestResult(
            erfolg=True,
            geraet_name=hostname or f"OpenDTU ({len(inverters)} WR)",
            geraet_typ=f"OpenDTU ({len(inverters)} Wechselrichter)",
            firmware=firmware,
            verfuegbare_sensoren=sensoren,
            aktuelle_werte=snapshot,
        )

    async def _try_ahoydtu(
        self, session: aiohttp.ClientSession, base_url: str
    ) -> tuple[str, Optional[ConnectionTestResult]]:
        """Versucht AhoyDTU-Endpunkte."""
        inv_list = await _fetch_json(session, f"{base_url}/api/inverter/list")
        if not inv_list or "inverter" not in inv_list:
            return "ahoydtu", None

        sensoren: list[str] = []
        inverters = inv_list.get("inverter", [])
        total_yield = 0.0
        total_power = 0.0
        has_data = False

        for inv in inverters:
            if not inv.get("enabled", False):
                continue

            inv_id = inv.get("id", 0)
            inv_name = inv.get("name", f"WR #{inv_id}")

            # Live-Daten für diesen Inverter abrufen
            inv_data = await _fetch_json(session, f"{base_url}/api/inverter/id/{inv_id}")
            if inv_data and "ch" in inv_data:
                ch = inv_data["ch"]
                if isinstance(ch, list) and len(ch) > 0 and isinstance(ch[0], list) and len(ch[0]) > 6:
                    # ch[0] = AC-Kanal: [UAC, IAC, PAC, F, PF, T, YieldTotal, YieldDay, ...]
                    yield_kwh = ch[0][6] if len(ch[0]) > 6 else 0
                    power_w = ch[0][2] if len(ch[0]) > 2 else 0
                    yield_day = ch[0][7] if len(ch[0]) > 7 else 0

                    if yield_kwh > 0:
                        total_yield += yield_kwh
                        has_data = True
                    total_power += power_w

                    sensoren.append(
                        f"WR {inv_name}: {yield_kwh:.2f} kWh gesamt, "
                        f"{yield_day:.0f} Wh heute, {power_w:.0f} W aktuell"
                    )
                else:
                    sensoren.append(f"WR {inv_name}: keine Daten (nicht erreichbar?)")
            else:
                sensoren.append(f"WR {inv_name}: keine Daten")

        if total_power > 0:
            sensoren.insert(0, f"Gesamtleistung: {total_power:.0f} W")
        if has_data:
            sensoren.insert(0, f"PV Gesamt: {total_yield:.2f} kWh")

        # System-Info
        sys_info = await _fetch_json(session, f"{base_url}/api/system")

        snapshot = MeterSnapshot(
            timestamp=datetime.now(timezone.utc).isoformat(),
            pv_erzeugung_kwh=round(total_yield, 3) if has_data else None,
        )

        return "ahoydtu", ConnectionTestResult(
            erfolg=True,
            geraet_name=f"AhoyDTU ({len(inverters)} WR)",
            geraet_typ=f"AhoyDTU ({len(inverters)} Wechselrichter)",
            verfuegbare_sensoren=sensoren,
            aktuelle_werte=snapshot,
        )

    async def read_meters(
        self, host: str, username: str, password: str
    ) -> MeterSnapshot:
        """Liest aktuelle kumulative PV-Zählerstände vom DTU-Gateway."""
        base_url = f"http://{host}"
        now = datetime.now(timezone.utc).isoformat()

        auth = None
        if username and password:
            auth = aiohttp.BasicAuth(username or "admin", password)

        async with aiohttp.ClientSession(auth=auth) as session:
            # OpenDTU versuchen
            data = await _fetch_json(session, f"{base_url}/api/livedata/status")
            if data and "total" in data:
                yield_total = _get_nested(data, "total", "YieldTotal", "v")
                return MeterSnapshot(
                    timestamp=now,
                    pv_erzeugung_kwh=round(yield_total, 3) if yield_total is not None else None,
                )

            # AhoyDTU Fallback
            inv_list = await _fetch_json(session, f"{base_url}/api/inverter/list")
            if inv_list and "inverter" in inv_list:
                total_yield = 0.0
                has_data = False
                for inv in inv_list["inverter"]:
                    if not inv.get("enabled", False):
                        continue
                    inv_data = await _fetch_json(
                        session, f"{base_url}/api/inverter/id/{inv.get('id', 0)}"
                    )
                    if inv_data and "ch" in inv_data:
                        ch = inv_data["ch"]
                        if isinstance(ch, list) and len(ch) > 0 and isinstance(ch[0], list) and len(ch[0]) > 6:
                            total_yield += ch[0][6]
                            has_data = True

                return MeterSnapshot(
                    timestamp=now,
                    pv_erzeugung_kwh=round(total_yield, 3) if has_data else None,
                )

            return MeterSnapshot(timestamp=now)

    async def read_live(
        self, host: str, username: str, password: str
    ) -> Optional[LiveSnapshot]:
        """Liest aktuelle PV-Leistung vom DTU-Gateway."""
        base_url = f"http://{host}"
        now = datetime.now(timezone.utc).isoformat()

        auth = None
        if username and password:
            auth = aiohttp.BasicAuth(username or "admin", password)

        try:
            async with aiohttp.ClientSession(auth=auth) as session:
                # OpenDTU
                data = await _fetch_json(session, f"{base_url}/api/livedata/status")
                if data and "total" in data:
                    power = _get_nested(data, "total", "Power", "v")
                    if power is not None:
                        return LiveSnapshot(timestamp=now, leistung_w=round(power, 1))

                # AhoyDTU Fallback
                inv_list = await _fetch_json(session, f"{base_url}/api/inverter/list")
                if inv_list and "inverter" in inv_list:
                    total_power = 0.0
                    for inv in inv_list["inverter"]:
                        if not inv.get("enabled", False):
                            continue
                        inv_data = await _fetch_json(
                            session, f"{base_url}/api/inverter/id/{inv.get('id', 0)}"
                        )
                        if inv_data and "ch" in inv_data:
                            ch = inv_data["ch"]
                            if isinstance(ch, list) and len(ch) > 0 and isinstance(ch[0], list) and len(ch[0]) > 2:
                                total_power += ch[0][2]  # PAC
                    return LiveSnapshot(timestamp=now, leistung_w=round(total_power, 1))
        except Exception as e:
            logger.warning("DTU read_live fehlgeschlagen: %s", e)
        return None
