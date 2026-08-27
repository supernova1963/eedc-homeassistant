"""
MQTT Energy History Service.

Periodische Snapshots der MQTT Energy-Cache-Werte in SQLite,
um Tagesberechnungen (heute/gestern kWh) im Standalone-MQTT-Modus
zu ermöglichen.

Snapshots: alle 5 Minuten via Scheduler.
Retention: 31 Tage.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import delete, func, select

from backend.core.berechnungen import summe_pv_bkw_kwh
from backend.core.database import get_session
from backend.models.anlage import Anlage
from backend.models.mqtt_energy_snapshot import MqttEnergySnapshot
from backend.services.mqtt_inbound_service import get_mqtt_inbound_service

logger = logging.getLogger(__name__)

# Mapping MQTT Energy Keys → Tages-Kategorien (wie HA-Pfad)
_KEY_TO_CATEGORY = {
    "pv_gesamt_kwh": "pv",
    "einspeisung_kwh": "einspeisung",
    "netzbezug_kwh": "netzbezug",
}

# Mapping MQTT Energy inv-field → Live-Key-Format (wie HA-Pfad in _get_tages_kwh)
# HA-Pfad liefert z.B. "pv_14", "batterie_15_ladung", "wallbox_12"
# MQTT-Pfad liefert "inv/14/pv_erzeugung_kwh", "inv/15/ladung_kwh", "inv/12/ladung_kwh"
# Diese Tabelle übersetzt MQTT → HA-Format, damit das Frontend identische Keys bekommt.
#
# `eigenverbrauch_kwh` stand hier bis 2026-07-31 mit dem Ziel `pv` — also auf
# DEMSELBEN Key wie die BKW-Erzeugung. Ein Balkonkraftwerk, das beide Topics
# publiziert, überschrieb damit seine eigene Erzeugung: gemessen wurden aus
# 10 kWh PV-Zuwachs und 4 kWh Eigenverbrauch die Werte `pv_7 = 4.0` und
# `pv = 4.0` — die „Heute"-Kachel zeigte den Eigenverbrauch statt der Erzeugung.
# Der Eintrag ist ersatzlos entfallen: Eigenverbrauch ist keine Erzeugung, und
# das Feld ist beim BKW ohnehin die manuell/per Import gepflegte Verfeinerung
# (SoT-Begründung im Modul-Docstring von `core/berechnungen/bkw_finanz.py`).
# Ohne Eintrag läuft der Key unverändert durch und wird von keinem Konsumenten
# aufgesammelt — still, aber nicht mehr schädlich.
#
# Die BKW-eigenen `speicher_ladung_kwh`/`speicher_entladung_kwh` stehen hier
# bewusst NICHT: der Kanon für einen BKW-Akku ist die eigene Speicher-Investition
# mit Parent Balkonkraftwerk, die über `ladung_kwh`/`entladung_kwh` (Typ
# `speicher`) läuft. Sie standen kurzzeitig hier (Paket D) und sind mit dem
# Kanon-Entscheid am selben Tag zurückgenommen worden.
_MQTT_FIELD_TO_LIVE_KEY: dict[str, dict[str, str]] = {
    # field → {typ → key_pattern}  (Pattern: {prefix}_{inv_id} wird im Code gebaut)
    "pv_erzeugung_kwh": {"pv-module": "pv", "balkonkraftwerk": "pv", "wechselrichter": "pv"},
    "ladung_kwh": {"speicher": "batterie:ladung", "wallbox": "wallbox", "e-auto": "eauto"},
    "entladung_kwh": {"speicher": "batterie:entladung"},
    "stromverbrauch_kwh": {"waermepumpe": "waermepumpe"},
    "erzeugung_kwh": {"sonstiges": "sonstige"},
    "verbrauch_sonstig_kwh": {"sonstiges": "sonstige"},
}


async def snapshot_energy_cache() -> int:
    """
    Snapshots alle aktuellen MQTT Energy-Werte in die DB.

    Returns:
        Anzahl geschriebener Snapshot-Einträge.
    """
    mqtt_svc = get_mqtt_inbound_service()
    if not mqtt_svc:
        return 0

    all_energy = mqtt_svc.cache.get_all_energy_raw()
    if not all_energy:
        return 0

    # Gültige Anlage-IDs aus DB holen (verhindert FK-Fehler bei gelöschten/fremden Anlagen)
    async with get_session() as session:
        result = await session.execute(select(Anlage.id))
        valid_ids = {row[0] for row in result.all()}

    now = datetime.now()
    count = 0

    async with get_session() as session:
        for anlage_id, cache in all_energy.items():
            if anlage_id not in valid_ids:
                logger.debug("MQTT Energy Snapshot: anlage_id=%d unbekannt, übersprungen", anlage_id)
                continue
            for key, (value, _ts) in cache.items():
                session.add(MqttEnergySnapshot(
                    anlage_id=anlage_id,
                    timestamp=now,
                    energy_key=key,
                    value_kwh=value,
                ))
                count += 1
        await session.commit()

    if count > 0:
        logger.debug("MQTT Energy Snapshot: %d Einträge geschrieben", count)
    return count


async def cleanup_old_snapshots(retention_days: int = 31) -> int:
    """
    Löscht Snapshots älter als retention_days.

    Returns:
        Anzahl gelöschter Einträge.
    """
    cutoff = datetime.now() - timedelta(days=retention_days)

    async with get_session() as session:
        result = await session.execute(
            delete(MqttEnergySnapshot).where(
                MqttEnergySnapshot.timestamp < cutoff
            )
        )
        await session.commit()
        deleted = result.rowcount
        if deleted > 0:
            logger.info("MQTT Energy Cleanup: %d alte Snapshots gelöscht", deleted)
        return deleted


async def get_tages_kwh(
    anlage_id: int, tage_zurueck: int = 0,
    inv_types: dict[str, str] | None = None,
) -> dict[str, Optional[float]]:
    """
    Berechnet Tages-kWh aus MQTT Energy Snapshots.

    Logik:
      heute (0):   current_cache_value - snapshot_midnight_today
      gestern (1): snapshot_midnight_today - snapshot_midnight_yesterday

    Args:
        inv_types: {inv_id: typ} für Key-Translation (inv/14/... → pv_14 etc.)

    Returns:
        {"pv": X, "einspeisung": Y, "netzbezug": Z, "pv_14": ..., "batterie_15_ladung": ...}
        — gleiche Keys wie HA-Pfad.
    """
    now = datetime.now()
    today_midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)

    if tage_zurueck == 0:
        # Heute: current - midnight_today (oder frühester Snapshot des Tages)
        mqtt_svc = get_mqtt_inbound_service()
        if not mqtt_svc:
            return {}
        current = mqtt_svc.cache.get_energy_data(anlage_id)
        if not current:
            return {}
        midnight_snap = await _get_closest_snapshot(anlage_id, today_midnight)
        if not midnight_snap:
            # Fallback: frühester Snapshot von heute (erster Tag nach Einrichtung)
            midnight_snap = await _get_earliest_snapshot_after(anlage_id, today_midnight)
        if not midnight_snap:
            return {}
        return _compute_deltas(current, midnight_snap, inv_types)

    else:
        # Gestern (oder weiter zurück)
        target_midnight = today_midnight - timedelta(days=tage_zurueck - 1)
        prev_midnight = target_midnight - timedelta(days=1)
        end_snap = await _get_closest_snapshot(anlage_id, target_midnight)
        start_snap = await _get_closest_snapshot(anlage_id, prev_midnight)
        if not end_snap or not start_snap:
            return {}
        return _compute_deltas(end_snap, start_snap, inv_types)


async def _get_closest_snapshot(
    anlage_id: int, target: datetime, window_minutes: int = 10
) -> Optional[dict[str, float]]:
    """
    Findet den Snapshot am nächsten zum Zielzeitpunkt.

    Sucht in einem ±window_minutes Fenster um target.
    Returns: {energy_key: value_kwh} oder None.
    """
    window_start = target - timedelta(minutes=window_minutes)
    window_end = target + timedelta(minutes=window_minutes)

    async with get_session() as session:
        # Finde den Timestamp am nächsten zum Ziel
        ts_result = await session.execute(
            select(MqttEnergySnapshot.timestamp)
            .where(
                MqttEnergySnapshot.anlage_id == anlage_id,
                MqttEnergySnapshot.timestamp >= window_start,
                MqttEnergySnapshot.timestamp <= window_end,
            )
            .order_by(
                func.abs(
                    func.julianday(MqttEnergySnapshot.timestamp)
                    - func.julianday(target)
                )
            )
            .limit(1)
        )
        closest_ts = ts_result.scalar_one_or_none()
        if closest_ts is None:
            return None

        # Alle Keys für diesen Timestamp holen
        rows = await session.execute(
            select(
                MqttEnergySnapshot.energy_key,
                MqttEnergySnapshot.value_kwh,
            ).where(
                MqttEnergySnapshot.anlage_id == anlage_id,
                MqttEnergySnapshot.timestamp == closest_ts,
            )
        )
        return {row[0]: row[1] for row in rows.all()}


async def _get_earliest_snapshot_after(
    anlage_id: int, after: datetime
) -> Optional[dict[str, float]]:
    """
    Findet den frühesten Snapshot nach einem Zeitpunkt.

    Fallback für den ersten Tag nach Einrichtung, wenn kein
    Mitternacht-Snapshot existiert.
    """
    async with get_session() as session:
        ts_result = await session.execute(
            select(MqttEnergySnapshot.timestamp)
            .where(
                MqttEnergySnapshot.anlage_id == anlage_id,
                MqttEnergySnapshot.timestamp >= after,
            )
            .order_by(MqttEnergySnapshot.timestamp.asc())
            .limit(1)
        )
        earliest_ts = ts_result.scalar_one_or_none()
        if earliest_ts is None:
            return None

        rows = await session.execute(
            select(
                MqttEnergySnapshot.energy_key,
                MqttEnergySnapshot.value_kwh,
            ).where(
                MqttEnergySnapshot.anlage_id == anlage_id,
                MqttEnergySnapshot.timestamp == earliest_ts,
            )
        )
        return {row[0]: row[1] for row in rows.all()}


def _compute_deltas(
    end: dict[str, float], start: dict[str, float],
    inv_types: dict[str, str] | None = None,
) -> dict[str, Optional[float]]:
    """
    Berechnet Deltas zwischen zwei Snapshot-Zuständen.

    Mapped MQTT Energy Keys auf die Kategorien die live_power_service erwartet.
    Behandelt Monatswechsel (negative Deltas → Counter-Reset).
    Investitions-Keys (inv/...) werden in das HA-kompatible Format übersetzt
    (z.B. inv/14/pv_erzeugung_kwh → pv_14).
    """
    result: dict[str, Optional[float]] = {}

    # Basis-Keys (pv_gesamt_kwh → pv, etc.)
    for key, category in _KEY_TO_CATEGORY.items():
        end_val = end.get(key)
        start_val = start.get(key)
        if end_val is None or start_val is None:
            continue

        delta = end_val - start_val
        # Monatswechsel: Counter wurde zurückgesetzt → end_val ist schon der Tageswert
        if delta < 0:
            delta = end_val

        result[category] = round(delta, 1)

    # Investitions-Keys (inv/{id}/{field}) → HA-kompatible Keys
    for key in end:
        if not key.startswith("inv/"):
            continue
        end_val = end.get(key)
        start_val = start.get(key)
        if end_val is None or start_val is None:
            continue

        delta = end_val - start_val
        if delta < 0:
            delta = end_val

        # Key-Translation: inv/{inv_id}/{field} → {typ_prefix}_{inv_id}
        parts = key.split("/", 2)  # ["inv", "14", "pv_erzeugung_kwh"]
        if len(parts) == 3 and inv_types:
            inv_id, field = parts[1], parts[2]
            typ = inv_types.get(inv_id)
            field_map = _MQTT_FIELD_TO_LIVE_KEY.get(field)
            if field_map and typ and typ in field_map:
                pattern = field_map[typ]
                if ":" in pattern:
                    # "batterie:ladung" → "batterie_{inv_id}_ladung"
                    prefix, suffix = pattern.split(":", 1)
                    target_key = f"{prefix}_{inv_id}_{suffix}"
                else:
                    target_key = f"{pattern}_{inv_id}"
            else:
                target_key = key  # Unbekanntes Feld: unverändert durchreichen
        else:
            target_key = key

        result[target_key] = round(delta, 2)

    # Pro-Wechselrichter-PV (pv_<id>/bkw_<id>) auf die Kategorie `pv` aggregieren —
    # analog HA-Pfad (live_history_service.py:372-383). Im MQTT-Modus liefert
    # mancher Nutzer PV nur pro Wechselrichter (inv/<id>/pv_erzeugung_kwh); ohne
    # diese Summierung blieb die „Heute"-PV-Kachel 0,0 kWh und der daraus
    # abgeleitete Eigen-/Hausverbrauch leer (Dirk-PN 2026-05-31).
    # Vorrang hat das anlagenweite Basis-Topic `pv_gesamt_kwh` (→ `pv` bereits
    # gesetzt); dann NICHT zusätzlich aus Komponenten summieren (Doppelzählung).
    # Whitelist via core/berechnungen statt Inline-Summe (ADR-001).
    if result.get("pv") is None:
        pv_summe = summe_pv_bkw_kwh(result)
        if pv_summe > 0:
            result["pv"] = round(pv_summe, 1)

    return result


# ─── Monatswerte aus den mitgeschriebenen Ständen (F-66) ────────────────────
#
# ⛔ **Ein MQTT-Energy-Topic trägt einen ZÄHLERSTAND, keine Monatsmenge.** Das
# steht so in der Topic-Registry (`mqtt_topic_registry.BASIS_ENERGY_TOPICS`:
# „Zählerstand der ins Netz eingespeisten Energie", „Kumulierter kWh-Zähler-
# stand") und war schon einmal Gegenstand einer Korrektur: das Label hieß bis
# zur Dirk-PN vom 2026-06-01 „… Monat (kWh)" und wurde als irreführend
# berichtigt. **Berichtigt wurde damals der Wortlaut, nicht die Leser.**
#
# Die Folge, gemeldet von **gruaGit** (Discussion #396, 27.08.): Der Monats-
# abschluss stellte den Lebenszählerstand neben den Monatswert und meldete elf
# Felder als „weicht ab" — 6675,3 gegen 552,75 kWh —, und daneben stand
# „Sensorwert übernehmen". Ein Klick hätte den Lebensstand als Monatsmenge
# gespeichert. In `aktueller_monat.py` war es kein Vorschlag, sondern ein
# `update`: im laufenden Monat gewann der Stand gegen den gespeicherten Wert.
#
# ⭐ **Der Stand wird deshalb hier zur Menge gemacht — an EINER Stelle, für
# beide Leser.** Die Reihe dafür gibt es längst: `snapshot/writer.py` schreibt
# die MQTT-Werte stündlich in `sensor_snapshots`, und deren Aufräumjob löscht
# nur Sub-Stunden-Slots — die vollen Stunden bleiben dauerhaft. `reader.delta`
# beantwortet damit „wie viel lief zwischen zwei Zeitpunkten", inklusive der
# beiden Fälle, in denen es keine Antwort gibt (fehlender Stand, Zählerreset).
#
# ⚠ **Was hier bewusst NICHT herauskommt:** Keys ohne kumulative Zählerreihe —
# `km_gefahren`, `ladevorgaenge`, Preisfelder. `_mqtt_key_to_sensor_key` gibt
# für sie `None`, es existiert kein Snapshot und damit keine Differenz. Sie
# fallen heraus statt roh durchgereicht zu werden: Genau ein solcher Rohwert
# war gruaGits Tachostand (13272 km gegen 1001 km im Monat). **Ein Feld ohne
# Vorschlag ist ehrlich; ein Feld mit einem Stand darin ist ein Datenverlust,
# der wie eine Messung aussieht.**


async def mqtt_monats_deltas(
    db,
    anlage_id: int,
    jahr: int,
    monat: int,
    energy_keys: list[str],
    quellen_energy: Optional[dict] = None,
    bis: Optional[datetime] = None,
) -> dict[str, float]:
    """Monatsmengen je MQTT-Energy-Key aus den mitgeschriebenen Ständen.

    Args:
        db: Async-Session (der Aufrufer hält sie bereits).
        anlage_id: Anlage.
        jahr, monat: der Monat, dessen Menge gefragt ist.
        energy_keys: Roh-Keys des Caches (``einspeisung_kwh``,
            ``inv/7/ladung_kwh`` …).
        quellen_energy: C2b-Read-Through (`extract_quellen_energy(anlage)`) —
            durchgereicht, damit ein auf „HA" oder „keine" gestelltes Feld
            nicht doch aus dem MQTT-Backup beantwortet wird (§2d).
        bis: Endzeitpunkt; Standard ist der Monatsanfang des Folgemonats. Der
            laufende Monat reicht ``datetime.now()`` durch — sonst stünde die
            Frage nach einem Stand in der Zukunft.

    Returns:
        ``{energy_key: menge_kwh}`` — **nur** für Keys mit Zählerreihe UND
        beidseitig vorhandenem Stand. Alles andere fehlt im Ergebnis; ein
        fehlender Eintrag heißt „keine Aussage", nicht „null".
    """
    from backend.services.snapshot.keys import _mqtt_key_to_sensor_key
    from backend.services.snapshot.reader import delta as snapshot_delta

    von = datetime(jahr, monat, 1)
    if bis is None:
        bis = datetime(jahr + 1, 1, 1) if monat == 12 else datetime(jahr, monat + 1, 1)
    # ⛔ Auf die volle Stunde abrunden — **die Reihe liegt auf Stundengrenzen**
    # (`snapshot/writer.py` schreibt stündlich; der Aufräumjob behält genau die
    # Slots mit `%M == "00"`). `get_snapshot` sucht in einem ±5-Minuten-Fenster.
    # Ein Aufrufer, der `datetime.now()` durchreicht, träfe damit nur in fünf von
    # sechzig Minuten einen Stand — der Vorschlag wäre zeitabhängig da oder weg.
    # ⭐ Beim Bau selbst hineingelaufen und von der Probe gefangen (27.08.): der
    # laufende Monat lieferte gar nichts, weil 09:26 keinen 09:00-Slot sieht.
    bis = bis.replace(minute=0, second=0, microsecond=0)
    if bis <= von:
        # Monatsanfang, noch keine volle Stunde vergangen — es gibt nichts zu
        # messen, und eine Null wäre eine Aussage.
        return {}

    ergebnis: dict[str, float] = {}
    for mqtt_key in energy_keys:
        sensor_key = _mqtt_key_to_sensor_key(mqtt_key)
        if not sensor_key:
            # Kein kumulativer Zähler (km, Ladevorgänge, Preise) — hier gibt es
            # nichts zu differenzieren und deshalb auch nichts zu behaupten.
            continue
        try:
            menge = await snapshot_delta(
                db, anlage_id, sensor_key,
                # MQTT-only: es gibt keine HA-Entity, und `get_snapshot`
                # verlangt das ausdrücklich nicht („None bei MQTT-only").
                None, von, bis,
                quellen_energy=quellen_energy,
            )
        except Exception:  # pragma: no cover — ein Vorschlag kippt nie die Seite
            logger.exception(
                "MQTT-Monatsdelta nicht berechenbar (anlage=%s key=%s)",
                anlage_id, mqtt_key,
            )
            continue
        if menge is not None and menge > 0:
            ergebnis[mqtt_key] = round(menge, 1)
    return ergebnis
