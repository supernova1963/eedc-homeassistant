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
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.tageswert_grund import (
    GRUND_KEINE_ZAEHLERSTAENDE,
    GRUND_NICHT_ZUGEORDNET,
    GRUND_RANG,
    GRUND_ZAEHLER_RUECKSPRUNG,
)
from backend.services.snapshot.boundary_range import BoundaryRange
from backend.services.snapshot.keys import (
    KUMULATIVE_COUNTER_FELDER,
    FLOAT_COUNTER_FELDER,
    extract_quellen_energy,
    feld_hat_zaehler,
)
from backend.services.snapshot.komponenten_beitraege import (
    basis_beitraege,
    basis_hourly_eintraege,
    investition_beitraege,
    investition_hourly_eintraege,
    mqtt_hourly_eintraege,
    pv_je_investition_in_sensor_keys,
    resolve_either_or_eintraege,
    wallbox_deckt_ladung_ab,
)
from backend.services.snapshot.plausibility import (
    cap_pv_einspeisung_stunde,
    schwelle_pv_einspeisung_stunde_kwh,
)
from backend.services.snapshot.reader import (
    MQTT_AKTIV_TAGE,
    get_snapshot,
    mqtt_zaehler_keys,
    zaehler_faellt_im_fenster,
)

logger = logging.getLogger(__name__)


def _investitionen_mit_mapping(sensor_mapping: dict, investitionen_by_id: dict):
    """Jede Investition der Anlage — samt ihrem *womöglich fehlenden* Mapping-Eintrag.

    ⛔ **Warum nicht über `sensor_mapping["investitionen"]` aufzählen** (so lief
    es bis 2026-08-27, in fünf Schleifen dieses Moduls): Auf einer reinen
    MQTT-Anlage steht dort für das Gerät **gar kein Eintrag**.
    `datenquellen_mapping_sync._inv_eintrag` legt den Teilbaum ausdrücklich nur
    bei einer HA-Wahl an (`anlegen=ist_ha`) — eine Inbound-, Gateway- oder
    „keine"-Wahl hinterlässt bewusst kein leeres Gerüst.

    Die Folge war nicht „falsch geprüft", sondern **unsichtbar**: Wärme,
    getrennte Strommessung, Speicher-Netzladung, E-Mob-Anteile und
    Kompressor-Starts blieben in *Cockpit → Tag* leer, obwohl ihre Snapshots
    geschrieben wurden (`writer.py`, `SnapshotSource.MQTT_INBOUND`) — N-328b,
    gemeldet als #396 (gruaGit).

    Die Investitionsliste ist die vollständige Menge und dabei die *bessere*
    Grenze: Sie trägt die Zeitfilterung des Aufrufers (`aktiv_am_tag`), die das
    `sensor_mapping` gar nicht kennt.

    Yields:
        ``(inv_id_str, investition, inv_data)`` — `inv_data` ist ``{}``, wenn
        die Investition keinen Mapping-Eintrag hat.
    """
    investitionen_map = sensor_mapping.get("investitionen", {}) or {}
    for inv_id_str, inv in investitionen_by_id.items():
        if inv is None:
            continue
        inv_data = investitionen_map.get(str(inv_id_str))
        yield str(inv_id_str), inv, inv_data if isinstance(inv_data, dict) else {}


async def _tageswert_aus_raendern(
    db: AsyncSession,
    anlage_id: int,
    sensor_key: str,
    s0: float,
    s1: float,
    ts_start: datetime,
    ts_ende: datetime,
    datum: date,
) -> Optional[float]:
    """Tageswert eines kumulativen Zählers — aus seinen zwei Randständen, und
    bei einem **Rücksprung** aus seiner ganzen Standreihe (SOLL §3.1).

    **Der eine Ort für die Tagesfenster-Regel.** Es gibt zwei Aufrufer, und sie
    hatten die Regel bis 2026-08-26 doppelt: `get_komponenten_tageskwh` (Bilanz)
    und `_tagesdetail_boundary_diff` (Detailzeilen). Genau die F-56-Klasse — und
    an diesem Feld ist sie schon einmal gedriftet.

    ⛔ **Hier stand bis 2026-08-26 `return max(0.0, s1)` für den erkannten
    Reset.** Das war eine **Behauptung ohne Wissen**: Springt der Zähler über
    das Tagesfenster zurück, ist der Tageswert **nicht** der Reststand danach.
    Die Funktion reklamierte im eigenen Docstring „P4: keine Aussage statt
    einer 0" und schrieb dann eine.

    ⛔ **Und der Tag summiert die Reihe NICHT, obwohl der Monat es seit dem
    28.08.2026 tut** (`reader.delta_mit_weg`, N-341). Das ist kein Versehen und
    keine Restschuld:

    * Die **Monatsschicht** las bei einem zurückgesetzten Zähler eine *falsche*
      Zahl (5,6 statt 140 kWh) und zeigte sie an. Dort ist die Summe aus der
      Reihe die Reparatur.
    * Der **Tag** lehnt bereits ab, und diese Ablehnung ist eine abgenommene
      Entscheidung: `soll-waerme-klima.md` §3.1 — *„Ein Zähler mit Tages-Reset
      wird erkannt und abgelehnt, statt still falsche Werte zu erzeugen"* —,
      festgehalten in vier Proben
      (`test_soll_waerme_klima_achse3_aufloesung.py::test_iii1*`).

    Der Weg hierher führt über diese Datei zu `get_betriebsart_strom_tageswerte`
    und damit auf die **Wärme/Klima-Fläche**, wo eine Betriebsart-Teilmenge mit
    3 % Abschlag gegen eine exakte Gesamtmenge stünde (Kanon-Regel K1). Wer den
    Tag umstellen will, entscheidet **zuerst** §3.1 um — nicht diese Zeile.

    ⚠ **Die Stunden-Variante (`get_hourly_kwh_by_category`) bleibt unberührt und
    hat recht.** Dort geht es um den **Slot über Mitternacht**: s0 ist der
    Tagesendwert, s1 die Energie seit dem Reset — eine sinnvolle Zahl für
    *diese Stunde*. Über den **ganzen Tag** kann dieselbe Rechnung nichts
    retten, weil das Fenster zwischen zwei Resets liegt. Gleiche Formel,
    verschiedene Fenster, verschiedene Wahrheit.

    ⭐ **Zwei Erkennungswege, weil ein Reset drei verschiedene Spuren
    hinterlässt:**

    1. **Randdifferenz negativ** — der Rücksprung liegt zwischen den Rändern und
       ist an ihnen selbst ablesbar.
    2. **Monotonie der Zwischenstände verletzt** (`zaehler_faellt_im_fenster`) —
       ein Zwischenstand liegt über dem End- oder unter dem Startstand.

    Weg 2 läuft **immer**, nicht nur bei verdächtig kleinem Delta. Der Grund ist
    der dritte Fall: Werden **beide** Ränder eines Tagesreset-Zählers vor dem
    Reset abgetastet, ist ``d = heutiger Tagesstand − gestriger Tagesstand`` —
    **positiv, plausibel und still falsch**. Weg 1 sieht davon nichts, und ein
    „nur bei d ≈ 0 nachsehen" hätte ihn ebenfalls durchgelassen.
    """
    d = s1 - s0
    if d < -0.01:
        logger.info(
            f"Zähler-Rücksprung über das Tagesfenster für anlage={anlage_id} "
            f"key={sensor_key} ({datum}): {d:.3f} → keine Tagesaussage"
        )
        return None
    if await zaehler_faellt_im_fenster(
        db, anlage_id, sensor_key, ts_start, ts_ende, s0, s1
    ):
        logger.info(
            f"Zähler fällt innerhalb des Tages für anlage={anlage_id} "
            f"key={sensor_key} ({datum}) → Tagesreset-Zähler, keine Tagesaussage"
        )
        return None
    return max(0.0, d)


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
    quellen_energy = extract_quellen_energy(anlage)  # C2b-Read-Through

    # 1. Zähler-Entities sammeln mit Kategorien
    # (sensor_key, entity_id | None, kategorie, fallback_gruppe)
    # entity_id=None bei reinen MQTT-Quellen (Standalone/Docker-Modus)
    eintraege: list[tuple[str, Optional[str], str, Optional[str]]] = []
    seen_keys: set[str] = set()

    # 1a-vorab. Die MQTT-Keys werden schon HIER geholt, obwohl sie erst in 1b
    # verarbeitet werden: die Alles-oder-nichts-Regel für `basis:pv_gesamt`
    # (Stufe 1 zu F-7) muss BEIDE Quellen kennen, bevor der Basis-Beitrag
    # entsteht. Eine gemischte Installation (Aggregat als HA-Sensor, Strings per
    # MQTT) hätte sonst Aggregat UND Einzelzähler in derselben Bilanz — die
    # #290/#298-Doppelzähl-Klasse. Nur geholt, nicht verarbeitet: die
    # Vorrang-Reihenfolge (HA schlägt MQTT über `seen_keys`) bleibt unverändert.
    cutoff = datetime.now() - timedelta(days=MQTT_AKTIV_TAGE)
    mqtt_sks_alle: list[str] = sorted(
        await mqtt_zaehler_keys(db, anlage.id, seit=cutoff)
    )
    pv_extern = pv_je_investition_in_sensor_keys(mqtt_sks_alle)

    # 1a. HA-gemappte Zähler aus sensor_mapping — Feld-Auswahl (Whitelist +
    # Either-Or + parent-Skip) über DIESELBE Normalisierung wie der Daily-Pfad
    # (`*_hourly_eintraege`), nicht mehr über rohe `_categorize_counter`-
    # Aufrufe. Issue #298 (Audit-§6.2, Pattern-Klasse
    # [[feedback_aggregator_symmetrie]]): ein doppelt gemappter E-Auto-Zähler
    # (`verbrauch_kwh` + `ladung_kwh`) wird in der Either-Or-Gruppe aufgelöst
    # statt doppelt summiert.
    basis = sensor_mapping.get("basis", {}) or {}
    for he in basis_hourly_eintraege(
        sensor_mapping, pv_je_investition_extern=pv_extern
    ):
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
    # Die Keys stehen schon oben bereit (`mqtt_sks_alle`, Filter: letzte 7 Tage,
    # um nur aktive Topics zu berücksichtigen).
    # Sie werden seen-gefiltert und über DIESELBE Normalisierung wie
    # der HA-Pfad oben auflösen (#317): inv-Keys laufen durch
    # `investition_hourly_eintraege` mit „MQTT-Key vorhanden" als Verfügbarkeit,
    # damit Whitelist + Either-Or + parent-Skip auch hier greifen. Ein E-Auto mit
    # ladung_kwh UND verbrauch_kwh per MQTT (evcc-Bridge) wird so in der Either-Or-
    # Gruppe aufgelöst statt doppelt gezählt — gleiche #298-Klasse, MQTT-Pfad.
    mqtt_sks = [sk for sk in mqtt_sks_alle if sk not in seen_keys]
    for sk, kat, grp in mqtt_hourly_eintraege(
        mqtt_sks, investitionen_by_id, investitionen_map
    ):
        if sk in seen_keys:
            continue
        eintraege.append((sk, None, kat, grp))  # entity_id=None → MQTT-Fallback
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
            wert = await get_snapshot(
                db, anlage.id, sensor_key, entity_id, ts,
                quellen_energy=quellen_energy,
            )
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
            # Sonstiges-Erzeuger-Anteil separat ausweisen, damit die
            # Performance-Ratio nur die REINE PV-Erzeugung gegen GTI rechnet
            # (`pv` enthält den Sonstiges-Anteil bewusst für die Bilanz).
            "erzeugung_sonstiges": sonst_erz,
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
) -> dict[str, dict[str, float]]:
    """
    Berechnet Tages-Differenzen reiner Counter (KUMULATIVE_COUNTER_FELDER)
    pro Investition aus Snapshot-Differenzen.

    Im Gegensatz zu kWh-Energiezählern, deren stündliches Muster für
    Heatmaps und Bilanz relevant ist, sind Counter wie WP-Kompressor-Starts
    auf Tagesebene aussagekräftig (Wartungs-/Auslegungs-KPI). Daher reicht
    der Tages-Wert: snapshot(Folgetag 00:00) − snapshot(Tag 00:00).

    Returns:
        {feld: {inv_id_str: wert}} z.B. {"wp_starts_anzahl": {"5": 12}}.
        Zähl-Counter (Starts) sind int, Float-Counter (Betriebsstunden,
        FLOAT_COUNTER_FELDER) bleiben gebrochen. Investitionen ohne gemappten
        Counter werden weggelassen.
    """
    sensor_mapping = anlage.sensor_mapping or {}
    quellen_energy = extract_quellen_energy(anlage)  # C2b-Read-Through
    # N-328b: MQTT-gespeiste Zähler mitzählen. `seit=None` — ein Tag im Frühjahr
    # darf nicht daran scheitern, dass das Topic heute schweigt.
    mqtt_keys = await mqtt_zaehler_keys(db, anlage.id)

    tag_start = datetime.combine(datum, datetime.min.time())
    tag_ende = tag_start + timedelta(days=1)

    result: dict[str, dict[str, float]] = {}

    for inv_id_str, inv, inv_data in _investitionen_mit_mapping(
        sensor_mapping, investitionen_by_id
    ):
        counter_felder = KUMULATIVE_COUNTER_FELDER.get(inv.typ, ())
        if not counter_felder:
            continue
        felder = inv_data.get("felder", {}) or {}
        for feld in counter_felder:
            config = felder.get(feld)
            sensor_key = f"inv:{inv_id_str}:{feld}"
            if not feld_hat_zaehler(config, sensor_key, quellen_energy, mqtt_keys):
                continue
            sensor_id = config.get("sensor_id") if isinstance(config, dict) else None
            snap_start = await get_snapshot(
                db, anlage.id, sensor_key, sensor_id, tag_start,
                quellen_energy=quellen_energy,
            )
            snap_ende = await get_snapshot(
                db, anlage.id, sensor_key, sensor_id, tag_ende,
                quellen_energy=quellen_energy,
            )
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
            # Stunden-Counter (#238) gebrochen lassen, Zähl-Counter int runden —
            # konsistent mit dem Stunden-Aggregator (Drift-Vermeidung).
            result.setdefault(feld, {})[inv_id_str] = (
                round(delta_count, 3) if feld in FLOAT_COUNTER_FELDER
                else int(round(delta_count))
            )

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
    quellen_energy = extract_quellen_energy(anlage)  # C2b-Read-Through
    mqtt_keys = await mqtt_zaehler_keys(db, anlage.id)  # N-328b
    rng = BoundaryRange.for_day_total(datum)
    start_off, end_off = rng.boundary_offsets  # (0, 24)
    ts_start = rng.boundary_at(start_off)
    ts_ende = rng.boundary_at(end_off)

    async def _diff(sensor_key: str, sensor_id: Optional[str]) -> Optional[float]:
        s0 = await get_snapshot(
            db, anlage.id, sensor_key, sensor_id, ts_start,
            quellen_energy=quellen_energy,
        )
        s1 = await get_snapshot(
            db, anlage.id, sensor_key, sensor_id, ts_ende,
            quellen_energy=quellen_energy,
        )
        if s0 is None or s1 is None:
            return None
        return await _tageswert_aus_raendern(
            db, anlage.id, sensor_key, s0, s1, ts_start, ts_ende, datum,
        )

    def _cfg_for(feld: str, mapping_quelle: dict):
        return (
            (mapping_quelle.get("felder", {}) or {}).get(feld)
            if "felder" in mapping_quelle else mapping_quelle.get(feld)
        )

    def _sensor_id_for(beitrag, mapping_quelle: dict) -> Optional[str]:
        cfg = _cfg_for(beitrag.feld, mapping_quelle)
        return cfg.get("sensor_id") if isinstance(cfg, dict) else None

    async def _apply_beitraege(beitraege, sensor_key_fn, mapping_quelle, result):
        """Wendet Beiträge auf result an — mit Either-Or-Fallback-Gruppen-Logik."""
        gruppe_genommen: set[str] = set()
        for b in beitraege:
            # Either-Or: pro Gruppe nur den ersten Beitrag mit verfügbarem Delta nehmen
            if b.fallback_gruppe and b.fallback_gruppe in gruppe_genommen:
                continue
            # ⛔ Hier stand bis 2026-08-27 `if not sid: continue` — die Stelle,
            # die einen MQTT-Zähler aus der Tagesbilanz warf (N-328b). Die
            # Verfügbarkeit entscheidet jetzt DAS PRÄDIKAT beim Bau der
            # Beiträge; `sensor_id` ist danach nur noch der HA-Self-Heal-Weg
            # und darf None sein (`get_snapshot` fällt dann über den
            # `sensor_key` auf MQTT zurück).
            sid = _sensor_id_for(b, mapping_quelle)
            d = await _diff(sensor_key_fn(b.feld), sid)
            if d is None:
                continue
            if b.fallback_gruppe:
                gruppe_genommen.add(b.fallback_gruppe)
            result[b.target_key] = result.get(b.target_key, 0.0) + b.vorzeichen * d

    result: dict[str, float] = {}

    # 1. Basis: einspeisung + netzbezug + PV gesamt (letzteres nur, wenn kein
    #    Erzeuger einen eigenen Zähler trägt — s. `basis_beitraege`).
    #
    # ⛔ **Hier stand bis 2026-08-27 das Gegenteil**: „Anders als der Hourly-Pfad
    # braucht diese Funktion KEINE MQTT-Gegenprobe … ein rein per MQTT gespeister
    # Zähler je Erzeuger existiert hier also gar nicht." Der Satz beschrieb den
    # **Defekt** und begründete ihn: Weil MQTT hier nicht existierte, blieb die
    # Tagesbilanz einer Standalone-Anlage leer, während der Stundenpfad daneben
    # gefüllt war (N-328b/#396). Existiert MQTT aber, dann **muss** auch die
    # Alles-oder-nichts-Regel für `pv_gesamt` beide Quellen kennen — sonst stünde
    # das Anlagen-Aggregat neben seinen eigenen Summanden (#290/#298).
    basis_map = sensor_mapping.get("basis", {}) or {}
    pv_extern = pv_je_investition_in_sensor_keys(mqtt_keys)
    await _apply_beitraege(
        basis_beitraege(
            sensor_mapping,
            pv_je_investition_extern=pv_extern,
            ist_verfuegbar=lambda feld: feld_hat_zaehler(
                basis_map.get(feld), f"basis:{feld}", quellen_energy, mqtt_keys,
            ),
        ),
        lambda feld: f"basis:{feld}",
        basis_map,
        result,
    )

    # 2. Investitionen — Per-Typ-Auswahl im Helper
    # N-196: strukturelle Quellen-Regel der E-Mob-Fläche, einmal je Lauf —
    # dieselbe Regel, die der Leistungspfad seit #356 kennt.
    _wb_deckt = wallbox_deckt_ladung_ab(investitionen_by_id.values(), sensor_mapping)
    for inv_id_str, inv, inv_data in _investitionen_mit_mapping(
        sensor_mapping, investitionen_by_id
    ):
        felder = inv_data.get("felder", {}) or {}
        await _apply_beitraege(
            investition_beitraege(
                inv, inv_data, wallbox_deckt_ladung=_wb_deckt,
                ist_verfuegbar=lambda feld, _id=inv_id_str, _f=felder: feld_hat_zaehler(
                    _f.get(feld), f"inv:{_id}:{feld}", quellen_energy, mqtt_keys,
                ),
            ),
            lambda feld, _id=inv_id_str: f"inv:{_id}:{feld}",
            inv_data,
            result,
        )

    return result


async def _tagesdetail_boundary_diff_mit_grund(
    db: AsyncSession,
    anlage,
    quellen_energy,
    sensor_key: str,
    sensor_id: Optional[str],
    ts_start: datetime,
    ts_ende: datetime,
    datum: date,
) -> tuple[Optional[float], Optional[str]]:
    """Boundary-Diff eines kumulativen kWh-Zählers über das HA-Tagesfenster.

    **Warum als Modul-Funktion und nicht als Closure** (#263): Sie hat zwei
    Aufrufer — `get_tagesdetail_kwh` und `get_betriebsart_strom_tageswerte`.
    Beide brauchen dieselbe Tagesreset-Behandlung; sie ein zweites Mal
    hinzuschreiben wäre die F-56-Klasse (*„eine Regel, die an zwei Stellen
    nachgebaut wird, driftet"*), und ausgerechnet an diesem Feld ist sie schon
    einmal gedriftet.
    """
    s0 = await get_snapshot(
        db, anlage.id, sensor_key, sensor_id, ts_start,
        quellen_energy=quellen_energy,
    )
    s1 = await get_snapshot(
        db, anlage.id, sensor_key, sensor_id, ts_ende,
        quellen_energy=quellen_energy,
    )
    if s0 is None or s1 is None:
        return None, GRUND_KEINE_ZAEHLERSTAENDE
    wert = await _tageswert_aus_raendern(
        db, anlage.id, sensor_key, s0, s1, ts_start, ts_ende, datum,
    )
    # W-18: `_tageswert_aus_raendern` gibt bei einem Rücksprung bewusst `None`
    # zurück und schreibt eine Logzeile — die kein Anwender sieht. Hier bekommt
    # derselbe Zustand einen Namen, damit die Oberfläche ihn aussprechen kann.
    if wert is None:
        return None, GRUND_ZAEHLER_RUECKSPRUNG
    return wert, None


async def _tagesdetail_boundary_diff(
    db: AsyncSession,
    anlage,
    quellen_energy,
    sensor_key: str,
    sensor_id: Optional[str],
    ts_start: datetime,
    ts_ende: datetime,
    datum: date,
) -> Optional[float]:
    """Nur der Wert — für Aufrufer, die den Grund nicht brauchen.

    ⚠ **Kein zweiter Rechenweg**: ein Durchreicher auf
    {@link _tagesdetail_boundary_diff_mit_grund}. Die Tagesreset-Behandlung
    steht weiterhin genau einmal im Baum (F-56).
    """
    wert, _grund = await _tagesdetail_boundary_diff_mit_grund(
        db, anlage, quellen_energy, sensor_key, sensor_id,
        ts_start, ts_ende, datum,
    )
    return wert


async def get_betriebsart_strom_tageswerte(
    db: AsyncSession,
    anlage,
    investitionen_by_id: dict,
    datum: date,
) -> dict[str, dict[str, float]]:
    """Tages-kWh der **gemessenen** Betriebsart-Zähler, je Wärmepumpe (#263).

    **Warum je Investition und nicht als anlagenweite Σ** — anders als jedes
    andere Feld in `get_tagesdetail_kwh`: Die Regel *gemessen schlägt
    abgeleitet* gilt **ganz oder gar nicht je Zeile**
    (`core/berechnungen/betriebsart_gemessen.py`). Eine Anlage darf eine
    Klimaanlage mit Betriebsart-Zählern und eine Wärmepumpe ohne haben; erst
    die Auflösung je Gerät entscheidet, welcher der beiden Wege für dieses
    Gerät gilt. Eine vorab gebildete Summe hätte diese Entscheidung schon
    verloren.

    ⚠ **Die Feldnamen bleiben unangetastet — samt Innengerät-Suffix**
    (`betriebsart_strom_kuehlen_kwh-3`). Das Ergebnis-Dict geht unverändert in
    `modus_strom_zeile()`, und dort löst `_aufgeloest` die Regel *Gerätefeld
    gewinnt, sonst Σ Innengeräte* auf. Sie hier vorab zu summieren würde genau
    diese Regel ein zweites Mal implementieren — und „Gerätefeld + Innengeräte"
    wäre die Doppelzählungs-Klasse, die der Modul-Kopf dort ausdrücklich
    ausschließt.

    Returns:
        ``{inv_id_str: {feldname: kwh}}`` — nur Wärmepumpen mit mindestens
        einem gemappten Betriebsart-Zähler **und** vorhandenen Snapshots.
        Fehlt beides, fehlt der Eintrag (P4: keine Aussage statt einer 0).
    """
    from backend.core.betriebsmodus import ist_betriebsart_strom_feld

    sensor_mapping = anlage.sensor_mapping or {}
    quellen_energy = extract_quellen_energy(anlage)  # C2b-Read-Through
    mqtt_keys = await mqtt_zaehler_keys(db, anlage.id)  # N-328b
    rng = BoundaryRange.for_day_total(datum)
    start_off, end_off = rng.boundary_offsets  # (0, 24)
    ts_start = rng.boundary_at(start_off)
    ts_ende = rng.boundary_at(end_off)

    ergebnis: dict[str, dict[str, float]] = {}
    for inv_id_str, inv, inv_data in _investitionen_mit_mapping(
        sensor_mapping, investitionen_by_id
    ):
        if getattr(inv, "typ", None) != "waermepumpe":
            continue
        felder = inv_data.get("felder", {}) or {}
        # N-328b: Die Feldnamen kommen aus BEIDEN Ablagen. Ein per MQTT
        # gespeister Betriebsart-Zähler steht nicht in `felder` — sein
        # `sensor_key` steht in `mqtt_keys`, und nur dort. Wer allein über
        # `felder` iteriert, sieht ihn nie.
        praefix = f"inv:{inv_id_str}:"
        kandidaten = set(felder) | {
            sk[len(praefix):] for sk in mqtt_keys if sk.startswith(praefix)
        }
        je_inv: dict[str, float] = {}
        for feld in sorted(kandidaten):
            if not ist_betriebsart_strom_feld(feld):
                continue
            cfg = felder.get(feld)
            if not feld_hat_zaehler(cfg, praefix + feld, quellen_energy, mqtt_keys):
                continue
            d = await _tagesdetail_boundary_diff(
                db, anlage, quellen_energy,
                praefix + feld, cfg.get("sensor_id") if isinstance(cfg, dict) else None,
                ts_start, ts_ende, datum,
            )
            if d is None:
                continue
            je_inv[feld] = d
        if je_inv:
            ergebnis[str(inv_id_str)] = je_inv
    return ergebnis


@dataclass(frozen=True)
class TagesDetail:
    """Die Tages-Detailwerte **und warum die fehlenden fehlen** (W-18).

    ⛔ **Warum das ein Rückgabetyp ist und kein zweiter Aufruf.** Der Grund
    entsteht aus derselben Zuordnung, denselben Snapshots und derselben
    Tagesreset-Behandlung wie der Wert. Eine zweite Funktion, die dieselben
    Regeln noch einmal abläuft, wäre die F-56-Klasse — und sie würde
    zuverlässig genau dann driften, wenn eine der drei Regeln sich ändert.
    """

    #: ``{ausgabe_key: Σ_kwh}`` — wie bisher, nur Felder mit Wert.
    werte: dict[str, float]
    #: ``{ausgabe_key: grund}`` für Keys **ohne** Wert. Nie beides zugleich.
    grund_je_feld: dict[str, str]


async def get_tagesdetail_kwh(
    db: AsyncSession,
    anlage,
    investitionen_by_id: dict,
    datum: date,
) -> "TagesDetail":
    """Tages-kWh für Felder, die `get_komponenten_tageskwh` bewusst NICHT separat
    ausweist, die aber Cockpit/Tag für die Detailzeilen braucht (D1 „maximal
    erheben", SPEC-COCKPIT-TAG-JAHR Abschnitt F):

      - WP `strom_heizen_kwh` / `strom_warmwasser_kwh` (getrennte Strommessung) —
        in der Bilanz zu EINEM `waermepumpe_<id>`-Key zusammengefasst.
      - Speicher `ladung_netz_kwh` (Arbitrage) — in der Bilanz bewusst
        ausgeschlossen (Teilmenge von `ladung_kwh`, Doppelzähl-Schutz).

    Boundary-Diff über das HA-Tagesfenster `[Tag 00:00, Folgetag 00:00)`,
    identisch zu `get_komponenten_tageskwh` (gleiche Tagesreset-Behandlung). Summe
    über alle aktiven Investitionen des Typs. Liefert `{feld: Σ_kwh}` nur für
    tatsächlich als Sensor gemappte Felder mit Snapshot-Daten — fehlt das
    Mapping/der Snapshot, fehlt das Feld (Aufrufer lässt es weg, kein „—"-Clutter).

    ⛔ **Seit W-18 liefert sie zusätzlich den GRUND** ({@link TagesDetail}).
    „Fehlt das Feld, fehlt es eben" war die Bauform, die dietmar1968 einen
    falschen Ratschlag gezeigt hat: Der Client hängte an jedes „—" denselben
    fest verdrahteten Satz *„Sensor zuordnen"* — auch dem Anwender, der
    zugeordnet hatte. Die Erhebung **weiß**, welcher der drei Zustände vorliegt;
    sie hat es bisher nur nicht gesagt.
    """
    sensor_mapping = anlage.sensor_mapping or {}
    quellen_energy = extract_quellen_energy(anlage)  # C2b-Read-Through
    mqtt_keys = await mqtt_zaehler_keys(db, anlage.id)  # N-328b
    rng = BoundaryRange.for_day_total(datum)
    start_off, end_off = rng.boundary_offsets  # (0, 24)
    ts_start = rng.boundary_at(start_off)
    ts_ende = rng.boundary_at(end_off)

    async def _diff(
        sensor_key: str, sensor_id: Optional[str],
    ) -> tuple[Optional[float], Optional[str]]:
        return await _tagesdetail_boundary_diff_mit_grund(
            db, anlage, quellen_energy, sensor_key, sensor_id,
            ts_start, ts_ende, datum,
        )

    # (typ, mapping-feld) → semantischer Ausgabe-Key. Alle Felder sind in
    # KUMULATIVE_ZAEHLER_FELDER, also per Boundary-Diff erhebbar. Wichtig: speicher-
    # und emob-`ladung_netz_kwh` sind verschiedene Begriffe → getrennte Ausgabe-Keys
    # (sonst Vermischung). Wallbox + E-Auto fließen in DENSELBEN emob-Key (Σ).
    AUSGABE = {
        ("waermepumpe", "strom_heizen_kwh"): "wp_strom_heizen_kwh",
        ("waermepumpe", "strom_warmwasser_kwh"): "wp_strom_warmwasser_kwh",
        # thermische Wärme (nur mit Wärmemengenzähler-Sensor; in der Bilanz
        # ausgeschlossen, hier für Tages-JAZ/Wärme).
        ("waermepumpe", "heizenergie_kwh"): "wp_heizung_kwh",
        ("waermepumpe", "warmwasser_kwh"): "wp_warmwasser_kwh",
        ("speicher", "ladung_netz_kwh"): "speicher_ladung_netz_kwh",
        ("wallbox", "ladung_pv_kwh"): "emob_ladung_pv_kwh",
        ("wallbox", "ladung_netz_kwh"): "emob_ladung_netz_kwh",
        ("e-auto", "ladung_pv_kwh"): "emob_ladung_pv_kwh",
        ("e-auto", "ladung_netz_kwh"): "emob_ladung_netz_kwh",
    }
    summen: dict[str, float] = {}
    # W-18: Warum ein Ausgabe-Key FEHLT — je Key der Zustand, der ihn verhindert
    # hat. Er entsteht in **derselben** Schleife wie der Wert; eine zweite
    # Schleife mit denselben Regeln wäre die F-56-Klasse.
    #
    # ⚠ **Der schwächste Grund gewinnt, und das ist Absicht.** Ein Ausgabe-Key
    # kann mehrere Geräte tragen (`emob_ladung_pv_kwh` = Wallbox + E-Auto).
    # Liefert eines davon einen Wert, ist die Zahl da und es gibt nichts zu
    # erklären; nur wenn KEIN Gerät geliefert hat, wird ein Grund genannt — und
    # dann der aussagekräftigste: „zugeordnet, aber leer" schlägt „nicht
    # zugeordnet", denn das ist der Fall, den der Anwender nicht selbst sieht.
    grund_kandidat: dict[str, str] = {}

    def _merke_grund(out_key: str, grund: str) -> None:
        vorher = grund_kandidat.get(out_key)
        if vorher is None or GRUND_RANG[grund] > GRUND_RANG[vorher]:
            grund_kandidat[out_key] = grund

    for inv_id_str, inv, inv_data in _investitionen_mit_mapping(
        sensor_mapping, investitionen_by_id
    ):
        typ = getattr(inv, "typ", None)
        # E-Auto mit parent (Wallbox misst die Ladung) → Skip, sonst Doppelzählung
        # (spiegelt investition_beitraege/Live-Pfad).
        if typ == "e-auto" and getattr(inv, "parent_investition_id", None) is not None:
            continue
        felder = inv_data.get("felder", {}) or {}
        for (t, feld), out_key in AUSGABE.items():
            if t != typ:
                continue
            cfg = felder.get(feld)
            sensor_key = f"inv:{inv_id_str}:{feld}"
            # ⛔ N-328b: Hier entschied bis 2026-08-27 `strategie == "sensor"`,
            # ob das Feld überhaupt erhoben wird — und wer per MQTT misst, bekam
            # von W-18 den Grund „Kein Zähler zugeordnet" zu lesen, obwohl seine
            # Zählerstände in der Datenbank standen. Der Grund war damit nicht
            # nur nutzlos, sondern **falsch**: Er riet zu einer Zuordnung, die
            # es gar nicht braucht.
            if not feld_hat_zaehler(cfg, sensor_key, quellen_energy, mqtt_keys):
                _merke_grund(out_key, GRUND_NICHT_ZUGEORDNET)
                continue
            d, grund = await _diff(
                sensor_key, cfg.get("sensor_id") if isinstance(cfg, dict) else None,
            )
            if d is None:
                _merke_grund(out_key, grund or GRUND_KEINE_ZAEHLERSTAENDE)
                continue
            summen[out_key] = summen.get(out_key, 0.0) + d

    return TagesDetail(
        werte=summen,
        # Ein Key mit Wert braucht keine Erklärung — und ein Grund neben einer
        # vorhandenen Zahl wäre ein Widerspruch auf der Fläche.
        grund_je_feld={k: g for k, g in grund_kandidat.items() if k not in summen},
    )


async def get_hourly_counter_sum_by_feld(
    db: AsyncSession,
    anlage,
    investitionen_by_id: dict,
    datum: date,
    feld: str,
) -> dict[int, Optional[float]]:
    """
    Berechnet Stunden-Counter-Summen für ein bestimmtes Feld (z.B. 'wp_starts_anzahl'),
    summiert über alle Investitionen mit gemapptem Counter.

    Zähl-Counter (Starts) werden ganzzahlig summiert; Float-Counter aus
    FLOAT_COUNTER_FELDER (z.B. Betriebsstunden, #238 — 0..1 h pro WP und Stunde)
    behalten ihre Nachkommastellen (3 Stellen). Diese Entscheidung teilt sich der
    Stunden-Aggregator mit dem Tages-Aggregator, damit Tages- und Stundensicht
    nicht auseinanderdriften.

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
    quellen_energy = extract_quellen_energy(anlage)  # C2b-Read-Through
    mqtt_keys = await mqtt_zaehler_keys(db, anlage.id)  # N-328b

    relevant_invs: list[tuple[str, Optional[str]]] = []  # (sensor_key, sensor_id)
    for inv_id_str, inv, inv_data in _investitionen_mit_mapping(
        sensor_mapping, investitionen_by_id
    ):
        if feld not in KUMULATIVE_COUNTER_FELDER.get(inv.typ, ()):
            continue
        felder = inv_data.get("felder", {}) or {}
        config = felder.get(feld)
        sensor_key = f"inv:{inv_id_str}:{feld}"
        if not feld_hat_zaehler(config, sensor_key, quellen_energy, mqtt_keys):
            continue
        relevant_invs.append(
            (sensor_key, config.get("sensor_id") if isinstance(config, dict) else None)
        )

    if not relevant_invs:
        return {}

    rng = BoundaryRange.for_hourly_slots(datum)
    snaps_per_inv: dict[str, dict[int, Optional[float]]] = {}
    for sensor_key, entity_id in relevant_invs:
        snaps: dict[int, Optional[float]] = {}
        for offset in rng.boundary_offsets:
            ts = rng.boundary_at(offset)
            snaps[offset] = await get_snapshot(
                db, anlage.id, sensor_key, entity_id, ts,
                quellen_energy=quellen_energy,
            )
        snaps_per_inv[sensor_key] = snaps

    # Plausibilitäts-Cap pro Stunde: Counter wie WP-Kompressor-Starts haben
    # physikalische Obergrenzen (Mindeststillstand-/-laufzeit), realistisch
    # max. ~20/h. HA-Statistics-Spikes nach Restarts (sum=NULL → state-Fallback,
    # #184) können dagegen Werte in der Größenordnung 10⁴ produzieren, die in
    # einer einzelnen Stunden-Zelle stehenbleiben, während der Tages-Pfad sie
    # über die Boundary-Diff wegfrisst (→ sichtbar als Drift zwischen Tagestab
    # und Stundentab, Forum-Befund Martin 2026-05-11).
    MAX_PLAUSIBLE_COUNTER_PER_HOUR = 200

    as_float = feld in FLOAT_COUNTER_FELDER
    result: dict[int, Optional[float]] = {}
    for slot_idx, prev_off, curr_off in rng.slot_pairs:
        any_value = False
        total = 0.0
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
            total += d if as_float else int(round(d))
            any_value = True
        if not any_value:
            result[slot_idx] = None
        else:
            result[slot_idx] = round(total, 3) if as_float else int(total)
    return result
