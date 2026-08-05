"""
Deye/Solarman Cloud-Import-Provider.

Nutzt die SolarMAN Open API v1.1.0 um historische Monatsdaten von Deye
Wechselrichtern abzurufen. Deye-Geräte kommunizieren über die Solarman-Cloud.

Auth: OAuth2 mit appId/appSecret + SHA256-verschlüsseltem Passwort.
Endpoint: POST /station/v1.0/history (timeType=3 für Monatsdaten, max 12 Monate)

Zwei Dinge, an denen der Provider bis #349 (OliS2811, 20.07.2026) scheiterte:

1. **Region.** Solarman betreibt zwei getrennte Wolken — die chinesische
   (`api.solarmanpv.com`, Portal `home.solarmanpv.com`) und die
   internationale (`globalapi.solarmanpv.com`, Portal
   `globalhome.solarmanpv.com`). Ein europäisches Konto existiert auf der
   chinesischen Seite schlicht nicht; der Host stand hier fest verdrahtet.
   Gelöst wie bei den fünf Geschwister-Providern (Anker, EcoFlow ×2,
   Sungrow, Huawei): ein `type="select"`-Feld „Server-Region".
2. **`bearer`-Präfix.** Das Handbuch der Open API verlangt es ausdrücklich
   („the header field authorization must be transmitted, and you should put
   bearer as a prefix"); hier ging der nackte Token raus. Folge: der Token
   wurde korrekt geholt, jeder fachliche Aufruf danach scheiterte trotzdem.
   Damit konnte dieser Provider seit seiner Einführung auf KEINER Region
   einen Import abschließen — deshalb ist der Default-Wechsel auf „Global"
   auch kein Bruch für Bestands-Zugangsdaten.

Das Passwort geht als kleingeschriebener SHA256-Hex-Digest raus — das war
bereits richtig und ist in #349 ausdrücklich mit geprüft worden.

HINWEIS: Erfordert einen Solarman-Entwickler-Account (appId + appSecret).
Dieser Provider ist NICHT mit echten Geräten getestet (getestet=False) —
deshalb trägt er, wie die EcoFlow-Provider, ein Diagnose-Logging: die
Antwort der Hersteller-API gehört sichtbar in den Backend-Log UND in die
Fehlermeldung, sonst muss der Anwender raten.
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

# Muster wie `sungrow_isolarcloud.API_HOSTS` / `huawei_fusionsolar.API_HOSTS`.
API_HOSTS = {
    "global": "https://globalapi.solarmanpv.com",
    "cn": "https://api.solarmanpv.com",
}

# ⚠ Muss mit der ERSTEN Option des `region`-Felds übereinstimmen: der Wizard
# (`CloudImportWizard.tsx:93`) belegt ein Select ohne gespeicherten Wert mit
# `options[0].value` vor. Stünde hier etwas anderes, wiche der Vorschlag im
# Formular still von dem ab, was das Backend ohne Feld annimmt.
DEFAULT_REGION = "global"


def _resolve_host(credentials: dict) -> str:
    """Basis-URL aus der gewählten Region (Fallback: Default-Region)."""
    region = (credentials.get("region") or DEFAULT_REGION).strip()
    return API_HOSTS.get(region, API_HOSTS[DEFAULT_REGION])


def _auth_header(token: str) -> dict:
    """Authorization-Header der Open API — MIT `bearer`-Präfix (s. Modul-Docstring)."""
    return {"Authorization": f"bearer {token}"}


def _api_fehlertext(data: dict) -> str:
    """`msg`/`code` der Solarman-Antwort für die Oberfläche aufbereiten."""
    msg = data.get("msg") or data.get("error") or "kein Grund genannt"
    code = data.get("code")
    return f"{msg} (code {code})" if code else str(msg)


@register_provider
class DeyeSolarmanProvider(CloudImportProvider):
    """Cloud-Import-Provider für Deye Wechselrichter (via Solarman Cloud)."""

    def info(self) -> CloudProviderInfo:
        return CloudProviderInfo(
            id="deye_solarman",
            name="Deye / Solarman",
            hersteller="Deye",
            beschreibung=(
                "Importiert historische Monatsdaten von Deye Wechselrichtern "
                "über die Solarman-Cloud-API. Unterstützt PV-Erzeugung, "
                "Einspeisung, Netzbezug, Eigenverbrauch und Batterie-Daten."
            ),
            anleitung=(
                "1. Server-Region wählen: Konten aus Europa liegen auf "
                "globalhome.solarmanpv.com, chinesische auf home.solarmanpv.com "
                "— maßgeblich ist die Adresse, unter der Sie sich anmelden\n"
                "2. Solarman-Entwicklerkonto auf demselben Portal anlegen\n"
                "3. App registrieren → appId und appSecret erhalten\n"
                "4. E-Mail/Benutzername und Passwort des Solarman-Kontos bereithalten\n"
                "5. Anlagen-ID (Station ID) aus der Solarman-App ablesen\n"
                "6. Hinweis: Die Station ID ist die numerische ID der Anlage, "
                "nicht der Name"
            ),
            credential_fields=[
                CredentialField(
                    id="app_id",
                    label="App ID",
                    type="text",
                    placeholder="z.B. 202301234567",
                    required=True,
                ),
                CredentialField(
                    id="app_secret",
                    label="App Secret",
                    type="password",
                    placeholder="API App Secret",
                    required=True,
                ),
                CredentialField(
                    id="email",
                    label="E-Mail / Benutzername",
                    type="text",
                    placeholder="Solarman-Konto E-Mail",
                    required=True,
                ),
                CredentialField(
                    id="password",
                    label="Passwort",
                    type="password",
                    placeholder="Solarman-Konto Passwort",
                    required=True,
                ),
                CredentialField(
                    id="region",
                    label="Server-Region",
                    type="select",
                    required=True,
                    options=[
                        {"value": "global", "label": "Global / Europa (globalhome.solarmanpv.com)"},
                        {"value": "cn", "label": "China (home.solarmanpv.com)"},
                    ],
                ),
                CredentialField(
                    id="station_id",
                    label="Anlagen-ID (Station ID)",
                    type="text",
                    placeholder="z.B. 12345",
                    required=True,
                ),
            ],
            getestet=False,
        )

    async def test_connection(self, credentials: dict) -> CloudConnectionTestResult:
        """Testet die Verbindung zur Solarman-API."""
        app_id = credentials.get("app_id", "")
        app_secret = credentials.get("app_secret", "")
        email = credentials.get("email", "")
        password = credentials.get("password", "")
        station_id = credentials.get("station_id", "")
        host = _resolve_host(credentials)

        # `region` steht bewusst NICHT in dieser Prüfung: fehlt sie (Bestands-
        # Zugangsdaten von vor #349), greift die Default-Region statt einer
        # Fehlermeldung über ein Feld, das der Anwender nie gesehen hat.
        if not all([app_id, app_secret, email, password, station_id]):
            return CloudConnectionTestResult(
                erfolg=False,
                fehler="Alle Felder müssen ausgefüllt werden.",
            )

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                token, token_fehler = await self._get_token(
                    client, host, app_id, app_secret, email, password
                )
                if not token:
                    return CloudConnectionTestResult(
                        erfolg=False,
                        # Der Grund der API steht vorn — die Prüfliste dahinter
                        # hilft nur, wenn man ihn kennt (#349: OliS2811 sah
                        # ausschließlich die Prüfliste und musste raten).
                        fehler=(
                            f"Authentifizierung an {host} fehlgeschlagen: "
                            f"{token_fehler or 'kein Grund genannt'}. "
                            "Bitte Server-Region, appId, appSecret, E-Mail und "
                            "Passwort prüfen."
                        ),
                    )

                # Anlagen-Info abrufen
                resp = await client.post(
                    f"{host}/station/v1.0/base",
                    headers=_auth_header(token),
                    json={"stationId": int(station_id)},
                )

                # Diagnose-Logging wie bei den EcoFlow-Providern: solange
                # `getestet=False` gilt, ist der Backend-Log die einzige Brücke
                # zwischen Hersteller-API und unserem Mapping.
                logger.info(
                    "Solarman Connection-Test: host=%s, station=%s, "
                    "http_status=%s, body=%s",
                    host, station_id, resp.status_code, resp.text[:500],
                )

                if resp.status_code != 200:
                    return CloudConnectionTestResult(
                        erfolg=False,
                        fehler=(
                            f"HTTP {resp.status_code} von {host}. "
                            f"Antwort: {resp.text[:300] or '(leer)'}"
                        ),
                    )

                data = resp.json()
                if not data.get("success", False):
                    return CloudConnectionTestResult(
                        erfolg=False,
                        fehler=f"API-Fehler: {_api_fehlertext(data)}. "
                        "Station ID prüfen.",
                    )

                station = data.get("body", {})
                name = station.get("name", "Deye Anlage")
                capacity = station.get("installedCapacity")

                verfuegbar = f"Anlage: {name}"
                if capacity:
                    verfuegbar += f", {capacity} kWp"

                return CloudConnectionTestResult(
                    erfolg=True,
                    geraet_name=name,
                    geraet_typ="Deye/Solarman",
                    seriennummer=str(station_id),
                    verfuegbare_daten=verfuegbar,
                )

        except httpx.ConnectError:
            return CloudConnectionTestResult(
                erfolg=False,
                fehler=f"Keine Verbindung zu {host}. Internetzugang und "
                "Server-Region prüfen.",
            )
        except httpx.TimeoutException:
            return CloudConnectionTestResult(
                erfolg=False,
                fehler=f"Zeitüberschreitung bei der Verbindung zu {host}.",
            )
        except Exception as e:
            logger.exception("Deye/Solarman Verbindungstest fehlgeschlagen")
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
        """Holt historische Monatsdaten von der Solarman-API."""
        app_id = credentials.get("app_id", "")
        app_secret = credentials.get("app_secret", "")
        email = credentials.get("email", "")
        password = credentials.get("password", "")
        station_id = int(credentials.get("station_id", "0"))
        host = _resolve_host(credentials)

        results: list[ParsedMonthData] = []

        async with httpx.AsyncClient(timeout=15) as client:
            token, token_fehler = await self._get_token(
                client, host, app_id, app_secret, email, password
            )
            if not token:
                raise Exception(
                    f"Solarman-Authentifizierung an {host} fehlgeschlagen: "
                    f"{token_fehler or 'kein Grund genannt'}"
                )

            # API erlaubt max 12 Monate pro Abfrage → in Jahresblöcke aufteilen
            current = (start_year, start_month)
            end = (end_year, end_month)

            while current <= end:
                # Block: ab current, max 12 Monate, nicht über end hinaus.
                #
                # ⚠ Die alte Formel (`block_start_y + (block_start_m + 11) // 12 - 1`)
                # verlor bei jedem Startmonat ≠ Januar ein Jahr: aus „ab Juni 2025,
                # zwölf Monate" wurde das Blockende **Mai 2025** — also VOR dem
                # Blockanfang. Der Fortschaltschritt am Schleifenende setzte
                # `current` damit auf denselben Monat zurück ⇒ Endlosschleife mit
                # einem Abruf pro Runde gegen die Hersteller-API. Sichtbar wurde es
                # erst mit #349: solange die Authentifizierung scheiterte, kam kein
                # Aufruf je bis hierher.
                block_start_y, block_start_m = current
                monate = (block_start_m - 1) + 11
                block_end_y = block_start_y + monate // 12
                block_end_m = monate % 12 + 1
                if (block_end_y, block_end_m) > end:
                    block_end_y, block_end_m = end

                start_time = f"{block_start_y}-{block_start_m:02d}-01"
                end_time = f"{block_end_y}-{block_end_m:02d}-28"

                resp = await client.post(
                    f"{host}/station/v1.0/history",
                    headers=_auth_header(token),
                    json={
                        "stationId": station_id,
                        "timeType": 3,  # Monatsdaten
                        "startTime": start_time,
                        "endTime": end_time,
                    },
                )

                # Abbruch mit Grund: was die API sagt, steht im Log — und wenn
                # noch KEIN Monat geholt ist, auch in der Oberfläche. Sonst
                # meldete der Import „keine Monatsdaten gefunden" und verschwieg,
                # dass er gar nicht erst gefragt hat (P4-Klasse).
                if resp.status_code != 200:
                    grund = (
                        f"HTTP {resp.status_code} von {host} für {start_time}: "
                        f"{resp.text[:300] or '(leer)'}"
                    )
                    logger.warning("Solarman API %s", grund)
                    if not results:
                        raise Exception(f"Solarman-Abruf fehlgeschlagen — {grund}")
                    break

                data = resp.json()
                if not data.get("success", False):
                    grund = f"{_api_fehlertext(data)} (ab {start_time})"
                    logger.warning("Solarman API Fehler: %s", grund)
                    if not results:
                        raise Exception(f"Solarman-Abruf fehlgeschlagen — {grund}")
                    break

                for item in data.get("body", {}).get("stationDataItems", []):
                    jahr = item.get("year")
                    monat = item.get("month")
                    if not jahr or not monat:
                        continue

                    if not ((start_year, start_month) <= (jahr, monat) <= (end_year, end_month)):
                        continue

                    month_data = ParsedMonthData(
                        jahr=jahr,
                        monat=monat,
                        pv_erzeugung_kwh=_round(item.get("generationValue")),
                        einspeisung_kwh=_round(item.get("gridValue")),
                        netzbezug_kwh=_round(item.get("buyValue")),
                        eigenverbrauch_kwh=_round(item.get("useValue")),
                        batterie_ladung_kwh=_round(item.get("chargeValue")),
                        batterie_entladung_kwh=_round(item.get("dischargeValue")),
                    )

                    if month_data.has_data():
                        results.append(month_data)

                # Nächster Block
                next_m = block_end_m + 1
                next_y = block_end_y
                if next_m > 12:
                    next_m = 1
                    next_y += 1
                if (next_y, next_m) <= current:
                    # Fortschritts-Wächter: keine Rechnung über Monatsgrenzen darf
                    # die Schleife stehen lassen (s. Kommentar oben). Lieber mit
                    # dem Geholten zurückkommen als endlos die API befragen.
                    logger.error(
                        "Solarman Blockrechnung ohne Fortschritt bei %s — Abbruch",
                        current,
                    )
                    break
                current = (next_y, next_m)

        return results

    async def _get_token(
        self,
        client: httpx.AsyncClient,
        host: str,
        app_id: str,
        app_secret: str,
        email: str,
        password: str,
    ) -> tuple[Optional[str], Optional[str]]:
        """Holt einen Access-Token.

        Rückgabe: `(token, fehler)` — genau eines der beiden ist gesetzt.
        Der Fehlertext ist der der Hersteller-API; bis #349 gab diese Funktion
        für HTTP-Fehler, fachliche Ablehnung und Exception gleichermaßen `None`
        zurück, und die Oberfläche riet.
        """
        try:
            # Solarman erwartet den SHA256-Hex-Digest in Kleinschreibung —
            # `hexdigest()` liefert genau das (in #349 gegengeprüft).
            pw_hash = hashlib.sha256(password.encode("utf-8")).hexdigest()

            resp = await client.post(
                f"{host}/account/v1.0/token",
                params={"appId": app_id},
                json={
                    "appSecret": app_secret,
                    "email": email,
                    "password": pw_hash,
                },
            )

            logger.info(
                "Solarman Token-Anfrage: host=%s, http_status=%s, body=%s",
                host, resp.status_code, resp.text[:500],
            )

            if resp.status_code != 200:
                return None, (
                    f"HTTP {resp.status_code} — {resp.text[:200] or '(leer)'}"
                )

            data = resp.json()
            if not data.get("success", False):
                erster_grund = _api_fehlertext(data)
                # Fallback: username statt email
                resp = await client.post(
                    f"{host}/account/v1.0/token",
                    params={"appId": app_id},
                    json={
                        "appSecret": app_secret,
                        "username": email,
                        "password": pw_hash,
                    },
                )
                if resp.status_code != 200:
                    return None, (
                        f"{erster_grund}; auch als Benutzername: "
                        f"HTTP {resp.status_code}"
                    )
                data = resp.json()
                if not data.get("success", False):
                    return None, (
                        f"{erster_grund}; auch als Benutzername: "
                        f"{_api_fehlertext(data)}"
                    )

            token = data.get("body", {}).get("access_token")
            if not token:
                return None, "Antwort enthielt keinen access_token"
            return token, None

        except Exception as e:
            fehler = f"{type(e).__name__}: {e}"
            logger.warning("Solarman Token-Anfrage fehlgeschlagen: %s", fehler)
            return None, fehler


def _round(value: Optional[float]) -> Optional[float]:
    """Rundet auf 2 Dezimalstellen, None bleibt None."""
    if value is None:
        return None
    return round(value, 2)
