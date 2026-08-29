"""
Kanonische Felddefinitionen für Monatsdaten-Eingabe und Import.

Single Source of Truth für alle Eingabe- und Import-Kanäle:
- MonatsabschlussWizard (liest via API)
- MonatsdatenForm (Frontend, direkte Eingabe)
- CSV-Import/Export (personalisiertes Template)
- Custom-Import-Wizard (Spalten-Mapping)
- Portal-Import / Cloud-Import

Kanonische Feldnamen = Backend-Namen (der Wizard war bereits korrekt).
Alle anderen Kanäle wurden auf diese Namen ausgerichtet.

Namens-History:
  speicher_ladung_netz_kwh → ladung_netz_kwh   (Speicher Arbitrage-Netzladung)
  entladung_v2h_kwh        → v2h_entladung_kwh  (E-Auto V2H)

Feld-Attribute:
  feld          — kanonischer Backend-Feldname in verbrauch_daten
  label         — Anzeigename (Wizard, Dropdown)
  einheit       — Einheit für Anzeige (kWh, km, €, ct/kWh, "")
  bedingung     — optionale Bedingung (Parameter-Key), z.B. "arbitrage_faehig"
  weich         — Tupel der Bedingungs-Schlüssel, deren Nicht-Erfüllung das Feld
                  NICHT entfernt, sondern als **erweitert** markiert (R1, SOLL
                  Wärme/Klima §3.2a). Siehe `bedingungs_urteil`.
  label_wenn    — optionales konditionelles Label: {Bedingungs-Key: Alt-Label}.
                  Trifft eine Bedingung zu, ersetzt sie das Default-`label`
                  (#281 — z.B. "Ladung" → "Ladung (gesamt, inkl. Netz)").
  csv_suffix    — Spalten-Suffix in der personalisierten CSV, z.B. "Ladung_kWh"
                  Konvention: {SanitizedBezeichnung}_{csv_suffix}
  csv_suffix_alt— alternativer (Legacy-)Suffix für Rückwärtskompatibilität
  aggregiert_in — Summen-Key für Monatsdaten-Aggregat:
                  "pv_sum", "batterie_ladung_sum", "batterie_entladung_sum"
  typ           — Datentyp für Import-Parsing: "float" (default) | "int"
  placeholder   — optionaler Platzhalter für Eingabefeld
  hinweis       — kurze Feld-Erklärung (welcher Wert/Sensortyp erwartet wird).
                  Universelle Single Source of Truth für Hilfetexte: gerendert im
                  Sensor-Zuordnungs-Wizard, im MQTT-Inbound-Wizard und in der
                  manuellen Monatsdaten-Eingabe. Sensor-Felder konsistent zu
                  docs/SENSOR-REFERENZ.md halten.
  nur_bestand   — True: das Feld ist **gar nicht mehr pflegbar** und faellt aus
                  `get_felder_fuer_investition` (Monatsabschluss). Es bleibt nur
                  in der Registry, damit eine BESTEHENDE Zuordnung sichtbar und
                  entfernbar ist — dafuer traegt es zusaetzlich `nur_manuell`,
                  das `routes/datenquellen.py::ohne_nicht_zuordenbare` auswertet
                  (Feld weg, ausser es traegt heute eine Quelle). Unterschied zu
                  `nur_manuell` allein: dort ist das Feld weiterhin ERFASSBAR,
                  nur nicht mehr zuordenbar. Erster Fall:
                  `wechselrichter/pv_erzeugung_kwh` (Gernot 24.08.2026 — der
                  Wechselrichter ist kein PV-Erzeuger, Begruendung dort).
  nur_manuell   — True: das Feld bleibt in Monatsabschluss, CSV-Import und
                  Export **erfassbar**, verschwindet aber als **zuordenbare
                  Quelle**. Markiert statt gefiltert: `build_expected_topics`
                  reicht die Kennung durch (die Registry ist die SoT „welche
                  Felder gibt es"), ausgewertet wird sie an den Rändern —
                  `routes/datenquellen.py::ohne_nicht_zuordenbare` nimmt das Feld
                  von der Fläche (außer es trägt heute eine Quelle, sonst ließe
                  sich die Zuordnung nicht mehr entfernen), der MQTT-Inbound
                  weist es ab und die Abdeckungs-Prüfung erwartet kein Topic
                  dafür. Der Rückbau-Modus dieses Projekts: kein Löschen,
                  gepflegte Werte bleiben lesbar und pflegbar, nur der
                  automatische Erfassungsweg entfällt
                  ([[feedback_reparatur_statt_loesch_features]]).
"""

from typing import Final, Optional

from backend.core.investition_parameter import (
    ist_brauchwasser_waermepumpe,
    ist_luft_luft_waermepumpe,
    lade_innengeraete,
)


# =============================================================================
# Basis-Felder (Monatsdaten — Zählerwerte)
# =============================================================================

BASIS_FELDER = [
    {"feld": "einspeisung_kwh",        "label": "Einspeisung",     "einheit": "kWh",    "mapping_key": "einspeisung",    "gruppe": "zaehler",
     "hinweis": "Kumulativer kWh-Zähler (oder Tagessensor mit 0:00-Reset) der ins Netz eingespeisten Energie. Immer ≥ 0; bei Zweirichtungszähler nur den Einspeise-Anteil."},
    {"feld": "netzbezug_kwh",          "label": "Netzbezug",       "einheit": "kWh",    "mapping_key": "netzbezug",      "gruppe": "zaehler",
     "hinweis": "Kumulativer kWh-Zähler (oder Tagessensor mit 0:00-Reset) der aus dem Netz bezogenen Energie. Immer ≥ 0; bei Zweirichtungszähler nur den Bezugs-Anteil."},
    {"feld": "globalstrahlung_kwh_m2", "label": "Globalstrahlung", "einheit": "kWh/m²", "mapping_key": "globalstrahlung","gruppe": "wetter",
     "hinweis": "Globalstrahlung im Monat (kWh/m²). Wird automatisch von Open-Meteo geholt, wenn nicht manuell gepflegt."},
    {"feld": "sonnenstunden",          "label": "Sonnenstunden",   "einheit": "h",      "mapping_key": "sonnenstunden",  "gruppe": "wetter",
     "hinweis": "Sonnenstunden im Monat (h). Wird automatisch von Open-Meteo geholt."},
    {"feld": "durchschnittstemperatur","label": "Ø Temperatur",    "einheit": "°C",     "mapping_key": "temperatur",     "gruppe": "wetter",
     "hinweis": "Monatsdurchschnittstemperatur (°C). Wird automatisch von Open-Meteo geholt."},
]

# =============================================================================
# Bedingte Basis-Felder (Anlage-Ebene)
#
# Diese Felder sind Monatsdaten-Spalten (wie BASIS_FELDER), werden aber nur
# angezeigt wenn eine Anlage-Bedingung erfüllt ist.
#
# bedingung_basis:
#   "dynamischer_tarif"    — Anlage hat einen dynamischen Stromtarif ODER einen
#                            Zeittarif mit Fenstern (N-267). Beides stellt
#                            dieselbe Frage: „welcher EINE Preis beschreibt
#                            diesen Monat?" — deshalb dasselbe Feld und keine
#                            zweite Bedingung. Der Name ist historisch.
#   "variable_einspeisung" — der Tarif trägt „Einspeisevergütung wechselt
#                            monatlich" (#392) — bewusst eine EIGENE Bedingung,
#                            nicht `dynamischer_tarif`: gruaGits Fall ist fixer
#                            Bezug + variable Einspeisung
#   "hat_eauto"            — Anlage hat mindestens eine aktive E-Auto-Investition
#   "hat_waermepumpe"      — Anlage hat mindestens eine aktive Wärmepumpe
# =============================================================================

BEDINGTE_BASIS_FELDER = [
    {
        "feld": "netzbezug_durchschnittspreis_cent",
        "label": "Ø Strompreis",
        "einheit": "ct/kWh",
        "bedingung_basis": "dynamischer_tarif",
        "mapping_key": "strompreis",
        "gruppe": "preise",
        "hinweis": "Verbrauchsgewichteter Ø-Arbeitspreis des Monats (ct/kWh). Bei dynamischem Tarif sonst automatisch aus dem Strompreis-Sensor (Tibber/aWATTar/EPEX) berechnet; bei einem Zeittarif (HT/NT) aus deinen gemessenen Stundenwerten. Ohne Stundenwerte — etwa bei handgetragenen Monatswerten — rechnet eedc mit dem Preis aus den Stammdaten; dann ist dieses Feld der Weg zum tatsächlichen Ø.",
    },
    {
        "feld": "einspeise_durchschnittspreis_cent",
        "label": "Einspeisevergütung (Monat)",
        "einheit": "ct/kWh",
        "bedingung_basis": "variable_einspeisung",
        "gruppe": "preise",
        "hinweis": "Vergütungssatz dieses Monats (ct/kWh), z. B. der OeMAG-Marktpreis. Schlägt den Stammwert des Tarifs; ohne Eintrag rechnet der Monat mit dem Stammwert. eedc holt den Satz nicht automatisch ab.",
    },
    {
        "feld": "kraftstoffpreis_euro",
        "label": "Ø Benzinpreis",
        "einheit": "€/L",
        "bedingung_basis": "hat_eauto",
        "gruppe": "preise",
        "hinweis": "Ø Kraftstoffpreis des Monats (€/L) für den E-Auto-vs-Verbrenner-Vergleich. Wird sonst automatisch aus dem EU Weekly Oil Bulletin geholt.",
    },
    {
        "feld": "gaspreis_cent_kwh",
        "label": "Ø Gas-/Ölpreis",
        "einheit": "ct/kWh",
        "bedingung_basis": "hat_waermepumpe",
        "gruppe": "preise",
        "hinweis": "Ø Gas-/Ölpreis des Monats (ct/kWh) für den Wärmepumpe-vs-fossile-Heizung-Vergleich.",
    },
]

# =============================================================================
# Optionale Felder (manuelle Eingabe, keine HA-Quelle)
# =============================================================================

OPTIONALE_FELDER = [
    {"feld": "sonderkosten_euro",        "label": "Sonderkosten",  "einheit": "€",  "typ": "number",
     "hinweis": "Einmalige Sonderkosten des Monats (€), z. B. Wartung oder Reparatur. Optional."},
    {"feld": "sonderkosten_beschreibung","label": "Beschreibung",  "einheit": "",   "typ": "text",
     "hinweis": "Kurzbeschreibung der Sonderkosten (Freitext). Optional."},
    {"feld": "notizen",                  "label": "Notizen",       "einheit": "",   "typ": "text",
     "hinweis": "Freie Notizen zum Monat (Freitext). Optional."},
]

# =============================================================================
# Investitions-Felder nach Typ
#
# Bedingungsfelder werden über get_felder_fuer_investition() aufgelöst.
# "bedingung" ist ein informativer String für Dokumentation/Debugging.
#
# Import-Attribute (csv_suffix, aggregiert_in, typ) werden von
# _import_investition_monatsdaten_v09() und _build_investition_felder()
# automatisch ausgewertet — keine hardcodierten Typ-Checks mehr nötig.
# =============================================================================

# ── #263: die gemessenen Betriebsart-Felder einer Split-Klimaanlage ─────────
#
# **Erzeugt statt achtmal getippt.** Die Feldnamen selbst stehen ausgeschrieben
# im Kanon (`core/betriebsmodus.py`) — dort ist die Grep-Barkeit, die dieses
# Projekt braucht. Hier entsteht daraus nur die Registry-Zeile, damit Hinweis
# und Einheit nicht achtmal auseinanderdriften können (dieselbe Bauform wie
# `_sonstiges_felder_*`, N-259).
#
# **Warum `bedingung: luft_luft` — und warum sie seit dem 26.08.2026 WEICH ist.**
# Eine Betriebsart im Sinne von Heizen · Kühlen · Lüften · Entfeuchten hat
# typischerweise ein Klimagerät. Eine Luft-Wasser-WP hat Heizen und Warmwasser —
# dafür gibt es `strom_heizen_kwh`/`strom_warmwasser_kwh`, und die bedeuten
# etwas anderes (Summanden, nicht Teilmengen). Die zwei Familien unbeschriftet
# nebeneinander anzubieten wäre genau die Zweideutigkeit, an der ein Tester
# schon einmal zwei Felder addiert hat (Forum simon42 #89667/62).
#
# ⛔ **Das spricht gegen ACHT Felder in der ersten Reihe jeder Wärmepumpe —
# nicht gegen die Kühl-Achse dort, wo ein Zähler sie belegt** (Befund W-2,
# SOLL §3.2a/R1). MartyBr hat seit dem Sommer 2026 einen getrennten Kühlzähler
# an einer Wärmepumpe und konnte ihn nirgends hinterlegen; pipp086 fragt nach
# derselben Größe (T89667 #199/#200). `weich` löst beides: hart entfernt das
# Feld, weich stellt es hinter „Weitere Größen erfassen" (s.
# `bedingungs_urteil`).
_BETRIEBSART_HINWEIS_STROM = (
    "Elektrische Energie, die dieses Gerät im {label} verbraucht hat (kWh, "
    "kumulativer Zähler oder Tagessensor). **Teilmenge** des Gesamtverbrauchs — "
    "eedc addiert sie nie dazu. Liegt dieser Wert vor, hat er Vorrang vor der "
    "Aufteilung, die eedc sonst aus dem Betriebsmodus ableitet — und zwar "
    "für **alle** Betriebsarten dieses Monats: sobald hier ein Zähler steht, "
    "zählt für dieses Gerät nur noch Gemessenes. Eine Betriebsart ohne Zähler "
    "erscheint dann unter „nicht aufgeteilt“. "
    "In Home Assistant bekommt man ihn mit einem **Utility Meter** (Helfer) auf "
    "den Energie-Sensor des Geräts, mit einem Tarif je Betriebsart. "
    "⚠ An Multisplit-Geräten misst kein Innengerät seinen eigenen Anteil: Was "
    "dort als Verbrauch erscheint, ist der Anteil des Außengeräts, der dem "
    "gerade anfordernden Innengerät zugeschrieben wird."
)
_BETRIEBSART_HINWEIS_NUTZ = (
    "Abgegebene Nutzenergie im {label} (kWh, kumulativer Zähler oder "
    "Tagessensor) — thermisch, NICHT Strom. Beim Kühlen ist das die abgeführte "
    "Wärme. Optional; ohne Wärmemengenzähler gibt es diesen Wert nicht, und "
    "eedc rechnet ihn nicht herbei."
)


#: CSV-Spaltenteil je Betriebsart — **ohne Umlaute**, wie jede bestehende
#: CSV-Spalte dieses Projekts (`Strom_Heizen_kWh`, `Ladung_PV_kWh`). Ein „ü" im
#: Spaltennamen überlebt die Runde durch Tabellenkalkulation und
#: Zeichensatz-Wechsel nicht zuverlässig, und die Spalte ist der Schlüssel, an
#: dem der Import wiederfindet, wohin ein Wert gehört.
_BETRIEBSART_CSV: dict[str, str] = {
    "heizen": "Heizbetrieb",
    "kuehlen": "Kuehlbetrieb",
    "lueften": "Lueftbetrieb",
    "entfeuchten": "Entfeuchtung",
}


def _betriebsart_felder() -> list[dict]:
    from backend.core.betriebsmodus import (
        BETRIEBSART_LABEL,
        BETRIEBSART_NUTZENERGIE_FELD,
        BETRIEBSART_STROM_FELD,
        MESSBARE_MODI,
    )
    out: list[dict] = []
    for modus in MESSBARE_MODI:
        label = BETRIEBSART_LABEL[modus]
        out.append({
            "feld": BETRIEBSART_STROM_FELD[modus],
            "label": f"Strom {label}",
            "einheit": "kWh",
            "bedingung": "luft_luft",
            "weich": ("luft_luft",),
            "je_innengeraet": True,
            "csv_suffix": f"Strom_{_BETRIEBSART_CSV[modus]}_kWh",
            "hinweis": _BETRIEBSART_HINWEIS_STROM.format(label=label),
        })
    for modus in MESSBARE_MODI:
        label = BETRIEBSART_LABEL[modus]
        out.append({
            "feld": BETRIEBSART_NUTZENERGIE_FELD[modus],
            "label": f"Nutzenergie {label}",
            "einheit": "kWh",
            "bedingung": "luft_luft",
            "weich": ("luft_luft",),
            "je_innengeraet": True,
            "csv_suffix": f"Nutzenergie_{_BETRIEBSART_CSV[modus]}_kWh",
            "hinweis": _BETRIEBSART_HINWEIS_NUTZ.format(label=label),
        })
    return out


_BETRIEBSART_FELDER: list[dict] = _betriebsart_felder()

#: Die reinen Feldnamen — für die Ausnahmelisten weiter unten, die (typ, feld)
#: erwarten. Aus derselben Quelle wie die Registry-Zeilen, damit eine spätere
#: Betriebsart nicht in der einen Liste steht und in der anderen fehlt.
_BETRIEBSART_STROM_FELDNAMEN: tuple[str, ...] = tuple(
    f["feld"] for f in _BETRIEBSART_FELDER if f["feld"].startswith("betriebsart_strom_")
)
_BETRIEBSART_NUTZENERGIE_FELDNAMEN: tuple[str, ...] = tuple(
    f["feld"] for f in _BETRIEBSART_FELDER
    if f["feld"].startswith("betriebsart_nutzenergie_")
)


INVESTITION_FELDER: dict = {
    "pv-module": [
        {
            "feld": "pv_erzeugung_kwh", "label": "PV-Erzeugung", "einheit": "kWh",
            "csv_suffix": "kWh",
            "aggregiert_in": "pv_erzeugung_sum",
            "hinweis": "Kumulativer kWh-Zähler (oder Tagessensor) der erzeugten Energie dieses PV-Strings. Immer ≥ 0. Alternativ anteilig per kWp aus dem PV-Gesamt-Sensor verteilt.",
        },
    ],

    # ⛔ **Der Wechselrichter ist KEIN PV-Erzeuger** (Entscheid Gernot 24.08.2026).
    # Das Feld bleibt nur noch stehen, damit eine BESTEHENDE Zuordnung sichtbar
    # und entfernbar ist — `nur_manuell` nimmt es sonst von der Flaeche
    # (`routes/datenquellen.py::ohne_nicht_zuordenbare`), und im Monatsabschluss
    # erscheint es gar nicht mehr.
    #
    # **Warum es weg musste, gemessen 24.08.:**
    # 1. Ein Wert hier wird von NIEMANDEM gelesen. Baumweit gilt
    #    `PV_ERZEUGER_TYPEN = ("pv-module", "balkonkraftwerk")`; der
    #    Wechselrichter steht in `live_sensor_config.SKIP_TYPEN` und fehlt in
    #    `snapshot/komponenten_beitraege._TYP_KEY_PREFIX`. Gemessen an der
    #    Fakten-Schicht: 900 kWh am Wechselrichter ⇒ `erzeugung.pv_kwh = 0.0`,
    #    dieselben 900 an einem PV-Modul ⇒ 900.0.
    # 2. Schlimmer als folgenlos: Das Feld war `("pflicht", "pv_energie")` und
    #    hat damit die Alternativ-Gruppe BESETZT. Wer seinen Zaehler hier
    #    zuordnete — auf der Zuordnungs-Flaeche ging das, obwohl der
    #    Monatsabschluss das Feld bei vorhandenen Modulen laengst ausblendete —,
    #    bekam eine Sackgasse: `basis:pv_gesamt` **und** das Modul-Feld meldeten
    #    „bereits an anderer Stelle zugeordnet", waehrend die einzige belegte
    #    Quelle nirgends gelesen wurde. Die Live-Kachel fiel auf die
    #    Trapez-Hochrechnung zurueck (+31 %, #388/F-57).
    # 3. Der Hinweistext sagte „Nur noetig, wenn keine separaten
    #    PV-Modul-Investitionen erfasst werden" — genau diese Lage ergibt aber
    #    **0 kWh PV** (gemessen: Anlagen-Aggregat 1000 ohne Modul-Komponente ⇒
    #    0.0) und wird vom Daten-Checker bereits als ERROR gemeldet
    #    („keine PV-Module angelegt"). Das Feld beschrieb ein Modell, das die
    #    Rechnung nicht kennt.
    #
    # **Der Weg ohne dieses Feld** ist gemessen und offen: der anlagenweite
    # Zaehler `basis:pv_gesamt` speist seit 2026-08-07 den Monatswert
    # (`snapshot/keys.py`: `basis["pv_gesamt"]` -> `Monatsdaten.pv_erzeugung_kwh`),
    # und von dort verteilt `resolve_pv_je_modul` kWp-gewichtet auf die Module.
    #
    # ⚠ `bedingung_anlage: keine_pv_module` ist bewusst ENTFALLEN: es blendete
    # das Feld genau dann aus, wenn Module existierten — also im Regelfall — und
    # liess es stehen, wenn es nichts bewirken konnte. Genau verkehrt herum.
    "wechselrichter": [
        {
            "feld": "pv_erzeugung_kwh", "label": "PV-Erzeugung", "einheit": "kWh",
            "csv_suffix": "kWh",
            "aggregiert_in": "pv_erzeugung_sum",
            "nur_manuell": True,
            "nur_bestand": True,
            "hinweis": (
                "\u26a0 Nicht mehr verwenden. Die PV-Erzeugung geh\u00f6rt an die "
                "PV-Module (oder an das Balkonkraftwerk); der anlagenweite Z\u00e4hler "
                "steht unter Anlage (Basis) als \u201ePV-Erzeugung Z\u00e4hlerstand\u201c. "
                "Ein Wert an dieser Stelle wird nicht ausgewertet. Das Feld erscheint "
                "nur noch, solange hier eine alte Zuordnung h\u00e4ngt \u2014 entferne "
                "sie und ordne den Z\u00e4hler neu zu."
            ),
        },
    ],

    "speicher": [
        {
            "feld": "ladung_kwh", "label": "Ladung", "einheit": "kWh",
            # #281: Mit Netzladung ist "Ladung" mehrdeutig (Gesamt vs. PV-Anteil).
            # `ladung_kwh` ist die Gesamtladung, `ladung_netz_kwh` ⊆ `ladung_kwh`.
            "label_wenn": {"laedt_aus_netz": "Ladung (gesamt, inkl. Netz)"},
            "csv_suffix": "Ladung_kWh",
            "aggregiert_in": "batterie_ladung_sum",
            # N-60/#351: Die Messstelle war nicht genannt — und ohne sie sind ein
            # DC-Zähler an der Batterie und ein AC-Zähler am Batterie-Wechsel-
            # richter **beide** vertragskonform und liefern trotzdem verschiedene
            # Zahlen (dazwischen liegt der Wandlungsverlust). Der Kanon ist
            # deshalb an die Kopplung gebunden: sie ist die einzige Angabe, die
            # für beide Bauformen erhebbar ist — bei einem DC-gekoppelten
            # Speicher gibt es zwischen Batterie und Hybrid-Wechselrichter gar
            # keinen AC-Punkt, ein „immer AC"-Vertrag wäre dort nicht messbar.
            "hinweis": "Gesamte in den Speicher geladene Energie (kWh, kumulativer Zähler oder Tagessensor). Immer ≥ 0. Gemessen an der Stelle, die zur Kopplung des Speichers passt: bei AC-Kopplung hausseitig hinter dem Batterie-Wechselrichter, bei DC-Kopplung am Batterie-Anschluss. Ladung und Entladung müssen von derselben Seite kommen — sonst enthält der Wirkungsgrad die Wandlung nur in eine Richtung.",
        },
        {
            "feld": "entladung_kwh", "label": "Entladung", "einheit": "kWh",
            "csv_suffix": "Entladung_kWh",
            "aggregiert_in": "batterie_entladung_sum",
            "hinweis": "Gesamte aus dem Speicher entladene Energie (kWh, kumulativer Zähler oder Tagessensor). Immer ≥ 0. Dieselbe Messstelle wie die Ladung (s. dort) — bei gemischten Seiten misst der Wirkungsgrad die Messstelle statt den Speicher.",
        },
        # Konditionell — nur wenn laedt_aus_netz=true (arbitrage_faehig impliziert das):
        {
            "feld": "ladung_netz_kwh", "label": "Netzladung", "einheit": "kWh",
            "bedingung": "laedt_aus_netz",
            "csv_suffix": "Netzladung_kWh",
            "hinweis": "Anteil der Ladung, der aus dem Netz kam (kWh, kumulativ oder Tagessensor). Optional und muss ≤ Ladung sein. Nur nötig, wenn der Speicher aus dem Netz lädt — bei reiner PV-Ladung leer lassen.",
        },
        # Ladepreis nur bei echter Arbitrage relevant — Backup-/Notladung läuft zum Bezugspreis.
        # `nur_manuell`: ein MONATSWERT, kein Messwert. Es gibt keinen Erfassungsweg,
        # der ihn aus einem Sensor oder Topic zöge (`snapshot/keys.py` schließt ihn
        # ausdrücklich aus) — angeboten wurde er auf der Zuordnungs-Fläche trotzdem,
        # und ein Tester hat dort einen Preis-Sensor hinterlegt, der nichts bewirkte,
        # aber eine Daten-Checker-Meldung auslöste (Forum simon42 #89667/54 + /64,
        # MartyBr; dort stand zudem ein €/kWh-Sensor in einem ct/kWh-Feld). Erfassbar
        # bleibt er im Monatsabschluss, im CSV-Import und über den errechneten
        # Vorschlag bei dynamischem Tarif.
        {
            "feld": "speicher_ladepreis_cent", "label": "Ø Ladepreis", "einheit": "ct/kWh",
            "bedingung": "arbitrage_faehig",
            "nur_manuell": True,
            "csv_suffix": "Ladepreis_Cent",
            "hinweis": "Ø Preis der Netzladung in ct/kWh. Nur bei Arbitrage relevant (gezielt günstig laden) — Backup-/Notladung läuft zum normalen Bezugspreis. Meist manuell im Monatsabschluss; bei dynamischem Tarif rechnet eedc den Wert selbst aus den Stundenpreisen.",
        },
    ],

    "waermepumpe": [
        # Default-Modus (getrennte_strommessung=false):
        {
            "feld": "stromverbrauch_kwh", "label": "Stromverbrauch", "einheit": "kWh",
            # **Weich seit dem 26.08.2026 (K3).** Ein gesetztes Kennzeichen darf
            # einen vorhandenen Gesamtzähler niemals entwerten — genau daran
            # verschwand bei OB73-gif der ganze Block *Wärme/Klima* (#263). Die
            # Auswertung hat das seit `530996f5` gelernt; die **Pflege** nicht:
            # im Monatsabschluss war das Feld hart weg, wer seine Aufteilung erst
            # halb eingerichtet hatte, konnte die Gesamtmenge nicht mehr
            # nachtragen. Auf der Zuordnungs-Fläche war es ohnehin schon sichtbar
            # (dort filtert nur die Geräteklasse) — die beiden Flächen sagten
            # also Gegenteiliges.
            "bedingung": "!getrennte_strommessung",
            "weich": ("getrennte_strommessung",),
            "csv_suffix": "Strom_kWh",
            "hinweis": "Gesamter elektrischer Energieverbrauch der WP (kWh, kumulativ oder Tagessensor). Bei getrennter Messung: Summe aus Heizen + Warmwasser.",
        },
        # Getrennte-Strommessung-Modus (getrennte_strommessung=true):
        {
            "feld": "strom_heizen_kwh", "label": "Strom Heizen", "einheit": "kWh",
            # ⚠ **Zwei Bedingungen verschiedener Härte** — der Fall, für den
            # `weich` die Schlüssel nennt statt ein Bool zu sein:
            # `getrennte_strommessung` ist **hart** (ohne Kennzeichen gibt es
            # die getrennte Achse nicht), `!brauchwasser` ist **weich** (eine
            # Brauchwasser-WP heizt typischerweise nicht — wer doch einen
            # Heizzähler hat, ordnet ihn unter „Weitere Größen erfassen" zu).
            "bedingung": ["getrennte_strommessung", "!brauchwasser"],
            "weich": ("brauchwasser",),
            "csv_suffix": "Strom_Heizen_kWh",
            "hinweis": "Elektrische Energie für den Heizbetrieb (kWh, kumulativ oder Tagessensor). Nur bei getrennter Strommessung.",
        },
        {
            "feld": "strom_warmwasser_kwh", "label": "Strom Warmwasser", "einheit": "kWh",
            # B5 (Entscheid Gernot 2026-08-22) — **die zweite Hälfte von N-304.**
            # Dort bekam `warmwasser_kwh` sein `!luft_luft`, weil eine
            # Split-Klimaanlage keinen Warmwasserkreis hat. Für den zugehörigen
            # STROM galt derselbe Satz und stand trotzdem nicht da: das Feld
            # wurde einer Klimaanlage mit getrennter Strommessung weiter
            # angeboten, und der Daten-Checker verlangte es unter dem Label
            # „Strom Heizen/Warmwasser".
            #
            # ⚠ **Zwei Bedingungen, nicht eine** — deshalb die Liste (UND, siehe
            # `bedingung_erfuellt`): `getrennte_strommessung` sagt, ob die Achse
            # überhaupt getrennt erfasst wird, `!luft_luft`, ob es die zweite
            # Seite der Achse an diesem Gerät gibt. Vorher konnte die Auswertung
            # nur eine Bedingung tragen — genau daran ist N-304 hier hängen
            # geblieben.
            #
            # `strom_heizen_kwh` bleibt bewusst OHNE `!luft_luft`: die
            # Heiz-Achse existiert an einer Klimaanlage sehr wohl (dieselbe
            # Trennlinie wie bei `heizenergie_kwh` in N-304).
            "bedingung": ["getrennte_strommessung", "!luft_luft"],
            "csv_suffix": "Strom_Warmwasser_kWh",
            "hinweis": "Elektrische Energie für die Warmwasserbereitung (kWh, kumulativ oder Tagessensor). Nur bei getrennter Strommessung.",
        },
        # Immer vorhanden:
        # #120: Wording-Schaerfung — abgegebene thermische Waerme, nicht Strom.
        # CSV-Suffix bleibt fuer Backwards-Kompat unveraendert.
        {
            "feld": "heizenergie_kwh", "label": "Heizwärme", "einheit": "kWh",
            # Eine Brauchwasser-WP gibt keine Heizwärme ab (SOLL §2.1/A6).
            # **Weich, nicht hart:** die Bauart ist eine Anwender-Angabe, und
            # ein Gerät, das doch beides kann, soll seinen Zähler behalten
            # dürfen. Die Warmwasser-Achse daneben bleibt hart erwartet.
            "bedingung": "!brauchwasser",
            "weich": ("brauchwasser",),
            "csv_suffix": "Heizung_kWh",
            "hinweis": "Abgegebene Heizwärme (thermisch, NICHT Strom!) in kWh, kumulativ oder Tagessensor. Ohne Wärmemengenzähler aus Stromverbrauch × JAZ berechnet.",
        },
        {
            "feld": "warmwasser_kwh", "label": "Warmwasser", "einheit": "kWh",
            "csv_suffix": "Warmwasser_kWh",
            # N-304: **eine Split-Klimaanlage hat keinen Warmwasserkreis.** Das
            # Feld war dort nicht nur überflüssig, sondern schädlich: es fließt
            # in dieselbe Summe `wp_waerme` wie die Heizwärme
            # (`imd_monatsaggregat`, D1) und speist damit `gas_kosten_altanlage`
            # und die CO₂-Bilanz — ein gefüllter Wert erzeugt an einem Gerät
            # ohne Warmwasserbereitung eine **erfundene Ersparnis**.
            #
            # ⚠ `heizenergie_kwh` bleibt bewusst OHNE diese Bedingung: eine
            # Klimaanlage gibt sehr wohl Wärme ab, und genau daran hängen die
            # Gas- und CO₂-Ersparnis, die vor dem #263-Konzept ganz fehlten
            # (Gernot, 2026-08-21). Nur die Warmwasser-Achse gibt es nicht.
            #
            # Die Entscheidung selbst ist älter: `64826a40` (N-86, 16.08.) hat
            # eine Klimaanlage von der Heizwärme-PFLICHT befreit, weil „die
            # Größe am Gerät nicht existiert" — umgesetzt aber nur in
            # `get_feld_bedarf`, also auf der Zuordnungs-Fläche. Der
            # Monatsabschluss liest `get_felder_fuer_investition` und kannte
            # die Unterscheidung nicht. Genau das Muster, das jener Commit
            # selbst beklagt: „dieselbe Anlage, zwei Flächen, gegenteilige
            # Aussage."
            "bedingung": "!luft_luft",
            "hinweis": "Abgegebene Warmwasser-Wärme (thermisch) in kWh, kumulativ oder Tagessensor. Optional — sonst in der Heizwärme enthalten.",
        },
        # #263 — GEMESSENER Verbrauch je Betriebsart (Split-Klimaanlage).
        # Erzeugt aus dem Kanon (`core/betriebsmodus.py`), siehe
        # `_betriebsart_felder` unter dieser Tabelle.
        *_BETRIEBSART_FELDER,
    ],

    "e-auto": [
        {
            "feld": "km_gefahren", "label": "Gefahrene km", "einheit": "km",
            "placeholder": "z.B. 1200",
            "csv_suffix": "km",
            "hinweis": "Gefahrene Kilometer im Monat — kumulativer km-Zähler (Auto-Integration/OBD) oder Tagessensor, sonst manuell.",
        },
        {
            "feld": "verbrauch_kwh", "label": "Verbrauch", "einheit": "kWh",
            "placeholder": "z.B. 216",
            "csv_suffix": "Verbrauch_kWh",
            "hinweis": "Kumulativer kWh-Zähler des gefahrenen Energieverbrauchs (zählt fortlaufend hoch, Tagessensor geht auch) — der reine Fahrverbrauch, NICHT pro Fahrt und NICHT kWh/100 km. eedc errechnet daraus mit den km die Effizienz. Optional: fehlt der Wert, nähert eedc die kWh/100 km aus der geladenen Energie an (inkl. Ladeverluste).",
        },
        {
            "feld": "ladung_pv_kwh", "label": "Heim: PV", "einheit": "kWh",
            "placeholder": "z.B. 130",
            "csv_suffix": "Ladung_PV_kWh",
            # Phase 2a: existiert eine Wallbox-Investition, ist SIE die kanonische
            # Quelle der Heimladung — dann nicht zusätzlich am E-Auto erfassen
            # (sonst Dual-Daten / Doppelzählung, siehe docs/KONZEPT-WALLBOX-EAUTO.md).
            "bedingung_anlage": "keine_wallbox",
            "hinweis": "Zu Hause aus PV geladene Energie (kWh, kumulativ oder Tagessensor). Nur ohne Wallbox — mit Wallbox wird die Heimladung dort erfasst. Alternativ per EV-Quote aus der Gesamt-Ladung berechnet.",
        },
        {
            "feld": "ladung_netz_kwh", "label": "Heim: Netz", "einheit": "kWh",
            "placeholder": "z.B. 50",
            "csv_suffix": "Ladung_Netz_kWh",
            "bedingung_anlage": "keine_wallbox",  # s. ladung_pv_kwh (Phase 2a)
            "hinweis": "Zu Hause aus dem Netz geladene Energie (kWh, kumulativ oder Tagessensor). Nur ohne Wallbox. Alternativ per EV-Quote berechnet.",
        },
        {
            "feld": "ladung_extern_kwh", "label": "Extern", "einheit": "kWh",
            "placeholder": "z.B. 36",
            "csv_suffix": "Ladung_Extern_kWh",
            "hinweis": "Unterwegs geladene Energie (Autobahn, Arbeit) in kWh. Meist manuell im Monatsabschluss. Optional.",
        },
        {
            "feld": "ladung_extern_euro", "label": "Extern Kosten", "einheit": "€",
            "placeholder": "z.B. 18.00",
            "csv_suffix": "Ladung_Extern_Euro",
            "hinweis": "Kosten der externen Ladung (€). Manuell. Optional.",
        },
        # Konditionell — nur wenn v2h_faehig=true oder nutzt_v2h=true:
        {
            "feld": "v2h_entladung_kwh", "label": "V2H Entladung", "einheit": "kWh",
            "bedingung": "v2h_faehig",
            "placeholder": "z.B. 25",
            "csv_suffix": "V2H_kWh",
            "hinweis": "Vehicle-to-Home zurück ins Haus gespeiste Energie (kWh, kumulativ oder Tagessensor). Nur bei V2H-fähigem Fahrzeug. Optional.",
        },
    ],

    "wallbox": [
        {
            "feld": "ladung_kwh", "label": "Ladung gesamt", "einheit": "kWh",
            "placeholder": "z.B. 200",
            "csv_suffix": "Ladung_kWh",
            "hinweis": "Gesamte von der Wallbox abgegebene Ladeenergie (kWh, kumulativer Zähler oder Tagessensor). Kanonische Heimladungs-Quelle (Phase 2a) — hier mappen, nicht am E-Auto.",
        },
        {
            "feld": "ladung_pv_kwh", "label": "Ladung PV", "einheit": "kWh",
            "placeholder": "z.B. 80",
            "csv_suffix": "Ladung_PV_kWh",
            "hinweis": "PV-Anteil der Wallbox-Ladung (kWh, kumulativ oder Tagessensor). Optional — manche Wallboxen (z. B. go-e) messen das separat.",
        },
        {
            "feld": "ladevorgaenge", "label": "Ladevorgänge", "einheit": "",
            "placeholder": "z.B. 12",
            "csv_suffix": "Ladevorgaenge",
            "typ": "int",
            "hinweis": "Anzahl der Ladevorgänge (kumulativer Zähler oder Tagessensor). Optional.",
        },
    ],

    # N-266: Hängen `pv-module` unter dem Balkonkraftwerk (seit 2026-08-17
    # möglich, damit zwei Module über Eck zwei Ausrichtungen tragen können),
    # dann wird `pv_erzeugung_kwh` zum **Aggregat seiner Kinder** — genau die
    # Rolle, die `Monatsdaten.pv_erzeugung_kwh` für die ganze Anlage hat: die
    # gemessenen Modulwerte gewinnen, das Aggregat füllt nur deren Lücken
    # (ADR-002/**P7**, aufgelöst in `services/pv_monatswerte.py`).
    #
    # ⛔ **Bewusst NICHT das `nur_manuell`-Muster des BKW-Akkus zwei Felder
    # weiter unten**, obwohl der Auftrag es als Blaupause vorsah. Beim Akku ist
    # der Kind-Weg strikt reicher (Live-Leistung, SoC, Energiefluss, Zählerpfad)
    # — das eigene Feld kennt nur einen Monatswert, es zu sperren verliert
    # nichts. Hier ist es umgekehrt: der Wechselrichter des BKW ist oft der
    # **einzige** Zähler, den es gibt, und die Module darunter haben gar keinen
    # eigenen Sensor. Das Feld zu sperren hätte dem Melder-Fall (ein Set, zwei
    # Ausrichtungen, ein Sensor) jede Erfassung genommen. Also bleibt es
    # vollständig zuordenbar; die Doppelzählung verhindert die **Leserichtung**,
    # nicht ein Erfassungsverbot.
    "balkonkraftwerk": [
        {
            "feld": "pv_erzeugung_kwh", "label": "Erzeugung", "einheit": "kWh",
            "csv_suffix": "Erzeugung_kWh",
            "csv_suffix_alt": "kWh",  # Rückwärtskompatibilität
            "aggregiert_in": "pv_erzeugung_sum",
            "hinweis": "Kumulativer kWh-Zähler (oder Tagessensor) der BKW-Erzeugung vom Wechselrichter. Immer ≥ 0. Sind dem Balkonkraftwerk PV-Module zugeordnet, gilt dieser Wert als deren Gesamtsumme: eigene Modulwerte haben Vorrang, dieser hier füllt die Lücken.",
        },
        {
            "feld": "eigenverbrauch_kwh", "label": "Eigenverbrauch", "einheit": "kWh",
            "csv_suffix": "Eigenverbrauch_kWh",
            "hinweis": "Direkt im Haushalt verbrauchte BKW-Erzeugung (kWh, kumulativ oder Tagessensor). Optional — sonst aus Erzeugung − Einspeisung berechnet.",
        },
        # Konditionell — nur wenn hat_speicher=true. ALTBESTAND, `nur_manuell`:
        # Der Kanon für einen BKW-Akku ist seit 2026-07-31 die **eigene
        # Speicher-Investition mit Parent Balkonkraftwerk** (Weg A) — die trägt
        # Live-Leistung, SoC, Energiefluss-Knoten und Zählerpfad, während diese
        # beiden Felder nur einen Monatswert kennen. Sie bleiben erfassbar,
        # damit gepflegte Werte lesbar bleiben, sind aber nicht mehr
        # **zuordenbar**: kein Sensor, kein MQTT-Topic. Wer sie gepflegt hat,
        # wird vom Daten-Checker auf Weg A gewiesen (`daten_checker/stammdaten.py`).
        {
            "feld": "speicher_ladung_kwh", "label": "Speicher Ladung", "einheit": "kWh",
            "bedingung": "hat_speicher",
            "nur_manuell": True,
            "csv_suffix": "Speicher_Ladung_kWh",
            "aggregiert_in": "batterie_ladung_sum",
            "hinweis": "In den BKW-Akku geladene Energie (kWh). Nur manuell oder per Import — für Sensor-/MQTT-Zuordnung den Akku als eigene Speicher-Investition mit Parent Balkonkraftwerk erfassen.",
        },
        {
            "feld": "speicher_entladung_kwh", "label": "Speicher Entladung", "einheit": "kWh",
            "bedingung": "hat_speicher",
            "nur_manuell": True,
            "csv_suffix": "Speicher_Entladung_kWh",
            "aggregiert_in": "batterie_entladung_sum",
            "hinweis": "Aus dem BKW-Akku entladene Energie (kWh). Nur manuell oder per Import — für Sensor-/MQTT-Zuordnung den Akku als eigene Speicher-Investition mit Parent Balkonkraftwerk erfassen.",
        },
    ],

    # Sonstiges: Felder hängen von der Kategorie ab (via get_felder_fuer_sonstiges)
    "sonstiges": {
        "erzeuger": [
            {
                "feld": "erzeugung_kwh", "label": "Erzeugung", "einheit": "kWh",
                "csv_suffix": "Erzeugung_kWh",
                "aggregiert_in": "pv_erzeugung_sum",
                "hinweis": "Erzeugte Energie (z. B. BHKW, Windrad) in kWh, kumulativer Zähler oder Tagessensor.",
            },
            {
                "feld": "eigenverbrauch_kwh", "label": "Eigenverbrauch", "einheit": "kWh",
                "csv_suffix": "Eigenverbrauch_kWh",
                "hinweis": "Direkt selbst verbrauchter Anteil der Erzeugung (kWh, kumulativ oder Tagessensor). Optional.",
            },
            {
                "feld": "einspeisung_kwh", "label": "Einspeisung", "einheit": "kWh",
                "csv_suffix": "Einspeisung_kWh",
                "hinweis": "Ins Netz eingespeister Anteil der Erzeugung (kWh, kumulativ oder Tagessensor). Optional.",
            },
            # Konzept-Wirtschaftlichkeit §9 Weg 2 (Bauschritt 9): eedc kennt
            # genau EINEN Einspeisesatz je Anlage (`Strompreis.anlage_id`). Wer
            # einen zweiten Erzeuger mit eigenem Vergütungssatz betreibt, kann
            # dessen Erlös deshalb nicht von eedc ausrechnen lassen — wohl aber
            # von Home Assistant: ein Template-Sensor kennt beide Sätze und
            # liefert den Betrag monatsgenau. Damit entfällt der geschätzte
            # Jahresbetrag aus §8/1 für diesen Fall.
            #
            # ⚠ KEIN Abzug von der Anlagen-Bewertung (Entscheid Maintainer,
            # 2026-08-10): zwei Vergütungssätze bedeuten zwei Messungen — sonst
            # könnte der Netzbetreiber nicht abrechnen. In den Anlagen-
            # Einspeisezähler gehört ohnehin nur die zum Anlagentarif vergütete
            # Menge; dieser Betrag kommt zusätzlich dazu. Der Hinweis sagt das.
            {
                "feld": "einspeise_erloes_euro", "label": "Einspeise-Erlös", "einheit": "€",
                "placeholder": "z. B. 42.30",
                "csv_suffix": "Einspeise_Erloes_Euro",
                "hinweis": (
                    "Erlös DIESES Erzeugers in € — für einen eigenen Einspeisetarif, "
                    "den eedc nicht kennen kann (es gibt einen Satz je Anlage). Am besten "
                    "als kumulativer Helfer-Sensor aus Home Assistant (state_class "
                    "total_increasing, device_class monetary), dann wird der Wert im "
                    "Monatsabschluss vorgeschlagen. Wichtig: In den Anlagen-Einspeisezähler "
                    "gehört nur die Menge, die zum Anlagentarif abgerechnet wird — dieser "
                    "Betrag kommt zusätzlich dazu."
                ),
            },
        ],
        "verbraucher": [
            {
                "feld": "verbrauch_sonstig_kwh", "label": "Verbrauch", "einheit": "kWh",
                "csv_suffix": "Verbrauch_kWh",
                "hinweis": "Verbrauchte Energie (z. B. Sauna, Pool) in kWh, kumulativer Zähler oder Tagessensor.",
            },
            {
                "feld": "bezug_pv_kwh", "label": "davon PV", "einheit": "kWh",
                "csv_suffix": "Bezug_PV_kWh",
                "hinweis": "PV-gedeckter Anteil des Verbrauchs (kWh, kumulativ oder Tagessensor). Optional.",
            },
            {
                "feld": "bezug_netz_kwh", "label": "davon Netz", "einheit": "kWh",
                "csv_suffix": "Bezug_Netz_kWh",
                "hinweis": "Netz-gedeckter Anteil des Verbrauchs (kWh, kumulativ oder Tagessensor). Optional.",
            },
        ],
        "speicher": [
            # Hinweis: cockpit/komponenten.py liest erzeugung_kwh/verbrauch_sonstig_kwh
            # für Sonstiges-Speicher — diese Feldnamen sind bindend.
            {
                "feld": "erzeugung_kwh", "label": "Erzeugung/Entladung", "einheit": "kWh",
                "csv_suffix": "Erzeugung_kWh",
                "aggregiert_in": "batterie_entladung_sum",
                "hinweis": "Aus dem Speicher entladene Energie (kWh, kumulativer Zähler oder Tagessensor).",
            },
            {
                "feld": "verbrauch_sonstig_kwh", "label": "Verbrauch/Ladung", "einheit": "kWh",
                "csv_suffix": "Verbrauch_kWh",
                "aggregiert_in": "batterie_ladung_sum",
                "hinweis": "In den Speicher geladene Energie (kWh, kumulativer Zähler oder Tagessensor).",
            },
        ],
        # #377 / N-294 — Verbrauchszähler für Gas, Öl, Wasser: **erfassen und
        # anzeigen, nicht bewerten.** Die Kategorie führt genau EINEN Wert, den
        # **Zählerstand**; die einzige Rechnung darauf ist `Ende − Anfang` des
        # betrachteten Fensters. Die Einheit hängt am **Gerät**
        # (`zaehler_einheit`), nicht am Feld — deshalb steht hier `""`.
        #
        # ⚑ **Die leere Einheit IST die Sicherung, nicht eine Auslassung.**
        # `einheit_klasse("")` ist `None` (s. u.) ⇒ das Feld kann strukturell
        # nie als Energie gelesen werden: es fällt aus
        # `kumulative_zaehler_felder_je_typ()` heraus, aus der Energiebilanz,
        # aus Autarkie/Eigenverbrauch, aus dem Community-Datensatz. Wer hier
        # „m³" oder gar „kWh" einträgt — auch „nur der Klarheit halber" —,
        # hebt genau diesen Schutz auf und lässt Gas in die Strombilanz laufen.
        # Die Anzeige-Einheit kommt aus `einheit_fuer(feld, investition)`.
        "zaehler": [
            {
                "feld": "zaehlerstand", "label": "Zählerstand", "einheit": "",
                "einheit_je_geraet": "zaehler_einheit",
                "csv_suffix": "Zaehlerstand",
                # ⚑ **`stand: True` — der Marker, an dem F-58 hing** (dietmar1968,
                # T89667 #185, 21.08.2026). Der stündliche Snapshot-Job holte den
                # Wert wie jeden anderen Zähler über `get_value_at`, und das nimmt
                # bei `has_sum` **ausschließlich HAs `sum`**: die reset-bereinigte
                # **Verbrauchssumme seit Aufzeichnungsbeginn**. Für einen
                # Energiezähler ist das richtig und ausdrücklich so entschieden
                # (v3.25.18 / #184) — für einen **Zählerstand** ist es die falsche
                # Größe. Sein Wasserzähler meldete 47,360 m³, eedc zeigte 90.
                #
                # Ein Zählerstand ist eine **Bestandsgröße**: die Zahl, die auf dem
                # Zähler steht. Sie kommt aus `state`, nie aus `sum`, und sie wird
                # **nicht umgerechnet** (§3 des Modells). Der Marker steht am Feld
                # und nicht als Liste in `snapshot/keys.py` — das war N-259, wo
                # genau so eine zweite Handliste auseinandergelaufen ist.
                "stand": True,
                "hinweis": (
                    "Der abgelesene Zählerstand — die Zahl, die auf dem Zähler steht "
                    "(Gas, Wasser, Heizöl …). eedc rechnet daraus nur die Differenz "
                    "zwischen Anfang und Ende des angezeigten Zeitraums; in "
                    "Energiebilanz, Autarkie, Wirtschaftlichkeit und CO₂ geht der Wert "
                    "bewusst nicht ein. Aus einem Sensor (stündlich) oder im "
                    "Monatsabschluss von Hand."
                ),
            },
        ],
    },
}

# =============================================================================
# Live-Felder pro Investitionstyp (Echtzeit: W, kW, %, °C)
#
# Diese Felder werden als MQTT-Topics und im Sensor-Mapping-Wizard verwendet.
# "key"     — MQTT-Topic-Suffix / Sensor-Mapping-Key
# "label"   — Anzeigename
# "einheit" — W, %, °C
# "bedingung" — optional, gleiche Semantik wie in INVESTITION_FELDER
# =============================================================================

LIVE_FELDER_INV: dict = {
    # Live-Felder speisen ausschließlich das Live-Dashboard (Momentanwerte in W/%).
    # Für Monatswerte, Statistik und Wirtschaftlichkeit zählen die kWh-Felder oben —
    # ein fehlender Live-Sensor kostet also nur die Echtzeit-Anzeige.
    "pv-module": [
        {"key": "leistung_w", "label": "Leistung", "einheit": "W",
         "hinweis": "Momentane Leistung dieses Strings in W. Ohne eigenen Sensor je Modul "
                    "nutzt eedc „PV gesamt (W)“ der Anlage — sobald hier einer zugeordnet "
                    "ist, hat er Vorrang."},
    ],
    "wechselrichter": [
        {"key": "leistung_w", "label": "Leistung", "einheit": "W",
         "hinweis": "Momentane AC-Ausgangsleistung des Wechselrichters in W."},
    ],
    "speicher": [
        {"key": "leistung_w", "label": "Leistung", "einheit": "W",
         "hinweis": "Momentane Lade-/Entladeleistung in W. Ein vorzeichenbehafteter Sensor "
                    "genügt (+ laden / − entladen); zeigt er in die falsche Richtung, dreht "
                    "ihn das ⇅-Symbol am Wert."},
        {"key": "soc",        "label": "Ladestand", "einheit": "%",
         "hinweis": "Ladestand des Speichers in Prozent (0–100)."},
    ],
    "e-auto": [
        {"key": "leistung_w", "label": "Ladeleistung", "einheit": "W",
         "hinweis": "Momentane Ladeleistung des Fahrzeugs in W. Bei vorhandener Wallbox "
                    "misst diese meist dasselbe — denselben Sensor nicht beiden Geräten "
                    "zuordnen, sonst zählt die Live-Bilanz ihn doppelt."},
        {"key": "soc",        "label": "Ladestand",    "einheit": "%",
         "hinweis": "Ladestand der Fahrzeugbatterie in Prozent (0–100)."},
    ],
    "wallbox": [
        {"key": "leistung_w", "label": "Leistung", "einheit": "W",
         "hinweis": "Momentane Ladeleistung der Wallbox in W."},
    ],
    "waermepumpe": [
        {"key": "leistung_w",              "label": "Leistung gesamt",      "einheit": "W",
         # #263: mit Innengeräte-Liste gibt es ihn zusätzlich je Innengerät —
         # das Gerätefeld bleibt der Anlagenwert, die Kopien sind die Aufschlüsselung.
         "je_innengeraet": True,
         "label_je_innengeraet": "Leistung",
         "hinweis": "Momentane elektrische Leistungsaufnahme der Wärmepumpe in W "
                    "(nicht die abgegebene Wärmeleistung)."},
        {"key": "leistung_heizen_w",       "label": "Leistung Heizen",      "einheit": "W",
         "hinweis": "Elektrische Leistungsaufnahme im Heizbetrieb in W. Nur sinnvoll, wenn "
                    "Heizen und Warmwasser getrennt gemessen werden."},
        {"key": "leistung_warmwasser_w",   "label": "Leistung Warmwasser",  "einheit": "W",
         "hinweis": "Elektrische Leistungsaufnahme der Warmwasserbereitung in W. Nur "
                    "sinnvoll bei getrennter Messung."},
        # ⭐ **W-13 (26.08.2026) — die dritte Leistung, die es bis dahin nicht gab.**
        # `leistung_heizen_w` und `leistung_warmwasser_w` stehen hier seit Langem
        # und an JEDER Wärmepumpe; für den Kühlbetrieb gab es kein Gegenstück —
        # an keiner Bauart. MartyBr schreibt am 25.08. (T89667 #200): „getrennte
        # Zähler für Heizung, Warmwassererwärmung … und seit dem Sommer auch für
        # den **Kühlbetrieb**. Es werden sowohl die **Live-Werte (Power in W)**
        # als auch die kumulierten Werte (Energy in kWh) [erfasst]."
        #
        # ⚠ **Ohne diese Zeile erreicht R1 seinen Fall nur zur Hälfte:** die
        # Energie-Achse wird mit `betriebsart_strom_kuehlen_kwh` zuordenbar, seine
        # Live-Leistung bliebe heimatlos.
        #
        # ⛔ **Bewusst KEINE vier `betriebsart_leistung_*_w`.** An einem
        # Luft-Luft-Gerät stünden dann `leistung_heizen_w` und
        # `betriebsart_leistung_heizen_w` nebeneinander — dieselbe Zweideutigkeit
        # zweier Familien, an der ein Tester schon einmal zwei Felder addiert hat
        # (#89667/62). Eine Zeile in der bestehenden Familie, ohne Bedingung wie
        # ihre beiden Nachbarn.
        {"key": "leistung_kuehlen_w",      "label": "Leistung Kühlen",      "einheit": "W",
         "hinweis": "Elektrische Leistungsaufnahme im Kühlbetrieb in W. Nur sinnvoll, "
                    "wenn der Kühlbetrieb getrennt gemessen wird — reine Anzeige, die "
                    "Mengen kommen aus dem kWh-Zähler."},
        {"key": "warmwasser_temperatur_c", "label": "Warmwasser-Temperatur","einheit": "°C",
         "hinweis": "Temperatur im Warmwasserspeicher in °C — reine Anzeige, geht in keine "
                    "Berechnung ein."},
        # #263 K-2: der erste Wert in eedc, der ein ZUSTAND ist statt einer Zahl.
        # `zustand: True` ist keine Kosmetik, sondern die Weiche — siehe
        # ZUSTAND_LIVE_FELDER unter der Tabelle.
        {"key": "betriebsmodus", "label": "Betriebsmodus", "einheit": "",
         "zustand": True,
         "hinweis": "Die `climate`-Entität der Klimaanlage/Wärmepumpe (z. B. "
                    "`climate.wohnzimmer`) — sie meldet Heizen, Kühlen, Entfeuchten "
                    "oder Aus. Optional: ohne sie zählt eedc den Stromverbrauch wie "
                    "bisher als eine Zahl, mit ihr kann es sagen, welcher Teil davon "
                    "ins Heizen und welcher ins Kühlen ging. Ein Zustand, kein "
                    "Messwert — deshalb nur als HA-Sensor zuordenbar, nicht über MQTT."},
        # #263 — Raumtemperaturen einer Split-Klimaanlage. Bewusst **ohne
        # Auswertung**: sie gehen in keine Bilanz, keine Effizienz und keine
        # Bewertung ein, sondern stehen im Live-Block, weil sie da sind
        # (Entscheid Gernots, 2026-08-21). Mit Innengeräte-Liste je Gerät.
        {"key": "soll_temperatur_c", "label": "Soll-Temperatur", "einheit": "°C",
         "bedingung": "luft_luft", "je_innengeraet": True,
         "hinweis": "Eingestellte Zieltemperatur in °C — reine Anzeige, geht in keine "
                    "Berechnung ein."},
        {"key": "ist_temperatur_c", "label": "Raumtemperatur", "einheit": "°C",
         "bedingung": "luft_luft", "je_innengeraet": True,
         "hinweis": "Gemessene Raumtemperatur in °C — reine Anzeige, geht in keine "
                    "Berechnung ein."},
    ],
    "balkonkraftwerk": [
        {"key": "leistung_w", "label": "Leistung", "einheit": "W",
         "hinweis": "Momentane Leistung des Balkonkraftwerks in W."},
    ],
    "sonstiges": [
        {"key": "leistung_w", "label": "Leistung", "einheit": "W",
         "hinweis": "Momentane Leistung in W — bei einem Erzeuger positiv als Erzeugung, "
                    "bei einem Verbraucher als Verbrauch gewertet."},
    ],
}

# Live-Felder auf Anlage-Ebene (kein Investment-Bezug).
#
# `bedarf`/`bedarf_gruppe` steuern die Zuordnungs-Fläche (Datenquellen-V4):
# „pflicht" wird rot und aufgeklappt gezeigt, solange weder das Feld selbst noch
# ein anderes Mitglied seiner `bedarf_gruppe` eine Quelle hat; „optional" bleibt
# leise grau und zählt nicht als offener Punkt. Live-Felder sind durchweg
# optional — ohne sie bleibt nur das Live-Dashboard leer, die Statistik läuft
# über die kWh-Zählerstände weiter.
BASIS_LIVE_FELDER: list[dict] = [
    {"key": "einspeisung_w",       "label": "Einspeisung",              "einheit": "W",
     "hinweis": "Momentane Einspeiseleistung in W — nur für das Live-Dashboard. "
                "Alternative: ein einzelner Sensor mit Vorzeichen unter „Netz kombiniert (±)“."},
    {"key": "netzbezug_w",         "label": "Netzbezug",                "einheit": "W",
     "hinweis": "Momentane Bezugsleistung in W — nur für das Live-Dashboard. "
                "Alternative: ein einzelner Sensor mit Vorzeichen unter „Netz kombiniert (±)“."},
    {"key": "netz_kombi_w",        "label": "Netz kombiniert (±)",      "einheit": "W",
     "hinweis": "EIN vorzeichenbehafteter Netz-Sensor (+ Bezug / − Einspeisung) statt zweier "
                "getrennter. Wirkt nur, wenn „Einspeisung (W)“ und „Netzbezug (W)“ beide auf "
                "„keine“ stehen — sonst haben die getrennten Felder Vorrang. Zeigt der Sensor "
                "in die falsche Richtung, dreht ihn das ⇅-Symbol am Wert."},
    {"key": "pv_gesamt_w",         "label": "PV gesamt",                "einheit": "W",
     "hinweis": "Momentane PV-Leistung der ganzen Anlage in W. Nur nötig, wenn die PV-Module "
                "keine eigenen Leistungs-Sensoren haben — sobald dort einer zugeordnet ist, "
                "wird diese Angabe ignoriert."},
    {"key": "aussentemperatur_c",  "label": "Außentemperatur",          "einheit": "°C",
     "hinweis": "Außentemperatur in °C für Live-Anzeige und Wärmepumpen-Kontext. Optional — "
                "fehlt sie, nutzt eedc die Wetterdaten des Standorts."},
    # SFML- und Solcast-Sensoren werden per Auto-Discovery erkannt (prognose_discovery.py),
    # kein manuelles Mapping mehr nötig.
]

# Preis-Felder auf Anlage-Ebene — weder Zähler noch Live-Leistung.
#
# Eigene Familie, weil ein Preis an drei Stellen anders behandelt wird als die
# übrigen Basis-Felder:
#   1. **Kein MQTT.** Der Wert wird ausschließlich als HA-Sensor gelesen
#      (stündlicher LTS-Mittelwert, `energie_profil/_helpers.py`). Deshalb steht
#      er NICHT in `BASIS_ENERGY_TOPICS` — dort wäre er ein erwartetes
#      MQTT-Topic, das niemand bedient, und der Abdeckungs-Check (#134) würde
#      ihn als Lücke melden.
#   2. **Kein Zähler.** `state_class: measurement` ist hier richtig; der
#      LTS-Summen-Check ist nicht zuständig (`daten_checker/sensoren.py`).
#   3. **Nur bei dynamischem Tarif sichtbar.** Bei einem Festpreis gehört der
#      Preis in die Stammdaten, nicht an einen Sensor — und ein angebotener
#      Preis-Slot verleitet genau dazu (Forum simon42 #89667/54, MartyBr hatte
#      seinen Festpreis-Template-Sensor mangels Alternative an den
#      Speicher-Ø-Ladepreis gehängt).
#
# Der Slot existierte bis v3 im Sensor-Mapping-Wizard („Basis-Sensoren") und ist
# beim V4-Umbau ersatzlos entfallen — das Backend las `basis.strompreis` weiter,
# nur setzen konnte man ihn nicht mehr. Bestehende v3-Zuordnungen waren davon
# nie betroffen.
BASIS_PREIS_FELDER: list[dict] = [
    {"key": "strompreis", "label": "Strompreis (dynamischer Tarif)", "einheit": "ct/kWh",
     "bedingung_basis": "dynamischer_tarif",
     "hinweis": "HA-Sensor mit dem aktuellen Arbeitspreis (Tibber, aWATTar, EPEX-Endpreis). "
                "eedc schreibt daraus die Stundenpreise mit und rechnet damit den "
                "verbrauchsgewichteten Ø-Bezugspreis des Monats sowie den Ø-Ladepreis der "
                "Speicher-Netzladung. Einheit ct/kWh oder €/kWh — eedc rechnet um. "
                "Ohne Sensor bleibt der Arbeitspreis aus den Stammdaten maßgeblich."},
]

# =============================================================================
# Bedarf je Feld — steuert die Zuordnungs-Fläche (Datenquellen-V4)
#
# EINE Tabelle statt eines Attributs an ~40 verstreuten Feld-Dicts: die
# Einstufung ist eine fachliche Festlegung und muss an einer Stelle prüfbar
# bleiben. Die Feld-TEXTE (`hinweis`) stehen weiter beim Feld — Text beschreibt,
# diese Tabelle bewertet.
#
#   "pflicht"  — ohne diesen Wert fehlt eine Kernauswertung. Die Fläche zeigt
#                das Feld rot und mit aufgeklapptem Hinweis, solange weder es
#                selbst noch ein Mitglied seiner `gruppe` eine Quelle hat.
#   "optional" — leise grau, zählt nie als offener Punkt.
#
# `gruppe` = Alternativ-Gruppe: EINE belegte Quelle in der Gruppe genügt, die
# übrigen Mitglieder gelten dann als abgedeckt (nicht als Lücke). Das löst die
# Konstellationen auf, in denen zwei Erfassungswege einander ausschließen:
#   pv_energie — Anlagen-Zählerstand ODER Zähler je PV-Modul/Balkonkraftwerk
#   pv_live    — Anlagen-Leistung ODER Leistung je Modul
#   netz_live  — „Netz kombiniert (±)" ODER Einspeisung+Netzbezug getrennt
#
# WICHTIG — „keine Quelle" ist kein Fehler: alle kWh-Felder lassen sich im
# Monatsabschluss auch manuell erfassen. Rot heißt deshalb „hier fehlt noch
# etwas", nie „falsch"; die Hinweistexte nennen die manuelle Alternative.
# =============================================================================

FELD_BEDARF: dict[tuple[str, str], tuple[str, Optional[str]]] = {
    # ── Anlage (Basis) ──────────────────────────────────────────────────────
    # Kernwerte laut Daten-Checker (`daten_checker/monatsdaten.py`: „Kernfeld —
    # ohne Einspeisung sind Eigenverbrauch und Autarkie nicht berechenbar").
    ("basis", "einspeisung_kwh"): ("pflicht", None),
    ("basis", "netzbezug_kwh"): ("pflicht", None),
    ("basis", "pv_gesamt_kwh"): ("pflicht", "pv_energie"),
    # Live-Felder sind durchweg optional: ohne sie bleibt das Live-Dashboard
    # leer, die Statistik läuft über die kWh-Zählerstände weiter.
    ("basis", "einspeisung_w"): ("optional", "netz_live"),
    ("basis", "netzbezug_w"): ("optional", "netz_live"),
    ("basis", "netz_kombi_w"): ("optional", "netz_live"),
    ("basis", "pv_gesamt_w"): ("optional", "pv_live"),
    ("basis", "aussentemperatur_c"): ("optional", None),

    # ── PV ──────────────────────────────────────────────────────────────────
    ("pv-module", "pv_erzeugung_kwh"): ("pflicht", "pv_energie"),
    ("pv-module", "leistung_w"): ("optional", "pv_live"),
    # ⛔ Kein PV-Erzeuger mehr (Gernot 24.08.2026) — und DIESE Zeile war der
    # eigentliche Schaden: als Mitglied der Gruppe `pv_energie` hat ein hier
    # belegtes Feld `basis:pv_gesamt` UND das Modul-Feld auf „bereits an
    # anderer Stelle zugeordnet" gesetzt, waehrend es selbst nirgends gelesen
    # wurde. Drei Quellen inaktiv, keine wirksam (#388/F-57). `("optional",
    # None)` statt Streichung: der Eintrag traegt die Begruendung, und ein
    # fehlender Schluessel faellt still auf FELD_BEDARF_DEFAULT zurueck.
    ("wechselrichter", "pv_erzeugung_kwh"): ("optional", None),
    ("wechselrichter", "leistung_w"): ("optional", "pv_live"),
    ("balkonkraftwerk", "pv_erzeugung_kwh"): ("pflicht", "pv_energie"),
    ("balkonkraftwerk", "leistung_w"): ("optional", "pv_live"),
    ("balkonkraftwerk", "eigenverbrauch_kwh"): ("optional", None),
    ("balkonkraftwerk", "speicher_ladung_kwh"): ("optional", None),
    ("balkonkraftwerk", "speicher_entladung_kwh"): ("optional", None),

    # ── Speicher ────────────────────────────────────────────────────────────
    # Ohne Lade-/Entlademenge bleibt die gesamte Speicher-Auswertung leer und
    # der Hausverbrauch wird falsch gerechnet (Daten-Checker warnt darauf).
    ("speicher", "ladung_kwh"): ("pflicht", None),
    ("speicher", "entladung_kwh"): ("pflicht", None),
    ("speicher", "ladung_netz_kwh"): ("optional", None),
    ("speicher", "speicher_ladepreis_cent"): ("optional", None),
    ("speicher", "leistung_w"): ("optional", None),
    ("speicher", "soc"): ("optional", None),

    # ── Wärmepumpe ──────────────────────────────────────────────────────────
    # Strom UND abgegebene Wärme: erst beide zusammen ergeben JAZ, Ersparnis
    # und CO₂. Der Strom kommt je nach Parameter aus einem oder zwei Feldern.
    ("waermepumpe", "stromverbrauch_kwh"): ("pflicht", "wp_strom"),
    ("waermepumpe", "strom_heizen_kwh"): ("pflicht", "wp_strom"),
    ("waermepumpe", "strom_warmwasser_kwh"): ("pflicht", "wp_strom"),
    # Ausnahme Split-Klimaanlage: s. KLIMA_OHNE_WAERMEMENGE unter der Tabelle.
    ("waermepumpe", "heizenergie_kwh"): ("pflicht", None),
    ("waermepumpe", "warmwasser_kwh"): ("optional", None),
    ("waermepumpe", "leistung_w"): ("optional", None),
    ("waermepumpe", "leistung_heizen_w"): ("optional", None),
    ("waermepumpe", "leistung_warmwasser_w"): ("optional", None),
    ("waermepumpe", "leistung_kuehlen_w"): ("optional", None),
    ("waermepumpe", "warmwasser_temperatur_c"): ("optional", None),
    # #263 K-2 (Konzept §7 E-E): JEDER Wärmepumpe angeboten, nicht nur
    # `wp_art = luft_luft`. Der Grund ist gemessen, nicht vorsorglich:
    # azywietz-webs zwei Klimaanlagen laufen als `luft_wasser`, weil das Feld
    # „Wärmepumpenart" als Community-Einstellung beschriftet war — wer nur
    # `luft_luft` bedient, baut an genau der Gruppe vorbei, die das Thema
    # meldet. Es gibt außerdem Luft-Wasser-Wärmepumpen MIT Kühlfunktion.
    # „optional": wer keinen Modus-Sensor zuordnet, merkt nichts.
    ("waermepumpe", "betriebsmodus"): ("optional", None),

    # ── E-Auto ──────────────────────────────────────────────────────────────
    # Kilometer sind der Bezugswert für Effizienz und Benzin-Vergleich.
    # Die Heimladungs-Felder sind bei vorhandener Wallbox verdrängt
    # (`bedingung_anlage: keine_wallbox`) — das wertet die Fläche selbst aus.
    ("e-auto", "km_gefahren"): ("pflicht", None),
    ("e-auto", "verbrauch_kwh"): ("optional", None),
    ("e-auto", "ladung_pv_kwh"): ("optional", None),
    ("e-auto", "ladung_netz_kwh"): ("optional", None),
    ("e-auto", "ladung_extern_kwh"): ("optional", None),
    ("e-auto", "ladung_extern_euro"): ("optional", None),
    ("e-auto", "v2h_entladung_kwh"): ("optional", None),
    ("e-auto", "leistung_w"): ("optional", None),
    ("e-auto", "soc"): ("optional", None),

    # ── Wallbox ─────────────────────────────────────────────────────────────
    ("wallbox", "ladung_kwh"): ("pflicht", None),
    ("wallbox", "ladung_pv_kwh"): ("optional", None),
    ("wallbox", "ladevorgaenge"): ("optional", None),
    ("wallbox", "leistung_w"): ("optional", None),
}

# Default für alles, was nicht in der Tabelle steht (u. a. „sonstiges", dessen
# Felder kategorie-abhängig erzeugt werden): nie rot, nie als Lücke gezählt.
FELD_BEDARF_DEFAULT: tuple[str, Optional[str]] = ("optional", None)

# Felder, deren Pflicht bei einer Split-Klimaanlage (`wp_art="luft_luft"`) entfällt.
#
# Die Tabelle oben kennt nur (typ, feld) — für die Wärmepumpe reicht das nicht: eine
# Split-Klimaanlage hat weder Wärmemengenzähler noch Warmwasserkreis. Genau deshalb
# stellt der Daten-Checker die „Heizwärme fehlt"-Forderung dort seit K-0 NICHT mehr
# (`daten_checker/monatsdaten.py::_check_wp_monatsdaten`, Begründung dort:
# „Dauer-Falschpositiv"). Die Zuordnungs-Fläche stellte sie weiter — dieselbe Anlage,
# zwei Flächen, gegenteilige Aussage: der Checker schwieg, *Einstellungen →
# Datenquellen* zeigte „Heizwärme" rot, aufgeklappt und zählte sie als offene Pflicht
# (Fund N-86; Melder mit Klimaanlage: dietmar1968 #89667/87, kingcap1 #263).
#
# „optional" und nicht „inaktiv": inaktiv heißt „ein anderer Weg gewinnt"
# (Alternativ-Gruppe belegt, verdrängendes Gerät) — hier gewinnt kein anderer Weg,
# die Größe existiert an diesem Gerät schlicht nicht. Wer doch einen
# Wärmemengenzähler an seiner Klimaanlage hat, ordnet ihn weiterhin zu.
#
# `warmwasser_kwh` steht bewusst nicht hier: es ist ohnehin schon „optional".
KLIMA_OHNE_WAERMEMENGE: frozenset[tuple[str, str]] = frozenset({
    ("waermepumpe", "heizenergie_kwh"),
})


def get_feld_bedarf(
    typ: str, feld: str, parameter: Optional[dict] = None,
) -> tuple[str, Optional[str]]:
    """Bedarf + Alternativ-Gruppe eines Felds — siehe {@link FELD_BEDARF}.

    `parameter` ist das `Investition.parameter`-Dict des Geräts (auf Anlagen-Ebene
    None). Ohne es bleibt die reine (typ, feld)-Einstufung — Aufrufer, die keinen
    Geräte-Kontext haben, müssen nichts wissen.
    """
    # #263 — je-Innengerät-Keys erben die Einstufung ihres Basis-Felds.
    feld = basis_feld_key(feld)
    bedarf = FELD_BEDARF.get((typ, feld), FELD_BEDARF_DEFAULT)
    if (typ, feld) in KLIMA_OHNE_WAERMEMENGE and ist_luft_luft_waermepumpe(parameter):
        return ("optional", bedarf[1])
    return bedarf


# Typen mit SoC-Live-Sensor (aus LIVE_FELDER_INV abgeleitet)
SOC_TYPEN: frozenset[str] = frozenset(
    typ for typ, felder in LIVE_FELDER_INV.items()
    if any(f["key"] == "soc" for f in felder)
)


# Live-Felder, deren Wert ein ZUSTAND ist statt einer Zahl (#263 K-2).
#
# **Warum diese Menge existiert und nicht drei verstreute Ausnahmen.** Der
# gesamte Live-Pfad ist numerisch, und zwar an drei Stellen unabhängig
# voneinander:
#
#   1. `live_power_service._states_zu_w` → `normalize_to_w(float(state))` — läuft
#      über JEDE Live-Zuordnung, alle 5 Sekunden. Ein `climate`-State ergibt dort
#      garantiert `None`; es wäre ein Dauerabruf ohne Ergebnis.
#   2. `mqtt_inbound_service` → `float(payload)`. Ein Modus über MQTT ist damit
#      nicht empfangbar — also wird er auch nicht als Topic **angeboten**, statt
#      dem Anwender eine Quelle hinzustellen, die nichts liefert (die P-6-Falle:
#      ein Hinweis bzw. hier ein Angebot, das niemand einlösen kann).
#   3. `daten_checker/sensoren.py` prüft Einheiten (kW≠kWh) — ein Feld ohne
#      Einheit hat dort nichts zu suchen.
#
# Statt an jeder dieser Stellen `if key == "betriebsmodus"` zu schreiben, steht
# die Eigenschaft **am Feld** und wird von hier gelesen. Ein zweites
# Zustandsfeld erbt damit alle drei Weichen, ohne dass jemand sie sucht.
#
# ⚠ Die Umkehrung gilt ausdrücklich: was hier NICHT steht, ist eine Zahl. Wer
# ein Feld ohne `einheit` einträgt, hat damit noch kein Zustandsfeld gebaut.
ZUSTAND_LIVE_FELDER: frozenset[tuple[str, str]] = frozenset(
    (typ, f["key"])
    for typ, felder in LIVE_FELDER_INV.items()
    for f in felder
    if f.get("zustand")
)

# Nur die Feld-Keys — für die Pfade, die ihren Investitionstyp nicht kennen
# (der Live-Poller sieht `{inv_id: {key: entity}}` ohne Typ-Kontext).
ZUSTAND_FELD_KEYS: frozenset[str] = frozenset(key for _, key in ZUSTAND_LIVE_FELDER)


def einheit_fuer(feld: str, investition=None) -> str:
    """Die Einheit, die neben diesem Wert stehen soll — **der eine Leser** (#377).

    Für fast jedes Feld steht sie fest in der Registry (`FELD_EINHEITEN`). Für
    den **Zählerstand** nicht: Er ist einheitenlos gespeichert, und was daneben
    steht (m³, l, kg, t, kWh), hängt am **Gerät** — ein Haushalt kann einen
    Gaszähler in m³ und einen Wasserzähler in m³ und einen Öltank in Litern
    führen.

    **Warum die Eigenschaft am Feld steht und nicht als `if feld ==`:**
    dieselbe Bauform wie `ZUSTAND_LIVE_FELDER`/`ist_zustand_feld` (#263 K-2) —
    *Eigenschaft am Feld, abgeleitete Menge, ein Leser*. Ein zweites Feld mit
    geräteabhängiger Einheit kostet damit einen Registry-Eintrag
    (`einheit_je_geraet: "<param>"`) und keine neue Verzweigung.

    ⚠ **Die Einheit ist Anzeige, nie Rechnung.** eedc rechnet Zählerstände
    grundsätzlich nicht um. Wer sein Gerät von m³ auf kWh umstellt, ändert das
    Wort neben der Zahl — die Zahl bleibt, wie der Zähler sie meldet.
    """
    # #263 — je-Innengerät-Keys tragen die Einheit ihres Basis-Felds.
    feld = basis_feld_key(feld)
    param_key = FELD_EINHEIT_JE_GERAET.get(feld)
    if param_key:
        if investition is not None:
            wert = (getattr(investition, "parameter", None) or {}).get(param_key)
            if wert:
                return str(wert)
        # Gerät ohne gepflegte Einheit: der Registry-Default gilt. Lokaler
        # Import, weil `investition_parameter` die Defaults führt und ein
        # Top-Level-Import dieses Basis-Modul an es binden würde.
        from backend.core.investition_parameter import PARAM_SONSTIGES_DEFAULTS

        standard = PARAM_SONSTIGES_DEFAULTS.get(param_key)
        if standard:
            return str(standard)
    return FELD_EINHEITEN.get(feld, "")


def ist_zustand_feld(feld: str, typ: Optional[str] = None) -> bool:
    """Ist dieses Live-Feld ein Zustand statt einer Zahl? — siehe {@link ZUSTAND_LIVE_FELDER}.

    `typ` schärft die Antwort, wo der Aufrufer ihn hat; ohne ihn gilt der
    Feld-Key allein. Beides ist gewollt: die Zuordnungs-Fläche kennt den Typ,
    der Live-Poller nicht.
    """
    # #263: Der Key kann eine Innengeräte-Adresse tragen
    # (`betriebsmodus-3`). Die Zustands-Eigenschaft hängt am Feld, nicht am
    # Innengerät — ohne Auflösung liefe eine `climate`-Entität in den
    # 5-Sekunden-Poller und in ein MQTT-Topic, das `float(payload)` nie
    # annehmen kann.
    basis = basis_feld_key(feld)
    if typ is not None:
        return (typ, basis) in ZUSTAND_LIVE_FELDER
    return basis in ZUSTAND_FELD_KEYS


# =============================================================================
# Alte Feldnamen → neue kanonische Namen (für Lese-Kompatibilität mit alten DB-Einträgen)
LEGACY_FELDNAMEN: dict[str, str] = {
    "speicher_ladung_netz_kwh": "ladung_netz_kwh",   # Speicher Arbitrage
    "entladung_v2h_kwh":        "v2h_entladung_kwh", # E-Auto V2H
}

# Summen-Keys die _import_investition_monatsdaten_v09 zurückgibt
IMPORT_SUMMEN_KEYS = ("pv_erzeugung_sum", "batterie_ladung_sum", "batterie_entladung_sum")


# =============================================================================
# Hilfsfunktionen
# =============================================================================

def get_feld_hinweise() -> dict[str, dict[str, str]]:
    """Liefert die Feld-Hilfetexte als ``{kontext: {schluessel: hinweis}}``.

    Single Source of Truth für alle Hilfetexte (Sensor-Zuordnungs-Wizard,
    künftiger MQTT-Inbound-Wizard, manuelle Monatsdaten-Eingabe). Speist sich
    ausschließlich aus den ``hinweis``-Attributen der Felddefinitionen.

    Kontext-Schlüssel:
      - ``"basis"``            → keyed by ``mapping_key`` (so adressiert der
                                 BasisSensorenStep, z. B. ``"einspeisung"``)
      - Investitionstyp        → keyed by ``feld`` (z. B. ``"e-auto"``)
      - ``"sonstiges:<kat>"``  → keyed by ``feld``, je Sonstiges-Kategorie
                                 (Feldname allein ist mehrdeutig: Verbraucher
                                 vs. Speicher)
    """
    result: dict[str, dict[str, str]] = {}

    basis: dict[str, str] = {}
    for e in (*BASIS_FELDER, *BEDINGTE_BASIS_FELDER):
        mk, hinweis = e.get("mapping_key"), e.get("hinweis")
        if mk and hinweis:
            basis[mk] = hinweis
    result["basis"] = basis

    for typ, val in INVESTITION_FELDER.items():
        if isinstance(val, dict):  # sonstiges → nach Kategorie aufgeschlüsselt
            for kat, felder in val.items():
                result[f"sonstiges:{kat}"] = {
                    e["feld"]: e["hinweis"] for e in felder if e.get("hinweis")
                }
        else:
            result[typ] = {e["feld"]: e["hinweis"] for e in val if e.get("hinweis")}

    return result


# =============================================================================
# Feld-Keys je Innengerät (#263)
#
# **Ein Feld-Key kann eine Adresse tragen.** `modus`-, Verbrauchs- und
# Live-Felder einer Split-Klimaanlage gibt es einmal je Innengerät; der Key
# trägt dafür die **vergebene ID** des Innengeräts als Suffix:
#
#     betriebsart_strom_kuehlen_kwh-3      soll_temperatur_c-3
#
# ⚠ **Warum die ID und nicht die Position.** `sensor_mapping` speichert nach
# Key. Eine Positionsnummer verschöbe beim Löschen des mittleren von drei
# Geräten alle folgenden Zuordnungen — jede zeigte danach auf den falschen
# Raum, ohne dass jemand etwas angefasst hätte.
#
# ⚠ **Und warum es EINEN Auflöser gibt.** Quer durchs Backend entscheiden
# Namens-Whitelists über das Verhalten eines Feldes: `ist_zustand_feld`
# (kommt es in den 5-Sekunden-Poller?), `_is_kumulativ_feld` (wird es
# gesnapshottet?), `FELD_EINHEITEN` (welche Einheit?), `get_feld_bedarf`
# (rot oder grau?). Alle vergleichen den **ganzen** Key. Ohne Auflösung fiele
# `betriebsart_strom_kuehlen_kwh-3` durch jede einzelne — und zwar still: das
# Feld wäre zuordenbar und würde nirgends ankommen. Deshalb löst **jeder**
# dieser Leser über `basis_feld_key` auf, statt an vier Stellen ein Suffix zu
# kennen.
#
# Der Trenner ist `-`, und das ist sicher: kein einziger der 53 Feld-Keys der
# Registry enthält einen Bindestrich (Proben in
# `test_263_innengeraete_feld_keys.py`).

INNENGERAET_TRENNER: Final[str] = "-"


def feld_je_innengeraet(basis_feld: str, innengeraet_id: int) -> str:
    """Feld-Key für ein bestimmtes Innengerät — der eine Erzeuger."""
    return f"{basis_feld}{INNENGERAET_TRENNER}{int(innengeraet_id)}"


def basis_feld_key(feld: str) -> str:
    """Der Feld-Key ohne Innengeräte-Suffix — siehe Kasten oben.

    ``betriebsart_strom_kuehlen_kwh-3`` → ``betriebsart_strom_kuehlen_kwh``.
    Ein Key ohne Suffix kommt unverändert zurück; die Funktion ist damit
    überall einsetzbar, wo heute der rohe Key steht.
    """
    if not feld:
        return feld
    kopf, trenner, rest = feld.rpartition(INNENGERAET_TRENNER)
    if trenner and kopf and rest.isdigit():
        return kopf
    return feld


def innengeraet_id_von_feld(feld: str) -> Optional[int]:
    """Die Innengeräte-ID eines Feld-Keys, oder ``None`` ohne Suffix."""
    if not feld:
        return None
    kopf, trenner, rest = feld.rpartition(INNENGERAET_TRENNER)
    if trenner and kopf and rest.isdigit():
        return int(rest)
    return None


#: Felder, die es **je Innengerät** gibt, sobald eine Innengeräte-Liste
#: gepflegt ist. Abgeleitet: alles, was `bedingung: "luft_luft"` trägt.
#: Der Betriebsmodus steht bewusst NICHT dabei — er gehört dem Außengerät,
#: bleibt ein Signal je Gerät, und die abgeleitete Aufteilung ändert sich
#: durch die Liste nicht (Konzept-Fassung 2026-08-21).
def _je_innengeraet_keys(felder: list[dict], key_name: str) -> set[str]:
    return {f[key_name] for f in felder if f.get("je_innengeraet")}


def _mit_innengeraeten(
    felder: list[dict], parameter: Optional[dict], key_name: str,
) -> list[dict]:
    """Hängt je Innengerät eine Kopie der Betriebsart-/Raumfelder an.

    **Das Gerätefeld bleibt stehen.** Wer den ganzen Verbrauch je Betriebsart
    an einem Zähler hat, ordnet ihn dort zu; die Liste ergänzt die
    Aufschlüsselung, sie ersetzt sie nicht. Ein Feld verschwinden zu lassen,
    sobald jemand ein Innengerät anlegt, würde eine bestehende Zuordnung
    unsichtbar machen und unlöschbar zurücklassen — dieselbe Falle, vor der
    `get_alle_felder_fuer_investition` warnt.
    """
    geraete = lade_innengeraete(parameter)
    if not geraete:
        return felder
    kandidaten = _je_innengeraet_keys(felder, key_name)
    if not kandidaten:
        return felder
    out = list(felder)
    for g in geraete:
        for feld in felder:
            if feld[key_name] not in kandidaten:
                continue
            kopie = dict(feld)
            kopie[key_name] = feld_je_innengeraet(feld[key_name], g["id"])
            kopie["label"] = (
                f"{g['bezeichnung']}: "
                f"{feld.get('label_je_innengeraet') or feld['label']}"
            )
            kopie["innengeraet_id"] = g["id"]
            kopie["innengeraet_bezeichnung"] = g["bezeichnung"]
            if kopie.get("csv_suffix"):
                kopie["csv_suffix"] = f"{kopie['csv_suffix']}_IG{g['id']}"
            out.append(kopie)
    return out


#: Bedingungs-Schlüssel, die eine **Geräteklasse** beschreiben statt eines
#: Schalters. Der Unterschied entscheidet auf der Zuordnungs-Fläche
#: (`get_alle_felder_fuer_investition`): Ein Schalter ist umlegbar, sein Feld
#: bleibt deshalb zuordenbar; eine Geräteklasse schließt die Größe aus, ihr Feld
#: verschwindet. Weiche Bedingungen sind von beidem unberührt — sie entfernen
#: nie, sie markieren (`bedingungs_urteil`).
GERAETEKLASSEN_SCHLUESSEL: Final[frozenset[str]] = frozenset(
    {"luft_luft", "brauchwasser"}
)


def _ist_geraeteklasse(bedingung) -> bool:
    """Trägt `bedingung` einen Geräteklassen-Schlüssel? (auch negiert, auch in Liste)"""
    if not bedingung:
        return False
    tokens = (bedingung,) if isinstance(bedingung, str) else tuple(bedingung)
    return any(t.lstrip("!") in GERAETEKLASSEN_SCHLUESSEL for t in tokens)


def _bedingungs_werte(parameter: Optional[dict]) -> dict[str, bool]:
    """Die Bedingungs-Keys einer Investition — eine Auswertung für alle Feld-Wege.

    Dieselben Keys steuern `bedingung` (Feld zeigen?) und `label_wenn` (wie heißt
    es dann?). Beide Wege lesen sie hier, damit die Zuordnungs-Fläche kein zweites,
    abweichendes Bild bekommt.
    """
    params = parameter or {}
    arbitrage_faehig = bool(params.get("arbitrage_faehig"))
    return {
        # #263: eine Betriebsart (Heizen/Kühlen/Lüften/Entfeuchten) hat nur ein
        # Klimagerät — bei der Luft-Wasser-WP heißt die Achse Heizen/Warmwasser.
        "luft_luft": ist_luft_luft_waermepumpe(params),
        # R1/A6: ein Gerät mit ausschließlich Warmwasser-Achse. Steuert die
        # WEICHE Herabstufung von Heizen — nie deren Entfernung.
        "brauchwasser": ist_brauchwasser_waermepumpe(params),
        "getrennte_strommessung": bool(params.get("getrennte_strommessung")),
        "arbitrage_faehig": arbitrage_faehig,
        # Arbitrage impliziert Netzladung — das Flag ist nur ein Erfassungs-Schalter,
        # die UI für `ladung_netz_kwh` muss auch ohne Arbitrage sichtbar sein können.
        "laedt_aus_netz": bool(params.get("laedt_aus_netz")) or arbitrage_faehig,
        "v2h_faehig": bool(params.get("v2h_faehig") or params.get("nutzt_v2h")),
        "hat_speicher": bool(params.get("hat_speicher")),
    }


#: Die drei Ausgänge von `bedingungs_urteil`.
URTEIL_GILT: Final[str] = "gilt"
URTEIL_ERWEITERT: Final[str] = "erweitert"
URTEIL_NEIN: Final[str] = "nein"


#: `bedingung_anlage` → der Investitionstyp, dessen Vorhandensein das Feld
#: verdrängt. **Der eine Ort dieser Zuordnung** (N-79).
#:
#: ⚠ Bis 2026-08-29 stand dieselbe Abbildung **zweimal** fest verdrahtet: hier
#: als `if`-Kette in `get_felder_fuer_investition` und als `_VERDRAENGT_TYP` in
#: `services/datenquellen_validierung.py`. Beide Kopien waren wertgleich — und
#: genau das ist die Falle: Ein dritter Wert, nur in eine der beiden Kopien
#: eingetragen, verdrängt das Feld auf der Datenquellen-Fläche, aber nicht im
#: Monatsabschluss (oder umgekehrt), und zwar **still**.
#:
#: ⚑ `bedingung` und `weich` hatten ihren Auswerter längst (`bedingungs_urteil`),
#: `label_wenn` wird an genau einer Stelle gelesen — `bedingung_anlage` war der
#: einzige Schlüssel der Registry ohne SoT.
BEDINGUNG_ANLAGE_VERDRAENGT: Final[dict[str, str]] = {
    "keine_wallbox": "wallbox",
    # Von keinem Feld mehr benutzt (s. Kasten bei `ladung_pv_kwh`: die Bedingung
    # ist 2026 bewusst entfallen) — der Wert bleibt im Vokabular, damit die
    # Regel wieder gesetzt werden kann, ohne sie neu herzuleiten.
    "keine_pv_module": "pv-module",
}


def verdraengender_typ(bedingung_anlage) -> Optional[str]:
    """Welcher Investitionstyp verdrängt ein Feld mit dieser `bedingung_anlage`?

    Gibt den Typ zurück (`"wallbox"`), oder `None`, wenn das Feld keine solche
    Bedingung trägt **oder der Wert unbekannt ist**.

    ⚠ **Ein unbekannter Wert verdrängt nicht** (fail-open) — dieselbe Wahl wie
    in `bedingung_erfuellt` und `bedingungs_urteil`, und aus demselben Grund:
    Die Gegenrichtung ließe ein bereits **zugeordnetes** Feld unsichtbar
    verschwinden und damit unlöschbar zurückbleiben. Ein Auswerter, der wirft,
    wäre die F-59-Klasse (latenter 500er im Lesepfad).

    Gegen den Tippfehler steht deshalb ein Wächter, kein Laufzeitfehler:
    ``test_bedingung_anlage_sot_n79.py::test_jeder_bedingung_anlage_wert_ist_bekannt``.
    """
    if not bedingung_anlage:
        return None
    return BEDINGUNG_ANLAGE_VERDRAENGT.get(bedingung_anlage)


def bedingungs_urteil(
    bedingung, weich, bedingungs_werte: dict[str, bool],
) -> str:
    """Gilt das Feld, ist es **erweitert**, oder gibt es die Größe hier nicht?

    ⭐ **Es gibt zwei Sorten Bauart-Abhängigkeit, und bis zum 26.08.2026 waren
    sie derselbe Mechanismus** — das ist die Ursache hinter Befund W-2:

    ======  ====================================  ==========================
    Sorte   Beispiel                              Folge
    ======  ====================================  ==========================
    hart    Luft-Luft hat keinen Warmwasserkreis  Feld verschwindet
    weich   Sole-Wasser-WP **mit** Kühlung        Feld ist „erweitert"
    ======  ====================================  ==========================

    MartyBr hat seit dem Sommer 2026 einen getrennten Kühlzähler an einer
    Wärmepumpe und konnte ihn **nirgends** hinterlegen; pipp086 fragt nach
    derselben Größe (Forum T89667 #199/#200). Die alte Begründung — „acht
    Betriebsart-Felder an jeder Wärmepumpe sind acht Angebote, die niemand
    einlösen kann" — bleibt richtig und wird hier eingelöst, **ohne** einen
    Fall auszuschließen: erweiterte Felder stehen auf der Zuordnungs-Fläche
    hinter einem Schritt „Weitere Größen erfassen".

    ⚠ **Hart schlägt weich.** Ein Feld kann beides tragen — `strom_heizen_kwh`
    braucht `getrennte_strommessung` **hart** (ohne Kennzeichen gibt es die
    getrennte Achse nicht) und `!brauchwasser` **weich** (an einer
    Brauchwasser-WP untypisch, aber möglich). Genau diese Kombination ist der
    Grund, warum `weich` die **Schlüssel** nennt und kein Wahrheitswert am Feld
    ist: mit einem Bool ließe sich nicht sagen, *welche* der beiden Bedingungen
    weich gemeint war.

    ⚠ **Ein unbekannter Schlüssel gilt** (fail-open) — wie in
    `bedingung_erfuellt`, und aus demselben Grund: ein Tippfehler ließe sonst
    ein **zugeordnetes** Feld unsichtbar verschwinden und damit unlöschbar
    zurückbleiben. Gewächtert wird der Tippfehler, nicht abgefangen
    (`test_b5_strom_warmwasser_luft_luft.py::
    test_jede_bedingung_der_registry_ist_ein_bekannter_schluessel`).
    """
    if not bedingung:
        return URTEIL_GILT
    weiche_schluessel = frozenset(weich or ())
    tokens = (bedingung,) if isinstance(bedingung, str) else tuple(bedingung)
    urteil = URTEIL_GILT
    for token in tokens:
        negiert = token.startswith("!")
        schluessel = token[1:] if negiert else token
        if schluessel not in bedingungs_werte:
            continue  # unbekannt → nicht filtern, s. Kasten oben
        if bedingungs_werte[schluessel] == negiert:
            if schluessel not in weiche_schluessel:
                return URTEIL_NEIN  # hart schlägt weich, sofort
            urteil = URTEIL_ERWEITERT
    return urteil


def bedingung_erfuellt(bedingung, bedingungs_werte: dict[str, bool]) -> bool:
    """Ist die `bedingung` eines Feldes erfüllt? — **der eine Auswerter**.

    ⚠ **Kennt die weiche Sorte NICHT** und beantwortet deshalb nur die harte
    Frage. Wer wissen muss, ob ein Feld „erweitert" ist, ruft
    `bedingungs_urteil`; die Aufrufer hier brauchen die Unterscheidung nicht
    (sie fragen „ist diese eine Bedingung erfüllt?", nicht „zeige ich das
    Feld?").

    Eine Bedingung ist ein Schlüssel aus `_bedingungs_werte`, optional mit `!`
    negiert. **Mehrere Bedingungen stehen als Liste und gelten alle zusammen
    (UND)** — genau das braucht `strom_warmwasser_kwh` (B5/N-304): getrennte
    Strommessung ja, Split-Klimaanlage nein. Vorher war die Auswertung eine
    Kette aus `elif bedingung == "…"`; sie konnte eine Bedingung ausdrücken und
    keine zwei, und jeder neue Schlüssel kostete dort einen Zweig.

    ⚠ **Ein unbekannter Schlüssel zeigt das Feld** (fail-open) — bitgleich zum
    früheren Verhalten, wo eine unbekannte Zeichenkette durch alle `elif` fiel.
    Die Gegenrichtung wäre schlimmer: ein Tippfehler ließe ein **zugeordnetes**
    Feld unsichtbar verschwinden, und damit unlöschbar zurückbleiben (dieselbe
    Falle, vor der `get_alle_felder_fuer_investition` warnt). Ein Auswerter, der
    stattdessen wirft, wäre die F-59-Klasse: ein latenter 500er im Lesepfad.
    Gegen den Tippfehler steht deshalb ein Wächter, kein Laufzeitfehler —
    `test_b5_strom_warmwasser_luft_luft.py::
    test_jede_bedingung_der_registry_ist_ein_bekannter_schluessel`.
    """
    if not bedingung:
        return True
    tokens = (bedingung,) if isinstance(bedingung, str) else tuple(bedingung)
    for token in tokens:
        negiert = token.startswith("!")
        schluessel = token[1:] if negiert else token
        if schluessel not in bedingungs_werte:
            continue  # unbekannt → nicht filtern, s. Kasten oben
        if bedingungs_werte[schluessel] == negiert:
            return False
    return True


def _label_aufgeloest(feld: dict, bedingungs_werte: dict[str, bool]) -> str:
    """#281: konditionelles Label — nutzt dieselben Bedingungs-Keys wie `bedingung`."""
    for cond_key, alt_label in (feld.get("label_wenn") or {}).items():
        if bedingungs_werte.get(cond_key):
            return alt_label
    return feld["label"]


def get_felder_fuer_investition(
    typ: str,
    parameter: Optional[dict],
    anlage_investitionen: Optional[list] = None,
    belegte_felder: Optional[set[str]] = None,
) -> list[dict]:
    """
    Gibt die relevanten Felder für eine Investition zurück (Bedingungen aufgelöst).

    Filtert konditionelle Felder basierend auf:
    - Investitions-Parametern ("bedingung", z.B. "arbitrage_faehig")
    - Anlage-Kontext ("bedingung_anlage", z.B. "keine_pv_module")

    Für Typ "sonstiges" bitte get_felder_fuer_sonstiges() verwenden.

    Args:
        typ: Investitionstyp (z.B. "speicher", "e-auto")
        parameter: Investitions-Parameter-Dict (inv.parameter)
        anlage_investitionen: Alle Investitionen der Anlage (für bedingung_anlage).
                              None → bedingung_anlage wird nicht ausgewertet.
        belegte_felder: Feldnamen, für die es an diesem Gerät bereits einen Wert
                        oder eine Zuordnung gibt. Sie entscheiden über die
                        **erweiterten** Felder (R1, `weich` — s.
                        `bedingungs_urteil`): ein erweitertes Feld erscheint hier
                        nur, wenn es belegt ist.

                        ⭐ **Das ist R1 wörtlich:** *„was ein Gerät liefern kann,
                        sagt der zugeordnete Zähler, nicht seine Bauart."* Ohne
                        das Argument (Import, Checker) bleibt es beim harten
                        Bild — dort ändert sich nichts.

    Returns:
        Liste von Feld-Dicts ohne "bedingung"-Keys (bereits aufgelöst)
    """
    params = parameter or {}
    alle_felder = INVESTITION_FELDER.get(typ, [])

    if isinstance(alle_felder, dict):
        # Sonstiges — Kategorie-abhängig. Ohne gepflegte Kategorie wird hier
        # NICHT geraten (N-244); die Entscheidung liegt im SoT darunter.
        return get_felder_fuer_sonstiges(params.get("kategorie"))

    # Anlage-Kontext vorberechnen (einmalig, nicht pro Feld)
    anlage_typen: set[str] = set()
    if anlage_investitionen is not None:
        anlage_typen = {getattr(i, "typ", None) for i in anlage_investitionen}

    result = []
    bedingungs_werte = _bedingungs_werte(params)

    # Steuer-Schlüssel — hier ausgewertet bzw. nur für die Zuordnungs-Fläche
    # relevant, gehören nicht in die Eingabe-Antwort.
    SKIP_KEYS = {"bedingung", "weich", "bedingung_anlage", "label_wenn",
                 "nur_manuell", "nur_bestand", "je_innengeraet",
                 "label_je_innengeraet"}
    belegt = belegte_felder or set()

    for feld in alle_felder:
        # ⛔ `nur_bestand`: gar nicht mehr pflegbar — siehe Kopf dieser Datei.
        # Es bleibt allein in der Registry, damit eine BESTEHENDE Zuordnung auf
        # der Zuordnungs-Flaeche sichtbar und entfernbar ist; dort entscheidet
        # `ohne_nicht_zuordenbare` ueber `nur_manuell`. Hier faellt es immer.
        if feld.get("nur_bestand"):
            continue
        bedingung = feld.get("bedingung")
        bedingung_anlage = feld.get("bedingung_anlage")

        # ── Anlage-Kontext-Bedingung ─────────────────────────────────────────
        # Hier wird gefiltert (Monatsabschluss/Import-Kontext). Die Datenquellen-
        # Fläche nutzt bewusst `get_alle_felder_fuer_investition` und wertet
        # `bedingung_anlage` selbst aus — sie muss ein bereits ZUGEORDNETES Feld
        # weiter zeigen, sonst verschwindet die Zuordnung unsichtbar und lässt
        # sich nicht mehr entfernen (`_bedarf_einstufung` in routes/datenquellen.py).
        if bedingung_anlage and anlage_investitionen is not None:
            # N-79: die Zuordnung Wert → verdrängender Typ steht im SoT
            # `BEDINGUNG_ANLAGE_VERDRAENGT`, nicht als `if`-Kette hier.
            # Unbekannter Wert ⇒ `None` ⇒ verdrängt nichts (fail-open).
            if verdraengender_typ(bedingung_anlage) in anlage_typen:
                continue  # Feld ausblenden: der verdrängende Typ ist da

        # ── Investment-Parameter-Bedingung ───────────────────────────────────
        urteil = bedingungs_urteil(bedingung, feld.get("weich"), bedingungs_werte)
        if urteil == URTEIL_NEIN:
            continue
        if urteil == URTEIL_ERWEITERT and basis_feld_key(feld["feld"]) not in belegt:
            # Erweitert und unbelegt: die Größe ist an diesem Gerät untypisch und
            # nichts deutet darauf hin, dass es sie gibt. Sie bleibt erreichbar —
            # über die Zuordnungs-Fläche, die erweiterte Felder ausdrücklich
            # zeigt. Hier stünde sie als leeres Eingabefeld in der ersten Reihe.
            continue

        aufgeloest = dict(feld)
        if urteil == URTEIL_ERWEITERT:
            aufgeloest["erweitert"] = True
        aufgeloest["label"] = _label_aufgeloest(feld, bedingungs_werte)
        result.append(aufgeloest)

    # #263 — je Innengerät eine Kopie, VOR dem Abstreifen der Steuer-Schlüssel:
    # `je_innengeraet` ist selbst einer, und ohne ihn wüsste die Erweiterung
    # nicht mehr, welche Felder sie vervielfältigen soll.
    result = _mit_innengeraeten(result, params, "feld")

    return [{k: v for k, v in f.items() if k not in SKIP_KEYS} for f in result]


def get_alle_felder_fuer_investition(typ: str, parameter: Optional[dict] = None) -> list[dict]:
    """
    Gibt ALLE Felder für einen Investitionstyp zurück — ohne Bedingungsfilter.

    Für Import-Kontext: alle Felder anbieten, unabhängig von aktuellen Parametern.
    Der Import soll nie Daten stillschweigend ignorieren. Dasselbe gilt für die
    Datenquellen-Fläche: ein bereits zugeordnetes Feld darf nicht unsichtbar
    verschwinden, sobald ein Parameter kippt.

    Das **Label** wird trotzdem an der konkreten Investition aufgelöst
    (`label_wenn`) — die Steuer-Keys (`bedingung`, `nur_manuell`, …) bleiben im
    Dict, weil die Aufrufer sie selbst auswerten. Ohne diese Auflösung hieß das
    Speicher-Feld auf der Fläche nur „Ladung", während im Monatsabschluss daneben
    „Ladung (gesamt, inkl. Netz)" stand — genau die Zweideutigkeit, an der ein
    Tester PV-Ladung und Netzladung addiert im Gesamt-Feld ablegte UND als
    Netzladung nochmal (Forum simon42 #89667/62 + /71, MartyBr).

    Args:
        typ: Investitionstyp
        parameter: Investitions-Parameter-Dict (Sonstiges-Kategorie + `label_wenn`)

    Returns:
        Liste aller Feld-Dicts (inkl. konditioneller Felder), Labels aufgelöst
    """
    alle_felder = INVESTITION_FELDER.get(typ, [])

    if isinstance(alle_felder, dict):
        # Sonstiges — Kategorie-abhängig. Ohne gepflegte Kategorie wird hier
        # NICHT geraten (N-244); die Entscheidung liegt im SoT darunter.
        params = parameter or {}
        return list(get_felder_fuer_sonstiges(params.get("kategorie")))

    # Kopie je Feld: die Dicts sind Modul-Konstanten, ein direktes Setzen des
    # Labels würde die Definition für alle folgenden Aufrufe umschreiben.
    bedingungs_werte = _bedingungs_werte(parameter)
    # ⚠ **Diese Funktion filtert NICHTS — sie markiert.** Drei Stufen, drei
    # Marken, und die Entscheidung fällt die Fläche
    # (`routes/datenquellen.py::ohne_nicht_zuordenbare`).
    #
    # Die Schalter (`getrennte_strommessung`, `arbitrage_faehig`, …) sind
    # umlegbar; bis dahin soll das Feld zuordenbar bleiben. Eine **harte**
    # Geräteklassen-Bedingung schließt die Größe dagegen aus: eine
    # Split-Klimaanlage hat keinen Warmwasserkreis, und das Feld dort anzubieten
    # wäre ein Angebot, das niemand einlösen kann (die P-6-Falle). Dazwischen
    # steht seit dem 26.08.2026 die **weiche** Bedingung: die Größe ist an
    # dieser Bauart untypisch, aber möglich — sie wird mit `erweitert` markiert,
    # die Fläche stellt sie hinter „Weitere Größen erfassen" (R1/W-2).
    #
    # ⛔ **Warum auch die harte Verletzung nur MARKIERT und nicht entfernt wird
    # — das ist der teuerste Teil dieser Funktion.** Ein Feld hier verschwinden
    # zu lassen, hieße: eine **bestehende Zuordnung** wird unsichtbar und damit
    # **unlöschbar**. Der Fall ist real und belegt: azywietz-web führt zwei
    # Klimaanlagen als `luft_wasser` (#383, weil das Feld „Wärmepumpenart" wie
    # eine Community-Einstellung beschriftet war). Stellt er sie um, hätte ein
    # zugeordneter `warmwasser_kwh`-Sensor keinen Weg mehr heraus.
    # `test_klima_ohne_warmwasser_n304.py::test_zuordnungsflaeche_zeigt_das_feld_weiter`
    # hält genau das fest — und hat am 26.08. einen ersten, zu groben Fix dieser
    # Stelle gefangen, der die Marke gegen ein `return None` getauscht hatte.
    #
    # ⛔ **Hier stand bis dahin ein exakter String-Vergleich**
    # (`f.get("bedingung") != "luft_luft"`), und der war die Ursache von **W-12**:
    # Er kannte weder die Negation `"!luft_luft"` (`warmwasser_kwh`) noch die
    # Listenform `["getrennte_strommessung", "!luft_luft"]`
    # (`strom_warmwasser_kwh`). Beide liefen daran vorbei — die Zuordnungs-Fläche
    # bot einer Split-Klimaanlage also **genau die zwei Warmwasser-Felder** an,
    # deren Fehlen der Daten-Checker bei OB73-gif zu Unrecht angemahnt hatte
    # (#263, repariert mit v4.0.28 — im Checker, nicht hier). Dritte Runde der
    # #236-Klasse: eine Regel auf einer Schicht reicht nicht bei parallelen
    # Pfaden. Der Auswerter (`bedingungs_urteil`) kennt beide Formen, und die
    # Fläche nimmt das markierte Feld heraus — **außer** es hat eine Quelle.
    # Dieselbe Bauform wie `nur_manuell`: Registry markiert, Fläche entscheidet.
    def _mit_urteil(feld: dict) -> dict:
        urteil = bedingungs_urteil(
            feld.get("bedingung"), feld.get("weich"), bedingungs_werte,
        )
        aufgeloest = {**feld, "label": _label_aufgeloest(feld, bedingungs_werte)}
        if urteil == URTEIL_ERWEITERT:
            aufgeloest["erweitert"] = True
        elif urteil == URTEIL_NEIN and _ist_geraeteklasse(feld.get("bedingung")):
            aufgeloest["nicht_an_dieser_bauart"] = True
        return aufgeloest

    return _mit_innengeraeten(
        [_mit_urteil(f) for f in alle_felder], parameter, "feld",
    )


def get_basis_felder(
    hat_dynamischen_tarif: bool = False,
    aktive_inv_typen: Optional[set[str]] = None,
    hat_variable_einspeisung: bool = False,
) -> list[dict]:
    """
    Gibt alle Basis-Felder für eine Anlage zurück (inkl. aufgelöster bedingter Felder).

    Kombiniert BASIS_FELDER + BEDINGTE_BASIS_FELDER, wobei letztere nur bei
    erfüllter Bedingung enthalten sind.

    Args:
        hat_dynamischen_tarif: True wenn die Anlage einen dynamischen Stromtarif hat
        aktive_inv_typen: Set der aktiven Investitionstypen (z.B. {"pv-module", "e-auto"})
        hat_variable_einspeisung: True wenn der (zum Stichtag gültige) allgemeine
            Tarif „Einspeisevergütung wechselt monatlich" trägt (#392)

    Returns:
        Liste von Feld-Dicts (ohne bedingung_basis-Key)
    """
    typen = aktive_inv_typen or set()
    result = list(BASIS_FELDER)

    for feld in BEDINGTE_BASIS_FELDER:
        bedingung = feld.get("bedingung_basis")
        if bedingung == "dynamischer_tarif" and not hat_dynamischen_tarif:
            continue
        if bedingung == "variable_einspeisung" and not hat_variable_einspeisung:
            continue
        if bedingung == "hat_eauto" and "e-auto" not in typen:
            continue
        if bedingung == "hat_waermepumpe" and "waermepumpe" not in typen:
            continue
        # bedingung_basis nicht an Consumer durchreichen
        result.append({k: v for k, v in feld.items() if k != "bedingung_basis"})

    return result


# Alle Monatsdaten-Feldnamen (Basis + Bedingte + Optionale) für generisches Speichern.
# Beim Save müssen keine Bedingungen geprüft werden — gespeichert wird was gesendet wurde.
ALLE_MONATSDATEN_FELDNAMEN: set[str] = {
    f["feld"] for f in BASIS_FELDER + BEDINGTE_BASIS_FELDER + OPTIONALE_FELDER
}


# Die Richtung, als die ein *Sonstiges*-Gerät **ohne gepflegte** `kategorie`
# gelesen wird — die eine benannte Stelle für eine Annahme, die am 17.08.2026
# an sechs Stellen als String-Literal `"verbraucher"` und an drei weiteren als
# `"erzeuger"` stand (N-244).
#
# **Warum ausgerechnet Verbraucher?** Weil beide Tages-Schreibpfade den Wert
# unter dieser Annahme überhaupt erst erzeugen (`live_sensor_config` ·
# `snapshot/komponenten_beitraege`) — wer ihn danach anders liest, liest an
# seiner eigenen Schreibweise vorbei. Begründung im Volltext:
# `berechnungen.energie.sonstiges_kwh_je_richtung`.
#
# ⚠ **Kein Ersatz für `energie.sonstiges_richtung`.** Diese Konstante gilt, wenn
# **kein Wert** vorliegt (Feldauswahl, Schlüsselbildung, Serienaufbau). Liegt
# einer vor, entscheidet er — das ist eine andere Frage und hat ihre eigene
# Funktion (N-250).
SONSTIGES_KATEGORIE_UNGEPFLEGT: Final[str] = "verbraucher"

# ─── Der dritte Zustand: Kategorien OHNE Stromrichtung (#377 / N-294) ────────
#
# *Sonstiges* war bis v4.0.22 **binär**: eine Kategorie ist entweder Erzeuger
# oder Verbraucher, und wer keine gepflegt hat, wird als Verbraucher gelesen
# (`SONSTIGES_KATEGORIE_UNGEPFLEGT`, neun Stellen — N-244). Ein **Zähler** ist
# weder das eine noch das andere: er trägt gar keine Stromrichtung, weil er gar
# keinen Strom führt. Ihn in eine der beiden Schubladen zu legen, hieße Gas oder
# Wasser in die Hausstrom-Aufschlüsselung zu geben.
#
# **Diese Konstante ist DER EINE ORT dafür.** Jede Stelle, die „ist das ein
# Erzeuger oder ein Verbraucher?" fragt, fragt zuerst hier — statt an neun
# Stellen `if kategorie == "zaehler"` zu schreiben, was die N-244-Wette ein
# zweites Mal wäre. Präzedenz im Baum: die Kategorie `speicher`, die
# `berechnungen.energie.sonstiges_kwh_je_richtung` bereits überspringt.
#
# ⚠ Eine Kategorie hier einzutragen heißt: sie taucht in **keiner**
# Energie-Rechnung auf. Wer eine hinzufügt, prüft die Stellen aus
# `test_377_zaehlerstaende.py` mit.
SONSTIGES_ZAEHLER_KATEGORIEN: Final[frozenset[str]] = frozenset({"zaehler"})

#: Der eine Feldname der Kategorie — ausgeschrieben statt aus der Registry
#: gezogen, weil dieses Projekt von der Grep-Barkeit lebt. Dass beide
#: übereinstimmen, hält `test_377_zaehlerstaende.py` fest.
ZAEHLERSTAND_FELD: Final[str] = "zaehlerstand"


def ist_zaehler_kategorie(kategorie: Optional[str]) -> bool:
    """Trägt diese *Sonstiges*-Kategorie einen Zählerstand statt Strom?

    Die eine Frage hinter {@link SONSTIGES_ZAEHLER_KATEGORIEN} — als Funktion,
    damit die Aufrufer nicht das Set importieren und dabei die Prüfung selbst
    formulieren (dieselbe Begründung wie bei `ist_zustand_feld`).
    """
    return kategorie in SONSTIGES_ZAEHLER_KATEGORIEN


def ist_gepflegte_sonstiges_kategorie(kategorie: Optional[str]) -> bool:
    """Ist ``kategorie`` eine **gepflegte** Kategorie eines *Sonstiges*-Geräts?

    Abgeleitet aus der Registry, damit eine vierte Kategorie nicht an einer
    handgeschriebenen Aufzählung vorbeiläuft. Gegenstück zu
    ``berechnungen.energie.sonstiges_richtung``: die dort getroffene
    Entscheidung kennt nur die zwei **Richtungen**, diese Frage kennt alle
    Kategorien — auch ``speicher``, der keine Richtung hat.
    """
    return kategorie in INVESTITION_FELDER.get("sonstiges", {})


def _sonstiges_felder_ungepflegt() -> list[dict]:
    """Alle Richtungen eines *Sonstiges*-Geräts, dedupliziert — **abgeleitet**.

    Verbraucher-Felder zuerst: das ist die Richtung, die jeder wertführende Pfad
    ohne gepflegte Kategorie annimmt (`SONSTIGES_KATEGORIE_UNGEPFLEGT`), also
    die wahrscheinlichere Eingabe. `speicher` bringt keinen eigenen Feldnamen
    mit und steht deshalb nicht extra in der Liste — die Ableitung nimmt ihn
    trotzdem mit, damit eine künftige Erweiterung der Kategorie nicht still
    danebenfällt.

    **Abgeleitet statt geschrieben, aus demselben Grund wie N-259:** eine
    handgepflegte vierte Feldliste wäre wieder die Wette darauf, dass jemand
    sie beim nächsten neuen Feld mitzieht.

    ⛔ **Zähler-Kategorien sind ausgenommen** (#377): Diese Liste beantwortet
    „welche Felder könnte ein Gerät führen, dessen Kategorie noch **nicht
    gepflegt** ist?" — und ein Zählerstand gehört nie dazu. Ohne die Ausnahme
    böte die Zuordnungsfläche eines kategorielosen Geräts `zaehlerstand` neben
    den Strom-Feldern an, und der Anwender ordnete einen Gassensor einem Gerät
    zu, das eedc anschließend als Verbraucher liest: **N-244 ein zweites Mal.**
    """
    sonstiges = INVESTITION_FELDER.get("sonstiges", {})
    reihenfolge = [SONSTIGES_KATEGORIE_UNGEPFLEGT] + [
        k for k in sonstiges
        if k != SONSTIGES_KATEGORIE_UNGEPFLEGT and not ist_zaehler_kategorie(k)
    ]
    gesehen: set[str] = set()
    out: list[dict] = []
    for kat in reihenfolge:
        for feld in sonstiges.get(kat, []):
            if feld["feld"] in gesehen:
                continue
            gesehen.add(feld["feld"])
            out.append(feld)
    return out


def get_felder_fuer_sonstiges(kategorie: Optional[str]) -> list[dict]:
    """
    Gibt Felder für eine Sonstiges-Investition nach Kategorie zurück.

    Args:
        kategorie: "erzeuger", "verbraucher", "speicher" — oder ``None``/leer/
                   unbekannt für ein Gerät **ohne gepflegte Kategorie**.

    Returns:
        Liste von Feld-Dicts. Ohne gepflegte Kategorie **alle Richtungen**
        (`SONSTIGES_FELDER_UNGEPFLEGT`), nicht eine geratene.

    **Warum hier nicht mehr geraten wird (N-244).** Bis 17.08.2026 stand hier
    ``sonstiges.get(kategorie, sonstiges.get("erzeuger", []))`` — ein Gerät ohne
    gepflegte Kategorie bekam also **Erzeuger**-Felder angeboten
    (``erzeugung_kwh`` · ``eigenverbrauch_kwh`` · ``einspeisung_kwh`` ·
    ``einspeise_erloes_euro``), während **jeder** wertführende Pfad denselben
    Zustand als *Verbraucher* liest und ``verbrauch_sonstig_kwh`` ·
    ``bezug_pv_kwh`` · ``bezug_netz_kwh`` erwartet (`sonstiges_feld_reihenfolge`
    28 Zeilen weiter unten, die beiden Tages-Schreibpfade,
    `berechnungen.energie.sonstiges_kwh_je_richtung`). Die **Schnittmenge beider
    Feldlisten ist leer** — die Zuordnungsfläche bot damit ausschließlich Felder
    an, die der Snapshot-Pfad für dieses Gerät nie sucht. Das ist die
    **N-259-Klasse**: nicht „Wert fehlt", sondern „Feld wird nirgends gefunden".
    """
    if ist_gepflegte_sonstiges_kategorie(kategorie):
        return INVESTITION_FELDER["sonstiges"][kategorie]
    return SONSTIGES_FELDER_UNGEPFLEGT


# Modul-Konstante statt Aufruf je Leser: die Ableitung ist rein und die
# Feld-Dicts sind ohnehin geteilte Modul-Objekte (wie in `INVESTITION_FELDER`).
SONSTIGES_FELDER_UNGEPFLEGT: Final[list[dict]] = _sonstiges_felder_ungepflegt()


def resolve_legacy_key(key: str) -> str:
    """
    Gibt den kanonischen Feldnamen für einen ggf. veralteten Key zurück.

    Für Rückwärtskompatibilität beim Lesen alter DB-Einträge.
    """
    return LEGACY_FELDNAMEN.get(key, key)


def get_live_felder_fuer_investition(typ: str, parameter: Optional[dict] = None) -> list[dict]:
    """
    Gibt die Live-Felder (W/kW/%) für einen Investitionstyp zurück.

    Bedingungen werden anhand der Parameter aufgelöst (gleiche Semantik wie
    get_felder_fuer_investition). Gibt immer eine leere Liste zurück wenn der
    Typ keine Live-Felder hat.

    Args:
        typ: Investitionstyp
        parameter: Investitions-Parameter-Dict (für konditionelle Felder)

    Returns:
        Liste von Live-Feld-Dicts (key, label, einheit)
    """
    params = parameter or {}
    alle = LIVE_FELDER_INV.get(typ, [])
    bedingungs_werte = _bedingungs_werte(params)

    # ⛔ **Hier stand bis zum 26.08.2026 eine eigene `elif`-Kette** — der dritte
    # Nachbau derselben Frage, neben `bedingung_erfuellt` und dem
    # String-Vergleich in `get_alle_felder_fuer_investition` (W-12). Sie konnte
    # weder Listen noch neue Schlüssel: `brauchwasser` hätte sie stillschweigend
    # ignoriert, und zwar fail-open in die falsche Richtung. Jetzt liest auch sie
    # `bedingungs_urteil`.
    result = []
    for feld in alle:
        urteil = bedingungs_urteil(
            feld.get("bedingung"), feld.get("weich"), bedingungs_werte,
        )
        if urteil == URTEIL_NEIN:
            continue
        eintrag = {k: v for k, v in feld.items() if k not in ("bedingung", "weich")}
        if urteil == URTEIL_ERWEITERT:
            eintrag["erweitert"] = True
        result.append(eintrag)

    return _mit_innengeraeten(result, params, "key")


def build_feld_labels() -> dict[str, str]:
    """
    Baut ein vollständiges Label-Dict aus der Registry auf.

    Kombiniert:
    - BASIS_FELDER (mapping_key → label)
    - INVESTITION_FELDER (feld → label, alle Typen/Kategorien)
    - LIVE_FELDER_INV (key → label)
    - Basis-Level-Extras (pv_gesamt, etc.)

    Returns:
        dict: {feldname_oder_key: anzeigelabel}
    """
    labels: dict[str, str] = {}

    # Basis-Felder (mapping_key-Form: "einspeisung", "netzbezug", ...)
    for f in BASIS_FELDER:
        labels[f["mapping_key"]] = f["label"]
        labels[f["feld"]] = f["label"]  # auch DB-Feldname → Label

    # Bedingte Basis-Felder
    for f in BEDINGTE_BASIS_FELDER:
        labels[f["feld"]] = f["label"]
        if "mapping_key" in f:
            labels[f["mapping_key"]] = f["label"]

    # Basis-Live-Felder
    for f in BASIS_LIVE_FELDER:
        labels[f["key"]] = f["label"]

    # Investitions-Felder (alle Typen)
    for typ, felder in INVESTITION_FELDER.items():
        if isinstance(felder, dict):
            # Sonstiges — Kategorien
            for kat_felder in felder.values():
                for f in kat_felder:
                    labels[f["feld"]] = f["label"]
        else:
            for f in felder:
                labels[f["feld"]] = f["label"]

    # Live-Felder (Investitions-Ebene)
    for felder in LIVE_FELDER_INV.values():
        for f in felder:
            labels[f["key"]] = f["label"]

    # Extras die nicht in oben definierter Struktur stecken
    labels["pv_gesamt"] = "PV Erzeugung Gesamt"
    # Counter-Felder (TagesEnergieProfil), erscheinen im Statistik-Import wenn
    # im Sensor-Mapping einer WP-Investition gemappt — detLAN #187/1 + #238.
    labels["wp_starts_anzahl"] = "Kompressor-Starts"
    labels["wp_betriebsstunden"] = "Betriebsstunden"

    return labels


# Vorgefertigtes Label-Dict (einmalig berechnet)
FELD_LABELS: dict[str, str] = build_feld_labels()


def build_feld_einheiten() -> dict[str, str]:
    """Baut {feldname_oder_key_oder_mapping_key: einheit} aus der Registry.

    Single Source of Truth für Einheiten-Plausibilität (Daten-Checker
    `_check_sensor_mapping_einheit`): erlaubt, zu jedem gemappten Slot die
    erwartete Einheit nachzuschlagen, statt sie aus Namenskonventionen zu raten.
    Deckt Basis-Zähler (mapping_key + feld), Basis-Live-Keys, alle
    Investitions-Felder (inkl. Sonstiges-Kategorien) und Investitions-Live-Keys
    ab. Strings kollidieren nicht über Kontexte (z. B. `einspeisung` vs.
    `einspeisung_kwh` vs. `einspeisung_w`); gleiche Strings tragen dieselbe
    Einheit.
    """
    einheiten: dict[str, str] = {}

    for f in BASIS_FELDER + BEDINGTE_BASIS_FELDER:
        if "mapping_key" in f:
            einheiten[f["mapping_key"]] = f.get("einheit", "")
        einheiten[f["feld"]] = f.get("einheit", "")

    for f in BASIS_LIVE_FELDER:
        einheiten[f["key"]] = f.get("einheit", "")

    for felder in INVESTITION_FELDER.values():
        if isinstance(felder, dict):  # sonstiges → nach Kategorie
            for kat_felder in felder.values():
                for f in kat_felder:
                    einheiten[f["feld"]] = f.get("einheit", "")
        else:
            for f in felder:
                einheiten[f["feld"]] = f.get("einheit", "")

    for felder in LIVE_FELDER_INV.values():
        for f in felder:
            einheiten[f["key"]] = f.get("einheit", "")

    return einheiten


# Vorgefertigtes Einheiten-Dict (einmalig berechnet)
FELD_EINHEITEN: dict[str, str] = build_feld_einheiten()


def _build_einheit_je_geraet() -> dict[str, str]:
    """`{feld: parameter-schlüssel}` für Felder mit **geräteabhängiger** Einheit.

    **Abgeleitet aus der Registry, nicht danebengeschrieben** — dieselbe
    Begründung wie bei `ZUSTAND_LIVE_FELDER` (#263 K-2) und `_sonstiges_felder_
    ungepflegt` (N-259): eine handgepflegte zweite Liste ist die Wette darauf,
    dass jemand sie beim nächsten Feld mitzieht.
    """
    out: dict[str, str] = {}
    for felder in INVESTITION_FELDER.values():
        listen = list(felder.values()) if isinstance(felder, dict) else [felder]
        for liste in listen:
            for f in liste:
                if f.get("einheit_je_geraet"):
                    out[f["feld"]] = f["einheit_je_geraet"]
    return out


#: Felder, deren Einheit erst am Gerät feststeht (#377). Leser: `einheit_fuer`.
FELD_EINHEIT_JE_GERAET: dict[str, str] = _build_einheit_je_geraet()


# ─── Einheiten-Dimension (SoT für Leistung↔Energie-Verwechslung) ────────────
# Gemeinsam genutzt vom Daten-Checker (`SENSOR_MAPPING_EINHEIT`) UND der
# Datenquellen-V4-Zuordnungs-Validierung (§2i, kWh-Sensor in W-Feld = #200).
# Bewusst NUR Leistung/Energie: SoC (%)/Temperatur (°C)/Preis/km sind legitime
# Einheiten-Varianten → kein Fehlalarm.
_POWER_EINHEITEN = {"W", "kW", "MW"}
_ENERGY_EINHEITEN = {"kWh", "Wh", "MWh"}


def einheit_klasse(unit: Optional[str]) -> Optional[str]:
    """Dimensions-Klasse einer Einheit: 'leistung' | 'energie' | None (egal)."""
    if unit in _POWER_EINHEITEN:
        return "leistung"
    if unit in _ENERGY_EINHEITEN:
        return "energie"
    return None


# ─── Zählerdifferenz-Felder (SoT für „darf aus HA-LTS gelesen werden?") ─────
# Zähler ohne Energie-Einheit: monoton steigend, der Monatswert ist die
# Differenz zweier Zählerstände. Energie-Felder erkennt `einheit_klasse`.
_ZAEHLER_FELDER_OHNE_ENERGIE_EINHEIT: frozenset[str] = frozenset({
    "km_gefahren",        # km-Zähler (Auto-Integration/OBD)
    "ladevorgaenge",      # Anzahl-Zähler der Wallbox
    "wp_starts_anzahl",   # #136
    "wp_betriebsstunden",  # #238
    # Basis-Mapping-Schlüssel des PV-Sammelzählers. kWh wie „einspeisung"/
    # „netzbezug", steht aber in KEINER Feld-Registry: es ist ein reiner
    # Mapping-Key, kein IMD-Feld — `FELD_EINHEITEN` kennt ihn deshalb nicht.
    # Ohne diesen Eintrag fiele der Sammelzähler still aus dem Statistik-Import
    # (gewächtert in test_zaehler_differenz_feld.py).
    "pv_gesamt",
})


def ist_zaehler_differenz_feld(feld: str) -> bool:
    """Darf der Monatswert dieses Feldes als Zählerdifferenz gelesen werden?

    Die Monatswert-Pfade aus HA (`monatsabschluss`-Vorschläge,
    HA-Statistik-Import) rechnen ausnahmslos `MAX(sum) − MIN(sum)` mit
    Fallback `MAX(state) − MIN(state)`. Das ist für einen Zählerstand richtig
    und für alles andere Unsinn: bei einem Preis-Sensor käme die **Preis-Spanne
    des Monats** heraus, bei einer Temperatur die Spreizung.

    Vorher iterierten beide Pfade ungefiltert über alles, was im Mapping stand.
    Praktisch blieb das meist folgenlos, weil ein `measurement`-Sensor weder
    `state` noch `sum` führt und still `None` liefert — aber eine Preis-Entität
    mit gefüllter `state`-Spalte schrieb ihre Monats-Spreizung als Ø Ladepreis
    in die Datenbank (Forum simon42 #89667/54, Anlass war die Sensor-Zuordnung
    an einem ct/kWh-Feld).

    Kein Gegenstück in `snapshot/keys.py`: dort geht es um den stündlichen
    Snapshot-Job, hier um den Monatswert aus HA-Langzeitstatistik. Die Mengen
    überschneiden sich, sind aber nicht dieselbe Frage — `ladung_extern_kwh`
    etwa ist ein Monatswert ohne Snapshot-Erfassung.
    """
    if einheit_klasse(FELD_EINHEITEN.get(feld)) == "energie":
        return True
    return feld in _ZAEHLER_FELDER_OHNE_ENERGIE_EINHEIT


# ─── Snapshot-Zählerfelder: die Ableitung für `services/snapshot/keys.py` ────
#
# **Warum es das gibt (N-259, Melder rapahl, 16.08.2026).** `snapshot/keys.py`
# führte `KUMULATIVE_ZAEHLER_FELDER` als **zweite, handgepflegte Liste**
# derselben Feldnamen, die hier oben in `INVESTITION_FELDER` stehen. Die beiden
# sind auseinandergelaufen, und niemand konnte es sehen:
#
# * Ein *Sonstiges*-Verbraucher heißt hier **`verbrauch_sonstig_kwh`** — die
#   Zuordnungsfläche schreibt diesen Key ins `sensor_mapping`, und
#   `mqtt_topic_registry` baut daraus das Topic
#   `…/inv/<id>_<name>/verbrauch_sonstig_kwh`. Die Snapshot-Liste kannte
#   stattdessen **`verbrauch_kwh`**, einen Namen, den es für diesen Typ gar
#   nicht gibt. Folge: `_mqtt_key_to_sensor_key` verwarf das **selbst
#   publizierte** Topic, `_add("verbrauch_kwh")` fand nie ein Mapping ⇒ ein
#   Heizstab mit eigenem Zähler existierte auf Stunden- und Tagesebene nicht.
#   Der Monat kam an, weil `get_sonstiges_verbrauch_kwh` **beide** Namen liest.
# * Der *Sonstiges*-**Erzeuger** war nie betroffen: er heißt in beiden Welten
#   `erzeugung_kwh`. Genau deshalb fiel es so lange nicht auf.
#
# **Die Ableitung ändert das heutige Verhalten NICHT** (außer dem belegten
# Fehler). Jede Abweichung zwischen Feld-Registry und Snapshot-Liste steht
# unten mit Grund — „bewusst nicht" ist von „noch nicht bewertet" unterscheidbar
# geworden, und genau das fehlte. Gewächtert in
# `test_snapshot_felder_sot_konformitaet.py`.

# (typ, feld) → Grund, warum das kWh-Feld NICHT stündlich gesnapshottet wird.
_SNAPSHOT_AUSNAHMEN: dict[tuple[str, str], str] = {
    # — Balkonkraftwerk: Kanon-Entscheid 2026-07-31 (Weg A) —
    ("balkonkraftwerk", "speicher_ladung_kwh"):
        "nur_manuell: BKW-Akku ist Kanon-Weg A eine eigene speicher-Investition "
        "mit Parent BKW; ein zweiter Zählerpfad wäre Doppelerfassung",
    ("balkonkraftwerk", "speicher_entladung_kwh"):
        "nur_manuell: siehe speicher_ladung_kwh",
    ("balkonkraftwerk", "eigenverbrauch_kwh"):
        "kein Zähler, sondern optionale Verfeinerung aus manueller Pflege/Import "
        "(Begründung: core/berechnungen/bkw_finanz.py)",
    # — Sonstiges-Erzeuger: dieselbe Klasse wie beim BKW —
    ("sonstiges", "eigenverbrauch_kwh"):
        "wie balkonkraftwerk/eigenverbrauch_kwh — Verfeinerung, kein Zähler",
    ("sonstiges", "einspeisung_kwh"):
        "Anteil der Erzeugung, optional gepflegt; die Bilanz führt der "
        "Anlagen-Einspeisezähler (basis:einspeisung)",
    # — Teilmengen des Sonstiges-Verbrauchs —
    ("sonstiges", "bezug_pv_kwh"):
        "⚠ UNBEWERTET: Teilmenge von verbrauch_sonstig_kwh. Bei der Wallbox ist "
        "das Gegenstück (ladung_pv_kwh) sehr wohl erfasst — die Ungleichheit ist "
        "gemessen, aber nicht entschieden. Beim nächsten Eingriff bewerten",
    ("sonstiges", "bezug_netz_kwh"):
        "⚠ UNBEWERTET: siehe bezug_pv_kwh",
    # — E-Auto —
    ("e-auto", "ladung_extern_kwh"):
        "Monatswert ohne Snapshot-Erfassung — auswärts geladene Energie fließt "
        "nicht durch den Hauszähler (so auch im Docstring von "
        "ist_zaehler_differenz_feld festgehalten)",
    ("e-auto", "v2h_entladung_kwh"):
        "⚠ UNBEWERTET: V2H speist ins Haus zurück und ist damit bilanzrelevant; "
        "warum das Feld nie im Snapshot-Pfad stand, ist nicht dokumentiert. "
        "Beim nächsten Eingriff am E-Auto-Pfad bewerten",
    # — Wechselrichter —
    ("wechselrichter", "pv_erzeugung_kwh"):
        "⚠ UNBEWERTET: Der Typ hat keinen Komponenten-Präfix "
        "(snapshot/komponenten_beitraege._TYP_KEY_PREFIX) und damit keinen "
        "Ziel-Key; die MQTT-Seite kennt ihn dagegen "
        "(mqtt_energy_history_service._MQTT_FIELD_TO_LIVE_KEY). Beim nächsten "
        "Eingriff am Wechselrichter-Pfad bewerten",
}

# Namen, die die Snapshot-Liste führt, obwohl es sie für diesen Typ in der
# Feld-Registry NICHT gibt. Sie bleiben stehen, weil sie in Altbeständen im
# `sensor_mapping` liegen können und ein Entfernen dort Zuordnungen unsichtbar
# machen würde — dieselbe Falle, die `nur_manuell` schon einmal gestellt hat.
# Wirkungslos sind sie nicht automatisch: `sonstiges/verbrauch_kwh` stand an der
# Stelle, an der `verbrauch_sonstig_kwh` fehlte, und täuschte Abdeckung vor.
_SNAPSHOT_KOMPATIBILITAET: dict[str, tuple[str, ...]] = {
    "wallbox": ("ladung_netz_kwh",),   # Wallbox-Registry kennt nur ladung_kwh/ladung_pv_kwh
    "e-auto": ("ladung_kwh",),         # Registry führt verbrauch_kwh; komponenten_beitraege nutzt beide
    "sonstiges": ("verbrauch_kwh",),   # Legacy-Zwilling von verbrauch_sonstig_kwh (s. get_sonstiges_verbrauch_kwh)
}


# (typ, feld) → Grund, warum das Feld zwar als **Zähler** mitgeschnitten wird,
# aber KEINEN Beitrag zu `komponenten_kwh` liefert.
#
# ⚑ **Diese Unterscheidung fehlte, und sie ist die eigentliche N-259-Lehre.**
# „Wird gesnapshottet" und „zählt in die Bilanz" sind zwei Fragen; bis hierher
# beantwortete sie eine Liste plus eine Reihe von `if typ ==`-Zweigen, zwischen
# denen niemand einen Abgleich ziehen konnte. `verbrauch_sonstig_kwh` fehlte in
# **beiden** — und weil es keine Deckungsprüfung gab, sah das aus wie Absicht.
_SNAPSHOT_OHNE_KOMPONENTEN_BEITRAG: dict[tuple[str, str], str] = {
    ("wallbox", "ladung_pv_kwh"):
        "Teilmenge von ladung_kwh — zusätzlich addiert wäre es die "
        "Doppelzählung aus #298 (14 + 9,24 = 23,24 statt 14)",
    ("wallbox", "ladung_netz_kwh"): "Teilmenge von ladung_kwh, s. ladung_pv_kwh",
    ("e-auto", "ladung_pv_kwh"): "Teilmenge der Ladung, s. wallbox/ladung_pv_kwh",
    ("e-auto", "ladung_netz_kwh"): "Teilmenge der Ladung, s. wallbox/ladung_pv_kwh",
    ("speicher", "ladung_netz_kwh"):
        "Teilmenge von ladung_kwh — sonst Doppelzählung für Arbitrage-Anwender",
    ("waermepumpe", "heizenergie_kwh"):
        "THERMISCH (~ Strom × COP), nicht elektrisch — gehört nicht in die "
        "Energiebilanz, nur in die JAZ-Rechnung",
    ("waermepumpe", "warmwasser_kwh"): "thermisch, s. heizenergie_kwh",
}

# #263 — die gemessenen Betriebsart-Zähler, aus zwei verschiedenen Gründen:
#
# * **Strom je Betriebsart ist eine Teilmenge** von `stromverbrauch_kwh` —
#   dieselbe Klasse wie `wallbox/ladung_pv_kwh` darüber. Als eigener
#   Komponenten-Beitrag stünde der Verbrauch der Wärmepumpe in der Tages- und
#   Stundenbilanz doppelt (einmal gesamt, einmal je Betriebsart).
# * **Nutzenergie je Betriebsart ist thermisch**, nicht elektrisch — dieselbe
#   Klasse wie `heizenergie_kwh`.
#
# ⚠ Der Monatswert entsteht davon unberührt: er kommt über die Vorschläge des
# Monatsabschlusses (HA-Statistik · MQTT · Connector) in die IMD-Zeile, nicht
# über den Komponenten-Beitrag. Gesnapshottet werden die Zähler weiterhin —
# nur eben ohne eigenen Eintrag in der Energiebilanz.
_SNAPSHOT_OHNE_KOMPONENTEN_BEITRAG.update({
    **{
        ("waermepumpe", _feld):
            "Teilmenge von stromverbrauch_kwh (#263) — als eigener Beitrag "
            "stünde der WP-Verbrauch in der Tagesbilanz doppelt"
        for _feld in _BETRIEBSART_STROM_FELDNAMEN
    },
    **{
        ("waermepumpe", _feld):
            "THERMISCH, nicht elektrisch (#263) — s. heizenergie_kwh"
        for _feld in _BETRIEBSART_NUTZENERGIE_FELDNAMEN
    },
})


def kumulative_zaehler_felder_je_typ() -> dict[str, tuple[str, ...]]:
    """Je Investitionstyp die kWh-Felder, die als **kumulativer Zähler**
    stündlich gesnapshottet werden — abgeleitet aus `INVESTITION_FELDER`.

    Regel: jedes Feld mit Energie-Einheit, außer es steht in
    `_SNAPSHOT_AUSNAHMEN`. Dazu die Kompatibilitäts-Namen aus
    `_SNAPSHOT_KOMPATIBILITAET`. Bei `sonstiges` werden die Kategorien
    (erzeuger/verbraucher/speicher) vereinigt — welche Felder ein konkretes
    Gerät führt, entscheidet erst `get_felder_fuer_sonstiges`.

    Die Reihenfolge ist stabil (Registry-Reihenfolge, dann Kompatibilität),
    damit Proben sie vergleichen können.
    """
    out: dict[str, tuple[str, ...]] = {}
    for typ, felder in INVESTITION_FELDER.items():
        listen = (list(felder.values()) if isinstance(felder, dict) else [felder])
        namen: list[str] = []
        for liste in listen:
            for f in liste:
                feld = f["feld"]
                if einheit_klasse(FELD_EINHEITEN.get(feld)) != "energie":
                    continue
                if (typ, feld) in _SNAPSHOT_AUSNAHMEN:
                    continue
                if feld not in namen:
                    namen.append(feld)
        for feld in _SNAPSHOT_KOMPATIBILITAET.get(typ, ()):
            if feld not in namen:
                namen.append(feld)
        if namen:
            out[typ] = tuple(namen)
    return out


def stand_felder() -> frozenset[str]:
    """Die Felder, deren Wert ein **Stand** ist und keine Menge — abgeleitet
    aus `INVESTITION_FELDER` über den Marker ``stand: True``.

    **Warum es diese Unterscheidung gibt (F-58, 21.08.2026).** Die
    Snapshot-Schiene holt jeden gemappten Zähler über
    `ha_statistics_service.get_value_at`, und das nimmt bei einem Sensor mit
    `has_sum` **ausschließlich HAs `sum`** — die reset-bereinigte
    Verbrauchssumme seit Aufzeichnungsbeginn. Das ist für eine **Flussgröße**
    richtig und bewusst so entschieden (v3.25.18, Issue #184): ein
    utility_meter mit Tagesreset hat in `state` den Tageswert, nur `sum` ist
    die Lebensdauer-Zahl.

    Für eine **Bestandsgröße** ist dieselbe Wahl falsch. Der Zählerstand eines
    Gas-, Wasser- oder Ölzählers ist die Zahl, die auf dem Zähler steht; sie
    steht in `state`. Ein Melder sah 90 m³, wo sein Sensor 47,360 m³ meldete —
    und wir haben ihm zunächst geantwortet, eedc zeige „genau die Zahl, die
    dein Sensor meldet".

    ⚠ **Der zweite Zweig war genauso falsch:** ohne `has_sum` verlangt
    `_value_at_wert` eine Energie-Einheit und liefert sonst `None`. Ein
    Wasserzähler in m³ bekam damit **gar keinen** Snapshot. Ein Stand-Feld
    braucht beides nicht — es liest `state` und rechnet nichts um.

    ⛔ **Was hier bewusst NICHT steht: `wp_starts_anzahl` und
    `wp_betriebsstunden`.** Sie sind zwar ebenfalls Bestandsgrößen, aber ihr
    Snapshot wird **nur differenziert** (`aggregate_day`), und der
    Lebensdauer-Stand kommt aus einem eigenen Leser
    (`snapshot/reader.get_counter_lifetime`, HA-Live-State zuerst). Sie
    umzustellen hieße, eine bestehende Reihe von `sum` auf `state` zu
    verschieben — bei einer WP, deren Gerätezähler weit über HAs
    Aufzeichnungssumme liegt, ergäbe das an genau einem Tag einen Sprung in
    der Größe des Lebensdauer-Zählers. `_get_counter_deltas_for_day` kappt
    **negative** Deltas, positive nicht. Das ist als Nebenfund geführt, nicht
    als Auslassung.
    """
    namen: set[str] = set()
    for felder in INVESTITION_FELDER.values():
        listen = (list(felder.values()) if isinstance(felder, dict) else [felder])
        for liste in listen:
            for f in liste:
                if f.get("stand"):
                    namen.add(f["feld"])
    return frozenset(namen)


#: Die Stand-Felder als Konstante — einmal abgeleitet, überall dieselbe Antwort.
STAND_FELDER: Final[frozenset[str]] = stand_felder()


def ist_stand_feld(feld: str) -> bool:
    """Ist der Wert dieses Feldes ein **Stand** (Bestandsgröße)?

    Mit Innengeräte-Auflösung wie jede andere Namens-Whitelist — ein Feld-Key
    kann das Suffix `-<id>` tragen (`basis_feld_key`).
    """
    if not feld:
        return False
    return basis_feld_key(feld) in STAND_FELDER


# =============================================================================
# Reader-Helper für `verbrauch_daten`-JSON
#
# Drift-Audit Domäne F: bisher waren 27+ Aufrufer mit Mustern wie
# `data.get("a", 0) or data.get("b", 0)` über das Repo verstreut. Bei
# Schema-Drift (alter Key bleibt in Daten, neuer Key fehlt) führte das
# zu inkonsistentem Verhalten zwischen Endpoints.
#
# Diese Helper sind die SoT für PV/WP/E-Auto/Speicher-Energiewerte. Bei
# künftigen Schema-Wechseln nur hier anpassen.
# =============================================================================

def get_pv_erzeugung_kwh(data: dict) -> float:
    """PV-Modul- oder BKW-Erzeugung. Liest `pv_erzeugung_kwh` (kanonisch),
    Legacy-Fallback `erzeugung_kwh`.
    """
    if not data:
        return 0.0
    return float(data.get("pv_erzeugung_kwh") or data.get("erzeugung_kwh") or 0)


def get_wp_heizenergie_kwh(data: dict) -> float:
    """Wärmepumpen-Heizenergie (nicht Warmwasser).
    Liest `heizenergie_kwh` (kanonisch), Legacy-Fallback `heizung_kwh`.
    """
    if not data:
        return 0.0
    return float(data.get("heizenergie_kwh") or data.get("heizung_kwh") or 0)


def get_eauto_ladung_kwh(data: dict) -> float:
    """E-Auto- oder Wallbox-Gesamtladung in kWh.
    Liest `ladung_kwh` (kanonisch), Legacy-Fallback `verbrauch_kwh`.
    """
    if not data:
        return 0.0
    return float(data.get("ladung_kwh") or data.get("verbrauch_kwh") or 0)


def get_speicher_netzladung_kwh(data: dict) -> float:
    """Speicher-Netzladung (Arbitrage). Liest `ladung_netz_kwh` (kanonisch),
    Legacy-Fallback `speicher_ladung_netz_kwh`.
    """
    if not data:
        return 0.0
    return float(data.get("ladung_netz_kwh") or data.get("speicher_ladung_netz_kwh") or 0)


def get_emob_pv_netz_kwh(data: dict, total_kwh: float | None = None) -> tuple[float, float]:
    """E-Mobilitäts-PV-/Netz-Anteil aus Wallbox-/E-Auto-Monatsdaten.

    Liest `ladung_pv_kwh` direkt. Für `ladung_netz_kwh`:
    - wenn als Key vorhanden → verwenden (auch 0 ist ein gültiger gepflegter Wert)
    - sonst aus Gesamt-Ladung ableiten: `netz = max(0, total - pv)`.

    Hintergrund #262 (junky84): der evcc-Portal-Import liefert pro Session nur
    `Energie (kWh)` + `Sonne (%)` und schreibt damit `ladung_kwh` + `ladung_pv_kwh`,
    aber kein `ladung_netz_kwh`. Pool-Max-Aggregationen, die nur diese beiden Keys
    direkt lasen, sahen Netz = 0 und damit PV-Anteil = 100 %.

    `total_kwh` darf vom Aufrufer übergeben werden, wenn die Gesamt-Ladung bereits
    via `get_eauto_ladung_kwh()` bestimmt wurde — spart eine zweite Lesung.
    """
    if not data:
        return (0.0, 0.0)
    pv = float(data.get("ladung_pv_kwh") or 0)
    if "ladung_netz_kwh" in data and data["ladung_netz_kwh"] is not None:
        return (pv, float(data["ladung_netz_kwh"]))
    if total_kwh is None:
        total_kwh = get_eauto_ladung_kwh(data)
    return (pv, max(0.0, total_kwh - pv))


# Die Verbrauchs-Felder eines *Sonstiges*-Geräts, in Präzedenz-Reihenfolge:
# `verbrauch_sonstig_kwh` ist der **kanonische** Registry-Name — so heißt der
# `sensor_mapping`-Key, und unter diesem Namen publiziert eedc auch sein
# MQTT-Topic. `verbrauch_kwh` ist der Legacy-Zwilling und bleibt nur lesbar
# (Altbestand im Mapping); er darf nie zusätzlich zählen, beide gehören
# derselben Either-Or-Gruppe an.
SONSTIGES_VERBRAUCH_FELDER: tuple[str, ...] = ("verbrauch_sonstig_kwh", "verbrauch_kwh")


def sonstiges_feld_reihenfolge(kategorie: str | None) -> tuple[str, ...]:
    """Energie-Felder eines *Sonstiges*-Geräts in **Präzedenz-Reihenfolge**.

    Ein solches Gerät hat entweder eine Erzeugung oder einen Verbrauch, nie
    beides — die gepflegte ``kategorie`` sagt, welches Feld führt. Wer keine
    gepflegt hat, wird als Verbraucher gelesen (dieselbe Lesart wie in den
    Schreibpfaden, siehe ``berechnungen.energie.sonstiges_richtung``).

    **Warum das eine Funktion ist (N-259).** Dieselbe Reihenfolge stand am
    16.08.2026 an **drei** Stellen handgeschrieben — und ein einziger
    abweichender Name hat gereicht, damit eedc ein MQTT-Topic **selbst
    publizierte und beim Einlesen wieder verwarf**: Der Snapshot suchte
    ``verbrauch_kwh``, die Zuordnungsfläche schrieb ``verbrauch_sonstig_kwh``.
    Der Monat kam trotzdem an (dieser Getter liest beide), der Tageswert nicht —
    es sah nach „Wert fehlt" aus statt nach „Feld wird nirgends gefunden".
    Eine vierte Kopie wäre dieselbe Wette noch einmal.

    ⚠ **Ein Zähler liefert `()` — und das ist kein Sonderfall, sondern die
    Antwort auf die gestellte Frage** (#377): Diese Funktion nennt die
    **Energie**-Felder eines Geräts, und ein Gaszähler hat keine. Ohne den
    leeren Rückgabewert liefe der Fallback in Zeile darunter, und der Snapshot
    suchte am Gaszähler nach `verbrauch_sonstig_kwh` — die N-259-Klasse in der
    Gegenrichtung: nicht ein falscher Name, sondern ein Feld, das es an diesem
    Gerät gar nicht geben darf.
    """
    if ist_zaehler_kategorie(kategorie):
        return ()
    if kategorie == "erzeuger":
        return ("erzeugung_kwh", *SONSTIGES_VERBRAUCH_FELDER)
    return (*SONSTIGES_VERBRAUCH_FELDER, "erzeugung_kwh")


def get_sonstiges_verbrauch_kwh(data: dict) -> float:
    """Sonstiges-Verbraucher-Energie. Liest `verbrauch_sonstig_kwh` (kanonisch),
    Legacy-Fallback `verbrauch_kwh` — Reihenfolge aus
    `SONSTIGES_VERBRAUCH_FELDER`, damit sie nicht neben dem SoT driftet.
    """
    if not data:
        return 0.0
    for feld in SONSTIGES_VERBRAUCH_FELDER:
        wert = data.get(feld)
        if wert:
            return float(wert)
    return 0.0


def get_wp_strom_kwh(data: dict, params: dict | None = None) -> float:
    """Wärmepumpen-Stromverbrauch in kWh — single source of truth.

    Bei `getrennte_strommessung=True` werden ausschließlich die getrennten
    Sensoren (`strom_heizen_kwh + strom_warmwasser_kwh`) summiert; das alte
    `stromverbrauch_kwh`-Feld wird ignoriert, auch wenn ein parallel laufender
    Sensor noch hineinschreibt. Sonst wird der Gesamt-Sensor genutzt
    (`stromverbrauch_kwh`/`strom_kwh`/`verbrauch_kwh`-Legacy-Fallbacks).

    Hintergrund #183: Mit beiden Pfaden parallel driften die drei JAZ-Werte
    (Gesamt vs. Heizen vs. Warmwasser) gegeneinander, weil der Gesamt-JAZ
    aus der alten Quelle gerechnet wird, die getrennten JAZ aber aus den
    neuen Sensoren — Folge: Gesamt-JAZ kann mathematisch außerhalb der
    gewichteten Mitte der beiden Einzel-JAZ liegen.

    ⭐ **W-16 (2026-08-26): Der getrennte Zweig kannte nur zwei Funktionen.**
    ``strom_heizen_kwh + strom_warmwasser_kwh`` war der ganze Verbrauch,
    solange eine Wärmepumpe nur heizen und Warmwasser machen konnte. Seit
    **R1/W-2** ist ein **Kühlzähler an jeder Bauart** zuordenbar — und sein
    Strom stand in **keinem** der beiden Felder. Folge an einer nachgestellten
    Anlage gemessen (MartyBrs Bauform, T89667 #200): **950 statt 1050 kWh**,
    also 100 kWh, die in Kosten, CO₂ und Verbrauchsseite fehlten.

    ⭐ **Und die zweite Folge, W-16b:** Weil der Nenner den Kühlstrom nie
    enthielt, zog ``arbeitszahl(...)`` ihn über ``strom_funktionsfremd_kwh``
    ein **zweites** Mal ab — 3600 ÷ 850 statt 3600 ÷ 950, die Anlage sah 12 %
    besser aus, als sie ist. Mit der Ergänzung hier wird jener Abzug wieder
    richtig, **ohne dass ein Aufrufer sich ändert**.

    ⚠ **Nur der GEMESSENE Split wird addiert, und das ist der Kern.** Ein
    **abgeleiteter** Split (aus dem Stunden-Signal) verteilt den *vorhandenen*
    Gesamtstrom auf Betriebsarten — sein Kühlanteil ist bereits Teil von
    ``strom_heizen_kwh``. Ihn zu addieren wäre genau die Doppelzählung, die
    W-16b beseitigt, nur andersherum. ``ModusStromZeile.gemessen`` trennt die
    beiden Fälle; ``funktionsfremd_kwh`` ist die **eine Stelle**, die sagt,
    welche Betriebsarten keine bewertete Nutzenergie haben (Kühlen · Lüften ·
    Entfeuchten, **E4**) — sie hier aufzuzählen wäre die Bauform, an der W-14
    entstanden ist.

    ⚠ **Im Nicht-getrennt-Zweig wird NICHTS addiert:** ``stromverbrauch_kwh``
    ist der Zählerstand des ganzen Geräts und enthält den Kühlbetrieb bereits.
    """
    if not data:
        return 0.0
    if params and params.get("getrennte_strommessung"):
        basis = float(
            (data.get("strom_heizen_kwh") or 0) +
            (data.get("strom_warmwasser_kwh") or 0)
        )
        # Lokaler Import: `betriebsart_gemessen` liest `basis_feld_key` aus
        # diesem Modul — ein Import auf Modulebene wäre zirkulär.
        from backend.core.berechnungen.betriebsart_gemessen import modus_strom_zeile

        zeile = modus_strom_zeile(data)
        if zeile.gemessen:
            basis += zeile.funktionsfremd_kwh
        return basis
    return float(
        data.get("stromverbrauch_kwh") or
        data.get("strom_kwh") or
        data.get("verbrauch_kwh") or 0
    )
