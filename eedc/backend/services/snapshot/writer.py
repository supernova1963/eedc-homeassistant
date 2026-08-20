"""
Snapshot-Schreiber.

Atomare Single-Snapshot-Operationen (`_upsert_snapshot`, `_delete_snapshot_if_exists`)
und die Job-Schicht (`snapshot_anlage`, `snapshot_anlage_5min`,
`cleanup_5min_snapshots`).

Beide Job-Funktionen lesen aus HA Long-Term Statistics (Add-on-Modus) und
ergänzen MQTT-Energy-Snapshots als Standalone-Fallback. Das Self-Healing-Read
über die zeitliche Kaskade liegt in `reader.get_snapshot()`.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import and_, delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.sensor_snapshot import SensorSnapshot
from backend.models.mqtt_energy_snapshot import MqttEnergySnapshot
from backend.services.ha_statistics_service import get_ha_statistics_service

from backend.services.snapshot.keys import (
    BASIS_ZAEHLER_FELDER,
    QUELLE_HA_ENERGY,
    QUELLE_KEINE_ENERGY,
    _is_kumulativ_feld,
    _mqtt_key_to_sensor_key,
    extract_quellen_energy,
)
from backend.services.snapshot.source import (
    SnapshotSource,
    assert_valid_source,
)

logger = logging.getLogger(__name__)


async def _stillgelegte_inv_ids(db: AsyncSession, anlage_id: int) -> set[str]:
    """IDs der Investitionen, deren Stilllegung **vorbei** ist (#377).

    Ein stillgelegtes Gerät ist ausgebaut — sein Sensor liefert nichts mehr
    oder, schlimmer, den eingefrorenen letzten Stand. Der Snapshot-Job
    iterierte bisher ausschließlich über das `sensor_mapping` und fragte ihn
    weiter ab: **Last gegen Home Assistant ohne jeden Nutzen**, stündlich, für
    immer.

    Praktisch geworden ist das mit dem Zählerwechsel (#377 §4): Der kanonische
    Weg ist *stilllegen + neu anlegen*, und danach stehen zwangsläufig zwei
    Zuordnungen im Mapping — die alte gehört einem Gerät, das es nicht mehr
    gibt.

    **Der Stilllegungstag zählt noch mit** (`< heute`, nicht `<=`): an ihm lief
    das Gerät. Dieselbe Grenze wie in `Investition.ist_aktiv_im_zeitraum`.

    ⚠ Bewusst **nur** die Stilllegung, nicht `aktiv=False`: Deaktivieren ist
    laut Modell „wie gelöscht, bis reaktiviert" — wer reaktiviert, will die
    Lücke nicht geschenkt bekommen. Wer stilllegt, bekommt kein Gerät zurück.
    """
    from datetime import date as _date

    from backend.models.investition import Investition

    heute = _date.today()
    rows = (await db.execute(
        select(Investition.id, Investition.stilllegungsdatum)
        .where(Investition.anlage_id == anlage_id)
        .where(Investition.stilllegungsdatum.isnot(None))
    )).all()
    return {str(inv_id) for inv_id, still in rows if still and still < heute}


def _build_counter_map(
    anlage, stillgelegte_inv_ids: Optional[set[str]] = None
) -> dict[str, str]:
    """
    Sammelt alle gemappten kumulativen kWh-Zähler einer Anlage.

    Returns:
        dict {sensor_key: entity_id}, z.B.:
        {
          "basis:einspeisung": "sensor.sma_total_yield",
          "basis:netzbezug":   "sensor.sma_total_absorbed",
          "inv:4:pv_erzeugung_kwh": "sensor.sma_pv_gen_meter",
          "inv:5:ladung_kwh":  "sensor.sma_battery_charge_total",
          "inv:5:entladung_kwh": "sensor.sma_battery_discharge_total",
        }

    Nur Felder mit strategie="sensor" und einer sensor_id werden aufgenommen.
    Strategien "manuell", "keine" etc. bleiben außen vor.

    Args:
        stillgelegte_inv_ids: IDs, deren Gerät nicht mehr existiert — ihre
            Zuordnungen werden übersprungen (s. `_stillgelegte_inv_ids`).
            `None` heißt „nicht gefiltert" und ist das Verhalten bis v4.0.22;
            die Bestandsproben rufen weiterhin ohne dieses Argument auf.
    """
    sensor_mapping = anlage.sensor_mapping or {}
    result: dict[str, str] = {}
    stillgelegt = stillgelegte_inv_ids or set()

    # Basis (Einspeisung/Netzbezug — die kumulativen kWh-Zähler, nicht leistung_w)
    basis = sensor_mapping.get("basis", {}) or {}
    for feld in BASIS_ZAEHLER_FELDER:
        config = basis.get(feld)
        if isinstance(config, dict) and config.get("strategie") == "sensor":
            eid = config.get("sensor_id")
            if eid:
                result[f"basis:{feld}"] = eid

    # Investitionen
    investitionen_map = sensor_mapping.get("investitionen", {}) or {}
    for inv_id_str, inv_data in investitionen_map.items():
        if not isinstance(inv_data, dict):
            continue
        if str(inv_id_str) in stillgelegt:
            continue
        felder = inv_data.get("felder", {}) or {}
        for feld, config in felder.items():
            if not isinstance(config, dict) or config.get("strategie") != "sensor":
                continue
            eid = config.get("sensor_id")
            if not eid:
                continue
            # Nur kumulative kWh-Felder (anhand Namens-Whitelist)
            # Whitelist-basiert statt per Typ, weil wir inv.typ hier nicht haben
            if _is_kumulativ_feld(feld):
                result[f"inv:{inv_id_str}:{feld}"] = eid

    # Datenquellen-V4 C2b: feld-zentrische `quellen`-Zuordnung honorieren
    # (Read-Through). Ohne Eintrag bleibt der oben aus sensor_mapping gebaute
    # HA-Zähler unverändert (Regressionsschutz). Mit Eintrag:
    #   HA   → zugeordnete Entity schreiben (Swap; bzw. Feld ERGÄNZEN, wenn im
    #          alten sensor_mapping gar kein Sensor stand — neue Fläche-Zuordnung)
    #   MQTT → aus der HA-Schreib-Map ENTFERNEN (MQTT-Step 2 deckt es)
    #   keine → aus der HA-Schreib-Map ENTFERNEN (kein Snapshot → Monatsabschluss
    #          manuell/Durchschnitt/Vorjahr, §2d)
    quellen_energy = extract_quellen_energy(anlage)
    for sensor_key, (quelle, entity_id) in quellen_energy.items():
        # Der Read-Through darf ein stillgelegtes Gerät nicht wieder
        # hereinholen — sonst wirkte der Filter oben nur für Zuordnungen aus
        # der klassischen Struktur, und ausgerechnet die neue Datenquellen-
        # Fläche liefe daran vorbei.
        if sensor_key.startswith("inv:") and sensor_key.split(":")[1] in stillgelegt:
            result.pop(sensor_key, None)
            continue
        if quelle in QUELLE_HA_ENERGY:
            if entity_id:
                result[sensor_key] = entity_id
            else:
                result.pop(sensor_key, None)
        else:  # MQTT-Quellen oder keine → HA-Schreib-Map lässt das Feld aus
            result.pop(sensor_key, None)

    return result


async def _delete_snapshot_if_exists(
    db: AsyncSession,
    anlage_id: int,
    sensor_key: str,
    zeitpunkt: datetime,
) -> bool:
    """Löscht einen vorhandenen SensorSnapshot-Eintrag (für resnap-Pfad).

    Wird verwendet, wenn HA-Statistics für einen Slot `None` liefert (z.B.
    `sum=NULL` direkt nach HA-Restart vor `recompile_statistics`) und der
    alte Eintrag in der DB sonst als korrupte Lifetime-Differenz weiter-
    propagieren würde. Ohne dieses Löschen bleibt der prä-#184-Spike
    persistent — `reaggregate-tag` heilt ihn nicht (Befund Rainer 2026-05-03).

    Returns:
        True wenn ein Eintrag gelöscht wurde, False wenn keiner existierte.
    """
    result = await db.execute(
        delete(SensorSnapshot).where(
            and_(
                SensorSnapshot.anlage_id == anlage_id,
                SensorSnapshot.sensor_key == sensor_key,
                SensorSnapshot.zeitpunkt == zeitpunkt,
            )
        )
    )
    return (result.rowcount or 0) > 0


async def _upsert_snapshot(
    db: AsyncSession,
    anlage_id: int,
    sensor_key: str,
    zeitpunkt: datetime,
    wert_kwh: float,
    *,
    quelle: str,
) -> None:
    """Upsert (insert or update) eines Snapshot-Eintrags.

    `quelle` ist Pflicht-Parameter (Etappe 3c P1) und muss aus
    `SnapshotSource`-Konstanten kommen. Bei UPDATE wird die Quelle ebenfalls
    überschrieben — wer zuletzt schreibt, prägt den Marker (für `sensor_snapshots`
    bewusst Last-Writer-Wins, weil pro Zeile nur ein Wert + Zeitpunkt existiert
    und der jüngste Schreiber den aktuellen Stand repräsentiert).
    """
    assert_valid_source(quelle)
    existing = await db.execute(
        select(SensorSnapshot).where(
            and_(
                SensorSnapshot.anlage_id == anlage_id,
                SensorSnapshot.sensor_key == sensor_key,
                SensorSnapshot.zeitpunkt == zeitpunkt,
            )
        )
    )
    row = existing.scalar_one_or_none()
    if row is not None:
        row.wert_kwh = wert_kwh
        row.quelle = quelle
    else:
        db.add(SensorSnapshot(
            anlage_id=anlage_id,
            sensor_key=sensor_key,
            zeitpunkt=zeitpunkt,
            wert_kwh=wert_kwh,
            quelle=quelle,
        ))
    await db.flush()


async def snapshot_anlage(
    db: AsyncSession,
    anlage,
    zeitpunkt: Optional[datetime] = None,
    force_resnap: bool = False,
) -> int:
    """
    Schreibt Snapshots aller verfügbaren kumulativen Zähler einer Anlage.

    Reihenfolge der Quellen:
      1. HA Statistics (für HA-gemappte sensor_id, Add-on-Modus)
      2. MQTT-Energy-Snapshot (Standalone/Docker-Modus, Fallback auf
         mqtt_energy_snapshots-Tabelle für Keys ohne HA-Sensor-ID)

    Wird vom Scheduler stündlich :05 aufgerufen, damit HA die Stunde
    bereits finalisiert hat (Latenz ~5 min).

    Args:
        db: Async Session
        anlage: Anlage-Objekt
        zeitpunkt: Zielzeitpunkt. Default: aktuelle Stunde (round down).
        force_resnap: Wenn True und HA-Statistics für einen Slot `None`
            liefert (z.B. `sum=NULL` aus prä-#184-Phase), wird der vor-
            handene Snapshot **gelöscht** statt belassen. Nur im Recovery-
            Pfad (`resnap_anlage_range`) aktiv — der reguläre :05-hourly-
            Job behält das alte Verhalten (skip), damit ein temporäres
            HA-Hänger keinen frisch geschriebenen Slot wegnimmt.

    Returns:
        Anzahl geschriebener Snapshots.
    """
    # Lokal-Import, weil reader.py von writer.py importiert (Self-Healing in
    # get_snapshot) — wir wollen keinen zirkulären Top-Level-Import.
    from backend.services.snapshot.reader import _get_mqtt_snapshot_at

    if zeitpunkt is None:
        now = datetime.now()
        zeitpunkt = now.replace(minute=0, second=0, microsecond=0)

    count = 0

    # 1. HA-gemappte Zähler (wenn sensor_mapping konfiguriert + HA verfügbar)
    # Toleranz 10 Min konsistent zu get_snapshot (Issue #145, #146): HA hourly-
    # Statistics sitzen exakt auf der Stundengrenze. Eine Abweichung > 10 min
    # bedeutet, dass HA die Zielstunde noch gar nicht finalisiert hat — dann
    # nichts schreiben (None bleibt), statt den Nachbar-Eintrag (z.B. h-1)
    # fälschlich als h zu speichern. Falscher Nachbarwert würde Slot-h = 0
    # erzeugen und Slot h+1 = 2-Stunden-Delta als Spike (Forum-Beobachtung
    # Rainer #146, gleicher Mechanismus wie #145 nur in der Job-Schicht).
    counter_map = _build_counter_map(anlage, await _stillgelegte_inv_ids(db, anlage.id))
    ha_svc = get_ha_statistics_service()
    if counter_map and ha_svc.is_available:
        for sensor_key, entity_id in counter_map.items():
            # `get_value_at` ist synchrones SQLAlchemy gegen die Recorder-DB.
            # Direkt im `async def` aufgerufen hielt es den Event-Loop von eedc
            # an — je Zähler, je Lauf. Bei einer Anlage mit zwanzig Zählern
            # stand die Oberfläche für die Dauer aller zwanzig Abfragen. Der
            # Job darf langsam sein, er darf nur nichts blockieren.
            wert = await asyncio.to_thread(
                ha_svc.get_value_at, entity_id, zeitpunkt, toleranz_minuten=10
            )
            if wert is None:
                # Recovery-Pfad: existierenden Eintrag löschen, damit ein
                # prä-#184-Spike (sum=NULL→state-Fallback) nicht persistent
                # bleibt. aggregate_day sieht dann eine Lücke statt eines
                # falschen Wertes (Befund Rainer 2026-05-03).
                if force_resnap:
                    await _delete_snapshot_if_exists(
                        db, anlage.id, sensor_key, zeitpunkt
                    )
                continue
            await _upsert_snapshot(
                db, anlage.id, sensor_key, zeitpunkt, wert,
                quelle=SnapshotSource.HA_STATISTICS,
            )
            count += 1

    # 2. MQTT-Energy-Snapshots (Standalone-Modus, ergänzt/deckt HA-Gap ab)
    # Liest alle in den letzten 60 Min für diese Anlage gesehenen MQTT-Keys
    # und schreibt deren nächstgelegenen Wert um zeitpunkt.
    seit = zeitpunkt - timedelta(minutes=60)
    bis = zeitpunkt + timedelta(minutes=60)
    mqtt_keys_result = await db.execute(
        select(MqttEnergySnapshot.energy_key).where(
            and_(
                MqttEnergySnapshot.anlage_id == anlage.id,
                MqttEnergySnapshot.timestamp >= seit,
                MqttEnergySnapshot.timestamp <= bis,
            )
        ).distinct()
    )
    # C2b: Felder, die per `quellen` explizit HA oder „keine" zugeordnet sind,
    # dürfen NICHT aus dem MQTT-Backup geschrieben werden — strikt eine Quelle
    # (§2d). MQTT-zugeordnete Felder (und Felder ganz ohne Eintrag) laufen wie
    # bisher durch. Verhalten für nicht-zugeordnete Felder bleibt unverändert.
    quellen_energy = extract_quellen_energy(anlage)
    for (mqtt_key,) in mqtt_keys_result.all():
        sensor_key = _mqtt_key_to_sensor_key(mqtt_key)
        if not sensor_key:
            continue
        # C2b: HA- oder keine-zugeordnetes Feld → MQTT-Backup schreibt es nicht.
        zuord = quellen_energy.get(sensor_key)
        if zuord and (zuord[0] in QUELLE_HA_ENERGY or zuord[0] == QUELLE_KEINE_ENERGY):
            continue
        # Sensor-Snapshot existiert schon aus HA-Pfad? Dann überspringen
        existing = await db.execute(
            select(SensorSnapshot.id).where(
                and_(
                    SensorSnapshot.anlage_id == anlage.id,
                    SensorSnapshot.sensor_key == sensor_key,
                    SensorSnapshot.zeitpunkt == zeitpunkt,
                )
            )
        )
        if existing.scalar_one_or_none() is not None:
            continue
        wert = await _get_mqtt_snapshot_at(db, anlage.id, mqtt_key, zeitpunkt, toleranz_minuten=10)
        if wert is None:
            continue
        await _upsert_snapshot(
            db, anlage.id, sensor_key, zeitpunkt, wert,
            quelle=SnapshotSource.MQTT_INBOUND,
        )
        count += 1

    return count


async def snapshot_anlage_5min(
    db: AsyncSession,
    anlage,
    zeitpunkt: datetime,
    force: bool = False,
    force_resnap: bool = False,
) -> int:
    """
    Schreibt 5-Min-Counter-Snapshots aus HA short_term_statistics für eine
    Anlage (Phase 1, Live-Snapshot-5-Min).

    Im Gegensatz zu snapshot_anlage() (hourly aus statistics):
      - liest aus statistics_short_term (5-Min-Slots, Retention ~10–14 Tage)
      - überspringt Slots wo bereits ein Snapshot existiert (idempotent,
        kein Überschreiben des hourly :05-Werts), außer `force=True`
      - kein MQTT-Pfad (Standalone-Anlagen profitieren erst, wenn
        mqtt_energy_history_service ähnliche 5-Min-Granularität liefert —
        eigener Refactor, siehe Konzept §1 Abgrenzung)

    Args:
        db: Async Session
        anlage: Anlage-Objekt
        zeitpunkt: Ziel-Slot, typisch floor(now, 5min)
        force: Wenn True, bestehende Slots überschreiben (für Resnap nach
            Service-Bugfixes, siehe resnap_anlage_range).

    Returns:
        Anzahl geschriebener Snapshots.
    """
    counter_map = _build_counter_map(anlage, await _stillgelegte_inv_ids(db, anlage.id))
    if not counter_map:
        return 0

    ha_svc = get_ha_statistics_service()
    if not ha_svc.is_available:
        return 0

    count = 0
    for sensor_key, entity_id in counter_map.items():
        if not force:
            # Idempotenz: nicht überschreiben wenn Slot schon belegt ist
            # (z.B. der :05-hourly-Snapshot, oder vorheriger 5-Min-Lauf).
            existing = await db.execute(
                select(SensorSnapshot.id).where(
                    and_(
                        SensorSnapshot.anlage_id == anlage.id,
                        SensorSnapshot.sensor_key == sensor_key,
                        SensorSnapshot.zeitpunkt == zeitpunkt,
                    )
                )
            )
            if existing.scalar_one_or_none() is not None:
                continue
        # Toleranz 3 Min: HA short_term schreibt exakt auf :00, :05, :10, ...
        # 3 Min ist eng genug um keinen Nachbar-Slot zu treffen, weit genug
        # für Latenz-Jitter.
        # Wie im hourly-Pfad: synchrone DB-Abfrage gehört nicht in den
        # Event-Loop. Dieser Job läuft alle fünf Minuten.
        wert = await asyncio.to_thread(
            ha_svc.get_value_at,
            entity_id, zeitpunkt, toleranz_minuten=3, short_term=True,
        )
        if wert is None:
            if force_resnap:
                await _delete_snapshot_if_exists(
                    db, anlage.id, sensor_key, zeitpunkt
                )
            continue
        await _upsert_snapshot(
            db, anlage.id, sensor_key, zeitpunkt, wert,
            quelle=SnapshotSource.HA_STATISTICS,
        )
        count += 1

    return count


async def cleanup_5min_snapshots(
    db: AsyncSession,
    keep_hours: int = 24,
) -> int:
    """
    Löscht Sub-Hour-Snapshots (zeitpunkt.minute != 0) älter als keep_hours.

    Variante A aus dem Konzept: hourly-Snapshots (:00) bleiben dauerhaft,
    Sub-Hour-Slots werden nach 24h gelöscht. Damit wächst sensor_snapshots
    pro Anlage nur um ~288 transiente Rows (1 Tag à 5-Min).

    Args:
        db: Async Session
        keep_hours: Sub-Hour-Slots jünger als das werden behalten (default 24h).

    Returns:
        Anzahl gelöschter Rows.
    """
    from sqlalchemy import delete, func
    cutoff = datetime.now() - timedelta(hours=keep_hours)
    # SQLite-Pfad (eedc.db ist immer SQLite, siehe core/config.py).
    # strftime('%M', zeitpunkt) liefert "00".."59" als String.
    result = await db.execute(
        delete(SensorSnapshot).where(
            and_(
                SensorSnapshot.zeitpunkt < cutoff,
                func.strftime("%M", SensorSnapshot.zeitpunkt) != "00",
            )
        )
    )
    await db.commit()
    return result.rowcount or 0
