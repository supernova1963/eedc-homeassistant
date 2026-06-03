"""
Snapshot-Aggregator.

Liest Boundary-Snapshots aus `sensor_snapshots` (mit Self-Healing über
`reader.get_snapshot()`) und liefert stündliche kWh-Werte nach Energiefluss-
Kategorie, stündliche Counter-Inkremente pro Feld und Tages-Counter-Deltas
pro Investition. Lückenfüllung via linearer Interpolation (Issue #145).

Slot-Konvention seit Etappe 3c P2 (KONZEPT-ENERGIEPROFIL-3C.md):
- Hourly-Konsumenten gehen über `BoundaryRange.for_hourly_slots()` —
  einheitlich Backward (Issue #144), Slot h = `snap[h] − snap[h-1]`.
- Tages-Counter-Konsumenten nutzen Boundary-Diff über das HA-Tagesfenster
  `[Heute 00:00, Folgetag 00:00)`, identisch zum HA Energy Dashboard.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.mqtt_energy_snapshot import MqttEnergySnapshot

from backend.services.snapshot.boundary_range import BoundaryRange
from backend.services.snapshot.keys import (
    KUMULATIVE_COUNTER_FELDER,
    _categorize_counter,
    _mqtt_key_to_sensor_key,
)
from backend.services.snapshot.komponenten_beitraege import (
    basis_beitraege,
    basis_hourly_eintraege,
    investition_beitraege,
    investition_hourly_eintraege,
    resolve_either_or_eintraege,
)
from backend.services.snapshot.plausibility import (
    cap_pv_einspeisung_stunde,
    schwelle_pv_einspeisung_stunde_kwh,
)
from backend.services.snapshot.reader import get_snapshot

logger = logging.getLogger(__name__)


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
    # (sensor_key, entity_id | None, kategorie, fallback_gruppe)
    # entity_id=None bei reinen MQTT-Quellen (Standalone/Docker-Modus)
    eintraege: list[tuple[str, Optional[str], str, Optional[str]]] = []
    seen_keys: set[str] = set()

    # 1a. HA-gemappte Zähler aus sensor_mapping — Feld-Auswahl (Whitelist +
    # Either-Or + parent-Skip) über DIESELBE Normalisierung wie der Daily-Pfad
    # (`*_hourly_eintraege`), nicht mehr über rohe `_categorize_counter`-
    # Aufrufe. Issue #298 (Audit-§6.2, Pattern-Klasse
    # [[feedback_aggregator_symmetrie]]): ein doppelt gemappter E-Auto-Zähler
    # (`verbrauch_kwh` + `ladung_kwh`) wird in der Either-Or-Gruppe aufgelöst
    # statt doppelt summiert.
    basis = sensor_mapping.get("basis", {}) or {}
    for he in basis_hourly_eintraege(sensor_mapping):
        cfg = basis.get(he.feld)
        if isinstance(cfg, dict):
            eid = cfg.get("sensor_id")
            if eid:
                sk = f"basis:{he.feld}"
                eintraege.append((sk, eid, he.kategorie, he.fallback_gruppe))
                seen_keys.add(sk)

    investitionen_map = sensor_mapping.get("investitionen", {}) or {}
    for inv_id_str, inv_data in investitionen_map.items():
        if not isinstance(inv_data, dict):
            continue
        inv = investitionen_by_id.get(inv_id_str) or investitionen_by_id.get(str(inv_id_str))
        if inv is None:
            continue
        felder = inv_data.get("felder", {}) or {}
        for he in investition_hourly_eintraege(inv, inv_data):
            cfg = felder.get(he.feld)
            if isinstance(cfg, dict):
                eid = cfg.get("sensor_id")
                if eid:
                    sk = f"inv:{inv_id_str}:{he.feld}"
                    eintraege.append((sk, eid, he.kategorie, he.fallback_gruppe))
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
        # Kategorie herleiten: für basis-Keys direkt, für inv-Keys via typ-Lookup.
        # MQTT-Standalone hat keinen Daily-Symmetrie-Partner (get_komponenten_
        # tageskwh deckt nur sensor-Strategie ab) → bewusst KEINE Either-Or-
        # Normalisierung hier (Anti-Bündelung [[feedback_release_bundling]]);
        # die #298-Doppelmapping-Auflösung greift im HA-gemappten Pfad oben.
        # MQTT-Doppelmapping als latente Restklasse separat getrackt.
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
            eintraege.append((sk, None, kat, None))  # entity_id=None → MQTT-Fallback
            seen_keys.add(sk)

    if not eintraege:
        return {}

    # 2. Snapshots für alle benötigten Stundenboundaries holen.
    # Backward-Konvention nach Issue #144 — gekapselt in BoundaryRange.
    # Slot 0 = Delta von Vortag 23:00 → Heute 00:00
    # Slot 23 = Delta von Heute 22:00 → 23:00
    # → 25 Boundaries (offsets -1..23), 24 Slots (0..23).
    rng = BoundaryRange.for_hourly_slots(datum)
    result: dict[int, dict[str, Optional[float]]] = {h: {} for h in range(24)}

    # pro sensor_key: {boundary_offset: wert}
    snaps: dict[str, dict[int, Optional[float]]] = {}
    for sensor_key, entity_id, _kat, _grp in eintraege:
        snaps[sensor_key] = {}
        for offset in rng.boundary_offsets:
            ts = rng.boundary_at(offset)
            wert = await get_snapshot(db, anlage.id, sensor_key, entity_id, ts)
            snaps[sensor_key][offset] = wert

    # 2b. Lücken durch lineare Interpolation füllen (Issue #145).
    # Kumulative Zähler sind monoton steigend, aber der genaue stündliche
    # Zuwachs über eine Lücke ist unbekannt — lineare Interpolation verteilt
    # das Gesamt-Delta gleichmäßig über die fehlenden Stunden. Das ist
    # deutlich besser als "Stunde-Null + Folge-Spike" (2h-Delta in eine
    # einzige Stunde aufgestaut), auch wenn es die reale intra-day-Dynamik
    # nicht perfekt wiedergibt.
    for sensor_key in snaps:
        _fill_gaps_linear(snaps[sensor_key])

    # 2c. Either-Or-Auflösung auf TAGES-Ebene (Issue #298): pro fallback_gruppe
    # gewinnt der erste Eintrag, dessen Sensor an irgendeinem Slot ein
    # vollständiges Delta-Paar liefert — identisch zur Daily-Auflösung in
    # `get_komponenten_tageskwh._apply_beitraege`. Tages-Ebene (nicht pro
    # Stunde), damit die Wahl über alle 24 Stunden stabil bleibt. MQTT-Einträge
    # (fallback_gruppe=None) bleiben unberührt.
    def _hat_tagesdaten(sensor_key: str) -> bool:
        s = snaps.get(sensor_key, {})
        return any(
            s.get(prev_off) is not None and s.get(curr_off) is not None
            for _slot, prev_off, curr_off in rng.slot_pairs
        )

    eintraege = resolve_either_or_eintraege(
        eintraege,
        gruppe_fn=lambda e: e[3],            # (sensor_key, eid, kat, gruppe)
        hat_tagesdaten_fn=lambda e: _hat_tagesdaten(e[0]),
    )

    # 3. Deltas pro Stunde und Kategorie summieren (Backward-Konvention).
    # Slot h = snap[curr=h] - snap[prev=h-1] → Energie [h-1, h).
    for slot_idx, prev_off, curr_off in rng.slot_pairs:
        per_kat: dict[str, Optional[float]] = {}
        for sensor_key, _eid, kat, _grp in eintraege:
            s0 = snaps[sensor_key][prev_off]
            s1 = snaps[sensor_key][curr_off]
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
                        f"Negatives Delta bei {sensor_key} ({datum} Slot{slot_idx}): {d:.3f}"
                    )
                    continue
            d = max(0.0, d)
            per_kat[kat] = (per_kat.get(kat) or 0.0) + d
        result[slot_idx] = per_kat

    # 4. Aggregierte Kategorien zu Bilanz-Feldern:
    #    pv, einspeisung, netzbezug, batterie_lade_netto, wp, wallbox, verbrauch
    schwelle_spike = schwelle_pv_einspeisung_stunde_kwh(
        getattr(anlage, "leistung_kwp", None)
    )
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

        # Plausibilitäts-Cap (Counter-Spike-Schutz, dietmar1968/Forum #529):
        # Wenn PV oder Einspeisung > kwp × 1.5 → None, weil physikalisch
        # unmöglich und typisch für HA-Counter-Off-by-ones nach Restarts.
        # Daten-Checker `_check_energieprofil_plausibilitaet` teilt die
        # Schwelle (SoT in `plausibility.py`).
        pv_total = cap_pv_einspeisung_stunde(
            pv_total, schwelle_spike,
            anlage_id=anlage.id, datum=datum, stunde=h, kategorie="pv",
        )
        einsp = cap_pv_einspeisung_stunde(
            einsp, schwelle_spike,
            anlage_id=anlage.id, datum=datum, stunde=h, kategorie="einspeisung",
        )

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


async def get_komponenten_tageskwh(
    db: AsyncSession,
    anlage,
    investitionen_by_id: dict,
    datum: date,
) -> dict[str, float]:
    """
    Tagesgesamt pro Komponente aus Snapshot-Boundary-Diff (Etappe 3c P3, E2).

    Liefert `{komponenten_key: tages_kwh}` über das HA-Tagesfenster
    `[Heute 00:00, Folgetag 00:00)`. Identisch zur HA-Energy-Dashboard-Rechnung
    `snap[Folgetag 00:00] − snap[Tag 00:00]`. Ersetzt die ältere
    `Σ-Hourly`-Berechnung im aggregate_day-Pfad für `TagesZusammenfassung.komponenten_kwh`.

    Komponenten-Key folgt der Live-Pfad-Konvention (`live_tagesverlauf_service`):
        pv-module        → "pv_<inv_id>"            ← inv:<id>:pv_erzeugung_kwh
        balkonkraftwerk  → "bkw_<inv_id>"           ← inv:<id>:pv_erzeugung_kwh
        speicher         → "batterie_<inv_id>"      ← (ladung − entladung)_kwh
        waermepumpe      → "waermepumpe_<inv_id>"   ← stromverbrauch_kwh (bzw.
                                                       strom_heizen + strom_warmwasser
                                                       bei getrennte_strommessung).
                                                       Nur elektrisch — heizenergie_kwh
                                                       und warmwasser_kwh sind thermische
                                                       Werte und gehören nicht in die
                                                       Bilanz (~ Strom × COP).
        wallbox          → "wallbox_<inv_id>"       ← inv:<id>:ladung_kwh
        e-auto           → "eauto_<inv_id>"         ← ladung_kwh oder verbrauch_kwh
        sonstiges        → "sonstige_<inv_id>"      ← (erzeugung − verbrauch)_kwh

    Plus Basis-Schlüssel (ohne Investition):
        einspeisung → "einspeisung" (≥ 0)
        netzbezug   → "netzbezug" (≥ 0)

    Investitionen ohne gemappten Counter erscheinen NICHT im Dict — der Aufrufer
    behält seine eigene Live-Σ-Variante als Fallback für solche Keys (typisch:
    WP-Suffix-Keys wie `waermepumpe_2_heizen` aus dem Live-Pfad ohne separates
    `heizenergie_kwh`-Mapping).
    """
    sensor_mapping = anlage.sensor_mapping or {}
    rng = BoundaryRange.for_day_total(datum)
    start_off, end_off = rng.boundary_offsets  # (0, 24)
    ts_start = rng.boundary_at(start_off)
    ts_ende = rng.boundary_at(end_off)

    async def _diff(sensor_key: str, sensor_id: Optional[str]) -> Optional[float]:
        s0 = await get_snapshot(db, anlage.id, sensor_key, sensor_id, ts_start)
        s1 = await get_snapshot(db, anlage.id, sensor_key, sensor_id, ts_ende)
        if s0 is None or s1 is None:
            return None
        d = s1 - s0
        if d < -0.01:
            # Tagesreset-Zähler (HA utility_meter daily): s0 ≈ Tagesendwert,
            # s1 ≈ 0 nach Mitternachts-Reset → s1 ist die Energie seit Reset
            # (analog zum Hourly-Pfad in get_hourly_kwh_by_category).
            if s1 < 0.5 and s0 > 0.5:
                return max(0.0, s1)
            logger.warning(
                f"Negatives Tagesgesamt-Delta für anlage={anlage.id} "
                f"key={sensor_key} ({datum}): {d:.3f} → ignoriert"
            )
            return None
        return max(0.0, d)

    def _sensor_id_for(beitrag, mapping_quelle: dict) -> Optional[str]:
        cfg = (mapping_quelle.get("felder", {}) or {}).get(beitrag.feld) \
            if "felder" in mapping_quelle else mapping_quelle.get(beitrag.feld)
        return cfg.get("sensor_id") if isinstance(cfg, dict) else None

    async def _apply_beitraege(beitraege, sensor_key_fn, mapping_quelle, result):
        """Wendet Beiträge auf result an — mit Either-Or-Fallback-Gruppen-Logik."""
        gruppe_genommen: set[str] = set()
        for b in beitraege:
            # Either-Or: pro Gruppe nur den ersten Beitrag mit verfügbarem Delta nehmen
            if b.fallback_gruppe and b.fallback_gruppe in gruppe_genommen:
                continue
            sid = _sensor_id_for(b, mapping_quelle)
            if not sid:
                continue
            d = await _diff(sensor_key_fn(b.feld), sid)
            if d is None:
                continue
            if b.fallback_gruppe:
                gruppe_genommen.add(b.fallback_gruppe)
            result[b.target_key] = result.get(b.target_key, 0.0) + b.vorzeichen * d

    result: dict[str, float] = {}

    # 1. Basis: einspeisung + netzbezug
    basis_map = sensor_mapping.get("basis", {}) or {}
    await _apply_beitraege(
        basis_beitraege(sensor_mapping),
        lambda feld: f"basis:{feld}",
        basis_map,
        result,
    )

    # 2. Investitionen — Per-Typ-Auswahl im Helper
    investitionen_map = sensor_mapping.get("investitionen", {}) or {}
    for inv_id_str, inv_data in investitionen_map.items():
        if not isinstance(inv_data, dict):
            continue
        inv = investitionen_by_id.get(inv_id_str) or investitionen_by_id.get(str(inv_id_str))
        if inv is None:
            continue
        await _apply_beitraege(
            investition_beitraege(inv, inv_data),
            lambda feld, _id=inv_id_str: f"inv:{_id}:{feld}",
            inv_data,
            result,
        )

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

    Backward-Konvention nach Issue #144 (an kWh-Pfad angeglichen, Etappe 3c P2):
    Slot h = `snap[h] − snap[h-1]` = Inkremente [Vortag-23 + h, ..., Heute-h)
    aufgelaufen seit dem vorherigen Stundenboundary.

    Für jede Stunde h (0..23) wird das Inkrement pro Investition aus zwei
    Snapshots gebildet und über alle Investitionen aufaddiert. Negative Deltas
    (Counter-Reset) werden als 0 gewertet.

    Returns:
        {h: count} für h in 0..23. Fehlt der Snapshot bei beiden Endpunkten
        einer Stunde, ist count None (Lücke). Fehlt der Counter komplett
        (kein Mapping), wird ein leeres Dict zurückgegeben.
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

    rng = BoundaryRange.for_hourly_slots(datum)
    snaps_per_inv: dict[str, dict[int, Optional[float]]] = {}
    for sensor_key, entity_id in relevant_invs:
        snaps: dict[int, Optional[float]] = {}
        for offset in rng.boundary_offsets:
            ts = rng.boundary_at(offset)
            snaps[offset] = await get_snapshot(db, anlage.id, sensor_key, entity_id, ts)
        snaps_per_inv[sensor_key] = snaps

    # Plausibilitäts-Cap pro Stunde: Counter wie WP-Kompressor-Starts haben
    # physikalische Obergrenzen (Mindeststillstand-/-laufzeit), realistisch
    # max. ~20/h. HA-Statistics-Spikes nach Restarts (sum=NULL → state-Fallback,
    # #184) können dagegen Werte in der Größenordnung 10⁴ produzieren, die in
    # einer einzelnen Stunden-Zelle stehenbleiben, während der Tages-Pfad sie
    # über die Boundary-Diff wegfrisst (→ sichtbar als Drift zwischen Tagestab
    # und Stundentab, Forum-Befund Martin 2026-05-11).
    MAX_PLAUSIBLE_COUNTER_PER_HOUR = 200

    result: dict[int, Optional[int]] = {}
    for slot_idx, prev_off, curr_off in rng.slot_pairs:
        any_value = False
        total = 0
        for sensor_key, _ in relevant_invs:
            s0 = snaps_per_inv[sensor_key][prev_off]
            s1 = snaps_per_inv[sensor_key][curr_off]
            if s0 is None or s1 is None:
                continue
            d = s1 - s0
            if d < 0:
                d = 0  # Counter-Reset → 0 (Warnung wäre redundant zur Tages-Aggregation)
            elif d > MAX_PLAUSIBLE_COUNTER_PER_HOUR:
                logger.warning(
                    f"Unplausibler Counter-Spike {feld} für anlage={anlage.id} "
                    f"key={sensor_key} ({datum} h={slot_idx}): {d:.0f} > "
                    f"{MAX_PLAUSIBLE_COUNTER_PER_HOUR} → 0"
                )
                d = 0
            total += int(round(d))
            any_value = True
        result[slot_idx] = total if any_value else None
    return result
