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
from backend.services.ha_statistics_service import get_ha_statistics_service

from backend.services.snapshot.keys import (
    KUMULATIVE_COUNTER_FELDER,
    extract_quellen_energy,
    feld_hat_zaehler,
    ist_stand_sensor_key,
    resolve_energy_ha_eid,
)
from backend.services.snapshot.reader import (
    MQTT_AKTIV_TAGE,
    mqtt_zaehler_keys,
)
from backend.services.snapshot.komponenten_beitraege import (
    basis_hourly_eintraege,
    investition_hourly_eintraege,
    mqtt_hourly_eintraege,
    wallbox_deckt_ladung_ab,
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

    # Counter-Entries sammeln — Feld-Auswahl (Whitelist + Either-Or +
    # parent-Skip) über DIESELBE Normalisierung wie die beiden Hourly-
    # Aggregatoren (Issue #298, Audit-§6.2, Pattern-Klasse
    # [[feedback_aggregator_symmetrie]]). Die Vorschau-Tabelle zeigte vorher für
    # doppelt gemappte E-Autos (`verbrauch_kwh` + `ladung_kwh`, evcc/#262)
    # verdoppelte Tagesummen — die Either-Or-Auflösung unten räumt das pro
    # Spalte (alt/neu) auf, deckungsgleich mit dem späteren Reload-Schreibwert.
    eintraege: list[tuple[str, Optional[str], str, Optional[str]]] = []
    seen_keys: set[str] = set()
    # C2b-Read-Through (HA-only-Pfad): die „neu"-Spalte (HA-Stats-Projektion des
    # Reloads) liest die zugeordnete Entity; MQTT-/keine-zugeordnete Felder haben
    # keine HA-„neu"-Projektion (entity → None). Die „alt"-Spalte (DB-Lookup per
    # sensor_key) bleibt quellen-agnostisch unverändert.
    quellen_energy = extract_quellen_energy(anlage)

    # MQTT-Keys vorab (identisch zum Snapshot-Aggregator).
    # ⛔ Bis #406 stand hier zusätzlich die Alles-oder-nichts-Regel für
    # `basis:pv_gesamt` (Stufe 1 zu F-7). Sie ist entfallen; die Vorschau zeigt
    # jetzt beide Quellen als Zeilen und damit genau das, was der Lauf liest.
    # ⚠ **Die Vorschau wählt bewusst NICHT selbst.** Sie ist eine
    # Gegenüberstellung „alt gegen neu" JE ZÄHLER — welche Quelle den Tag
    # trägt, entscheidet der Aggregator. Eine zweite Wahl hier wäre ein zweiter
    # Rechenweg und könnte von seiner abweichen.
    cutoff = datetime.now() - timedelta(days=MQTT_AKTIV_TAGE)
    mqtt_sks_alle: list[str] = sorted(
        await mqtt_zaehler_keys(db, anlage.id, seit=cutoff)
    )

    basis = sensor_mapping.get("basis", {}) or {}
    for he in basis_hourly_eintraege(sensor_mapping):
        cfg = basis.get(he.feld)
        if isinstance(cfg, dict):
            eid = cfg.get("sensor_id")
            if eid:
                sk = f"basis:{he.feld}"
                eid_eff, behalten = resolve_energy_ha_eid(quellen_energy, sk, eid)
                eintraege.append((sk, eid_eff if behalten else None,
                                  he.kategorie, he.fallback_gruppe))
                seen_keys.add(sk)

    investitionen_map = sensor_mapping.get("investitionen", {}) or {}
    # N-555 (Konzept Regel 6): dieselbe Auswahl wie der Stunden-Aggregator —
    # Wallbox-Regel in der Stunde, E-Auto-Felder über HA und MQTT gemeinsam gewählt.
    _mqtt_sk_set = set(mqtt_sks_alle)

    def _hat_zaehler(inv_id: str, feld: str) -> bool:
        _felder = ((investitionen_map.get(inv_id) or {}).get("felder") or {})
        return feld_hat_zaehler(
            _felder.get(feld), f"inv:{inv_id}:{feld}", quellen_energy, _mqtt_sk_set,
        )

    def _auswahl(inv_id: str):
        return lambda feld: _hat_zaehler(inv_id, feld)

    _wb_deckt = wallbox_deckt_ladung_ab(
        investitionen_by_id.values(), sensor_mapping,
        ist_verfuegbar=lambda inv, feld: _hat_zaehler(str(inv.id), feld),
        datum=datum,
    )
    for inv_id_str, inv_data in investitionen_map.items():
        if not isinstance(inv_data, dict):
            continue
        inv = investitionen_by_id.get(inv_id_str) or investitionen_by_id.get(str(inv_id_str))
        if inv is None:
            continue
        felder = inv_data.get("felder", {}) or {}
        for he in investition_hourly_eintraege(
            inv, inv_data, wallbox_deckt_ladung=_wb_deckt,
            auswahl_verfuegbar=_auswahl(str(inv_id_str)),
        ):
            cfg = felder.get(he.feld)
            if isinstance(cfg, dict):
                eid = cfg.get("sensor_id")
                if eid:
                    sk = f"inv:{inv_id_str}:{he.feld}"
                    eid_eff, behalten = resolve_energy_ha_eid(quellen_energy, sk, eid)
                    eintraege.append((sk, eid_eff if behalten else None,
                                      he.kategorie, he.fallback_gruppe))
                    seen_keys.add(sk)

    # MQTT-Keys (oben geholt) über DIESELBE Normalisierung wie der HA-Pfad
    # auflösen (#317), damit die Vorschau-Tabelle ein doppelt per MQTT gemapptes
    # E-Auto (ladung_kwh + verbrauch_kwh) in der Either-Or-Gruppe auflöst statt
    # doppelt summiert — deckungsgleich mit dem Snapshot-Hourly-Schreibwert.
    mqtt_sks = [sk for sk in mqtt_sks_alle if sk not in seen_keys]
    for sk, kat, grp in mqtt_hourly_eintraege(
        mqtt_sks, investitionen_by_id, investitionen_map,
        wallbox_deckt_ladung=_wb_deckt, auswahl_je_inv=_auswahl,
    ):
        if sk in seen_keys:
            continue
        eintraege.append((sk, None, kat, grp))
        seen_keys.add(sk)

    ha_svc = get_ha_statistics_service()
    ha_verfuegbar = ha_svc.is_available

    tag_0 = datetime.combine(datum, datetime.min.time())
    boundaries: list[dict] = []

    # Pro Counter, pro Stunde -1..24: alt aus DB (5min Toleranz), neu aus HA-Stats
    # h=-1 ist Vortag 23:00 (Slot-0-Boundary), h=24 ist Folgetag 00:00 (für etwaige
    # Folgetags-Slot-0-Berechnung — aber primär brauchen wir h=-1..23 für Slot 0..23).
    # Wir liefern 25 Boundaries (h=-1..23), das deckt Slot 0..23 ab.
    snap_alt: dict[str, dict[int, Optional[float]]] = {sk: {} for sk, _, _, _ in eintraege}
    snap_neu: dict[str, dict[int, Optional[float]]] = {sk: {} for sk, _, _, _ in eintraege}

    for sensor_key, entity_id, kat, _grp in eintraege:
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
                neu = ha_svc.get_value_at(
                    entity_id, zp, toleranz_minuten=10,
                    als_stand=ist_stand_sensor_key(sensor_key),
                )
            snap_neu[sensor_key][h] = neu

            boundaries.append({
                "sensor_key": sensor_key,
                "kategorie": kat,
                "zeitpunkt": zp,
                "alt_kwh": alt,
                "neu_kwh": neu,
            })

    # ── Stunden alt/neu (Zählerlücken wie HA, Ü7) ─────────────────────────────
    # ⭐ **„neu" ist, was der Lauf schreiben WÜRDE — über dieselbe Tagestabelle
    # wie der Aggregator** (R5): HA erreichbar ⇒ die HA-Slot-Tabelle
    # (`lts_tagestabelle`, der Lauf liest nach dem Resnap genau sie), sonst die
    # Snapshot-Tabelle aus den gespeicherten Ständen. **„alt" ist, was gespeichert
    # ist** — die Stundenzeilen (`TagesEnergieProfil`), nicht noch einmal
    # gerechnet. Bis zum Umbau rechnete die Vorschau beide Spalten mit einer
    # eigenen Slot-Arithmetik aus den Snapshots (Nachbarstände, eine Lücke leerte
    # zwei Slots) — eine zweite Rechnung neben dem Lauf, die mit dem Umbau
    # auseinandergelaufen wäre („Vorschau sagt 69, Ergebnis 39").
    #
    # Die Zeilen sind je **Achse** (pv · einspeisung · netzbezug · batterie ·
    # waermepumpe · wallbox), dieselben Größen wie die Spalten der Stundenzeile;
    # Batterie mit deren Vorzeichen (Entladung positiv). `spanne_neu` sagt, wie
    # viele reale Stunden der neue Wert trägt — eine Stunde nach einer Lücke
    # zeigt dort ihre Energie „aus der Lücke".
    from backend.core.berechnungen import batterie_kw_spalte
    from backend.models.tages_energie_profil import TagesEnergieProfil
    from backend.services.snapshot import aggregator as _snapshot_aggregator
    from backend.services.snapshot import lts_aggregator as _lts_aggregator

    tep_alt = {
        r.stunde: r for r in (await db.execute(
            select(TagesEnergieProfil).where(
                TagesEnergieProfil.anlage_id == anlage.id,
                TagesEnergieProfil.datum == datum,
            )
        )).scalars().all()
    }
    tabelle_neu = None
    if ha_verfuegbar:
        tabelle_neu = await _lts_aggregator.lts_tagestabelle(anlage, investitionen_by_id, datum)
    if tabelle_neu is None:
        tabelle_neu = await _snapshot_aggregator.snapshot_tagestabelle(
            db, anlage, investitionen_by_id, datum,
        )
    stunden_neu = tabelle_neu.stunden if tabelle_neu is not None else {}

    _ACHSEN_VORSCHAU = (
        ("pv", "pv_kw", lambda z: z.get("pv")),
        ("einspeisung", "einspeisung_kw", lambda z: z.get("einspeisung")),
        ("netzbezug", "netzbezug_kw", lambda z: z.get("netzbezug")),
        ("batterie", "batterie_kw", lambda z: batterie_kw_spalte(z.get("batterie_netto"))),
        ("waermepumpe", "waermepumpe_kw", lambda z: z.get("wp")),
        ("wallbox", "wallbox_kw", lambda z: z.get("wallbox")),
    )
    slot_deltas: list[dict] = []
    tagesumme_alt: dict[str, Optional[float]] = {}
    tagesumme_neu: dict[str, Optional[float]] = {}
    for h in range(24):
        zeile_alt = tep_alt.get(h)
        zeile_neu = stunden_neu.get(h) or {}
        spannen_neu = zeile_neu.get("spannen") or {}
        for achse, spalte, neu_fn in _ACHSEN_VORSCHAU:
            alt = getattr(zeile_alt, spalte, None) if zeile_alt is not None else None
            neu = neu_fn(zeile_neu)
            neu = round(neu, 3) if neu is not None else None
            if alt is None and neu is None:
                continue
            slot_deltas.append({
                "stunde": h,
                "kategorie": achse,
                "alt_kwh": alt,
                "neu_kwh": neu,
                "spanne_neu": spannen_neu.get(achse),
            })
            if alt is not None:
                tagesumme_alt[achse] = (tagesumme_alt.get(achse) or 0.0) + alt
            if neu is not None:
                tagesumme_neu[achse] = (tagesumme_neu.get(achse) or 0.0) + neu

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

    # N-328b: auch hier zählte bis zum 27.08. nur ein HA-Sensor als Zähler. Die
    # „alt"-Spalte liest den SensorSnapshot per `sensor_key` und ist damit
    # quellen-agnostisch — sie blieb für einen MQTT-Anwender trotzdem leer, weil
    # sein Feld gar nicht erst aufgezählt wurde. Die „neu"-Projektion bleibt
    # HA-only und sagt das selbst (`resolve_energy_ha_eid` → `behalten=False`).
    for inv_id_str, inv in investitionen_by_id.items():
        if inv is None:
            continue
        inv_id_str = str(inv_id_str)
        counter_felder = KUMULATIVE_COUNTER_FELDER.get(inv.typ, ())
        if not counter_felder:
            continue
        inv_data = investitionen_map.get(inv_id_str)
        felder = (inv_data.get("felder", {}) or {}) if isinstance(inv_data, dict) else {}
        for feld in counter_felder:
            config = felder.get(feld)
            sensor_key = f"inv:{inv_id_str}:{feld}"
            if not feld_hat_zaehler(
                config, sensor_key, quellen_energy, set(mqtt_sks_alle)
            ):
                continue
            entity_id = config.get("sensor_id") if isinstance(config, dict) else None

            alt_start = await _db_snap_at(sensor_key, tag_0)
            alt_ende = await _db_snap_at(sensor_key, tag_ende)
            if alt_start is not None and alt_ende is not None:
                d = alt_ende - alt_start
                if d >= 0:
                    counter_alt_per_feld[feld] = counter_alt_per_feld.get(feld, 0) + int(round(d))

            # C2b: „neu"-Projektion liest die zugeordnete HA-Entity; MQTT-/keine-
            # zugeordnete Counter haben keine HA-„neu"-Projektion.
            neu_entity, behalten = resolve_energy_ha_eid(quellen_energy, sensor_key, entity_id)
            if ha_verfuegbar and behalten and neu_entity:
                _stand = ist_stand_sensor_key(sensor_key)
                neu_start = ha_svc.get_value_at(
                    neu_entity, tag_0, toleranz_minuten=10, als_stand=_stand)
                neu_ende = ha_svc.get_value_at(
                    neu_entity, tag_ende, toleranz_minuten=10, als_stand=_stand)
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
