"""
Live Sensor Konfiguration - Konstanten und Mapping-Extraktion für Live-Daten.

Ausgelagert aus live_power_service.py (Schritt 1 des Refactorings).
Enthält nur reine Daten und Logik ohne I/O.
"""

import logging
from dataclasses import dataclass
from typing import Callable, Container, Mapping, Optional, Sequence

from backend.core.field_definitions import (
    SONSTIGES_KATEGORIE_UNGEPFLEGT,
    ist_zaehler_kategorie,
    ist_zustand_feld,
)
from backend.models.anlage import Anlage

logger = logging.getLogger(__name__)


# Einheiten-Konvertierung: HA gibt State in suggested_unit zurück (z.B. kW statt W).
# Wir normalisieren alles zu W, damit die Berechnung einheitlich ist.
UNIT_TO_W: dict[str, float] = {
    "W": 1.0,
    "kW": 1000.0,
    "MW": 1_000_000.0,
}


def normalize_to_w(value: float, unit: str) -> float:
    """Konvertiert einen Leistungswert in W basierend auf der HA-Einheit.

    SoC (%) und unbekannte Einheiten werden unverändert durchgereicht.
    """
    factor = UNIT_TO_W.get(unit)
    if factor is not None:
        return value * factor
    return value


# Icon-Zuordnung pro Investitionstyp
TYP_ICON = {
    "pv-module": "sun",
    "balkonkraftwerk": "sun",
    "speicher": "battery",
    "e-auto": "car",
    "wallbox": "plug",
    "waermepumpe": "flame",
    "sonstiges": "wrench",
    "wechselrichter": "zap",
}

# Investitionstypen die als Erzeuger zählen
ERZEUGER_TYPEN = {"pv-module", "balkonkraftwerk"}

# Bidirektionale Typen (positiv = Ladung/Verbrauch, negativ = Entladung/Erzeugung)
BIDIREKTIONAL_TYPEN = {"speicher"}

# Typen die SoC-Gauges bekommen
SOC_TYPEN = {"speicher", "e-auto"}

# Typen die im Live-Dashboard übersprungen werden (Durchleiter, keine eigene Messgröße)
SKIP_TYPEN = {"wechselrichter"}

# Kategorien für Tagesverlauf-Aggregation (Legacy, wird noch für Live-Komponenten-Keys genutzt)
TAGESVERLAUF_KATEGORIE = {
    "pv-module": "pv",
    "balkonkraftwerk": "pv",
    "speicher": "batterie",
    "e-auto": "eauto",
    "wallbox": "eauto",
    "waermepumpe": "waermepumpe",
    "sonstiges": "sonstige",
}

# Tagesverlauf: Kategorie + Seite (quelle/senke) + Farbe pro Investitionstyp
TV_SERIE_CONFIG: dict[str, dict] = {
    # Farben kanonisch aus Frontend lib/colors.ts (KOMPONENTEN_FARBEN/COLORS, Regel A/B
    # 2026-06-24). Guard: tests/test_live_tagesverlauf_farben_kanon.py.
    "pv-module":       {"kategorie": "pv",          "seite": "quelle", "farbe": "#f59e0b", "bidirektional": False, "max_w": 100_000},
    "balkonkraftwerk": {"kategorie": "pv",          "seite": "quelle", "farbe": "#f59e0b", "bidirektional": False, "max_w":   2_000},
    "speicher":        {"kategorie": "batterie",    "seite": "quelle", "farbe": "#3b82f6", "bidirektional": True,  "max_w":  50_000},
    "wallbox":         {"kategorie": "wallbox",     "seite": "senke",  "farbe": "#06b6d4", "bidirektional": False, "max_w":  50_000},
    "e-auto":          {"kategorie": "eauto",       "seite": "senke",  "farbe": "#14b8a6", "bidirektional": False, "max_w":  50_000},
    "waermepumpe":     {"kategorie": "waermepumpe", "seite": "senke",  "farbe": "#ef4444", "bidirektional": False, "max_w":  20_000},
    "sonstiges":       {"kategorie": "sonstige",    "seite": "senke",  "farbe": "#6b7280", "bidirektional": False, "max_w": 100_000},
}

# Separate Key-Prefixe für Live-Komponenten (Energiefluss)
LIVE_KEY_PREFIX = {
    "wallbox": "wallbox",
}


@dataclass(frozen=True)
class TagesverlaufSerie:
    """Kern-Spezifikation einer Investitions-Tagesverlauf-Serie.

    Enthält NUR die Felder, die zwischen Live-Chart-Pfad
    (``live_tagesverlauf_service``) und Backfill-Pfad
    (``energie_profil.backfill``) symmetrisch sein müssen. Chart-Metadaten
    (label/farbe/max_w) und die Netz-/PV-Gesamt-Repräsentation legt jeder
    Konsument selbst darüber (sie unterscheiden sich legitim je Downstream).

    ``suffix`` markiert die WP-Split-Serien (``heizen``/``warmwasser``) für die
    Label-/Farb-Rekonstruktion im Live-Pfad.
    """

    key: str
    inv_id: str
    kategorie: str
    seite: str
    bidirektional: bool
    suffix: Optional[str] = None


def baue_investitions_serien(
    inv_live_map: dict[str, dict[str, str]],
    investitionen: dict[str, "object"],
) -> tuple[list[TagesverlaufSerie], dict[str, list[str]]]:
    """Single Source of Truth für die Investitions-Serien-Selektion des
    Tagesverlaufs (Issue #318, M1).

    Vor v3.35.x bauten ``live_tagesverlauf_service`` und ``energie_profil.backfill``
    dieselbe Selektion zweimal parallel — ohne Symmetrie-Test (S1 umging die
    Achse). Drift: der Pool-Dedup (#227, gleiche ``leistung_w``-Entity →
    Wallbox vor E-Auto) lief NUR im Live-Pfad. Da ``aggregate_day`` seine
    ``punkte`` für den Scheduler aus ``get_tagesverlauf`` (live, mit Dedup) und
    für den Backfill aus ``prefetched_tagesverlauf`` (backfill, ohne Dedup) zog,
    konnte derselbe Tag je nach Trigger unterschiedliche ``TEP.komponenten``/
    Peaks erzeugen — gleiche Aggregator-Asymmetrie-Klasse wie #290/#298
    ([[feedback_aggregator_symmetrie]]).

    Diese Funktion ist jetzt die einzige Stelle, in der die Selektion lebt —
    inklusive Pool-Dedup, damit beide Pfade deckungsgleich sind.

    Args:
        inv_live_map: ``{inv_id: {leistung_w: entity_id, ...}}`` aus
            ``extract_live_config``.
        investitionen: ``{inv_id: Investition}`` (typ/parameter/parent_id/…).

    Returns:
        ``(serien, serie_entities)`` — Kern-Serien in stabiler, Pool-deduplizierter
        Reihenfolge + ``{serie_key: [entity_id]}``.
    """
    serien: list[TagesverlaufSerie] = []
    serie_entities: dict[str, list[str]] = {}

    for inv_id, live in inv_live_map.items():
        inv = investitionen.get(inv_id)
        if not inv:
            continue
        typ = inv.typ
        if typ in SKIP_TYPEN:
            continue

        has_leistung = live.get("leistung_w")

        # WP mit getrennter Strommessung → zwei Serien (Heizen/Warmwasser)
        if not has_leistung and typ == "waermepumpe":
            config = TV_SERIE_CONFIG.get("waermepumpe")
            if config:
                # ⭐ **Drei Betriebsarten, nicht zwei** (N-439, 13.09.2026).
                # `leistung_kuehlen_w` ist seit W-13 (26.08.) jeder Wärmepumpe
                # zuordenbar und wurde bis hierher an keiner Station gelesen —
                # wer nur den Kühlsensor hatte, bekam gar keine Serie und stand
                # darunter als „nicht dargestellt". Die drei Felder sind
                # **disjunkte Momentanwerte** desselben Kältekreises
                # (`core/betriebsmodus.py`: ein Umschaltventil, dietmar1968
                # T89667 #225), also dieselbe Bauform wie ihre zwei Nachbarn.
                for suffix, field in (
                    ("heizen", "leistung_heizen_w"),
                    ("warmwasser", "leistung_warmwasser_w"),
                    ("kuehlen", "leistung_kuehlen_w"),
                ):
                    eid = live.get(field)
                    if eid:
                        key = f"waermepumpe_{inv_id}_{suffix}"
                        serien.append(TagesverlaufSerie(
                            key=key, inv_id=inv_id, kategorie=config["kategorie"],
                            seite=config["seite"], bidirektional=config["bidirektional"],
                            suffix=suffix,
                        ))
                        serie_entities[key] = [eid]
            continue

        if not has_leistung:
            continue

        # E-Auto mit Parent (Wallbox) überspringen — Wallbox misst bereits
        if typ == "e-auto" and inv.parent_investition_id is not None:
            continue

        config = TV_SERIE_CONFIG.get(typ)
        if not config:
            continue

        seite = config["seite"]
        bidirektional = config["bidirektional"]
        if typ == "sonstiges" and isinstance(inv.parameter, dict):
            kat = inv.parameter.get("kategorie", SONSTIGES_KATEGORIE_UNGEPFLEGT)
            # #377: Ein Zähler bekommt **keine Serie**. Er führt keine
            # Leistung, und m³ auf einer kW-Achse ist genau die
            # Einheiten-Verwechslung, vor der der `soc_je_speicher`-Kommentar
            # in `models/tages_energie_profil.py` warnt. Die Alternative
            # („Serie mit Seite quelle/senke") gibt es nicht — er hat keine
            # Seite, das ist der dritte Zustand.
            if ist_zaehler_kategorie(kat):
                continue
            if kat == "erzeuger":
                seite = "quelle"
            elif kat == "speicher":
                bidirektional = True

        serie_key = f"{config['kategorie']}_{inv_id}"
        serien.append(TagesverlaufSerie(
            key=serie_key, inv_id=inv_id, kategorie=config["kategorie"],
            seite=seite, bidirektional=bidirektional, suffix=None,
        ))
        serie_entities[serie_key] = [live["leistung_w"]]

    # Pool-Doppelzählungs-Schutz (#227): teilen zwei Investitionen dieselbe
    # primäre `leistung_w`-Entity (Wallbox + E-Auto ohne gesetzten
    # parent_investition_id — beide messen denselben Stromfluss), bleibt nur
    # die wichtigere Serie. Wallbox > E-Auto (Infrastruktur vor Fahrzeug),
    # Rest stabil in Originalreihenfolge. Vorher nur im Live-Pfad → Backfill
    # zählte doppelt (der M1-Drift dieses Issues).
    prioritaet = {"wallbox": 0, "eauto": 1}
    serien.sort(key=lambda s: prioritaet.get(s.kategorie, 2))
    gesehen_entity: set[str] = set()
    dedupliziert: list[TagesverlaufSerie] = []
    for serie in serien:
        eids = serie_entities.get(serie.key, [])
        primary = eids[0] if eids else None
        if primary and primary in gesehen_entity:
            serie_entities.pop(serie.key, None)
            continue
        if primary:
            gesehen_entity.add(primary)
        dedupliziert.append(serie)

    # Strukturelle Quellen-Regel für E-Mob (#356) — dieselbe wie auf der
    # Monatsebene (`eauto_wirtschaftlichkeit.get_emob_heimladung_canonical`,
    # Phase 2a / Entscheidung 1): **existiert eine Wallbox-Serie, ist sie die
    # Quelle der Heimladung**; sonst das E-Auto.
    #
    # Die beiden Regeln darüber greifen nur, wenn das E-Auto einen Parent hat
    # oder **dieselbe** `leistung_w`-Entity teilt. Misst das Fahrzeug mit einem
    # eigenen Sensor, lief derselbe Ladevorgang zweimal ins `komponenten`-JSON:
    # Anlage 1, 2026-08-06, Zähler 12,00 kWh → `wallbox_2` −12,00 **und**
    # `eauto_1` −17,32; die HA-Historie beider Sensoren zeigt Ladung in genau
    # denselben fünf Stunden (893/779 W · 8237/8773 W · 4239/4406 W · 979/920 W
    # · 2067/2445 W) — dieselbe Energie, an zwei Enden gemessen.
    #
    # Ladung, die **nicht** über die eigene Wallbox lief (auswärts), fällt damit
    # aus dem Tagesverlauf. Das ist beabsichtigt: sie ist kein Hausstrom und
    # stünde sonst als Senke in einer Bilanz, durch die sie nie geflossen ist.
    if any(s.kategorie == "wallbox" for s in dedupliziert):
        behalten: list[TagesverlaufSerie] = []
        for serie in dedupliziert:
            if serie.kategorie == "eauto":
                serie_entities.pop(serie.key, None)
                continue
            behalten.append(serie)
        dedupliziert = behalten

    return dedupliziert, serie_entities


#: Die Felder, aus denen der Tagesverlauf überhaupt eine Leistungskurve bauen
#: kann. `leistung_w` ist der Regelfall; die drei Funktions-Felder tragen die
#: Wärmepumpe mit getrennter Strommessung (s. {@link baue_investitions_serien}).
#:
#: ⚠ **`leistung_kuehlen_w` gehört dazu, seit es eine Serie erzeugt** (N-439).
#: Die Liste steht im Anwendersatz *„Nicht dargestellt (kein HA-Leistungssensor)"*
#: (N-447) — ein Feld, das eine Fläche zeichnet, aber hier fehlt, macht genau
#: die Falschaussage, gegen die dieser Satz gebaut wurde.
LEISTUNGS_FELDER: tuple[str, ...] = (
    "leistung_w", "leistung_heizen_w", "leistung_warmwasser_w",
    "leistung_kuehlen_w",
)


def uebersprungene_investitionen(
    investitionen: Mapping[str, object],
    inv_ids_mit_serie: Container[str],
    hat_leistungsquelle: Callable[[str], bool],
) -> list[str]:
    """Welche Geräte der Tagesverlauf **nicht** zeichnet — die EINE Bedingung
    hinter dem Anwendersatz *„Nicht dargestellt (kein HA-Leistungssensor)"*.

    ⛔ **N-447: bis 12.09.2026 beantworteten beide Pfade diese Frage anders, und
    beide falsch.** Der HA-Pfad sammelte jede Investition ohne ``leistung_w`` —
    also auch die Wärmepumpe mit getrennten Leistungssensoren, die zwölf Zeilen
    später in **zwei** Serien zerlegt und gezeichnet wurde: Der Anwender sah
    seine Wärmepumpe zweimal im Chart und darüber den Satz, sie fehle. Der
    MQTT-Pfad machte denselben Fehler spiegelverkehrt (``if typ != "waermepumpe"``)
    und ließ eine Wärmepumpe **ganz ohne** Leistungsquelle wortlos verschwinden.
    SOLL §3.3/**S3**: *„Eine Sicht, die weniger zeigt als die Nachbarsicht, sagt
    warum"* — hier sagte sie das Gegenteil des Sichtbaren.

    ⭐ **Der Satz behauptet ZWEI Dinge, also prüft die Bedingung beide:** das
    Gerät ist nicht gezeichnet (keine Serie) **und** der Grund dafür ist eine
    fehlende Leistungsquelle. Die zweite Hälfte ist nicht redundant, sie ist die
    Abgrenzung: ``baue_investitions_serien`` lässt Geräte auch aus **anderen**
    Gründen weg, und für die wäre der Satz eine Falschaussage — das E-Auto an
    einer Wallbox (die es mitmisst), zwei Investitionen an derselben Entity
    (Pool-Dedup #227) und ein Zähler unter *Sonstiges* (#377, hat keine Seite).
    Alle drei haben einen Leistungssensor; sie standen deshalb auch bisher nicht
    in dieser Liste und dürfen es nicht anfangen.

    Args:
        investitionen: ``{inv_id: Investition}`` — dieselbe Map wie beim
            Serien-Bau, damit die Frage über derselben Menge gestellt wird.
        inv_ids_mit_serie: die IDs, für die der Serien-Bauer geliefert hat.
        hat_leistungsquelle: ``inv_id -> bool``; die Pfade beantworten sie
            verschieden (HA aus dem Mapping, MQTT aus den Snapshot-Keys) —
            **die Regel darüber ist dieselbe.**
    """
    uebersprungen: list[str] = []
    for inv_id, inv in investitionen.items():
        typ = getattr(inv, "typ", None)
        if typ in SKIP_TYPEN or typ not in TV_SERIE_CONFIG:
            continue
        if inv_id in inv_ids_mit_serie:
            continue
        if hat_leistungsquelle(inv_id):
            continue
        uebersprungen.append(getattr(inv, "bezeichnung", None) or typ)
    return uebersprungen


def inv_ids_mit_serie(serien: Sequence[TagesverlaufSerie]) -> set[str]:
    """Die Investitionen, für die {@link baue_investitions_serien} geliefert hat."""
    return {s.inv_id for s in serien}


def _legacy_invert_ablage(mapping: dict, field_id: str) -> tuple[Optional[dict], Optional[str]]:
    """Wo das Legacy-`live_invert` einer Feld-ID liegt: ``(Ablage, Key)`` oder ``(None, None)``.

    Die Zerlegung ist dieselbe wie in `extract_live_config` unten — eine
    zweite Lesart der Feld-ID hätte hier genau die Drift erzeugt, die N-562
    behebt.
    """
    if not isinstance(field_id, str):
        return None, None
    if field_id.startswith("basis_live_"):
        basis = mapping.get("basis")
        ablage = basis.get("live_invert") if isinstance(basis, dict) else None
        return (ablage if isinstance(ablage, dict) else None), field_id[len("basis_live_"):]
    if field_id.startswith("inv_live_"):
        inv_id, sep, key = field_id[len("inv_live_"):].partition("_")
        if not (sep and inv_id.isdigit() and key):
            return None, None
        inv_data = (mapping.get("investitionen") or {}).get(inv_id)
        ablage = inv_data.get("live_invert") if isinstance(inv_data, dict) else None
        return (ablage if isinstance(ablage, dict) else None), key
    return None, None


def legacy_invert_aktiv(mapping: dict, field_id: str) -> bool:
    """True, wenn das Feld über ein Legacy-`live_invert` (vor v4) umgekehrt wird.

    ⭐ **N-562 (T89667 #378):** `extract_live_config` unioniert dieses Flag mit
    dem Store `sensor_mapping.invertieren` — es **wirkt** also. Die Fläche las bis
    dahin nur den Store und zeigte den Schalter grau, während der Wert weiter
    umgedreht wurde. Wer wissen will, ob ein Feld umgekehrt ist, fragt beide.
    """
    ablage, key = _legacy_invert_ablage(mapping, field_id)
    return bool(ablage and ablage.get(key))


def entferne_legacy_invert(mapping: dict, field_id: str) -> bool:
    """Entfernt das Legacy-`live_invert` des Feldes; True, wenn eines da war.

    ⭐ **N-562:** Ohne das blieb eine vor v4 gesetzte Umkehr **unabschaltbar** —
    der Schalter entfernte nur den Store-Eintrag, die Union in
    `extract_live_config` hielt das Legacy-Flag aktiv, und die Startup-Migration
    läuft nur einmal (`_apply_once`), räumt also nie nach. Mutiert ``mapping``
    in-place; der Aufrufer setzt `flag_modified`.
    """
    ablage, key = _legacy_invert_ablage(mapping, field_id)
    if not ablage or key not in ablage:
        return False
    war_aktiv = bool(ablage.pop(key))
    return war_aktiv


def extract_live_config(anlage: Anlage) -> tuple[
    dict[str, str], dict[str, dict[str, str]],
    dict[str, bool], dict[str, dict[str, bool]],
]:
    """
    Extrahiert Live-Sensor-Konfiguration aus sensor_mapping.

    Returns:
        (basis_live, inv_live_map, basis_invert, inv_invert_map)
        basis_live: {einspeisung_w: entity_id, netzbezug_w: entity_id}
        inv_live_map: {inv_id: {leistung_w: entity_id, soc: entity_id}}
        basis_invert: {einspeisung_w: True}  — Vorzeichen invertieren
        inv_invert_map: {inv_id: {leistung_w: True}}

    ⚠ **Zustandsfelder sind hier ausgeschlossen** (#263 K-2,
    `field_definitions.ZUSTAND_LIVE_FELDER`). Alles, was durch diese Funktion
    kommt, landet in `live_power_service._states_zu_w` und damit in
    `normalize_to_w(float(state))` — ein `climate`-Zustand („heat") ergibt dort
    garantiert `None`. Er stünde also alle 5 Sekunden als Abruf in der Liste und
    lieferte nie etwas. Der Betriebsmodus wird stattdessen einmal je
    Aggregationslauf über `ha_state_service.get_zustand_history` gelesen.
    """
    mapping = anlage.sensor_mapping or {}

    basis_live: dict[str, str] = {}
    inv_live_map: dict[str, dict[str, str]] = {}
    basis_invert: dict[str, bool] = {}
    inv_invert_map: dict[str, dict[str, bool]] = {}

    basis = mapping.get("basis", {})
    if isinstance(basis.get("live"), dict):
        basis_live = {k: v for k, v in basis["live"].items() if v}
    # Legacy-Invert (`basis.live_invert`) — wird unten mit dem vereinheitlichten
    # Store (`sensor_mapping.invertieren`) vereinigt (Datenquellen-V4-Invert-SoT).
    if isinstance(basis.get("live_invert"), dict):
        basis_invert = {k: v for k, v in basis["live_invert"].items() if v}

    for inv_id, inv_data in mapping.get("investitionen", {}).items():
        if isinstance(inv_data, dict) and isinstance(inv_data.get("live"), dict):
            live = {
                k: v for k, v in inv_data["live"].items()
                if v and not ist_zustand_feld(k)
            }
            if live:
                inv_live_map[inv_id] = live
        if isinstance(inv_data, dict) and isinstance(inv_data.get("live_invert"), dict):
            invert = {k: v for k, v in inv_data["live_invert"].items() if v}
            if invert:
                inv_invert_map[inv_id] = invert

    # Vereinheitlichter Invert-Store (Datenquellen-V4): `sensor_mapping.invertieren`
    # = {field_id: true}, feld-/wert-level und QUELLEN-UNABHÄNGIG. EINE Wahrheit für
    # ALLE Consumer (Live-Power finaler Pass + apply_invert_to_history in
    # tagesverlauf/verbrauchsprofil/history). Union mit dem Legacy-`live_invert`
    # oben (defensiv für noch nicht migrierte Installationen; Invert ist idempotent
    # boolesch → Union appliziert genau einmal). Nur W-/Live-Felder (`*_live_*`).
    invert_store = mapping.get("invertieren")
    if isinstance(invert_store, dict):
        for field_id, flag in invert_store.items():
            if not flag or not isinstance(field_id, str):
                continue
            if field_id.startswith("basis_live_"):
                basis_invert[field_id[len("basis_live_"):]] = True
            elif field_id.startswith("inv_live_"):
                inv_id, sep, key = field_id[len("inv_live_"):].partition("_")
                if sep and inv_id.isdigit() and key:
                    inv_invert_map.setdefault(inv_id, {})[key] = True

    # Fallback: altes live_sensors-Dict (Migration)
    if not basis_live and not inv_live_map:
        legacy = mapping.get("live_sensors", {})
        if legacy:
            if legacy.get("einspeisung_w"):
                basis_live["einspeisung_w"] = legacy["einspeisung_w"]
            if legacy.get("netzbezug_w"):
                basis_live["netzbezug_w"] = legacy["netzbezug_w"]
            if any(k not in ("einspeisung_w", "netzbezug_w") for k in legacy):
                logger.info(
                    "Anlage %s nutzt noch legacy live_sensors — "
                    "bitte Sensor-Zuordnung im Wizard aktualisieren",
                    anlage.id,
                )

    return basis_live, inv_live_map, basis_invert, inv_invert_map


def extract_quellen_live(anlage: Anlage) -> tuple[
    dict[str, tuple], dict[str, dict[str, tuple]], set[str],
]:
    """Explizite Datenquellen-Zuordnungen (`quellen`-Map) der LIVE-Felder (C2a).

    Read-Through-Resolver-Eingabe: NUR Felder mit ausdrücklichem `quellen`-Eintrag;
    Felder ohne Eintrag bleiben dem heutigen Merge überlassen (Regressionsschutz).
    Energie-Felder (`basis_energy_*`/`inv_energy_*`) werden hier ignoriert (C2b).

    Returns:
        (basis_overrides, inv_overrides, ha_entities)
        basis_overrides: {live_key: (quelle, entity_id|None, invertieren)}
        inv_overrides:   {inv_id: {live_key: (quelle, entity_id|None, invertieren)}}
        ha_entities:     set der HA-Entity-IDs, die für ha_app/ha_connector zu lesen sind

    `invertieren` (Datenquellen-V4-Invert-Modell): Per-Feld-Vorzeichen-Flip als
    Eigenschaft der Quellen-Zuordnung. Wird am Read (HA/Inbound) angewendet; beim
    Gateway lebt der Sign im Republish-Transform (`mqtt_gateway_mappings`) → hier
    für Gateway-Felder bewusst False, kein Doppel-Invert.
    """
    mapping = anlage.sensor_mapping or {}
    quellen = mapping.get("quellen") if isinstance(mapping, dict) else None
    basis_ov: dict[str, tuple] = {}
    inv_ov: dict[str, dict[str, tuple]] = {}
    ha_entities: set[str] = set()
    if not isinstance(quellen, dict):
        return basis_ov, inv_ov, ha_entities

    for field_id, entry in quellen.items():
        if not isinstance(entry, dict):
            continue
        quelle = entry.get("quelle")
        entity_id = entry.get("entity_id")
        # Invert ist NICHT mehr quellen-gekoppelt (Datenquellen-V4): das Vorzeichen
        # lebt im vereinheitlichten `sensor_mapping.invertieren`-Store und wird als
        # finaler Pass in `_collect_values` angewendet (einmal, quellen-unabhängig).
        # Der 3-Tuple-Slot bleibt zur Kompatibilität, trägt aber konstant False.
        invertieren = False
        if isinstance(field_id, str) and field_id.startswith("basis_live_"):
            key = field_id[len("basis_live_"):]
            basis_ov[key] = (quelle, entity_id, invertieren)
        elif isinstance(field_id, str) and field_id.startswith("inv_live_"):
            rest = field_id[len("inv_live_"):]
            inv_id, sep, key = rest.partition("_")
            if not sep or not inv_id.isdigit() or not key:
                continue
            inv_ov.setdefault(inv_id, {})[key] = (quelle, entity_id, invertieren)
        else:
            continue  # Energie-Felder → C2b
        if quelle in ("ha_app", "ha_connector") and entity_id:
            ha_entities.add(entity_id)

    return basis_ov, inv_ov, ha_entities
