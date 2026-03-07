"""
Huawei FusionSolar Cloud-Import-Provider.

Nutzt die FusionSolar Northbound API um historische Energiedaten abzurufen.

Auth: Login mit userName + systemCode → XSRF-TOKEN Cookie/Header.
Base URL: https://eu5.fusionsolar.huawei.com/thirdData (EU) oder
          https://intl.fusionsolar.huawei.com/thirdData (International)

Endpoints:
  - POST /login                  → Authentifizierung
  - POST /getStationList         → Anlagen auflisten
  - POST /getKpiStationMonth     → Monatliche KPI-Daten

HINWEIS: Northbound-API-Account muss separat in FusionSolar angelegt werden
(System → Northbound Management). Token ist 30 Minuten gültig.
Dieser Provider ist NICHT mit echten Geräten getestet (getestet=False).
"""

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

# Regionale API-Hosts
API_HOSTS = {
    "eu": "https://eu5.fusionsolar.huawei.com/thirdData",
    "intl": "https://intl.fusionsolar.huawei.com/thirdData",
    "cn": "https://cn5.fusionsolar.huawei.com/thirdData",
}

# Mapping: dataItemMap Felder → ParsedMonthData
# Basierend auf offizieller Huawei Northbound API Dokumentation
KPI_MAPPING = {
    # PV-Erzeugung (Wechselrichter-Leistung gesamt)
    "inverter_power": "pv_erzeugung_kwh",
    "inverterPower": "pv_erzeugung_kwh",
    # Einspeisung (ins Netz)
    "ongrid_power": "einspeisung_kwh",
    "ongridPower": "einspeisung_kwh",
    "power_profit": "einspeisung_kwh",
    # Netzbezug (aus dem Netz)
    "buy_power": "netzbezug_kwh",
    "buyPower": "netzbezug_kwh",
    # Eigenverbrauch
    "self_use_power": "eigenverbrauch_kwh",
    "selfUsePower": "eigenverbrauch_kwh",
    "selfProvide": "eigenverbrauch_kwh",
    # Gesamtverbrauch
    "use_power": "eigenverbrauch_kwh",
    "usePower": "eigenverbrauch_kwh",
    # Batterie-Ladung
    "charge_cap": "batterie_ladung_kwh",
    "chargeCap": "batterie_ladung_kwh",
    # Batterie-Entladung
    "discharge_cap": "batterie_entladung_kwh",
    "dischargeCap": "batterie_entladung_kwh",
}


@register_provider
class HuaweiFusionSolarProvider(CloudImportProvider):
    """Cloud-Import-Provider für Huawei FusionSolar."""

    def info(self) -> CloudProviderInfo:
        return CloudProviderInfo(
            id="huawei_fusionsolar",
            name="Huawei FusionSolar",
            hersteller="Huawei",
            beschreibung=(
                "Importiert historische Energiedaten (PV-Erzeugung, Eigenverbrauch, "
                "Einspeisung, Netzbezug, Batterie) über die Huawei FusionSolar "
                "Northbound API."
            ),
            anleitung=(
                "1. FusionSolar Portal: System → Unternehmensverwaltung → "
                "Northbound Management\n"
                "2. Northbound-API-Benutzer anlegen (separater Username + Passwort)\n"
                "3. Username und System-Code (Passwort) notieren\n"
                "4. Station-Code aus der FusionSolar URL ablesen\n"
                "5. Region wählen (EU für europäische Accounts)"
            ),
            credential_fields=[
                CredentialField(
                    id="username",
                    label="Northbound API Username",
                    type="text",
                    placeholder="Ihr API-Benutzername",
                    required=True,
                ),
                CredentialField(
                    id="system_code",
                    label="System-Code (Passwort)",
                    type="password",
                    placeholder="Ihr API-Passwort",
                    required=True,
                ),
                CredentialField(
                    id="station_code",
                    label="Station-Code",
                    type="text",
                    placeholder="z.B. NE=12345678",
                    required=True,
                ),
                CredentialField(
                    id="region",
                    label="Region",
                    type="select",
                    required=True,
                    options=[
                        {"value": "eu", "label": "Europa (EU)"},
                        {"value": "intl", "label": "International"},
                        {"value": "cn", "label": "China"},
                    ],
                ),
            ],
            getestet=False,
        )

    async def test_connection(self, credentials: dict) -> CloudConnectionTestResult:
        """Testet die Verbindung zur FusionSolar API."""
        username = credentials.get("username", "")
        system_code = credentials.get("system_code", "")
        station_code = credentials.get("station_code", "")
        region = credentials.get("region", "eu")

        if not username or not system_code or not station_code:
            return CloudConnectionTestResult(
                erfolg=False,
                fehler="Username, System-Code und Station-Code sind erforderlich.",
            )

        base_url = API_HOSTS.get(region, API_HOSTS["eu"])

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                # Login
                token = await self._login(client, base_url, username, system_code)
                if not token:
                    return CloudConnectionTestResult(
                        erfolg=False,
                        fehler="Login fehlgeschlagen. Username/System-Code prüfen.",
                    )

                # Station-Liste abrufen
                resp = await client.post(
                    f"{base_url}/getStationList",
                    json={"pageNo": 1, "pageSize": 100},
                    headers={"XSRF-TOKEN": token},
                    cookies={"XSRF-TOKEN": token},
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
                        fehler=f"API-Fehler: {data.get('failCode', 'Unbekannt')}",
                    )

                # Station finden
                stations = data.get("data", {}).get("list", [])
                station = None
                for s in stations:
                    if s.get("stationCode") == station_code:
                        station = s
                        break

                if not station:
                    station_codes = [s.get("stationCode", "?") for s in stations[:5]]
                    return CloudConnectionTestResult(
                        erfolg=False,
                        fehler=(
                            f"Station '{station_code}' nicht gefunden. "
                            f"Verfügbare Stationen: {', '.join(station_codes)}"
                        ),
                    )

                name = station.get("stationName", "Unbekannt")
                capacity = station.get("capacity")

                verfuegbar = f"Anlage: {name}"
                if capacity is not None:
                    verfuegbar += f", {capacity} kWp"

                return CloudConnectionTestResult(
                    erfolg=True,
                    geraet_name=name,
                    geraet_typ="Huawei FusionSolar",
                    seriennummer=station_code,
                    verfuegbare_daten=verfuegbar,
                )

        except httpx.TimeoutException:
            return CloudConnectionTestResult(
                erfolg=False,
                fehler="Zeitüberschreitung bei der Verbindung zur FusionSolar API.",
            )
        except Exception as e:
            logger.exception("FusionSolar API Verbindungstest fehlgeschlagen")
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
        """Holt historische Monatsdaten von FusionSolar.

        Nutzt getKpiStationMonth – erwartet collectTime als Monats-Timestamp (ms).
        Pro Request wird ein collectTime übergeben, die API liefert Daten für diesen Monat.
        """
        username = credentials.get("username", "")
        system_code = credentials.get("system_code", "")
        station_code = credentials.get("station_code", "")
        region = credentials.get("region", "eu")

        base_url = API_HOSTS.get(region, API_HOSTS["eu"])
        results: list[ParsedMonthData] = []

        async with httpx.AsyncClient(timeout=30) as client:
            token = await self._login(client, base_url, username, system_code)
            if not token:
                raise Exception("FusionSolar Login fehlgeschlagen")

            current_year = start_year
            current_month = start_month

            while (current_year, current_month) <= (end_year, end_month):
                try:
                    month_data = await self._fetch_single_month(
                        client, base_url, token, station_code,
                        current_year, current_month,
                    )
                    if month_data and month_data.has_data():
                        results.append(month_data)
                except Exception as e:
                    # Token abgelaufen? Neu einloggen
                    if "305" in str(e):
                        token = await self._login(
                            client, base_url, username, system_code,
                        )
                        if token:
                            try:
                                month_data = await self._fetch_single_month(
                                    client, base_url, token, station_code,
                                    current_year, current_month,
                                )
                                if month_data and month_data.has_data():
                                    results.append(month_data)
                            except Exception as retry_e:
                                logger.warning(
                                    f"FusionSolar {current_year}-{current_month:02d} "
                                    f"Retry fehlgeschlagen: {retry_e}"
                                )
                    else:
                        logger.warning(
                            f"FusionSolar {current_year}-{current_month:02d} "
                            f"fehlgeschlagen: {e}"
                        )

                # Nächster Monat
                if current_month == 12:
                    current_year += 1
                    current_month = 1
                else:
                    current_month += 1

        return results

    async def _login(
        self,
        client: httpx.AsyncClient,
        base_url: str,
        username: str,
        system_code: str,
    ) -> Optional[str]:
        """Login und XSRF-TOKEN erhalten."""
        try:
            resp = await client.post(
                f"{base_url}/login",
                json={"userName": username, "systemCode": system_code},
            )

            if resp.status_code != 200:
                return None

            # Token aus Cookie oder Header extrahieren
            token = resp.cookies.get("XSRF-TOKEN")
            if not token:
                token = resp.headers.get("xsrf-token")
            return token

        except Exception as e:
            logger.warning(f"FusionSolar Login fehlgeschlagen: {e}")
            return None

    async def _fetch_single_month(
        self,
        client: httpx.AsyncClient,
        base_url: str,
        token: str,
        station_code: str,
        year: int,
        month: int,
    ) -> Optional[ParsedMonthData]:
        """Holt KPI-Daten für einen einzelnen Monat."""

        # collectTime: Timestamp des 1. des Monats in Millisekunden
        collect_time = int(
            datetime(year, month, 1).timestamp() * 1000
        )

        resp = await client.post(
            f"{base_url}/getKpiStationMonth",
            json={
                "stationCodes": station_code,
                "collectTime": collect_time,
            },
            headers={"XSRF-TOKEN": token},
            cookies={"XSRF-TOKEN": token},
        )

        if resp.status_code != 200:
            raise Exception(f"HTTP {resp.status_code}")

        data = resp.json()

        if not data.get("success", False):
            fail_code = str(data.get("failCode", ""))
            raise Exception(f"API-Fehler: {fail_code}")

        # Response: { data: [ { stationCode, dataItemMap: { ... }, collectTime } ] }
        entries = data.get("data", [])
        if not entries:
            return None

        # Erste Station mit passendem Code
        entry = entries[0]
        item_map = entry.get("dataItemMap", {})
        if not item_map:
            return None

        aggregated: dict[str, float] = {}
        for api_key, value in item_map.items():
            field_name = KPI_MAPPING.get(api_key)
            if field_name and value is not None:
                try:
                    float_val = float(value)
                    # Nur den ersten Match pro Feld verwenden (Priorität durch Mapping-Reihenfolge)
                    if field_name not in aggregated:
                        aggregated[field_name] = float_val
                except (ValueError, TypeError):
                    continue

        if not aggregated:
            return None

        return ParsedMonthData(
            jahr=year,
            monat=month,
            pv_erzeugung_kwh=_round(aggregated.get("pv_erzeugung_kwh")),
            einspeisung_kwh=_round(aggregated.get("einspeisung_kwh")),
            netzbezug_kwh=_round(aggregated.get("netzbezug_kwh")),
            eigenverbrauch_kwh=_round(aggregated.get("eigenverbrauch_kwh")),
            batterie_ladung_kwh=_round(aggregated.get("batterie_ladung_kwh")),
            batterie_entladung_kwh=_round(aggregated.get("batterie_entladung_kwh")),
        )


def _round(value: Optional[float]) -> Optional[float]:
    """Rundet auf 2 Dezimalstellen, None bleibt None."""
    if value is None:
        return None
    return round(value, 2)
