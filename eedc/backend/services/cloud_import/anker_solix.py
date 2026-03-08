"""
Anker SOLIX Cloud-Import-Provider.

Nutzt die reverse-engineered Anker Cloud-API um historische Energiedaten
von Anker SOLIX Solarbank (und MI80 Mikrowechselrichter) abzurufen.

Auth: E-Mail + Passwort (identisch zur Anker App).
API-Basis: https://ankerpower-api-eu.anker.com (EU)

Basiert auf der Community-Dokumentation von:
https://github.com/thomluther/anker-solix-api

HINWEIS: Reverse-engineered API, kann bei App-Updates brechen.
Dieser Provider ist NICHT mit echten Geräten getestet (getestet=False).
"""

import hashlib
import json
import logging
import time
import uuid
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
API_BASE_EU = "https://ankerpower-api-eu.anker.com"
API_BASE_COM = "https://ankerpower-api.anker.com"

# API-Pfade
LOGIN_PATH = "/passport/login"
SITE_LIST_PATH = "/power_service/v1/site/get_site_list"
ENERGY_DAILY_PATH = "/power_service/v1/site/energy_daily"

# Standard-Header für Anker API
APP_VERSION = "2.9.2"
MODEL_TYPE = "PHONE"
OS_TYPE = "android"


def _get_api_base(server: str) -> str:
    """API-Basis-URL für den gewählten Server."""
    if server == "com":
        return API_BASE_COM
    return API_BASE_EU


def _default_headers() -> dict:
    """Standard-Header die bei jedem Request mitgeschickt werden."""
    return {
        "Content-Type": "application/json",
        "App-Version": APP_VERSION,
        "Model-Type": MODEL_TYPE,
        "Os-Type": OS_TYPE,
        "Country": "DE",
        "Timezone": "Europe/Berlin",
        "gtoken": "",
    }


def _hash_password(password: str) -> str:
    """Passwort-Hash für die Anker API (MD5 des MD5)."""
    first = hashlib.md5(password.encode("utf-8")).hexdigest()
    return hashlib.md5(first.encode("utf-8")).hexdigest()


async def _login(
    client: httpx.AsyncClient,
    api_base: str,
    email: str,
    password: str,
) -> tuple[str, str]:
    """Login bei der Anker API und Auth-Token erhalten.

    Returns:
        Tuple von (auth_token, user_id)
    """
    payload = {
        "ab": "DE",
        "client_secret_info": {
            "public_key": "",
        },
        "enc": 0,
        "email": email,
        "password": _hash_password(password),
        "time_zone": 2,
        "transaction": str(uuid.uuid4()),
    }

    resp = await client.post(
        f"{api_base}{LOGIN_PATH}",
        json=payload,
    )

    if resp.status_code != 200:
        raise Exception(f"Login fehlgeschlagen: HTTP {resp.status_code}")

    data = resp.json()
    code = data.get("code", -1)

    if code != 0:
        msg = data.get("msg", "Unbekannter Fehler")
        raise Exception(f"Login fehlgeschlagen: {msg} (Code: {code})")

    result = data.get("data", {})
    token = result.get("auth_token", "")
    user_id = result.get("user_id", "")

    if not token:
        raise Exception("Kein Auth-Token in der Login-Response erhalten.")

    return token, user_id


async def _get_site_list(
    client: httpx.AsyncClient,
    api_base: str,
    auth_token: str,
) -> list[dict]:
    """Liste der Anlagen (Sites) abrufen."""
    headers = _default_headers()
    headers["gtoken"] = auth_token

    resp = await client.post(
        f"{api_base}{SITE_LIST_PATH}",
        json={},
        headers=headers,
    )

    if resp.status_code != 200:
        raise Exception(f"Site-Liste abrufen fehlgeschlagen: HTTP {resp.status_code}")

    data = resp.json()
    if data.get("code", -1) != 0:
        raise Exception(f"Site-Liste Fehler: {data.get('msg', 'Unbekannt')}")

    return data.get("data", {}).get("site_list", [])


async def _get_energy_daily(
    client: httpx.AsyncClient,
    api_base: str,
    auth_token: str,
    site_id: str,
    start_date: str,
    end_date: str,
) -> list[dict]:
    """Tagesweise Energiedaten für eine Site abrufen.

    Args:
        start_date: Format "YYYY-MM-DD"
        end_date: Format "YYYY-MM-DD"
    """
    headers = _default_headers()
    headers["gtoken"] = auth_token

    payload = {
        "site_id": site_id,
        "start_day": start_date,
        "end_day": end_date,
        "device_sn": "",
    }

    resp = await client.post(
        f"{api_base}{ENERGY_DAILY_PATH}",
        json=payload,
        headers=headers,
    )

    if resp.status_code != 200:
        raise Exception(f"Energiedaten abrufen fehlgeschlagen: HTTP {resp.status_code}")

    data = resp.json()
    if data.get("code", -1) != 0:
        raise Exception(f"Energiedaten Fehler: {data.get('msg', 'Unbekannt')}")

    return data.get("data", {}).get("statistics", [])


def _safe_float(value) -> Optional[float]:
    """Sicher einen Wert in float umwandeln."""
    if value is None or value == "" or value == "null":
        return None
    try:
        f = float(value)
        return f if f >= 0 else None
    except (ValueError, TypeError):
        return None


@register_provider
class AnkerSolixProvider(CloudImportProvider):
    """Cloud-Import-Provider für Anker SOLIX (Solarbank, MI80)."""

    def info(self) -> CloudProviderInfo:
        return CloudProviderInfo(
            id="anker_solix",
            name="Anker SOLIX",
            hersteller="Anker",
            beschreibung=(
                "Importiert historische Energiedaten (PV-Erzeugung, Einspeisung, "
                "Eigenverbrauch) von Anker SOLIX Solarbank und MI80 Mikrowechselrichter "
                "(Balkonkraftwerk) über die Anker Cloud-API."
            ),
            anleitung=(
                "1. Anker App Zugangsdaten bereithalten (E-Mail + Passwort)\n"
                "2. Es werden die gleichen Zugangsdaten wie in der Anker App verwendet\n"
                "3. Server-Region wählen (EU für europäische Accounts)\n\n"
                "Hinweis: Dies nutzt die inoffizielle Anker Cloud-API. "
                "Die Verbindung kann bei App-Updates vorübergehend gestört werden.\n"
                "Seit App-Version 3.10 werden parallele Logins unterstützt — "
                "die App wird nicht mehr ausgeloggt."
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
                    placeholder="Ihr Anker App Passwort",
                    required=True,
                ),
                CredentialField(
                    id="server",
                    label="Server-Region",
                    type="select",
                    required=True,
                    options=[
                        {"value": "eu", "label": "Europa (EU)"},
                        {"value": "com", "label": "Global (US/Asien)"},
                    ],
                ),
            ],
            getestet=False,
        )

    async def test_connection(self, credentials: dict) -> CloudConnectionTestResult:
        """Testet die Verbindung zur Anker Cloud-API."""
        email = credentials.get("email", "")
        password = credentials.get("password", "")
        server = credentials.get("server", "eu")

        if not email or not password:
            return CloudConnectionTestResult(
                erfolg=False,
                fehler="E-Mail und Passwort sind erforderlich.",
            )

        api_base = _get_api_base(server)

        try:
            async with httpx.AsyncClient(
                timeout=20, headers=_default_headers()
            ) as client:
                auth_token, user_id = await _login(client, api_base, email, password)
                sites = await _get_site_list(client, api_base, auth_token)

            if not sites:
                return CloudConnectionTestResult(
                    erfolg=True,
                    geraet_name="Anker SOLIX",
                    geraet_typ="Keine Anlage gefunden",
                    verfuegbare_daten="Login erfolgreich, aber keine Anlage konfiguriert.",
                )

            site = sites[0]
            site_name = site.get("site_name", "Unbenannt")
            site_id = site.get("site_id", "")

            # Geräte-Infos sammeln
            devices = site.get("solarbank_list", []) + site.get("pps_list", [])
            device_names = [d.get("device_name", "Unbekannt") for d in devices]

            return CloudConnectionTestResult(
                erfolg=True,
                geraet_name=site_name,
                geraet_typ="Anker SOLIX Balkonkraftwerk",
                seriennummer=site_id,
                verfuegbare_daten=(
                    f"Anlage: {site_name}, "
                    f"Geräte: {', '.join(device_names) if device_names else 'keine'}"
                ),
            )

        except httpx.TimeoutException:
            return CloudConnectionTestResult(
                erfolg=False,
                fehler="Zeitüberschreitung bei der Verbindung zur Anker API.",
            )
        except Exception as e:
            logger.exception("Anker SOLIX Verbindungstest fehlgeschlagen")
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
        """Holt historische Monatsdaten von der Anker SOLIX Cloud.

        Die API liefert Tagesdaten. Diese werden pro Monat aggregiert.
        Rate-Limit beachten: max. ~10 Requests/Minute.
        """
        email = credentials.get("email", "")
        password = credentials.get("password", "")
        server = credentials.get("server", "eu")

        api_base = _get_api_base(server)
        results: list[ParsedMonthData] = []

        async with httpx.AsyncClient(
            timeout=20, headers=_default_headers()
        ) as client:
            # Login
            auth_token, user_id = await _login(client, api_base, email, password)

            # Erste Site ermitteln
            sites = await _get_site_list(client, api_base, auth_token)
            if not sites:
                logger.warning("Anker SOLIX: Keine Anlage gefunden")
                return []

            site_id = sites[0].get("site_id", "")

            # Monate iterieren
            current_year = start_year
            current_month = start_month

            while (current_year, current_month) <= (end_year, end_month):
                try:
                    month_data = await self._fetch_single_month(
                        client, api_base, auth_token, site_id,
                        current_year, current_month,
                    )
                    if month_data and month_data.has_data():
                        results.append(month_data)
                except Exception as e:
                    logger.warning(
                        f"Anker SOLIX Monat {current_year}-{current_month:02d} "
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
        api_base: str,
        auth_token: str,
        site_id: str,
        year: int,
        month: int,
    ) -> Optional[ParsedMonthData]:
        """Tagesdaten für einen Monat abrufen und aggregieren."""
        # Monatsanfang/-ende berechnen
        start_date = f"{year}-{month:02d}-01"
        if month == 12:
            end_date = f"{year + 1}-01-01"
        else:
            end_date = f"{year}-{month + 1:02d}-01"

        # Nicht in der Zukunft abfragen
        now = datetime.now()
        if datetime(year, month, 1) > now:
            return None

        daily_data = await _get_energy_daily(
            client, api_base, auth_token, site_id,
            start_date, end_date,
        )

        if not daily_data:
            return None

        # Tageswerte aggregieren
        pv_total = 0.0
        einspeisung_total = 0.0
        eigenverbrauch_total = 0.0
        batterie_ladung_total = 0.0
        batterie_entladung_total = 0.0
        has_any = False

        for day in daily_data:
            # Die Anker API liefert verschiedene Feld-Varianten
            pv = _safe_float(day.get("solar_production") or day.get("solar_total"))
            feed_in = _safe_float(day.get("grid_to") or day.get("to_grid"))
            self_use = _safe_float(
                day.get("home_usage") or day.get("self_consumption")
            )
            bat_charge = _safe_float(
                day.get("battery_charge") or day.get("charge_battery")
            )
            bat_discharge = _safe_float(
                day.get("battery_discharge") or day.get("discharge_battery")
            )

            if pv is not None:
                pv_total += pv
                has_any = True
            if feed_in is not None:
                einspeisung_total += feed_in
                has_any = True
            if self_use is not None:
                eigenverbrauch_total += self_use
                has_any = True
            if bat_charge is not None:
                batterie_ladung_total += bat_charge
                has_any = True
            if bat_discharge is not None:
                batterie_entladung_total += bat_discharge
                has_any = True

        if not has_any:
            return None

        return ParsedMonthData(
            jahr=year,
            monat=month,
            pv_erzeugung_kwh=round(pv_total, 2) or None,
            einspeisung_kwh=round(einspeisung_total, 2) or None,
            eigenverbrauch_kwh=round(eigenverbrauch_total, 2) or None,
            batterie_ladung_kwh=round(batterie_ladung_total, 2) or None,
            batterie_entladung_kwh=round(batterie_entladung_total, 2) or None,
        )
