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

from backend.core.field_definitions import (
    BEDARF_GRUPPEN_ALTERNATIV,
    einheit_klasse,
    verdraengender_typ,
)

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
#   PV gesamt (kWh) — Monat UND (seit 2026-08-07) Tag/Stunde. Das Feld landet
#                     über `basis["pv_gesamt"]` in `Monatsdaten.pv_erzeugung_kwh`
#                     und ist damit der EINGANG von `resolve_pv_je_modul`: es
#                     füllt die Lücken der Module OHNE eigenen Wert. Auf der
#                     Tagesebene gilt eine ANDERE Regel — dort ist es
#                     alles-oder-nichts (`snapshot/komponenten_beitraege.
#                     basis_beitraege`), weil `komponenten_kwh` einen flachen
#                     Keyspace hat und die Anlagensumme nicht neben ihre eigenen
#                     Summanden gebucht werden darf. Wirkungslos ist das Feld
#                     erst, wenn es im Monat keine Lücke mehr gibt — sonst rät
#                     die Fläche, genau die Quelle abzuschalten, aus der die
#                     Anlagensumme kommt (Stufe 3 → QUELLE_FEHLT → 0 für die
#                     ganze Anlage).
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
PV_MODUL_TYP = "pv-module"
BKW_TYP = "balkonkraftwerk"
#: Die Größen, die ein Balkonkraftwerk an seine Kinder abtritt (N-266):
#: Erzeugung und Momentanleistung. Die Wechselrichter-Grenze tritt es NICHT ab.
_BKW_ABTRETBARE_FELDER = {"pv_erzeugung_kwh", "leistung_w"}
_NETZ_AGGREGAT_FELDER = {"netz_kombi_w"}
_NETZ_KOMPONENTEN_FELDER = {"einspeisung_w", "netzbezug_w"}


# ⛔ HIER STAND `finde_aggregat_teilweise_verdraengt` — mit #406 ERSATZLOS
# ENTFERNT (Entscheid Gernot 2026-09-04).
#
# Sie warnte: „Für Tag und Stunde zählt der Anlagen-Zählerstand nicht mehr mit,
# weil einzelne Erzeuger einen eigenen Zähler haben … Die Tagessumme ist damit
# zu niedrig." Das beschrieb den Zustand richtig — und war die Antwort, die am
# 2026-08-07 anstelle einer Reparatur gewählt wurde (Stufe 1 zu F-7, Journal:
# „Er macht es schlechter, indem er dem Rat folgt.").
#
# ⭐ Zwei Gründe, warum sie nicht reicht und deshalb geht:
# 1. **Sie hat den gemeldeten Fall nicht erreicht.** Mathek (#406) hat ALLEN
#    Strings einen Zähler zugeordnet — es gab keine Teilbelegung, die Warnung
#    schwieg, und der Tag verlor trotzdem 21 Stunden PV.
# 2. **Ihr Defekt existiert nicht mehr.** Seit der Präzedenz je Tag
#    (`core/berechnungen/pv_tages_praezedenz.py`) trägt das Aggregat die Bilanz
#    genau dann, wenn die Einzelzähler sie nicht vollständig tragen. Die
#    Tagessumme ist nicht mehr zu niedrig — eine Warnung wäre eine
#    Falschmeldung ([[feedback_user_fehlermeldungen]]: warnen nur, wo etwas
#    kaputt ist).
#
# Was ein eigener Zähler zusätzlich bringt, steht weiter an der Komponenten-
# Zeile (`_PV_AGGREGAT_NUR_ANLAGENSUMME_TEXT`) — informierend, nicht warnend.


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


#: **Bauschnitt 7** — die feinen Leistungsfelder einer Wärmepumpe. Sie erzeugen
#: die getrennten Verlaufs-Reihen (Heizen/Warmwasser/Kühlen) nur, solange am
#: selben Gerät **keine** Gesamtleistung zugeordnet ist.
#:
#: ⭐ **`leistung_kuehlen_w` gehört seit dem 13.09.2026 dazu** (N-439) — nicht
#: als Erweiterung der Regel, sondern weil es an diesem Tag überhaupt erst eine
#: Verlaufs-Reihe erzeugt. Vorher wurde es nirgends ausgewertet und konnte
#: deshalb auch von nichts verdrängt werden; jetzt gilt für es dieselbe
#: Bedingung wie für seine zwei Nachbarn (`baue_investitions_serien`:
#: `if not has_leistung`). Ein Hinweis an zwei von drei gleich behandelten
#: Feldern wäre genau die Lücke, gegen die SOLL §3.3/**S3** steht.
_WP_LEISTUNG_FEIN = (
    "leistung_heizen_w", "leistung_warmwasser_w", "leistung_kuehlen_w",
)
_WP_LEISTUNG_GESAMT = "leistung_w"

#: Was die Zuordnung bewirkt — die **Ursache**, nicht das Bild.
#:
#: ⛔ **Nicht „wirkungslos", und kein Rat.** Beide Zustände sind legitim: Die
#: Gesamtleistung ist der genauere Anlagenwert, die Aufteilung die feinere
#: Auskunft. Zwei Formulierungen sind an der Messung gescheitert (Gegenprüfung
#: 12.09.2026): „wirkungslos" ist falsch, weil Symbol und MQTT-Snapshots die
#: feinen Felder weiter lesen; und der Rat „Zuordnung entfernen" hätte auf einer
#: frischen HA-Anlage den Wärmepumpen-Anteil der Verbrauchsprognose gekostet
#: (`live_verbrauchsprofil_service.py`, HA-Pfad). Auch „als eine Fläche" wäre zu
#: viel behauptet: Bei einer zugeordneten, aber toten Entity erscheint die
#: Wärmepumpe im Verlauf **gar nicht**.
_GESAMTLEISTUNG_TEXT = (
    "Solange „Leistung gesamt“ zugeordnet ist, wertet eedc „Leistung Heizen“, "
    "„Leistung Warmwasser“ und „Leistung Kühlen“ im Verlauf nicht aus."
)


def finde_gesamtleistung_verdraengt(felder: list[dict]) -> dict[str, dict]:
    """Feine WP-Leistungsfelder, die von der Gesamtleistung **desselben Geräts**
    aus dem Verlauf gedrängt werden (**Bauschnitt 7**, Konzept Wärme/Klima §5).

    ``felder``: ``[{"id", "feld", "typ", "inv_id", "in_ha_live": bool}]``.

    ⭐ **Maßgeblich ist die HA-Zuordnungsliste, nicht „belegt" und nicht „liefert"
    — und das ist an zwei Fehlversuchen gelernt** (Gegenprüfung, zwei Runden):

    * ``_liefert`` (die Bedingung der Aggregat-Redundanz) wäre **zu eng**: Drei
      der vier Verdrängungsstellen lesen den **Eintrag** (`live.get("leistung_w")`),
      nicht den Wert. Eine zugeordnete, aber tote Entity verdrängt weiter — der
      Anwender bekäme keinen Hinweis, während die Aufteilung ausbleibt.
    * ``belegt`` wäre **zu weit**: Die B8-Materialisierung stempelt
      ``mqtt_inbound_standard`` auf **jedes** Feld ohne HA-Sensor, also auch auf
      diese; jede migrierte Anlage bekäme einen Hinweis, ohne etwas zugeordnet zu
      haben. Ein solcher Stempel erreicht die ``live``-Map nie
      (``datenquellen_mapping_sync._setze_live`` schreibt nur bei HA).

    Die ``live``-Map ist genau die Menge, die die Verdrängung **bewirkt** — eine
    Quelle, kein Nachbau. Der MQTT-Zweig (`live_tagesverlauf_service`) verdrängt
    wertgetrieben und bleibt bewusst außen vor; dort führt kein Weg zur
    Aufteilung, den ein Hinweis eröffnen könnte.

    ⚠ **Roher Feldschlüssel, kein ``basis_feld_key``.** Mit Innengeräte-Liste gibt
    es ``leistung_w-<gid>``; verdrängt wird nur vom **Gerätefeld**. Wer hier
    normalisiert, meldet an einer Multisplit-Anlage eine Verdrängung, die es nicht
    gibt (die übliche Bewegung im Baum ist die andere — deshalb der Hinweis).

    Returns ``{feld_id: {"art", "schwere", "grund", "wirksame_felder", "text"}}``.
    """
    gesamt_je_inv: dict[str, str] = {}
    for f in felder:
        if (f.get("typ") == "waermepumpe" and f.get("feld") == _WP_LEISTUNG_GESAMT
                and f.get("in_ha_live")):
            gesamt_je_inv[str(f.get("inv_id"))] = f["id"]

    out: dict[str, dict] = {}
    for f in felder:
        if f.get("typ") != "waermepumpe" or f.get("feld") not in _WP_LEISTUNG_FEIN:
            continue
        if not f.get("in_ha_live"):
            continue
        gesamt_fid = gesamt_je_inv.get(str(f.get("inv_id")))
        if not gesamt_fid:
            continue
        out[f["id"]] = {
            # ⛔ **Nicht `redundant`.** Für diese Art rendert die Fläche inline
            # „auf keine setzen", und der Knopf leert **das Feld der Zeile** —
            # er würde also die Aufteilung löschen statt der Gesamtleistung.
            "art": "gesamtleistung_verdraengt",
            # `info`: Es liegt kein Fehler vor. `warning` (amber) steht auf
            # dieser Fläche für Zuordnungs-PROBLEME.
            "schwere": "info",
            "grund": "gesamtleistung",
            "wirksame_felder": [gesamt_fid],
            "text": _GESAMTLEISTUNG_TEXT,
        }
    return out


def _liefert(feld: dict) -> bool:
    """Belegt UND es kommt etwas an — die Bedingung fürs Verdrängen.

    ⚠ **Ist Home Assistant nicht erreichbar**, hat kein HA-Feld einen Wert, und
    die Verdrängungs-Hinweise verstummen sämtlich. Das ist gewollt und
    dasselbe Muster wie eine Zeile darüber in der Route (*„Nicht erreichbar →
    leeres Dict, keine Validierungs-Fehlalarme"*): Ohne Messwerte lässt sich
    nicht sagen, was wen verdrängt — „nicht prüfbar" bleibt still, nie
    Pseudo-Grün und nie eine geratene Warnung.

    ⚠ Fehlt `hat_wert` im Eintrag (älterer Aufrufer), gilt die alte, schwächere
    Bedingung. Ein `.get("hat_wert", True)` wäre hier die stillere Variante
    gewesen; sie ist bewusst gewählt, damit ein nicht umgestellter Aufrufer
    nicht schlagartig ALLE Verdrängungs-Hinweise verliert — das wäre die
    Gegenrichtung desselben Fehlers.
    """
    return bool(feld.get("belegt")) and bool(feld.get("hat_wert", True))


def finde_redundante_aggregate(felder: list[dict]) -> dict[str, dict]:
    """Belegte Aggregat-Felder, die durch belegte Komponenten wirkungslos sind (C).

    `felder`: [{"id", "feld", "typ", "belegt": bool, "hat_wert": bool}].
    `belegt` = Quelle ≠ keine · `hat_wert` = dort kommt tatsächlich etwas an.

    ⭐ **Verdrängen kann nur, was liefert** (rapahl PN 91806, 2026-08-30).
    Bis dahin genügte hier der EINTRAG. Das traf einen realen Fall: Die
    B8-Materialisierung stempelt `mqtt_inbound_standard` auf jedes Feld ohne
    HA-Sensor und ohne Gateway-Zeile — bei ihm auf *Einspeisung (W)* und
    *Netzbezug (W)*, wo nie eine Nachricht ankam. Beide galten als „belegt" und
    erklärten damit seinen bidirektionalen Netzsensor für wirkungslos, der als
    einziger einen Wert lieferte. Die Live-Engine sah das anders und benutzte
    ihn — sie verwirft wertlose Felder
    (`live_power_service._apply_quellen_overrides`). Zwei Definitionen von
    „belegt" auf derselben Fläche; die Meldung hatte die schwächere.
    Erwartet die Felder ALLER aktiven Investitionen — auch die unbelegten: die
    kWh-Bedingung („keine Lücke mehr") ist sonst nicht entscheidbar.
    Returns {aggregat_field_id: {"art":"redundant","schwere":"warning","grund","wirksame_felder":[…],"text"}}.
    """
    # Live: ein einziges belegtes `leistung_w` genügt (Engine-Vorrang).
    pv_komp_live = [
        f for f in felder
        if _liefert(f) and f.get("typ") in _PV_KOMPONENTEN_TYPEN
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
    pv_komp_monat_belegt = [f for f in pv_komp_monat if _liefert(f)]
    pv_monat_vollstaendig = (
        bool(pv_komp_monat_belegt)
        and len(pv_komp_monat_belegt) == len(pv_komp_monat)
    )
    netz_split = [
        f for f in felder
        if _liefert(f) and f.get("typ") == "basis"
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


#: Einheiten, deren Werte NICHT summiert werden. Ein Preis, der an zwei Stellen
#: gelesen wird, wird nicht doppelt gezählt — er gilt zweimal.
_NICHT_ADDITIVE_EINHEITEN = {"ct/kwh", "€/kwh", "eur/kwh", "€", "eur", "%", "°c", "ct"}



#: Text der BKW-Abtretung auf der Zuordnungs-Fläche (N-537). Er sagt die
#: WIRKUNG, nicht eine Aufforderung — anders als `redundant`, dessen Knopf
#: („auf keine setzen") hier falscher Rat wäre: misst nur eines von zwei
#: Modulen selbst, ist der Wert des Balkonkraftwerks die einzige Quelle für das
#: andere, und ihn zu entfernen halbierte die Erzeugung.
_BKW_FUELLT_LUECKEN_TEXT = (
    "Die zugeordneten PV-Module tragen die Erzeugung dieses Balkonkraftwerks. "
    "Dieser Wert füllt nur noch, was ihnen fehlt — messen alle Module selbst, "
    "wird er nicht mehr gelesen."
)


def finde_bkw_fuellt_kinder_luecken(
    felder: list[dict],
    kind_zu_parent: dict,
) -> dict[str, dict]:
    """BKW-Felder, deren `pv-module`-Kinder die Erzeugung tragen (N-266/N-536).

    ``felder``: ``[{"id", "feld", "typ", "inv_id", "belegt"}]``;
    ``kind_zu_parent``: ``{str(kind_id): str(bkw_id)}`` für jedes `pv-module`
    mit Balkonkraftwerk-Parent.

    **Warum `info` und kein Knopf.** Dieselbe Bauform wie
    ``finde_gesamtleistung_verdraengt``: Es liegt kein Fehler vor, sondern eine
    Folge der Zuordnung. Die Alternative ``redundant`` („Wirkungslos … auf
    keine setzen") wäre hier ein **falscher Rat** — gemessen an der
    Teil-Deckung: Misst nur eines von zwei Modulen, trägt das Balkonkraftwerk
    die Lücke des anderen; ohne seine Zuordnung sänke die Erzeugung von 52 auf
    28 Wh, also unter den Fehler, den der Hinweis beheben sollte.

    Gemeldet wird nur, wenn mindestens ein Kind **selbst** eine Quelle hat —
    sonst gibt es nichts abzutreten und das Gerät ist die einzige Quelle.
    """
    if not felder or not kind_zu_parent:
        return {}
    belegte_kinder_je_bkw: dict[str, set[str]] = {}
    for f in felder:
        if f.get("typ") != PV_MODUL_TYP or not f.get("belegt"):
            continue
        parent = kind_zu_parent.get(str(f.get("inv_id")))
        if parent is not None:
            belegte_kinder_je_bkw.setdefault(parent, set()).add(str(f.get("inv_id")))

    out: dict[str, dict] = {}
    for f in felder:
        if f.get("typ") != BKW_TYP or f.get("feld") not in _BKW_ABTRETBARE_FELDER:
            continue
        if not f.get("belegt"):
            continue
        kinder = belegte_kinder_je_bkw.get(str(f.get("inv_id")))
        if not kinder:
            continue
        out[f["id"]] = {
            "art": "bkw_fuellt_luecken",
            "schwere": "info",
            "grund": "bkw_abtretung",
            "wirksame_felder": sorted(
                k["id"] for k in felder
                if str(k.get("inv_id")) in kinder and k.get("feld") == f.get("feld")
            ),
            "text": _BKW_FUELLT_LUECKEN_TEXT,
        }
    return out

def finde_doppelmappings(
    ha_zuordnungen: dict[str, str],
    feld_einheit: Optional[dict[str, str]] = None,
) -> dict[str, dict]:
    """Dieselbe HA-Entity in ≥2 MENGEN-Feldern → Doppelzählung (#314).

    `ha_zuordnungen`: {field_id: entity_id} nur der HA-zugeordneten Felder.
    `feld_einheit`: {field_id: Einheit} — ohne sie gilt das alte Verhalten.

    ⭐ **Preise werden nicht doppelt gezählt** (rapahl, PN 91806, 2026-08-30).
    Bei ihm hängt derselbe Sensor am *Strompreis (dynamischer Tarif)* und am
    *Ø Ladepreis* des Speichers — beides richtig und beides wirksam: Sein
    Octopus-Heat-Tarif hat drei Tagespreise, der Monatsabschluss bildet daraus
    korrekt Ø 28,67 ct/kWh. Trotzdem stand an beiden Feldern „→ Doppelzählung.
    Nur einem Feld zuordnen" — ein Rat, der eine korrekte Zuordnung entfernt
    hätte.

    ⚠ **Der Hinweis bleibt für Mengen** (kWh, km, Stück): Dort ist er richtig,
    dort war er auch gemeint (#314). Die Trennlinie ist die Einheit, nicht das
    Feld — additiv oder nicht.
    """
    per_eid: dict[str, list[str]] = defaultdict(list)
    for fid, eid in ha_zuordnungen.items():
        if eid:
            per_eid[eid].append(fid)
    einheiten = feld_einheit or {}

    def _additiv(fid: str) -> bool:
        return (einheiten.get(fid) or "").strip().lower() not in _NICHT_ADDITIVE_EINHEITEN

    out: dict[str, dict] = {}
    for eid, fids in per_eid.items():
        # Nur Felder, deren Werte überhaupt summiert werden, können doppelt
        # zählen. Bleiben davon weniger als zwei, gibt es nichts zu melden.
        additive = [f for f in fids if _additiv(f)]
        if len(additive) >= 2:
            for fid in additive:
                out[fid] = {
                    "art": "doppelmapping", "schwere": "warning", "entity_id": eid,
                    "andere_felder": [x for x in additive if x != fid],
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
# N-79: die Zuordnung Wert → verdrängender Typ ist KEIN lokales Wissen mehr.
# Sie stand hier wertgleich neben einer `if`-Kette in `field_definitions.py`;
# ein dritter Wert nur an einer der beiden Stellen hätte still verschieden
# gewirkt. SoT ist `BEDINGUNG_ANLAGE_VERDRAENGT`, gelesen über
# `verdraengender_typ` (unbekannter Wert ⇒ None ⇒ verdrängt nicht).
# ⚠ `_VERDRAENGT_TEXT` darüber bleibt hier: das ist der Anwendertext DIESER
#   Fläche, keine Semantik. Dass beide dasselbe Vokabular führen, hält der
#   Wächter in `test_bedingung_anlage_sot_n79.py` — er prüft beide Seiten.

# Sonderfall der Gruppe `pv_energie`, wenn sie AUSSCHLIESSLICH durch den
# Anlagen-Zählerstand belegt ist: „bereits an anderer Stelle zugeordnet" sagt
# nicht, was ein eigener Zähler noch bringen würde — und seit Stufe 1 zu F-7
# auch nicht, was er kostet.
#
# ⚠ **Text am 2026-08-07 zum zweiten Mal überarbeitet.** Die F-7-Fassung sagte
# „Tages- und Stundenwerte entstehen nur aus einem eigenen Zähler je
# Komponente"; das stimmte, solange das Aggregat die Tagesebene nicht erreichte.
# Mit Stufe 1 erreicht es sie — die Anlagensumme steht in Tag und Stunde. Was
# ein eigener Zähler noch hinzufügt, ist die **Aufschlüsselung** je Erzeuger.
#
# Und er kostet etwas, deshalb steht die Bedingung im Satz: die Regel ist
# alles-oder-nichts (`komponenten_beitraege.basis_beitraege`). Wer EINEM von
# mehreren Erzeugern einen Zähler zuordnet, schaltet die Anlagensumme für Tag
# und Stunde ab und sieht danach weniger als vorher. Ein Hinweis, der dazu rät
# und das verschweigt, führt in genau diese Falle.
# ⛔ Der letzte Satz lautete bis #406: „Dann brauchen ihn aber alle Erzeuger:
# sobald einer gemessen wird, zählt für Tag und Stunde nur noch, was je Erzeuger
# gemessen ist." Das war der **Preis** der alten Alles-oder-nichts-Regel — und
# damit eine Anleitung in die Falle, in die Mathek gelaufen ist. Der Preis
# existiert nicht mehr; geblieben ist der Gewinn.
_PV_AGGREGAT_NUR_ANLAGENSUMME_TEXT = (
    "Über den Anlagen-Zählerstand abgedeckt — als Summe der ganzen Anlage, "
    "auch für Tag und Stunde. Ein eigener Zähler hier schlüsselt zusätzlich "
    "je Erzeuger auf und macht den Anteil dieses Erzeugers zu einem gemessenen "
    "Wert. Ohne ihn wird der Tagesanteil nach kWp aus der Anlagensumme "
    "abgeleitet; die Anlagensumme selbst stimmt in beiden Fällen."
)

# ⭐ Diese Texte sagen seit 2026-08-30, was sie BEDEUTEN — nicht nur, was der
# Fall ist (rapahl, PN 91806). Vorher stand hier ein reiner Zustandssatz an
# einer Stelle, an der rechts ein Schalter sitzt; er hat sich die Handlung
# dazugedacht („hier stand immer: bitte keine auswählen") und geklickt. Sein
# eigener Vorschlag war der bessere: sagen, dass nichts zu tun ist.
_GRUPPEN_TEXT = {
    "pv_energie": "Die PV-Erzeugung ist bereits an anderer Stelle zugeordnet — "
                  "hier ist nichts einzutragen.",
    "pv_live": "Die PV-Leistung ist bereits an anderer Stelle zugeordnet — "
               "hier ist nichts einzutragen.",
    "netz_live": "Netz-Leistung ist bereits zugeordnet (kombiniert oder "
                 "getrennt) — hier ist nichts einzutragen.",
    # N-391: *Heizwärme* und *Wärme gesamt* sind zwei Wege zu derselben Größe —
    # ein gemeinsamer Wärmemengenzähler oder getrennte. Wer einen davon
    # zugeordnet hat, braucht den anderen nicht.
    "wp_waerme": "Die abgegebene Wärme ist bereits zugeordnet — hier ist "
                 "nichts einzutragen.",
}

# ⛔ **`wp_strom` stand bis zum 14.09.2026 in der Tabelle darüber**, mit dem
# Satz *„Der WP-Stromverbrauch ist bereits zugeordnet — hier ist nichts
# einzutragen."* Er ist mit WK-16d falsch geworden: Seit ein Gesamtzähler die
# Menge ist (K1), trägt er **mehr** als die beiden Achsen — Standby, Steuerung,
# Umwälzpumpen —, und wer ihn wegen dieses Satzes nicht zuordnet, verliert
# genau diese Kilowattstunden. Der Ersatz sagt, was er **bringt**, statt was
# angeblich nichts zu tun ist (dieselbe Lehre wie bei rapahl, PN 91806).
#
# ⚠ **Und die Einstufung ändert sich mit**: „inaktiv" heißt auf dieser Fläche
# *hier gehört nichts hin*; das Feld ist aber **optional nützlich**. Beides
# folgt jetzt aus einer Eigenschaft der Gruppe statt aus einem Sonderfall —
# s. {@link stufe_bedarf_ein}, Schritt 2.
_SUMMANDEN_ZUSATZ_TEXT: dict[tuple[str, str], str] = {
    ("waermepumpe", "stromverbrauch_kwh"): (
        "Optional — misst dieser Zähler mehr als Strom Heizen und Strom "
        "Warmwasser zusammen (Standby, Steuerung, Umwälzpumpen), gilt sein "
        "Wert als Verbrauch des Geräts und die Differenz erscheint als "
        "„nicht aufgeteilt“."
    ),
}


def _deckt_ab(belegtes: dict, leeres: dict) -> bool:
    """Deckt dieses **belegte** Feld das **leere** seiner Gruppe ab? (N-456)

    ⛔ **Nein, sobald beide an VERSCHIEDENEN Geräten hängen.** Bis zum
    13.09.2026 war die Belegung nur nach `bedarf_gruppe` geschlüsselt — an einer
    Anlage mit zwei Wärmepumpen schaltete ein zugeordnetes Feld an Gerät A die
    leeren Felder an Gerät B auf *„hier ist nichts einzutragen"*. Das Feld des
    zweiten Geräts konnte damit gar nicht als offen erscheinen.

    ⭐ **Die Anlagen-Ebene deckt weiterhin in BEIDE Richtungen ab, und das ist
    kein Widerspruch:** Der Anlagen-Zählerstand (`typ: basis`, ohne Gerät) und
    ein Komponentenzähler messen dieselbe Größe an verschiedenen Stellen — dort
    ist die Gruppe eine echte Alternative (`pv_energie`, `pv_live`,
    `netz_live`). Zwei Geräte sind es nie.
    """
    a, b = belegtes.get("inv_id"), leeres.get("inv_id")
    return not (a and b and a != b)


def stufe_bedarf_ein(
    felder: list[dict], vorhandene_typen: set[str],
) -> dict[str, dict]:
    """Bedarfs-Einstufung je Feld.

    `felder`: [{"id", "feld", "typ", "belegt", "bedarf", "bedarf_gruppe",
                "bedingung_anlage", "inv_id", "pflicht_am_geraet"}].
    `vorhandene_typen`: Investitionstypen der Anlage (für `bedingung_anlage`).

    ``inv_id`` und ``pflicht_am_geraet`` sind **optional** — ohne sie verhält
    sich die Funktion wie vor N-456 (alles anlagenweit, jede Gruppe eine
    Alternative). Die Route füllt beide; die Vorgabe hält die vorhandenen
    Proben unverändert gültig.

    Returns {field_id: {"bedarf": …, "grund": …|None, "text": …|None}}.
    """
    # Nicht nur WELCHE Gruppe belegt ist, sondern WOMIT: beim PV-Energie-Paar
    # deckt der Anlagen-Zählerstand nur den Monat ab (s. `_PV_AGGREGAT_NUR_ANLAGENSUMME_TEXT`).
    belegt_je_gruppe: dict[str, list[dict]] = {}
    for f in felder:
        gruppe_f = f.get("bedarf_gruppe")
        if f.get("belegt") and gruppe_f:
            belegt_je_gruppe.setdefault(gruppe_f, []).append(f)
    out: dict[str, dict] = {}
    for f in felder:
        fid = f["id"]
        belegt = bool(f.get("belegt"))
        bedingung_anlage = f.get("bedingung_anlage")

        # 1. Anlagen-Kontext verdrängt das Feld (Wallbox schlägt E-Auto-Heimladung,
        #    PV-Module schlagen den Wechselrichter-Sammelzähler). Ein BELEGTES Feld
        #    bleibt trotzdem sichtbar — sonst verschwände die Zuordnung unsichtbar
        #    und ließe sich nicht mehr entfernen; die Redundanz-Warnung greift dort.
        if bedingung_anlage and verdraengender_typ(bedingung_anlage) in vorhandene_typen:
            out[fid] = {
                "bedarf": "inaktiv", "grund": bedingung_anlage,
                "text": _VERDRAENGT_TEXT.get(bedingung_anlage),
            }
            continue

        if belegt:
            out[fid] = {"bedarf": f.get("bedarf") or "optional", "grund": None, "text": None}
            continue

        # 2. Leer, aber ein anderes Mitglied der Alternativ-Gruppe trägt den Wert.
        #
        # ⛔ **Zwei Einschränkungen seit N-456 (13.09.2026), beide aus der
        # Registry, keine für `wp_strom` erfundene Sonderregel:**
        #
        # (a) Deckung nur innerhalb desselben Geräts oder gegen die
        #     Anlagen-Ebene (`_deckt_ab`) — an zwei Wärmepumpen schaltete
        #     bisher ein belegtes Feld an Gerät A das leere an Gerät B still ab.
        #
        # (b) **Ein Feld, das an DIESEM Gerät Pflicht ist, wird nie verdrängt.**
        #     Sind an einem Gerät zwei Felder derselben Gruppe gleichzeitig
        #     Pflicht, sind sie **Summanden** und keine Alternativen — bei
        #     getrennter Strommessung tragen `strom_heizen_kwh` und
        #     `strom_warmwasser_kwh` zusammen den Verbrauch, jedes einzeln nur
        #     die Hälfte. Wäre eines von beiden eine Alternative, hätte die
        #     Registry es als `erweitert` oder `nicht_an_dieser_bauart`
        #     gekennzeichnet und `pflicht_felder_am_geraet` ließe es weg — genau
        #     das passiert mit `stromverbrauch_kwh`, sobald F5 an ist.
        #
        # ⭐ **Dieselbe Wahrheit, zwei Leser:** `pflicht_am_geraet` kommt aus
        # `pflicht_felder_am_geraet(typ, parameter, gruppe)`, dem Helfer, den
        # `_check_energieprofil_abdeckung` schon liest. Vorher sagten die zwei
        # Flächen über dasselbe Feld Gegenteiliges (N-86-Klasse): „hier ist
        # nichts einzutragen" gegen „ohne vollständige Zähler-Abdeckung".
        gruppe = f.get("bedarf_gruppe")
        deckende = [b for b in belegt_je_gruppe.get(gruppe or "", ())
                    if _deckt_ab(b, f)]
        if gruppe and deckende and not f.get("pflicht_am_geraet"):
            # ⛔ **(c) seit WK-16d: nur eine ALTERNATIV-Gruppe deckt ab.**
            # `BEDARF_GRUPPEN_ALTERNATIV` trägt die Unterscheidung bereits
            # (N-391) — Alternativen sind Wege zu EINER Größe, Summanden sind
            # Teile einer Größe. Ein Summand kann seine Geschwister deshalb
            # niemals decken, auch dann nicht, wenn er an diesem Gerät keine
            # Pflicht ist: `stromverbrauch_kwh` ist bei getrennter Messung
            # „erweitert" (weiche Bedingung) und fiel damit bis dahin in diesen
            # Zweig — mit dem Satz „ist bereits zugeordnet, hier ist nichts
            # einzutragen". Seit ein Gesamtzähler die Menge ist (K1), ist dieser
            # Satz ein Rat, der Kilowattstunden kostet.
            #
            # ⚠ **`pflicht_am_geraet` bleibt daneben stehen und bleibt nötig:**
            # Es beantwortet die Frage für die Felder, die an DIESEM Gerät
            # Pflicht sind (N-456, zwei Wärmepumpen, F5-Achsen). Die neue
            # Klausel beantwortet sie für die Gruppe als Ganzes. Zwei Fragen,
            # zwei Bedingungen.
            if gruppe not in BEDARF_GRUPPEN_ALTERNATIV:
                out[fid] = {
                    "bedarf": f.get("bedarf") or "optional",
                    "grund": None,
                    "text": _SUMMANDEN_ZUSATZ_TEXT.get(
                        (f.get("typ") or "", f.get("feld") or "")
                    ),
                }
                continue
            text = _GRUPPEN_TEXT.get(gruppe)
            # Trägt NUR das Anlagen-Aggregat die Gruppe, ist die Komponenten-
            # Zeile für den Monat abgedeckt und für Tag/Stunde eben nicht.
            # Umgekehrt (Komponenten belegt, Aggregat leer) bleibt der
            # allgemeine Satz richtig — deshalb die Herkunftsprüfung.
            if (gruppe == "pv_energie"
                    and f.get("feld") == _PV_KOMPONENTEN_FELD_MONAT
                    and all(b.get("typ") == "basis" for b in deckende)):
                text = _PV_AGGREGAT_NUR_ANLAGENSUMME_TEXT
            out[fid] = {
                "bedarf": "inaktiv", "grund": f"gruppe:{gruppe}",
                "text": text,
            }
            continue

        # 3. Echte Lücke — nur bei Pflicht.
        out[fid] = {"bedarf": f.get("bedarf") or "optional", "grund": None, "text": None}
    return out
