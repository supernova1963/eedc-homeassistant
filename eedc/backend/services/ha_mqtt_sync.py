"""
HA MQTT Sync Service.

Single Source of Truth für den MQTT-Outbound-Pfad (eedc-Ergebnisse → Home
Assistant). Bündelt die Broker-Konfigurations-Auflösung und das Publizieren der
Anlage-Sensoren, das zuvor in `scheduler.mqtt_auto_publish_job` und der
manuellen `/ha/export/mqtt/publish`-Route dupliziert war (#655).
"""

import os
from typing import Optional, Any

from backend.services.mqtt_client import MQTTClient, MQTTConfig
from backend.services.mqtt_broker_settings import resolve_broker_config


def resolve_mqtt_config(
    host: Optional[str] = None,
    port: Optional[int] = None,
    username: Optional[str] = None,
    password: Optional[str] = None,
) -> MQTTConfig:
    """Löst die MQTT-Broker-Konfiguration konsistent auf.

    Pro Feld: expliziter Override → Umgebungsvariable → kanonischer Default.

    Wichtig (#655): Ein leeres Config-Objekt aus dem Frontend (alle Felder None)
    fällt damit auf die ENV-Werte zurück. Vorher zog die manuelle Publish-Route
    den Pydantic-Default `core-mosquitto` und zielte so auf einen anderen Broker
    als der ENV-basierte Auto-Publish — ein Broker-Mismatch, der „erfolgreich
    publiziert, aber in HA nichts sichtbar" verursachte.
    """
    return MQTTConfig(
        host=host or os.environ.get("MQTT_HOST", "core-mosquitto"),
        port=port or int(os.environ.get("MQTT_PORT", "1883")),
        username=username if username is not None else (os.environ.get("MQTT_USER") or None),
        password=password if password is not None else (os.environ.get("MQTT_PASSWORD") or None),
    )


def _get_mqtt_config_from_env() -> MQTTConfig:
    """Lädt MQTT-Konfiguration aus Umgebungsvariablen."""
    return resolve_mqtt_config()


async def publish_anlage_sensors(
    db,
    anlage,
    mqtt_config: Optional[MQTTConfig] = None,
) -> dict:
    """Berechnet + publiziert alle HA-Export-Sensoren einer Anlage via MQTT Discovery.

    Der eine Outbound-Pfad für Auto-Publish (Scheduler) UND die manuelle Route.
    Beide meldeten zuvor „erfolg=True, 0 Sensoren" über den nicht existenten Key
    `published` — hier liefern wir die realen `success`/`failed`-Zahlen, damit
    Logs/Activity die Wahrheit zeigen.

    Returns:
        dict mit:
          available: bool   — aiomqtt verfügbar
          no_data: bool     — keine Sensoren (keine Monatsdaten)
          total/success/failed: int
          errors: list[str] — Stichprobe der Fehlergründe (für aussagekräftige Logs)
    """
    # Lazy-Import: die beiden Rechner liegen im Route-Modul; ein Top-Level-
    # Import erzeugte einen Zyklus (die Route importiert diesen Service).
    from backend.api.routes.ha_export import (
        calculate_anlage_sensors,
        calculate_investition_sensors,
        _load_emob_pool_ctx,
    )

    # B7-5: Broker aus der EINEN Wahrheit (DB-Broker-Block → ENV → Default) statt
    # nur ENV — Export und Inbound/Gateway teilen sich denselben Broker (§2g, #655).
    client = MQTTClient(mqtt_config or await resolve_broker_config(db))
    if not client.is_available:
        return {"available": False, "no_data": False, "total": 0, "success": 0, "failed": 0, "errors": []}

    sensor_values = await calculate_anlage_sensors(db, anlage)
    if not sensor_values:
        return {"available": True, "no_data": True, "total": 0, "success": 0, "failed": 0, "errors": []}

    result = await client.publish_all_sensors(sensor_values, anlage.id, anlage.anlagenname)
    gesamt = dict(result)
    gesamt.setdefault("total", len(sensor_values))

    # ── Die Geräte-Sensoren, und warum sie hier bis 2026-08-27 fehlten ────────
    #
    # ⛔ **Gemessen am 27.08.:** Dieser Pfad ist der EINZIGE MQTT-Publisher, und
    # er kannte nur `calculate_anlage_sensors` (39 Sensoren). Alles, was je
    # GERÄT entsteht — 6 Wärmepumpen-, 4 E-Auto- und 4 Investitions-Sensoren je
    # Komponente — existierte ausschließlich im REST-Export. Für eine Add-on-
    # Installation, die über MQTT-Discovery angebunden ist, gab es sie nicht.
    #
    # ⭐ **Der Apparat dafür war vollständig gebaut und wurde nie gerufen:**
    # `publish_all_sensors` nimmt seit jeher `investition_id`/`investition_name`
    # und legt darunter ein eigenes HA-Gerät an (`mqtt_client.py:146-149`).
    # Dieselbe Klasse wie N-333 (`get_zustand_states_batch`, null Aufrufer) —
    # eine gebaute Hälfte ohne Anschluss.
    #
    # ⚠ **`docs/SENSOR-REFERENZ.md` sagt es dem Anwender seit v4.0 zu:**
    # „Zusätzlich erscheinen **pro Komponente** … eigene Sensoren … jeweils
    # unter einem eigenen HA-Gerät." Der Anschluss macht die Zusage wahr; er
    # erfindet sie nicht.
    #
    # ⚠ **Sichtbare Folge:** In HA erscheinen bei bestehenden Installationen
    # erstmals Geräte-Entitäten. Das ist ein Zuwachs, kein Umbau — bestehende
    # Entitäten und ihre Langzeitstatistik bleiben unberührt.
    from backend.models.investition import Investition
    from backend.models.strompreis import Strompreis
    from sqlalchemy import select

    inv_result = await db.execute(
        select(Investition).where(Investition.anlage_id == anlage.id)
    )
    investitionen = list(inv_result.scalars().all())
    if investitionen:
        preis_result = await db.execute(
            select(Strompreis)
            .where(Strompreis.anlage_id == anlage.id)
            .order_by(Strompreis.gueltig_ab.desc())
            .limit(1)
        )
        strompreis = preis_result.scalar_one_or_none()
        emob_ctx = await _load_emob_pool_ctx(db, investitionen)

        from backend.services.betriebsmodus_live import lade_betriebsmodus_live
        modus_map = await lade_betriebsmodus_live(db, anlage)

        for inv in investitionen:
            inv_values = await calculate_investition_sensors(
                db, inv, strompreis, emob_ctx, modus_map
            )
            if not inv_values:
                continue
            inv_result_pub = await client.publish_all_sensors(
                inv_values, anlage.id, anlage.anlagenname, inv.id, inv.bezeichnung
            )
            for schluessel in ("total", "success", "failed"):
                gesamt[schluessel] = gesamt.get(schluessel, 0) + inv_result_pub.get(schluessel, 0)
            # Fehlergründe bleiben eine Stichprobe (wie im Anlagen-Zweig) —
            # ein Log, das jeden Fehler einzeln nennt, ist bei 100 Sensoren
            # keins mehr.
            for fehler in inv_result_pub.get("errors", []):
                if len(gesamt.setdefault("errors", [])) < 3:
                    gesamt["errors"].append(fehler)

    return {
        "available": True,
        "no_data": False,
        "total": gesamt.get("total", len(sensor_values)),
        "success": gesamt.get("success", 0),
        "failed": gesamt.get("failed", 0),
        "errors": gesamt.get("errors", []),
    }


class HAMqttSyncService:
    """Publiziert EEDC-Ergebnisse nach HA via MQTT."""

    def __init__(self, mqtt_client: Optional[MQTTClient] = None):
        # B7-5: kein Client-Cache mehr. Der Broker kommt jetzt aus den DB-Settings
        # und kann sich zur Laufzeit ändern (Broker-Block) — ein im Konstruktor
        # gebauter Client würde den alten Broker festhalten (das Singleton lebt bis
        # zum Neustart). Injizierter Client (Tests) gewinnt weiterhin.
        self._injected = mqtt_client

    async def _client(self) -> MQTTClient:
        """Broker frisch auflösen: DB-Broker-Block → ENV → Default."""
        if self._injected is not None:
            return self._injected
        from backend.core.database import get_session

        async with get_session() as db:
            return MQTTClient(await resolve_broker_config(db))

    async def publish_final_month_data(
        self,
        anlage_id: int,
        jahr: int,
        monat: int,
        daten: dict[str, Any],
        einheiten: Optional[dict[str, str]] = None,
    ) -> bool:
        """
        Publiziert finale Monatsdaten auf MQTT (retained).

        Args:
            anlage_id: ID der Anlage
            jahr: Jahr
            monat: Monat
            daten: Monatsdaten
            einheiten: Größenart je Feld für die Export-Rundung (N-54)

        Returns:
            True wenn erfolgreich
        """
        client = await self._client()
        return await client.publish_monatsdaten(
            anlage_id=anlage_id,
            jahr=jahr,
            monat=monat,
            daten=daten,
            einheiten=einheiten,
        )


# Singleton-Instanz
_ha_mqtt_sync_service: Optional[HAMqttSyncService] = None


def get_ha_mqtt_sync_service() -> HAMqttSyncService:
    """Gibt die Singleton-Instanz des Services zurück."""
    global _ha_mqtt_sync_service
    if _ha_mqtt_sync_service is None:
        _ha_mqtt_sync_service = HAMqttSyncService()
    return _ha_mqtt_sync_service
