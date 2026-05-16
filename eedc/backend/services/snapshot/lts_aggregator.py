"""
HA-LTS-basierte Variante von `get_hourly_kwh_by_category` (Etappe 4 v3.31.0).

Liest Stunden-kWh-Deltas direkt aus HA-Statistics-LTS (`statistics`-Tabelle)
und liefert dieselbe Output-Form wie `services.snapshot.aggregator.
get_hourly_kwh_by_category` — damit der Aufrufer (`services.energie_profil.
aggregator.aggregate_day`) nur den Datenherkunft-Switch braucht, nicht
die nachgelagerte Verarbeitung anpassen.

Unterschied zur Snapshot-Variante:
  - Quelle: HA-LTS-Statistics direkt (kein sensor_snapshots-Zwischenschritt)
  - Schreib-Provenance: `external:ha_statistics:hourly` (Caller setzt das)
  - Konsistent mit `external:ha_statistics:daily` für TagesZusammenfassung
    (Caller summiert die Stunden-Deltas für Daily, beide aus derselben Quelle)
  - Standalone-Modus (MQTT) wird NICHT bedient — dafür bleibt die
    Snapshot-Variante (`get_hourly_kwh_by_category`) als Fallback

Konzept-Doc: `docs/KONZEPT-ETAPPE-4-HA-LTS-SOT.md`.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.ha_statistics_service import get_ha_statistics_service
from backend.services.snapshot.keys import (
    BASIS_ZAEHLER_FELDER,
    _categorize_counter,
)
from backend.services.snapshot.plausibility import (
    cap_pv_einspeisung_stunde,
    schwelle_pv_einspeisung_stunde_kwh,
)

logger = logging.getLogger(__name__)


async def get_hourly_kwh_by_category_lts(
    db: AsyncSession,
    anlage,
    investitionen_by_id: dict,
    datum: date,
) -> dict[int, dict[str, Optional[float]]]:
    """
    Etappe 4: Stündliche kWh-Werte pro Energiefluss-Kategorie aus HA-LTS.

    Returns:
        Gleiches Format wie `services.snapshot.aggregator.get_hourly_kwh_by_category`:
        {h: {"pv": x, "einspeisung": y, "netzbezug": z, "verbrauch": v,
             "wp": w, "wallbox": w2, "batterie_netto": b, "verbrauch_sonstiges": s}}
        Werte können None sein (kein Sensor-Mapping oder HA-LTS-Lücke).

    Keine Daten:
        Wenn HA-LTS nicht verfügbar oder kein Sensor-Mapping greift, wird
        ein leeres Dict `{}` zurückgegeben — der Aufrufer kann dann auf die
        Snapshot-Variante als Fallback fallen.
    """
    ha_svc = get_ha_statistics_service()
    if not ha_svc.is_available:
        return {}

    sensor_mapping = anlage.sensor_mapping or {}

    # Sensor-Mapping durchgehen: (entity_id, kategorie) pro Counter-Feld.
    # Anders als bei der Snapshot-Variante: HA-LTS hat keine MQTT-Zähler,
    # also nur HA-gemappte Sensoren.
    eintraege: list[tuple[str, str]] = []  # (entity_id, kategorie)

    basis = sensor_mapping.get("basis", {}) or {}
    for feld in BASIS_ZAEHLER_FELDER:
        config = basis.get(feld)
        if isinstance(config, dict) and config.get("strategie") == "sensor":
            eid = config.get("sensor_id")
            if eid:
                kat = _categorize_counter(feld, None, None)
                if kat:
                    eintraege.append((eid, kat))

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
                eintraege.append((eid, kat))

    if not eintraege:
        return {}

    # HA-LTS-Read: alle entity_ids in einem Schwung, 24 Stunden-Deltas pro Sensor.
    # `ha_svc.get_hourly_kwh_deltas_for_day` ist synchron (SQL-Engine ist
    # connection-pool-basiert); im async-Kontext akzeptabel als Inline-Call,
    # weil es eine kurze Read-Operation ist.
    sensor_ids = list({eid for eid, _kat in eintraege})
    deltas = ha_svc.get_hourly_kwh_deltas_for_day(sensor_ids, datum)

    if not deltas:
        return {}

    # Per-Stunde-Kategorie-Aggregation
    result_kat: dict[int, dict[str, Optional[float]]] = {h: {} for h in range(24)}
    for h in range(24):
        per_kat: dict[str, Optional[float]] = {}
        for eid, kat in eintraege:
            slot_delta = deltas.get(eid, {}).get(h)
            if slot_delta is None:
                continue
            # Negative Deltas (Counter-Reset Mitten am Tag): roh durchreichen,
            # Cap greift im Plausibility-Schritt unten. Snapshot-Variante
            # behandelt das speziell (Tagesreset → s1 nehmen); für HA-LTS
            # wären solche Resets in `sum` schon bereinigt — sehr selten.
            if slot_delta < 0:
                logger.warning(
                    f"Anlage {anlage.id}, {datum} h={h} {eid}: "
                    f"negatives HA-LTS-Delta {slot_delta:.3f} — verwerfe"
                )
                continue
            per_kat[kat] = (per_kat.get(kat) or 0.0) + slot_delta
        result_kat[h] = per_kat

    # Kategorien zu Bilanz-Feldern aggregieren — analog Snapshot-Variante.
    schwelle_spike = schwelle_pv_einspeisung_stunde_kwh(
        getattr(anlage, "leistung_kwp", None),
    )
    final: dict[int, dict[str, Optional[float]]] = {}
    for h in range(24):
        d = result_kat[h]
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

        pv_total = None
        if pv is not None or sonst_erz is not None:
            pv_total = (pv or 0.0) + (sonst_erz or 0.0)

        pv_total = cap_pv_einspeisung_stunde(
            pv_total, schwelle_spike,
            anlage_id=anlage.id, datum=datum, stunde=h, kategorie="pv",
        )
        einsp = cap_pv_einspeisung_stunde(
            einsp, schwelle_spike,
            anlage_id=anlage.id, datum=datum, stunde=h, kategorie="einspeisung",
        )

        batt_netto = None
        if ladung_batt is not None or entladung_batt is not None:
            batt_netto = (ladung_batt or 0.0) - (entladung_batt or 0.0)

        verbrauch = None
        if pv_total is not None and einsp is not None and bez is not None:
            v = pv_total + bez - einsp - (batt_netto or 0.0)
            verbrauch = max(0.0, v)

        final[h] = {
            "pv": pv_total,
            "einspeisung": einsp,
            "netzbezug": bez,
            "batterie_netto": batt_netto,
            "wp": wp,
            "wallbox": (wallbox or 0.0) + (eauto or 0.0) if (wallbox is not None or eauto is not None) else None,
            "verbrauch_sonstiges": sonst_verbr,
            "verbrauch": verbrauch,
        }
    return final


async def get_komponenten_tageskwh_lts(
    anlage,
    investitionen_by_id: dict,
    datum: date,
) -> dict[str, float]:
    """
    Etappe 4 (v3.31.0): Tages-kWh pro Komponente aus HA-LTS — direkter
    Ersatz für `snapshot.aggregator.get_komponenten_tageskwh` (Snapshot-
    Pfad).

    Liefert `{komponenten_key: tages_kwh}` mit gleicher Key-Konvention wie
    die Snapshot-Variante:
        einspeisung           Basis
        netzbezug             Basis
        pv_<inv_id>           pv-module
        bkw_<inv_id>          balkonkraftwerk
        batterie_<inv_id>     speicher (ladung − entladung)
        waermepumpe_<inv_id>  waermepumpe (alle Strom-Sensoren summiert)
        wallbox_<inv_id>      wallbox
        eauto_<inv_id>        e-auto
        sonstige_<inv_id>     sonstiges (erzeugung − verbrauch)

    Tagessumme = Σ der 24 LTS-Stunden-Deltas pro Sensor. Damit ist
    Σ Hourly == Daily per Konstruktion — kein Drift zwischen
    TagesEnergieProfil.*_kw und TagesZusammenfassung.komponenten_kwh.

    Investitionen ohne gemappten Counter erscheinen NICHT im Dict
    (analog Snapshot-Variante; Caller behält für solche Keys seinen
    Live-Σ-Fallback).
    """
    ha_svc = get_ha_statistics_service()
    if not ha_svc.is_available:
        return {}

    sensor_mapping = anlage.sensor_mapping or {}

    # Per-Sensor-Mapping: (entity_id, komponenten_key, vorzeichen)
    # vorzeichen +1 = Beitrag positiv (Erzeugung, Verbrauch, Ladung)
    # vorzeichen -1 = Beitrag negativ (Entladung bei Speicher)
    eintraege: list[tuple[str, str, int]] = []

    basis = sensor_mapping.get("basis", {}) or {}
    for feld in ("einspeisung", "netzbezug"):
        cfg = basis.get(feld)
        if isinstance(cfg, dict) and cfg.get("strategie") == "sensor":
            eid = cfg.get("sensor_id")
            if eid:
                eintraege.append((eid, feld, +1))

    investitionen_map = sensor_mapping.get("investitionen", {}) or {}
    for inv_id_str, inv_data in investitionen_map.items():
        if not isinstance(inv_data, dict):
            continue
        inv = investitionen_by_id.get(inv_id_str) or investitionen_by_id.get(str(inv_id_str))
        if inv is None:
            continue

        if inv.typ == "pv-module":
            key = f"pv_{inv_id_str}"
        elif inv.typ == "balkonkraftwerk":
            key = f"bkw_{inv_id_str}"
        elif inv.typ == "speicher":
            key = f"batterie_{inv_id_str}"
        elif inv.typ == "waermepumpe":
            key = f"waermepumpe_{inv_id_str}"
        elif inv.typ == "wallbox":
            key = f"wallbox_{inv_id_str}"
        elif inv.typ == "e-auto":
            key = f"eauto_{inv_id_str}"
        elif inv.typ == "sonstiges":
            key = f"sonstige_{inv_id_str}"
        else:
            continue

        felder = inv_data.get("felder", {}) or {}
        for feld, config in felder.items():
            if not isinstance(config, dict) or config.get("strategie") != "sensor":
                continue
            eid = config.get("sensor_id")
            if not eid:
                continue

            # Vorzeichen-Logik je Investitionstyp + Feld
            vorzeichen = +1
            if inv.typ == "speicher" and feld == "entladung_kwh":
                vorzeichen = -1
            elif inv.typ == "sonstiges":
                kategorie = (inv.parameter or {}).get("kategorie", "verbraucher") if isinstance(inv.parameter, dict) else "verbraucher"
                if feld == "verbrauch_kwh" and kategorie != "erzeuger":
                    vorzeichen = -1

            eintraege.append((eid, key, vorzeichen))

    if not eintraege:
        return {}

    sensor_ids = list({eid for eid, _key, _vz in eintraege})
    deltas = ha_svc.get_hourly_kwh_deltas_for_day(sensor_ids, datum)

    if not deltas:
        return {}

    # Pro Sensor: Tages-Σ aus den 24 Stunden-Slots. Lücken (None) werden
    # ignoriert — wer mehrere Stunden Lücken hat, bekommt entsprechend
    # niedrigeren Tageswert. Caller-Live-Σ-Fallback greift dann ggf.
    sensor_tagessumme: dict[str, float] = {}
    for eid, slots in deltas.items():
        s = 0.0
        any_valid = False
        for h_val in slots.values():
            if h_val is not None:
                s += h_val
                any_valid = True
        if any_valid:
            sensor_tagessumme[eid] = s

    # Aggregation pro komponenten_key (mit Vorzeichen)
    result: dict[str, float] = {}
    for eid, key, vz in eintraege:
        s = sensor_tagessumme.get(eid)
        if s is None:
            continue
        result[key] = result.get(key, 0.0) + vz * s

    # Negative Tagessummen (z. B. Speicher netto entladen) bleiben negativ;
    # die Snapshot-Variante macht das gleichermaßen. Konsumenten können den
    # Vorzeichen-Sinn aus der Key-Konvention herleiten.
    return result
