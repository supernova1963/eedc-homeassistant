"""
Sungrow iSolarCloud Cloud-Import-Provider.

Nutzt die iSolarCloud API um historische Energiedaten von Sungrow
Wechselrichtern (SG, SH Serie) abzurufen.

Auth: AppKey + User-Account + Passwort (API-Key-basiert).
Regionale Server: EU (gateway.isolarcloud.eu), Global (gateway.isolarcloud.com).

Referenz-Implementierungen:
- https://github.com/MickMake/GoSungrow (GoLang, reverse-engineered)
- https://github.com/bugjam/pysolarcloud (Python, offizielle API)

HINWEIS: Dieser Provider ist NICHT mit echten Geräten getestet (getestet=False).
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

# Regionale API-Server
API_HOSTS = {
    "eu": "https://gateway.isolarcloud.eu",
    "global": "https://gateway.isolarcloud.com",
    "au": "https://augateway.isolarcloud.com",
    "hk": "https://gateway.isolarcloud.com.hk",
}

# Bekannter AppKey (Android App, kann sich ändern)
DEFAULT_APPKEY = "ANDROIDE13EC118BD7892FE7AB5A3F20"

# API-Pfade
LOGIN_PATH = "/v1/userService/login"
PLANT_LIST_PATH = "/v1/powerStationService/getPsList"
PLANT_REPORT_PATH = "/v1/powerStationService/getHouseholdStoragePsReport"
POWER_STATS_PATH = "/v1/powerStationService/getPowerStatistics"


def _hash_password(password: str) -> str:
    """Passwort als SHA-256 Hash (hex, lowercase)."""
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def _make_headers() -> dict:
    """Standard-Header für iSolarCloud API."""
    return {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "sys_code": "901",
        "x-access-key": DEFAULT_APPKEY,
    }


async def _login(
    client: httpx.AsyncClient,
    host: str,
    appkey: str,
    account: str,
    password: str,
) -> tuple[str, str]:
    """Login bei iSolarCloud und Token + User-ID erhalten.

    Returns:
        Tuple von (token, user_id)
    """
    payload = {
        "appkey": appkey,
        "user_account": account,
        "user_password": _hash_password(password),
    }

    resp = await client.post(
        f"{host}{LOGIN_PATH}",
        json=payload,
    )

    if resp.status_code != 200:
        raise Exception(f"Login fehlgeschlagen: HTTP {resp.status_code}")

    data = resp.json()
    result_code = data.get("result_code")

    if result_code != 1 and str(result_code) != "1":
        msg = data.get("result_msg", "Unbekannter Fehler")
        raise Exception(f"Login fehlgeschlagen: {msg}")

    result_data = data.get("result_data", {})
    token = result_data.get("token", "")
    user_id = str(result_data.get("user_id", ""))

    if not token:
        raise Exception("Kein Token in der Login-Response erhalten.")

    return token, user_id


async def _get_plant_list(
    client: httpx.AsyncClient,
    host: str,
    token: str,
    appkey: str,
) -> list[dict]:
    """Liste aller PV-Anlagen (Power Stations) abrufen."""
    payload = {
        "appkey": appkey,
        "token": token,
        "curPage": 1,
        "size": 20,
    }

    resp = await client.post(
        f"{host}{PLANT_LIST_PATH}",
        json=payload,
    )

    if resp.status_code != 200:
        raise Exception(f"Anlagenliste fehlgeschlagen: HTTP {resp.status_code}")

    data = resp.json()
    if data.get("result_code") != 1 and str(data.get("result_code")) != "1":
        raise Exception(f"Anlagenliste Fehler: {data.get('result_msg', 'Unbekannt')}")

    page_list = data.get("result_data", {}).get("pageList", [])
    return page_list


async def _get_monthly_report(
    client: httpx.AsyncClient,
    host: str,
    token: str,
    appkey: str,
    ps_id: str,
    year: int,
    month: int,
) -> dict:
    """Monatsbericht für eine Anlage abrufen (Hybrid/Speicher-Anlagen)."""
    date_str = f"{year}{month:02d}"

    payload = {
        "appkey": appkey,
        "token": token,
        "ps_id": ps_id,
        "date_id": date_str,
        "date_type": "4",  # 4 = Monat
    }

    resp = await client.post(
        f"{host}{PLANT_REPORT_PATH}",
        json=payload,
    )

    if resp.status_code != 200:
        raise Exception(f"Monatsbericht fehlgeschlagen: HTTP {resp.status_code}")

    data = resp.json()
    if data.get("result_code") != 1 and str(data.get("result_code")) != "1":
        # Fallback auf getPowerStatistics für reine PV-Anlagen (ohne Speicher)
        return await _get_power_statistics(
            client, host, token, appkey, ps_id, year, month,
        )

    return data.get("result_data", {})


async def _get_power_statistics(
    client: httpx.AsyncClient,
    host: str,
    token: str,
    appkey: str,
    ps_id: str,
    year: int,
    month: int,
) -> dict:
    """Fallback: Einfache Leistungsstatistiken für reine PV-Anlagen."""
    date_str = f"{year}{month:02d}"

    payload = {
        "appkey": appkey,
        "token": token,
        "ps_id": ps_id,
        "date_id": date_str,
        "date_type": "4",
    }

    resp = await client.post(
        f"{host}{POWER_STATS_PATH}",
        json=payload,
    )

    if resp.status_code != 200:
        raise Exception(f"Statistiken fehlgeschlagen: HTTP {resp.status_code}")

    data = resp.json()
    return data.get("result_data", {})


def _safe_float(value) -> Optional[float]:
    """Sicher einen Wert in float umwandeln."""
    if value is None or value == "" or value == "--" or value == "null":
        return None
    try:
        f = float(value)
        return f if f >= 0 else None
    except (ValueError, TypeError):
        return None


def _extract_kwh(data: dict, *keys: str) -> Optional[float]:
    """Ersten gültigen kWh-Wert aus mehreren möglichen Schlüsseln extrahieren."""
    for key in keys:
        val = _safe_float(data.get(key))
        if val is not None:
            return val
    return None


@register_provider
class SungrowISolarCloudProvider(CloudImportProvider):
    """Cloud-Import-Provider für Sungrow Wechselrichter (iSolarCloud)."""

    def info(self) -> CloudProviderInfo:
        return CloudProviderInfo(
            id="sungrow_isolarcloud",
            name="Sungrow iSolarCloud",
            hersteller="Sungrow",
            beschreibung=(
                "Importiert historische Energiedaten (PV-Erzeugung, Einspeisung, "
                "Netzbezug, Batterie, Eigenverbrauch) von Sungrow Wechselrichtern "
                "(SG, SH Serie) über die iSolarCloud."
            ),
            anleitung=(
                "1. iSolarCloud Account unter isolarcloud.com anlegen "
                "(oder in der iSolarCloud App)\n"
                "2. Wechselrichter in der iSolarCloud registrieren\n"
                "3. Zugangsdaten (E-Mail/Account + Passwort) hier eingeben\n"
                "4. Server-Region passend zum Account wählen "
                "(EU für europäische Accounts)\n\n"
                "Unterstützte Geräte: SG-Serie (String-WR), SH-Serie (Hybrid-WR), "
                "SBR-Serie (Speicher)."
            ),
            credential_fields=[
                CredentialField(
                    id="account",
                    label="Account / E-Mail",
                    type="text",
                    placeholder="name@example.com oder Benutzername",
                    required=True,
                ),
                CredentialField(
                    id="password",
                    label="Passwort",
                    type="password",
                    placeholder="Ihr iSolarCloud Passwort",
                    required=True,
                ),
                CredentialField(
                    id="region",
                    label="Server-Region",
                    type="select",
                    required=True,
                    options=[
                        {"value": "eu", "label": "Europa (EU)"},
                        {"value": "global", "label": "Global (China/International)"},
                        {"value": "au", "label": "Australien"},
                        {"value": "hk", "label": "Hongkong"},
                    ],
                ),
            ],
            getestet=False,
        )

    async def test_connection(self, credentials: dict) -> CloudConnectionTestResult:
        """Testet die Verbindung zur iSolarCloud."""
        account = credentials.get("account", "")
        password = credentials.get("password", "")
        region = credentials.get("region", "eu")

        if not account or not password:
            return CloudConnectionTestResult(
                erfolg=False,
                fehler="Account und Passwort sind erforderlich.",
            )

        host = API_HOSTS.get(region, API_HOSTS["eu"])

        try:
            async with httpx.AsyncClient(
                timeout=20, headers=_make_headers()
            ) as client:
                token, user_id = await _login(
                    client, host, DEFAULT_APPKEY, account, password,
                )
                plants = await _get_plant_list(
                    client, host, token, DEFAULT_APPKEY,
                )

            if not plants:
                return CloudConnectionTestResult(
                    erfolg=True,
                    geraet_name="Sungrow",
                    geraet_typ="Keine Anlage gefunden",
                    verfuegbare_daten="Login erfolgreich, aber keine Anlage konfiguriert.",
                )

            plant = plants[0]
            plant_name = plant.get("ps_name", "Unbenannt")
            ps_id = str(plant.get("ps_id", ""))
            capacity = plant.get("design_capacity", "")
            ps_type = plant.get("ps_type_name", "PV-Anlage")

            verfuegbar = f"Anlage: {plant_name}, Typ: {ps_type}"
            if capacity:
                verfuegbar += f", {capacity} kWp"
            if len(plants) > 1:
                verfuegbar += f" (+{len(plants) - 1} weitere)"

            return CloudConnectionTestResult(
                erfolg=True,
                geraet_name=plant_name,
                geraet_typ=f"Sungrow {ps_type}",
                seriennummer=ps_id,
                verfuegbare_daten=verfuegbar,
            )

        except httpx.TimeoutException:
            return CloudConnectionTestResult(
                erfolg=False,
                fehler="Zeitüberschreitung bei der Verbindung zur iSolarCloud.",
            )
        except Exception as e:
            logger.exception("Sungrow iSolarCloud Verbindungstest fehlgeschlagen")
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
        """Holt historische Monatsdaten von der iSolarCloud.

        Pro Monat wird ein API-Request gemacht. Bei Hybrid-Anlagen (SH-Serie)
        werden erweiterte Daten (Batterie, Eigenverbrauch) abgerufen.
        """
        account = credentials.get("account", "")
        password = credentials.get("password", "")
        region = credentials.get("region", "eu")

        host = API_HOSTS.get(region, API_HOSTS["eu"])
        results: list[ParsedMonthData] = []

        async with httpx.AsyncClient(
            timeout=20, headers=_make_headers()
        ) as client:
            token, user_id = await _login(
                client, host, DEFAULT_APPKEY, account, password,
            )

            plants = await _get_plant_list(
                client, host, token, DEFAULT_APPKEY,
            )
            if not plants:
                logger.warning("Sungrow: Keine Anlage gefunden")
                return []

            ps_id = str(plants[0].get("ps_id", ""))

            current_year = start_year
            current_month = start_month

            while (current_year, current_month) <= (end_year, end_month):
                now = datetime.now()
                if datetime(current_year, current_month, 1) > now:
                    break

                try:
                    month_data = await self._fetch_single_month(
                        client, host, token, DEFAULT_APPKEY, ps_id,
                        current_year, current_month,
                    )
                    if month_data and month_data.has_data():
                        results.append(month_data)
                except Exception as e:
                    logger.warning(
                        f"Sungrow Monat {current_year}-{current_month:02d} "
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
        host: str,
        token: str,
        appkey: str,
        ps_id: str,
        year: int,
        month: int,
    ) -> Optional[ParsedMonthData]:
        """Daten für einen einzelnen Monat abrufen."""
        data = await _get_monthly_report(
            client, host, token, appkey, ps_id, year, month,
        )

        if not data:
            return None

        # iSolarCloud liefert verschiedene Feld-Varianten
        # je nach Anlagentyp (PV-only vs. Hybrid mit Speicher)
        pv_kwh = _extract_kwh(
            data,
            "p83022",          # PV-Erzeugung (kWh) - Household Report
            "total_pv_energy", # PV-Erzeugung (Power Statistics)
            "pv_energy",
            "energy_pv",
        )

        einspeisung_kwh = _extract_kwh(
            data,
            "p83025",           # Einspeisung (kWh)
            "grid_feed_energy",
            "feed_in_energy",
            "energy_feed_in",
        )

        netzbezug_kwh = _extract_kwh(
            data,
            "p83024",            # Netzbezug (kWh)
            "grid_purchase_energy",
            "purchased_energy",
            "energy_purchased",
        )

        batterie_ladung_kwh = _extract_kwh(
            data,
            "p83027",           # Batterie-Ladung (kWh)
            "charge_energy",
            "battery_charge_energy",
        )

        batterie_entladung_kwh = _extract_kwh(
            data,
            "p83028",             # Batterie-Entladung (kWh)
            "discharge_energy",
            "battery_discharge_energy",
        )

        eigenverbrauch_kwh = _extract_kwh(
            data,
            "p83023",              # Eigenverbrauch (kWh)
            "self_consumption_energy",
            "self_use_energy",
            "energy_self_consumption",
        )

        return ParsedMonthData(
            jahr=year,
            monat=month,
            pv_erzeugung_kwh=round(pv_kwh, 2) if pv_kwh is not None else None,
            einspeisung_kwh=round(einspeisung_kwh, 2) if einspeisung_kwh is not None else None,
            netzbezug_kwh=round(netzbezug_kwh, 2) if netzbezug_kwh is not None else None,
            batterie_ladung_kwh=round(batterie_ladung_kwh, 2) if batterie_ladung_kwh is not None else None,
            batterie_entladung_kwh=round(batterie_entladung_kwh, 2) if batterie_entladung_kwh is not None else None,
            eigenverbrauch_kwh=round(eigenverbrauch_kwh, 2) if eigenverbrauch_kwh is not None else None,
        )
