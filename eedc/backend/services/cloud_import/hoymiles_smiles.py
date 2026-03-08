"""
Hoymiles S-Miles Cloud-Import-Provider.

Nutzt die reverse-engineered S-Miles Cloud API (global.hoymiles.com) um
historische Energiedaten von Hoymiles Mikrowechselrichtern abzurufen.

Auth: E-Mail + Passwort (S-Miles Cloud Login).
API-Basis: https://global.hoymiles.com/platform/api/gateway

Basiert auf der Community-Dokumentation von:
https://github.com/Xinayder/hoymiles-api

HINWEIS: Reverse-engineered API, kann bei Updates brechen.
Dieser Provider ist NICHT mit echten Geräten getestet (getestet=False).
"""

import hashlib
import json
import logging
import time
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

# API-Endpunkte
API_BASE = "https://global.hoymiles.com/platform/api/gateway"

# API-Pfade
LOGIN_PATH = "/iam/auth_login"
STATION_LIST_PATH = "/pvm/station_select_by_page"
STATION_DATA_PATH = "/pvm-data/data_count_station_real_data"


def _default_headers() -> dict:
    """Standard-Header für die S-Miles Cloud API."""
    return {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _make_body(path: str, payload: dict, token: str = "") -> dict:
    """Request-Body im S-Miles API-Format erstellen."""
    body = {
        "body": payload,
        "header": {
            "hm_token": token,
            "language": "de",
            "time": str(int(time.time())),
        },
    }
    return body


async def _login(
    client: httpx.AsyncClient,
    email: str,
    password: str,
) -> str:
    """Login bei der S-Miles Cloud und Token erhalten.

    Returns:
        Auth-Token (hm_token)
    """
    payload = {
        "user_name": email,
        "password": hashlib.md5(password.encode("utf-8")).hexdigest(),
    }

    body = _make_body(LOGIN_PATH, payload)

    resp = await client.post(
        f"{API_BASE}{LOGIN_PATH}",
        json=body,
    )

    if resp.status_code != 200:
        raise Exception(f"Login fehlgeschlagen: HTTP {resp.status_code}")

    data = resp.json()
    status = data.get("status", "")

    if status != "0":
        msg = data.get("message", "Unbekannter Fehler")
        raise Exception(f"Login fehlgeschlagen: {msg}")

    token = data.get("data", {}).get("token", "")
    if not token:
        raise Exception("Kein Token in der Login-Response erhalten.")

    return token


async def _get_stations(
    client: httpx.AsyncClient,
    token: str,
) -> list[dict]:
    """Liste aller Stationen (Anlagen) abrufen."""
    payload = {
        "page": 1,
        "page_size": 20,
    }

    body = _make_body(STATION_LIST_PATH, payload, token)

    resp = await client.post(
        f"{API_BASE}{STATION_LIST_PATH}",
        json=body,
    )

    if resp.status_code != 200:
        raise Exception(f"Stationsliste fehlgeschlagen: HTTP {resp.status_code}")

    data = resp.json()
    if data.get("status", "") != "0":
        raise Exception(f"Stationsliste Fehler: {data.get('message', 'Unbekannt')}")

    return data.get("data", {}).get("list", [])


async def _get_station_monthly_data(
    client: httpx.AsyncClient,
    token: str,
    station_id: str,
    year: int,
    month: int,
) -> dict:
    """Monatsdaten für eine Station abrufen.

    Die API liefert Produktionsdaten für den angegebenen Monat.
    """
    # Datum im Format YYYY-MM
    date_str = f"{year}-{month:02d}"

    payload = {
        "sid": station_id,
        "date": date_str,
        "range": 2,  # 1=Tag, 2=Monat, 3=Jahr
    }

    body = _make_body(STATION_DATA_PATH, payload, token)

    resp = await client.post(
        f"{API_BASE}{STATION_DATA_PATH}",
        json=body,
    )

    if resp.status_code != 200:
        raise Exception(f"Monatsdaten fehlgeschlagen: HTTP {resp.status_code}")

    data = resp.json()
    if data.get("status", "") != "0":
        raise Exception(f"Monatsdaten Fehler: {data.get('message', 'Unbekannt')}")

    return data.get("data", {})


def _safe_float(value, divisor: float = 1.0) -> Optional[float]:
    """Sicher einen Wert in float umwandeln, optional durch divisor teilen."""
    if value is None or value == "" or value == "null":
        return None
    try:
        f = float(value) / divisor
        return f if f >= 0 else None
    except (ValueError, TypeError):
        return None


@register_provider
class HoymilesSmilesProvider(CloudImportProvider):
    """Cloud-Import-Provider für Hoymiles Mikrowechselrichter (S-Miles Cloud)."""

    def info(self) -> CloudProviderInfo:
        return CloudProviderInfo(
            id="hoymiles_smiles",
            name="Hoymiles S-Miles Cloud",
            hersteller="Hoymiles",
            beschreibung=(
                "Importiert historische Energiedaten (PV-Erzeugung) von Hoymiles "
                "Mikrowechselrichtern (HMS, HM, HMT Serie) über die S-Miles Cloud. "
                "Besonders geeignet für Balkonkraftwerke mit Hoymiles Wechselrichter."
            ),
            anleitung=(
                "1. S-Miles Cloud Account unter global.hoymiles.com anlegen\n"
                "2. Wechselrichter in der S-Miles Cloud registrieren "
                "(oder über die Hoymiles App)\n"
                "3. Zugangsdaten (E-Mail + Passwort) hier eingeben\n\n"
                "Hinweis: Dies nutzt die inoffizielle S-Miles Cloud API. "
                "Für lokale Abfrage (ohne Cloud) empfiehlt sich OpenDTU/AhoyDTU "
                "in Kombination mit Home Assistant."
            ),
            credential_fields=[
                CredentialField(
                    id="email",
                    label="E-Mail",
                    type="text",
                    placeholder="name@example.com",
                    required=True,
                ),
                CredentialField(
                    id="password",
                    label="Passwort",
                    type="password",
                    placeholder="Ihr S-Miles Cloud Passwort",
                    required=True,
                ),
            ],
            getestet=False,
        )

    async def test_connection(self, credentials: dict) -> CloudConnectionTestResult:
        """Testet die Verbindung zur S-Miles Cloud."""
        email = credentials.get("email", "")
        password = credentials.get("password", "")

        if not email or not password:
            return CloudConnectionTestResult(
                erfolg=False,
                fehler="E-Mail und Passwort sind erforderlich.",
            )

        try:
            async with httpx.AsyncClient(
                timeout=20, headers=_default_headers()
            ) as client:
                token = await _login(client, email, password)
                stations = await _get_stations(client, token)

            if not stations:
                return CloudConnectionTestResult(
                    erfolg=True,
                    geraet_name="Hoymiles",
                    geraet_typ="Keine Station gefunden",
                    verfuegbare_daten="Login erfolgreich, aber keine Station konfiguriert.",
                )

            station = stations[0]
            station_name = station.get("station_name", "Unbenannt")
            station_id = str(station.get("id", ""))
            capacity = station.get("capacity", "")

            # Geräteinfo
            verfuegbar = f"Station: {station_name}"
            if capacity:
                verfuegbar += f", Kapazität: {capacity} W"
            if len(stations) > 1:
                verfuegbar += f" (+{len(stations) - 1} weitere)"

            return CloudConnectionTestResult(
                erfolg=True,
                geraet_name=station_name,
                geraet_typ="Hoymiles Mikrowechselrichter",
                seriennummer=station_id,
                verfuegbare_daten=verfuegbar,
            )

        except httpx.TimeoutException:
            return CloudConnectionTestResult(
                erfolg=False,
                fehler="Zeitüberschreitung bei der Verbindung zur S-Miles Cloud.",
            )
        except Exception as e:
            logger.exception("Hoymiles S-Miles Verbindungstest fehlgeschlagen")
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
        """Holt historische Monatsdaten von der S-Miles Cloud.

        Pro Monat wird ein API-Request gemacht.
        """
        email = credentials.get("email", "")
        password = credentials.get("password", "")

        results: list[ParsedMonthData] = []

        async with httpx.AsyncClient(
            timeout=20, headers=_default_headers()
        ) as client:
            # Login
            token = await _login(client, email, password)

            # Erste Station ermitteln
            stations = await _get_stations(client, token)
            if not stations:
                logger.warning("Hoymiles: Keine Station gefunden")
                return []

            station_id = str(stations[0].get("id", ""))

            # Monate iterieren
            current_year = start_year
            current_month = start_month

            while (current_year, current_month) <= (end_year, end_month):
                # Nicht in der Zukunft abfragen
                now = datetime.now()
                if datetime(current_year, current_month, 1) > now:
                    break

                try:
                    month_result = await self._fetch_single_month(
                        client, token, station_id,
                        current_year, current_month,
                    )
                    if month_result and month_result.has_data():
                        results.append(month_result)
                except Exception as e:
                    logger.warning(
                        f"Hoymiles Monat {current_year}-{current_month:02d} "
                        f"fehlgeschlagen: {e}"
                    )

                if current_month == 12:
                    current_year += 1
                    current_month = 1
                else:
                    current_month += 1

        return results

    async def _fetch_single_month(
        self,
        client: httpx.AsyncClient,
        token: str,
        station_id: str,
        year: int,
        month: int,
    ) -> Optional[ParsedMonthData]:
        """Daten für einen einzelnen Monat abrufen."""
        data = await _get_station_monthly_data(
            client, token, station_id, year, month,
        )

        if not data:
            return None

        # Die S-Miles API liefert verschiedene Feld-Varianten
        # Werte können in Wh oder kWh sein (abhängig von der API-Version)
        pv_kwh = _safe_float(
            data.get("total_eq")
            or data.get("real_power")
            or data.get("today_eq")
        )

        # Einspeisung (falls Smart Meter angeschlossen)
        feed_in = _safe_float(data.get("grid_eq") or data.get("feed_in_eq"))

        # Eigenverbrauch (falls Smart Meter angeschlossen)
        self_use = _safe_float(data.get("self_eq") or data.get("self_consumption_eq"))

        # Netzbezug
        grid_purchase = _safe_float(data.get("grid_purchase_eq"))

        # Prüfen ob Werte in Wh statt kWh (typisch >1000 für einen Monat BKW)
        # Hoymiles liefert teilweise in Wh
        if pv_kwh is not None and pv_kwh > 10000:
            pv_kwh = pv_kwh / 1000
        if feed_in is not None and feed_in > 10000:
            feed_in = feed_in / 1000
        if self_use is not None and self_use > 10000:
            self_use = self_use / 1000
        if grid_purchase is not None and grid_purchase > 10000:
            grid_purchase = grid_purchase / 1000

        return ParsedMonthData(
            jahr=year,
            monat=month,
            pv_erzeugung_kwh=round(pv_kwh, 2) if pv_kwh is not None else None,
            einspeisung_kwh=round(feed_in, 2) if feed_in is not None else None,
            eigenverbrauch_kwh=round(self_use, 2) if self_use is not None else None,
            netzbezug_kwh=round(grid_purchase, 2) if grid_purchase is not None else None,
        )
