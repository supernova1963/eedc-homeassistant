"""
Snapshot-Reaggregator — Vorschau und Range-Resnap.

`get_reaggregate_preview` liefert die alt/neu-Tabelle für einen Tag (DB-Werte
vs. HA-Statistics-Werte) ohne zu schreiben. `resnap_anlage_range` schreibt
Snapshots im Range neu (Recovery nach Service-Bugfixes).

Beides sind Repair-Pfade — sie werden vom Reparatur-Endpoint
(`POST /reaggregate-tag`) und vom Diagnostics-Modul aufgerufen, nicht vom
regulären Scheduler.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import and_, select, func as _sql_func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.sensor_snapshot import SensorSnapshot
from backend.models.mqtt_energy_snapshot import MqttEnergySnapshot
from backend.services.ha_statistics_service import get_ha_statistics_service

from backend.services.snapshot.keys import (
    BASIS_ZAEHLER_FELDER,
    KUMULATIVE_COUNTER_FELDER,
    _categorize_counter,
    _mqtt_key_to_sensor_key,
)
from backend.services.snapshot.writer import snapshot_anlage, snapshot_anlage_5min

logger = logging.getLogger(__name__)


async def get_reaggregate_preview(
    db: AsyncSession,
    anlage,
    investitionen_by_id: dict,
    datum: date,
) -> dict:
    """
    Liefert die alt/neu-Vergleichstabelle für den geplanten Reload eines Tages.

    Liest pro Counter:
      - 25 Stunden-Boundaries (Vortag 23:00 .. Folgetag 00:00):
        `alt` = aktueller DB-Snapshot, `neu` = HA-Statistics-Wert (sum)
      - 24 Slot-Deltas: alt = snap_alt[h] - snap_alt[h-1],
                       neu = snap_neu[h] - snap_neu[h-1]
      - Tagesumme pro Kategorie alt/neu

    **Schreibt nichts.** Der Aufrufer entscheidet (UI-Bestätigung), ob danach
    `reaggregate_tag` aufgerufen wird, das die `neu`-Werte tatsächlich in die
    DB schreibt.

    Returns:
        {
          "boundaries": [
            {"sensor_key": str, "kategorie": str|None, "zeitpunkt": datetime,
             "alt_kwh": float|None, "neu_kwh": float|None},
            ...  # 25 × n_counter
          ],
          "slot_deltas": [
            {"stunde": int, "kategorie": str,
             "alt_kwh": float|None, "neu_kwh": float|None},
            ...  # 24 × n_kategorie
          ],
          "tagesumme_alt": {kategorie: float|None},
          "tagesumme_neu": {kategorie: float|None},
          "ha_verfuegbar": bool,
          "counter_tagesdelta": [
            {"feld": str, "alt": int|None, "neu": int|None},
            ...  # je KUMULATIVE_COUNTER_FELDER-Eintrag mit gemapptem Sensor;
                 # Werte über alle Investitionen pro Feld summiert.
          ],
        }
    """
    sensor_mapping = anlage.sensor_mapping or {}

    # Counter-Entries sammeln (gleiche Logik wie get_hourly_kwh_by_category)
    eintraege: list[tuple[str, Optional[str], str]] = []
    seen_keys: set[str] = set()

    basis = sensor_mapping.get("basis", {}) or {}
    for feld in BASIS_ZAEHLER_FELDER:
        config = basis.get(feld)
        if isinstance(config, dict) and config.get("strategie") == "sensor":
            eid = config.get("sensor_id")
            if eid:
                kat = _categorize_counter(feld, None, None)
                if kat:
                    sk = f"basis:{feld}"
                    eintraege.append((sk, eid, kat))
                    seen_keys.add(sk)

    investitionen_map = sensor_mapping.get("investitionen", {}) or {}
    for inv_id_str, inv_data in investitionen_map.items():
        if not isinstance(inv_data, dict):
            continue
        inv = investitionen_by_id.get(inv_id_str) or investitionen_by_id.get(str(inv_id_str))
        if inv is None:
            continue
        felder = inv_data.get("felder", {}) or {}
        for feld, config in felder.items():
            if not isinstance(config, dict) or config.get("strategie") != "sensor":
                continue
            eid = config.get("sensor_id")
            if not eid:
                continue
            kat = _categorize_counter(feld, inv.typ, inv.parameter)
            if kat:
                sk = f"inv:{inv_id_str}:{feld}"
                eintraege.append((sk, eid, kat))
                seen_keys.add(sk)

    cutoff = datetime.now() - timedelta(days=7)
    mqtt_keys_result = await db.execute(
        select(MqttEnergySnapshot.energy_key)
        .where(
            and_(
                MqttEnergySnapshot.anlage_id == anlage.id,
                MqttEnergySnapshot.timestamp >= cutoff,
            )
        )
        .distinct()
    )
    for (mqtt_key,) in mqtt_keys_result.all():
        sk = _mqtt_key_to_sensor_key(mqtt_key)
        if not sk or sk in seen_keys:
            continue
        if sk.startswith("basis:"):
            feld = sk.split(":", 1)[1]
            kat = _categorize_counter(feld, None, None)
        elif sk.startswith("inv:"):
            _, inv_id, feld = sk.split(":", 2)
            inv = investitionen_by_id.get(inv_id) or investitionen_by_id.get(str(inv_id))
            if inv is None:
                continue
            kat = _categorize_counter(feld, inv.typ, inv.parameter)
        else:
            continue
        if kat:
            eintraege.append((sk, None, kat))
            seen_keys.add(sk)

    ha_svc = get_ha_statistics_service()
    ha_verfuegbar = ha_svc.is_available

    tag_0 = datetime.combine(datum, datetime.min.time())
    boundaries: list[dict] = []

    # Pro Counter, pro Stunde -1..24: alt aus DB (5min Toleranz), neu aus HA-Stats
    # h=-1 ist Vortag 23:00 (Slot-0-Boundary), h=24 ist Folgetag 00:00 (für etwaige
    # Folgetags-Slot-0-Berechnung — aber primär brauchen wir h=-1..23 für Slot 0..23).
    # Wir liefern 25 Boundaries (h=-1..23), das deckt Slot 0..23 ab.
    snap_alt: dict[str, dict[int, Optional[float]]] = {sk: {} for sk, _, _ in eintraege}
    snap_neu: dict[str, dict[int, Optional[float]]] = {sk: {} for sk, _, _ in eintraege}

    for sensor_key, entity_id, kat in eintraege:
        for h in range(-1, 24):
            zp = tag_0 + timedelta(hours=h)
            # alt: DB-Lookup (toleranz 5min)
            von = zp - timedelta(minutes=5)
            bis = zp + timedelta(minutes=5)
            abstand = _sql_func.abs(
                _sql_func.julianday(SensorSnapshot.zeitpunkt) - _sql_func.julianday(zp)
            )
            r = await db.execute(
                select(SensorSnapshot.wert_kwh).where(
                    and_(
                        SensorSnapshot.anlage_id == anlage.id,
                        SensorSnapshot.sensor_key == sensor_key,
                        SensorSnapshot.zeitpunkt >= von,
                        SensorSnapshot.zeitpunkt <= bis,
                    )
                ).order_by(abstand.asc()).limit(1)
            )
            alt = r.scalar_one_or_none()
            snap_alt[sensor_key][h] = alt

            # neu: HA-Stats lookup (kein Schreiben)
            neu = None
            if entity_id and ha_verfuegbar:
                neu = ha_svc.get_value_at(entity_id, zp, toleranz_minuten=10)
            snap_neu[sensor_key][h] = neu

            boundaries.append({
                "sensor_key": sensor_key,
                "kategorie": kat,
                "zeitpunkt": zp,
                "alt_kwh": alt,
                "neu_kwh": neu,
            })

    # Slot-Deltas aggregieren pro Kategorie (alt und neu getrennt)
    slot_deltas: list[dict] = []
    tagesumme_alt: dict[str, Optional[float]] = {}
    tagesumme_neu: dict[str, Optional[float]] = {}

    # alle Kategorien sammeln, die in eintraege vorkommen
    alle_kategorien = sorted({kat for _, _, kat in eintraege})

    for h in range(24):
        per_kat_alt: dict[str, Optional[float]] = {}
        per_kat_neu: dict[str, Optional[float]] = {}
        for sensor_key, _eid, kat in eintraege:
            # alt-Delta
            a0 = snap_alt[sensor_key].get(h - 1)
            a1 = snap_alt[sensor_key].get(h)
            if a0 is not None and a1 is not None:
                d = a1 - a0
                if d < -0.01 and a1 < 0.5 and a0 > 0.5:
                    d = max(0.0, a1)  # Tagesreset-Schutz analog get_hourly_kwh_by_category
                if d >= -0.01:
                    d = max(0.0, d)
                    per_kat_alt[kat] = (per_kat_alt.get(kat) or 0.0) + d
            # neu-Delta
            n0 = snap_neu[sensor_key].get(h - 1)
            n1 = snap_neu[sensor_key].get(h)
            if n0 is not None and n1 is not None:
                d = n1 - n0
                if d < -0.01 and n1 < 0.5 and n0 > 0.5:
                    d = max(0.0, n1)
                if d >= -0.01:
                    d = max(0.0, d)
                    per_kat_neu[kat] = (per_kat_neu.get(kat) or 0.0) + d
        for kat in alle_kategorien:
            slot_deltas.append({
                "stunde": h,
                "kategorie": kat,
                "alt_kwh": per_kat_alt.get(kat),
                "neu_kwh": per_kat_neu.get(kat),
            })
            if per_kat_alt.get(kat) is not None:
                tagesumme_alt[kat] = (tagesumme_alt.get(kat) or 0.0) + per_kat_alt[kat]
            if per_kat_neu.get(kat) is not None:
                tagesumme_neu[kat] = (tagesumme_neu.get(kat) or 0.0) + per_kat_neu[kat]

    # ── Counter-Tagesdelta (KUMULATIVE_COUNTER_FELDER) ────────────────────────
    # Reine Counter (z. B. wp_starts_anzahl) tauchen in den kWh-Slots/Tagesummen
    # nicht auf — sie haben keine Energiefluss-Kategorie. Damit der Tester vor
    # einem Reload trotzdem sieht, ob sich die Tageszahl ändert (Befund Bug B
    # MartyBr 2026-05-07: Verdopplung nach Recycle blieb in der Vorschau
    # unsichtbar), liefern wir hier die Tagesgesamt-Werte alt vs. neu.
    # Boundary: snap(Tag 00:00) und snap(Folgetag 00:00), summiert über alle
    # Investitionen pro Feld (analog zur Spalte „WP-Starts" in der Tagestabelle).
    investitionen_map = sensor_mapping.get("investitionen", {}) or {}
    tag_ende = tag_0 + timedelta(days=1)
    counter_alt_per_feld: dict[str, int] = {}
    counter_neu_per_feld: dict[str, int] = {}

    async def _db_snap_at(sensor_key: str, zp: datetime) -> Optional[float]:
        von = zp - timedelta(minutes=5)
        bis = zp + timedelta(minutes=5)
        abstand = _sql_func.abs(
            _sql_func.julianday(SensorSnapshot.zeitpunkt) - _sql_func.julianday(zp)
        )
        r = await db.execute(
            select(SensorSnapshot.wert_kwh).where(
                and_(
                    SensorSnapshot.anlage_id == anlage.id,
                    SensorSnapshot.sensor_key == sensor_key,
                    SensorSnapshot.zeitpunkt >= von,
                    SensorSnapshot.zeitpunkt <= bis,
                )
            ).order_by(abstand.asc()).limit(1)
        )
        return r.scalar_one_or_none()

    for inv_id_str, inv_data in investitionen_map.items():
        if not isinstance(inv_data, dict):
            continue
        inv = investitionen_by_id.get(inv_id_str) or investitionen_by_id.get(str(inv_id_str))
        if inv is None:
            continue
        counter_felder = KUMULATIVE_COUNTER_FELDER.get(inv.typ, ())
        if not counter_felder:
            continue
        felder = inv_data.get("felder", {}) or {}
        for feld in counter_felder:
            config = felder.get(feld)
            if not isinstance(config, dict) or config.get("strategie") != "sensor":
                continue
            entity_id = config.get("sensor_id")
            if not entity_id:
                continue
            sensor_key = f"inv:{inv_id_str}:{feld}"

            alt_start = await _db_snap_at(sensor_key, tag_0)
            alt_ende = await _db_snap_at(sensor_key, tag_ende)
            if alt_start is not None and alt_ende is not None:
                d = alt_ende - alt_start
                if d >= 0:
                    counter_alt_per_feld[feld] = counter_alt_per_feld.get(feld, 0) + int(round(d))

            if ha_verfuegbar:
                neu_start = ha_svc.get_value_at(entity_id, tag_0, toleranz_minuten=10)
                neu_ende = ha_svc.get_value_at(entity_id, tag_ende, toleranz_minuten=10)
                if neu_start is not None and neu_ende is not None:
                    d = neu_ende - neu_start
                    if d >= 0:
                        counter_neu_per_feld[feld] = counter_neu_per_feld.get(feld, 0) + int(round(d))

    counter_tagesdelta: list[dict] = []
    for feld in sorted(set(counter_alt_per_feld) | set(counter_neu_per_feld)):
        counter_tagesdelta.append({
            "feld": feld,
            "alt": counter_alt_per_feld.get(feld),
            "neu": counter_neu_per_feld.get(feld),
        })

    return {
        "boundaries": boundaries,
        "slot_deltas": slot_deltas,
        "tagesumme_alt": tagesumme_alt,
        "tagesumme_neu": tagesumme_neu,
        "ha_verfuegbar": ha_verfuegbar,
        "counter_tagesdelta": counter_tagesdelta,
    }


async def resnap_anlage_range(
    db: AsyncSession,
    anlage,
    von: datetime,
    bis: datetime,
    include_5min: bool = True,
) -> dict[str, int]:
    """
    Schreibt SensorSnapshots für [von, bis) neu — sowohl hourly :00 als auch
    5-Min Sub-Hour-Slots. Existierende Slots werden überschrieben.

    Zweck: Validierung/Recovery nach Service-Bugfixes wie dem off-by-one in
    `get_value_at` (Befund 2026-05-01). Liest die korrigierten Werte aus HA
    Statistics und überschreibt die Snapshots der letzten Tage in einem
    Rutsch — leichter als pro Tag manuell `reaggregate-tag` zu klicken.

    Args:
        db: Async Session
        anlage: Anlage-Objekt
        von: Start (inklusiv, wird auf volle Stunde abgerundet)
        bis: Ende (exklusiv, wird auf volle Stunde abgerundet)
        include_5min: Wenn True, auch 5-Min-Slots resnappen (nur sinnvoll
            für die letzten ~10–14 Tage, dann ist HA short_term gefüllt).

    Returns:
        {"hourly": <Anzahl>, "5min": <Anzahl>, "stunden": <#h>, "slots_5min": <#5m>}
    """
    von_h = von.replace(minute=0, second=0, microsecond=0)
    bis_h = bis.replace(minute=0, second=0, microsecond=0)

    hourly_count = 0
    fivemin_count = 0
    stunden = 0
    slots_5min = 0

    # Erwartete Schrittzahl + Start-Log (Klausnn #190: bisher schweigender
    # Hänger bei großen Ranges, weil _nichts_ geloggt wurde bis das Aggregat
    # dranknam).
    stunden_total = max(0, int((bis_h - von_h).total_seconds() // 3600))
    log_every = max(1, stunden_total // 20)  # ~5 %-Schritte
    logger.info(
        f"Resnap Anlage {anlage.id} startet: {stunden_total} Stunden "
        f"[{von_h.isoformat()} → {bis_h.isoformat()}], 5min={include_5min}"
    )

    # 1) Stündliche Slots (überschreiben via _upsert in snapshot_anlage).
    # force_resnap=True: HA-None löscht den vorhandenen Snapshot (prä-#184-
    # Spike-Recovery, Befund Rainer 2026-05-03). aggregate_day sieht danach
    # eine echte Lücke statt einer falschen Lifetime-Differenz.
    zp = von_h
    while zp < bis_h:
        try:
            n = await snapshot_anlage(db, anlage, zeitpunkt=zp, force_resnap=True)
            hourly_count += n
        except Exception as e:
            logger.warning(
                f"Resnap hourly Anlage {anlage.id} {zp}: {type(e).__name__}: {e}"
            )
        stunden += 1
        if stunden % log_every == 0:
            logger.info(
                f"Resnap Anlage {anlage.id}: {stunden}/{stunden_total} Stunden "
                f"({100 * stunden // stunden_total}%), {hourly_count} Snapshots geschrieben"
            )
        zp += timedelta(hours=1)

    # 2) 5-Min-Slots (force=True, da Off-by-one-Fix sonst nicht überschreibt)
    if include_5min:
        zp = von_h
        while zp < bis_h:
            # Nur Sub-Hour-Slots :05..:55 (volle Stunden bereits durch Schritt 1)
            for minute in (5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55):
                slot = zp.replace(minute=minute)
                if slot >= bis:
                    break
                try:
                    n = await snapshot_anlage_5min(
                        db, anlage, zeitpunkt=slot, force=True, force_resnap=True
                    )
                    fivemin_count += n
                except Exception as e:
                    logger.debug(
                        f"Resnap 5min Anlage {anlage.id} {slot}: {type(e).__name__}: {e}"
                    )
                slots_5min += 1
            zp += timedelta(hours=1)

    await db.commit()
    logger.info(
        f"Resnap Anlage {anlage.id} [{von_h.isoformat()} → {bis_h.isoformat()}]: "
        f"{hourly_count} hourly / {fivemin_count} 5min snapshots geschrieben"
    )
    return {
        "hourly": hourly_count,
        "5min": fivemin_count,
        "stunden": stunden,
        "slots_5min": slots_5min,
    }
