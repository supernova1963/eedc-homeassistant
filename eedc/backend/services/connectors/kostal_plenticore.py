"""
Kostal Plenticore / PIKO IQ Connector.

Verbindet sich über die lokale REST API mit Kostal Wechselrichtern
und liest kumulative Zählerstände (kWh) aus.

Endpoints:
- POST /api/v1/auth/start + /api/v1/auth/finish → SCRAM-SHA256 Auth
- POST /api/v1/processdata → Kumulative Zählerstände

Besonderheiten:
- SCRAM-SHA256 Authentifizierung (PBKDF2-HMAC-SHA256)
- Standard-Benutzer: 'pvserver' (oder 'installer')
- Alle Energiewerte in Wh (werden zu kWh konvertiert)
- Session-Token verfällt nach ~2 Minuten

HINWEIS: Dieser Connector wurde anhand der HA kostal_plenticore Integration
und pykoplern-Bibliothek erstellt, aber noch nicht mit echten Wechselrichtern
verifiziert (getestet=False).
"""

import base64
import hashlib
import hmac
import logging
import os
from datetime import datetime, timezone
from typing import Optional

import aiohttp

from .base import DeviceConnector, ConnectorInfo, MeterSnapshot, ConnectionTestResult
from .registry import register_connector

logger = logging.getLogger(__name__)

# Modul und Process-Data-IDs für kumulative Zähler
MODULE_ID = "scb:statistic:EnergyFlow"
PROCESSDATA_IDS = [
    "Statistic:Yield:Total",           # PV Gesamtertrag (Wh)
    "Statistic:EnergyGrid:Total",      # Einspeisung ins Netz (Wh)
    "Statistic:EnergyHomeGrid:Total",  # Netzbezug (Wh)
    "Statistic:EnergyCharger:Total",   # Batterie-Ladung gesamt (Wh)
    "Statistic:EnergyHomeBat:Total",   # Batterie-Entladung gesamt (Wh)
]


def _wh_to_kwh(value) -> Optional[float]:
    """Konvertiert Wh zu kWh."""
    if value is None:
        return None
    try:
        return round(float(value) / 1000.0, 3)
    except (ValueError, TypeError):
        return None


async def _scram_auth(
    session: aiohttp.ClientSession, base_url: str, username: str, password: str
) -> Optional[str]:
    """Führt SCRAM-SHA256 Authentifizierung durch und gibt Session-Token zurück.

    Flow:
    1. POST /api/v1/auth/start → Challenge (nonce, salt, rounds)
    2. PBKDF2-HMAC-SHA256 Berechnung
    3. POST /api/v1/auth/finish → Token
    """
    try:
        # Schritt 1: Auth starten
        client_nonce = base64.b64encode(os.urandom(18)).decode()

        async with session.post(
            f"{base_url}/api/v1/auth/start",
            json={"username": username, "nonce": client_nonce},
            timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            if resp.status != 200:
                logger.warning("Kostal auth/start returned status %d", resp.status)
                return None
            auth_data = await resp.json(content_type=None)

        server_nonce = auth_data["nonce"]
        transaction_id = auth_data["transactionId"]
        rounds = auth_data["rounds"]
        salt = base64.b64decode(auth_data["salt"])

        # Schritt 2: PBKDF2-HMAC-SHA256 Proof berechnen
        salted_password = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), salt, rounds
        )
        client_key = hmac.new(salted_password, b"Client Key", hashlib.sha256).digest()
        stored_key = hashlib.sha256(client_key).digest()

        auth_message = f"{client_nonce},{server_nonce},{client_nonce}"
        client_signature = hmac.new(
            stored_key, auth_message.encode(), hashlib.sha256
        ).digest()
        client_proof = base64.b64encode(
            bytes(a ^ b for a, b in zip(client_key, client_signature))
        ).decode()

        # Schritt 3: Auth abschließen
        async with session.post(
            f"{base_url}/api/v1/auth/finish",
            json={"transactionId": transaction_id, "proof": client_proof},
            timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            if resp.status != 200:
                logger.warning("Kostal auth/finish returned status %d", resp.status)
                return None
            finish_data = await resp.json(content_type=None)

        return finish_data.get("token")

    except Exception as e:
        logger.warning("Kostal SCRAM auth failed: %s", e)
        return None


async def _fetch_processdata(
    session: aiohttp.ClientSession, base_url: str, token: str,
    module_id: str, processdata_ids: list[str]
) -> dict[str, float]:
    """Liest Process-Data vom Kostal Wechselrichter.

    Gibt dict mit processdata_id → Wert zurück.
    """
    result: dict[str, float] = {}

    try:
        payload = [{"moduleid": module_id, "processdataids": processdata_ids}]
        headers = {"Authorization": f"Bearer {token}"}

        async with session.post(
            f"{base_url}/api/v1/processdata",
            json=payload,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            if resp.status != 200:
                logger.warning("Kostal processdata returned status %d", resp.status)
                return result
            data = await resp.json(content_type=None)

        if isinstance(data, list):
            for module in data:
                for pd in module.get("processdata", []):
                    pd_id = pd.get("id")
                    value = pd.get("value")
                    if pd_id and value is not None:
                        result[pd_id] = float(value)

    except Exception as e:
        logger.warning("Kostal processdata request failed: %s", e)

    return result


@register_connector
class KostalPlenticoreConnector(DeviceConnector):
    """Connector für Kostal Plenticore / PIKO IQ Wechselrichter."""

    def info(self) -> ConnectorInfo:
        return ConnectorInfo(
            id="kostal_plenticore",
            name="Kostal Plenticore / PIKO IQ",
            hersteller="Kostal",
            beschreibung=(
                "Direktverbindung zu Kostal Plenticore Plus und PIKO IQ "
                "Wechselrichtern über die lokale REST API. Liest kumulative "
                "Zählerstände für PV-Erzeugung, Einspeisung, Netzbezug und "
                "Batterie aus."
            ),
            anleitung=(
                "1. IP-Adresse des Wechselrichters im lokalen Netzwerk ermitteln\n"
                "2. Benutzername: 'pvserver' (Standard-Benutzer)\n"
                "3. Passwort: Das bei der Inbetriebnahme gesetzte Passwort\n"
                "   (steht auch auf dem Typenschild des Wechselrichters)\n"
                "4. Hinweis: Die Session läuft nach ~2 Min. ab, wird automatisch erneuert"
            ),
            getestet=False,
        )

    async def test_connection(
        self, host: str, username: str, password: str
    ) -> ConnectionTestResult:
        """Testet die Verbindung zum Kostal Wechselrichter."""
        base_url = f"http://{host}"
        user = username or "pvserver"

        try:
            async with aiohttp.ClientSession() as session:
                # SCRAM-Auth
                token = await _scram_auth(session, base_url, user, password)
                if not token:
                    return ConnectionTestResult(
                        erfolg=False,
                        fehler=(
                            f"Authentifizierung bei {host} fehlgeschlagen. "
                            "Bitte Benutzername (Standard: 'pvserver') und Passwort prüfen."
                        ),
                    )

                # Process-Data lesen
                values = await _fetch_processdata(
                    session, base_url, token, MODULE_ID, PROCESSDATA_IDS
                )
                if not values:
                    return ConnectionTestResult(
                        erfolg=False,
                        fehler="Verbindung hergestellt, aber keine Prozessdaten verfügbar.",
                    )

                # Sensoren-Liste für UI
                sensoren: list[str] = []
                labels = {
                    "Statistic:Yield:Total": "PV Erzeugung",
                    "Statistic:EnergyGrid:Total": "Einspeisung",
                    "Statistic:EnergyHomeGrid:Total": "Netzbezug",
                    "Statistic:EnergyCharger:Total": "Batterie-Ladung",
                    "Statistic:EnergyHomeBat:Total": "Batterie-Entladung",
                }
                for pd_id, label in labels.items():
                    val = values.get(pd_id)
                    if val is not None:
                        sensoren.append(f"{label}: {val/1000:.1f} kWh")

                snapshot = self._build_snapshot(values)

                return ConnectionTestResult(
                    erfolg=True,
                    geraet_name=f"Kostal ({host})",
                    geraet_typ="Kostal Plenticore / PIKO IQ",
                    verfuegbare_sensoren=sensoren,
                    aktuelle_werte=snapshot,
                )

        except aiohttp.ClientError as e:
            return ConnectionTestResult(
                erfolg=False,
                fehler=f"Verbindungsfehler: {str(e)}",
            )
        except Exception as e:
            logger.exception("Fehler beim Kostal-Verbindungstest")
            return ConnectionTestResult(
                erfolg=False,
                fehler=f"Unerwarteter Fehler: {str(e)}",
            )

    async def read_meters(
        self, host: str, username: str, password: str
    ) -> MeterSnapshot:
        """Liest aktuelle kumulative Zählerstände vom Kostal Wechselrichter."""
        base_url = f"http://{host}"
        user = username or "pvserver"

        async with aiohttp.ClientSession() as session:
            token = await _scram_auth(session, base_url, user, password)
            if not token:
                raise PermissionError("Kostal Authentifizierung fehlgeschlagen.")

            values = await _fetch_processdata(
                session, base_url, token, MODULE_ID, PROCESSDATA_IDS
            )

            return self._build_snapshot(values)

    def _build_snapshot(self, values: dict[str, float]) -> MeterSnapshot:
        """Baut MeterSnapshot aus Kostal Process-Data."""
        return MeterSnapshot(
            timestamp=datetime.now(timezone.utc).isoformat(),
            pv_erzeugung_kwh=_wh_to_kwh(values.get("Statistic:Yield:Total")),
            einspeisung_kwh=_wh_to_kwh(values.get("Statistic:EnergyGrid:Total")),
            netzbezug_kwh=_wh_to_kwh(values.get("Statistic:EnergyHomeGrid:Total")),
            batterie_ladung_kwh=_wh_to_kwh(values.get("Statistic:EnergyCharger:Total")),
            batterie_entladung_kwh=_wh_to_kwh(values.get("Statistic:EnergyHomeBat:Total")),
        )
