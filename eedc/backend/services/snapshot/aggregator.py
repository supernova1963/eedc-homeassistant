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
from dataclasses import dataclass, field as dc_field
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.berechnungen.betriebsart_gemessen import (
    geraetefeld_oder_innengeraete,
)
from backend.core.betriebsmodus import BETRIEBSART_NUTZENERGIE_FELD, HEIZEN, KUEHLEN
from backend.core.field_definitions import FEINE_STROM_FELDER, WP_GESAMT_STROM_FELDER
from backend.core.berechnungen.stundenbilanz import (
    berechne_batterie_netto_kwh,
    stunden_verbrauch_kwh,
)
from backend.core.tageswert_grund import (
    GRUND_KEINE_ZAEHLERSTAENDE,
    GRUND_NICHT_ZUGEORDNET,
    GRUND_RANG,
    GRUND_ZAEHLER_RUECKSPRUNG,
)
from backend.services.snapshot.boundary_range import BoundaryRange, tagesfenster_fuer
from backend.services.snapshot.keys import (
    KUMULATIVE_COUNTER_FELDER,
    FLOAT_COUNTER_FELDER,
    PV_AGGREGAT_BASIS_FELD,
    extract_quellen_energy,
    feld_hat_zaehler,
    innengeraet_felder,
    zaehler_feld_kandidaten,
)
from backend.core.berechnungen.pv_tages_praezedenz import (
    QUELLE_AGGREGAT,
    QUELLE_EINZEL,
    erwartete_erzeuger_ids,
    waehle_pv_quelle,
)
from backend.core.berechnungen.erzeuger_traeger import (
    bkw_restwerte,
    ergaenze_kinder_deckung,
)
from backend.services.snapshot.komponenten_beitraege import (
    basis_beitraege,
    basis_hourly_eintraege,
    investition_beitraege,
    investition_hourly_eintraege,
    mqtt_hourly_eintraege,
    loese_pv_tageswerte_auf,
    resolve_either_or_eintraege,
    wallbox_deckt_ladung_ab,
)
from backend.services.snapshot.plausibility import (
    cap_pv_einspeisung_stunde,
    schwelle_pv_einspeisung_stunde_kwh,
)
from backend.services.snapshot.reader import (
    MQTT_AKTIV_TAGE,
    TAGESRESET_TOLERANZ_KWH,
    erster_stand_im_fenster,
    get_snapshot,
    letzter_stand_im_fenster,
    mqtt_zaehler_keys,
    reihe_im_fenster,
    tageswert_aus_reihe,
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
    2. **Monotonie der Zwischenstände verletzt** (`tageswert_aus_reihe`) —
       ein Zwischenstand liegt über dem End- oder unter dem Startstand.

    Weg 2 läuft **immer**, nicht nur bei verdächtig kleinem Delta. Der Grund ist
    der dritte Fall: Werden **beide** Ränder eines Tagesreset-Zählers vor dem
    Reset abgetastet, ist ``d = heutiger Tagesstand − gestriger Tagesstand`` —
    **positiv, plausibel und still falsch**. Weg 1 sieht davon nichts, und ein
    „nur bei d ≈ 0 nachsehen" hätte ihn ebenfalls durchgelassen.
    """
    # ⛔ **Hier stand die Regel bis 10.09.2026 ein ZWEITES Mal ausgeschrieben** —
    # mit dem Literal `-0.01`, während `reader.delta` dieselbe Schwelle als
    # Konstante `TAGESRESET_TOLERANZ_KWH` führte. Zwei Stellen, beide mit dem
    # Anspruch „der eine Ort", formal schon auseinander: genau die F-56-Form,
    # vor der dieser Docstring warnt. Die Regel selbst steht jetzt als reine
    # Funktion in `reader.tageswert_aus_reihe`; hier wird geladen und
    # protokolliert.
    zwischenstaende = [w for _ts, w in await reihe_im_fenster(
        db, anlage_id, sensor_key, ts_start, ts_ende
    )]
    wert = tageswert_aus_reihe(s0, s1, zwischenstaende)
    if wert is None:
        logger.info(
            f"Zähler-Rücksprung im Tagesfenster für anlage={anlage_id} "
            f"key={sensor_key} ({datum}): {s0:.3f} → {s1:.3f} über "
            f"{len(zwischenstaende)} Zwischenstände → keine Tagesaussage"
        )
        return None
    return wert


def stunden_slot_delta(
    s0: float,
    s1: float,
    *,
    sensor_key: str,
    datum: date,
    slot_idx: int,
) -> Optional[float]:
    """Die Menge **eines Stunden-Slots** aus zwei Zählerständen — die Regel selbst.

    ⭐ **Warum sie eine Funktion ist** (11.09.2026, Wärme/Klima Bauschnitt 5): Sie
    stand inline in `get_hourly_kwh_by_category`, und der Tag-Verlauf braucht
    für die Stundenform seiner Zähler **dieselbe** Regel. Abgeschrieben wäre sie
    die F-56-Klasse — und die Gegenprüfung hat genau diese Divergenz zwischen
    Kachel-Stunden und Verlaufs-Stunden als Einwand gebracht.

    ⚠ **Dieselbe Schwelle wie im Tagesfenster, aber eine ANDERE Frage** — und
    deshalb bewusst eine andere Antwort. Der Tag lehnt einen zurückgesetzten
    Zähler ab (`tageswert_aus_reihe`); der Slot über Mitternacht wertet ihn mit
    `s1` (der Energie seit dem Reset), weil das für DIESE Stunde die richtige
    Zahl ist. *Gleiche Formel, verschiedene Fenster, verschiedene Wahrheit* —
    s. Docstring von `_tageswert_aus_raendern`. Geteilt wird nur die
    **Schwelle**, seit 10.09.2026 als Konstante statt als Literal.

    Returns:
        Menge in kWh (≥ 0), oder ``None`` für einen Rücksprung, der kein
        Tagesreset ist (protokolliert).
    """
    d = s1 - s0
    if d < -TAGESRESET_TOLERANZ_KWH:
        # Tagesreset-Zähler (HA utility_meter mit daily cycle): s0 ≈ Tagesendwert,
        # s1 ≈ 0 nach Mitternachts-Reset. Slot wird mit s1 (Energie seit Reset)
        # gewertet statt verworfen, sonst bliebe Slot 0 dauerhaft None und
        # ist_unvollstaendig=True würde irreführend triggern.
        if s1 < 0.5 and s0 > 0.5:
            return max(0.0, s1)
        logger.warning(
            f"Negatives Delta bei {sensor_key} ({datum} Slot{slot_idx}): {d:.3f}"
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
        "verbrauch" wird bilanziell berechnet (SoT:
        `core/berechnungen/stundenbilanz.py`):
            verbrauch = pv + netzbezug - einspeisung - (ladung - entladung)
        nur wenn pv, einspeisung und netzbezug verfügbar sind.
    """
    sensor_mapping = anlage.sensor_mapping or {}
    quellen_energy = extract_quellen_energy(anlage)  # C2b-Read-Through

    # 1. Zähler-Entities sammeln mit Kategorien
    # (sensor_key, entity_id | None, kategorie, fallback_gruppe)
    # entity_id=None bei reinen MQTT-Quellen (Standalone/Docker-Modus)
    eintraege: list[tuple[str, Optional[str], str, Optional[str]]] = []
    seen_keys: set[str] = set()

    # 1a-vorab. Die MQTT-Keys werden hier geholt und erst in 1b verarbeitet.
    # ⛔ Bis #406 stand hier zusätzlich die Alles-oder-nichts-Regel für
    # `basis:pv_gesamt` (Stufe 1 zu F-7) — sie musste BEIDE Quellen kennen,
    # bevor der Basis-Beitrag entstand. Die Regel ist entfallen: sie fragte die
    # Konfiguration statt die Daten. Beide Quellen sind jetzt Kandidaten, die
    # Wahl fällt in Schritt 3b über `core/berechnungen/pv_tages_praezedenz.py`.
    # Die Doppelzählung, gegen die die alte Regel gebaut war, verhindert die
    # Präzedenz genauso — sie nimmt in JEDEM Slot genau eine Seite.
    cutoff = datetime.now() - timedelta(days=MQTT_AKTIV_TAGE)
    mqtt_sks_alle: list[str] = sorted(
        await mqtt_zaehler_keys(db, anlage.id, seit=cutoff)
    )

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
    #
    # ⚑ #406: Die Kategorie `pv` wird dabei NICHT sofort zusammengeworfen. Sie
    # hat zwei Quellen — das Anlagen-Aggregat `basis:pv_gesamt` und die Zähler
    # je Erzeuger —, und welche von beiden den Tag trägt, entscheidet Schritt 3b
    # nach dem Lesen. Würden sie hier addiert, stünde die Anlagensumme neben
    # ihren eigenen Summanden (#290/#298).
    pv_aggregat_je_slot: dict[int, Optional[float]] = {}
    pv_einzel_je_slot: dict[int, dict[str, float]] = {}
    for slot_idx, prev_off, curr_off in rng.slot_pairs:
        per_kat: dict[str, Optional[float]] = {}
        pv_aggregat_je_slot[slot_idx] = None
        pv_einzel_je_slot[slot_idx] = {}
        for sensor_key, _eid, kat, _grp in eintraege:
            s0 = snaps[sensor_key][prev_off]
            s1 = snaps[sensor_key][curr_off]
            if s0 is None or s1 is None:
                continue  # Kategorie unvollständig für diese Stunde
            d = stunden_slot_delta(
                s0, s1, sensor_key=sensor_key, datum=datum, slot_idx=slot_idx,
            )
            if d is None:
                continue
            if kat == "pv":
                # Getrennt halten statt summieren — die Wahl fällt in 3b.
                if sensor_key == f"basis:{PV_AGGREGAT_BASIS_FELD}":
                    pv_aggregat_je_slot[slot_idx] = (
                        pv_aggregat_je_slot[slot_idx] or 0.0
                    ) + d
                else:
                    # `inv:<id>:pv_erzeugung_kwh` — die ID trägt die Deckung.
                    inv_id = sensor_key.split(":", 2)[1]
                    pv_einzel_je_slot[slot_idx][inv_id] = (
                        pv_einzel_je_slot[slot_idx].get(inv_id, 0.0) + d
                    )
                continue
            per_kat[kat] = (per_kat.get(kat) or 0.0) + d
        result[slot_idx] = per_kat

    # 3b. Welche PV-Quelle trägt diesen Tag? (#406, Layer-SoT)
    # Die Präzedenz ist die des Monats, auf den Tag übertragen: liefern alle
    # erwarteten Erzeuger den ganzen Tag, gewinnen sie; sonst trägt das
    # Aggregat. Die Wahl gilt für ALLE Slots — nur so bleibt die Quelle über
    # den Tag einheitlich und Σ Hourly / Tages-Boundary behalten die
    # Konsistenz, die sie heute haben.
    # N-536: Deckung auf TRÄGER-Ebene und Summe ohne Doppelzählung.
    # Ein Kind gilt als gedeckt, wenn es selbst oder sein abtretendes
    # Balkonkraftwerk liefert (sie messen dieselbe Energie); und in der Summe
    # trägt das Balkonkraftwerk nur noch den Rest. **Unverteilt** — die
    # kWp-Gewichtung ist eine Tages-Aussage (s. `komponenten_beitraege`).
    _alle_invs = list(investitionen_by_id.values())
    pv_quelle = waehle_pv_quelle(
        erwartete_ids=erwartete_erzeuger_ids(investitionen_by_id.values(), datum),
        gedeckte_ids_je_slot={
            h: ergaenze_kinder_deckung(ids.keys(), _alle_invs)
            for h, ids in pv_einzel_je_slot.items()
        },
        aggregat_je_slot=pv_aggregat_je_slot,
    )
    for slot_idx in range(24):
        if pv_quelle == QUELLE_AGGREGAT:
            wert = pv_aggregat_je_slot.get(slot_idx)
        elif pv_quelle == QUELLE_EINZEL:
            einzel = pv_einzel_je_slot.get(slot_idx) or {}
            if einzel:
                einzel = dict(einzel)
                einzel.update(bkw_restwerte(_alle_invs, einzel))
            wert = sum(einzel.values()) if einzel else None
        else:
            wert = None
        if wert is not None:
            result[slot_idx]["pv"] = wert

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

        # Batterie netto (positiv = Ladung, negativ = Entladung) und der
        # Bilanz-Verbrauch kommen aus dem Layer-SoT (ADR-001) — die Formel stand
        # bis 29.08.2026 hier UND im LTS-Pfad wortgleich. Verhaltensneutral;
        # dass ein fehlender Batterie-Beitrag als 0 zählt, ist dort als offener
        # Punkt beschrieben.
        batt_netto = berechne_batterie_netto_kwh(
            ladung_kwh=ladung_batt,
            entladung_kwh=entladung_batt,
        )
        verbrauch = stunden_verbrauch_kwh(
            pv_kwh=pv_total,
            netzbezug_kwh=bez,
            einspeisung_kwh=einsp,
            batterie_netto_kwh=batt_netto,
        )

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
    *,
    marken_out: Optional[dict[str, str]] = None,
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

    ⚑ `marken_out` (optional): nimmt die Herkunfts-Marken der PV-Auflösung auf
    (`{komponenten_key: ABGELEITET_*}`). Nur `aggregate_day` braucht sie, um sie
    in `source_provenance` zu schreiben — die übrigen Konsumenten lesen bloß
    Zahlen. Als Out-Parameter statt als zweitem Rückgabewert, weil die Funktion
    sieben Aufrufer hat und ein Tupel jeden davon anfassen müsste.

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

    # 1. Basis: einspeisung + netzbezug + PV gesamt.
    #
    # ⛔ **Hier stand bis 2026-08-27**: „Anders als der Hourly-Pfad braucht diese
    # Funktion KEINE MQTT-Gegenprobe … ein rein per MQTT gespeister Zähler je
    # Erzeuger existiert hier also gar nicht." Der Satz beschrieb den **Defekt**
    # und begründete ihn: Weil MQTT hier nicht existierte, blieb die Tagesbilanz
    # einer Standalone-Anlage leer, während der Stundenpfad daneben gefüllt war
    # (N-328b/#396).
    # ⛔ **Und bis #406 stand hier die Alles-oder-nichts-Regel**: `pv_gesamt`
    # fiel weg, sobald ein Erzeuger einen eigenen Zähler ZUGEORDNET hatte. Beide
    # Quellen kommen jetzt herein; die Wahl fällt unten in `loese_pv_tageswerte_auf`
    # — nach dem Lesen, an den Daten. Doppelt gezählt wird trotzdem nie: das
    # Aggregat verlässt die Funktion entweder aufgelöst oder gar nicht.
    basis_map = sensor_mapping.get("basis", {}) or {}
    await _apply_beitraege(
        basis_beitraege(
            sensor_mapping,
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
                # K3 Regel 4 (R-1) fragt auch nach Innengerät-Kopien, und die
                # stehen bei einer MQTT-Anlage nur in den Topics (N-328b).
                kandidaten=zaehler_feld_kandidaten(inv_id_str, felder, mqtt_keys),
            ),
            lambda feld, _id=inv_id_str: f"inv:{_id}:{feld}",
            inv_data,
            result,
        )

    # 3. PV-Präzedenz je Tag (#406): Einzelzähler schlagen das Aggregat, sobald
    # sie den Tag VOLLSTÄNDIG tragen — sonst löst das Aggregat sich in die
    # Erzeuger auf. `pv_gesamt` steht danach in keinem Fall mehr im Ergebnis.
    result, marken = loese_pv_tageswerte_auf(result, investitionen_by_id, datum)
    if marken_out is not None:
        marken_out.update(marken)

    return result


@dataclass(frozen=True)
class TagesRandMenge:
    """Ein Tageswert **und** das Fenster, das ihn wirklich trägt (R-4/N-491).

    ``ab_tagesbeginn``/``bis_tagesende`` sind ``True``, solange beide
    Tagesränder standen — dann ist ``seit``/``bis`` genau das angefragte
    Fenster und die Zahl ist der volle Tag. Steht einer der beiden nicht, rückt
    er auf den ersten bzw. letzten Stand **im** Tag, und die Marke sagt es
    (ADR-002/**P4**: keine Hochrechnung, aber auch kein Verschweigen).

    ⭐ **Der Zwilling zu** {@link
    backend.services.snapshot.reader.MengeSeit} **eine Zeitebene tiefer.** Der
    Monat hat die Frage am 14.09.2026 beantwortet (N-472, „MQTT (14.–30.09.)");
    der Tag stellte sie bis zum 15.09.2026 nicht und lieferte am ersten Tag nach
    einer Zuordnung **gar keine** Zahl je Gerät.
    """

    wert_kwh: float
    seit: datetime
    bis: datetime
    ab_tagesbeginn: bool
    bis_tagesende: bool


async def _tagesdetail_boundary_diff_mit_grund(
    db: AsyncSession,
    anlage,
    quellen_energy,
    sensor_key: str,
    sensor_id: Optional[str],
    ts_start: datetime,
    ts_ende: datetime,
    datum: date,
    *,
    rueckfall_tagesrand: bool = False,
) -> tuple[Optional["TagesRandMenge"], Optional[str]]:
    """Boundary-Diff eines kumulativen kWh-Zählers über das HA-Tagesfenster.

    **Warum als Modul-Funktion und nicht als Closure** (#263): Sie hat zwei
    Aufrufer — `get_tagesdetail_kwh` und `get_betriebsart_strom_tageswerte`.
    Beide brauchen dieselbe Tagesreset-Behandlung; sie ein zweites Mal
    hinzuschreiben wäre die F-56-Klasse (*„eine Regel, die an zwei Stellen
    nachgebaut wird, driftet"*), und ausgerechnet an diesem Feld ist sie schon
    einmal gedriftet.

    Args:
        rueckfall_tagesrand: **R-4** (15.09.2026). Ohne den Schalter ist das
            Ergebnis bitgleich zu vorher, nur um die Fenster-Marke ergänzt. Mit
            ihm gilt zusätzlich: *fehlt ein Tagesrand, rückt er auf den ersten
            bzw. letzten Stand **im** Tag* — und die Zahl sagt, ab wann bzw. bis
            wann sie gilt.

            ⛔ **Er greift ausschließlich bei einem fehlenden RAND**, nie bei
            einem Zählerrücksprung: dessen ``None`` ist eine *Entscheidung über
            Datenqualität* (N-341), und ein engeres Fenster machte daraus eine
            kleinere, ebenso falsche Zahl. Die Struktur schützt davor von
            selbst — gefragt wird nur der Rand, der wirklich fehlt; stehen
            beide, entscheidet weiterhin allein
            {@link _tageswert_aus_raendern}.

            ⛔ **Und er ist ein Schalter, kein Default.** Der zweite Leser
            dieser Funktion ist über ``get_komponenten_tageskwh`` der
            **gespeicherte** Tageswert (``TagesZusammenfassung.komponenten_kwh``);
            dort wäre eine Menge „seit 11 Uhr" ein Tageswert wie jeder andere —
            dieselbe Klasse wie F-66 eine Zeitebene höher. Nur die **Anzeige**
            bekommt den Rückfall, weil sie ihn beschriften kann.
    """
    s0 = await get_snapshot(
        db, anlage.id, sensor_key, sensor_id, ts_start,
        quellen_energy=quellen_energy,
    )
    s1 = await get_snapshot(
        db, anlage.id, sensor_key, sensor_id, ts_ende,
        quellen_energy=quellen_energy,
    )
    von, bis = ts_start, ts_ende
    if rueckfall_tagesrand and (s0 is None or s1 is None):
        if s0 is None:
            von_neu = await erster_stand_im_fenster(
                db, anlage.id, sensor_key, ts_start, ts_ende,
            )
            if von_neu is not None:
                s0 = await get_snapshot(
                    db, anlage.id, sensor_key, sensor_id, von_neu,
                    quellen_energy=quellen_energy,
                )
                von = von_neu
        if s1 is None:
            bis_neu = await letzter_stand_im_fenster(
                db, anlage.id, sensor_key, von, ts_ende,
            )
            # ⚠ **Echt größer, nicht „größer gleich".** Ein einziger Stand im
            # Tag ist kein Fenster: ``_tageswert_aus_raendern(s, s)`` lieferte
            # eine gemessene **0**, und die sähe aus wie „nichts gelaufen"
            # (ADR-002/P4, F-42-Klasse). Gemessen am Sprengsatz S20.
            if bis_neu is not None and bis_neu > von:
                s1 = await get_snapshot(
                    db, anlage.id, sensor_key, sensor_id, bis_neu,
                    quellen_energy=quellen_energy,
                )
                bis = bis_neu
    # ⛔ **Hier stand bis zum 15.09.2026 zusätzlich ``or bis <= von``.** Der
    # Sprengsatz S20 blieb daran **still**, und die Nachschau gab ihm recht: Der
    # Zweig ist unerreichbar — ``von`` rückt nur vor, wenn ``s0`` fehlte, und
    # ``bis`` nur zurück, wenn ``bis_neu > von`` gilt. Eine tote Klausel, die
    # kein Sprengsatz treffen kann, ist keine Absicherung, sondern Rauschen;
    # die echte Kante bewacht die Zeile ``bis_neu > von`` oben.
    if s0 is None or s1 is None:
        return None, GRUND_KEINE_ZAEHLERSTAENDE
    wert = await _tageswert_aus_raendern(
        db, anlage.id, sensor_key, s0, s1, von, bis, datum,
    )
    # W-18: `_tageswert_aus_raendern` gibt bei einem Rücksprung bewusst `None`
    # zurück und schreibt eine Logzeile — die kein Anwender sieht. Hier bekommt
    # derselbe Zustand einen Namen, damit die Oberfläche ihn aussprechen kann.
    if wert is None:
        return None, GRUND_ZAEHLER_RUECKSPRUNG
    return TagesRandMenge(
        wert_kwh=wert, seit=von, bis=bis,
        ab_tagesbeginn=von == ts_start, bis_tagesende=bis == ts_ende,
    ), None


async def _tagesdetail_boundary_diff(
    db: AsyncSession,
    anlage,
    quellen_energy,
    sensor_key: str,
    sensor_id: Optional[str],
    ts_start: datetime,
    ts_ende: datetime,
    datum: date,
    *,
    rueckfall_tagesrand: bool = False,
) -> Optional[float]:
    """Nur der Wert — für Aufrufer, die den Grund nicht brauchen.

    ⚠ **Kein zweiter Rechenweg**: ein Durchreicher auf
    {@link _tagesdetail_boundary_diff_mit_grund}. Die Tagesreset-Behandlung
    steht weiterhin genau einmal im Baum (F-56).
    """
    menge, _grund = await _tagesdetail_boundary_diff_mit_grund(
        db, anlage, quellen_energy, sensor_key, sensor_id,
        ts_start, ts_ende, datum, rueckfall_tagesrand=rueckfall_tagesrand,
    )
    return menge.wert_kwh if menge is not None else None


async def get_betriebsart_strom_tageswerte(
    db: AsyncSession,
    anlage,
    investitionen_by_id: dict,
    datum: date,
    *,
    rueckwaerts: bool = False,
) -> dict[str, dict[str, float]]:
    """Tages-kWh der **gemessenen** Betriebsart-Zähler, je Wärmepumpe (#263).

    ⛔ **``rueckwaerts`` ist keine Stilfrage (N-434, 11.09.2026).** Diese Werte
    sind **Teilmengen** eines Bezugs, und der Bezug steht in
    ``TagesZusammenfassung.komponenten_kwh`` — im HA-Add-on als Σ der 24
    LTS-Slots, also im Fenster [Vortag 23:00, Heute 23:00). Im bisherigen
    Tagesfenster [00:00, 24:00) gelesen, stand die Differenz zweier Randstunden
    als „nicht aufgeteilt" in der Tagesaufteilung (gemessen: 1,8 von 7,0 kWh an
    einem Gerät, das nur heizt) — oder die Aufteilung verschwand ganz. Der
    Aufrufer entscheidet über ``tageszeile_ist_rueckwaerts`` an der Herkunft
    DERSELBEN Tageszeile, aus der er den Bezug nimmt.

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
    # Dieselbe Tabelle wie `get_tagesdetail_kwh` (N-444): das Fenster eines Typs
    # steht EINMAL im Baum. Verhalten bitgleich zur früheren lokalen Weiche —
    # `waermepumpe` ist dort „bedingt", und dieser Aufrufer liest nur Wärmepumpen.
    rng = tagesfenster_fuer(
        "waermepumpe", datum, tageszeile_rueckwaerts=rueckwaerts
    )
    start_off, end_off = rng.boundary_offsets  # (-1, 23) bzw. (0, 24)
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
        kandidaten = zaehler_feld_kandidaten(inv_id_str, felder, mqtt_keys)
        je_inv: dict[str, float] = {}
        for feld in sorted(kandidaten):
            if not ist_betriebsart_strom_feld(feld):
                continue
            cfg = felder.get(feld)
            if not feld_hat_zaehler(cfg, praefix + feld, quellen_energy, mqtt_keys):
                continue
            # R-4: derselbe Rückfall wie in `get_tagesdetail_kwh` — die
            # Teilmengen eines Tages müssen im selben Fenster stehen wie ihr
            # Bezug, und der bekommt ihn seit dem 15.09.2026 auch. Ohne das
            # fiele am ersten Tag nach einer Zuordnung die ganze Aufteilung in
            # den Rest *nicht aufgeteilt*, obwohl sie gemessen ist.
            d = await _tagesdetail_boundary_diff(
                db, anlage, quellen_energy,
                praefix + feld, cfg.get("sensor_id") if isinstance(cfg, dict) else None,
                ts_start, ts_ende, datum, rueckfall_tagesrand=True,
            )
            if d is None:
                continue
            je_inv[feld] = d
        if je_inv:
            ergebnis[str(inv_id_str)] = je_inv
    return ergebnis


async def get_wp_strom_stufe_je_investition(
    db: AsyncSession,
    anlage,
    investitionen_by_id: dict,
) -> dict[str, str]:
    """Welche **K3-Stufe** trägt der Tagesbezug je Wärmepumpe? (N-462)

    ``{inv_id_str: "fein" | "gesamt"}`` — dieselbe Frage und **derselbe
    Eingang**, mit dem ``investition_beitraege`` den Tageswert in
    ``TagesZusammenfassung.komponenten_kwh`` gelegt hat: ``feld_hat_zaehler``
    über HA-Mapping **und** MQTT-Keys. ⭐ Seit WK-16d ist das genau **ein**
    Feld — ``stromverbrauch_kwh`` —, weil ein zugeordneter Gesamtzähler die
    Menge ist (K1) und die Registry-Achsen an der Stufe nichts mehr entscheiden.

    ⛔ **Warum das eine eigene Funktion ist und keine Ableitung aus dem
    Kennzeichen.** ``funktionsfremd_abzug_kwh`` fragt *„steht der funktionsfremde
    Anteil überhaupt im Nenner?"* (SOLL-§9-E7/Option A). Der Nenner des
    Tagesstapels ist ``komponenten_kwh[waermepumpe_<id>]``, und ob darin die
    feine Summe oder der Gesamtzähler steht, entscheidet K3 — nicht
    ``getrennte_strommessung``. **Gemessen** (13.09.2026): derselbe Bezug,
    derselbe abgeleitete Split, Tages-Arbeitszahl **3,00 mit** und **3,75 ohne**
    gesetztes Kennzeichen — 20 % Unterschied durch einen Schalter, der in dieser
    Lage nichts misst. Klasse **N-450**: *„denselben Layer zu rufen genügt nicht,
    es müssen dieselben EINGÄNGE sein."*

    ⚠ **Die Antwort hängt an der Zuordnung, nicht am Tag** — sie gilt für die
    ganze Reihe und wird deshalb **einmal** vor einer Tagesschleife erhoben
    (``waerme_verlauf``), nicht je Tag.
    """
    from backend.core.berechnungen.betriebsart_gemessen import (
        betriebsart_strom_felder_belegt,
    )
    from backend.core.field_definitions import feine_strom_achsen, wp_strom_stufe

    sensor_mapping = anlage.sensor_mapping or {}
    quellen_energy = extract_quellen_energy(anlage)
    mqtt_keys = await mqtt_zaehler_keys(db, anlage.id)

    ergebnis: dict[str, str] = {}
    for inv_id_str, inv, inv_data in _investitionen_mit_mapping(
        sensor_mapping, investitionen_by_id
    ):
        if getattr(inv, "typ", None) != "waermepumpe":
            continue
        felder = inv_data.get("felder", {}) or {}
        praefix = f"inv:{inv_id_str}:"

        def _belegt(feld: str, _f=felder, _p=praefix) -> bool:
            return feld_hat_zaehler(
                _f.get(feld), _p + feld, quellen_energy, mqtt_keys,
            )

        # K3 Regel 4 (R-1): dieselben zwei Eingänge wie in der Beitragsschicht.
        # Die Stufe entscheidet den Nenner-Abzug (E7/Option A) — steht dort
        # „betriebsart", IST die Menge die Σ der Betriebsart-Zähler und der
        # funktionsfremde Anteil steckt darin, muss also abgezogen werden.
        ergebnis[str(inv_id_str)] = wp_strom_stufe(
            hat_gesamtzaehler=_belegt("stromverbrauch_kwh"),
            hat_feine_achsen=any(
                _belegt(f) for f in feine_strom_achsen(
                    getattr(inv, "parameter", None) or {}
                )
            ),
            hat_betriebsart_zaehler=bool(betriebsart_strom_felder_belegt(
                zaehler_feld_kandidaten(inv_id_str, felder, mqtt_keys), _belegt,
            )),
        )
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
    #: ``{ausgabe_key: {inv_id: kwh}}`` — dieselben Werte **je Gerät**; ``werte``
    #: ist ihre Summe. Bauschnitt 6: Die Tages-Kühlzahl muss ihren Zähler auf
    #: die Geräte einschränken, die ihren Nenner tragen (R2 beidseitig) — aus
    #: der Summe allein ist das nicht ablesbar (gemessen: 6,0 statt 3,0, wenn ein
    #: Gerät aus dem Tages-Stapel fällt, seine Kälte aber mitgezählt wird).
    werte_je_inv: dict[str, dict[str, float]] = dc_field(default_factory=dict)
    #: ``{ausgabe_key: {inv_id: {feld: kwh}}}`` — die Feldwerte, die je Gerät
    #: in ``geraetefeld_oder_innengeraete`` gingen (Gerätefeld und/oder
    #: Innengerät-Kopien, nur Felder mit Tageswert). Bauschnitt 6b (N-437): Der
    #: Stunden-Verlauf liest die Formen **genau dieser** Felder und löst je
    #: Stunde mit derselben Regel auf — sonst nähme die Stunde eine andere
    #: Quelle als der Tag (gemessen: Gerätefeld mit Rücksprung, Wert aus den
    #: Innengeräten, Form aus dem Gerätefeld ⇒ Stunde 14 leer).
    felder_je_inv: dict[str, dict[str, dict[str, float]]] = dc_field(default_factory=dict)
    #: **Ab wann / bis wann die Zahlen wirklich gemessen sind** (R-4, N-491) —
    #: der früheste und der späteste Rand über alle Felder, die den Tag **nicht**
    #: von 0 bis 24 Uhr abdecken. ``None``, solange jedes gelesene Feld beide
    #: Tagesränder hatte (der Regelfall; dann gibt es nichts auszuweisen).
    #:
    #: ⚠ **Eine Marke für den ganzen Block, nicht je Feld.** Sie beantwortet die
    #: Frage *„deckt diese Sicht den ganzen Tag ab?"*; je Feld beantwortet sie
    #: dieselbe Frage n-mal und zwänge die Oberfläche zu n Fußnoten. Die
    #: Marke ist absichtlich die **weiteste** Einschränkung (spätestes ``von``,
    #: frühestes ``bis``) — sie warnt damit eher zu viel als zu wenig (P4).
    abdeckung_von: Optional[datetime] = None
    abdeckung_bis: Optional[datetime] = None


#: **(typ, mapping-feld) → semantischer Ausgabe-Key** — die Feldmenge, die
#: `get_tagesdetail_kwh` erhebt und die der Bereichs-Leser des Wärme/Klima-
#: Verlaufs teilt.
#:
#: ⭐ **Warum sie eine Modul-Konstante ist** (10.09.2026): Sie stand als lokale
#: Variable in `get_tagesdetail_kwh` und war damit für jeden anderen Leser
#: unerreichbar — obwohl `core/berechnungen/waermepumpe_kennzahl.py` künftige
#: Leser ausdrücklich hierher schickt (*„die AUSGABE-Tabelle … erweitern, damit
#: ihn niemand neu suchen muss"*, Weg zur Tages-Kühlzahl). Der Monats-Verlauf
#: brauchte dieselbe Menge für 28–31 Tage; eine zweite Liste hätte bedeutet,
#: dass **Bauschnitt 6** (Kälte je Tag) an zwei Stellen gebaut werden muss.
#:
#: Alle Felder liegen in `KUMULATIVE_ZAEHLER_FELDER`, sind also per
#: Boundary-Diff erhebbar. Wichtig: speicher- und emob-`ladung_netz_kwh` sind
#: verschiedene Begriffe → getrennte Ausgabe-Keys (sonst Vermischung). Wallbox
#: und E-Auto fließen in DENSELBEN emob-Key (Σ).
TAGESDETAIL_AUSGABE: dict[tuple[str, str], str] = {
    ("waermepumpe", "strom_heizen_kwh"): "wp_strom_heizen_kwh",
    ("waermepumpe", "strom_warmwasser_kwh"): "wp_strom_warmwasser_kwh",
    # R-4/N-482: der **Gesamt**-Stromzähler je Gerät. Er steht hier nicht, weil
    # die Tagessicht ihn als eigene Zeile zeigte — er steht hier, damit der Tag
    # K3 an denselben Werten entscheiden kann wie der Monat, wenn der
    # aggregierte Tageswert (`komponenten_kwh`) für ein Gerät fehlt: ein
    # zugeordneter, an diesem Tag **stummer** Gesamtzähler ließ bis zum
    # 15.09.2026 die feinen Achsen nicht tragen, weil die Beitragsschicht
    # 1-aus-n an der *Zuordnung* entscheidet.
    ("waermepumpe", "stromverbrauch_kwh"): "wp_strom_gesamt_kwh",
    # R-2/N-487: die gemessene **Nutzenergie Heizbetrieb**. Bis zum 15.09.2026
    # mappte diese Tabelle von den vier Nutzenergie-Feldern nur KUEHLEN — ein
    # Gerät, das seine Heizwärme je Betriebsart misst, zeigte sie in Monat und
    # Jahr und im Tag nicht, und der Kasten nannte dort „Wärmemengenzähler
    # zuordnen", obwohl er zugeordnet war. Die Weiche darüber (D1-Stufe 3,
    # `waermepumpe_kennzahl.heizwaerme_kwh`) ist dieselbe wie im Monat; sie
    # steht NICHT in `WAERME_AUSGABE_KEYS`, weil dort summiert wird und diese
    # Menge die Heizwärme **ersetzt**, statt sie zu ergänzen.
    ("waermepumpe", BETRIEBSART_NUTZENERGIE_FELD[HEIZEN]):
        "wp_betriebsart_heizen_kwh",
    # thermische Wärme (nur mit Wärmemengenzähler-Sensor; in der Bilanz
    # ausgeschlossen, hier für Tages-JAZ/Wärme).
    ("waermepumpe", "heizenergie_kwh"): "wp_heizung_kwh",
    ("waermepumpe", "warmwasser_kwh"): "wp_warmwasser_kwh",
    # N-391: der gemeinsame Wärmemengenzähler. Er ist der **Gesamtwert** über
    # den beiden Achsen (D1) — deshalb steht er NICHT in `WAERME_AUSGABE_KEYS`
    # (dort wird summiert; er würde dieselbe Wärme ein zweites Mal in die Linie
    # legen). Der Tag löst ihn mit derselben Vorrangregel auf wie der Monat.
    ("waermepumpe", "waerme_kwh"): "wp_waerme_kwh",
    # Kälte (Bauschnitt 6): eine **eigene Rolle**, kein Wärme-Sonderfall —
    # deshalb NICHT in `WAERME_AUSGABE_KEYS` (Konzept Wärme/Klima §8). Das Feld
    # gibt es auch je Innengerät; `get_tagesdetail_kwh` und der Bereichs-Leser
    # lösen den Suffix mit `geraetefeld_oder_innengeraete` auf.
    ("waermepumpe", BETRIEBSART_NUTZENERGIE_FELD[KUEHLEN]): "wp_kaelte_kwh",
    ("speicher", "ladung_netz_kwh"): "speicher_ladung_netz_kwh",
    ("wallbox", "ladung_pv_kwh"): "emob_ladung_pv_kwh",
    ("wallbox", "ladung_netz_kwh"): "emob_ladung_netz_kwh",
    ("e-auto", "ladung_pv_kwh"): "emob_ladung_pv_kwh",
    ("e-auto", "ladung_netz_kwh"): "emob_ladung_netz_kwh",
}

#: Die Wärme-Ausgabekeys — die Teilmenge, die der Verlauf als Linie zeichnet.
WAERME_AUSGABE_KEYS: frozenset[str] = frozenset(
    {"wp_heizung_kwh", "wp_warmwasser_kwh"}
)

#: **Ausgabe-Key → Registry-Feld** für die drei Strom-Größen einer Wärmepumpe —
#: der Rückweg aus der Tabelle oben.
#:
#: ⭐ **Wozu (R-4):** ``wp_strom_aufteilung`` beantwortet K3 an **Registry**-
#: Feldnamen, weil sie für eine Monatszeile geschrieben ist. Damit der Tag
#: dieselbe Funktion rufen kann statt die Regel nachzubauen, braucht er genau
#: diese Rückabbildung. Sie wird **abgeleitet** und nicht getippt: eine zweite
#: Liste neben der Tabelle wäre die F-56-Form.
WP_STROM_AUSGABE_ZU_FELD: dict[str, str] = {
    ausgabe: feld
    for (typ, feld), ausgabe in TAGESDETAIL_AUSGABE.items()
    if typ == "waermepumpe"
    and (feld in WP_GESAMT_STROM_FELDER or feld in FEINE_STROM_FELDER)
}


async def get_tagesdetail_kwh(
    db: AsyncSession,
    anlage,
    investitionen_by_id: dict,
    datum: date,
    *,
    tageszeile_rueckwaerts: bool = False,
) -> "TagesDetail":
    """Tages-kWh für Felder, die `get_komponenten_tageskwh` bewusst NICHT separat
    ausweist, die aber Cockpit/Tag für die Detailzeilen braucht (D1 „maximal
    erheben", SPEC-COCKPIT-TAG-JAHR Abschnitt F):

      - WP `strom_heizen_kwh` / `strom_warmwasser_kwh` (getrennte Strommessung) —
        in der Bilanz zu EINEM `waermepumpe_<id>`-Key zusammengefasst.
      - Speicher `ladung_netz_kwh` (Arbitrage) — in der Bilanz bewusst
        ausgeschlossen (Teilmenge von `ladung_kwh`, Doppelzähl-Schutz).

    Boundary-Diff **im Fenster des jeweiligen Bezugs** — je Gerätetyp aus
    {@link tagesfenster_fuer} (SOLL §3.3/S1a, N-444), Tagesreset-Behandlung
    identisch zu `get_komponenten_tageskwh`. Summe
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
    # ⛔ **Jeder Typ liest im Fenster SEINES Bezugs (N-435 · N-444, SOLL §3.3/S1a).**
    # Ein Tagesdetail ist eine Teilmenge, ein Anteil oder ein Quotient — Zähler
    # und Bezug müssen denselben Zeitraum abdecken, sonst ist die Zahl eine
    # Rechnung über zwei Tage. Welches Fenster ein Typ trägt, steht **einmal** in
    # `boundary_range.TAGESFENSTER_JE_TYP`; hier wird es nur je Investition
    # abgefragt (keine zusätzliche DB-Abfrage — weiterhin zwei Randstände je Feld).
    #
    # ⚠ **Es ist NICHT „alle rückwärts".** Die Wärmepumpe bleibt bedingt: ihr
    # Bezug `komponenten_kwh` ist im HA-Add-on Σ der LTS-Slots [Vortag 23:00,
    # 23:00), im Snapshot-Pfad [00:00, 24:00) — über das falsche Fenster gelesen
    # war die Arbeitszahl um die Differenz zweier Randstunden verfälscht
    # (gemessen: 2,23 statt 4,04 an einer Wärmepumpe, die jede Stunde 3,0 macht).
    # Speicher, Wallbox und E-Auto hängen dagegen an den **Stundenzeilen**, und
    # die liegen seit N-382 unbedingt rückwärts — dort ist der Versatz in JEDER
    # Installation da.
    #
    # ⭐ **Hier stand bis N-444: „Speicher- und E-Mob-Felder behalten [0, 24) …
    # Verdacht V-4, aber nicht gemessen".** Gemessen ist er seit dem 12.09.2026
    # (Demo-DB, 187 Tage): an 18 von 182 Tagen weicht die Speicher-Ladung
    # zwischen den Fenstern um mehr als 5 % ab, am 25.11.2025 um +131,9 %
    # (1,11 gegen 2,58 kWh). Die Netzladung konnte dadurch größer sein als ihr
    # eigener Bezug — im Client still auf 100 % gekappt.
    async def _diff(
        sensor_key: str, sensor_id: Optional[str], *, rng: BoundaryRange,
    ) -> tuple[Optional["TagesRandMenge"], Optional[str]]:
        start_off, end_off = rng.boundary_offsets
        return await _tagesdetail_boundary_diff_mit_grund(
            db, anlage, quellen_energy, sensor_key, sensor_id,
            rng.boundary_at(start_off), rng.boundary_at(end_off),
            datum, rueckfall_tagesrand=True,
        )

    AUSGABE = TAGESDETAIL_AUSGABE
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

    je_inv: dict[str, dict[str, float]] = {}
    felder_je: dict[str, dict[str, dict[str, float]]] = {}
    abdeckung_von: Optional[datetime] = None
    abdeckung_bis: Optional[datetime] = None
    for inv_id_str, inv, inv_data in _investitionen_mit_mapping(
        sensor_mapping, investitionen_by_id
    ):
        typ = getattr(inv, "typ", None)
        # E-Auto mit parent (Wallbox misst die Ladung) → Skip, sonst Doppelzählung
        # (spiegelt investition_beitraege/Live-Pfad).
        if typ == "e-auto" and getattr(inv, "parent_investition_id", None) is not None:
            continue
        # Das Fenster hängt am Bezug DIESES Typs, nicht am Aufrufweg (S1a).
        rng_typ = tagesfenster_fuer(
            typ, datum, tageszeile_rueckwaerts=tageszeile_rueckwaerts
        )
        felder = inv_data.get("felder", {}) or {}
        kandidaten = zaehler_feld_kandidaten(inv_id_str, felder, mqtt_keys)
        for (t, feld), out_key in AUSGABE.items():
            if t != typ:
                continue
            # ⭐ Bauschnitt 6: Gerätefeld UND seine Innengerät-Kopien (Suffix
            # `-<id>`). Bis dahin las diese Schleife allein den exakten Key — ein
            # Multisplit mit Kälte je Innengerät bekam deshalb keine Zahl und den
            # Grund „nicht zugeordnet", obwohl beide Zähler zugeordnet waren
            # (gemessen 11.09.2026). Für Felder ohne Innengerät-Kopien ist die
            # Liste leer und die Schleife bitgleich zu vorher.
            werte_geraet: dict[str, float] = {}
            for k in (feld, *innengeraet_felder(feld, kandidaten)):
                cfg = felder.get(k)
                sensor_key = f"inv:{inv_id_str}:{k}"
                # ⛔ N-328b: Hier entschied bis 2026-08-27 `strategie == "sensor"`,
                # ob das Feld überhaupt erhoben wird — und wer per MQTT misst,
                # bekam von W-18 den Grund „Kein Zähler zugeordnet" zu lesen,
                # obwohl seine Zählerstände in der Datenbank standen. Der Grund
                # war damit nicht nur nutzlos, sondern **falsch**: Er riet zu
                # einer Zuordnung, die es gar nicht braucht.
                if not feld_hat_zaehler(cfg, sensor_key, quellen_energy, mqtt_keys):
                    _merke_grund(out_key, GRUND_NICHT_ZUGEORDNET)
                    continue
                menge, grund = await _diff(
                    sensor_key, cfg.get("sensor_id") if isinstance(cfg, dict) else None,
                    rng=rng_typ,
                )
                if menge is None:
                    _merke_grund(out_key, grund or GRUND_KEINE_ZAEHLERSTAENDE)
                    continue
                werte_geraet[k] = menge.wert_kwh
                # R-4: die weiteste Einschränkung über alle gelesenen Felder.
                if not menge.ab_tagesbeginn:
                    abdeckung_von = (
                        menge.seit if abdeckung_von is None
                        else max(abdeckung_von, menge.seit)
                    )
                if not menge.bis_tagesende:
                    abdeckung_bis = (
                        menge.bis if abdeckung_bis is None
                        else min(abdeckung_bis, menge.bis)
                    )
            # Die EINE Regel für Gerät vs. Innengeräte — dieselbe, mit der der
            # Monat und der Nenner (Zweig 1, `modus_strom_zeile`) auflösen.
            d = geraetefeld_oder_innengeraete(werte_geraet, feld)
            if d is None:
                continue
            summen[out_key] = summen.get(out_key, 0.0) + d
            geraete = je_inv.setdefault(out_key, {})
            geraete[inv_id_str] = geraete.get(inv_id_str, 0.0) + d
            felder_je.setdefault(out_key, {}).setdefault(inv_id_str, {}).update(werte_geraet)

    return TagesDetail(
        werte=summen,
        # Ein Key mit Wert braucht keine Erklärung — und ein Grund neben einer
        # vorhandenen Zahl wäre ein Widerspruch auf der Fläche.
        grund_je_feld={k: g for k, g in grund_kandidat.items() if k not in summen},
        werte_je_inv=je_inv,
        felder_je_inv=felder_je,
        abdeckung_von=abdeckung_von,
        abdeckung_bis=abdeckung_bis,
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
