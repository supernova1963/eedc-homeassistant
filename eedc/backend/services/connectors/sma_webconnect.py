"""
SMA WebConnect Connector.

Verbindet sich über die lokale WebConnect-Schnittstelle mit SMA Wechselrichtern
(Sunny Boy, Tripower, etc.) und liest kumulative Zählerstände (kWh) aus.

Angeschlossene SMA Energy Meter werden automatisch erkannt und ausgelesen.

Nutzt die pysma-plus Bibliothek für Auth, Session-Management und Sensor-Mapping.
"""

import logging
import ssl
from datetime import datetime, timezone
from typing import Optional

import aiohttp

from .base import DeviceConnector, ConnectorInfo, MeterSnapshot, ConnectionTestResult
from .registry import register_connector

try:
    from pysmaplus.exceptions import (
        SmaAuthenticationException,
        SmaConnectionException,
        SmaReadException,
    )
except ImportError:
    SmaAuthenticationException = Exception
    SmaConnectionException = Exception
    SmaReadException = Exception

logger = logging.getLogger(__name__)

# Sensor-Mapping: pysma-plus Sensor-Name → EEDC-Feld
# WebConnect-Sensoren haben stabile .name Attribute (z.B. "total_yield")
# Reihenfolge = Priorität (erster verfügbarer Sensor gewinnt)
SENSOR_MAPPING: dict[str, list[str]] = {
    "pv_erzeugung_kwh": ["total_yield", "pv_gen_meter"],
    "einspeisung_kwh": ["metering_total_yield"],
    "netzbezug_kwh": ["metering_total_absorbed"],
    "batterie_ladung_kwh": ["battery_charge_total"],
    "batterie_entladung_kwh": ["battery_discharge_total"],
}


def _create_ssl_context() -> ssl.SSLContext:
    """Erstellt SSL-Context der Self-Signed Certs akzeptiert (lokales Netzwerk)."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


@register_connector
class SMAWebConnectConnector(DeviceConnector):
    """Connector für SMA WebConnect Geräte (Sunny Boy, Tripower, etc.)."""

    def info(self) -> ConnectorInfo:
        return ConnectorInfo(
            id="sma_webconnect",
            name="SMA WebConnect (Sunny Boy / Tripower)",
            hersteller="SMA",
            beschreibung=(
                "Direkte Verbindung zum SMA Wechselrichter über die lokale "
                "WebConnect-Schnittstelle. Liest kumulative Zählerstände "
                "(PV-Erzeugung, Einspeisung, Netzbezug, Batterie) direkt vom Gerät aus. "
                "Angeschlossene SMA Energy Meter werden automatisch erkannt."
            ),
            anleitung=(
                "1. IP-Adresse des Wechselrichters im lokalen Netzwerk ermitteln\n"
                "   (z.B. über Router-Oberfläche oder SMA Sunny Portal)\n"
                "2. Benutzername: 'user' (Standard-Benutzer) oder 'installer' (Installateur)\n"
                "3. Passwort: Das bei der Inbetriebnahme vergebene Geräte-Passwort\n"
                "   (max. 12 Zeichen bei WebConnect)\n"
                "4. Verbindung testen → Geräteinfo und aktuelle Zählerstände werden angezeigt\n"
                "5. Falls ein SMA Energy Meter angeschlossen ist, werden dessen Sensoren\n"
                "   automatisch erkannt und mit ausgelesen\n"
                "6. Connector einrichten → Zählerstände werden gespeichert"
            ),
        )

    async def test_connection(
        self, host: str, username: str, password: str
    ) -> ConnectionTestResult:
        """Testet Verbindung zum WebConnect-Gerät und gibt Geräteinfo + aktuelle Werte zurück."""
        try:
            import pysmaplus
        except ImportError:
            return ConnectionTestResult(
                erfolg=False,
                fehler="pysma-plus Bibliothek nicht installiert. Bitte 'pip install pysma-plus' ausführen.",
            )

        url = f"https://{host}"
        ssl_ctx = _create_ssl_context()
        connector = aiohttp.TCPConnector(ssl=ssl_ctx)

        try:
            async with aiohttp.ClientSession(connector=connector) as session:
                try:
                    device = pysmaplus.getDevice(
                        session, url, password, groupuser=username, accessmethod="webconnect"
                    )
                except KeyError:
                    return ConnectionTestResult(
                        erfolg=False,
                        fehler=f"Ungültiger Benutzername '{username}'. "
                        "Erlaubt sind 'user' oder 'installer'.",
                    )

                if device is None:
                    return ConnectionTestResult(
                        erfolg=False,
                        fehler=f"Kein WebConnect-Gerät unter {url} gefunden. "
                        "Bitte IP-Adresse prüfen.",
                    )

                try:
                    await device.new_session()
                except SmaAuthenticationException:
                    return ConnectionTestResult(
                        erfolg=False,
                        fehler="Authentifizierung fehlgeschlagen. "
                        "Bitte Benutzername und Passwort prüfen. "
                        "Hinweis: Max. Sessions erreicht? Bitte kurz warten und erneut versuchen.",
                    )

                try:
                    # Geräteinfo
                    device_info = await device.device_info()
                    geraet_name = device_info.get("name")
                    geraet_typ = device_info.get("type")
                    seriennummer = device_info.get("serial")
                    firmware = device_info.get("sw_version")

                    # Sensoren abrufen (Energy Meter wird automatisch erkannt)
                    sensors = await device.get_sensors()
                    verfuegbare = [s.name for s in sensors if s.name]

                    # Aktuelle Werte lesen
                    await device.read(sensors)
                    snapshot = self._build_snapshot(sensors)

                    return ConnectionTestResult(
                        erfolg=True,
                        geraet_name=geraet_name,
                        geraet_typ=geraet_typ,
                        seriennummer=seriennummer,
                        firmware=firmware,
                        verfuegbare_sensoren=verfuegbare,
                        aktuelle_werte=snapshot,
                    )

                finally:
                    await device.close_session()

        except (aiohttp.ClientConnectorError, SmaConnectionException):
            return ConnectionTestResult(
                erfolg=False,
                fehler=f"Verbindung zu {url} fehlgeschlagen. "
                "Ist der Wechselrichter eingeschaltet und im Netzwerk erreichbar?",
            )
        except SmaAuthenticationException:
            return ConnectionTestResult(
                erfolg=False,
                fehler="Authentifizierung fehlgeschlagen. "
                "Bitte Benutzername und Passwort prüfen.",
            )
        except Exception as e:
            logger.exception(f"WebConnect Verbindungstest fehlgeschlagen: {e}")
            return ConnectionTestResult(
                erfolg=False,
                fehler=f"Verbindungsfehler: {type(e).__name__}: {str(e)}",
            )

    async def read_meters(
        self, host: str, username: str, password: str
    ) -> MeterSnapshot:
        """Liest aktuelle kumulative Zählerstände vom WebConnect-Gerät."""
        import pysmaplus

        url = f"https://{host}"
        ssl_ctx = _create_ssl_context()
        connector = aiohttp.TCPConnector(ssl=ssl_ctx)

        async with aiohttp.ClientSession(connector=connector) as session:
            device = pysmaplus.getDevice(
                session, url, password, groupuser=username, accessmethod="webconnect"
            )
            if device is None:
                raise ConnectionError(f"Kein WebConnect-Gerät unter {url} gefunden.")

            try:
                await device.new_session()
            except SmaAuthenticationException:
                raise PermissionError("Authentifizierung fehlgeschlagen.")

            try:
                sensors = await device.get_sensors()
                await device.read(sensors)
                return self._build_snapshot(sensors)
            finally:
                await device.close_session()

    def _build_snapshot(self, sensors) -> MeterSnapshot:
        """Baut MeterSnapshot aus pysma-plus WebConnect Sensor-Werten."""
        # Sensor-Werte nach Name indexieren (WebConnect nutzt .name, nicht .key)
        sensor_values: dict[str, Optional[float]] = {}
        for s in sensors:
            if s.name and s.value is not None:
                try:
                    sensor_values[s.name] = float(s.value)
                except (ValueError, TypeError):
                    pass

        # EEDC-Felder aus Sensor-Mapping befüllen
        result: dict[str, Optional[float]] = {}
        for eedc_feld, sensor_names in SENSOR_MAPPING.items():
            for name in sensor_names:
                if name in sensor_values:
                    result[eedc_feld] = round(sensor_values[name], 2)
                    break

        return MeterSnapshot(
            timestamp=datetime.now(timezone.utc).isoformat(),
            pv_erzeugung_kwh=result.get("pv_erzeugung_kwh"),
            einspeisung_kwh=result.get("einspeisung_kwh"),
            netzbezug_kwh=result.get("netzbezug_kwh"),
            batterie_ladung_kwh=result.get("batterie_ladung_kwh"),
            batterie_entladung_kwh=result.get("batterie_entladung_kwh"),
        )
