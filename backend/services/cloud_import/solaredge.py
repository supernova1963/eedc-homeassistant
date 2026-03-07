"""
SolarEdge Cloud-Import-Provider.

Nutzt die SolarEdge Monitoring API um historische Energiedaten abzurufen.

Auth: API-Key als Query-Parameter.
Endpoints:
  - GET /site/{siteId}/details         → Verbindungstest + Anlagen-Info
  - GET /site/{siteId}/energyDetails   → Monatliche Energiedaten aufgeschlüsselt

API-Dokumentation: https://knowledge-center.solaredge.com/sites/kc/files/se_monitoring_api.pdf
"""

import logging
from datetime import date, timedelta
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

API_BASE = "https://monitoringapi.solaredge.com"


@register_provider
class SolarEdgeProvider(CloudImportProvider):
    """Cloud-Import-Provider für SolarEdge Wechselrichter."""

    def info(self) -> CloudProviderInfo:
        return CloudProviderInfo(
            id="solaredge",
            name="SolarEdge",
            hersteller="SolarEdge",
            beschreibung=(
                "Importiert historische Energiedaten (PV-Erzeugung, Eigenverbrauch, "
                "Einspeisung, Netzbezug) über die SolarEdge Monitoring API."
            ),
            anleitung=(
                "1. Im SolarEdge Monitoring Portal einloggen (monitoring.solaredge.com)\n"
                "2. Admin → Site Access → API Access aktivieren\n"
                "3. API Key kopieren (Site-Level oder Account-Level)\n"
                "4. Site ID aus der URL ablesen (Zahl nach #/site/)"
            ),
            credential_fields=[
                CredentialField(
                    id="api_key",
                    label="API Key",
                    type="password",
                    placeholder="Ihr SolarEdge API Key",
                    required=True,
                ),
                CredentialField(
                    id="site_id",
                    label="Site ID",
                    type="text",
                    placeholder="z.B. 1234567",
                    required=True,
                ),
            ],
            getestet=False,
        )

    async def test_connection(self, credentials: dict) -> CloudConnectionTestResult:
        """Testet die Verbindung zur SolarEdge API über den Site-Details-Endpoint."""
        api_key = credentials.get("api_key", "")
        site_id = credentials.get("site_id", "")

        if not api_key or not site_id:
            return CloudConnectionTestResult(
                erfolg=False,
                fehler="API Key und Site ID sind erforderlich.",
            )

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    f"{API_BASE}/site/{site_id}/details",
                    params={"api_key": api_key},
                )

            if resp.status_code == 403:
                return CloudConnectionTestResult(
                    erfolg=False,
                    fehler="API Key ungültig oder kein Zugriff auf diese Site.",
                )
            if resp.status_code == 404:
                return CloudConnectionTestResult(
                    erfolg=False,
                    fehler=f"Site ID {site_id} nicht gefunden.",
                )
            if resp.status_code != 200:
                return CloudConnectionTestResult(
                    erfolg=False,
                    fehler=f"API-Fehler: HTTP {resp.status_code}",
                )

            data = resp.json()
            details = data.get("details", {})

            name = details.get("name", "Unbekannt")
            peak_power = details.get("peakPower")
            install_date = details.get("installationDate")
            status = details.get("status", "")

            verfuegbar = f"Anlage: {name}"
            if peak_power is not None:
                verfuegbar += f", {peak_power} kWp"
            if install_date:
                verfuegbar += f", installiert: {install_date}"

            return CloudConnectionTestResult(
                erfolg=True,
                geraet_name=name,
                geraet_typ=f"SolarEdge ({status})",
                seriennummer=site_id,
                verfuegbare_daten=verfuegbar,
            )

        except httpx.TimeoutException:
            return CloudConnectionTestResult(
                erfolg=False,
                fehler="Zeitüberschreitung bei der Verbindung zur SolarEdge API.",
            )
        except Exception as e:
            logger.exception("SolarEdge API Verbindungstest fehlgeschlagen")
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
        """Holt historische Monatsdaten von SolarEdge.

        Nutzt den energyDetails-Endpoint mit timeUnit=MONTH.
        API-Limit: max. 1 Jahr pro Request → bei Bedarf aufteilen.
        """
        api_key = credentials.get("api_key", "")
        site_id = credentials.get("site_id", "")

        results: list[ParsedMonthData] = []

        # In Jahresblöcke aufteilen (API-Limit: 1 Jahr)
        current_start = date(start_year, start_month, 1)
        final_end = date(end_year, end_month, 1)

        while current_start <= final_end:
            # Block-Ende: max. 1 Jahr ab Start, aber nicht über final_end
            block_end_year = current_start.year + 1
            block_end_month = current_start.month
            if block_end_month == 1:
                block_end_year -= 1
                block_end_month = 12
            else:
                block_end_month -= 1

            block_end = date(block_end_year, block_end_month, 1)
            if block_end > final_end:
                block_end = final_end

            try:
                block_results = await self._fetch_energy_block(
                    api_key, site_id, current_start, block_end,
                )
                results.extend(block_results)
            except Exception as e:
                logger.warning(
                    f"SolarEdge energyDetails {current_start} - {block_end} "
                    f"fehlgeschlagen: {e}"
                )

            # Nächster Block: Monat nach block_end
            if block_end.month == 12:
                current_start = date(block_end.year + 1, 1, 1)
            else:
                current_start = date(block_end.year, block_end.month + 1, 1)

        return results

    async def _fetch_energy_block(
        self,
        api_key: str,
        site_id: str,
        start: date,
        end: date,
    ) -> list[ParsedMonthData]:
        """Holt einen Block Monatsdaten (max. 1 Jahr) vom energyDetails-Endpoint."""

        # endDate muss der letzte Tag des Monats sein
        if end.month == 12:
            next_month_first = date(end.year + 1, 1, 1)
        else:
            next_month_first = date(end.year, end.month + 1, 1)
        last_day_of_month = next_month_first - timedelta(days=1)
        end_date_str = last_day_of_month.strftime("%Y-%m-%d")

        params = {
            "api_key": api_key,
            "timeUnit": "MONTH",
            "startDate": start.strftime("%Y-%m-%d"),
            "endDate": end_date_str,
            "meters": "Production,Consumption,FeedIn,Purchased",
        }

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{API_BASE}/site/{site_id}/energyDetails",
                params=params,
            )

        if resp.status_code != 200:
            raise Exception(f"HTTP {resp.status_code}: {resp.text[:200]}")

        data = resp.json()
        details = data.get("energyDetails", {})
        meters = details.get("meters", [])

        # Meter-Daten nach Typ aufschlüsseln
        meter_data: dict[str, dict[str, float]] = {}
        for meter in meters:
            meter_type = meter.get("type", "")
            for entry in meter.get("values", []):
                entry_date = entry.get("date", "")
                value = entry.get("value")
                if not entry_date or value is None:
                    continue
                # Datum parsen: "2024-01-01 00:00:00" → "2024-01"
                key = entry_date[:7]
                if key not in meter_data:
                    meter_data[key] = {}
                # Wh → kWh
                meter_data[key][meter_type] = value / 1000.0

        # In ParsedMonthData umwandeln
        results: list[ParsedMonthData] = []
        for date_key in sorted(meter_data.keys()):
            values = meter_data[date_key]
            year = int(date_key[:4])
            month = int(date_key[5:7])

            production = values.get("Production")
            consumption = values.get("Consumption")
            feed_in = values.get("FeedIn")
            purchased = values.get("Purchased")

            # Eigenverbrauch berechnen: Production - FeedIn (wenn beides vorhanden)
            self_consumption = None
            if production is not None and feed_in is not None:
                self_consumption = round(production - feed_in, 2)

            month_data = ParsedMonthData(
                jahr=year,
                monat=month,
                pv_erzeugung_kwh=round(production, 2) if production is not None else None,
                einspeisung_kwh=round(feed_in, 2) if feed_in is not None else None,
                netzbezug_kwh=round(purchased, 2) if purchased is not None else None,
                eigenverbrauch_kwh=(
                    round(self_consumption, 2) if self_consumption is not None
                    else (round(consumption, 2) if consumption is not None else None)
                ),
            )

            if month_data.has_data():
                results.append(month_data)

        return results
