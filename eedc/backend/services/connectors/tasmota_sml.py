"""
Tasmota Smart Meter (SML) Connector.

Verbindet sich über die lokale Tasmota HTTP API mit ESP-basierten
Smart-Meter-Readern und liest kumulative Zählerstände aus.

Tasmota-Geräte mit SML-Skript lesen den Hauptstromzähler per IR-Lesekopf
aus und stellen die OBIS-Codes als JSON bereit.

Endpoints:
- GET /cm?cmnd=Status%208 → Sensor-Daten (StatusSNS)
- GET /cm?cmnd=Status%200 → Alle Status-Daten (Geräteinfo)

OBIS-Codes (Standard für deutsche/österreichische/Schweizer Smart Meter):
- 1.8.0 (1_8_0) → Netzbezug gesamt (Wh oder kWh)
- 2.8.0 (2_8_0) → Einspeisung gesamt (Wh oder kWh)
- 16.7.0 (16_7_0) → Aktuelle Gesamtleistung (W)
- 36/56/76.7.0 → Phasenleistung L1/L2/L3 (W)
- 96.1.0 (96_1_0) → Zähler-Seriennummer

Besonderheiten:
- Keine Authentifizierung nötig (Standard-Tasmota)
- Einheiten hängen vom SML-Skript ab (Wh oder kWh)
- Automatische Erkennung der Einheit per Heuristik
- Funktioniert mit jedem Stromzähler der SML/OBIS unterstützt
"""

import logging
from datetime import datetime, timezone
from typing import Optional

import aiohttp

from .base import DeviceConnector, ConnectorInfo, MeterSnapshot, ConnectionTestResult
from .registry import register_connector

logger = logging.getLogger(__name__)

# OBIS-Code Mapping: Tasmota-Feldname → Bedeutung
OBIS_NETZBEZUG = "1_8_0"     # 1.8.0 – Wirkenergie Bezug gesamt
OBIS_EINSPEISUNG = "2_8_0"   # 2.8.0 – Wirkenergie Lieferung gesamt
OBIS_LEISTUNG = "16_7_0"     # 16.7.0 – Momentane Gesamtleistung
OBIS_LEISTUNG_L1 = "36_7_0"  # 36.7.0 – Momentanleistung L1
OBIS_LEISTUNG_L2 = "56_7_0"  # 56.7.0 – Momentanleistung L2
OBIS_LEISTUNG_L3 = "76_7_0"  # 76.7.0 – Momentanleistung L3
OBIS_SERIENNUMMER = "96_1_0"  # 96.1.0 – Geräte-Identifikation


async def _fetch_json(
    session: aiohttp.ClientSession, url: str, timeout: int = 10
) -> Optional[dict]:
    """Holt JSON von der Tasmota API."""
    try:
        async with session.get(
            url, timeout=aiohttp.ClientTimeout(total=timeout)
        ) as resp:
            if resp.status == 401:
                return {"_auth_error": True}
            if resp.status != 200:
                return None
            return await resp.json(content_type=None)
    except Exception as e:
        logger.warning("Tasmota API request failed for %s: %s", url, e)
        return None


def _find_meter_data(status_sns: dict) -> Optional[tuple[str, dict]]:
    """Findet das Smart-Meter-Datenobjekt in StatusSNS.

    Sucht nach einem Dict-Wert der OBIS-Code-artige Schlüssel enthält
    (z.B. 1_8_0, 2_8_0). Der Schlüsselname hängt vom SML-Skript ab
    (häufig: SM, SML, Meter, Zaehler).
    """
    for key, value in status_sns.items():
        if key == "Time":
            continue
        if isinstance(value, dict):
            # Prüfe ob OBIS-ähnliche Keys vorhanden sind
            if OBIS_NETZBEZUG in value or OBIS_EINSPEISUNG in value:
                return key, value
    return None


def _to_kwh(value, all_values: list[float]) -> Optional[float]:
    """Konvertiert Energiewert zu kWh.

    Heuristik für die Einheit:
    - Werte > 100.000 → wahrscheinlich Wh → /1000 für kWh
    - Werte <= 100.000 → wahrscheinlich bereits kWh

    Die Heuristik basiert darauf, dass ein kumulativer Haushaltszähler
    mit 100.000 kWh unrealistisch schnell wäre, während 100.000 Wh = 100 kWh
    für einen neuen Zähler realistisch ist.
    """
    if value is None:
        return None
    try:
        val = float(value)
        # Entscheide anhand des größten Wertes ob Wh oder kWh
        max_val = max(all_values) if all_values else val
        if max_val > 100_000:
            # Wahrscheinlich Wh → zu kWh konvertieren
            return round(val / 1000.0, 3)
        else:
            # Wahrscheinlich bereits kWh
            return round(val, 3)
    except (ValueError, TypeError):
        return None


@register_connector
class TasmotaSMLConnector(DeviceConnector):
    """Connector für Tasmota-basierte Smart-Meter-Reader (SML/OBIS)."""

    def info(self) -> ConnectorInfo:
        return ConnectorInfo(
            id="tasmota_sml",
            name="Tasmota Smart Meter (SML)",
            hersteller="Tasmota (ESP8266/ESP32)",
            beschreibung=(
                "Verbindung zu Tasmota-basierten Smart-Meter-Readern mit "
                "IR-Lesekopf. Liest kumulative Zählerstände (Netzbezug und "
                "Einspeisung) direkt vom Hauptstromzähler via SML/OBIS aus. "
                "Funktioniert mit allen deutschen Smart Metern die SML unterstützen."
            ),
            anleitung=(
                "1. IP-Adresse des Tasmota-Geräts im lokalen Netzwerk ermitteln\n"
                "2. Prüfen ob die Tasmota-Weboberfläche erreichbar ist: http://<IP>/\n"
                "3. Das SML-Skript muss konfiguriert sein (Scripting → Edit Script)\n"
                "4. Benutzername und Passwort nur eingeben falls in Tasmota gesetzt\n"
                "5. Der Connector erkennt OBIS-Codes 1.8.0 (Bezug) und 2.8.0 (Einspeisung)"
            ),
            getestet=True,
        )

    async def test_connection(
        self, host: str, username: str, password: str
    ) -> ConnectionTestResult:
        """Testet die Verbindung zum Tasmota Smart Meter Reader."""
        base_url = f"http://{host}"

        try:
            auth = None
            if username and password:
                auth = aiohttp.BasicAuth(username, password)

            async with aiohttp.ClientSession(auth=auth) as session:
                # Alle Status-Daten abrufen
                data = await _fetch_json(session, f"{base_url}/cm?cmnd=Status%200")
                if not data:
                    return ConnectionTestResult(
                        erfolg=False,
                        fehler=f"Keine Antwort von {host}. Ist die IP korrekt und das Tasmota-Gerät erreichbar?",
                    )

                if data.get("_auth_error"):
                    return ConnectionTestResult(
                        erfolg=False,
                        fehler="Authentifizierung erforderlich. Bitte Benutzername und Passwort eingeben.",
                    )

                # Geräteinfo extrahieren
                status = data.get("Status", {})
                geraet_name = status.get("DeviceName") or status.get("Topic") or f"Tasmota ({host})"

                firmware_info = data.get("StatusFWR", {})
                firmware = firmware_info.get("Version")
                hardware = firmware_info.get("Hardware", "ESP")

                net_info = data.get("StatusNET", {})
                hostname = net_info.get("Hostname")

                # Sensor-Daten suchen
                status_sns = data.get("StatusSNS", {})
                meter_result = _find_meter_data(status_sns)

                if not meter_result:
                    return ConnectionTestResult(
                        erfolg=False,
                        fehler=(
                            "Tasmota-Gerät erreichbar, aber keine Smart-Meter-Daten gefunden. "
                            "Ist ein SML-Skript mit OBIS-Codes (1.8.0, 2.8.0) konfiguriert?"
                        ),
                    )

                meter_name, meter_data = meter_result
                sensoren: list[str] = []

                # Seriennummer des Stromzählers
                seriennummer = meter_data.get(OBIS_SERIENNUMMER)
                if seriennummer:
                    sensoren.append(f"Zähler-Nr: {seriennummer}")

                # Energiewerte sammeln für Einheitenheuristik
                energy_values = []
                bezug_raw = meter_data.get(OBIS_NETZBEZUG)
                einsp_raw = meter_data.get(OBIS_EINSPEISUNG)
                if bezug_raw is not None:
                    try:
                        energy_values.append(float(bezug_raw))
                    except (ValueError, TypeError):
                        pass
                if einsp_raw is not None:
                    try:
                        energy_values.append(float(einsp_raw))
                    except (ValueError, TypeError):
                        pass

                # Kumulative Zähler
                bezug_kwh = _to_kwh(bezug_raw, energy_values)
                einsp_kwh = _to_kwh(einsp_raw, energy_values)

                if bezug_kwh is not None:
                    sensoren.append(f"Netzbezug (1.8.0): {bezug_kwh:.1f} kWh")
                if einsp_kwh is not None:
                    sensoren.append(f"Einspeisung (2.8.0): {einsp_kwh:.1f} kWh")

                # Momentanleistung
                leistung = meter_data.get(OBIS_LEISTUNG)
                if leistung is not None:
                    try:
                        p = float(leistung)
                        richtung = "Export" if p < 0 else "Bezug"
                        sensoren.append(f"Leistung: {abs(p):.0f} W ({richtung})")
                    except (ValueError, TypeError):
                        pass

                # Phasenleistungen
                for obis, label in [
                    (OBIS_LEISTUNG_L1, "L1"),
                    (OBIS_LEISTUNG_L2, "L2"),
                    (OBIS_LEISTUNG_L3, "L3"),
                ]:
                    val = meter_data.get(obis)
                    if val is not None:
                        try:
                            sensoren.append(f"  {label}: {float(val):.0f} W")
                        except (ValueError, TypeError):
                            pass

                # Einheitenhinweis
                max_energy = max(energy_values) if energy_values else 0
                if max_energy > 100_000:
                    sensoren.append("(Werte in Wh erkannt → kWh konvertiert)")
                else:
                    sensoren.append("(Werte vermutlich in kWh)")

                snapshot = MeterSnapshot(
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    netzbezug_kwh=bezug_kwh,
                    einspeisung_kwh=einsp_kwh,
                )

                return ConnectionTestResult(
                    erfolg=True,
                    geraet_name=geraet_name,
                    geraet_typ=f"Tasmota SML ({hardware})",
                    seriennummer=str(seriennummer) if seriennummer else None,
                    firmware=firmware,
                    verfuegbare_sensoren=sensoren,
                    aktuelle_werte=snapshot,
                )

        except aiohttp.ClientError as e:
            return ConnectionTestResult(
                erfolg=False,
                fehler=f"Verbindungsfehler: {str(e)}",
            )
        except Exception as e:
            logger.exception("Fehler beim Tasmota-Verbindungstest")
            return ConnectionTestResult(
                erfolg=False,
                fehler=f"Unerwarteter Fehler: {str(e)}",
            )

    async def read_meters(
        self, host: str, username: str, password: str
    ) -> MeterSnapshot:
        """Liest aktuelle kumulative Zählerstände vom Tasmota Smart Meter Reader."""
        base_url = f"http://{host}"
        now = datetime.now(timezone.utc).isoformat()

        auth = None
        if username and password:
            auth = aiohttp.BasicAuth(username, password)

        async with aiohttp.ClientSession(auth=auth) as session:
            data = await _fetch_json(session, f"{base_url}/cm?cmnd=Status%208")
            if not data:
                return MeterSnapshot(timestamp=now)

            status_sns = data.get("StatusSNS", {})
            meter_result = _find_meter_data(status_sns)
            if not meter_result:
                return MeterSnapshot(timestamp=now)

            _, meter_data = meter_result

            # Energiewerte für Heuristik
            energy_values = []
            for key in [OBIS_NETZBEZUG, OBIS_EINSPEISUNG]:
                val = meter_data.get(key)
                if val is not None:
                    try:
                        energy_values.append(float(val))
                    except (ValueError, TypeError):
                        pass

            return MeterSnapshot(
                timestamp=now,
                netzbezug_kwh=_to_kwh(meter_data.get(OBIS_NETZBEZUG), energy_values),
                einspeisung_kwh=_to_kwh(meter_data.get(OBIS_EINSPEISUNG), energy_values),
            )
