"""
Fronius Solar API Connector.

Verbindet sich über die lokale Fronius Solar API V1 mit Fronius Wechselrichtern
(Primo, Symo, Gen24, etc.) und liest kumulative Zählerstände (kWh) aus.

Endpoints:
- GetPowerFlowRealtimeData → PV-Gesamterzeugung (E_Total)
- GetMeterRealtimeData → Grid-Import/Export (Smart Meter)
- GetInverterInfo → Geräteinfo (Modell, Seriennummer)

Besonderheiten:
- Keine Authentifizierung nötig (offene lokale API)
- Alle Energiewerte in Wh (werden zu kWh konvertiert)
- Smart Meter muss konfiguriert sein für Grid-Werte

HINWEIS: Dieser Connector wurde anhand der Fronius Solar API V1 Dokumentation
erstellt, aber noch nicht mit echten Wechselrichtern verifiziert (getestet=False).
"""

import logging
from datetime import datetime, timezone
from typing import Optional

import aiohttp

from .base import DeviceConnector, ConnectorInfo, MeterSnapshot, ConnectionTestResult
from .registry import register_connector

logger = logging.getLogger(__name__)

# Fronius API Base-Pfade
API_BASE = "/solar_api/v1"
POWERFLOW_URL = f"{API_BASE}/GetPowerFlowRealtimeData.fcgi"
METER_URL = f"{API_BASE}/GetMeterRealtimeData.cgi"
INVERTER_INFO_URL = f"{API_BASE}/GetInverterInfo.cgi"
INVERTER_DATA_URL = f"{API_BASE}/GetInverterRealtimeData.cgi"


async def _fetch_json(
    session: aiohttp.ClientSession, base_url: str, path: str, params: Optional[dict] = None
) -> Optional[dict]:
    """Holt JSON von der Fronius API."""
    url = f"{base_url}{path}"
    try:
        async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status != 200:
                logger.warning("Fronius API %s returned status %d", path, resp.status)
                return None
            return await resp.json(content_type=None)
    except Exception as e:
        logger.warning("Fronius API request failed for %s: %s", path, e)
        return None


def _get_nested(data: dict, *keys, default=None):
    """Sicherer Zugriff auf verschachtelte dict-Keys."""
    current = data
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key, default)
        if current is default:
            return default
    return current


def _wh_to_kwh(value) -> Optional[float]:
    """Konvertiert Wh zu kWh."""
    if value is None:
        return None
    try:
        val = float(value)
        return round(val / 1000.0, 3)
    except (ValueError, TypeError):
        return None


def _extract_meter_energy(meter_info: dict) -> tuple[Optional[float], Optional[float]]:
    """Extrahiert Grid-Import und Export aus Meter-Daten.

    Unterstützt Legacy-Felder (ältere Fronius) und Gen24/SmartMeter-Felder.
    Rückgabe: (import_wh, export_wh)

    Feldnamen basieren auf der Home Assistant pyfronius-Bibliothek:
    - Legacy: EnergyReal_WAC_Minus_Absolute (Import), EnergyReal_WAC_Plus_Absolute (Export)
    - Gen24: SMARTMETER_ENERGYACTIVE_CONSUMED_SUM_F64, SMARTMETER_ENERGYACTIVE_PRODUCED_SUM_F64
    """
    import_wh: Optional[float] = None
    export_wh: Optional[float] = None

    # Legacy-Felder (Fronius Smart Meter am Einspeisepunkt)
    # Plus = Export (ins Netz), Minus = Import (aus dem Netz)
    minus = meter_info.get("EnergyReal_WAC_Minus_Absolute")
    plus = meter_info.get("EnergyReal_WAC_Plus_Absolute")
    if minus is not None:
        import_wh = float(minus)
    if plus is not None:
        export_wh = float(plus)

    # Gen24 SmartMeter-Felder überschreiben Legacy falls vorhanden
    consumed = meter_info.get("SMARTMETER_ENERGYACTIVE_CONSUMED_SUM_F64")
    produced = meter_info.get("SMARTMETER_ENERGYACTIVE_PRODUCED_SUM_F64")
    if consumed is not None:
        import_wh = float(consumed)
    if produced is not None:
        export_wh = float(produced)

    return import_wh, export_wh


@register_connector
class FroniusSolarApiConnector(DeviceConnector):
    """Connector für Fronius Wechselrichter via lokaler Solar API V1."""

    def info(self) -> ConnectorInfo:
        return ConnectorInfo(
            id="fronius_solar_api",
            name="Fronius Solar API",
            hersteller="Fronius",
            beschreibung=(
                "Direktverbindung zu Fronius Wechselrichtern (Primo, Symo, Gen24) "
                "über die lokale Solar API. Liest PV-Erzeugung und Smart Meter "
                "Daten (Netz-Import/Export) aus. Keine Authentifizierung nötig."
            ),
            anleitung=(
                "1. IP-Adresse des Fronius Wechselrichters im lokalen Netzwerk ermitteln\n"
                "   (z.B. über Router oder Fronius Solar.web)\n"
                "2. Prüfen ob die API erreichbar ist: http://<IP>/solar_api/v1/GetAPIVersion.cgi\n"
                "3. Benutzername und Passwort können leer gelassen werden (API ist offen)\n"
                "4. Für Grid-Werte muss ein Fronius Smart Meter installiert und konfiguriert sein"
            ),
            getestet=False,
        )

    async def test_connection(
        self, host: str, username: str, password: str
    ) -> ConnectionTestResult:
        """Testet die Verbindung zum Fronius Wechselrichter."""
        base_url = f"http://{host}"

        try:
            # Gen24 (FW 1.35.4+) leitet HTTP→HTTPS mit Self-Signed Cert um
            connector = aiohttp.TCPConnector(ssl=False)
            async with aiohttp.ClientSession(connector=connector) as session:
                # Inverter-Info abrufen
                info_data = await _fetch_json(session, base_url, INVERTER_INFO_URL)
                if not info_data:
                    return ConnectionTestResult(
                        erfolg=False,
                        fehler=f"Keine Antwort von {host}. Ist die IP korrekt und der Wechselrichter erreichbar?",
                    )

                status_code = _get_nested(info_data, "Head", "Status", "Code")
                if status_code != 0:
                    reason = _get_nested(info_data, "Head", "Status", "Reason", default="Unbekannt")
                    return ConnectionTestResult(
                        erfolg=False,
                        fehler=f"Fronius API Fehler: {reason}",
                    )

                # Geräteinfo extrahieren
                inverters = _get_nested(info_data, "Body", "Data", default={})
                geraet_name = None
                geraet_typ = None
                seriennummer = None

                # Erstes Gerät (typischerweise DeviceId "1")
                for dev_id, dev_info in inverters.items():
                    geraet_typ = dev_info.get("DT", None)
                    geraet_name = dev_info.get("CustomName") or dev_info.get("UniqueID", f"Fronius #{dev_id}")
                    seriennummer = dev_info.get("UniqueID")
                    break

                # Verfügbare Sensoren ermitteln
                sensoren: list[str] = []

                # PowerFlow testen (PV-Erzeugung)
                pf_data = await _fetch_json(session, base_url, POWERFLOW_URL)
                if pf_data and _get_nested(pf_data, "Head", "Status", "Code") == 0:
                    site = _get_nested(pf_data, "Body", "Data", "Site", default={})
                    if site.get("E_Total") is not None:
                        sensoren.append(f"PV Erzeugung (Gesamt: {_wh_to_kwh(site['E_Total']):.1f} kWh)")
                    if site.get("P_PV") is not None:
                        sensoren.append(f"PV Leistung (aktuell: {site['P_PV']:.0f} W)")
                    if site.get("P_Grid") is not None:
                        sensoren.append(f"Netz-Leistung (aktuell: {site['P_Grid']:.0f} W)")
                    if site.get("P_Akku") is not None:
                        sensoren.append(f"Batterie-Leistung (aktuell: {site['P_Akku']:.0f} W)")

                # Meter testen (Grid-Import/Export)
                meter_data = await _fetch_json(
                    session, base_url, METER_URL, params={"Scope": "System"}
                )
                if meter_data and _get_nested(meter_data, "Head", "Status", "Code") == 0:
                    meters = _get_nested(meter_data, "Body", "Data", default={})
                    for meter_id, meter_info in meters.items():
                        if not isinstance(meter_info, dict):
                            continue
                        import_wh, export_wh = _extract_meter_energy(meter_info)
                        if import_wh is not None:
                            sensoren.append(f"Smart Meter #{meter_id}: Netzbezug ({_wh_to_kwh(import_wh):.1f} kWh)")
                        if export_wh is not None:
                            sensoren.append(f"Smart Meter #{meter_id}: Einspeisung ({_wh_to_kwh(export_wh):.1f} kWh)")

                # Aktuelle Werte lesen
                snapshot = await self._read_snapshot(session, base_url)

                return ConnectionTestResult(
                    erfolg=True,
                    geraet_name=geraet_name,
                    geraet_typ=f"Fronius (DT={geraet_typ})" if geraet_typ else "Fronius Wechselrichter",
                    seriennummer=seriennummer,
                    verfuegbare_sensoren=sensoren,
                    aktuelle_werte=snapshot,
                )

        except aiohttp.ClientError as e:
            return ConnectionTestResult(
                erfolg=False,
                fehler=f"Verbindungsfehler: {str(e)}",
            )
        except Exception as e:
            logger.exception("Fehler beim Fronius-Verbindungstest")
            return ConnectionTestResult(
                erfolg=False,
                fehler=f"Unerwarteter Fehler: {str(e)}",
            )

    async def read_meters(
        self, host: str, username: str, password: str
    ) -> MeterSnapshot:
        """Liest aktuelle kumulative Zählerstände vom Fronius Wechselrichter."""
        base_url = f"http://{host}"

        connector = aiohttp.TCPConnector(ssl=False)
        async with aiohttp.ClientSession(connector=connector) as session:
            return await self._read_snapshot(session, base_url)

    async def _read_snapshot(
        self, session: aiohttp.ClientSession, base_url: str
    ) -> MeterSnapshot:
        """Interne Methode: Liest alle Zählerstände und baut MeterSnapshot."""
        now = datetime.now(timezone.utc).isoformat()

        pv_total_kwh: Optional[float] = None
        einspeisung_kwh: Optional[float] = None
        netzbezug_kwh: Optional[float] = None

        # 1. PV-Erzeugung aus PowerFlow
        pf_data = await _fetch_json(session, base_url, POWERFLOW_URL)
        if pf_data and _get_nested(pf_data, "Head", "Status", "Code") == 0:
            site = _get_nested(pf_data, "Body", "Data", "Site", default={})
            pv_total_kwh = _wh_to_kwh(site.get("E_Total"))

        # 2. Grid-Import/Export aus Smart Meter
        # Felder nach HA/pyfronius: Minus_Absolute=Import, Plus_Absolute=Export
        # Gen24 Fallback: SMARTMETER_ENERGYACTIVE_CONSUMED/PRODUCED_SUM_F64
        meter_data = await _fetch_json(
            session, base_url, METER_URL, params={"Scope": "System"}
        )
        if meter_data and _get_nested(meter_data, "Head", "Status", "Code") == 0:
            meters = _get_nested(meter_data, "Body", "Data", default={})
            total_import = 0.0
            total_export = 0.0
            has_meter = False

            for meter_info in meters.values():
                if not isinstance(meter_info, dict):
                    continue
                import_wh, export_wh = _extract_meter_energy(meter_info)
                if import_wh is not None:
                    total_import += import_wh
                    has_meter = True
                if export_wh is not None:
                    total_export += export_wh
                    has_meter = True

            if has_meter:
                netzbezug_kwh = _wh_to_kwh(total_import)
                einspeisung_kwh = _wh_to_kwh(total_export)

        return MeterSnapshot(
            timestamp=now,
            pv_erzeugung_kwh=pv_total_kwh,
            einspeisung_kwh=einspeisung_kwh,
            netzbezug_kwh=netzbezug_kwh,
            batterie_ladung_kwh=None,  # Fronius API hat keine kumulativen Batterie-Zähler
            batterie_entladung_kwh=None,
        )
