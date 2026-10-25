"""
MQTT Live History Service.

Periodische Snapshots der MQTT Live-Leistungsdaten (W) in SQLite,
um den Tagesverlauf-Chart im Standalone-MQTT-Modus zu ermöglichen.

Snapshots: alle 5 Minuten via Scheduler.
Retention: 15 Tage.

**Betriebsmodus (HA-Bauform §9, Standalone-Gleichstand S1, 25.10.2026).** Zusätzlich je Gerät mit
MQTT-Modus eine Zeile je Kanon-Modus des Fensters, ``inv:<id>:betriebsmodus:<modus>``, Wert = Anteil des
Fensters (0–1) aus der Haltezeit im Inbound-Cache (``MqttInboundCache.modus_anteile_abschliessen``) — kein
Punktwert. **Nur bei lebender Verbindung** (``cache.verbunden``, E-SG-9): ein toter Broker liefert keine
Zeile statt eines eingefrorenen Modus. Jede Zeile trägt ``ts_unix`` (E-SG-8); daraus verdichtet der
Stundenlauf die Betriebsart-Mitschrift (``kanal/schreiber._betriebsart_mitschrift_mqtt``). Der Tagesverlauf
liest nur benannte Leistungs-Keys und sieht die Modus-Zeilen nicht.

**Mittelwerte (HA-Bauform §9, Standalone-Gleichstand S2, G3).** Je Gerät die Live-Keys aus
``kanal/katalog.mittelwert_live_keys(typ, parameter)`` (W · °C · %, Innengeräte-Kopien; ohne Preis), auf
Anlagen-Ebene die Basis-Live-Felder: eine Zeile je Key mit ``value_w`` = **zeitgewichtetes Mittel des
5-Minuten-Fensters** aus dem Integrator des Inbound-Cache (``MqttInboundCache.mittel_abschliessen``), ``min``/``max``
= Extrema des Fensters — kein Punktwert mehr. Daraus verdichtet der Stundenlauf die Mittelwert-Mitschrift
(``kanal/schreiber._mean_mitschrift``); der Tagesverlauf zeigt damit 5-Minuten-Mittel statt Momentanwerten.
``strompreis_ct`` bleibt als Momentanwert im Snapshot, **nur** für den Tagesverlauf — kein Kanal (G7). Wie die
Modus-Zeilen entstehen alle Zeilen **nur bei lebender Verbindung** (E-SG-9).
"""

import logging
import time
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database import get_session
from backend.models.anlage import Anlage
from backend.models.investition import Investition
from backend.models.mqtt_live_snapshot import MqttLiveSnapshot
from backend.services.kanal.katalog import mittelwert_live_keys
from backend.services.mqtt_inbound_service import get_mqtt_inbound_service

logger = logging.getLogger(__name__)

# Basis-Keys, die als Momentanwert gesnapshoted werden — nur für den Tagesverlauf, kein Mitschrift-Kanal (G7).
_BASIS_EXTRA_KEYS = {
    "strompreis_ct",  # Dynamischer Strompreis in ct/kWh
}
# ⭐ Die Leistungs-Keys (`einspeisung_w` … `leistung_kuehlen_w`, N-439) standen bis S2 hier als zwei feste Mengen;
# seit HA-Bauform §9 kommen sie mit den übrigen Mittelwert-Feldern aus EINER Katalog-Funktion
# (`mittelwert_live_keys`) — die vier WP-Leistungen, die PV-, Speicher-, Wallbox- und E-Auto-Leistung und die
# Basis-Leistungen sind darin enthalten (Probe `test_standalone_s2_mittelwert_mitschrift.py`).


def modus_zeilen(cache, valid_ids: set[int], now: datetime, jetzt_unix: float) -> list[MqttLiveSnapshot]:
    """Die Modus-Zeilen dieses Snapshots: je Gerät und Kanon-Modus der Anteil des abgeschlossenen Fensters.

    Ohne Verbindung (``cache.verbunden`` False) keine Zeile und kein Abschluss — die Fenster hat der
    Verbindungsverlust schon geleert, beim Reconnect beginnen sie neu (E-SG-9).
    """
    if not getattr(cache, "verbunden", False):
        return []
    rows: list[MqttLiveSnapshot] = []
    for anlage_id, geraete in cache.modus_anteile_abschliessen(jetzt_unix).items():
        if anlage_id not in valid_ids:
            continue
        for inv_id, anteile in geraete.items():
            for modus, anteil in sorted(anteile.items()):
                rows.append(MqttLiveSnapshot(
                    anlage_id=anlage_id,
                    timestamp=now,
                    component_key=f"inv:{inv_id}:betriebsmodus:{modus}",
                    value_w=float(anteil),
                    ts_unix=int(jetzt_unix),
                ))
    return rows


def _zeile(anlage_id: int, now: datetime, component_key: str, wert: float, ts_unix: int,
           minimum: Optional[float] = None, maximum: Optional[float] = None) -> MqttLiveSnapshot:
    return MqttLiveSnapshot(anlage_id=anlage_id, timestamp=now, component_key=component_key, value_w=wert,
                            ts_unix=ts_unix, min=minimum, max=maximum)


def mittel_zeilen(cache, geraete: dict[int, dict[str, dict[str, str]]], now: datetime,
                  jetzt_unix: float) -> list[MqttLiveSnapshot]:
    """Die Mittelwert-Zeilen dieses Snapshots (G3): je Mittelwert-Key das Mittel des abgeschlossenen Fensters.

    ``geraete`` = ``{anlage_id: {inv_id: mittelwert_live_keys(typ, parameter)}}`` der Anlagen in der DB; die
    Basis-Keys kommen aus ``mittelwert_live_keys(None)``. Ein Key außerhalb davon (fremdes Topic, unbekanntes Gerät,
    Preis) bekommt hier keine Zeile. Ohne Verbindung keine Zeile und kein Abschluss (E-SG-9).
    """
    if not getattr(cache, "verbunden", False):
        return []
    basis_keys = mittelwert_live_keys(None)
    ts_unix = int(jetzt_unix)
    rows: list[MqttLiveSnapshot] = []
    for anlage_id, fenster in cache.mittel_abschliessen(jetzt_unix).items():
        inv_keys = geraete.get(anlage_id)
        if inv_keys is None:
            continue
        for key, (mittel, lo, hi) in sorted(fenster["basis"].items()):
            if key in basis_keys:
                rows.append(_zeile(anlage_id, now, f"basis:{key}", mittel, ts_unix, lo, hi))
        for inv_id, werte in sorted(fenster["inv"].items()):
            erlaubt = inv_keys.get(inv_id) or {}
            for key, (mittel, lo, hi) in sorted(werte.items()):
                if key in erlaubt:
                    rows.append(_zeile(anlage_id, now, f"inv:{inv_id}:{key}", mittel, ts_unix, lo, hi))
    return rows


def preis_zeilen(cache, valid_ids: set[int], now: datetime, jetzt_unix: float) -> list[MqttLiveSnapshot]:
    """``strompreis_ct`` als Momentanwert — nur für den Tagesverlauf, kein Mitschrift-Kanal (G7); nur bei Verbindung."""
    if not getattr(cache, "verbunden", False):
        return []
    rows: list[MqttLiveSnapshot] = []
    for anlage_id, daten in cache.get_all_live_raw().items():
        if anlage_id not in valid_ids:
            continue
        for key, (value, _ts) in daten.get("basis", {}).items():
            if key in _BASIS_EXTRA_KEYS:
                rows.append(_zeile(anlage_id, now, f"basis:{key}", value, int(jetzt_unix)))
    return rows


async def _geraete_keys() -> dict[int, dict[str, dict[str, str]]]:
    """``{anlage_id: {inv_id: {key: einheit}}}`` aller Anlagen in der DB (verhindert FK-Fehler und fremde Keys)."""
    async with get_session() as session:
        anlagen = {row[0] for row in (await session.execute(select(Anlage.id))).all()}
        invs = (await session.execute(
            select(Investition.id, Investition.anlage_id, Investition.typ, Investition.parameter))).all()
    out: dict[int, dict[str, dict[str, str]]] = {aid: {} for aid in anlagen}
    for inv_id, anlage_id, typ, parameter in invs:
        if anlage_id in out:
            out[anlage_id][str(inv_id)] = mittelwert_live_keys(typ, parameter if isinstance(parameter, dict) else None)
    return out


async def snapshot_live_cache() -> int:
    """
    Snapshots der MQTT-Live-Werte in die DB: Mittelwerte des 5-Minuten-Fensters, Modus-Anteile, Preis.

    Returns:
        Anzahl geschriebener Snapshot-Einträge.
    """
    mqtt_svc = get_mqtt_inbound_service()
    if not mqtt_svc:
        return 0

    if not mqtt_svc.cache.get_all_live_raw():
        return 0

    geraete = await _geraete_keys()
    valid_ids = set(geraete)

    now = datetime.now()
    jetzt_unix = time.time()
    count = 0
    rows = mittel_zeilen(mqtt_svc.cache, geraete, now, jetzt_unix)
    rows.extend(preis_zeilen(mqtt_svc.cache, valid_ids, now, jetzt_unix))
    rows.extend(modus_zeilen(mqtt_svc.cache, valid_ids, now, jetzt_unix))

    if not rows:
        return 0

    async with get_session() as session:
        session.add_all(rows)
        await session.commit()
        count = len(rows)

    logger.debug("MQTT Live Snapshot: %d Einträge geschrieben", count)
    return count


async def cleanup_old_snapshots(retention_days: int = 15) -> int:
    """
    Löscht Snapshots älter als retention_days.

    Returns:
        Anzahl gelöschter Einträge.
    """
    cutoff = datetime.now() - timedelta(days=retention_days)

    async with get_session() as session:
        result = await session.execute(
            delete(MqttLiveSnapshot).where(MqttLiveSnapshot.timestamp < cutoff)
        )
        await session.commit()
        deleted = result.rowcount

    if deleted > 0:
        logger.info("MQTT Live Cleanup: %d alte Snapshots gelöscht", deleted)
    return deleted


async def get_snapshots_for_range(
    anlage_id: int, start: datetime, end: datetime, db: AsyncSession
) -> list[MqttLiveSnapshot]:
    """
    Lädt alle Power-Snapshots für einen Zeitraum.

    Args:
        start: Startzeit (inklusiv)
        end: Endzeit (exklusiv)

    Returns:
        Liste aller MqttLiveSnapshot-Einträge im Zeitraum.
    """
    result = await db.execute(
        select(MqttLiveSnapshot)
        .where(
            MqttLiveSnapshot.anlage_id == anlage_id,
            MqttLiveSnapshot.timestamp >= start,
            MqttLiveSnapshot.timestamp < end,
        )
        .order_by(MqttLiveSnapshot.timestamp)
    )
    return list(result.scalars().all())
