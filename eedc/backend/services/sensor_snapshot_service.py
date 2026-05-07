"""
Sensor Snapshot Service (Issue #135).

Führt stündliche Snapshots kumulativer Zählerstände und liefert
Zähler-Delta-basierte Energie- und Counter-Werte für aggregate_day/backfill.

Neben kWh-Energiezählern werden auch reine Counter (z.B. WP-Kompressor-Starts,
Issue #136) in derselben Tabelle abgelegt — das Wert-Feld ist generisch numerisch,
nur die Aggregations-Schicht (aggregate_day) entscheidet, ob ein Feld in die
Energie-Bilanz fließt oder als separater Tages-Counter aggregiert wird.

Self-Healing: Fehlt ein Snapshot zu einem benötigten Zeitpunkt, wird der
Wert on-demand aus HA Statistics geholt und gespeichert. Gleicher Pfad für:
- Scheduler-Ausfall (Lücke im aktuellen Tag)
- Vollbackfill historischer Tage
- Erstbefüllung nach Release

Sensor-Key-Schema:
    "basis:einspeisung", "basis:netzbezug"
    "inv:<inv_id>:<feld>"  (z.B. "inv:4:pv_erzeugung_kwh", "inv:5:ladung_kwh")
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import and_, delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.sensor_snapshot import SensorSnapshot
from backend.models.mqtt_energy_snapshot import MqttEnergySnapshot
from backend.services.ha_statistics_service import get_ha_statistics_service

logger = logging.getLogger(__name__)


# Felder die kumulative kWh-Zählerstände enthalten, pro Investitionstyp.
# Wird von _build_counter_map konsumiert.
KUMULATIVE_ZAEHLER_FELDER: dict[str, tuple[str, ...]] = {
    "pv-module": ("pv_erzeugung_kwh",),
    "balkonkraftwerk": ("pv_erzeugung_kwh",),
    "speicher": ("ladung_kwh", "entladung_kwh", "ladung_netz_kwh"),
    "waermepumpe": ("stromverbrauch_kwh", "heizenergie_kwh", "warmwasser_kwh"),
    "wallbox": ("ladung_kwh", "ladung_pv_kwh", "ladung_netz_kwh"),
    "e-auto": ("ladung_kwh", "ladung_pv_kwh", "ladung_netz_kwh", "verbrauch_kwh"),
    "sonstiges": ("verbrauch_kwh", "erzeugung_kwh"),
}

# Reine Counter (Anzahl-Zählwerte ohne kWh-Semantik, Issue #136).
# Werden vom Snapshot-Job mit erfasst (gleiches Schema, gleiche Tabelle), aber
# NICHT in die Energie-Bilanz von get_hourly_kwh_by_category einbezogen.
# Aggregation als Tages-Differenz erfolgt separat in aggregate_day.
KUMULATIVE_COUNTER_FELDER: dict[str, tuple[str, ...]] = {
    "waermepumpe": ("wp_starts_anzahl",),
}

BASIS_ZAEHLER_FELDER: tuple[str, ...] = ("einspeisung", "netzbezug")


# MQTT-Energy-Topic-Keys → sensor_snapshots.sensor_key Mapping.
# Das MQTT-Inbound nutzt flachere Keys (z.B. "inv/14/pv_erzeugung_kwh"),
# SensorSnapshot nutzt Doppelpunkt-Schema für Konsistenz mit HA-Pfad.
_MQTT_BASIS_KEYS: dict[str, str] = {
    "einspeisung_kwh": "basis:einspeisung",
    "netzbezug_kwh": "basis:netzbezug",
}


def _mqtt_key_to_sensor_key(mqtt_key: str) -> Optional[str]:
    """
    Konvertiert MQTT-Energy-Topic-Key ins SensorSnapshot.sensor_key-Schema.

    Gibt None zurück für Keys die keine kumulative kWh-Energie sind
    (ladevorgaenge, km_gefahren, speicher_ladepreis_cent etc.).
    """
    if mqtt_key in _MQTT_BASIS_KEYS:
        return _MQTT_BASIS_KEYS[mqtt_key]
    if mqtt_key.startswith("inv/"):
        parts = mqtt_key.split("/", 2)
        if len(parts) == 3:
            _, inv_id, feld = parts
            # Kumulative Energie-Felder + reine Counter (keine km_gefahren, Preise, etc.)
            alle_felder = (
                {f for felder in KUMULATIVE_ZAEHLER_FELDER.values() for f in felder}
                | {f for felder in KUMULATIVE_COUNTER_FELDER.values() for f in felder}
            )
            if feld in alle_felder:
                return f"inv:{inv_id}:{feld}"
    return None


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
    from sqlalchemy import func
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


def _sensor_key_to_mqtt_key(sensor_key: str) -> Optional[str]:
    """Umkehrung von _mqtt_key_to_sensor_key."""
    if sensor_key == "basis:einspeisung":
        return "einspeisung_kwh"
    if sensor_key == "basis:netzbezug":
        return "netzbezug_kwh"
    if sensor_key.startswith("inv:"):
        parts = sensor_key.split(":", 2)
        if len(parts) == 3:
            _, inv_id, feld = parts
            return f"inv/{inv_id}/{feld}"
    return None


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

    from sqlalchemy import func
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
    if sensor_id:
        ha_svc = get_ha_statistics_service()
        if ha_svc.is_available:
            wert = ha_svc.get_value_at(sensor_id, zeitpunkt, ha_toleranz_minuten)

    # Fallback: MQTT-Energy-Snapshot (Standalone/Docker-Modus)
    if wert is None:
        mqtt_key = _sensor_key_to_mqtt_key(sensor_key)
        if mqtt_key:
            wert = await _get_mqtt_snapshot_at(db, anlage_id, mqtt_key, zeitpunkt)

    if wert is None:
        logger.debug(
            f"Kein Wert für anlage={anlage_id} key={sensor_key} @ {zeitpunkt} "
            f"(weder HA Statistics noch MQTT-Snapshot)"
        )
        return None

    # Upsert in DB (idempotent bei parallelen Anfragen dank UniqueConstraint)
    await _upsert_snapshot(db, anlage_id, sensor_key, zeitpunkt, wert)
    return wert


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
) -> None:
    """Upsert (insert or update) eines Snapshot-Eintrags."""
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
    else:
        db.add(SensorSnapshot(
            anlage_id=anlage_id,
            sensor_key=sensor_key,
            zeitpunkt=zeitpunkt,
            wert_kwh=wert_kwh,
        ))
    await db.flush()


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


def _build_counter_map(anlage) -> dict[str, str]:
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
    """
    sensor_mapping = anlage.sensor_mapping or {}
    result: dict[str, str] = {}

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

    return result


def _is_kumulativ_feld(feld_name: str) -> bool:
    """Prüft ob ein Feld-Name ein kumulativer Zähler ist (Energie oder Counter)."""
    alle = (
        {f for felder in KUMULATIVE_ZAEHLER_FELDER.values() for f in felder}
        | {f for felder in KUMULATIVE_COUNTER_FELDER.values() for f in felder}
    )
    return feld_name in alle


def _categorize_counter(
    feld: str,
    inv_typ: Optional[str],
    parameter: Optional[dict],
) -> Optional[str]:
    """
    Ordnet ein gemapptes Zähler-Feld einer Energiefluss-Kategorie zu.

    Rückgabewerte werden in aggregate_day für die Summenbildung pro
    Stunde genutzt:
        "pv", "einspeisung", "netzbezug",
        "ladung_batterie", "entladung_batterie",
        "ladung_wallbox", "verbrauch_wp",
        "verbrauch_eauto",
        "erzeugung_sonstiges", "verbrauch_sonstiges"
    """
    if inv_typ is None:  # basis
        if feld == "einspeisung":
            return "einspeisung"
        if feld == "netzbezug":
            return "netzbezug"
        return None

    if inv_typ in ("pv-module", "balkonkraftwerk") and feld == "pv_erzeugung_kwh":
        return "pv"
    if inv_typ == "speicher":
        if feld == "ladung_kwh":
            return "ladung_batterie"
        if feld == "entladung_kwh":
            return "entladung_batterie"
    if inv_typ == "waermepumpe" and feld == "stromverbrauch_kwh":
        return "verbrauch_wp"
    if inv_typ == "wallbox" and feld == "ladung_kwh":
        return "ladung_wallbox"
    if inv_typ == "e-auto" and feld in ("verbrauch_kwh", "ladung_kwh"):
        return "verbrauch_eauto"
    if inv_typ == "sonstiges":
        kategorie = (parameter or {}).get("kategorie", "verbraucher") if isinstance(parameter, dict) else "verbraucher"
        if feld == "erzeugung_kwh" or (feld == "verbrauch_kwh" and kategorie == "erzeuger"):
            return "erzeugung_sonstiges"
        if feld == "verbrauch_kwh":
            return "verbrauch_sonstiges"
    return None


def _fill_gaps_linear(snaps_per_hour: dict[int, Optional[float]]) -> None:
    """
    Füllt None-Werte in {stunde: wert}-Dict per linearer Interpolation
    zwischen dem letzten und dem nächsten verfügbaren Wert (Issue #145).

    Ränder: fehlt der Wert am Anfang (h=0..k) oder Ende (h=m..24), wird NICHT
    extrapoliert — die Randwerte bleiben None und die betroffenen
    Stunden-Deltas fallen bei der Delta-Bildung wie bisher raus. Das ist
    bewusst: ohne Ankerpunkt an mindestens einer Seite gibt es keine
    sinnvolle Schätzung.

    Arbeitet in-place.
    """
    hours_with_values = sorted(h for h, v in snaps_per_hour.items() if v is not None)
    if len(hours_with_values) < 2:
        return  # keine Interpolation ohne mindestens zwei Ankerpunkte möglich

    # Zwischen-Lücken interpolieren (nur solche, die von bekannten Werten eingerahmt sind)
    for a, b in zip(hours_with_values, hours_with_values[1:]):
        if b - a <= 1:
            continue  # keine Lücke zwischen a und b
        v_a = snaps_per_hour[a]
        v_b = snaps_per_hour[b]
        for h in range(a + 1, b):
            # lineare Interpolation: v_a + (v_b - v_a) * (h - a) / (b - a)
            snaps_per_hour[h] = v_a + (v_b - v_a) * (h - a) / (b - a)


async def get_hourly_kwh_by_category(
    db: AsyncSession,
    anlage,
    investitionen_by_id: dict,
    datum: date,
) -> dict[int, dict[str, Optional[float]]]:
    """
    Berechnet stündliche kWh-Werte pro Energiefluss-Kategorie aus Zähler-Deltas.

    Für jede Stunde H (0..23) wird snapshot(H+1) - snapshot(H) pro Kategorie
    gebildet. Fehlende Snapshots werden on-demand via HA Statistics gefüllt
    (Self-Healing).

    Args:
        db: Async Session
        anlage: Anlage-Objekt (mit sensor_mapping)
        investitionen_by_id: {str(inv_id): Investition} — für typ/parameter
        datum: Der Tag (alle Stunden 00..23 + Abschluss am Folgetag 00:00)

    Returns:
        {h: {"pv": 4.2, "einspeisung": 3.1, ..., "verbrauch": 2.1}}
        Werte können None sein (kein Zähler gemappt oder Lücke).
        "verbrauch" wird bilanziell berechnet:
            verbrauch = pv + netzbezug - einspeisung - (ladung - entladung)
        nur wenn pv, einspeisung, netzbezug alle verfügbar sind.
    """
    sensor_mapping = anlage.sensor_mapping or {}

    # 1. Zähler-Entities sammeln mit Kategorien
    # (sensor_key, entity_id | None, kategorie)
    # entity_id=None bei reinen MQTT-Quellen (Standalone/Docker-Modus)
    eintraege: list[tuple[str, Optional[str], str]] = []
    seen_keys: set[str] = set()

    # 1a. HA-gemappte Zähler aus sensor_mapping
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

    # 1b. MQTT-gespeiste Zähler (Standalone/Docker-Modus ohne HA-Integration).
    # Enumeriert Keys die in mqtt_energy_snapshots für diese Anlage vorkommen
    # (Filter: letzte 7 Tage, um nur aktive Topics zu berücksichtigen).
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
        # Kategorie herleiten: für basis-Keys direkt, für inv-Keys via typ-Lookup
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
            eintraege.append((sk, None, kat))  # entity_id=None → MQTT-Fallback
            seen_keys.add(sk)

    if not eintraege:
        return {}

    # 2. Snapshots für alle benötigten Stundenboundaries holen.
    # Backward-Konvention (Issue #144): Slot N = Energie [N-1, N).
    # Slot 0 = Delta von Vortag 23:00 → Heute 00:00
    # Slot 1 = Delta von Heute 00:00 → 01:00
    # Slot 23 = Delta von Heute 22:00 → 23:00
    # → Snapshots bei h=-1..23 werden benötigt (nicht mehr 0..24).
    tag_0 = datetime.combine(datum, datetime.min.time())
    result: dict[int, dict[str, Optional[float]]] = {h: {} for h in range(24)}

    # pro sensor_key: {stunde_-1_bis_23: wert}
    snaps: dict[str, dict[int, Optional[float]]] = {}
    for sensor_key, entity_id, _kat in eintraege:
        snaps[sensor_key] = {}
        for h in range(-1, 24):  # -1 = Vortag 23:00, 0..23 = Heute 00:00..23:00
            ts = tag_0 + timedelta(hours=h)
            wert = await get_snapshot(db, anlage.id, sensor_key, entity_id, ts)
            snaps[sensor_key][h] = wert

    # 2b. Lücken durch lineare Interpolation füllen (Issue #145).
    # Kumulative Zähler sind monoton steigend, aber der genaue stündliche
    # Zuwachs über eine Lücke ist unbekannt — lineare Interpolation verteilt
    # das Gesamt-Delta gleichmäßig über die fehlenden Stunden. Das ist
    # deutlich besser als "Stunde-Null + Folge-Spike" (2h-Delta in eine
    # einzige Stunde aufgestaut), auch wenn es die reale intra-day-Dynamik
    # nicht perfekt wiedergibt.
    for sensor_key in snaps:
        _fill_gaps_linear(snaps[sensor_key])

    # 3. Deltas pro Stunde und Kategorie summieren (Backward-Konvention).
    # Slot h = snap[h] - snap[h-1] → Energie [h-1, h).
    for h in range(24):
        per_kat: dict[str, Optional[float]] = {}
        for sensor_key, _eid, kat in eintraege:
            s0 = snaps[sensor_key][h - 1]
            s1 = snaps[sensor_key][h]
            if s0 is None or s1 is None:
                continue  # Kategorie unvollständig für diese Stunde
            d = s1 - s0
            if d < -0.01:
                # Tagesreset-Zähler (HA utility_meter mit daily cycle): s0 ≈ Tagesendwert,
                # s1 ≈ 0 nach Mitternachts-Reset. Slot wird mit s1 (Energie seit Reset)
                # gewertet statt verworfen, sonst bliebe Slot 0 dauerhaft None und
                # ist_unvollstaendig=True würde irreführend triggern.
                if s1 < 0.5 and s0 > 0.5:
                    d = max(0.0, s1)
                else:
                    logger.warning(
                        f"Negatives Delta bei {sensor_key} ({datum} Slot{h}): {d:.3f}"
                    )
                    continue
            d = max(0.0, d)
            per_kat[kat] = (per_kat.get(kat) or 0.0) + d
        result[h] = per_kat

    # 4. Aggregierte Kategorien zu Bilanz-Feldern:
    #    pv, einspeisung, netzbezug, batterie_lade_netto, wp, wallbox, verbrauch
    final: dict[int, dict[str, Optional[float]]] = {}
    for h in range(24):
        d = result[h]
        pv = d.get("pv")
        einsp = d.get("einspeisung")
        bez = d.get("netzbezug")
        ladung_batt = d.get("ladung_batterie")
        entladung_batt = d.get("entladung_batterie")
        wp = d.get("verbrauch_wp")
        wallbox = d.get("ladung_wallbox")
        eauto = d.get("verbrauch_eauto")
        sonst_erz = d.get("erzeugung_sonstiges")
        sonst_verbr = d.get("verbrauch_sonstiges")

        # Gesamt-PV inkl. Sonstiges-Erzeuger
        pv_total = None
        if pv is not None or sonst_erz is not None:
            pv_total = (pv or 0.0) + (sonst_erz or 0.0)

        # Batterie netto (positiv = Ladung, negativ = Entladung)
        batt_netto = None
        if ladung_batt is not None or entladung_batt is not None:
            batt_netto = (ladung_batt or 0.0) - (entladung_batt or 0.0)

        # Bilanz-Verbrauch: PV + Netzbezug − Einspeisung − Batterie-Nettoladung
        verbrauch = None
        if pv_total is not None and einsp is not None and bez is not None:
            v = pv_total + bez - einsp - (batt_netto or 0.0)
            verbrauch = max(0.0, v)

        final[h] = {
            "pv": pv_total,
            "einspeisung": einsp,
            "netzbezug": bez,
            "ladung_batterie": ladung_batt,
            "entladung_batterie": entladung_batt,
            "batterie_netto": batt_netto,
            "wp": wp,
            "wallbox": (wallbox or 0.0) + (eauto or 0.0) if (wallbox is not None or eauto is not None) else None,
            "verbrauch_sonstiges": sonst_verbr,
            "verbrauch": verbrauch,
        }
    return final


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
            from sqlalchemy import func
            abstand = func.abs(
                func.julianday(SensorSnapshot.zeitpunkt) - func.julianday(zp)
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

    from sqlalchemy import func as _sql_func

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


async def get_daily_counter_deltas_by_inv(
    db: AsyncSession,
    anlage,
    investitionen_by_id: dict,
    datum: date,
) -> dict[str, dict[str, int]]:
    """
    Berechnet Tages-Differenzen reiner Counter (KUMULATIVE_COUNTER_FELDER)
    pro Investition aus Snapshot-Differenzen.

    Im Gegensatz zu kWh-Energiezählern, deren stündliches Muster für
    Heatmaps und Bilanz relevant ist, sind Counter wie WP-Kompressor-Starts
    auf Tagesebene aussagekräftig (Wartungs-/Auslegungs-KPI). Daher reicht
    der Tages-Wert: snapshot(Folgetag 00:00) − snapshot(Tag 00:00).

    Returns:
        {feld: {inv_id_str: int}} z.B. {"wp_starts_anzahl": {"5": 12}}
        Investitionen ohne gemappten Counter werden weggelassen.
    """
    sensor_mapping = anlage.sensor_mapping or {}
    investitionen_map = sensor_mapping.get("investitionen", {}) or {}

    tag_start = datetime.combine(datum, datetime.min.time())
    tag_ende = tag_start + timedelta(days=1)

    result: dict[str, dict[str, int]] = {}

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
            sensor_id = config.get("sensor_id")
            sensor_key = f"inv:{inv_id_str}:{feld}"
            snap_start = await get_snapshot(db, anlage.id, sensor_key, sensor_id, tag_start)
            snap_ende = await get_snapshot(db, anlage.id, sensor_key, sensor_id, tag_ende)
            if snap_start is None or snap_ende is None:
                continue
            delta_count = snap_ende - snap_start
            if delta_count < 0:
                # Counter-Reset (Firmware-Update o.ä.) — als 0 werten, nicht als Lücke
                logger.warning(
                    f"Negatives Counter-Delta {feld} für anlage={anlage.id} "
                    f"inv={inv_id_str} ({datum}): {delta_count:.1f} → 0"
                )
                delta_count = 0
            result.setdefault(feld, {})[inv_id_str] = int(round(delta_count))

    return result


async def get_hourly_counter_sum_by_feld(
    db: AsyncSession,
    anlage,
    investitionen_by_id: dict,
    datum: date,
    feld: str,
) -> dict[int, Optional[int]]:
    """
    Berechnet Stunden-Counter-Summen für ein bestimmtes Feld (z.B. 'wp_starts_anzahl'),
    summiert über alle Investitionen mit gemapptem Counter.

    Für jede Stunde h (0..23) wird snapshot(h+1) − snapshot(h) pro Investition
    gebildet und über alle Investitionen aufaddiert. Negative Deltas (Counter-Reset)
    werden als 0 gewertet.

    Returns:
        {h: count} für h in 0..23. Fehlt der Snapshot bei beiden Endpunkten einer
        Stunde, ist count None (Lücke). Fehlt der Counter komplett (kein Mapping),
        wird ein leeres Dict zurückgegeben.
    """
    sensor_mapping = anlage.sensor_mapping or {}
    investitionen_map = sensor_mapping.get("investitionen", {}) or {}

    relevant_invs: list[tuple[str, Optional[str]]] = []  # (sensor_key, sensor_id)
    for inv_id_str, inv_data in investitionen_map.items():
        if not isinstance(inv_data, dict):
            continue
        inv = investitionen_by_id.get(inv_id_str) or investitionen_by_id.get(str(inv_id_str))
        if inv is None:
            continue
        if feld not in KUMULATIVE_COUNTER_FELDER.get(inv.typ, ()):
            continue
        felder = inv_data.get("felder", {}) or {}
        config = felder.get(feld)
        if not isinstance(config, dict) or config.get("strategie") != "sensor":
            continue
        sensor_key = f"inv:{inv_id_str}:{feld}"
        relevant_invs.append((sensor_key, config.get("sensor_id")))

    if not relevant_invs:
        return {}

    tag_0 = datetime.combine(datum, datetime.min.time())
    snaps_per_inv: dict[str, dict[int, Optional[float]]] = {}
    for sensor_key, entity_id in relevant_invs:
        snaps: dict[int, Optional[float]] = {}
        for h in range(25):  # 0..24, damit jede Stunde h ein Boundary-Paar (h, h+1) hat
            ts = tag_0 + timedelta(hours=h)
            snaps[h] = await get_snapshot(db, anlage.id, sensor_key, entity_id, ts)
        snaps_per_inv[sensor_key] = snaps

    result: dict[int, Optional[int]] = {}
    for h in range(24):
        any_value = False
        total = 0
        for sensor_key, _ in relevant_invs:
            s0 = snaps_per_inv[sensor_key][h]
            s1 = snaps_per_inv[sensor_key][h + 1]
            if s0 is None or s1 is None:
                continue
            d = s1 - s0
            if d < 0:
                d = 0  # Counter-Reset → 0 (Warnung wäre redundant zur Tages-Aggregation)
            total += int(round(d))
            any_value = True
        result[h] = total if any_value else None
    return result


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
    counter_map = _build_counter_map(anlage)
    ha_svc = get_ha_statistics_service()
    if counter_map and ha_svc.is_available:
        for sensor_key, entity_id in counter_map.items():
            wert = ha_svc.get_value_at(entity_id, zeitpunkt, toleranz_minuten=10)
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
            await _upsert_snapshot(db, anlage.id, sensor_key, zeitpunkt, wert)
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
    for (mqtt_key,) in mqtt_keys_result.all():
        sensor_key = _mqtt_key_to_sensor_key(mqtt_key)
        if not sensor_key:
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
        await _upsert_snapshot(db, anlage.id, sensor_key, zeitpunkt, wert)
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
    counter_map = _build_counter_map(anlage)
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
        wert = ha_svc.get_value_at(
            entity_id, zeitpunkt, toleranz_minuten=3, short_term=True
        )
        if wert is None:
            if force_resnap:
                await _delete_snapshot_if_exists(
                    db, anlage.id, sensor_key, zeitpunkt
                )
            continue
        await _upsert_snapshot(db, anlage.id, sensor_key, zeitpunkt, wert)
        count += 1

    return count


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


async def live_snapshot_if_missing(
    db: AsyncSession,
    anlage,
    zeitpunkt: datetime,
) -> int:
    """
    Schreibt für eine anstehende volle Stunde einen Live-Snapshot pro
    MQTT-Counter, aber nur wenn dort noch kein Eintrag existiert.

    Hintergrund: Der reguläre `snapshot_anlage` läuft erst :05 nach voller
    Stunde. Im Standalone-/Docker-Modus mit MQTT publishen die Geräte ihre
    kumulativen kWh-Werte kontinuierlich; ein Live-Snapshot kurz vor voller
    Stunde liefert einen guten Annäherungswert für die laufende Stunde.

    HA-Counter-Pfad (Add-on-Modus) wurde in v3.25.18 entfernt:
    `ha_state_svc.get_sensor_state()` liefert das Sensor-`state`, nicht das
    Statistics-`sum`. Bei Tagesreset-Zählern (utility_meter daily cycle) sind
    die zwei verschiedene Skalen — `state`=Tagesenergie, `sum`=Lifetime-
    bereinigt. Wurde der :05-Hourly-Job nach so einem Live-Schreiben
    übersprungen (HA/Add-on-Restart, Job-Crash), blieb der `state`-Wert
    persistent in der Snapshot-Tabelle und produzierte beim nächsten
    Aggregat einen Lifetime-grossen Stunden-Spike (Issue #184, Befund Rainer
    1.5.2026). Die laufende Stunde wartet im Add-on-Modus jetzt bis :05 der
    Folgestunde — wie vor #146 — und der reguläre `snapshot_anlage`-Job
    schreibt aus HA-Statistics den exakten `sum`-Wert.

    MQTT hat keinen `state`/`sum`-Split: Topics liefern direkt kumulative
    Lifetime-Werte. Der MQTT-Pfad bleibt unverändert.

    Args:
        db: Async Session
        anlage: Anlage-Objekt
        zeitpunkt: Anstehende volle Stunde (typisch: now+1h auf :00 gerundet)

    Returns:
        Anzahl geschriebener Live-Snapshots (MQTT-Counter).
    """
    count = 0

    # MQTT-gespeiste Zähler (Standalone-Modus): jüngsten Snapshot der
    # letzten ~10 Min als Live-Wert verwenden. Bei MQTT ist der Topic-Wert
    # die kumulative Lifetime-Energie (kein state/sum-Split wie bei HA).
    cutoff = zeitpunkt - timedelta(minutes=10)
    mqtt_keys_result = await db.execute(
        select(MqttEnergySnapshot.energy_key).where(
            and_(
                MqttEnergySnapshot.anlage_id == anlage.id,
                MqttEnergySnapshot.timestamp >= cutoff,
            )
        ).distinct()
    )
    for (mqtt_key,) in mqtt_keys_result.all():
        sensor_key = _mqtt_key_to_sensor_key(mqtt_key)
        if not sensor_key:
            continue
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
        # Jüngsten MQTT-Wert nehmen (innerhalb des cutoff-Fensters)
        recent = await db.execute(
            select(MqttEnergySnapshot.value_kwh).where(
                and_(
                    MqttEnergySnapshot.anlage_id == anlage.id,
                    MqttEnergySnapshot.energy_key == mqtt_key,
                    MqttEnergySnapshot.timestamp >= cutoff,
                )
            ).order_by(MqttEnergySnapshot.timestamp.desc()).limit(1)
        )
        wert = recent.scalar_one_or_none()
        if wert is None:
            continue
        await _upsert_snapshot(db, anlage.id, sensor_key, zeitpunkt, wert)
        count += 1

    return count
