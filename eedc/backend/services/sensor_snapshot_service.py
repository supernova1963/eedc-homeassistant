"""
Sensor Snapshot Service (Issue #135).

Führt stündliche Snapshots kumulativer kWh-Zählerstände und liefert
Zähler-Delta-basierte Energiewerte für aggregate_day/backfill.

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

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.sensor_snapshot import SensorSnapshot
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

BASIS_ZAEHLER_FELDER: tuple[str, ...] = ("einspeisung", "netzbezug")


async def get_snapshot(
    db: AsyncSession,
    anlage_id: int,
    sensor_key: str,
    sensor_id: str,
    zeitpunkt: datetime,
    toleranz_minuten: int = 5,
    ha_toleranz_minuten: int = 120,
) -> Optional[float]:
    """
    Holt den kumulativen Zählerstand zu einem bestimmten Zeitpunkt.

    Self-Healing: Wenn kein Snapshot in der DB existiert (±toleranz_minuten
    um zeitpunkt), wird HA Statistics befragt und das Ergebnis gespeichert.

    Args:
        db: Async Session
        anlage_id: Anlagen-ID
        sensor_key: Stabiler Schlüssel im sensor_snapshots-Schema
                    (z.B. "inv:4:pv_erzeugung_kwh", "basis:einspeisung")
        sensor_id: HA Entity-ID des kumulativen Zählers
        zeitpunkt: Zielzeitpunkt (typisch: Stundenanfang, 00:00, 01:00 ...)
        toleranz_minuten: Max. zeitliche Abweichung bei DB-Lookup
        ha_toleranz_minuten: Max. zeitliche Abweichung bei HA-Statistics-Fallback

    Returns:
        Zählerstand in kWh oder None (kein Datenpunkt verfügbar).
    """
    von = zeitpunkt - timedelta(minutes=toleranz_minuten)
    bis = zeitpunkt + timedelta(minutes=toleranz_minuten)

    result = await db.execute(
        select(SensorSnapshot.wert_kwh).where(
            and_(
                SensorSnapshot.anlage_id == anlage_id,
                SensorSnapshot.sensor_key == sensor_key,
                SensorSnapshot.zeitpunkt >= von,
                SensorSnapshot.zeitpunkt <= bis,
            )
        ).order_by(
            # Nächstliegender Zeitpunkt zuerst (absolute Differenz)
            SensorSnapshot.zeitpunkt.asc()
        ).limit(1)
    )
    row = result.scalar_one_or_none()
    if row is not None:
        return row

    # Self-Healing via HA Statistics
    ha_svc = get_ha_statistics_service()
    if not ha_svc.is_available:
        logger.debug(
            f"Snapshot-Lücke für anlage={anlage_id} key={sensor_key} @ {zeitpunkt} "
            f"— HA Statistics nicht verfügbar"
        )
        return None

    wert = ha_svc.get_value_at(sensor_id, zeitpunkt, ha_toleranz_minuten)
    if wert is None:
        logger.debug(
            f"HA Statistics liefert keinen Wert für {sensor_id} @ {zeitpunkt}"
        )
        return None

    # Upsert in DB (idempotent bei parallelen Anfragen dank UniqueConstraint)
    await _upsert_snapshot(db, anlage_id, sensor_key, zeitpunkt, wert)
    return wert


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
    """Prüft ob ein Feld-Name ein kumulativer kWh-Zähler ist."""
    # Alle Felder aus KUMULATIVE_ZAEHLER_FELDER (flache Menge)
    alle = {f for felder in KUMULATIVE_ZAEHLER_FELDER.values() for f in felder}
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
    eintraege: list[tuple[str, str, str]] = []
    # (sensor_key, entity_id, kategorie)

    basis = sensor_mapping.get("basis", {}) or {}
    for feld in BASIS_ZAEHLER_FELDER:
        config = basis.get(feld)
        if isinstance(config, dict) and config.get("strategie") == "sensor":
            eid = config.get("sensor_id")
            if eid:
                kat = _categorize_counter(feld, None, None)
                if kat:
                    eintraege.append((f"basis:{feld}", eid, kat))

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
                eintraege.append((f"inv:{inv_id_str}:{feld}", eid, kat))

    if not eintraege:
        return {}

    # 2. Für jede Stunde: Snapshot bei H und bei H+1 holen (mit Self-Healing)
    tag_0 = datetime.combine(datum, datetime.min.time())
    result: dict[int, dict[str, Optional[float]]] = {h: {} for h in range(24)}

    # Pre-fetch: Für alle 25 Zeitpunkte (00:00..24:00) alle Snapshots parallel holen
    # Einfach: sequential, der Overhead ist gering dank DB-Cache
    # pro sensor_key: {stunde_0_24: wert}
    snaps: dict[str, dict[int, Optional[float]]] = {}
    for sensor_key, entity_id, _kat in eintraege:
        snaps[sensor_key] = {}
        for h in range(25):  # 0..24 (24 = nächster Tag 00:00)
            ts = tag_0 + timedelta(hours=h)
            wert = await get_snapshot(db, anlage.id, sensor_key, entity_id, ts)
            snaps[sensor_key][h] = wert

    # 3. Deltas pro Stunde und Kategorie summieren
    for h in range(24):
        per_kat: dict[str, Optional[float]] = {}
        for sensor_key, _eid, kat in eintraege:
            s0 = snaps[sensor_key][h]
            s1 = snaps[sensor_key][h + 1]
            if s0 is None or s1 is None:
                continue  # Kategorie unvollständig für diese Stunde
            d = s1 - s0
            if d < -0.01:  # Reset
                logger.warning(
                    f"Negatives Delta bei {sensor_key} ({datum} H{h}): {d:.3f}"
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


async def snapshot_anlage(
    db: AsyncSession,
    anlage,
    zeitpunkt: Optional[datetime] = None,
) -> int:
    """
    Schreibt einen Snapshot aller gemappten kumulativen Zähler für eine Anlage.

    Liest den aktuellen Sensor-Wert via HA Statistics (toleranz: 60 min ab
    zeitpunkt rückwärts). Kein Live-State-Pull — der Scheduler-Job ruft
    am Stundenanfang und vertraut darauf, dass HA Statistics die Stunde
    bereits finalisiert hat (Latenz ~5 min).

    Args:
        db: Async Session
        anlage: Anlage-Objekt
        zeitpunkt: Zielzeitpunkt. Default: aktuelle Stunde (round down).

    Returns:
        Anzahl geschriebener Snapshots.
    """
    if zeitpunkt is None:
        now = datetime.now()
        zeitpunkt = now.replace(minute=0, second=0, microsecond=0)

    counter_map = _build_counter_map(anlage)
    if not counter_map:
        return 0

    ha_svc = get_ha_statistics_service()
    if not ha_svc.is_available:
        return 0

    count = 0
    for sensor_key, entity_id in counter_map.items():
        wert = ha_svc.get_value_at(entity_id, zeitpunkt, toleranz_minuten=60)
        if wert is None:
            continue
        await _upsert_snapshot(db, anlage.id, sensor_key, zeitpunkt, wert)
        count += 1

    return count
