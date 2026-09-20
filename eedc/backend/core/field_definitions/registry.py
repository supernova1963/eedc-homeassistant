"""Die Feld-Registries: Basis-, bedingte und optionale Felder, `INVESTITION_FELDER` je Typ, Live- und Preisfelder,
Legacy-Feldnamen. Reine Daten.
"""
# Reiner Umzug aus `core/field_definitions.py` (18.09.2026, Vorlage 3 des Refactorings grosser
# Dateien): Code 1:1 uebernommen, kein Verhaltenswechsel. Die Fassade `__init__.py` exportiert
# alle Namen weiter, die Aufrufer und Tests bisher aus dem Modul importierten.




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
    # N-426 (Nachbesserung): derselbe Halbsatz wie bei der Globalstrahlung
    # darüber. Seit alle drei Wetterfelder nur noch LÜCKEN füllen, ist er für
    # beide wahr — vorher versprach ihn nur das eine Feld, und keines hielt ihn.
    {"feld": "sonnenstunden",          "label": "Sonnenstunden",   "einheit": "h",      "mapping_key": "sonnenstunden",  "gruppe": "wetter",
     "hinweis": "Sonnenstunden im Monat (h). Wird automatisch von Open-Meteo geholt, wenn nicht manuell gepflegt."},
    # N-426: Bis v4.0.44 stand hier „Wird automatisch von Open-Meteo geholt" —
    # eine Zusage, die der V4-Auto-Fill nicht mehr einlöste (er füllte nur die
    # zwei Felder darüber). Der Hinweis sagt jetzt, was der Knopf wirklich tut,
    # UND woher der Wert kommt: die eigene Messreihe schlägt das Archiv.
    {"feld": "durchschnittstemperatur","label": "Ø Temperatur",    "einheit": "°C",     "mapping_key": "temperatur",     "gruppe": "wetter",
     "hinweis": "Monatsdurchschnittstemperatur (°C). „Auto-Fill\" holt sie aus den gemessenen Außentemperaturen des Monats, sonst von Open-Meteo — ein selbst eingetragener Wert bleibt stehen und lässt sich jederzeit überschreiben."},
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
        "hinweis": "Dein abgerechneter Ø-Arbeitspreis dieses Monats (ct/kWh) — er schlägt jede Berechnung. Trägst du nichts ein, rechnet eedc mit dem verbrauchsgewichteten Ø deiner mitgeschriebenen Stundenpreise (Tibber/aWATTar/EPEX) und bei einem Zeittarif (HT/NT) mit dem über deinen Netzbezug gewichteten Tarifpreis. Erst wenn beides fehlt — etwa bei handgetragenen Monatswerten — gilt der Preis aus den Stammdaten.",
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
            # ⛔ Der Hinweis endete bis zum 14.09.2026 mit „Bei getrennter
            # Messung: Summe aus Heizen + Warmwasser." Das war die Zusage, die
            # WK-16d aufgehoben hat: Der Zähler misst, was er misst — und wenn
            # das mehr ist als die beiden Achsen, gilt seither er und die
            # Differenz heißt „nicht aufgeteilt" (K1/K5).
            "hinweis": "Gesamter elektrischer Energieverbrauch der WP (kWh, kumulativ oder Tagessensor). Auch bei getrennter Messung sinnvoll: misst er mehr als Heizen + Warmwasser zusammen (Standby, Steuerung, Umwälzpumpen), gilt sein Wert als Verbrauch des Geräts und die Differenz erscheint als „nicht aufgeteilt“.",
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
            # #120-Schaerfung, zweite Haelfte (01.09.2026, dietmar1968 T89667 #283).
            # `heizenergie_kwh` bekam mit #120 ausdruecklich "abgegebene thermische
            # Waerme, nicht Strom" ins LABEL — dieses Schwesterfeld blieb bei
            # "Warmwasser" stehen. Das Label ist die einzige Beschriftung, die
            # die Custom-Import-Zuordnung zeigt (`custom_import/analyze.py` baut
            # die Option aus `label` + Einheit), und genau dort ordnete ein
            # Melder eine Umgebungswaerme-Spalte auf dieses Feld zu. Bei
            # "Heizwaerme" daneben ist ihm das nicht passiert.
            # CSV-Suffix bleibt unveraendert — wie bei #120.
            "feld": "warmwasser_kwh", "label": "Warmwasser-Wärme", "einheit": "kWh",
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
            "hinweis": "Abgegebene Warmwasser-Wärme (thermisch) in kWh, kumulativ oder Tagessensor. Optional — misst EIN Zähler Heizung und Warmwasser zusammen, gehört sein Wert unter „Wärme gesamt“.",
        },
        {
            # N-391 — **der Ort für EINEN gemeinsamen Wärmemengenzähler.**
            #
            # ⛔ **Warum es das Feld bis zum 14.09.2026 nicht gab und was das
            # gekostet hat.** Eine Luft-Wasser-Wärmepumpe mit Umschaltventil hat
            # EINEN Vorlauf; der Wärmemengenzähler sitzt dort und misst Heizung
            # **und** Warmwasser. Wer so misst, trug seine Zahl mangels
            # Alternative unter *Heizwärme* ein (so stand es im Handbuch) — und
            # bei getrennter Strommessung (F5) rechnete eedc daraus
            # `Gesamtwärme ÷ Heizstrom`: gemessen **5,0** statt 3,0, ohne
            # jeden Grund daneben. Eine Zahl, die gut aussieht und nichts misst.
            #
            # ⭐ **Der LESE-Vertrag stand schon** (D1,
            # `waermepumpe_kennzahl.waerme_gesamt_kwh`, seit 26.08.): „Liegt eine
            # gemessene Gesamtwärme vor, gilt sie. Sonst ist die Wärme die Summe
            # ihrer beiden Achsen." Es fehlte allein der **Erfassungsweg** —
            # ohne Registry-Eintrag gibt es kein Formularfeld, keinen
            # Zuordnungs-Slot und keinen `csv_suffix`.
            #
            # ⚠ **Keine `bedingung`** (Entscheid 14.09.): Die Bilanzgröße gibt es
            # an jedem Gerät, wie `stromverbrauch_kwh` auf der Stromseite. Sie an
            # eine Bauart zu binden wäre die Bauform, die R1 abgelöst hat — was
            # ein Gerät liefern kann, sagt der zugeordnete Zähler.
            #
            # ⭐ **Und die Vorrangregel ist seit WK-16d dieselbe wie auf der
            # Stromseite:** Gesamtwert ⇒ Menge, Aufteilung ⇒ daneben, Rest ⇒
            # *nicht aufgeteilt* (K1/K5). ⛔ Bis zum 14.09.2026 stand hier das
            # Gegenteil — *„auf der Stromseite gewinnt die vollständige feine
            # Aufteilung, weil `getrennte_strommessung` erklärt, dass die zwei
            # Zähler zusammen das Ganze sind"*. Das Kennzeichen erklärt, dass die
            # zwei Zähler **Summanden** sind; dass sie zusammen **alles** messen,
            # erklärt es nicht (Standby, Steuerung, Umwälzpumpen). Die beiden
            # Seiten sagen jetzt denselben Satz.
            "feld": "waerme_kwh", "label": "Wärme gesamt", "einheit": "kWh",
            "csv_suffix": "Waerme_Gesamt_kWh",
            "hinweis": "Abgegebene Wärme GESAMT (thermisch, NICHT Strom!) in kWh, kumulativ oder Tagessensor — für EINEN Wärmemengenzähler, der Heizung und Warmwasser zusammen misst. Wer getrennte Zähler hat, lässt das Feld leer. Trägt hier ein Wert, gilt er als die Wärme des Geräts; Heizwärme und Warmwasser-Wärme stehen dann nur noch als Aufteilung daneben.",
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
        # #407 (8ear): der TACHOSTAND als Handeingabe — das Zählerstand-Modell
        # aus #377 auf das Auto übertragen: eedc führt den Stand, die einzige
        # Rechnung darauf ist Ende − Anfang, und die landet als Vorschlag auf
        # „Gefahrene km" (`vorschlag_service._get_berechnete_werte`). Das Feld
        # darüber bleibt unverändert die MENGE — alle Leser (Effizienz, Benzin-
        # Vergleich, HA-Export, Community) lesen weiter nur `km_gefahren`.
        #
        # `stand: True` — eine Bestandsgröße, keine Menge (kein Vormonats-/
        # Durchschnitts-Vorschlag: ein Tachostand hat keinen Mittelwert, s.
        # `ist_stand_feld`). `nur_manuell` — der SENSOR-Weg existiert schon:
        # ein Kilometerstand-Sensor gehört auf `km_gefahren`, dort bildet die
        # HA-Statistik bzw. die MQTT-Reihe (#396) die Differenz selbst. Ein
        # zweiter Sensor-Slot für denselben Stand wäre Doppelerfassung.
        # ⛔ Kein Parameter „Kilometerstand bei Anschaffung": der erste Monat
        # hat keinen Anfang, und das Modell weist eine fehlende Anfangsmessung
        # aus (`anfang_vollstaendig`), statt sie zu erfinden.
        {
            "feld": "km_stand", "label": "Tachostand", "einheit": "km",
            "placeholder": "z.B. 45230",
            "csv_suffix": "Tachostand",
            "stand": True,
            "nur_manuell": True,
            "hinweis": (
                "Kilometerstand am Monatsende, wie er im Auto steht. eedc rechnet "
                "daraus die gefahrenen Kilometer (Stand dieses Monats minus Stand des "
                "Vormonats) und schlägt sie oben vor. Nur für die Handeingabe — ein "
                "Kilometerstand-Sensor gehört auf „Gefahrene km“, dort bildet eedc die "
                "Differenz selbst."
            ),
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
        # Abgabe an Dritte — der dritte Weg der Netzpunkt-Bilanz (KONZEPT-
        # WIRTSCHAFTLICHKEITSRECHNUNG §9.2, Entscheid 05.09.2026, #402/N-378).
        # Mieterstrom, Allgemeinstrom, Nachbarhaus: Energie, die das Haus hinter
        # dem Hausanschluss verlässt, ohne Eigenverbrauch und ohne Netz-
        # Einspeisung zu sein. Die Menge ist ein ZÄHLER an der Übergabestelle —
        # gemessen, nie geschätzt; ohne Zähler bleibt die Handbuch-Grenze.
        "abgabe": [
            {
                "feld": "abgabe_kwh", "label": "Abgabe", "einheit": "kWh",
                "csv_suffix": "Abgabe_kWh",
                "hinweis": (
                    "An Dritte abgegebene Energie (Mieterstrom, Allgemeinstrom, "
                    "Nachbarhaus) in kWh — Zähler an der Übergabestelle, kumulativ "
                    "oder Tagessensor. eedc zieht sie vom Eigenverbrauch ab; sie ist "
                    "weder Eigenverbrauch noch Netz-Einspeisung."
                ),
            },
            {
                "feld": "einspeise_erloes_euro", "label": "Erlös", "einheit": "€",
                "placeholder": "z. B. 42.30",
                "csv_suffix": "Erloes_Euro",
                "hinweis": (
                    "Erlös aus der Abgabe in € (eigener Satz, den eedc nicht kennen "
                    "kann). Am besten als kumulativer Helfer-Sensor aus Home Assistant; "
                    "die Abrechnung an die Abnehmer ist nicht Sache von eedc."
                ),
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
        # ⭐ **Der Anzeigepfad kam am 13.09.2026 nach** (N-439, Entscheid Gernot
        # Tor G-K). Das Feld war seit W-13 zuordenbar und wurde an keiner
        # Station gelesen — „Live-Wert" stand als Zusage in WAS-IST-NEU, ohne
        # dass irgendetwas ihn zeigte. Jetzt läuft er den Weg der Nachbarn:
        # Live-Bild (Summe + Symbol), Live-Tagesverlauf und Tag-Stundenverlauf
        # (eigene Fläche), MQTT-Snapshot. **„Reine Anzeige" bleibt wörtlich
        # gültig:** aus diesem Feld entsteht keine kWh, keine Integration und
        # keine Kennzahl — die Mengen kommen aus dem Zähler (E4).
        {"key": "leistung_kuehlen_w",      "label": "Leistung Kühlen",      "einheit": "W",
         "hinweis": "Elektrische Leistungsaufnahme im Kühlbetrieb in W. Nur sinnvoll, "
                    "wenn der Kühlbetrieb getrennt gemessen wird — reine Anzeige: "
                    "erscheint im Live-Bild und als eigene Fläche im Tagesverlauf, "
                    "die Mengen kommen aus dem kWh-Zähler."},
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
         "hinweis": "Momentane Leistung des Balkonkraftwerks in W. Sind ihm PV-Module "
                    "zugeordnet, gilt hier dieselbe Regel wie beim Monatswert: die Module "
                    "tragen die Leistung, dieser Wert füllt nur noch ihre Lücken — messen "
                    "alle selbst, wird er nicht mehr gelesen."},
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
# Alte Feldnamen → neue kanonische Namen (für Lese-Kompatibilität mit alten DB-Einträgen)
LEGACY_FELDNAMEN: dict[str, str] = {
    "speicher_ladung_netz_kwh": "ladung_netz_kwh",   # Speicher Arbitrage
    "entladung_v2h_kwh":        "v2h_entladung_kwh", # E-Auto V2H
}

# Summen-Keys die _import_investition_monatsdaten_v09 zurückgibt
IMPORT_SUMMEN_KEYS = ("pv_erzeugung_sum", "batterie_ladung_sum", "batterie_entladung_sum")
