"""
Datenquellen-V4 §2i — proaktive, feld-bezogene Zuordnungs-Validierung.

Rein DIAGNOSTISCH (nie blockierend, §2d). Deckt die config-basierten (zur
Zuordnungszeit erkennbaren) Zuordnungsfehler ab; datenbasierte Checks bleiben
im Daten-Checker. Reuse statt Neubau: der Einheiten-Dimensions-Klassifikator
(`einheit_klasse`) ist die gemeinsame SoT mit `SENSOR_MAPPING_EINHEIT`.

Vier Prüfungen (Gernot 2026-07-16):
1. **Einheit** — kWh-Sensor in W-Feld / W-Sensor in kWh-Feld (#200).
2. **Aggregat-Redundanz** — Aggregat (PV gesamt / Netz kombi) neben Komponenten
   belegt → Aggregat wirkungslos (Engine-Vorrang), Inline „auf keine".
3. **state_class** — HA-Energie-Sensor ohne `state_class` → keine History/LTS.
4. **Doppelmapping** — dieselbe HA-Entity in ≥2 Feldern → Doppelzählung (#314).
"""

from __future__ import annotations

from collections import defaultdict
from typing import Optional

from backend.core.field_definitions import einheit_klasse

# ─── Aggregat ⊥ Komponenten (Engine-Vorrang, C) ─────────────────────────────
# Aggregat-Sensor wird bei vorhandenen Komponenten still ignoriert:
#   PV gesamt  — `live_komponenten_builder` `not has_individual_pv`; Energie-
#                Bilanz zählt pro WR (pv_gesamt_kwh ohne Snapshot-Counterpart).
#   Netz kombi — `_collect_values`: kombi nur wenn einspeisung_w UND netzbezug_w
#                fehlen → ≥1 Split-Feld belegt = kombi wirkungslos.
_PV_AGGREGAT_FELDER = {"pv_gesamt_kwh", "pv_gesamt_w"}
_PV_KOMPONENTEN_FELDER = {"pv_erzeugung_kwh", "leistung_w"}
_PV_KOMPONENTEN_TYPEN = {"pv-module", "balkonkraftwerk"}
_NETZ_AGGREGAT_FELDER = {"netz_kombi_w"}
_NETZ_KOMPONENTEN_FELDER = {"einspeisung_w", "netzbezug_w"}


def einheit_problem(feld_einheit: Optional[str], sensor_einheit: Optional[str]) -> Optional[dict]:
    """Leistung↔Energie-Verwechslung (#200). Nur die klare Dimension; sonst None."""
    erwartet = einheit_klasse(feld_einheit)
    tatsaechlich = einheit_klasse(sensor_einheit)
    if erwartet is None or tatsaechlich is None or erwartet == tatsaechlich:
        return None
    if erwartet == "leistung":  # Energie-Sensor im Leistungs-Feld (#674)
        return {
            "art": "einheit", "schwere": "error",
            "text": f"Leistungs-Feld, aber Energie-Sensor ({sensor_einheit}) — "
                    f"Zählerstand wird als Leistung gelesen. W/kW-Sensor wählen.",
        }
    return {  # Leistungssensor im Energie-Feld (#200)
        "art": "einheit", "schwere": "warning",
        "text": f"Energie-Feld, aber Leistungs-Sensor ({sensor_einheit}) — "
                f"kWh nur näherungsweise per Integration. kWh-Zähler wählen.",
    }


def state_class_problem(feld_einheit: Optional[str], state_class: Optional[str]) -> Optional[dict]:
    """HA-Energie-Feld (kWh) ohne `state_class` → keine History/Zeitmaschine.

    Nur Energie-Felder: Live-W liest den State direkt und braucht kein state_class
    (Symmetrie zu SENSOR_MAPPING_LTS, das Live-Mappings ignoriert).
    """
    if einheit_klasse(feld_einheit) != "energie":
        return None
    if state_class:  # 'total'/'total_increasing'/'measurement' → ok
        return None
    return {
        "art": "state_class", "schwere": "warning",
        "text": "HA-Sensor ohne state_class → keine Langzeit-Statistik/History "
                "(nur Live). Einen Sensor mit state_class wählen.",
    }


def finde_redundante_aggregate(felder: list[dict]) -> dict[str, dict]:
    """Belegte Aggregat-Felder, die durch belegte Komponenten wirkungslos sind (C).

    `felder`: [{"id", "feld", "typ", "belegt": bool}]. `belegt` = Quelle ≠ keine.
    Returns {aggregat_field_id: {"art":"redundant","schwere":"warning","grund","wirksame_felder":[…],"text"}}.
    """
    pv_komp = [
        f for f in felder
        if f.get("belegt") and f.get("typ") in _PV_KOMPONENTEN_TYPEN
        and f.get("feld") in _PV_KOMPONENTEN_FELDER
    ]
    netz_split = [
        f for f in felder
        if f.get("belegt") and f.get("typ") == "basis"
        and f.get("feld") in _NETZ_KOMPONENTEN_FELDER
    ]
    out: dict[str, dict] = {}
    for f in felder:
        if not f.get("belegt"):
            continue
        feld = f.get("feld")
        if feld in _PV_AGGREGAT_FELDER and f.get("typ") == "basis" and pv_komp:
            out[f["id"]] = {
                "art": "redundant", "schwere": "warning", "grund": "pv_aggregat",
                "wirksame_felder": [k["id"] for k in pv_komp],
                "text": "Wirkungslos: einzelne PV-Erzeugung ist zugeordnet — die "
                        "gesamt-Zuordnung wird ignoriert. Auf „keine“ setzen.",
            }
        elif feld in _NETZ_AGGREGAT_FELDER and netz_split:
            out[f["id"]] = {
                "art": "redundant", "schwere": "warning", "grund": "netz_kombi",
                "wirksame_felder": [k["id"] for k in netz_split],
                "text": "Wirkungslos: Einspeisung/Netzbezug sind einzeln zugeordnet "
                        "— der Kombi-Sensor wird ignoriert. Auf „keine“ setzen.",
            }
    return out


def finde_doppelmappings(ha_zuordnungen: dict[str, str]) -> dict[str, dict]:
    """Dieselbe HA-Entity in ≥2 Feldern → Doppelzählung (#314).

    `ha_zuordnungen`: {field_id: entity_id} nur der HA-zugeordneten Felder.
    Returns {field_id: {"art":"doppelmapping","schwere":"warning","entity_id","andere_felder":[…],"text"}}.
    """
    per_eid: dict[str, list[str]] = defaultdict(list)
    for fid, eid in ha_zuordnungen.items():
        if eid:
            per_eid[eid].append(fid)
    out: dict[str, dict] = {}
    for eid, fids in per_eid.items():
        if len(fids) >= 2:
            for fid in fids:
                out[fid] = {
                    "art": "doppelmapping", "schwere": "warning", "entity_id": eid,
                    "andere_felder": [x for x in fids if x != fid],
                    "text": f"Dieselbe HA-Entity ({eid}) ist mehreren Feldern "
                            f"zugeordnet → Doppelzählung. Nur einem Feld zuordnen.",
                }
    return out
