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
    einheit_fuer,
    get_alle_felder_fuer_investition,
    get_feld_bedarf,
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
# (key, feld_label, einheit, beschreibung). feld_label +
# einheit getrennt, damit die Datenquellen-Fläche nach Einheit gruppieren kann
# (Energie-Sensoren kWh) — das Anzeige-`label` setzt die Einheit wieder in
# Klammern (rückwärtskompatibel).
BASIS_ENERGY_TOPICS = [
    ("pv_gesamt_kwh", "PV-Erzeugung Zählerstand", "kWh",
     "Zählerstand der gesamten PV-Erzeugung. Nur nötig, wenn die PV-Module keine "
     "eigenen Zähler haben — ist dort einer zugeordnet, wird diese Angabe ignoriert. "
     + _HEUTE_HINWEIS),
    ("einspeisung_kwh", "Einspeisung Zählerstand", "kWh",
     "Zählerstand der ins Netz eingespeisten Energie. Kernwert: ohne ihn lassen sich "
     "Eigenverbrauch und Autarkie nicht berechnen. Ohne Sensor im Monatsabschluss "
     "manuell erfassbar. " + _HEUTE_HINWEIS),
    ("netzbezug_kwh", "Netzbezug Zählerstand", "kWh",
     "Zählerstand der aus dem Netz bezogenen Energie. Kernwert: ohne ihn lassen sich "
     "Hausverbrauch und Stromkosten nicht berechnen. Ohne Sensor im Monatsabschluss "
     "manuell erfassbar. " + _HEUTE_HINWEIS),
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
            "bedarf": get_feld_bedarf("basis", feld["key"])[0],
            "bedarf_gruppe": get_feld_bedarf("basis", feld["key"])[1],
            "gruppe_id": "basis",
            "gruppe_titel": "Anlage (Basis)",
        })

    # Basis-Energy
    for key, feld_label, einheit, beschreibung in BASIS_ENERGY_TOPICS:
        # Wie oben und wie unten: die Klammer haengt an der Einheit, nicht am
        # Label. Heute traegt jedes dieser drei Felder eine Einheit — die Zeile
        # steht hier trotzdem, weil sie sonst die eine Stelle waere, an der ein
        # neues einheitenloses Feld wieder „Name ()" schriebe (N-299).
        einheit_str = f" ({einheit})" if einheit else ""
        topics.append({
            "topic": f"{energy_prefix}/{key}",
            "label": f"{feld_label}{einheit_str}",
            "beschreibung": beschreibung,
            "kategorie": "energy",
            "typ": "basis",
            "match_key": ("basis_energy", key),
            "feld": key,
            "feld_label": feld_label,
            "einheit": einheit,
            "hinweis": beschreibung,
            "bedarf": get_feld_bedarf("basis", key)[0],
            "bedarf_gruppe": get_feld_bedarf("basis", key)[1],
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
            # #263 K-2: Ein Zustandsfeld bekommt KEIN Standard-Topic. Der
            # MQTT-Inbound-Parser ist `float(payload)`
            # (`mqtt_inbound_service:74`) — ein Modus-String käme dort nie an.
            # Wie beim Preis-Slot (`_basis_preis_eintraege`) bleibt `topic`
            # deshalb leer: als erwartetes Topic gelistet wäre es eine Lücke,
            # die niemand schließen kann, und der Abdeckungs-Check (#134)
            # meldete sie dauerhaft. Das Feld selbst bleibt in der Liste —
            # die Zuordnungs-Fläche liest sie und bietet HA an.
            ist_zustand = bool(live_feld.get("zustand"))
            # N-299: Ein Zustandsfeld hat KEINE Einheit, und das ist Absicht
            # (`betriebsmodus`: Heizen/Kuehlen/Aus ist kein Messwert). Die
            # Klammer unbedingt zu setzen schrieb „Betriebsmodus ()" — sichtbar
            # im Historie-Vermerk der Datenquellen-Flaeche, der dieses Label
            # ueber `_feld_label` liest. Dieselbe Bildung wie 20 Zeilen tiefer.
            einheit_str = (
                f" ({live_feld['einheit']})" if live_feld.get("einheit") else ""
            )
            topics.append({
                "topic": "" if ist_zustand else f"{inv_live_prefix}/{live_feld['key']}",
                "zustand": ist_zustand,
                "label": f"{inv.bezeichnung} – {live_feld['label']}{einheit_str}",
                "kategorie": "live",
                "typ": inv.typ,
                "match_key": ("inv_live", str(inv.id), live_feld["key"]),
                "feld": live_feld["key"],
                "feld_label": live_feld["label"],
                "einheit": live_feld.get("einheit", ""),
                "hinweis": live_feld.get("hinweis", ""),
                "bedarf": get_feld_bedarf(inv.typ, live_feld["key"], inv.parameter)[0],
                "bedarf_gruppe": get_feld_bedarf(inv.typ, live_feld["key"], inv.parameter)[1],
                "erweitert": bool(live_feld.get("erweitert")),
                "gruppe_id": gruppe_id,
                "gruppe_titel": gruppe_titel,
            })

        for feld in get_alle_felder_fuer_investition(inv.typ, inv.parameter):
            # #377: Die Einheit kann am GERÄT hängen (Zählerstand: m³ / l / …)
            # statt am Feld. `einheit_fuer` ist der eine Leser dafür — ohne ihn
            # bliebe `einheit_str` beim Zählerstand leer, und das Topic hieße
            # „Gaszähler – Zählerstand" ohne jeden Hinweis darauf, was der
            # Absender schicken soll.
            feld_einheit = einheit_fuer(feld["feld"], inv)
            einheit_str = f" ({feld_einheit})" if feld_einheit else ""
            topics.append({
                "topic": f"{inv_energy_prefix}/{feld['feld']}",
                "label": f"{inv.bezeichnung} – {feld['label']}{einheit_str}",
                "kategorie": "energy",
                "typ": inv.typ,
                "match_key": ("inv_energy", str(inv.id), feld["feld"]),
                "feld": feld["feld"],
                "feld_label": feld["label"],
                "einheit": feld_einheit,
                "hinweis": feld.get("hinweis", ""),
                # Mit `inv.parameter`, weil (typ, feld) allein die Wärmemengen-
                # Erwartung einer Split-Klimaanlage nicht auflösen kann (N-86).
                "bedarf": get_feld_bedarf(inv.typ, feld["feld"], inv.parameter)[0],
                "bedarf_gruppe": get_feld_bedarf(inv.typ, feld["feld"], inv.parameter)[1],
                # R1: an dieser Bauart untypisch, aber möglich (`weich`). Roh
                # durchgereicht wie `bedingung`/`nur_manuell` — die Fläche
                # entscheidet, ob das Feld in der ersten Reihe steht oder hinter
                # „Weitere Größen erfassen".
                "erweitert": bool(feld.get("erweitert")),
                # Geräteklassen-Verletzung: die Größe gibt es an dieser Bauart
                # NICHT. Die Fläche nimmt sie heraus, solange keine Quelle
                # zugeordnet ist — mit Quelle bleibt sie sichtbar und damit
                # löschbar (N-304).
                "nicht_an_dieser_bauart": bool(feld.get("nicht_an_dieser_bauart")),
                # Roh durchgereicht — die Zuordnungs-Fläche wertet selbst aus
                # (markieren statt filtern, s. get_felder_fuer_investition).
                # Auch `nur_manuell` wird hier NICHT gefiltert: die Registry ist
                # die SoT „welche Felder gibt es", und ein bereits zugeordnetes
                # Feld muss sichtbar bleiben, sonst lässt sich die Zuordnung
                # nicht mehr entfernen. Die Fläche entscheidet (routes/datenquellen.py).
                "bedingung": feld.get("bedingung"),
                "bedingung_anlage": feld.get("bedingung_anlage"),
                "nur_manuell": bool(feld.get("nur_manuell")),
                "gruppe_id": gruppe_id,
                "gruppe_titel": gruppe_titel,
            })

    return topics
