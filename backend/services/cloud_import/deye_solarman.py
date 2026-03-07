"""
Deye/Solarman Cloud-Import-Provider.

Nutzt die SolarMAN Open API v1.1.0 um historische Monatsdaten von Deye
Wechselrichtern abzurufen. Deye-Geräte kommunizieren über die Solarman-Cloud.

Auth: OAuth2 mit appId/appSecret + SHA256-verschlüsseltem Passwort.
Endpoint: POST /station/v1.0/history (timeType=3 für Monatsdaten, max 12 Monate)

HINWEIS: Erfordert einen Solarman-Entwickler-Account (appId + appSecret).
Dieser Provider ist NICHT mit echten Geräten getestet (getestet=False).
"""

import hashlib
import logging
from datetime import datetime
from typing import Optional

import httpx

from backend.services.import_parsers.base import ParsedMonthData

from .base import (
    CloudImportProvider,
    CloudProviderInfo,
    CloudConnectionTestResult,
    CredentialField,
)
from .registry import register_provider

logger = logging.getLogger(__name__)

BASE_URL = "https://api.solarmanpv.com"


@register_provider
class DeyeSolarmanProvider(CloudImportProvider):
    """Cloud-Import-Provider für Deye Wechselrichter (via Solarman Cloud)."""

    def info(self) -> CloudProviderInfo:
        return CloudProviderInfo(
            id="deye_solarman",
            name="Deye / Solarman",
            hersteller="Deye",
            beschreibung=(
                "Importiert historische Monatsdaten von Deye Wechselrichtern "
                "über die Solarman-Cloud-API. Unterstützt PV-Erzeugung, "
                "Einspeisung, Netzbezug, Eigenverbrauch und Batterie-Daten."
            ),
            anleitung=(
                "1. Solarman-Entwicklerkonto unter home.solarmanpv.com anlegen\n"
                "2. App registrieren → appId und appSecret erhalten\n"
                "3. E-Mail/Benutzername und Passwort des Solarman-Kontos bereithalten\n"
                "4. Anlagen-ID (Station ID) aus der Solarman-App ablesen\n"
                "5. Hinweis: Die Station ID ist die numerische ID der Anlage, "
                "nicht der Name"
            ),
            credential_fields=[
                CredentialField(
                    id="app_id",
                    label="App ID",
                    type="text",
                    placeholder="z.B. 202301234567",
                    required=True,
                ),
                CredentialField(
                    id="app_secret",
                    label="App Secret",
                    type="password",
                    placeholder="API App Secret",
                    required=True,
                ),
                CredentialField(
                    id="email",
                    label="E-Mail / Benutzername",
                    type="text",
                    placeholder="Solarman-Konto E-Mail",
                    required=True,
                ),
                CredentialField(
                    id="password",
                    label="Passwort",
                    type="password",
                    placeholder="Solarman-Konto Passwort",
                    required=True,
                ),
                CredentialField(
                    id="station_id",
                    label="Anlagen-ID (Station ID)",
                    type="text",
                    placeholder="z.B. 12345",
                    required=True,
                ),
            ],
            getestet=False,
        )

    async def test_connection(self, credentials: dict) -> CloudConnectionTestResult:
        """Testet die Verbindung zur Solarman-API."""
        app_id = credentials.get("app_id", "")
        app_secret = credentials.get("app_secret", "")
        email = credentials.get("email", "")
        password = credentials.get("password", "")
        station_id = credentials.get("station_id", "")

        if not all([app_id, app_secret, email, password, station_id]):
            return CloudConnectionTestResult(
                erfolg=False,
                fehler="Alle Felder müssen ausgefüllt werden.",
            )

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                token = await self._get_token(client, app_id, app_secret, email, password)
                if not token:
                    return CloudConnectionTestResult(
                        erfolg=False,
                        fehler="Authentifizierung fehlgeschlagen. "
                        "Bitte appId, appSecret, E-Mail und Passwort prüfen.",
                    )

                # Anlagen-Info abrufen
                resp = await client.post(
                    f"{BASE_URL}/station/v1.0/base",
                    headers={"Authorization": token},
                    json={"stationId": int(station_id)},
                )

                if resp.status_code != 200:
                    return CloudConnectionTestResult(
                        erfolg=False,
                        fehler=f"API-Fehler: HTTP {resp.status_code}",
                    )

                data = resp.json()
                if not data.get("success", False):
                    return CloudConnectionTestResult(
                        erfolg=False,
                        fehler=f"API-Fehler: {data.get('msg', 'Unbekannt')}. "
                        "Station ID prüfen.",
                    )

                station = data.get("body", {})
                name = station.get("name", "Deye Anlage")
                capacity = station.get("installedCapacity")

                verfuegbar = f"Anlage: {name}"
                if capacity:
                    verfuegbar += f", {capacity} kWp"

                return CloudConnectionTestResult(
                    erfolg=True,
                    geraet_name=name,
                    geraet_typ="Deye/Solarman",
                    seriennummer=str(station_id),
                    verfuegbare_daten=verfuegbar,
                )

        except httpx.ConnectError:
            return CloudConnectionTestResult(
                erfolg=False,
                fehler="Keine Verbindung zur Solarman-API. Internetzugang prüfen.",
            )
        except httpx.TimeoutException:
            return CloudConnectionTestResult(
                erfolg=False,
                fehler="Zeitüberschreitung bei Verbindung zur Solarman-API.",
            )
        except Exception as e:
            logger.exception("Deye/Solarman Verbindungstest fehlgeschlagen")
            return CloudConnectionTestResult(
                erfolg=False,
                fehler=f"Verbindungsfehler: {str(e)}",
            )

    async def fetch_monthly_data(
        self,
        credentials: dict,
        start_year: int,
        start_month: int,
        end_year: int,
        end_month: int,
    ) -> list[ParsedMonthData]:
        """Holt historische Monatsdaten von der Solarman-API."""
        app_id = credentials.get("app_id", "")
        app_secret = credentials.get("app_secret", "")
        email = credentials.get("email", "")
        password = credentials.get("password", "")
        station_id = int(credentials.get("station_id", "0"))

        results: list[ParsedMonthData] = []

        async with httpx.AsyncClient(timeout=15) as client:
            token = await self._get_token(client, app_id, app_secret, email, password)
            if not token:
                raise Exception("Solarman Authentifizierung fehlgeschlagen")

            # API erlaubt max 12 Monate pro Abfrage → in Jahresblöcke aufteilen
            current = (start_year, start_month)
            end = (end_year, end_month)

            while current <= end:
                # Block: ab current, max 12 Monate, nicht über end hinaus
                block_start_y, block_start_m = current
                block_end_y = block_start_y + (block_start_m + 11) // 12 - 1
                block_end_m = (block_start_m + 11 - 1) % 12 + 1
                if (block_end_y, block_end_m) > end:
                    block_end_y, block_end_m = end

                start_time = f"{block_start_y}-{block_start_m:02d}-01"
                end_time = f"{block_end_y}-{block_end_m:02d}-28"

                resp = await client.post(
                    f"{BASE_URL}/station/v1.0/history",
                    headers={"Authorization": token},
                    json={
                        "stationId": station_id,
                        "timeType": 3,  # Monatsdaten
                        "startTime": start_time,
                        "endTime": end_time,
                    },
                )

                if resp.status_code != 200:
                    logger.warning(f"Solarman API HTTP {resp.status_code} für {start_time}")
                    break

                data = resp.json()
                if not data.get("success", False):
                    logger.warning(f"Solarman API Fehler: {data.get('msg')}")
                    break

                for item in data.get("body", {}).get("stationDataItems", []):
                    jahr = item.get("year")
                    monat = item.get("month")
                    if not jahr or not monat:
                        continue

                    if not ((start_year, start_month) <= (jahr, monat) <= (end_year, end_month)):
                        continue

                    month_data = ParsedMonthData(
                        jahr=jahr,
                        monat=monat,
                        pv_erzeugung_kwh=_round(item.get("generationValue")),
                        einspeisung_kwh=_round(item.get("gridValue")),
                        netzbezug_kwh=_round(item.get("buyValue")),
                        eigenverbrauch_kwh=_round(item.get("useValue")),
                        batterie_ladung_kwh=_round(item.get("chargeValue")),
                        batterie_entladung_kwh=_round(item.get("dischargeValue")),
                    )

                    if month_data.has_data():
                        results.append(month_data)

                # Nächster Block
                next_m = block_end_m + 1
                next_y = block_end_y
                if next_m > 12:
                    next_m = 1
                    next_y += 1
                current = (next_y, next_m)

        return results

    async def _get_token(
        self,
        client: httpx.AsyncClient,
        app_id: str,
        app_secret: str,
        email: str,
        password: str,
    ) -> Optional[str]:
        """Holt einen Access-Token von der Solarman-API."""
        try:
            pw_hash = hashlib.sha256(password.encode("utf-8")).hexdigest()

            resp = await client.post(
                f"{BASE_URL}/account/v1.0/token",
                params={"appId": app_id},
                json={
                    "appSecret": app_secret,
                    "email": email,
                    "password": pw_hash,
                },
            )

            if resp.status_code != 200:
                return None

            data = resp.json()
            if not data.get("success", False):
                # Fallback: username statt email
                resp = await client.post(
                    f"{BASE_URL}/account/v1.0/token",
                    params={"appId": app_id},
                    json={
                        "appSecret": app_secret,
                        "username": email,
                        "password": pw_hash,
                    },
                )
                if resp.status_code != 200:
                    return None
                data = resp.json()
                if not data.get("success", False):
                    return None

            return data.get("body", {}).get("access_token")

        except Exception as e:
            logger.warning(f"Solarman Token-Anfrage fehlgeschlagen: {e}")
            return None


def _round(value: Optional[float]) -> Optional[float]:
    """Rundet auf 2 Dezimalstellen, None bleibt None."""
    if value is None:
        return None
    return round(value, 2)
