"""
Datenquellen-V4 B7-5c — Materialisierung der MQTT-Richtungen (Import/Export).

Bis hierher vermengte `mqtt_inbound.enabled` **Verbindung** und **Import-
Richtung** in einem Schalter; der Export hing allein an ENV
(`MQTT_AUTO_PUBLISH`/`MQTT_ENABLED`). Beide Richtungen sind jetzt eigene,
gleichrangige Einstellungen — mit einer neuen Default-Regel (Gernot-Weiche
2026-07-16): **liegt eine HA-Verbindung vor (Supervisor ODER HA Connector), ist
der Import per Default AUS** (HA-Sensoren sind der Weg, MQTT-Import ist der
Ausnahmefall — F2 „HA-Sensor Vorrang, MQTT = Notstopfen").

**Wozu diese Migration:** ohne sie würde der neue Default rückwirkend greifen.
Ein Bestands-Add-on mit `MQTT_ENABLED=true` und OHNE DB-Eintrag importiert heute
über MQTT (`main.py::_load_mqtt_config` fiel auf ENV zurück und startete den
Subscriber) — der Default-Flip hätte es **stumm verstummen** lassen. Dieselbe
Falle wie bei B8; dieselbe Lösung (Gernot: „erst Migration, dann Default
kippen"): wir schreiben für jede BESTEHENDE Installation die HEUTE effektive
Richtung explizit hin. Danach erreicht nur noch eine Neuinstallation den
Default — dort kann niemand etwas verlieren.

**Additiv + idempotent:** ein bereits expliziter Eintrag wird nie überschrieben.
**Kein HTTP/Blocking** ([[feedback_migration_startup_kein_http]]): liest nur
Settings + ENV.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from backend.core.config import settings as env_settings
from backend.models.settings import Settings as SettingsModel
from backend.services.mqtt_broker_settings import (
    MQTT_EXPORT_SETTINGS_KEY,
    MQTT_SETTINGS_KEY,
)

logger = logging.getLogger(__name__)


async def _hole(db: AsyncSession, key: str):
    return (
        await db.execute(select(SettingsModel).where(SettingsModel.key == key))
    ).scalar_one_or_none()


async def migriere_mqtt_richtungen(db: AsyncSession) -> None:
    """Schreibt Import- und Export-Richtung explizit fest (nur wo unbestimmt)."""
    geaendert: list[str] = []

    # ── Import ──────────────────────────────────────────────────────────────
    # Heute effektiv = expliziter DB-Wert, sonst ENV `mqtt_enabled` (so entschied
    # `_load_mqtt_config` über den Subscriber-Start). Nur wenn NICHTS explizit
    # gesetzt ist, frieren wir den ENV-Stand ein — sonst bliebe er dem neuen
    # Default ausgeliefert.
    inbound = await _hole(db, MQTT_SETTINGS_KEY)
    if inbound is None or not inbound.value:
        # Kein Eintrag: nur festschreiben, wenn ENV heute tatsächlich importiert.
        # Sonst nichts anlegen — eine frische Installation soll den neuen Default
        # bekommen, nicht einen eingefrorenen „aus"-Zustand.
        if env_settings.mqtt_enabled:
            db.add(
                SettingsModel(
                    key=MQTT_SETTINGS_KEY,
                    value={
                        "enabled": True,
                        "host": env_settings.mqtt_host,
                        "port": env_settings.mqtt_port,
                        "username": env_settings.mqtt_username,
                        "password": env_settings.mqtt_password,
                    },
                )
            )
            geaendert.append("Import=an (aus Add-on-/ENV-Optionen übernommen)")
    elif "enabled" not in inbound.value:
        # Eintrag ohne Richtungs-Aussage (z. B. nur Zugangsdaten): der Subscriber
        # startete bei fehlendem `enabled` NICHT (`mqtt_cfg.get("enabled")`).
        inbound.value = {**inbound.value, "enabled": False}
        flag_modified(inbound, "value")
        geaendert.append("Import=aus (Eintrag ohne Richtung)")

    # ── Export ──────────────────────────────────────────────────────────────
    # Heute effektiv = die alte Scheduler-Bedingung `mqtt_auto_publish or
    # mqtt_enabled` (M-B-Entscheid Gernot 2026-06-10).
    #
    # ⚠️ Nur festschreiben, wenn der Export heute WIRKLICH läuft — symmetrisch zum
    # Import oben. Eine erste Fassung schrieb IMMER (also auch `enabled=False` bei
    # einer frischen Standalone-Installation) und hätte damit den neuen Default
    # („HA-Verbindung + Broker → Export an", Gernot: Publishen ist Pflicht) für
    # jede Neuinstallation dauerhaft tot geschrieben: expliziter Eintrag schlägt
    # Default. Nichts zu erhalten → nichts schreiben.
    export = await _hole(db, MQTT_EXPORT_SETTINGS_KEY)
    if export is None or not export.value or "enabled" not in export.value:
        if bool(env_settings.mqtt_auto_publish or env_settings.mqtt_enabled):
            if export is not None:
                export.value = {**(export.value or {}), "enabled": True}
                flag_modified(export, "value")
            else:
                db.add(SettingsModel(key=MQTT_EXPORT_SETTINGS_KEY, value={"enabled": True}))
            geaendert.append("Export=an (aus Add-on-/ENV-Optionen übernommen)")

    if geaendert:
        await db.commit()
        logger.info("MQTT-Richtungen materialisiert: %s", "; ".join(geaendert))
