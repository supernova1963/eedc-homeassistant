"""
Anker SOLIX Cloud-Import-Provider.

Nutzt die reverse-engineered Anker Cloud-API um historische Energiedaten
von Anker SOLIX Solarbank (und MI80 Mikrowechselrichter) abzurufen.

Auth: E-Mail + Passwort (identisch zur Anker App).
API-Basis: https://ankerpower-api-eu.anker.com (EU)

Login-Schema (Stand 2026, #328):
- ECDH-Schlüsselaustausch (NIST P-256) mit dem statischen Anker-Server-Public-Key,
  das Passwort wird mit dem Shared Secret AES-256-CBC-verschlüsselt übertragen
  (IV = erste 16 Bytes des Shared Secret, PKCS7-Padding, Base64).
- Nach dem Login: Header `x-auth-token` = auth_token, `gtoken` = MD5(user_id).
- Pflicht-Header `app-name: anker_power`.

Daten-Endpunkt ist `energy_analysis` — das früher verwendete `energy_daily`
existiert in der aktuellen API nicht (mehr). Das Abfrage-Fenster
(start_time/end_time) ist TAG-INKLUSIV auf beiden Seiten: Für einen Monat
muss end_time der letzte Monatstag sein, NICHT der 1. des Folgemonats.

`energy_analysis` liefert je `device_type` (devType) NUR die Felder seines
Bereichs — ein einzelner Aufruf reicht NICHT für alle eedc-Größen (#328,
Gegentest Johnny_1993): `solar_production` hat PV/Einspeisung/Eigenverbrauch,
aber WEDER Netzbezug NOCH die Batterie-Summen. Wir fragen daher pro Monat drei
devTypes ab und setzen sie zusammen:
- `solar_production` → PV, `solar_to_grid_total` (Einspeisung),
  `solar_to_home_total` + `solar_to_battery_total` (Eigenverbrauch/Ladung-PV)
- `home_usage`       → `grid_to_home_total` (Netzbezug), `battery_to_home_total`
  (Batterie-Entladung)
- `solarbank`        → `grid_to_battery_total` (Netz-Ladung der Batterie)
Batterie-Ladung = solar_to_battery + grid_to_battery, Entladung =
battery_to_home. (Frühere `charge_total`/`discharge_total` aus der solar-
Response waren die falschen Felder — Netzbezug fehlte ganz, Batterie falsch.)

Schema nachvollzogen anhand der Community-Dokumentation von
https://github.com/thomluther/anker-solix-api (eigene Implementierung).

HINWEIS: Reverse-engineered API, kann bei App-Updates brechen.
Mit echtem Gerät validiert (Johnny_1993, #328, 2026-06-11: Login + Daten-
Mapping inkl. Netzbezug/Batterie korrekt) → getestet=True.
"""

import asyncio
import base64
import calendar
import hashlib
import logging
import time
from datetime import datetime
from typing import Optional

import httpx
from cryptography.hazmat.primitives import padding, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

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
ENERGY_ANALYSIS_PATH = "/power_service/v1/site/energy_analysis"

# Statischer Public Key der Anker-API-Server (EU und COM identisch),
# unkomprimiertes X9.62-Format: 0x04 + 32 Byte X + 32 Byte Y, hex-kodiert.
ANKER_SERVER_PUBLIC_KEY_HEX = (
    "04c5c00c4f8d1197cc7c3167c52bf7acb054d722f0ef08dcd7e0883236e0d72a"
    "3868d9750cb47fa4619248f3d83f0f662671dadc6e2d31c2f41db0161651c7c076"
)

# Die Anker-Server drosseln wiederholte Aufrufe desselben Endpunkts
# (Community-Erfahrung: ~10 Requests/Minute pro Endpunkt). Pro Monat machen
# wir DREI energy_analysis-Requests (devTypes solar/home/solarbank) und halten
# zwischen ALLEN Requests Abstand.
REQUEST_DELAY_S = 6.0

# Trotz Drosselung kann ein 429 auftreten (lange Zeiträume = viele Requests,
# Johnny_1993 #328). Statt den Bereich/Monat zu verlieren, warten wir gestaffelt
# und versuchen es erneut. Werte als Modul-Konstante, damit Tests sie patchen.
RATE_LIMIT_RETRY_DELAYS_S = (30.0, 60.0)

# Bekannte Anker-API-Fehlercodes → verständliche UI-Meldung.
# (Cloud-Import-Fehler sind seit v3.31.5 in der UI sichtbar.)
API_ERROR_HINTS = {
    26108: "E-Mail oder Passwort ist falsch.",
    26156: "E-Mail oder Passwort ist falsch.",
    26052: (
        "Anker verlangt eine zusätzliche Verifizierung. Bitte einmalig in der "
        "Anker-App an- und abmelden und den Import danach erneut versuchen."
    ),
    26070: (
        "Der Server hat den Verschlüsselungs-Schlüssel abgelehnt — vermutlich "
        "hat Anker das Login-Schema geändert. Bitte als Bug melden."
    ),
    26084: "Die Sitzung wurde von einem anderen Login beendet. Bitte erneut versuchen.",
    100053: "Zu viele Login-Versuche. Bitte später erneut versuchen.",
}


def _get_api_base(server: str) -> str:
    """API-Basis-URL für den gewählten Server."""
    if server == "com":
        return API_BASE_COM
    return API_BASE_EU


def _trimmed_credentials(credentials: dict) -> tuple[str, str, str]:
    """E-Mail/Passwort/Server aus den Credentials lesen und Whitespace trimmen.

    Copy-Paste aus Hersteller-Portalen bringt gern führende/folgende
    Leerzeichen mit — die API lehnt das als falsche Zugangsdaten ab.
    """
    email = (credentials.get("email") or "").strip()
    password = (credentials.get("password") or "").strip()
    server = (credentials.get("server") or "eu").strip()
    return email, password, server


def _timezone_gmt_string() -> str:
    """Lokale Zeitzone im Anker-Header-Format, z. B. 'GMT+01:00'."""
    tzo = datetime.now().astimezone().strftime("%z")
    return f"GMT{tzo[:3]}:{tzo[3:5]}"


def _timezone_offset_ms() -> int:
    """Lokaler UTC-Offset in Millisekunden (Login-Feld `time_zone`)."""
    offset = datetime.now().astimezone().utcoffset()
    return round(offset.total_seconds() * 1000) if offset else 0


def _default_headers() -> dict:
    """Standard-Header die bei jedem Request mitgeschickt werden."""
    return {
        "Content-Type": "application/json",
        "Model-Type": "DESKTOP",
        "App-Name": "anker_power",
        "Os-Type": "android",
        "Country": "DE",
        "Timezone": _timezone_gmt_string(),
    }


def _auth_headers(auth_token: str, user_id: str) -> dict:
    """Header für authentifizierte Requests: x-auth-token + gtoken."""
    headers = _default_headers()
    headers["x-auth-token"] = auth_token
    headers["gtoken"] = _gtoken(user_id)
    return headers


def _gtoken(user_id: str) -> str:
    """gtoken = MD5-Hex des user_id aus der Login-Response."""
    return hashlib.md5(user_id.encode("utf-8")).hexdigest()


def _generate_ecdh_keypair() -> ec.EllipticCurvePrivateKey:
    """Frisches ephemeres ECDH-Schlüsselpaar (NIST P-256) pro Login."""
    return ec.generate_private_key(ec.SECP256R1())


def _public_key_hex(private_key: ec.EllipticCurvePrivateKey) -> str:
    """Client-Public-Key unkomprimiert (0x04 + X + Y) als Hex-String."""
    return private_key.public_key().public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint,
    ).hex()


def _compute_shared_secret(
    private_key: ec.EllipticCurvePrivateKey,
    server_public_key_hex: str = ANKER_SERVER_PUBLIC_KEY_HEX,
) -> bytes:
    """ECDH-Shared-Secret (32 Byte) mit dem Anker-Server-Public-Key."""
    server_public_key = ec.EllipticCurvePublicKey.from_encoded_point(
        ec.SECP256R1(), bytes.fromhex(server_public_key_hex)
    )
    return private_key.exchange(ec.ECDH(), server_public_key)


def _encrypt_password(password: str, shared_secret: bytes) -> str:
    """Passwort AES-256-CBC-verschlüsseln, Base64-kodiert.

    Schlüssel = Shared Secret (32 Byte), IV = erste 16 Byte des Shared
    Secret, PKCS7-Padding — exakt das Format, das der Anker-Login erwartet.
    """
    cipher = Cipher(
        algorithms.AES(shared_secret),
        modes.CBC(shared_secret[:16]),
    )
    encryptor = cipher.encryptor()
    padder = padding.PKCS7(128).padder()
    padded = padder.update(password.encode("utf-8")) + padder.finalize()
    encrypted = encryptor.update(padded) + encryptor.finalize()
    return base64.b64encode(encrypted).decode("ascii")


def _build_login_payload(
    email: str,
    password: str,
    private_key: ec.EllipticCurvePrivateKey,
) -> dict:
    """Login-Payload mit ECDH-Public-Key und verschlüsseltem Passwort."""
    shared_secret = _compute_shared_secret(private_key)
    return {
        "ab": "DE",
        "client_secret_info": {
            "public_key": _public_key_hex(private_key),
        },
        "enc": 0,
        "email": email,
        "password": _encrypt_password(password, shared_secret),
        # UTC-Offset in Millisekunden (z. B. GMT+01:00 → 3600000)
        "time_zone": _timezone_offset_ms(),
        # Unix-Timestamp in Millisekunden als String
        "transaction": str(int(time.time() * 1000)),
    }


def _check_response(status_code: int, data: dict, kontext: str) -> dict:
    """HTTP-Status + Anker-Fehlercode prüfen; bei Fehler klare Meldung werfen.

    Returns:
        Das `data`-Objekt der Response bei Erfolg.
    """
    if status_code in (401, 403):
        raise Exception(
            f"{kontext}: Anmeldung von der Anker-API abgelehnt "
            f"(HTTP {status_code}). Bitte Zugangsdaten prüfen."
        )
    if status_code == 429:
        raise Exception(
            f"{kontext}: Zu viele Anfragen an die Anker-API (HTTP 429). "
            "Bitte einige Minuten warten und erneut versuchen."
        )
    if status_code != 200:
        raise Exception(f"{kontext}: HTTP {status_code} von der Anker-API.")

    code = data.get("code", -1)
    if code != 0:
        hint = API_ERROR_HINTS.get(code)
        msg = data.get("msg", "Unbekannter Fehler")
        if hint:
            raise Exception(f"{kontext}: {hint} (Code {code}, '{msg}')")
        raise Exception(f"{kontext}: {msg} (Code {code})")

    return data.get("data") or {}


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
    payload = _build_login_payload(email, password, _generate_ecdh_keypair())

    resp = await client.post(f"{api_base}{LOGIN_PATH}", json=payload)
    result = _check_response(resp.status_code, resp.json(), "Anker-Login fehlgeschlagen")

    token = result.get("auth_token", "")
    user_id = result.get("user_id", "")

    if not token or not user_id:
        raise Exception(
            "Anker-Login: Kein Auth-Token/User-ID in der Login-Response erhalten."
        )

    return token, user_id


async def _get_site_list(
    client: httpx.AsyncClient,
    api_base: str,
    auth_token: str,
    user_id: str,
) -> list[dict]:
    """Liste der Anlagen (Sites) abrufen."""
    resp = await client.post(
        f"{api_base}{SITE_LIST_PATH}",
        json={},
        headers=_auth_headers(auth_token, user_id),
    )
    result = _check_response(
        resp.status_code, resp.json(), "Site-Liste abrufen fehlgeschlagen"
    )
    return result.get("site_list", [])


def _month_window(year: int, month: int) -> tuple[str, str]:
    """Abfrage-Fenster für einen Monat — beidseitig TAG-INKLUSIV.

    Die Anker-API liefert für start_time/end_time beide Randtage mit
    (EcoFlow-Lehre: halboffen angenommen → Import zu hoch). end_time muss
    daher der LETZTE Monatstag sein, nicht der 1. des Folgemonats.
    """
    last_day = calendar.monthrange(year, month)[1]
    return f"{year}-{month:02d}-01", f"{year}-{month:02d}-{last_day:02d}"


async def _get_energy_analysis(
    client: httpx.AsyncClient,
    api_base: str,
    auth_token: str,
    user_id: str,
    site_id: str,
    start_date: str,
    end_date: str,
    dev_type: str = "solar_production",
) -> dict:
    """Energiedaten (Tageswerte + Intervall-Summen) für eine Site abrufen.

    rangeType 'week' akzeptiert beliebige Zeiträume (bis 1 Jahr) und liefert
    eine Tages-Aufschlüsselung in `power` plus *_total-Felder über das
    gesamte (inklusive) Intervall.

    Bei HTTP 429 (Drosselung) wird gestaffelt erneut versucht
    (RATE_LIMIT_RETRY_DELAYS_S), statt den Bereich zu verlieren.
    """
    payload = {
        "site_id": site_id,
        "device_sn": "",  # Pflichtfeld, Daten kommen trotzdem auf Site-Ebene
        "device_type": dev_type,
        "type": "week",
        "start_time": start_date,
        "end_time": end_date,
    }
    url = f"{api_base}{ENERGY_ANALYSIS_PATH}"
    headers = _auth_headers(auth_token, user_id)

    # Erster Versuch + gestaffelte Retries NUR bei 429; andere Fehler sofort
    # an _check_response (klare Meldung). Bei 429 bis zum letzten Versuch warten.
    delays = (0.0, *RATE_LIMIT_RETRY_DELAYS_S)
    for attempt, delay in enumerate(delays):
        if delay:
            logger.info(
                "Anker SOLIX 429 (devType %s) — warte %.0fs und versuche erneut "
                "(%d/%d)", dev_type, delay, attempt, len(delays) - 1,
            )
            await asyncio.sleep(delay)
        resp = await client.post(url, json=payload, headers=headers)
        if resp.status_code != 429 or attempt == len(delays) - 1:
            return _check_response(
                resp.status_code, resp.json(),
                "Energiedaten abrufen fehlgeschlagen",
            )


def _safe_float(value) -> Optional[float]:
    """Sicher einen Wert in float umwandeln."""
    if value is None or value == "" or value == "null":
        return None
    try:
        f = float(value)
        return f if f >= 0 else None
    except (ValueError, TypeError):
        return None


def _sum_optional(*values: Optional[float]) -> Optional[float]:
    """Summe der nicht-None-Werte; None nur wenn ALLE None sind.

    Eine fehlende Teilkomponente (z. B. keine Netz-Ladung der Batterie)
    darf die Gesamtsumme nicht auf None ziehen, ein komplett fehlendes
    Feld aber schon (sonst würde 0 statt „unbekannt" geschrieben).
    """
    present = [v for v in values if v is not None]
    return sum(present) if present else None


def _parse_month_response(
    solar: dict,
    home: dict,
    battery: dict,
    year: int,
    month: int,
) -> Optional[ParsedMonthData]:
    """Drei energy_analysis-Responses (devTypes) → ParsedMonthData.

    `solar` (solar_production) liefert PV/Einspeisung/Eigenverbrauch,
    `home` (home_usage) den Netzbezug + die Batterie-Entladung,
    `battery` (solarbank) die Netz-Ladung der Batterie. Die *_total-Felder
    sind Summen über das abgefragte (inklusive) Intervall. Achtung:
    `power_unit` behauptet 'wh', die Werte sind aber kWh (API-Eigenheit).
    """
    solar = solar or {}
    home = home or {}
    battery = battery or {}

    # PV-Erzeugung: Summe der Tageswerte, Fallback auf solar_total
    daily = [
        _safe_float(item.get("value"))
        for item in (solar.get("power") or [])
    ]
    daily_values = [v for v in daily if v is not None]
    pv = round(sum(daily_values), 2) if daily_values else _safe_float(
        solar.get("solar_total")
    )

    einspeisung = _safe_float(solar.get("solar_to_grid_total"))
    netzbezug = _safe_float(home.get("grid_to_home_total"))

    # Batterie-Ladung = PV in die Batterie + Netz in die Batterie.
    # Entladung = Batterie ins Haus (Fallback: solarbank-Response).
    solar_to_battery = _safe_float(solar.get("solar_to_battery_total"))
    grid_to_battery = _safe_float(battery.get("grid_to_battery_total"))
    batterie_ladung = _sum_optional(solar_to_battery, grid_to_battery)
    batterie_entladung = _safe_float(
        home.get("battery_to_home_total")
    ) or _safe_float(battery.get("battery_to_home_total"))

    # Eigenverbrauch = PV direkt ins Haus + PV in die Batterie.
    # Fallback: Erzeugung − Einspeisung (gleiche Größe, andere Quelle).
    solar_to_home = _safe_float(solar.get("solar_to_home_total"))
    if solar_to_home is not None or solar_to_battery is not None:
        eigenverbrauch = (solar_to_home or 0.0) + (solar_to_battery or 0.0)
    elif pv is not None and einspeisung is not None:
        eigenverbrauch = max(pv - einspeisung, 0.0)
    else:
        eigenverbrauch = None

    month_data = ParsedMonthData(
        jahr=year,
        monat=month,
        pv_erzeugung_kwh=round(pv, 2) if pv is not None else None,
        einspeisung_kwh=round(einspeisung, 2) if einspeisung is not None else None,
        netzbezug_kwh=round(netzbezug, 2) if netzbezug is not None else None,
        eigenverbrauch_kwh=(
            round(eigenverbrauch, 2) if eigenverbrauch is not None else None
        ),
        batterie_ladung_kwh=(
            round(batterie_ladung, 2) if batterie_ladung is not None else None
        ),
        batterie_entladung_kwh=(
            round(batterie_entladung, 2) if batterie_entladung is not None else None
        ),
    )
    return month_data if month_data.has_data() else None


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
            getestet=True,
        )

    async def test_connection(self, credentials: dict) -> CloudConnectionTestResult:
        """Testet die Verbindung zur Anker Cloud-API."""
        email, password, server = _trimmed_credentials(credentials)

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
                sites = await _get_site_list(client, api_base, auth_token, user_id)

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

        Pro Monat DREI energy_analysis-Requests (devTypes solar_production,
        home_usage, solarbank): PV/Einspeisung/Eigenverbrauch aus solar,
        Netzbezug + Batterie-Entladung aus home_usage, Netz-Ladung der
        Batterie aus solarbank — ein einzelner devType liefert nicht alle
        Größen (#328). Endpunkt-Drosselung wird zwischen ALLEN Requests
        eingehalten; home_usage/solarbank dürfen fehlschlagen (z. B. Anlage
        ohne Speicher) ohne den ganzen Monat zu verlieren.
        """
        email, password, server = _trimmed_credentials(credentials)

        api_base = _get_api_base(server)
        results: list[ParsedMonthData] = []

        async with httpx.AsyncClient(
            timeout=20, headers=_default_headers()
        ) as client:
            # Login
            auth_token, user_id = await _login(client, api_base, email, password)

            # Erste Site ermitteln
            sites = await _get_site_list(client, api_base, auth_token, user_id)
            if not sites:
                logger.warning("Anker SOLIX: Keine Anlage gefunden")
                return []

            site_id = sites[0].get("site_id", "")

            # Monate iterieren
            current_year = start_year
            current_month = start_month
            # Flag in einer Liste, damit die innere Closure es mutieren kann.
            first_request = [True]

            async def _throttled(start_date, end_date, dev_type, allow_fail):
                """Ein energy_analysis-Request mit Endpunkt-Drosselung.

                Vor jedem Request (außer dem allerersten) wird gewartet, da
                alle Requests denselben gedrosselten Endpunkt treffen.
                `allow_fail` liefert {} statt zu werfen — für optionale
                devTypes (home_usage/solarbank), die bei Anlagen ohne
                Speicher/Netzbezug fehlen dürfen.
                """
                if not first_request[0]:
                    await asyncio.sleep(REQUEST_DELAY_S)
                first_request[0] = False
                if allow_fail:
                    try:
                        return await _get_energy_analysis(
                            client, api_base, auth_token, user_id,
                            site_id, start_date, end_date, dev_type=dev_type,
                        )
                    except Exception as e:
                        logger.warning(
                            f"Anker SOLIX devType {dev_type} "
                            f"{current_year}-{current_month:02d}: {e}"
                        )
                        return {}
                return await _get_energy_analysis(
                    client, api_base, auth_token, user_id,
                    site_id, start_date, end_date, dev_type=dev_type,
                )

            while (current_year, current_month) <= (end_year, end_month):
                # Monate in der Zukunft überspringen
                now = datetime.now()
                if datetime(current_year, current_month, 1) <= now:
                    try:
                        start_date, end_date = _month_window(
                            current_year, current_month
                        )
                        solar = await _throttled(
                            start_date, end_date, "solar_production",
                            allow_fail=False,
                        )
                        home = await _throttled(
                            start_date, end_date, "home_usage", allow_fail=True
                        )
                        battery = await _throttled(
                            start_date, end_date, "solarbank", allow_fail=True
                        )
                        month_data = _parse_month_response(
                            solar, home, battery, current_year, current_month
                        )
                        if month_data:
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
