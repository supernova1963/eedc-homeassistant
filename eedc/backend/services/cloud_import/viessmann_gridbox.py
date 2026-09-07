"""
Viessmann GridBox Cloud-Import-Provider.

Nutzt die gridX Cloud API (gleiche API wie das Viessmann GridBox Dashboard)
um historische Energiedaten abzurufen.

Auth: OAuth2 via Auth0 mit den GridBox-Zugangsdaten.
  - Token URL: https://gridx.eu.auth0.com/oauth/token
  - API Base:  https://api.gridx.de
  - Audience:  identisch mit der API-Basis. Bis 2026 stand hier "my.gridx";
    gridX akzeptiert den alten Wert nur noch waehrend einer Gnadenfrist
    (#410, gemeldet von gridX selbst).
  - Bearer:    der `access_token` der Auth0-Antwort, NICHT der `id_token`.
    Der id_token ist der abgekuendigte Weg derselben Umstellung.

Endpoints:
  - GET /gateways                                 → Gateway-Liste mit System-IDs
  - GET /systems/{id}/live                        → Live-Daten
  - GET /systems/{id}/historical?interval=...     → Historische Daten

Die historischen Daten werden mit Tages-Auflösung (resolution=1d) abgerufen
und zu Monatssummen aggregiert. Die API liefert Leistungswerte in Watt,
die über die Tages-Auflösung bereits zu Wh-Werten integriert sind.

HINWEIS: Dieser Provider ist NICHT mit echten Geräten getestet (getestet=False).

Angemeldet wird gegen den Auth0-Realm von **E.ON Home**, nicht gegen einen
Viessmann-eigenen. Das ist Absicht und keine Verwechslung: Die GridBox ist zum
31.12.2025 samt Daten zu E.ON Home gewechselt, der Viessmann-Realm
(`viessmann-authentication-db`) ist seither abgeschaltet. Anmeldeseite ist
https://eon.gridx.de/login — `mygridbox.viessmann.com` gibt es nicht mehr.
"""

import logging
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import quote

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

AUTH_URL = "https://gridx.eu.auth0.com/oauth/token"
API_BASE = "https://api.gridx.de"

# Auth0 Client-Konfiguration (öffentlicher Client der GridBox-App)
AUTH0_CLIENT_ID = "mG0Phmo7DmnvAqO7p6B0WOYBODppY3cc"
# Die Audience IST die API — so lautet die Anforderung von gridX woertlich
# (#410). Deshalb steht hier keine zweite Zeichenkette neben `API_BASE`, die
# unbemerkt auseinanderlaufen koennte, sondern die Kopplung selbst.
AUTH0_AUDIENCE = API_BASE
# E.ON Home, nicht Viessmann — siehe Kopf-Docstring. Der Viessmann-Realm ist
# seit Ende 2025 abgeschaltet; wer ihn hier einsetzt, sperrt alle Anwender aus.
AUTH0_REALM = "eon-home-authentication-db"
AUTH0_SCOPE = "email openid offline_access"


def _auth_fehlertext(resp: httpx.Response) -> str:
    """Grund einer abgelehnten Auth0-Antwort — nicht nur ihre Nummer.

    Auth0 nennt in `error_description` den echten Grund (falscher Realm,
    unbekannte Audience, gesperrter Account). Ohne ihn meldete eedc jeden
    Fehlschlag als „E-Mail/Passwort prüfen" — auch dann, wenn beide stimmten.
    """
    try:
        data = resp.json()
    except ValueError:
        return f"HTTP {resp.status_code}"
    grund = data.get("error_description") or data.get("error")
    return f"HTTP {resp.status_code}: {grund}" if grund else f"HTTP {resp.status_code}"


async def _get_token(
    username: str, password: str,
) -> tuple[Optional[str], Optional[str]]:
    """OAuth2 Token über Auth0 Password-Realm Grant holen.

    Rückgabe: `(token, fehler)` — genau eines der beiden ist gesetzt
    (Idiom aus `deye_solarman`).
    """
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            AUTH_URL,
            json={
                "grant_type": "http://auth0.com/oauth/grant-type/password-realm",
                "username": username,
                "password": password,
                "audience": AUTH0_AUDIENCE,
                "client_id": AUTH0_CLIENT_ID,
                "scope": AUTH0_SCOPE,
                "realm": AUTH0_REALM,
                "client_secret": "",
            },
        )

    if resp.status_code != 200:
        return None, _auth_fehlertext(resp)

    data = resp.json()

    # gridX erwartet den `access_token`. Der `id_token` wird nur noch waehrend
    # der Gnadenfrist akzeptiert (#410) und bleibt ausschliesslich als Rueckfall
    # fuer den Fall stehen, dass Auth0 fuer diesen Realm keinen access_token
    # liefert — dann steht es im Log, statt still den abgekuendigten Weg zu
    # gehen. Die Audience wird NICHT zurueckgenommen: ein Audience-Fehler soll
    # sofort durchschlagen und nicht bis zum Ende der Gnadenfrist verdeckt sein.
    token = data.get("access_token")
    if token:
        return token, None

    token = data.get("id_token")
    if token:
        logger.warning(
            "gridX-Antwort enthielt keinen access_token — eedc verwendet den "
            "abgekuendigten id_token. Der Zugang faellt aus, sobald gridX die "
            "Gnadenfrist beendet (#410).",
        )
        return token, None

    return None, "Antwort enthielt weder access_token noch id_token"


def _auth_headers(token: str) -> dict:
    """HTTP-Header mit Bearer-Token."""
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }


def _round(value: Optional[float]) -> Optional[float]:
    """Rundet auf 2 Dezimalstellen, None bleibt None."""
    if value is None:
        return None
    return round(value, 2)


@register_provider
class ViessmannGridBoxProvider(CloudImportProvider):
    """Cloud-Import-Provider für Viessmann GridBox (gridX Cloud API)."""

    def info(self) -> CloudProviderInfo:
        return CloudProviderInfo(
            id="viessmann_gridbox",
            name="Viessmann GridBox / E.ON Home",
            hersteller="gridX",
            beschreibung=(
                "Importiert historische Energiedaten (PV-Erzeugung, Eigenverbrauch, "
                "Einspeisung, Netzbezug, Batterie) über die gridX Cloud API — die "
                "Plattform hinter der Viessmann GridBox und dem E.ON Home Manager. "
                "Angemeldet wird mit dem E.ON-Home-Konto."
            ),
            anleitung=(
                "1. E-Mail-Adresse und Passwort des E.ON-Home-Kontos bereithalten\n"
                "   (Anmeldeseite: https://eon.gridx.de/login)\n"
                "2. Viessmann-GridBox-Anlagen sind zum 31.12.2025 samt Daten zu\n"
                "   E.ON Home gewechselt; der frühere Viessmann-Zugang besteht nicht mehr\n"
                "3. System-ID wird beim Verbindungstest automatisch ermittelt\n"
                "   (alternativ aus dem Dashboard-URL ablesen)"
            ),
            credential_fields=[
                CredentialField(
                    id="username",
                    label="E-Mail-Adresse",
                    type="text",
                    placeholder="ihre.email@beispiel.de",
                    required=True,
                ),
                CredentialField(
                    id="password",
                    label="Passwort",
                    type="password",
                    placeholder="Ihr GridBox-Passwort",
                    required=True,
                ),
                CredentialField(
                    id="system_id",
                    label="System-ID (optional)",
                    type="text",
                    placeholder="Wird automatisch ermittelt wenn leer",
                    required=False,
                ),
            ],
            getestet=False,
        )

    async def test_connection(self, credentials: dict) -> CloudConnectionTestResult:
        """Testet die Verbindung zur Viessmann GridBox / gridX API."""
        username = credentials.get("username", "")
        password = credentials.get("password", "")

        if not username or not password:
            return CloudConnectionTestResult(
                erfolg=False,
                fehler="E-Mail-Adresse und Passwort sind erforderlich.",
            )

        try:
            token, login_fehler = await _get_token(username, password)
            if not token:
                # Den Grund nennen, statt ihn zu behaupten: Bis #410 stand hier
                # pauschal „E-Mail/Passwort prüfen" — auch wenn Realm oder
                # Audience abgelehnt wurden und die Zugangsdaten stimmten.
                return CloudConnectionTestResult(
                    erfolg=False,
                    fehler=f"Login fehlgeschlagen. Grund laut gridX: {login_fehler}",
                )

            headers = _auth_headers(token)

            async with httpx.AsyncClient(timeout=15) as client:
                # Gateway-Liste abrufen → System-IDs ermitteln
                resp = await client.get(
                    f"{API_BASE}/gateways",
                    headers=headers,
                )

            if resp.status_code != 200:
                return CloudConnectionTestResult(
                    erfolg=False,
                    fehler=f"API-Fehler beim Abruf der Gateways: HTTP {resp.status_code}",
                )

            gateways = resp.json()
            if not gateways:
                return CloudConnectionTestResult(
                    erfolg=False,
                    fehler="Keine GridBox-Gateways in Ihrem Account gefunden.",
                )

            # Erstes Gateway / System nehmen
            gateway = gateways[0]
            system = gateway.get("system", {})
            system_id = system.get("id", "")
            system_name = system.get("name", gateway.get("name", "GridBox System"))

            # Live-Daten abrufen um zu prüfen ob PV vorhanden
            verfuegbar = f"System: {system_name}"
            async with httpx.AsyncClient(timeout=15) as client:
                live_resp = await client.get(
                    f"{API_BASE}/systems/{system_id}/live",
                    headers=headers,
                )
                if live_resp.status_code == 200:
                    live = live_resp.json()
                    pv_power = live.get("photovoltaic")
                    if pv_power is not None:
                        verfuegbar += f", PV aktuell: {pv_power} W"

            if len(gateways) > 1:
                verfuegbar += f" ({len(gateways)} Gateways gefunden)"

            return CloudConnectionTestResult(
                erfolg=True,
                geraet_name=system_name,
                geraet_typ="Viessmann GridBox",
                seriennummer=system_id,
                verfuegbare_daten=verfuegbar,
            )

        except httpx.TimeoutException:
            return CloudConnectionTestResult(
                erfolg=False,
                fehler="Zeitüberschreitung bei der Verbindung zur GridBox API.",
            )
        except Exception as e:
            logger.exception("GridBox API Verbindungstest fehlgeschlagen")
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
        """Holt historische Monatsdaten von der GridBox / gridX API.

        Ruft Tagesdaten ab (resolution=1d) und aggregiert sie zu Monatssummen.
        """
        username = credentials.get("username", "")
        password = credentials.get("password", "")
        system_id = credentials.get("system_id", "")

        token, login_fehler = await _get_token(username, password)
        if not token:
            raise Exception(
                f"GridBox Login fehlgeschlagen. Grund laut gridX: {login_fehler}"
            )

        headers = _auth_headers(token)

        # System-ID ermitteln wenn nicht angegeben
        if not system_id:
            system_id = await self._get_first_system_id(headers)

        results: list[ParsedMonthData] = []

        # Monat für Monat abrufen um API-Limits zu vermeiden
        for year in range(start_year, end_year + 1):
            m_start = start_month if year == start_year else 1
            m_end = end_month if year == end_year else 12

            for month in range(m_start, m_end + 1):
                try:
                    month_data = await self._fetch_month(
                        headers, system_id, year, month,
                    )
                    if month_data and month_data.has_data():
                        results.append(month_data)
                except Exception as e:
                    logger.warning(
                        f"GridBox Monatsdaten {year}-{month:02d} fehlgeschlagen: {e}"
                    )

        return results

    async def _get_first_system_id(self, headers: dict) -> str:
        """Ermittelt die erste System-ID aus den Gateways."""
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(f"{API_BASE}/gateways", headers=headers)

        if resp.status_code != 200:
            raise Exception(f"Gateway-Abruf fehlgeschlagen: HTTP {resp.status_code}")

        gateways = resp.json()
        if not gateways:
            raise Exception("Keine Gateways gefunden")

        return gateways[0].get("system", {}).get("id", "")

    async def _fetch_month(
        self,
        headers: dict,
        system_id: str,
        year: int,
        month: int,
    ) -> Optional[ParsedMonthData]:
        """Holt Tagesdaten eines Monats und summiert sie."""
        # Zeitraum: Erster bis letzter Tag des Monats (ISO 8601 Interval)
        start = datetime(year, month, 1)
        if month == 12:
            end = datetime(year + 1, 1, 1)
        else:
            end = datetime(year, month + 1, 1)

        # gridX interval Format: "2024-01-01T00:00:00Z/2024-02-01T00:00:00Z"
        interval = f"{start.strftime('%Y-%m-%dT00:00:00Z')}/{end.strftime('%Y-%m-%dT00:00:00Z')}"
        encoded_interval = quote(interval)

        url = f"{API_BASE}/systems/{system_id}/historical?interval={encoded_interval}&resolution=1d"

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url, headers=headers)

        if resp.status_code != 200:
            raise Exception(f"HTTP {resp.status_code}: {resp.text[:200]}")

        data = resp.json()

        # Response: Array von Datenpunkten mit Energiewerten
        # Jeder Datenpunkt enthält Tageswerte in Wh
        # Felder (basierend auf Live-Daten-Struktur, analog für historical):
        #   photovoltaic, production, consumption, grid,
        #   selfConsumption, directConsumption,
        #   gridMeterReadingPositive, gridMeterReadingNegative
        totals: dict[str, float] = defaultdict(float)

        entries = data if isinstance(data, list) else data.get("data", [])

        for entry in entries:
            if not isinstance(entry, dict):
                continue

            # PV-Erzeugung
            pv = entry.get("photovoltaic") or entry.get("production")
            if pv is not None and isinstance(pv, (int, float)):
                totals["pv"] += abs(pv)

            # Eigenverbrauch
            sc = entry.get("selfConsumption") or entry.get("directConsumption")
            if sc is not None and isinstance(sc, (int, float)):
                totals["eigenverbrauch"] += abs(sc)

            # Grid: positiv = Bezug, negativ = Einspeisung (oder umgekehrt)
            grid = entry.get("grid")
            if grid is not None and isinstance(grid, (int, float)):
                if grid > 0:
                    totals["netzbezug"] += grid
                else:
                    totals["einspeisung"] += abs(grid)

            # Alternative: separate Felder für Einspeisung/Bezug
            feed_in = entry.get("gridFeedIn") or entry.get("feedIn")
            if feed_in is not None and isinstance(feed_in, (int, float)):
                totals["einspeisung"] += abs(feed_in)

            grid_purchase = entry.get("gridPurchase") or entry.get("purchase")
            if grid_purchase is not None and isinstance(grid_purchase, (int, float)):
                totals["netzbezug"] += abs(grid_purchase)

            # Batterie
            bat_charge = entry.get("batteryCharge") or entry.get("charge")
            if bat_charge is not None and isinstance(bat_charge, (int, float)):
                totals["bat_ladung"] += abs(bat_charge)

            bat_discharge = entry.get("batteryDischarge") or entry.get("discharge")
            if bat_discharge is not None and isinstance(bat_discharge, (int, float)):
                totals["bat_entladung"] += abs(bat_discharge)

        if not totals:
            return None

        # Werte: Die API liefert bei resolution=1d bereits Wh-Werte,
        # Umrechnung in kWh
        return ParsedMonthData(
            jahr=year,
            monat=month,
            pv_erzeugung_kwh=_round(totals.get("pv", 0) / 1000) or None,
            einspeisung_kwh=_round(totals.get("einspeisung", 0) / 1000) or None,
            netzbezug_kwh=_round(totals.get("netzbezug", 0) / 1000) or None,
            eigenverbrauch_kwh=_round(totals.get("eigenverbrauch", 0) / 1000) or None,
            batterie_ladung_kwh=_round(totals.get("bat_ladung", 0) / 1000) or None,
            batterie_entladung_kwh=_round(totals.get("bat_entladung", 0) / 1000) or None,
        )
