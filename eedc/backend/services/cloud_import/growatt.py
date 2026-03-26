"""
Growatt Cloud-Import-Provider.

Nutzt die Growatt Server API um historische Energiedaten abzurufen.

Auth: Login mit Username + MD5(Password) → Session-Cookie.
Base URL: https://openapi.growatt.com/

Endpoints:
  - POST /newTwoLoginAPI.do                → Login
  - POST /newPlantAPI.do                   → Pflanzenliste
  - GET  /PlantDetailAPI.do                → Monatsübersicht mit Energiedaten

HINWEIS: Dieser Provider nutzt die klassische Growatt-Server-API mit
Session-basierter Authentifizierung (gleiche Zugangsdaten wie ShinePhone App).
Dieser Provider ist NICHT mit echten Geräten getestet (getestet=False).
"""

import hashlib
import logging
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

API_BASE = "https://openapi.growatt.com"


def _md5_password(password: str) -> str:
    """Growatt-spezifisches Passwort-Hashing (MD5, dann Byte-Manipulation)."""
    # Growatt verwendet ein spezielles MD5-Hash-Verfahren
    md5 = hashlib.md5(password.encode("utf-8")).hexdigest()
    # Growatt mischt die Bytes: Tausche Paare von Hex-Zeichen
    result = ""
    for i in range(0, len(md5), 2):
        if i < len(md5) - 1:
            result += md5[i + 1] + md5[i]
        else:
            result += md5[i]
    return result


@register_provider
class GrowattProvider(CloudImportProvider):
    """Cloud-Import-Provider für Growatt Wechselrichter."""

    def info(self) -> CloudProviderInfo:
        return CloudProviderInfo(
            id="growatt",
            name="Growatt",
            hersteller="Growatt",
            beschreibung=(
                "Importiert historische Energiedaten (PV-Erzeugung, Eigenverbrauch, "
                "Einspeisung, Netzbezug, Batterie) über die Growatt Server API. "
                "Gleiche Zugangsdaten wie die ShinePhone App."
            ),
            anleitung=(
                "1. ShinePhone App oder server.growatt.com Account anlegen\n"
                "2. Benutzername und Passwort bereithalten\n"
                "3. Plant-ID aus der Growatt Web-Oberfläche ablesen "
                "(URL-Parameter plantId)"
            ),
            credential_fields=[
                CredentialField(
                    id="username",
                    label="Benutzername",
                    type="text",
                    placeholder="Ihr Growatt/ShinePhone Benutzername",
                    required=True,
                ),
                CredentialField(
                    id="password",
                    label="Passwort",
                    type="password",
                    placeholder="Ihr Growatt Passwort",
                    required=True,
                ),
                CredentialField(
                    id="plant_id",
                    label="Plant ID",
                    type="text",
                    placeholder="z.B. 1234567",
                    required=True,
                ),
            ],
            getestet=False,
        )

    async def test_connection(self, credentials: dict) -> CloudConnectionTestResult:
        """Testet die Verbindung zur Growatt API."""
        username = credentials.get("username", "")
        password = credentials.get("password", "")
        plant_id = credentials.get("plant_id", "")

        if not username or not password or not plant_id:
            return CloudConnectionTestResult(
                erfolg=False,
                fehler="Benutzername, Passwort und Plant ID sind erforderlich.",
            )

        try:
            async with httpx.AsyncClient(
                timeout=15,
                base_url=API_BASE,
                follow_redirects=True,
            ) as client:
                # Login
                cookies = await self._login(client, username, password)
                if not cookies:
                    return CloudConnectionTestResult(
                        erfolg=False,
                        fehler="Login fehlgeschlagen. Benutzername/Passwort prüfen.",
                    )

                # Plant-Info abrufen
                resp = await client.get(
                    "/panel/getPlantData",
                    params={"plantId": plant_id},
                    cookies=cookies,
                )

                if resp.status_code != 200:
                    return CloudConnectionTestResult(
                        erfolg=False,
                        fehler=f"API-Fehler: HTTP {resp.status_code}",
                    )

                data = resp.json()
                obj = data.get("obj", data)

                plant_name = obj.get("plantName", "Growatt Anlage")
                nominal_power = obj.get("nominalPower") or obj.get("peakPower")

                verfuegbar = f"Anlage: {plant_name}"
                if nominal_power:
                    verfuegbar += f", {nominal_power}"

                return CloudConnectionTestResult(
                    erfolg=True,
                    geraet_name=plant_name,
                    geraet_typ="Growatt Wechselrichter",
                    seriennummer=plant_id,
                    verfuegbare_daten=verfuegbar,
                )

        except httpx.TimeoutException:
            return CloudConnectionTestResult(
                erfolg=False,
                fehler="Zeitüberschreitung bei der Verbindung zur Growatt API.",
            )
        except Exception as e:
            logger.exception("Growatt API Verbindungstest fehlgeschlagen")
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
        """Holt historische Monatsdaten von Growatt.

        Nutzt PlantDetailAPI.do mit type=2 (Monatsansicht pro Jahr).
        Gibt für jedes Jahr die monatlichen Energiewerte zurück.
        """
        username = credentials.get("username", "")
        password = credentials.get("password", "")
        plant_id = credentials.get("plant_id", "")

        results: list[ParsedMonthData] = []

        async with httpx.AsyncClient(
            timeout=30,
            base_url=API_BASE,
            follow_redirects=True,
        ) as client:
            cookies = await self._login(client, username, password)
            if not cookies:
                raise Exception("Growatt Login fehlgeschlagen")

            for year in range(start_year, end_year + 1):
                try:
                    year_data = await self._fetch_year_data(
                        client, cookies, plant_id, year,
                    )

                    for month_data in year_data:
                        if (month_data.jahr, month_data.monat) < (start_year, start_month):
                            continue
                        if (month_data.jahr, month_data.monat) > (end_year, end_month):
                            continue
                        if month_data.has_data():
                            results.append(month_data)

                except Exception as e:
                    logger.warning(f"Growatt Jahresdaten {year} fehlgeschlagen: {type(e).__name__}: {e}")

        return results

    async def _login(
        self,
        client: httpx.AsyncClient,
        username: str,
        password: str,
    ) -> Optional[dict]:
        """Login bei Growatt und Session-Cookies erhalten."""
        try:
            hashed_pw = _md5_password(password)

            resp = await client.post(
                "/newTwoLoginAPI.do",
                data={
                    "userName": username,
                    "password": "",
                    "passwordCrc": hashed_pw,
                    "validateCode": "",
                    "isReadPact": "0",
                },
            )

            if resp.status_code != 200:
                return None

            data = resp.json()
            result = data.get("result", data.get("back", {}))

            if isinstance(result, dict) and result.get("success", False):
                return dict(resp.cookies)
            # Einige API-Versionen geben result=1 für Erfolg
            if result == 1 or data.get("back", {}).get("success"):
                return dict(resp.cookies)

            return None

        except Exception as e:
            logger.warning(f"Growatt Login fehlgeschlagen: {type(e).__name__}: {e}")
            return None

    async def _fetch_year_data(
        self,
        client: httpx.AsyncClient,
        cookies: dict,
        plant_id: str,
        year: int,
    ) -> list[ParsedMonthData]:
        """Holt Monatsdaten für ein ganzes Jahr über PlantDetailAPI."""

        # type=2 = Jahresansicht mit Monatswerten
        resp = await client.get(
            "/PlantDetailAPI.do",
            params={
                "plantId": plant_id,
                "type": "2",
                "date": str(year),
            },
            cookies=cookies,
        )

        if resp.status_code != 200:
            raise Exception(f"HTTP {resp.status_code}")

        data = resp.json()
        obj = data.get("obj", data)

        results: list[ParsedMonthData] = []

        # Energiedaten aus verschiedenen möglichen Response-Strukturen extrahieren
        # Variante 1: charts mit monatlichen Arrays
        charts = obj.get("charts", obj.get("chartData", {}))
        if isinstance(charts, dict):
            # Array-basierte Charts: Index 0-11 = Jan-Dez
            pv_array = charts.get("ppv", charts.get("photovoltaic", []))
            grid_export = charts.get("pacToGrid", charts.get("toGrid", []))
            grid_import = charts.get("pacToUser", charts.get("toUser", []))
            self_use = charts.get("pself", charts.get("selfUse", []))
            charge = charts.get("pcharge", charts.get("charge", []))
            discharge = charts.get("pdischarge", charts.get("discharge", []))
            load = charts.get("elocalLoad", charts.get("localLoad", []))

            for month_idx in range(12):
                month = month_idx + 1
                month_data = ParsedMonthData(
                    jahr=year,
                    monat=month,
                    pv_erzeugung_kwh=_safe_float(pv_array, month_idx),
                    einspeisung_kwh=_safe_float(grid_export, month_idx),
                    netzbezug_kwh=_safe_float(grid_import, month_idx),
                    eigenverbrauch_kwh=(
                        _safe_float(self_use, month_idx)
                        or _safe_float(load, month_idx)
                    ),
                    batterie_ladung_kwh=_safe_float(charge, month_idx),
                    batterie_entladung_kwh=_safe_float(discharge, month_idx),
                )
                if month_data.has_data():
                    results.append(month_data)

        # Variante 2: energyMonth dict mit Monats-Keys
        if not results:
            energy_data = obj.get("energyMonth", obj.get("plantMonthEnergy", {}))
            if isinstance(energy_data, dict):
                for month_key, value in energy_data.items():
                    try:
                        month = int(month_key)
                        if 1 <= month <= 12 and value:
                            results.append(ParsedMonthData(
                                jahr=year,
                                monat=month,
                                pv_erzeugung_kwh=round(float(value), 2),
                            ))
                    except (ValueError, TypeError):
                        continue

        return results


def _safe_float(
    array: list, index: int,
) -> Optional[float]:
    """Sicherer Zugriff auf Array-Wert, konvertiert zu float oder None."""
    if not array or index >= len(array):
        return None
    val = array[index]
    if val is None:
        return None
    try:
        f = float(val)
        return round(f, 2) if f > 0 else None
    except (ValueError, TypeError):
        return None
