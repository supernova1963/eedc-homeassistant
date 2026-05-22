"""
Victron VRM Cloud-Import-Provider.

Holt historische Monats-Energiedaten aus dem Victron VRM Portal über die
VRM API v2. Damit lassen sich auch Daten aus der Zeit vor der HA-Anbindung
nachholen — der Live-Pfad (HA-Add-on + ha-victron-mqtt) bleibt davon
unberührt (Issue #255).

Auth: Access-Token im Header `X-Authorization: Token <token>`. Der Token
wird im VRM-Portal unter Preferences → Integrations → Access tokens erzeugt;
es wird kein Passwort gespeichert.

Endpoints:
  - GET /v2/installations/{idSite}/system-overview  → Verbindungstest
  - GET /v2/installations/{idSite}/stats            → Monats-Energiedaten

HINWEIS: Dieser Provider ist NICHT mit echten Geräten getestet
(getestet=False). Die VRM-Stats-Attributnamen in STATS_ATTR_MAPPING stammen
aus der öffentlichen API-Doku und müssen mit echten Konto-Daten verifiziert
werden — `_fetch_stats_block` loggt die tatsächlich gelieferten Record-Keys
auf INFO-Level, damit eine Abweichung sofort sichtbar wird.

API-Dokumentation: https://vrm-api-docs.victronenergy.com/
"""

import logging
from datetime import datetime, timezone
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

API_BASE = "https://vrmapi.victronenergy.com/v2"

# Mapping: VRM-Stats-Attribut (records-Key bei type=kwh) → ParsedMonthData-Feld.
# WICHTIG: Diese Codes sind aus der öffentlichen VRM-API-Doku abgeleitet und
# müssen mit echten Konto-Daten verifiziert werden. Pro Energieart sind
# plausible Varianten hinterlegt; `_fetch_stats_block` loggt die echten Keys.
STATS_ATTR_MAPPING = {
    # PV-Erzeugung
    "solar_yield": "pv_erzeugung_kwh",
    "Pdc": "pv_erzeugung_kwh",
    # Netzbezug (Netz → System)
    "grid_history_from": "netzbezug_kwh",
    "from_grid": "netzbezug_kwh",
    # Einspeisung (System → Netz)
    "grid_history_to": "einspeisung_kwh",
    "to_grid": "einspeisung_kwh",
    # Gesamtverbrauch
    "consumption": "eigenverbrauch_kwh",
    "total_consumption": "eigenverbrauch_kwh",
    # Batterie
    "battery_history_charged": "batterie_ladung_kwh",
    "battery_charged_energy": "batterie_ladung_kwh",
    "battery_history_discharged": "batterie_entladung_kwh",
    "battery_discharged_energy": "batterie_entladung_kwh",
}


def _ts_to_year_month(ts: float) -> tuple[int, int]:
    """Rechnet einen VRM-Record-Zeitstempel auf (Jahr, Monat) um.

    VRM liefert Stats-Zeitstempel in Sekunden (ältere Endpunkte teils in
    Millisekunden — wird erkannt). Für `interval=months` markiert der
    Zeitstempel den Monatsanfang in der Anlagen-Zeitzone. Damit eine
    Zeitzonen-Verschiebung (±14 h) den Wert nicht über die Monatsgrenze
    in den Nachbarmonat schiebt, wird vor der Auswertung 15 Tage addiert —
    das landet robust in der Monatsmitte.
    """
    if ts > 1e12:  # Millisekunden
        ts = ts / 1000.0
    dt = datetime.fromtimestamp(ts + 15 * 86400, tz=timezone.utc)
    return dt.year, dt.month


def _records_to_monthly_data(records: dict) -> list[ParsedMonthData]:
    """Wandelt das VRM-`records`-Objekt (type=kwh) in ParsedMonthData um.

    `records` ist ein Dict `attribut → [[zeitstempel, wert], …]`. Jede Serie
    liefert pro Monat einen Wert; nicht gemappte Attribute werden ignoriert.
    Pure Funktion ohne Netzwerk — direkt testbar.
    """
    monats: dict[tuple[int, int], dict[str, float]] = {}

    for attr, serie in records.items():
        feld = STATS_ATTR_MAPPING.get(attr)
        if not feld or not isinstance(serie, list):
            continue
        for punkt in serie:
            if not isinstance(punkt, (list, tuple)) or len(punkt) < 2:
                continue
            ts, wert = punkt[0], punkt[1]
            if ts is None or wert is None:
                continue
            jahr, monat = _ts_to_year_month(float(ts))
            # Jede (Monat, Attribut)-Kombination ist ein eigener Messwert —
            # zuweisen, nicht summieren.
            monats.setdefault((jahr, monat), {})[feld] = float(wert)

    results: list[ParsedMonthData] = []
    for (jahr, monat) in sorted(monats.keys()):
        werte = monats[(jahr, monat)]

        pv = werte.get("pv_erzeugung_kwh")
        einspeisung = werte.get("einspeisung_kwh")
        verbrauch = werte.get("eigenverbrauch_kwh")

        # Eigenverbrauch bevorzugt aus PV − Einspeisung (analog SolarEdge-
        # Provider), sonst der gemeldete Gesamtverbrauch als Fallback.
        eigenverbrauch = None
        if pv is not None and einspeisung is not None:
            eigenverbrauch = round(pv - einspeisung, 2)
        elif verbrauch is not None:
            eigenverbrauch = round(verbrauch, 2)

        month_data = ParsedMonthData(
            jahr=jahr,
            monat=monat,
            pv_erzeugung_kwh=round(pv, 2) if pv is not None else None,
            einspeisung_kwh=round(einspeisung, 2) if einspeisung is not None else None,
            netzbezug_kwh=(
                round(werte["netzbezug_kwh"], 2)
                if werte.get("netzbezug_kwh") is not None else None
            ),
            batterie_ladung_kwh=(
                round(werte["batterie_ladung_kwh"], 2)
                if werte.get("batterie_ladung_kwh") is not None else None
            ),
            batterie_entladung_kwh=(
                round(werte["batterie_entladung_kwh"], 2)
                if werte.get("batterie_entladung_kwh") is not None else None
            ),
            eigenverbrauch_kwh=eigenverbrauch,
        )
        if month_data.has_data():
            results.append(month_data)

    return results


@register_provider
class VictronVRMProvider(CloudImportProvider):
    """Cloud-Import-Provider für das Victron VRM Portal."""

    def info(self) -> CloudProviderInfo:
        return CloudProviderInfo(
            id="victron_vrm",
            name="Victron VRM",
            hersteller="Victron Energy",
            beschreibung=(
                "Importiert historische Energiedaten (PV-Erzeugung, Einspeisung, "
                "Netzbezug, Batterie) aus dem Victron VRM Portal über die VRM API. "
                "Für das Nachholen von Daten aus der Zeit vor der HA-Anbindung."
            ),
            anleitung=(
                "1. Im VRM Portal einloggen (vrm.victronenergy.com)\n"
                "2. Preferences → Integrations → Access tokens → neuen Token "
                "erstellen und kopieren\n"
                "3. Installation-ID (idSite) aus der Portal-URL ablesen "
                "(Zahl nach /installation/)"
            ),
            credential_fields=[
                CredentialField(
                    id="access_token",
                    label="Access Token",
                    type="password",
                    placeholder="Ihr VRM Access Token",
                    required=True,
                ),
                CredentialField(
                    id="installation_id",
                    label="Installation-ID (idSite)",
                    type="text",
                    placeholder="z.B. 123456",
                    required=True,
                ),
            ],
            getestet=False,
        )

    def _auth_headers(self, access_token: str) -> dict:
        """Header für die VRM-API-Authentifizierung per Access-Token."""
        return {"X-Authorization": f"Token {access_token}"}

    async def test_connection(self, credentials: dict) -> CloudConnectionTestResult:
        """Testet die Verbindung zur VRM API über den system-overview-Endpoint."""
        access_token = credentials.get("access_token", "")
        site_id = credentials.get("installation_id", "")

        if not access_token or not site_id:
            return CloudConnectionTestResult(
                erfolg=False,
                fehler="Access Token und Installation-ID sind erforderlich.",
            )

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    f"{API_BASE}/installations/{site_id}/system-overview",
                    headers=self._auth_headers(access_token),
                )

            # Diagnose-Logging: dieser Provider ist getestet=False, echte
            # Fehler-Antworten der VRM-API gehören sichtbar in den Log.
            logger.info(
                "VRM Connection-Test: idSite=%s, http_status=%s, body=%s",
                site_id, resp.status_code, resp.text[:500],
            )

            if resp.status_code == 401:
                return CloudConnectionTestResult(
                    erfolg=False,
                    fehler="Access Token ungültig oder abgelaufen.",
                )
            if resp.status_code == 403:
                return CloudConnectionTestResult(
                    erfolg=False,
                    fehler=f"Kein Zugriff auf Installation {site_id} mit diesem Token.",
                )
            if resp.status_code == 404:
                return CloudConnectionTestResult(
                    erfolg=False,
                    fehler=f"Installation-ID {site_id} nicht gefunden.",
                )
            if resp.status_code != 200:
                return CloudConnectionTestResult(
                    erfolg=False,
                    fehler=(
                        f"VRM-API-Fehler: HTTP {resp.status_code}. "
                        f"Antwort: {resp.text[:300] or '(leer)'}"
                    ),
                )

            try:
                data = resp.json()
            except Exception as e:
                return CloudConnectionTestResult(
                    erfolg=False,
                    fehler=(
                        f"Antwort der VRM-API ist kein gültiges JSON "
                        f"({type(e).__name__}). Body: {resp.text[:300]}"
                    ),
                )

            if not data.get("success", False):
                fehler_detail = data.get("errors") or data.get("error") or "Unbekannter Fehler"
                return CloudConnectionTestResult(
                    erfolg=False,
                    fehler=f"VRM-API meldet einen Fehler: {fehler_detail}",
                )

            records = data.get("records", {})
            geraete = records.get("devices", []) if isinstance(records, dict) else []
            verfuegbar = f"Installation {site_id} erreichbar"
            if geraete:
                verfuegbar += f", {len(geraete)} Gerät(e)"

            return CloudConnectionTestResult(
                erfolg=True,
                geraet_name=f"Victron VRM Installation {site_id}",
                geraet_typ="Victron VRM",
                seriennummer=str(site_id),
                verfuegbare_daten=verfuegbar,
            )

        except httpx.TimeoutException:
            return CloudConnectionTestResult(
                erfolg=False,
                fehler="Zeitüberschreitung bei der Verbindung zur VRM API.",
            )
        except Exception as e:
            logger.exception("VRM API Verbindungstest fehlgeschlagen")
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
        """Holt historische Monatsdaten aus dem VRM Portal.

        Der stats-Endpoint wird pro Kalenderjahr abgefragt (ein Request je
        Jahr), die Monatswerte werden zusammengeführt.
        """
        access_token = credentials.get("access_token", "")
        site_id = credentials.get("installation_id", "")

        results: list[ParsedMonthData] = []

        for jahr in range(start_year, end_year + 1):
            erster_monat = start_month if jahr == start_year else 1
            letzter_monat = end_month if jahr == end_year else 12

            block_start = datetime(jahr, erster_monat, 1, tzinfo=timezone.utc)
            if letzter_monat == 12:
                block_end = datetime(jahr + 1, 1, 1, tzinfo=timezone.utc)
            else:
                block_end = datetime(jahr, letzter_monat + 1, 1, tzinfo=timezone.utc)

            try:
                block = await self._fetch_stats_block(
                    access_token, site_id, block_start, block_end,
                )
                results.extend(block)
            except Exception as e:
                logger.warning(
                    f"VRM Stats-Block {jahr} (idSite={site_id}) fehlgeschlagen: {e}"
                )

        return results

    async def _fetch_stats_block(
        self,
        access_token: str,
        site_id: str,
        block_start: datetime,
        block_end: datetime,
    ) -> list[ParsedMonthData]:
        """Holt einen Stats-Block (Monatswerte) vom VRM stats-Endpoint."""
        params = {
            "type": "kwh",
            "interval": "months",
            "start": int(block_start.timestamp()),
            # Eine Sekunde vor dem Folgemonat → letzter angefragter Monat inklusive.
            "end": int(block_end.timestamp()) - 1,
        }

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{API_BASE}/installations/{site_id}/stats",
                params=params,
                headers=self._auth_headers(access_token),
            )

        if resp.status_code != 200:
            raise Exception(f"HTTP {resp.status_code}: {resp.text[:200]}")

        data = resp.json()
        if not data.get("success", False):
            fehler_detail = data.get("errors") or data.get("error") or "Unbekannt"
            raise Exception(f"VRM-API-Fehler: {fehler_detail}")

        records = data.get("records", {})
        if not isinstance(records, dict):
            return []

        # Diagnose: tatsächliche Attribut-Keys loggen, damit eine Abweichung
        # vom STATS_ATTR_MAPPING bei diesem getestet=False-Provider auffällt.
        logger.info(
            "VRM stats records keys (idSite=%s): %s",
            site_id, list(records.keys()),
        )

        return _records_to_monthly_data(records)
