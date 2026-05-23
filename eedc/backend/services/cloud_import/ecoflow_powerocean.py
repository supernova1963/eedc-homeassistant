"""
EcoFlow PowerOcean Cloud-Import-Provider.

Nutzt die EcoFlow Developer API (IoT Open Platform) um historische
Energiedaten vom PowerOcean Wechselrichter/Speicher abzurufen.

Auth: HMAC-SHA256 Signierung mit AccessKey + SecretKey.
Endpoint: POST /iot-open/sign/device/quota/data (Fenster STRIKT < 1 Woche
pro Request — siehe MAX_BLOCK_DAYS).

HINWEIS: Dieser Provider ist NICHT mit echten Geräten getestet (getestet=False).
Die indexName-Werte aus dem History-Endpoint müssen ggf. angepasst werden.
"""

import hashlib
import hmac
import logging
import random
import time
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
from .registry import register_provider

logger = logging.getLogger(__name__)

# API-Regionen
API_HOSTS = {
    "eu": "https://api-e.ecoflow.com",
    "us": "https://api-a.ecoflow.com",
}

HISTORY_CODE = "JT303_Dashboard_Overview_Summary_Week"

# History-Fenstergrenze: die EcoFlow-API verlangt ein Abfragefenster von
# STRIKT weniger als einer Woche. Ein Fenster von exakt 7 Tagen (z. B.
# 2026-02-22 00:00:00 → 2026-03-01 00:00:00 = 168 h) lehnt sie ab mit
# "time must be less than one week" (Dirk-PN 2026-05-22). Daher 6-Tage-Blöcke.
MAX_BLOCK_DAYS = 6

# Mapping: indexName aus EcoFlow API → ParsedMonthData Felder
# WICHTIG: Diese Werte sind geschätzt und müssen mit echten API-Daten verifiziert werden!
INDEX_NAME_MAPPING = {
    # PV-Erzeugung
    "Solar Generation": "pv_erzeugung_kwh",
    "solarGeneration": "pv_erzeugung_kwh",
    "Solar generation": "pv_erzeugung_kwh",
    # Einspeisung
    "Grid Feed-in": "einspeisung_kwh",
    "gridFeedIn": "einspeisung_kwh",
    "Feed-in to grid": "einspeisung_kwh",
    # Netzbezug
    "Grid Consumption": "netzbezug_kwh",
    "gridConsumption": "netzbezug_kwh",
    "Grid consumption": "netzbezug_kwh",
    # Batterie-Ladung
    "Battery Charge": "batterie_ladung_kwh",
    "batteryCharge": "batterie_ladung_kwh",
    "Battery charge": "batterie_ladung_kwh",
    # Batterie-Entladung
    "Battery Discharge": "batterie_entladung_kwh",
    "batteryDischarge": "batterie_entladung_kwh",
    "Battery discharge": "batterie_entladung_kwh",
    # Eigenverbrauch
    "Home Consumption": "eigenverbrauch_kwh",
    "homeConsumption": "eigenverbrauch_kwh",
    "Home consumption": "eigenverbrauch_kwh",
}


def _hmac_sha256(message: str, secret_key: str) -> str:
    """HMAC-SHA256 Signatur berechnen."""
    return hmac.new(
        secret_key.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _flatten_dict(d: dict, prefix: str = "") -> dict:
    """Verschachtelte Dicts flach machen (für Signierung)."""
    items = {}
    for k, v in d.items():
        key = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            items.update(_flatten_dict(v, key))
        else:
            items[key] = v
    return items


def _build_sign_headers(
    access_key: str, secret_key: str, params: Optional[dict] = None
) -> dict:
    """HTTP-Header mit HMAC-SHA256 Signatur erzeugen.

    EcoFlow signiert die Request-Parameter alphabetisch sortiert und hängt
    `accessKey/nonce/timestamp` an: `sn=…&accessKey=…&nonce=…&timestamp=…`.
    Ein parameterloser Aufruf (device/list) ergibt `accessKey=…&nonce=…&
    timestamp=…`. Per Live-Konto bestätigt (Dirk-PN 2026-05-21,
    device/quota/all → code=0).

    KEIN `Content-Type`-Header: Auf dem GET `device/quota/all` lehnt die
    EcoFlow-API die Signatur mit `code 8521 signature is wrong` ab, sobald
    `Content-Type: application/json` gesetzt ist. Für POST `device/quota/data`
    setzt httpx den Header über `json=` selbst korrekt — hier darf er nicht
    fest gesetzt werden.

    HISTORIE: Fix 2da913ce sortierte irrtümlich ALLE Parameter gemeinsam
    (`accessKey=…&nonce=…&sn=…&timestamp=…`); Dirks Live-Test ergab 8521 —
    die Theorie war falsch, die echte Ursache war der Content-Type-Header.
    """
    nonce = str(random.randint(100000, 999999))
    timestamp = str(int(time.time() * 1000))

    # Request-Parameter sortiert als Query-String, dann Auth-Triple anhängen.
    if params:
        flat = _flatten_dict(params)
        sorted_parts = sorted(flat.items(), key=lambda x: x[0])
        param_str = "&".join(f"{k}={v}" for k, v in sorted_parts)
        sign_str = f"{param_str}&accessKey={access_key}&nonce={nonce}&timestamp={timestamp}"
    else:
        sign_str = f"accessKey={access_key}&nonce={nonce}&timestamp={timestamp}"

    sign = _hmac_sha256(sign_str, secret_key)

    return {
        "accessKey": access_key,
        "nonce": nonce,
        "timestamp": timestamp,
        "sign": sign,
    }


def _get_api_host(region: str) -> str:
    """API-Host für Region ermitteln."""
    return API_HOSTS.get(region, API_HOSTS["eu"])


@register_provider
class EcoFlowPowerOceanProvider(CloudImportProvider):
    """Cloud-Import-Provider für EcoFlow PowerOcean."""

    def info(self) -> CloudProviderInfo:
        return CloudProviderInfo(
            id="ecoflow_powerocean",
            name="EcoFlow PowerOcean",
            hersteller="EcoFlow",
            beschreibung=(
                "Importiert historische Energiedaten (PV-Erzeugung, Einspeisung, "
                "Netzbezug, Batterie) vom EcoFlow PowerOcean über die EcoFlow Developer API."
            ),
            anleitung=(
                "1. EcoFlow Developer Account anlegen unter developer-eu.ecoflow.com\n"
                "2. AccessKey und SecretKey generieren (Bereich 'Sicherheit')\n"
                "3. Seriennummer vom PowerOcean bereithalten (steht auf dem Gerät oder in der App)\n"
                "4. Region wählen (EU für europäische Accounts)"
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
        """Testet die Verbindung zur EcoFlow API."""
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
            # GET-Request: SN als Query-Parameter in die Signatur einbeziehen
            query_params = {"sn": serial_number}
            headers = _build_sign_headers(access_key, secret_key, query_params)

            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    f"{host}/iot-open/sign/device/quota/all",
                    params=query_params,
                    headers=headers,
                )

            # Diagnose-Logging: dieser Provider ist mit getestet=False markiert,
            # echte Fehler-Antworten der EcoFlow-API gehören sichtbar in den
            # Backend-Log + in die UI (via fehler-Feld) — sonst muss der Anwender
            # raten oder Logs ziehen.
            logger.info(
                f"EcoFlow Connection-Test: host={host}, sn={serial_number}, "
                f"http_status={resp.status_code}, body={resp.text[:500]}"
            )

            if resp.status_code != 200:
                return CloudConnectionTestResult(
                    erfolg=False,
                    fehler=(
                        f"HTTP {resp.status_code} von {host}. "
                        f"Antwort: {resp.text[:300] or '(leer)'}"
                    ),
                )

            try:
                data = resp.json()
            except Exception as e:
                return CloudConnectionTestResult(
                    erfolg=False,
                    fehler=(
                        f"Antwort der EcoFlow-API ist kein gültiges JSON "
                        f"({type(e).__name__}). Body: {resp.text[:300]}"
                    ),
                )
            if str(data.get("code")) != "0":
                # EcoFlow-Antworten haben typisch: {code, message, data}
                # message ist die Hersteller-Fehler-Erklärung (z.B. "Invalid sign",
                # "Access key not found"). Bei get-Endpoints kommt auch HTTP 200
                # mit code != "0" zurück — das ist die wichtigste Diagnose-Quelle.
                msg = data.get("message", "Unbekannter Fehler")
                code = data.get("code", "?")
                return CloudConnectionTestResult(
                    erfolg=False,
                    fehler=f"EcoFlow-API meldet code={code}: {msg}",
                )

            # Gerätedaten aus der Response extrahieren
            quota_data = data.get("data", {})
            geraet_name = "EcoFlow PowerOcean"
            geraet_typ = "Wechselrichter + Speicher"
            soc = quota_data.get("bpSoc")

            verfuegbar = f"Gerät erreichbar, SN: {serial_number}"
            if soc is not None:
                verfuegbar += f", Akku: {soc}%"

            return CloudConnectionTestResult(
                erfolg=True,
                geraet_name=geraet_name,
                geraet_typ=geraet_typ,
                seriennummer=serial_number,
                verfuegbare_daten=verfuegbar,
            )

        except httpx.TimeoutException:
            return CloudConnectionTestResult(
                erfolg=False,
                fehler="Zeitüberschreitung bei der Verbindung zur EcoFlow API.",
            )
        except Exception as e:
            logger.exception("EcoFlow API Verbindungstest fehlgeschlagen")
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
        """Holt historische Monatsdaten vom EcoFlow PowerOcean.

        Die History-API verlangt ein Fenster von weniger als 1 Woche pro
        Request. Für jeden Monat werden daher ~6 Requests gemacht und die
        Werte summiert.
        """
        access_key = credentials.get("access_key", "")
        secret_key = credentials.get("secret_key", "")
        serial_number = credentials.get("serial_number", "")
        region = credentials.get("region", "eu")

        host = _get_api_host(region)
        results: list[ParsedMonthData] = []
        # Diagnose: alle indexName-Werte, die die API geliefert hat — quer
        # über alle Monate. Wird unten zur WARNING genutzt, wenn die API
        # antwortet, aber kein einziger Name im INDEX_NAME_MAPPING vorkommt.
        seen_indexnames: set[str] = set()

        # Monate iterieren
        current_year = start_year
        current_month = start_month

        while (current_year, current_month) <= (end_year, end_month):
            month_data, names = await self._fetch_single_month(
                host, access_key, secret_key, serial_number,
                current_year, current_month,
            )
            seen_indexnames.update(names)
            if month_data and month_data.has_data():
                results.append(month_data)

            # Nächster Monat
            if current_month == 12:
                current_year += 1
                current_month = 1
            else:
                current_month += 1

        # Lautes Scheitern bei stillem Mapping-Miss: API hat geantwortet,
        # aber kein einziger indexName ist in INDEX_NAME_MAPPING enthalten.
        # Dirk-PN-Klasse — ohne diesen Log konnte 2026-05-22 niemand sehen,
        # WAS die EcoFlow-API überhaupt zurückgegeben hat.
        if not results and seen_indexnames:
            unmapped = sorted(
                n for n in seen_indexnames if n not in INDEX_NAME_MAPPING
            )
            logger.warning(
                "EcoFlow PowerOcean (sn=%s) lieferte 0 verwertbare Monatswerte. "
                "Erhaltene indexNames: %s. Davon nicht im Mapping: %s. Bitte "
                "INDEX_NAME_MAPPING in ecoflow_powerocean.py um die echten "
                "Namen erweitern (oder im Issue posten — der Log liegt damit vor).",
                serial_number, sorted(seen_indexnames), unmapped,
            )

        return results

    async def _fetch_single_month(
        self,
        host: str,
        access_key: str,
        secret_key: str,
        serial_number: str,
        year: int,
        month: int,
    ) -> tuple[Optional[ParsedMonthData], set[str]]:
        """Holt Daten für einen einzelnen Monat (in Blöcken < 1 Woche).

        Liefert zusätzlich die Menge aller indexName-Werte, die die API
        in diesem Monat zurückgegeben hat — für die Mapping-Diagnose im
        Aufrufer (`fetch_monthly_data`).
        """

        # Monatsanfang und -ende bestimmen
        month_start = datetime(year, month, 1)
        if month == 12:
            month_end = datetime(year + 1, 1, 1)
        else:
            month_end = datetime(year, month + 1, 1)

        # Nicht in der Zukunft abfragen
        now = datetime.now()
        if month_start > now:
            return None, set()
        if month_end > now:
            month_end = now

        # Aggregierte Werte für den Monat + alle gesehenen indexNames
        aggregated: dict[str, float] = {}
        seen_names: set[str] = set()

        # In Blöcken < 1 Woche abfragen (API verlangt < 7 Tage pro Request)
        block_start = month_start
        while block_start < month_end:
            block_end = min(block_start + timedelta(days=MAX_BLOCK_DAYS), month_end)

            try:
                block_data = await self._fetch_history_block(
                    host, access_key, secret_key, serial_number,
                    block_start, block_end,
                )

                # Werte zum Monats-Aggregat addieren + alle Namen für die
                # Diagnose mitführen, auch unbekannte.
                for index_name, index_value in block_data:
                    seen_names.add(index_name)
                    field_name = INDEX_NAME_MAPPING.get(index_name)
                    if field_name and index_value is not None:
                        aggregated[field_name] = aggregated.get(field_name, 0) + index_value

            except Exception as e:
                logger.warning(
                    f"EcoFlow History-Block {block_start.date()} - {block_end.date()} "
                    f"fehlgeschlagen: {e}"
                )

            block_start = block_end

        if not aggregated:
            return None, seen_names

        return ParsedMonthData(
            jahr=year,
            monat=month,
            pv_erzeugung_kwh=round(aggregated.get("pv_erzeugung_kwh", 0), 2) or None,
            einspeisung_kwh=round(aggregated.get("einspeisung_kwh", 0), 2) or None,
            netzbezug_kwh=round(aggregated.get("netzbezug_kwh", 0), 2) or None,
            batterie_ladung_kwh=round(aggregated.get("batterie_ladung_kwh", 0), 2) or None,
            batterie_entladung_kwh=round(aggregated.get("batterie_entladung_kwh", 0), 2) or None,
            eigenverbrauch_kwh=round(aggregated.get("eigenverbrauch_kwh", 0), 2) or None,
        ), seen_names

    async def _fetch_history_block(
        self,
        host: str,
        access_key: str,
        secret_key: str,
        serial_number: str,
        begin: datetime,
        end: datetime,
    ) -> list[tuple[str, Optional[float]]]:
        """Einzelnen History-Block (Fenster < 1 Woche) von der API abrufen."""

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

        # Verschachtelte Response: data.data.data[]
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

        # Diagnose: echte indexNames pro Block sichtbar machen — bei einem
        # `getestet=False`-Provider die einzige Brücke zwischen Hersteller-
        # API und unserem INDEX_NAME_MAPPING. Ohne diesen Log konnten wir
        # 2026-05-22 nicht sehen, was die EcoFlow-API überhaupt liefert.
        logger.info(
            "EcoFlow history block (sn=%s, %s→%s) indexNames: %s",
            serial_number, begin.date(), end.date(),
            [n for n, _ in result],
        )

        return result
