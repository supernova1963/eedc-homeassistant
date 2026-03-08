"""
EcoFlow PowerStream Cloud-Import-Provider.

Nutzt die EcoFlow Developer API (IoT Open Platform) um historische
Energiedaten vom PowerStream Mikrowechselrichter (Balkonkraftwerk) abzurufen.

Auth: HMAC-SHA256 Signierung mit AccessKey + SecretKey (identisch zu PowerOcean).
Der PowerStream liefert PV-Erzeugung, Einspeisung und ggf. Batterie-Daten
(wenn ein Delta-Speicher angeschlossen ist).

HINWEIS: Dieser Provider ist NICHT mit echten Geräten getestet (getestet=False).
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

import httpx

from backend.services.import_parsers.base import ParsedMonthData

from .base import (
    CloudImportProvider,
    CloudProviderInfo,
    CloudConnectionTestResult,
    CredentialField,
)
from .ecoflow_powerocean import (
    API_HOSTS,
    _build_sign_headers,
    _get_api_host,
)
from .registry import register_provider

logger = logging.getLogger(__name__)

# PowerStream History-Code (Wochen-Übersicht)
HISTORY_CODE = "JT303_Dashboard_Overview_Summary_Week"

# Mapping: indexName aus EcoFlow API -> ParsedMonthData Felder
# PowerStream liefert andere Feldnamen als PowerOcean
INDEX_NAME_MAPPING = {
    # PV-Erzeugung (Solar-Input am Mikrowechselrichter)
    "Solar Generation": "pv_erzeugung_kwh",
    "solarGeneration": "pv_erzeugung_kwh",
    "Solar generation": "pv_erzeugung_kwh",
    "PV Generation": "pv_erzeugung_kwh",
    "pvGeneration": "pv_erzeugung_kwh",
    "Solar Input": "pv_erzeugung_kwh",
    "solarInput": "pv_erzeugung_kwh",
    # Einspeisung (ins Hausnetz / Stromnetz)
    "Grid Feed-in": "einspeisung_kwh",
    "gridFeedIn": "einspeisung_kwh",
    "Feed-in to grid": "einspeisung_kwh",
    "Output to Grid": "einspeisung_kwh",
    "outputToGrid": "einspeisung_kwh",
    "Grid Output": "einspeisung_kwh",
    # Netzbezug (bei PowerStream eher selten direkt gemessen)
    "Grid Consumption": "netzbezug_kwh",
    "gridConsumption": "netzbezug_kwh",
    # Batterie-Ladung (Delta-Speicher, falls angeschlossen)
    "Battery Charge": "batterie_ladung_kwh",
    "batteryCharge": "batterie_ladung_kwh",
    "Battery charge": "batterie_ladung_kwh",
    "Charge to Battery": "batterie_ladung_kwh",
    # Batterie-Entladung
    "Battery Discharge": "batterie_entladung_kwh",
    "batteryDischarge": "batterie_entladung_kwh",
    "Battery discharge": "batterie_entladung_kwh",
    "Discharge from Battery": "batterie_entladung_kwh",
    # Eigenverbrauch / Hausverbrauch
    "Home Consumption": "eigenverbrauch_kwh",
    "homeConsumption": "eigenverbrauch_kwh",
    "Home consumption": "eigenverbrauch_kwh",
    "Output to Home": "eigenverbrauch_kwh",
    "outputToHome": "eigenverbrauch_kwh",
}


@register_provider
class EcoFlowPowerStreamProvider(CloudImportProvider):
    """Cloud-Import-Provider für EcoFlow PowerStream (Balkonkraftwerk)."""

    def info(self) -> CloudProviderInfo:
        return CloudProviderInfo(
            id="ecoflow_powerstream",
            name="EcoFlow PowerStream",
            hersteller="EcoFlow",
            beschreibung=(
                "Importiert historische Energiedaten (PV-Erzeugung, Einspeisung, "
                "ggf. Batterie) vom EcoFlow PowerStream Mikrowechselrichter "
                "(Balkonkraftwerk) über die EcoFlow Developer API."
            ),
            anleitung=(
                "1. EcoFlow Developer Account anlegen unter developer-eu.ecoflow.com\n"
                "2. AccessKey und SecretKey generieren (Bereich 'Sicherheit')\n"
                "3. Seriennummer vom PowerStream bereithalten "
                "(steht auf dem Gerät oder in der EcoFlow App)\n"
                "4. Region wählen (EU für europäische Accounts)\n\n"
                "Hinweis: Der Developer-Zugang muss erst von EcoFlow freigeschaltet "
                "werden (kann bis zu 1 Woche dauern)."
            ),
            credential_fields=[
                CredentialField(
                    id="access_key",
                    label="Access Key",
                    type="text",
                    placeholder="z.B. AbCdEfGh...",
                    required=True,
                ),
                CredentialField(
                    id="secret_key",
                    label="Secret Key",
                    type="password",
                    placeholder="Ihr EcoFlow Secret Key",
                    required=True,
                ),
                CredentialField(
                    id="serial_number",
                    label="Seriennummer",
                    type="text",
                    placeholder="z.B. HW51Zxxxxxxxxxx",
                    required=True,
                ),
                CredentialField(
                    id="region",
                    label="Region",
                    type="select",
                    required=True,
                    options=[
                        {"value": "eu", "label": "Europa (EU)"},
                        {"value": "us", "label": "Amerika (US)"},
                    ],
                ),
            ],
            getestet=False,
        )

    async def test_connection(self, credentials: dict) -> CloudConnectionTestResult:
        """Testet die Verbindung zur EcoFlow API mit PowerStream SN."""
        access_key = credentials.get("access_key", "")
        secret_key = credentials.get("secret_key", "")
        serial_number = credentials.get("serial_number", "")
        region = credentials.get("region", "eu")

        if not access_key or not secret_key or not serial_number:
            return CloudConnectionTestResult(
                erfolg=False,
                fehler="AccessKey, SecretKey und Seriennummer sind erforderlich.",
            )

        host = _get_api_host(region)

        try:
            query_params = {"sn": serial_number}
            headers = _build_sign_headers(access_key, secret_key, query_params)

            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    f"{host}/iot-open/sign/device/quota/all",
                    params=query_params,
                    headers=headers,
                )

            if resp.status_code != 200:
                return CloudConnectionTestResult(
                    erfolg=False,
                    fehler=f"API-Fehler: HTTP {resp.status_code}",
                )

            data = resp.json()
            if str(data.get("code")) != "0":
                return CloudConnectionTestResult(
                    erfolg=False,
                    fehler=f"API-Fehler: {data.get('message', 'Unbekannter Fehler')}",
                )

            return CloudConnectionTestResult(
                erfolg=True,
                geraet_name="EcoFlow PowerStream",
                geraet_typ="Mikrowechselrichter (Balkonkraftwerk)",
                seriennummer=serial_number,
                verfuegbare_daten=f"Gerät erreichbar, SN: {serial_number}",
            )

        except httpx.TimeoutException:
            return CloudConnectionTestResult(
                erfolg=False,
                fehler="Zeitüberschreitung bei der Verbindung zur EcoFlow API.",
            )
        except Exception as e:
            logger.exception("EcoFlow PowerStream Verbindungstest fehlgeschlagen")
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
        """Holt historische Monatsdaten vom EcoFlow PowerStream.

        Die History-API erlaubt max. 7 Tage pro Request.
        Für jeden Monat werden daher ~5 Requests gemacht und die Werte summiert.
        """
        access_key = credentials.get("access_key", "")
        secret_key = credentials.get("secret_key", "")
        serial_number = credentials.get("serial_number", "")
        region = credentials.get("region", "eu")

        host = _get_api_host(region)
        results: list[ParsedMonthData] = []

        current_year = start_year
        current_month = start_month

        while (current_year, current_month) <= (end_year, end_month):
            month_data = await self._fetch_single_month(
                host, access_key, secret_key, serial_number,
                current_year, current_month,
            )
            if month_data and month_data.has_data():
                results.append(month_data)

            if current_month == 12:
                current_year += 1
                current_month = 1
            else:
                current_month += 1

        return results

    async def _fetch_single_month(
        self,
        host: str,
        access_key: str,
        secret_key: str,
        serial_number: str,
        year: int,
        month: int,
    ) -> Optional[ParsedMonthData]:
        """Holt Daten für einen einzelnen Monat (in 7-Tage-Blöcken)."""
        month_start = datetime(year, month, 1)
        if month == 12:
            month_end = datetime(year + 1, 1, 1)
        else:
            month_end = datetime(year, month + 1, 1)

        now = datetime.now()
        if month_start > now:
            return None
        if month_end > now:
            month_end = now

        aggregated: dict[str, float] = {}

        block_start = month_start
        while block_start < month_end:
            block_end = min(block_start + timedelta(days=7), month_end)

            try:
                block_data = await self._fetch_history_block(
                    host, access_key, secret_key, serial_number,
                    block_start, block_end,
                )

                for index_name, index_value in block_data:
                    field_name = INDEX_NAME_MAPPING.get(index_name)
                    if field_name and index_value is not None:
                        aggregated[field_name] = aggregated.get(field_name, 0) + index_value

            except Exception as e:
                logger.warning(
                    f"EcoFlow PowerStream History-Block "
                    f"{block_start.date()} - {block_end.date()} fehlgeschlagen: {e}"
                )

            block_start = block_end

        if not aggregated:
            return None

        return ParsedMonthData(
            jahr=year,
            monat=month,
            pv_erzeugung_kwh=round(aggregated.get("pv_erzeugung_kwh", 0), 2) or None,
            einspeisung_kwh=round(aggregated.get("einspeisung_kwh", 0), 2) or None,
            netzbezug_kwh=round(aggregated.get("netzbezug_kwh", 0), 2) or None,
            batterie_ladung_kwh=round(aggregated.get("batterie_ladung_kwh", 0), 2) or None,
            batterie_entladung_kwh=round(aggregated.get("batterie_entladung_kwh", 0), 2) or None,
            eigenverbrauch_kwh=round(aggregated.get("eigenverbrauch_kwh", 0), 2) or None,
        )

    async def _fetch_history_block(
        self,
        host: str,
        access_key: str,
        secret_key: str,
        serial_number: str,
        begin: datetime,
        end: datetime,
    ) -> list[tuple[str, Optional[float]]]:
        """Einzelnen 7-Tage-Block von der History-API abrufen."""
        body = {
            "sn": serial_number,
            "params": {
                "code": HISTORY_CODE,
                "beginTime": begin.strftime("%Y-%m-%d %H:%M:%S"),
                "endTime": end.strftime("%Y-%m-%d %H:%M:%S"),
            },
        }

        headers = _build_sign_headers(access_key, secret_key, body)

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{host}/iot-open/sign/device/quota/data",
                json=body,
                headers=headers,
            )

        if resp.status_code != 200:
            raise Exception(f"HTTP {resp.status_code}: {resp.text[:200]}")

        data = resp.json()
        if str(data.get("code")) != "0":
            raise Exception(f"API-Fehler: {data.get('message', 'Unbekannt')}")

        inner = data.get("data", {})
        if isinstance(inner, dict):
            items = inner.get("data", [])
        else:
            items = []

        result: list[tuple[str, Optional[float]]] = []
        for item in items:
            name = item.get("indexName", "")
            value = item.get("indexValue")
            if name:
                result.append((name, value))

        return result
