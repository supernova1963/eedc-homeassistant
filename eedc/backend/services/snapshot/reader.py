"""
Snapshot-Reader.

Single-Snapshot-Read mit Self-Healing-Kaskade (DB → HA Statistics → MQTT-
Energy-Snapshot), Delta-Berechnung über Zeit-Range, sowie Lifetime-Counter-
Read aus drei Quellen (HA-State → HA-Statistics → jüngster Snapshot).

Reader greift auf `writer._upsert_snapshot` zurück, um neu geholte Werte
aus dem Self-Healing zu persistieren — die einseitige Abhängigkeit
reader → writer ist explizit gewollt (writer importiert nichts aus reader).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import and_, select, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.sensor_snapshot import SensorSnapshot
from backend.models.mqtt_energy_snapshot import MqttEnergySnapshot
from backend.services.ha_statistics_service import get_ha_statistics_service

from backend.services.snapshot.keys import (
    KUMULATIVE_COUNTER_FELDER,
    _sensor_key_to_mqtt_key,
)
from backend.services.snapshot.source import SnapshotSource
from backend.services.snapshot.writer import _upsert_snapshot

logger = logging.getLogger(__name__)


async def _get_mqtt_snapshot_at(
    db: AsyncSession,
    anlage_id: int,
    mqtt_key: str,
    zeitpunkt: datetime,
    toleranz_minuten: int = 10,
) -> Optional[float]:
    """
    Liest den zeitlich nächstgelegenen MqttEnergySnapshot um zeitpunkt
    (±toleranz_minuten).

    Wird als MQTT-Fallback genutzt wenn HA Statistics nicht verfügbar ist
    (Standalone/Docker-Modus ohne HA-Integration).

    Standard ±10 min (vorher ±30): MQTT-Publisher liefern Zählerstände
    typischerweise alle 1–5 min. Ein Fenster > 10 min bedeutet fast immer,
    dass der Zielzeitpunkt gar keine frische Publikation hatte — in dem Fall
    ist None + Interpolation in der aufrufenden Schicht (Issue #145) besser
    als ein weit entfernter Wert, der Stunden-Deltas verzerrt.

    Kandidaten werden nach absolutem Zeitabstand sortiert (nearest first),
    nicht nach Timestamp-Reihenfolge — damit der zeitlich passendste Wert
    gewählt wird, nicht zufällig der früheste im Fenster.
    """
    von = zeitpunkt - timedelta(minutes=toleranz_minuten)
    bis = zeitpunkt + timedelta(minutes=toleranz_minuten)
    abstand = func.abs(
        func.julianday(MqttEnergySnapshot.timestamp) - func.julianday(zeitpunkt)
    )
    result = await db.execute(
        select(MqttEnergySnapshot.value_kwh, MqttEnergySnapshot.timestamp).where(
            and_(
                MqttEnergySnapshot.anlage_id == anlage_id,
                MqttEnergySnapshot.energy_key == mqtt_key,
                MqttEnergySnapshot.timestamp >= von,
                MqttEnergySnapshot.timestamp <= bis,
            )
        ).order_by(abstand.asc()).limit(1)
    )
    row = result.first()
    return row[0] if row else None


async def get_snapshot(
    db: AsyncSession,
    anlage_id: int,
    sensor_key: str,
    sensor_id: Optional[str],
    zeitpunkt: datetime,
    toleranz_minuten: int = 5,
    ha_toleranz_minuten: int = 10,
) -> Optional[float]:
    """
    Holt den kumulativen Zählerstand zu einem bestimmten Zeitpunkt.

    Self-Healing-Reihenfolge:
      1. DB-Lookup in sensor_snapshots (±toleranz_minuten)
      2. HA Statistics via sensor_id (nur wenn sensor_id gesetzt)
      3. MqttEnergySnapshot-Fallback (Standalone-Modus, Issue #135 Blocker 2)

    Args:
        db: Async Session
        anlage_id: Anlagen-ID
        sensor_key: Stabiler Schlüssel (z.B. "inv:4:pv_erzeugung_kwh")
        sensor_id: HA Entity-ID des kumulativen Zählers; None bei MQTT-only
        zeitpunkt: Zielzeitpunkt (typisch: Stundenanfang, 00:00, 01:00 ...)
        toleranz_minuten: Max. zeitliche Abweichung bei DB-Lookup
        ha_toleranz_minuten: Max. zeitliche Abweichung bei HA-Statistics-Fallback.
            Standard 10 min: HA Statistics speichert stündliche Snapshots mit
            start_ts exakt auf der Stunde; eine Abweichung über 10 min bedeutet
            fast immer, dass der Zielzeitpunkt in HA gar keinen Eintrag hat —
            ein nearest-Lookup würde den Nachbar-Wert liefern und zu
            Stunde-Null-mit-Folge-Spike-Artefakten führen (Issue #145).

    Returns:
        Zählerstand in kWh oder None (kein Datenpunkt verfügbar).
    """
    von = zeitpunkt - timedelta(minutes=toleranz_minuten)
    bis = zeitpunkt + timedelta(minutes=toleranz_minuten)

    abstand = func.abs(
        func.julianday(SensorSnapshot.zeitpunkt) - func.julianday(zeitpunkt)
    )
    result = await db.execute(
        select(SensorSnapshot.wert_kwh).where(
            and_(
                SensorSnapshot.anlage_id == anlage_id,
                SensorSnapshot.sensor_key == sensor_key,
                SensorSnapshot.zeitpunkt >= von,
                SensorSnapshot.zeitpunkt <= bis,
            )
        ).order_by(abstand.asc()).limit(1)
    )
    row = result.scalar_one_or_none()
    if row is not None:
        return row

    # Self-Healing via HA Statistics (wenn HA-Sensor-ID bekannt)
    wert: Optional[float] = None
    quelle: Optional[str] = None
    if sensor_id:
        ha_svc = get_ha_statistics_service()
        if ha_svc.is_available:
            wert = ha_svc.get_value_at(sensor_id, zeitpunkt, ha_toleranz_minuten)
            if wert is not None:
                quelle = SnapshotSource.HA_STATISTICS

    # Fallback: MQTT-Energy-Snapshot (Standalone/Docker-Modus)
    if wert is None:
        mqtt_key = _sensor_key_to_mqtt_key(sensor_key)
        if mqtt_key:
            wert = await _get_mqtt_snapshot_at(db, anlage_id, mqtt_key, zeitpunkt)
            if wert is not None:
                # Self-Healing-Read über MQTT-Backup, wenn HA nichts lieferte —
                # konzeptionell die `live_fallback`-Quelle (siehe source.py).
                quelle = SnapshotSource.LIVE_FALLBACK

    if wert is None:
        logger.debug(
            f"Kein Wert für anlage={anlage_id} key={sensor_key} @ {zeitpunkt} "
            f"(weder HA Statistics noch MQTT-Snapshot)"
        )
        return None

    # Upsert in DB (idempotent bei parallelen Anfragen dank UniqueConstraint)
    assert quelle is not None  # eine der beiden Quellen muss gegriffen haben
    await _upsert_snapshot(db, anlage_id, sensor_key, zeitpunkt, wert, quelle=quelle)
    return wert


async def delta(
    db: AsyncSession,
    anlage_id: int,
    sensor_key: str,
    sensor_id: str,
    von: datetime,
    bis: datetime,
) -> Optional[float]:
    """
    Berechnet Zähler-Delta zwischen zwei Zeitpunkten.

    Delta = snapshot(bis) − snapshot(von). Negative Werte (Zählerreset,
    Firmware-Update) werden als None zurückgegeben, damit sie nicht als
    echter Wert durchschlagen.

    Returns:
        Delta in kWh (≥ 0) oder None.
    """
    snap_von = await get_snapshot(db, anlage_id, sensor_key, sensor_id, von)
    snap_bis = await get_snapshot(db, anlage_id, sensor_key, sensor_id, bis)
    if snap_von is None or snap_bis is None:
        return None
    d = snap_bis - snap_von
    if d < -0.01:  # Zählerreset o.ä.
        logger.warning(
            f"Negatives Delta für anlage={anlage_id} key={sensor_key} "
            f"({von} → {bis}): {d:.3f} kWh — ignoriert"
        )
        return None
    return max(0.0, round(d, 3))


async def get_counter_lifetime(
    db: AsyncSession,
    anlage,
    inv,
    feld: str,
) -> Optional[int]:
    """
    Liefert den aktuellen Lebensdauer-Stand eines kumulativen Counter-Sensors
    direkt aus der Hersteller-Quelle (z.B. WP-Kompressor-Starts).

    Read-Kaskade: HA-Live-State → HA-Statistics → jüngster SensorSnapshot.
    Keine Berechnung, keine Eichung, keine Drift-Möglichkeit — der Sensor
    selbst ist die Wahrheit. Vergleich gegen EEDC-erfasste Tagesinkremente
    erfolgt im Daten-Checker, nicht im Read-Pfad.

    Returns:
        Aktueller Counter-Stand (gerundet), oder None wenn weder Live-Read
        noch Snapshot ermittelbar.
    """
    if feld not in KUMULATIVE_COUNTER_FELDER.get(inv.typ, ()):
        return None

    sensor_mapping = anlage.sensor_mapping or {}
    inv_data = (sensor_mapping.get("investitionen", {}) or {}).get(str(inv.id))
    if not isinstance(inv_data, dict):
        return None
    config = (inv_data.get("felder", {}) or {}).get(feld)
    if not isinstance(config, dict) or config.get("strategie") != "sensor":
        return None
    entity_id = config.get("sensor_id")
    if not entity_id:
        return None

    wert: Optional[float] = None
    try:
        from backend.services.ha_state_service import get_ha_state_service
        ha_state = get_ha_state_service()
        if ha_state.is_available:
            wert = await ha_state.get_sensor_state(entity_id)
    except Exception as e:
        logger.debug(f"lifetime {feld} inv={inv.id}: ha_state Fehler: {type(e).__name__}: {e}")

    if wert is None:
        ha_svc = get_ha_statistics_service()
        if ha_svc.is_available:
            wert = ha_svc.get_value_at(entity_id, datetime.now(), toleranz_minuten=120)

    if wert is None:
        sensor_key = f"inv:{inv.id}:{feld}"
        result = await db.execute(
            select(SensorSnapshot.wert_kwh).where(
                and_(
                    SensorSnapshot.anlage_id == anlage.id,
                    SensorSnapshot.sensor_key == sensor_key,
                )
            ).order_by(SensorSnapshot.zeitpunkt.desc()).limit(1)
        )
        wert = result.scalar_one_or_none()

    if wert is None:
        return None
    return int(round(wert))
