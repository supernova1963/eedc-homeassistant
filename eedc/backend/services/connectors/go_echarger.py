"""
go-eCharger Wallbox Connector.

Verbindet sich über die lokale HTTP API v2 mit go-eCharger Wallboxen
(HOME+, Gemini, Gemini flex) und liest den kumulativen Ladezähler aus.

Endpoints:
- GET /api/status?filter=eto,fna,sse,fwv,car → Gefilterte Status-Abfrage
- Fallback GET /status → API v1 für ältere HOME-Modelle

Besonderheiten:
- Keine Authentifizierung nötig (Standard; optional über httpStaAuthentication)
- eto = Gesamt-Energie in Wh (kumulativ, überlebt Neustarts)
- wh = Energie seit letztem Anstecken (wird bei Trennung zurückgesetzt)

HINWEIS: Dieser Connector wurde anhand der go-eCharger API v2 Dokumentation
erstellt, aber noch nicht mit echten Wallboxen verifiziert (getestet=False).
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
    """Holt JSON von der go-eCharger API."""
    try:
        async with session.get(
            url, timeout=aiohttp.ClientTimeout(total=timeout)
        ) as resp:
            if resp.status != 200:
                return None
            return await resp.json(content_type=None)
    except Exception as e:
        logger.warning("go-eCharger API request failed for %s: %s", url, e)
        return None


def _wh_to_kwh(value) -> Optional[float]:
    """Konvertiert Wh zu kWh."""
    if value is None:
        return None
    try:
        return round(float(value) / 1000.0, 3)
    except (ValueError, TypeError):
        return None


@register_connector
class GoEChargerConnector(DeviceConnector):
    """Connector für go-eCharger Wallboxen via lokaler HTTP API."""

    def info(self) -> ConnectorInfo:
        return ConnectorInfo(
            id="go_echarger",
            name="go-eCharger (HOME+ / Gemini)",
            hersteller="go-e",
            beschreibung=(
                "Direktverbindung zu go-eCharger Wallboxen über die lokale "
                "HTTP API. Liest den kumulativen Ladezähler (Gesamt-kWh) aus. "
                "Unterstützt API v2 (HOME+, Gemini) und v1 (ältere HOME)."
            ),
            anleitung=(
                "1. IP-Adresse der Wallbox im lokalen Netzwerk ermitteln\n"
                "   (z.B. über Router oder go-e App)\n"
                "2. HTTP API in der go-e App aktivieren (falls nicht aktiv)\n"
                "3. Benutzername und Passwort können leer gelassen werden\n"
                "   (Standard: keine Authentifizierung)\n"
                "4. Falls HTTP-Authentifizierung aktiviert ist: Zugangsdaten eingeben"
            ),
            getestet=False,
        )

    async def test_connection(
        self, host: str, username: str, password: str
    ) -> ConnectionTestResult:
        """Testet die Verbindung zur go-eCharger Wallbox."""
        base_url = f"http://{host}"

        try:
            auth = None
            if username and password:
                auth = aiohttp.BasicAuth(username, password)

            async with aiohttp.ClientSession(auth=auth) as session:
                # API v2 versuchen (HOME+, Gemini)
                data = await _fetch_json(
                    session, f"{base_url}/api/status?filter=eto,wh,fna,sse,fwv,car,nrg"
                )
                api_version = "v2"

                if not data:
                    # Fallback auf API v1 (ältere HOME)
                    data = await _fetch_json(session, f"{base_url}/status")
                    api_version = "v1"

                if not data:
                    return ConnectionTestResult(
                        erfolg=False,
                        fehler=(
                            f"Keine Antwort von {host}. Ist die IP korrekt, "
                            "die Wallbox eingeschaltet und die HTTP API aktiviert?"
                        ),
                    )

                # Geräteinfo
                geraet_name = data.get("fna", f"go-eCharger ({host})")
                seriennummer = data.get("sse", None)
                firmware = data.get("fwv", None)

                # Sensoren
                sensoren: list[str] = []

                eto = data.get("eto")
                if eto is not None:
                    sensoren.append(f"Ladezähler gesamt: {_wh_to_kwh(eto):.1f} kWh")

                wh = data.get("wh")
                if wh is not None:
                    sensoren.append(f"Aktuelle Ladung: {_wh_to_kwh(wh):.3f} kWh")

                car = data.get("car")
                car_states = {1: "bereit", 2: "lädt", 3: "wartet auf Fahrzeug", 4: "fertig"}
                if car is not None:
                    sensoren.append(f"Status: {car_states.get(car, f'unbekannt ({car})')}")

                nrg = data.get("nrg")
                if isinstance(nrg, list) and len(nrg) >= 12:
                    # nrg[11] = P_Total (Gesamtleistung W)
                    sensoren.append(f"Aktuelle Leistung: {nrg[11]:.0f} W")

                snapshot = self._build_snapshot(data, api_version)

                return ConnectionTestResult(
                    erfolg=True,
                    geraet_name=geraet_name,
                    geraet_typ=f"go-eCharger (API {api_version})",
                    seriennummer=str(seriennummer) if seriennummer else None,
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
            logger.exception("Fehler beim go-eCharger-Verbindungstest")
            return ConnectionTestResult(
                erfolg=False,
                fehler=f"Unerwarteter Fehler: {str(e)}",
            )

    async def read_meters(
        self, host: str, username: str, password: str
    ) -> MeterSnapshot:
        """Liest aktuelle kumulative Zählerstände von der go-eCharger Wallbox."""
        base_url = f"http://{host}"

        auth = None
        if username and password:
            auth = aiohttp.BasicAuth(username, password)

        async with aiohttp.ClientSession(auth=auth) as session:
            # API v2 zuerst
            data = await _fetch_json(
                session, f"{base_url}/api/status?filter=eto"
            )
            api_version = "v2"
            if not data:
                # Fallback v1
                data = await _fetch_json(session, f"{base_url}/status")
                api_version = "v1"

            if not data:
                return MeterSnapshot(
                    timestamp=datetime.now(timezone.utc).isoformat()
                )

            return self._build_snapshot(data, api_version)

    def _build_snapshot(self, data: dict, api_version: str = "v2") -> MeterSnapshot:
        """Baut MeterSnapshot aus go-eCharger API-Daten.

        Wichtig: eto-Einheiten unterscheiden sich je nach API-Version:
        - API v1: eto in 0.1 kWh → /10 für kWh
        - API v2: eto in Wh → /1000 für kWh
        """
        eto = data.get("eto")
        wallbox_kwh = None
        if eto is not None:
            try:
                val = float(eto)
                if api_version == "v1":
                    wallbox_kwh = round(val / 10.0, 3)  # 0.1 kWh → kWh
                else:
                    wallbox_kwh = round(val / 1000.0, 3)  # Wh → kWh
            except (ValueError, TypeError):
                pass

        return MeterSnapshot(
            timestamp=datetime.now(timezone.utc).isoformat(),
            wallbox_ladung_kwh=wallbox_kwh,
        )
