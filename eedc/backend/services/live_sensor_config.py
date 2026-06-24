"""
Live Sensor Konfiguration - Konstanten und Mapping-Extraktion für Live-Daten.

Ausgelagert aus live_power_service.py (Schritt 1 des Refactorings).
Enthält nur reine Daten und Logik ohne I/O.
"""

import logging
from dataclasses import dataclass
from typing import Optional

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
                for suffix, field in (
                    ("heizen", "leistung_heizen_w"),
                    ("warmwasser", "leistung_warmwasser_w"),
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
            kat = inv.parameter.get("kategorie", "verbraucher")
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

    return dedupliziert, serie_entities


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
    """
    mapping = anlage.sensor_mapping or {}

    basis_live: dict[str, str] = {}
    inv_live_map: dict[str, dict[str, str]] = {}
    basis_invert: dict[str, bool] = {}
    inv_invert_map: dict[str, dict[str, bool]] = {}

    basis = mapping.get("basis", {})
    if isinstance(basis.get("live"), dict):
        basis_live = {k: v for k, v in basis["live"].items() if v}
    if isinstance(basis.get("live_invert"), dict):
        basis_invert = {k: v for k, v in basis["live_invert"].items() if v}

    for inv_id, inv_data in mapping.get("investitionen", {}).items():
        if isinstance(inv_data, dict) and isinstance(inv_data.get("live"), dict):
            live = {k: v for k, v in inv_data["live"].items() if v}
            if live:
                inv_live_map[inv_id] = live
        if isinstance(inv_data, dict) and isinstance(inv_data.get("live_invert"), dict):
            invert = {k: v for k, v in inv_data["live_invert"].items() if v}
            if invert:
                inv_invert_map[inv_id] = invert

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
