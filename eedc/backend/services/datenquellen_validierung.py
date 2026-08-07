"""
Datenquellen-V4 §2i — proaktive, feld-bezogene Zuordnungs-Validierung.

Rein DIAGNOSTISCH (nie blockierend, §2d). Deckt die config-basierten (zur
Zuordnungszeit erkennbaren) Zuordnungsfehler ab; datenbasierte Checks bleiben
im Daten-Checker. Reuse statt Neubau: der Einheiten-Dimensions-Klassifikator
(`einheit_klasse`) ist die gemeinsame SoT mit `SENSOR_MAPPING_EINHEIT`.

Fünf Prüfungen (Gernot 2026-07-16; Takt: D2/#343, 2026-07-18):
1. **Einheit** — kWh-Sensor in W-Feld / W-Sensor in kWh-Feld (#200).
2. **Aggregat-Redundanz** — Aggregat (PV gesamt / Netz kombi) neben Komponenten
   belegt → Aggregat wirkungslos (Engine-Vorrang), Inline „auf keine". Je
   Aggregat-Feld eigene Bedingung, s. Kommentar-Block unten (N131 §4).
3. **state_class** — HA-Energie-Sensor ohne `state_class` → keine History/LTS.
4. **Doppelmapping** — dieselbe HA-Entity in ≥2 Feldern → Doppelzählung (#314).
5. **Takt** — kWh-Zähler mit nur sprunghaften Updates (Session-Ende-Statistik,
   #343) — Kernlogik hier, Datenbeschaffung (REST-History) im Aufrufer; läuft
   nur ON-DEMAND im Pick-Moment (nicht im /felder-Batch — History-Kosten).
"""

from __future__ import annotations

from collections import defaultdict
from typing import Optional

from backend.core.field_definitions import einheit_klasse

# ─── Aggregat ⊥ Komponenten (Engine-Vorrang, C) ─────────────────────────────
# Aggregat-Sensor wird bei vorhandenen Komponenten still ignoriert — ABER die
# beiden PV-Aggregat-Felder tragen ZWEI verschiedene Rollen und haben deshalb
# je eigene Bedingung (2026-07-29, Befund N131 §4):
#
#   PV gesamt (W)   — Live. `live_komponenten_builder:267` hängt das Aggregat
#                     an `not has_individual_pv`, und eine PV-Komponente
#                     entsteht dort NUR mit `leistung_w` (`val_w is None` →
#                     `continue`, :107). Ein einziges belegtes `leistung_w`
#                     macht das Live-Aggregat wirkungslos.
#   PV gesamt (kWh) — Monat. Das Feld landet über `basis["pv_gesamt"]` in
#                     `Monatsdaten.pv_erzeugung_kwh` und ist damit der EINGANG
#                     von `resolve_pv_je_modul`: es füllt die Lücken der Module
#                     OHNE eigenen Wert. Wirkungslos ist es erst, wenn es keine
#                     Lücke mehr gibt — sonst rät die Fläche, genau die Quelle
#                     abzuschalten, aus der die Anlagensumme kommt (Stufe 3 →
#                     QUELLE_FEHLT → 0 für die ganze Anlage).
#   Netz kombi      — `_collect_values`: kombi nur wenn einspeisung_w UND
#                     netzbezug_w fehlen → ≥1 Split-Feld belegt = wirkungslos.
#
# Die kWh-Bedingung ist NICHT neu erfunden: sie ist die zweite Bedingung von
# `core/database.py::_migrate_pv_erzeugung_aggregat_clear` („JEDE im Monat
# aktive PV-Quelle hat einen eigenen Wert") — dieselbe Frage („darf das
# Aggregat weg?"), deshalb dieselbe Antwort. Wie dort zählen `pv-module` UND
# `balkonkraftwerk`: das Aggregat verteilt zwar nur auf `pv-module`, aber
# Schweigen ist die sichere Richtung — eine überflüssige Zuordnung kostet
# nichts, ein befolgter falscher Rat kostet die Anlagensumme.
_PV_AGGREGAT_FELD_MONAT = "pv_gesamt_kwh"
_PV_AGGREGAT_FELD_LIVE = "pv_gesamt_w"
_PV_KOMPONENTEN_FELD_MONAT = "pv_erzeugung_kwh"
_PV_KOMPONENTEN_FELD_LIVE = "leistung_w"
_PV_KOMPONENTEN_TYPEN = {"pv-module", "balkonkraftwerk"}
_NETZ_AGGREGAT_FELDER = {"netz_kombi_w"}
_NETZ_KOMPONENTEN_FELDER = {"einspeisung_w", "netzbezug_w"}


def finde_aggregat_ohne_tageszaehler(felder: list[dict]) -> dict[str, dict]:
    """Anlagen-PV-Zählerstand, der die Tagesebene nicht erreichen kann (F-7).

    Gegenstück zu `finde_redundante_aggregate`: dort ist das Aggregat
    **wirkungslos**, weil jede Komponente ihren eigenen Wert hat — hier ist es
    **wirksam, aber nur für den Monat**. Die Tages-/Stundenebene entsteht
    ausschließlich aus kumulativen Zählern je Komponente; `basis_energy_pv_gesamt_kwh`
    hat kein Snapshot-Gegenstück (`snapshot/keys.py::_energy_field_id_to_sensor_key`
    liefert dafür `None`, `BASIS_ZAEHLER_FELDER` kennt nur Einspeisung/Netzbezug).

    Gemeldet wird **nur**, wenn die betroffene Komponente einen belegten
    Leistungssensor hat: dann lässt sich in Home Assistant ein Integral-Sensor
    daraus bauen und der Anwender kann die Lage auflösen. Wer nur einen
    Summenzähler besitzt, konfiguriert nichts falsch und bekommt deshalb kein
    Warndreieck, sondern den Hinweistext an der Komponenten-Zeile
    (`_PV_AGGREGAT_NUR_MONAT_TEXT`) — sonst wäre es der reflexhafte
    Fehlerhinweis, den wir sonst vermeiden ([[feedback_user_fehlermeldungen]]).

    `felder`: wie `finde_redundante_aggregate` — ALLE Felder aller aktiven
    Investitionen, auch die unbelegten.
    Returns {aggregat_field_id: {"art":"nur_monat","schwere":"warning","grund","text"}}.
    """
    lueckenhafte_typen = {
        f.get("typ") for f in felder
        if f.get("typ") in _PV_KOMPONENTEN_TYPEN
        and f.get("feld") == _PV_KOMPONENTEN_FELD_MONAT
        and not f.get("belegt")
    }
    if not lueckenhafte_typen:
        return {}  # keine Lücke ⇒ `finde_redundante_aggregate` ist zuständig
    mit_leistung = [
        f for f in felder
        if f.get("belegt") and f.get("typ") in _PV_KOMPONENTEN_TYPEN
        and f.get("feld") == _PV_KOMPONENTEN_FELD_LIVE
    ]
    if not mit_leistung:
        return {}  # nicht auflösbar ⇒ kein Warndreieck
    out: dict[str, dict] = {}
    for f in felder:
        if (f.get("belegt") and f.get("typ") == "basis"
                and f.get("feld") == _PV_AGGREGAT_FELD_MONAT):
            out[f["id"]] = {
                "art": "nur_monat", "schwere": "warning", "grund": "pv_aggregat_tagesebene",
                "wirksame_felder": [k["id"] for k in mit_leistung],
                "text": "Deckt die Monatswerte — Tages- und Stundenwerte entstehen "
                        "nur aus einem Zähler je Erzeuger. Für die Leistungs-Sensoren "
                        "deiner Erzeuger baut Home Assistant unter Helfer → "
                        "„Integral-Sensor“ (Riemannsche Summe) einen kWh-Zähler; "
                        "diesen dann beim jeweiligen Erzeuger zuordnen.",
            }
    return out


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
    Erwartet die Felder ALLER aktiven Investitionen — auch die unbelegten: die
    kWh-Bedingung („keine Lücke mehr") ist sonst nicht entscheidbar.
    Returns {aggregat_field_id: {"art":"redundant","schwere":"warning","grund","wirksame_felder":[…],"text"}}.
    """
    # Live: ein einziges belegtes `leistung_w` genügt (Engine-Vorrang).
    pv_komp_live = [
        f for f in felder
        if f.get("belegt") and f.get("typ") in _PV_KOMPONENTEN_TYPEN
        and f.get("feld") == _PV_KOMPONENTEN_FELD_LIVE
    ]
    # Monat: erst wenn JEDE aktive PV-Quelle ihren eigenen kWh-Wert hat, ist
    # das Aggregat wirkungslos (sonst füllt es Lücken). `felder` enthält nur
    # im Moment aktive Investitionen (`datenquellen.py` filtert per
    # `aktiv_am_tag`), der Lifecycle-Filter ist damit schon gezogen.
    pv_komp_monat = [
        f for f in felder
        if f.get("typ") in _PV_KOMPONENTEN_TYPEN
        and f.get("feld") == _PV_KOMPONENTEN_FELD_MONAT
    ]
    pv_komp_monat_belegt = [f for f in pv_komp_monat if f.get("belegt")]
    pv_monat_vollstaendig = (
        bool(pv_komp_monat_belegt)
        and len(pv_komp_monat_belegt) == len(pv_komp_monat)
    )
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
        if feld == _PV_AGGREGAT_FELD_LIVE and f.get("typ") == "basis" and pv_komp_live:
            out[f["id"]] = {
                "art": "redundant", "schwere": "warning", "grund": "pv_aggregat",
                "wirksame_felder": [k["id"] for k in pv_komp_live],
                "text": "Wirkungslos: einzelne PV-Leistung ist zugeordnet — die "
                        "gesamt-Zuordnung wird ignoriert. Auf „keine“ setzen.",
            }
        elif (feld == _PV_AGGREGAT_FELD_MONAT and f.get("typ") == "basis"
                and pv_monat_vollstaendig):
            out[f["id"]] = {
                "art": "redundant", "schwere": "warning", "grund": "pv_aggregat",
                "wirksame_felder": [k["id"] for k in pv_komp_monat_belegt],
                "text": "Wirkungslos: jede PV-Quelle hat eine eigene Erzeugungs-"
                        "Zuordnung — die gesamt-Zuordnung wird ignoriert. "
                        "Auf „keine“ setzen.",
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


# ─── Takt-Check (#343 Baustein B, D2 2026-07-18) ────────────────────────────
# Heuristik über ~48 h REST-History (funktioniert Supervisor UND Remote-LL-Token;
# die evcc-Fehlerklasse hatte Einheit UND state_class KORREKT — nur der Update-
# Takt war unbrauchbar: Wertsprung erst am Lade-Session-Ende → Nadel im Live-Tag).
_TAKT_MIN_AENDERUNGEN = 12   # unter ~1 Zuwachs je 4 h gilt als sprunghaft
_TAKT_SPRUNG_ANTEIL = 0.5    # EIN Einzelsprung trägt ≥ 50 % des Gesamt-Zuwachses


def takt_problem(werte: list[float]) -> Optional[dict]:
    """Sprunghafter kWh-Zähler (#343). `werte` = numerische History-States
    (zeitlich sortiert, ~48 h). None bei zu dünner Datenlage oder ohne Zuwachs —
    „nicht prüfbar" bleibt still (Muster MQTT-Checker v3.23.8), nie Pseudo-Grün.
    """
    if len(werte) < 4:
        return None
    zuwaechse = [b - a for a, b in zip(werte, werte[1:]) if b > a]
    gesamt = sum(zuwaechse)
    if gesamt <= 0:
        return None
    sprunghaft = len(zuwaechse) < _TAKT_MIN_AENDERUNGEN or (max(zuwaechse) / gesamt) >= _TAKT_SPRUNG_ANTEIL
    if not sprunghaft:
        return None
    return {
        "art": "takt", "schwere": "warning",
        "text": "Dieser Zähler aktualisiert sich nur sprunghaft (z. B. am Ende "
                "einer Lade-Session) — Live- und Tageskurven zeigen dann Nadeln. "
                "Für Monatssummen ist er ok.",
    }


# ─── Bedarfs-Einstufung je Feld (§2i-6, 2026-07-28) ──────────────────────────
# Beantwortet die Frage, die der Rollup „n ohne Quelle" bisher nicht stellte:
# IST ein leeres Feld überhaupt eine Lücke? Drei Ausgänge:
#
#   "pflicht"  — leer und durch nichts abgedeckt → rot, Hinweis aufgeklappt.
#   "optional" — leer ist in Ordnung → leise, zählt nicht.
#   "inaktiv"  — hier gar nicht zu erfassen, weil ein anderer Weg gewinnt
#                (Alternativ-Gruppe belegt, oder Anlagen-Kontext verdrängt das
#                Feld) → leise, zählt nicht, mit Begründung.
#
# Gegenstück zu `finde_redundante_aggregate`: dort geht es um ein BELEGTES Feld,
# das ignoriert wird; hier um ein LEERES, das keins sein muss.

_VERDRAENGT_TEXT = {
    "keine_wallbox": "Die Wallbox ist die maßgebliche Quelle der Heimladung — "
                     "dort zuordnen, nicht hier.",
    "keine_pv_module": "Die PV-Module sind einzeln erfasst — dort zuordnen, "
                       "nicht hier.",
}
_VERDRAENGT_TYP = {"keine_wallbox": "wallbox", "keine_pv_module": "pv-module"}

# Sonderfall der Gruppe `pv_energie`, wenn sie AUSSCHLIESSLICH durch den
# Anlagen-Zählerstand belegt ist: „bereits an anderer Stelle zugeordnet" wäre
# dann nur für die Monatswerte wahr. Die Tages-/Stundenebene entsteht aus
# kumulativen Zählern **je Komponente** (`snapshot/keys.py`: das Aggregat hat
# kein Snapshot-Gegenstück) — der Satz führte den Anwender also von der einzigen
# Zuordnung weg, die ihm Tageswerte bringt (Forum kaba-kakao, T89667 #109).
_PV_AGGREGAT_NUR_MONAT_TEXT = (
    "Über den Anlagen-Zählerstand für die Monatswerte abgedeckt. Tages- und "
    "Stundenwerte entstehen nur aus einem eigenen Zähler je Komponente — "
    "hier zuordnen, wenn du sie brauchst."
)

_GRUPPEN_TEXT = {
    "pv_energie": "Die PV-Erzeugung ist bereits an anderer Stelle zugeordnet.",
    "pv_live": "Die PV-Leistung ist bereits an anderer Stelle zugeordnet.",
    "netz_live": "Netz-Leistung ist bereits zugeordnet (kombiniert oder getrennt).",
    "wp_strom": "Der WP-Stromverbrauch ist bereits zugeordnet.",
}


def stufe_bedarf_ein(
    felder: list[dict], vorhandene_typen: set[str],
) -> dict[str, dict]:
    """Bedarfs-Einstufung je Feld.

    `felder`: [{"id", "feld", "typ", "belegt", "bedarf", "bedarf_gruppe",
                "bedingung_anlage"}].
    `vorhandene_typen`: Investitionstypen der Anlage (für `bedingung_anlage`).

    Returns {field_id: {"bedarf": …, "grund": …|None, "text": …|None}}.
    """
    # Nicht nur WELCHE Gruppe belegt ist, sondern WOMIT: beim PV-Energie-Paar
    # deckt der Anlagen-Zählerstand nur den Monat ab (s. `_PV_AGGREGAT_NUR_MONAT_TEXT`).
    belegt_je_gruppe: dict[str, list[dict]] = {}
    for f in felder:
        gruppe_f = f.get("bedarf_gruppe")
        if f.get("belegt") and gruppe_f:
            belegt_je_gruppe.setdefault(gruppe_f, []).append(f)
    belegte_gruppen = set(belegt_je_gruppe)
    out: dict[str, dict] = {}
    for f in felder:
        fid = f["id"]
        belegt = bool(f.get("belegt"))
        bedingung_anlage = f.get("bedingung_anlage")

        # 1. Anlagen-Kontext verdrängt das Feld (Wallbox schlägt E-Auto-Heimladung,
        #    PV-Module schlagen den Wechselrichter-Sammelzähler). Ein BELEGTES Feld
        #    bleibt trotzdem sichtbar — sonst verschwände die Zuordnung unsichtbar
        #    und ließe sich nicht mehr entfernen; die Redundanz-Warnung greift dort.
        if bedingung_anlage and _VERDRAENGT_TYP.get(bedingung_anlage) in vorhandene_typen:
            out[fid] = {
                "bedarf": "inaktiv", "grund": bedingung_anlage,
                "text": _VERDRAENGT_TEXT.get(bedingung_anlage),
            }
            continue

        if belegt:
            out[fid] = {"bedarf": f.get("bedarf") or "optional", "grund": None, "text": None}
            continue

        # 2. Leer, aber ein anderes Mitglied der Alternativ-Gruppe trägt den Wert.
        gruppe = f.get("bedarf_gruppe")
        if gruppe and gruppe in belegte_gruppen:
            text = _GRUPPEN_TEXT.get(gruppe)
            # Trägt NUR das Anlagen-Aggregat die Gruppe, ist die Komponenten-
            # Zeile für den Monat abgedeckt und für Tag/Stunde eben nicht.
            # Umgekehrt (Komponenten belegt, Aggregat leer) bleibt der
            # allgemeine Satz richtig — deshalb die Herkunftsprüfung.
            if (gruppe == "pv_energie"
                    and f.get("feld") == _PV_KOMPONENTEN_FELD_MONAT
                    and all(b.get("typ") == "basis"
                            for b in belegt_je_gruppe.get(gruppe, ()))):
                text = _PV_AGGREGAT_NUR_MONAT_TEXT
            out[fid] = {
                "bedarf": "inaktiv", "grund": f"gruppe:{gruppe}",
                "text": text,
            }
            continue

        # 3. Echte Lücke — nur bei Pflicht.
        out[fid] = {"bedarf": f.get("bedarf") or "optional", "grund": None, "text": None}
    return out
