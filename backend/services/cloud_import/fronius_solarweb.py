"""
Fronius Solar.web Cloud-Import-Provider.

Nutzt die Fronius Solar.web Query API (SWQAPI) um historische
Energiedaten von Fronius Wechselrichtern abzurufen.

Auth: AccessKeyId + AccessKeyValue als HTTP-Header.
Base URL: https://api.solarweb.com/swqapi
Endpoint: GET /pvsystems/{pvSystemId}/aggdata/years/{year}/months

HINWEIS: Die Solar.web Query API ist primär für Business-Partner gedacht.
Privatkunden müssen API-Zugang bei Fronius beantragen.
Dieser Provider ist NICHT mit echten Geräten getestet (getestet=False).
"""

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

API_BASE = "https://api.solarweb.com/swqapi"

# Mapping: Fronius channelName → ParsedMonthData Felder
# Die exakten Channel-Namen müssen ggf. mit echten API-Daten verifiziert werden.
CHANNEL_MAPPING = {
    # PV-Erzeugung
    "EnergyProductionTotal": "pv_erzeugung_kwh",
    "EnergyProduction": "pv_erzeugung_kwh",
    "energyProductionTotal": "pv_erzeugung_kwh",
    # Einspeisung (Grid Feed-In / Export)
    "GridExportTotal": "einspeisung_kwh",
    "GridFeedIn": "einspeisung_kwh",
    "gridFeedIn": "einspeisung_kwh",
    "gridfeedin": "einspeisung_kwh",
    # Netzbezug (Grid Import / Purchased)
    "GridImportTotal": "netzbezug_kwh",
    "GridConsumption": "netzbezug_kwh",
    "gridpower": "netzbezug_kwh",
    "gridPower": "netzbezug_kwh",
    # Eigenverbrauch
    "SelfConsumptionTotal": "eigenverbrauch_kwh",
    "SelfConsumption": "eigenverbrauch_kwh",
    "selfconsumption": "eigenverbrauch_kwh",
    "selfConsumption": "eigenverbrauch_kwh",
    # Batterie
    "BatteryChargeTotal": "batterie_ladung_kwh",
    "BatteryCharge": "batterie_ladung_kwh",
    "batteryCharge": "batterie_ladung_kwh",
    "BatteryDischargeTotal": "batterie_entladung_kwh",
    "BatteryDischarge": "batterie_entladung_kwh",
    "batteryDischarge": "batterie_entladung_kwh",
}


def _build_headers(access_key_id: str, access_key_value: str) -> dict:
    """HTTP-Header für die Fronius SWQAPI."""
    return {
        "AccessKeyId": access_key_id,
        "AccessKeyValue": access_key_value,
        "Accept": "application/json",
    }


def _wh_to_kwh(value: Optional[float], unit: str) -> Optional[float]:
    """Konvertiert Wh zu kWh falls nötig."""
    if value is None:
        return None
    if "kWh" in unit:
        return value
    if "Wh" in unit:
        return value / 1000.0
    return value


@register_provider
class FroniusSolarWebProvider(CloudImportProvider):
    """Cloud-Import-Provider für Fronius über Solar.web Query API."""

    def info(self) -> CloudProviderInfo:
        return CloudProviderInfo(
            id="fronius_solarweb",
            name="Fronius Solar.web",
            hersteller="Fronius",
            beschreibung=(
                "Importiert historische Energiedaten (PV-Erzeugung, Eigenverbrauch, "
                "Einspeisung, Netzbezug, Batterie) über die Fronius Solar.web Query API."
            ),
            anleitung=(
                "1. Solar.web Account unter www.solarweb.com\n"
                "2. API-Zugang bei Fronius beantragen (REST API Feature aktivieren)\n"
                "3. Unter Benutzereinstellungen → REST API → API Key erstellen\n"
                "4. AccessKeyId und AccessKeyValue notieren\n"
                "5. PV-System-ID aus der Solar.web URL ablesen"
            ),
            credential_fields=[
                CredentialField(
                    id="access_key_id",
                    label="Access Key ID",
                    type="text",
                    placeholder="Ihr Fronius AccessKeyId",
                    required=True,
                ),
                CredentialField(
                    id="access_key_value",
                    label="Access Key Value",
                    type="password",
                    placeholder="Ihr Fronius AccessKeyValue",
                    required=True,
                ),
                CredentialField(
                    id="pv_system_id",
                    label="PV-System-ID",
                    type="text",
                    placeholder="z.B. xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
                    required=True,
                ),
            ],
            getestet=False,
        )

    async def test_connection(self, credentials: dict) -> CloudConnectionTestResult:
        """Testet die Verbindung zur Fronius Solar.web API."""
        access_key_id = credentials.get("access_key_id", "")
        access_key_value = credentials.get("access_key_value", "")
        pv_system_id = credentials.get("pv_system_id", "")

        if not access_key_id or not access_key_value or not pv_system_id:
            return CloudConnectionTestResult(
                erfolg=False,
                fehler="AccessKeyId, AccessKeyValue und PV-System-ID sind erforderlich.",
            )

        headers = _build_headers(access_key_id, access_key_value)

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    f"{API_BASE}/pvsystems/{pv_system_id}",
                    headers=headers,
                )

            if resp.status_code == 401:
                return CloudConnectionTestResult(
                    erfolg=False,
                    fehler="Authentifizierung fehlgeschlagen. AccessKeyId/Value prüfen.",
                )
            if resp.status_code == 403:
                return CloudConnectionTestResult(
                    erfolg=False,
                    fehler="Kein Zugriff auf dieses PV-System.",
                )
            if resp.status_code == 404:
                return CloudConnectionTestResult(
                    erfolg=False,
                    fehler=f"PV-System {pv_system_id} nicht gefunden.",
                )
            if resp.status_code != 200:
                return CloudConnectionTestResult(
                    erfolg=False,
                    fehler=f"API-Fehler: HTTP {resp.status_code}",
                )

            data = resp.json()
            name = data.get("name", "Fronius PV-System")
            peak_power = data.get("peakPower")
            address = data.get("address", {})
            city = address.get("city", "")

            verfuegbar = f"Anlage: {name}"
            if peak_power is not None:
                verfuegbar += f", {peak_power} kWp"
            if city:
                verfuegbar += f", {city}"

            return CloudConnectionTestResult(
                erfolg=True,
                geraet_name=name,
                geraet_typ="Fronius Wechselrichter",
                seriennummer=pv_system_id,
                verfuegbare_daten=verfuegbar,
            )

        except httpx.TimeoutException:
            return CloudConnectionTestResult(
                erfolg=False,
                fehler="Zeitüberschreitung bei der Verbindung zur Fronius API.",
            )
        except Exception as e:
            logger.exception("Fronius API Verbindungstest fehlgeschlagen")
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
        """Holt historische Monatsdaten von Fronius Solar.web.

        Nutzt den aggdata-Endpoint pro Jahr: /pvsystems/{id}/aggdata/years/{year}/months
        """
        access_key_id = credentials.get("access_key_id", "")
        access_key_value = credentials.get("access_key_value", "")
        pv_system_id = credentials.get("pv_system_id", "")

        headers = _build_headers(access_key_id, access_key_value)
        results: list[ParsedMonthData] = []

        for year in range(start_year, end_year + 1):
            try:
                year_data = await self._fetch_year_months(
                    headers, pv_system_id, year,
                )

                for month_data in year_data:
                    # Nur Monate im gewünschten Bereich
                    if (month_data.jahr, month_data.monat) < (start_year, start_month):
                        continue
                    if (month_data.jahr, month_data.monat) > (end_year, end_month):
                        continue
                    if month_data.has_data():
                        results.append(month_data)

            except Exception as e:
                logger.warning(f"Fronius aggdata Jahr {year} fehlgeschlagen: {e}")

        return results

    async def _fetch_year_months(
        self,
        headers: dict,
        pv_system_id: str,
        year: int,
    ) -> list[ParsedMonthData]:
        """Holt alle Monatsdaten eines Jahres."""

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{API_BASE}/pvsystems/{pv_system_id}/aggdata/years/{year}/months",
                headers=headers,
            )

        if resp.status_code != 200:
            raise Exception(f"HTTP {resp.status_code}: {resp.text[:200]}")

        data = resp.json()

        # Response-Struktur: { data: [ { logPeriod: {year, month}, channels: [...] } ] }
        # oder: { data: { logPeriod: ..., channels: [...] } } für einzelne Monate
        entries = data.get("data", [])
        if isinstance(entries, dict):
            entries = [entries]

        results: list[ParsedMonthData] = []
        for entry in entries:
            log_period = entry.get("logPeriod", {})
            entry_year = log_period.get("year", year)
            entry_month = log_period.get("month")
            if entry_month is None:
                continue

            channels = entry.get("channels", [])
            aggregated: dict[str, float] = {}

            for channel in channels:
                ch_name = channel.get("channelName", "")
                ch_unit = channel.get("unit", "Wh")

                # values kann ein dict mit einem Summen-Key sein oder direkt ein Wert
                values = channel.get("values", {})
                if isinstance(values, dict):
                    # Summe aller Werte im Monat
                    ch_value = sum(
                        v for v in values.values()
                        if isinstance(v, (int, float))
                    )
                elif isinstance(values, (int, float)):
                    ch_value = values
                else:
                    continue

                field_name = CHANNEL_MAPPING.get(ch_name)
                if field_name:
                    kwh = _wh_to_kwh(ch_value, ch_unit)
                    if kwh is not None:
                        aggregated[field_name] = aggregated.get(field_name, 0) + kwh

            if not aggregated:
                continue

            results.append(ParsedMonthData(
                jahr=entry_year,
                monat=entry_month,
                pv_erzeugung_kwh=_round(aggregated.get("pv_erzeugung_kwh")),
                einspeisung_kwh=_round(aggregated.get("einspeisung_kwh")),
                netzbezug_kwh=_round(aggregated.get("netzbezug_kwh")),
                eigenverbrauch_kwh=_round(aggregated.get("eigenverbrauch_kwh")),
                batterie_ladung_kwh=_round(aggregated.get("batterie_ladung_kwh")),
                batterie_entladung_kwh=_round(aggregated.get("batterie_entladung_kwh")),
            ))

        return results


def _round(value: Optional[float]) -> Optional[float]:
    """Rundet auf 2 Dezimalstellen, None bleibt None."""
    if value is None:
        return None
    return round(value, 2)
