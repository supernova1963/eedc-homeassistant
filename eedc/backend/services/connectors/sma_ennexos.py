"""
SMA ennexOS Connector.

Verbindet sich über die lokale REST-API mit SMA ennexOS-Geräten
(Tripower X, Wallbox EVC, etc.) und liest kumulative Zählerstände (kWh) aus.

Liest automatisch alle angeschlossenen Sub-Geräte (z.B. Energy Meter) aus
und aggregiert die Sensor-Werte.

Nutzt die pysma-plus Bibliothek für Auth, Token-Refresh und Sensor-Mapping.
"""

import logging
import ssl
from datetime import datetime, timezone
from typing import Optional

import aiohttp

from .base import DeviceConnector, ConnectorInfo, MeterSnapshot, ConnectionTestResult
from .registry import register_connector

try:
    from pysmaplus.exceptions import SmaAuthenticationException, SmaConnectionException
except ImportError:
    SmaAuthenticationException = Exception
    SmaConnectionException = Exception

logger = logging.getLogger(__name__)

# Sensor-Mapping: ennexOS Channel-Key → EEDC-Feld
# Reihenfolge = Priorität (erster verfügbarer Sensor gewinnt)
SENSOR_MAPPING: dict[str, list[str]] = {
    "pv_erzeugung_kwh": ["Metering.TotWhOut.Pv", "Metering.TotWhOut"],
    "einspeisung_kwh": ["Metering.GridMs.TotWhOut"],
    "netzbezug_kwh": ["Metering.GridMs.TotWhIn"],
    "batterie_ladung_kwh": ["Metering.GridMs.TotWhIn.Bat"],
    "batterie_entladung_kwh": ["Metering.GridMs.TotWhOut.Bat"],
}


def _create_ssl_context() -> ssl.SSLContext:
    """Erstellt SSL-Context der Self-Signed Certs akzeptiert (lokales Netzwerk)."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


@register_connector
class SMAennexOSConnector(DeviceConnector):
    """Connector für SMA ennexOS Geräte (Tripower X, Wallbox, etc.)."""

    def info(self) -> ConnectorInfo:
        return ConnectorInfo(
            id="sma_ennexos",
            name="SMA ennexOS (Tripower X / Wallbox)",
            hersteller="SMA",
            beschreibung=(
                "Direkte Verbindung zum SMA Gerät über die lokale ennexOS REST-API. "
                "Liest kumulative Zählerstände (PV-Erzeugung, Einspeisung, Netzbezug, Batterie) "
                "direkt vom Gerät aus. Angeschlossene Sub-Geräte wie SMA Energy Meter "
                "werden automatisch erkannt und ausgelesen."
            ),
            anleitung=(
                "1. IP-Adresse des ennexOS-Geräts im lokalen Netzwerk ermitteln\n"
                "   (z.B. über Router-Oberfläche oder SMA Sunny Portal)\n"
                "2. Benutzername: z.B. 'User' oder 'installer'\n"
                "3. Passwort: Das bei der Inbetriebnahme vergebene Geräte-Passwort\n"
                "4. Verbindung testen → Geräteinfo und aktuelle Zählerstände werden angezeigt\n"
                "5. Angeschlossene Energy Meter werden automatisch mit ausgelesen\n"
                "6. Connector einrichten → Zählerstände werden gespeichert"
            ),
        )

    async def _collect_all_sensor_values(self, device) -> tuple[
        dict[str, float], list[str], dict
    ]:
        """Liest Sensoren von allen Geräten und gibt aggregierte Werte zurück.

        Returns:
            tuple: (sensor_values, sensor_keys_mit_prefix, device_list)
        """
        device_list = await device.device_list()
        all_sensor_values: dict[str, float] = {}
        all_sensor_keys: list[str] = []

        # IGULD:SELF zuerst (höchste Priorität), dann EM:* und andere
        priority_order = []
        if "IGULD:SELF" in device_list:
            priority_order.append("IGULD:SELF")
        for did in device_list:
            if did not in ("IGULD:SELF", "Plant:1"):
                priority_order.append(did)

        for did in priority_order:
            try:
                sensors = await device.get_sensors(deviceID=did)
                await device.read(sensors, deviceID=did)
                for s in sensors:
                    if not s.key:
                        continue
                    all_sensor_keys.append(f"{did}:{s.key}")
                    if s.value is not None:
                        try:
                            val = float(s.value)
                            # Nur setzen wenn nicht schon vorhanden (Priorität)
                            if s.key not in all_sensor_values:
                                all_sensor_values[s.key] = val
                        except (ValueError, TypeError):
                            pass
            except Exception as e:
                logger.warning(f"Fehler beim Lesen von Gerät {did}: {e}")

        return all_sensor_values, all_sensor_keys, device_list

    async def test_connection(
        self, host: str, username: str, password: str
    ) -> ConnectionTestResult:
        """Testet Verbindung zum ennexOS-Gerät und gibt Geräteinfo + aktuelle Werte zurück."""
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
                device = pysmaplus.getDevice(
                    session, url, password, groupuser=username, accessmethod="ennexos"
                )
                if device is None:
                    return ConnectionTestResult(
                        erfolg=False,
                        fehler=f"Kein ennexOS-Gerät unter {url} gefunden. "
                        "Bitte IP-Adresse und Zugangsdaten prüfen.",
                    )

                try:
                    await device.new_session()
                except SmaAuthenticationException:
                    return ConnectionTestResult(
                        erfolg=False,
                        fehler="Authentifizierung fehlgeschlagen. "
                        "Bitte Benutzername und Passwort prüfen.",
                    )

                try:
                    # Alle Geräte auslesen (inkl. Energy Meter)
                    sensor_values, sensor_keys, device_list = (
                        await self._collect_all_sensor_values(device)
                    )

                    # Geräteinfo vom Hauptgerät
                    geraet_name = None
                    geraet_typ = None
                    seriennummer = None
                    firmware = None

                    if device_list:
                        first_device = next(iter(device_list.values()))
                        geraet_name = first_device.name
                        geraet_typ = first_device.type
                        seriennummer = first_device.serial
                        firmware = first_device.sw_version

                    snapshot = self._build_snapshot(sensor_values)

                    return ConnectionTestResult(
                        erfolg=True,
                        geraet_name=geraet_name,
                        geraet_typ=geraet_typ,
                        seriennummer=seriennummer,
                        firmware=firmware,
                        verfuegbare_sensoren=sensor_keys,
                        aktuelle_werte=snapshot,
                    )

                finally:
                    await device.close_session()

        except (aiohttp.ClientConnectorError, SmaConnectionException):
            return ConnectionTestResult(
                erfolg=False,
                fehler=f"Verbindung zu {url} fehlgeschlagen. "
                "Ist das Gerät eingeschaltet und im Netzwerk erreichbar?",
            )
        except SmaAuthenticationException:
            return ConnectionTestResult(
                erfolg=False,
                fehler="Authentifizierung fehlgeschlagen. "
                "Bitte Benutzername und Passwort prüfen.",
            )
        except Exception as e:
            logger.exception(f"ennexOS Verbindungstest fehlgeschlagen: {e}")
            return ConnectionTestResult(
                erfolg=False,
                fehler=f"Verbindungsfehler: {type(e).__name__}: {str(e)}",
            )

    async def read_meters(
        self, host: str, username: str, password: str
    ) -> MeterSnapshot:
        """Liest aktuelle kumulative Zählerstände vom ennexOS-Gerät."""
        import pysmaplus

        url = f"https://{host}"
        ssl_ctx = _create_ssl_context()
        connector = aiohttp.TCPConnector(ssl=ssl_ctx)

        async with aiohttp.ClientSession(connector=connector) as session:
            device = pysmaplus.getDevice(
                session, url, password, groupuser=username, accessmethod="ennexos"
            )
            if device is None:
                raise ConnectionError(f"Kein ennexOS-Gerät unter {url} gefunden.")

            try:
                await device.new_session()
            except SmaAuthenticationException:
                raise PermissionError("Authentifizierung fehlgeschlagen.")

            try:
                sensor_values, _, _ = await self._collect_all_sensor_values(device)
                return self._build_snapshot(sensor_values)
            finally:
                await device.close_session()

    def _build_snapshot(self, sensor_values: dict[str, float]) -> MeterSnapshot:
        """Baut MeterSnapshot aus aggregierten Sensor-Werten."""
        result: dict[str, Optional[float]] = {}
        for eedc_feld, sensor_keys in SENSOR_MAPPING.items():
            for key in sensor_keys:
                if key in sensor_values:
                    result[eedc_feld] = round(sensor_values[key], 2)
                    break

        return MeterSnapshot(
            timestamp=datetime.now(timezone.utc).isoformat(),
            pv_erzeugung_kwh=result.get("pv_erzeugung_kwh"),
            einspeisung_kwh=result.get("einspeisung_kwh"),
            netzbezug_kwh=result.get("netzbezug_kwh"),
            batterie_ladung_kwh=result.get("batterie_ladung_kwh"),
            batterie_entladung_kwh=result.get("batterie_entladung_kwh"),
        )
