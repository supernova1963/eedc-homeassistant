"""
Erwartungsliste der MQTT-Inbound-Topics pro Anlage.

Zentrale Quelle für die Topic-Liste, die EEDC erwartet — basiert auf der
dynamischen Felder-Registry (`field_definitions.py`) und den konkreten
Anlage- und Investitions-IDs.

Nutzer:
- API-Endpoint `/api/live/mqtt/topics` (Anzeige im Wizard)
- Daten-Checker (Issue #134, MQTT_TOPIC_ABDECKUNG)
"""

import re
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.anlage import Anlage
from backend.models.investition import Investition
from backend.utils.investition_filter import aktiv_jetzt
from backend.core.field_definitions import (
    BASIS_LIVE_FELDER,
    get_alle_felder_fuer_investition,
    get_live_felder_fuer_investition,
)


# Wechselrichter erzeugen keine eigenen MQTT-Topics — sie liefern Daten,
# die anderen Investitionen (PV-Strings, Speicher) zugeordnet werden.
SKIP_TYPEN = {"wechselrichter"}

# Drei hartkodierte Basis-Energy-Topics (anlagenweite Aggregate).
# (key, label, beschreibung). Das frühere Label „… Monat (kWh)" war
# irreführend — es sind kumulierte Zählerstände, aus denen EEDC das
# Tagesdelta für die „Heute"-Kacheln bildet (Dirk-PN 2026-06-01).
_HEUTE_HINWEIS = (
    "Kumulierter kWh-Zählerstand. Speist die „Heute\"-Kachel — EEDC bildet "
    "das Tagesdelta gegen den Mitternachtswert (täglich resettende oder "
    "fortlaufende Zähler funktionieren beide)."
)
# (key, feld_label, einheit, beschreibung). feld_label + einheit getrennt, damit
# die Datenquellen-Fläche nach Einheit gruppieren kann (Energie-Sensoren kWh) —
# das Anzeige-`label` setzt die Einheit wieder in Klammern (rückwärtskompatibel).
BASIS_ENERGY_TOPICS = [
    ("pv_gesamt_kwh", "PV-Erzeugung Zählerstand", "kWh", _HEUTE_HINWEIS),
    ("einspeisung_kwh", "Einspeisung Zählerstand", "kWh", _HEUTE_HINWEIS),
    ("netzbezug_kwh", "Netzbezug Zählerstand", "kWh", _HEUTE_HINWEIS),
]


def _mqtt_slug(name: str) -> str:
    slug = name.strip().replace(" ", "_")
    slug = re.sub(r"[^\w.\-]", "", slug)
    return slug or "unnamed"


async def build_expected_topics(
    db: AsyncSession,
    anlage: Anlage,
    investitionen: Optional[list[Investition]] = None,
) -> list[dict]:
    """
    Liefert die erwartete Liste von MQTT-Topics für die gegebene Anlage.

    Args:
        db: Async-Session, wird genutzt um aktive Investitionen zu laden,
            wenn `investitionen` nicht durchgereicht wird.
        anlage: Die Anlage. Erwartet `id` und `anlagenname`.
        investitionen: Optional vorab geladene Investitionsliste. Wird kein
            Wert übergeben, lädt der Helfer die aktuell aktiven Investitionen
            via `aktiv_jetzt()` selbst.

    Rückgabe-Schema je Eintrag:
        {
          "topic": "eedc/1_Foo/live/inv/3_Bar/leistung_w",
          "label": "Bar – Leistung (W)",
          "kategorie": "live" | "energy",
          "typ": "basis" | <inv-typ>,
          "match_key": (cache_kind, *args),
        }

    `match_key` adressiert den Eintrag im `MqttInboundCache`:
        ("basis_live", key)                  → cache._live[aid]["basis"][key]
        ("basis_energy", key)                → cache._energy[aid][key]
        ("inv_live", inv_id, key)            → cache._live[aid]["inv"][inv_id][key]
        ("inv_energy", inv_id, feld)         → cache._energy[aid][f"inv/{inv_id}/{feld}"]
    """
    aid = anlage.id
    aname = anlage.anlagenname or f"Anlage {aid}"
    aslug = _mqtt_slug(aname)
    live_prefix = f"eedc/{aid}_{aslug}/live"
    energy_prefix = f"eedc/{aid}_{aslug}/energy"

    topics: list[dict] = []

    # Basis-Live aus Registry.
    # Die zusätzlichen Keys `feld`/`feld_label`/`einheit`/`gruppe_*` speisen die
    # feld-zentrische Datenquellen-Zuordnung (Datenquellen-V4 B2) — rückwärts-
    # kompatibel (bestehende Konsumenten lesen topic/label/kategorie/typ/match_key).
    for feld in BASIS_LIVE_FELDER:
        einheit_str = f" ({feld['einheit']})" if feld.get("einheit") else ""
        topics.append({
            "topic": f"{live_prefix}/{feld['key']}",
            "label": f"{feld['label']}{einheit_str}",
            "kategorie": "live",
            "typ": "basis",
            "match_key": ("basis_live", feld["key"]),
            "feld": feld["key"],
            "feld_label": feld["label"],
            "einheit": feld.get("einheit", ""),
            "hinweis": feld.get("hinweis", ""),
            "gruppe_id": "basis",
            "gruppe_titel": "Anlage (Basis)",
        })

    # Basis-Energy
    for key, feld_label, einheit, beschreibung in BASIS_ENERGY_TOPICS:
        topics.append({
            "topic": f"{energy_prefix}/{key}",
            "label": f"{feld_label} ({einheit})",
            "beschreibung": beschreibung,
            "kategorie": "energy",
            "typ": "basis",
            "match_key": ("basis_energy", key),
            "feld": key,
            "feld_label": feld_label,
            "einheit": einheit,
            "hinweis": beschreibung,
            "gruppe_id": "basis",
            "gruppe_titel": "Anlage (Basis)",
        })

    # Investitionen
    if investitionen is None:
        result = await db.execute(
            select(Investition).where(
                Investition.anlage_id == aid,
                aktiv_jetzt(),
            )
        )
        investitionen = list(result.scalars().all())

    for inv in investitionen:
        if inv.typ in SKIP_TYPEN:
            continue
        islug = _mqtt_slug(inv.bezeichnung)
        inv_live_prefix = f"{live_prefix}/inv/{inv.id}_{islug}"
        inv_energy_prefix = f"{energy_prefix}/inv/{inv.id}_{islug}"
        gruppe_id = f"inv:{inv.id}"
        # Nur der Gerätename; das lesbare Typ-Label (TYP_LABELS-SoT) setzt das
        # Frontend voran — kein Roh-Enum in der UI ([[feedback_typ_labels_pattern]]).
        gruppe_titel = inv.bezeichnung

        for live_feld in get_live_felder_fuer_investition(inv.typ, inv.parameter):
            topics.append({
                "topic": f"{inv_live_prefix}/{live_feld['key']}",
                "label": f"{inv.bezeichnung} – {live_feld['label']} ({live_feld['einheit']})",
                "kategorie": "live",
                "typ": inv.typ,
                "match_key": ("inv_live", str(inv.id), live_feld["key"]),
                "feld": live_feld["key"],
                "feld_label": live_feld["label"],
                "einheit": live_feld.get("einheit", ""),
                "hinweis": live_feld.get("hinweis", ""),
                "gruppe_id": gruppe_id,
                "gruppe_titel": gruppe_titel,
            })

        for feld in get_alle_felder_fuer_investition(inv.typ, inv.parameter):
            einheit_str = f" ({feld['einheit']})" if feld.get("einheit") else ""
            topics.append({
                "topic": f"{inv_energy_prefix}/{feld['feld']}",
                "label": f"{inv.bezeichnung} – {feld['label']}{einheit_str}",
                "kategorie": "energy",
                "typ": inv.typ,
                "match_key": ("inv_energy", str(inv.id), feld["feld"]),
                "feld": feld["feld"],
                "feld_label": feld["label"],
                "einheit": feld.get("einheit", ""),
                "hinweis": feld.get("hinweis", ""),
                "gruppe_id": gruppe_id,
                "gruppe_titel": gruppe_titel,
            })

    return topics
