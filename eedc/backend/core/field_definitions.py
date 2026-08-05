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

from typing import Optional


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
#   "dynamischer_tarif" — Anlage hat einen dynamischen Stromtarif
#   "hat_eauto"         — Anlage hat mindestens eine aktive E-Auto-Investition
#   "hat_waermepumpe"   — Anlage hat mindestens eine aktive Wärmepumpe
# =============================================================================

BEDINGTE_BASIS_FELDER = [
    {
        "feld": "netzbezug_durchschnittspreis_cent",
        "label": "Ø Strompreis",
        "einheit": "ct/kWh",
        "bedingung_basis": "dynamischer_tarif",
        "mapping_key": "strompreis",
        "gruppe": "preise",
        "hinweis": "Verbrauchsgewichteter Ø-Arbeitspreis des Monats (ct/kWh). Bei dynamischem Tarif sonst automatisch aus dem Strompreis-Sensor (Tibber/aWATTar/EPEX) berechnet.",
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

INVESTITION_FELDER: dict = {
    "pv-module": [
        {
            "feld": "pv_erzeugung_kwh", "label": "PV-Erzeugung", "einheit": "kWh",
            "csv_suffix": "kWh",
            "aggregiert_in": "pv_erzeugung_sum",
            "hinweis": "Kumulativer kWh-Zähler (oder Tagessensor) der erzeugten Energie dieses PV-Strings. Immer ≥ 0. Alternativ anteilig per kWp aus dem PV-Gesamt-Sensor verteilt.",
        },
    ],

    "wechselrichter": [
        {
            "feld": "pv_erzeugung_kwh", "label": "PV-Erzeugung", "einheit": "kWh",
            "csv_suffix": "kWh",
            "aggregiert_in": "pv_erzeugung_sum",
            # Nur anzeigen wenn keine separaten PV-Modul-Investments existieren.
            # Sonst wird die Erzeugung bei den einzelnen PV-Modul-Segmenten erfasst.
            "bedingung_anlage": "keine_pv_module",
            "hinweis": "Kumulativer kWh-Zähler (oder Tagessensor) der gesamten PV-Erzeugung am Wechselrichter. Nur nötig, wenn keine separaten PV-Modul-Investitionen erfasst werden.",
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
            "bedingung": "!getrennte_strommessung",
            "csv_suffix": "Strom_kWh",
            "hinweis": "Gesamter elektrischer Energieverbrauch der WP (kWh, kumulativ oder Tagessensor). Bei getrennter Messung: Summe aus Heizen + Warmwasser.",
        },
        # Getrennte-Strommessung-Modus (getrennte_strommessung=true):
        {
            "feld": "strom_heizen_kwh", "label": "Strom Heizen", "einheit": "kWh",
            "bedingung": "getrennte_strommessung",
            "csv_suffix": "Strom_Heizen_kWh",
            "hinweis": "Elektrische Energie für den Heizbetrieb (kWh, kumulativ oder Tagessensor). Nur bei getrennter Strommessung.",
        },
        {
            "feld": "strom_warmwasser_kwh", "label": "Strom Warmwasser", "einheit": "kWh",
            "bedingung": "getrennte_strommessung",
            "csv_suffix": "Strom_Warmwasser_kWh",
            "hinweis": "Elektrische Energie für die Warmwasserbereitung (kWh, kumulativ oder Tagessensor). Nur bei getrennter Strommessung.",
        },
        # Immer vorhanden:
        # #120: Wording-Schaerfung — abgegebene thermische Waerme, nicht Strom.
        # CSV-Suffix bleibt fuer Backwards-Kompat unveraendert.
        {
            "feld": "heizenergie_kwh", "label": "Heizwärme", "einheit": "kWh",
            "csv_suffix": "Heizung_kWh",
            "hinweis": "Abgegebene Heizwärme (thermisch, NICHT Strom!) in kWh, kumulativ oder Tagessensor. Ohne Wärmemengenzähler aus Stromverbrauch × JAZ berechnet.",
        },
        {
            "feld": "warmwasser_kwh", "label": "Warmwasser", "einheit": "kWh",
            "csv_suffix": "Warmwasser_kWh",
            "hinweis": "Abgegebene Warmwasser-Wärme (thermisch) in kWh, kumulativ oder Tagessensor. Optional — sonst in der Heizwärme enthalten.",
        },
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

    "balkonkraftwerk": [
        {
            "feld": "pv_erzeugung_kwh", "label": "Erzeugung", "einheit": "kWh",
            "csv_suffix": "Erzeugung_kWh",
            "csv_suffix_alt": "kWh",  # Rückwärtskompatibilität
            "aggregiert_in": "pv_erzeugung_sum",
            "hinweis": "Kumulativer kWh-Zähler (oder Tagessensor) der BKW-Erzeugung vom Wechselrichter. Immer ≥ 0.",
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
         "hinweis": "Momentane elektrische Leistungsaufnahme der Wärmepumpe in W "
                    "(nicht die abgegebene Wärmeleistung)."},
        {"key": "leistung_heizen_w",       "label": "Leistung Heizen",      "einheit": "W",
         "hinweis": "Elektrische Leistungsaufnahme im Heizbetrieb in W. Nur sinnvoll, wenn "
                    "Heizen und Warmwasser getrennt gemessen werden."},
        {"key": "leistung_warmwasser_w",   "label": "Leistung Warmwasser",  "einheit": "W",
         "hinweis": "Elektrische Leistungsaufnahme der Warmwasserbereitung in W. Nur "
                    "sinnvoll bei getrennter Messung."},
        {"key": "warmwasser_temperatur_c", "label": "Warmwasser-Temperatur","einheit": "°C",
         "hinweis": "Temperatur im Warmwasserspeicher in °C — reine Anzeige, geht in keine "
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
    ("wechselrichter", "pv_erzeugung_kwh"): ("pflicht", "pv_energie"),
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
    ("waermepumpe", "heizenergie_kwh"): ("pflicht", None),
    ("waermepumpe", "warmwasser_kwh"): ("optional", None),
    ("waermepumpe", "leistung_w"): ("optional", None),
    ("waermepumpe", "leistung_heizen_w"): ("optional", None),
    ("waermepumpe", "leistung_warmwasser_w"): ("optional", None),
    ("waermepumpe", "warmwasser_temperatur_c"): ("optional", None),

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


def get_feld_bedarf(typ: str, feld: str) -> tuple[str, Optional[str]]:
    """Bedarf + Alternativ-Gruppe eines Felds — siehe {@link FELD_BEDARF}."""
    return FELD_BEDARF.get((typ, feld), FELD_BEDARF_DEFAULT)


# Typen mit SoC-Live-Sensor (aus LIVE_FELDER_INV abgeleitet)
SOC_TYPEN: frozenset[str] = frozenset(
    typ for typ, felder in LIVE_FELDER_INV.items()
    if any(f["key"] == "soc" for f in felder)
)


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


def _bedingungs_werte(parameter: Optional[dict]) -> dict[str, bool]:
    """Die Bedingungs-Keys einer Investition — eine Auswertung für alle Feld-Wege.

    Dieselben Keys steuern `bedingung` (Feld zeigen?) und `label_wenn` (wie heißt
    es dann?). Beide Wege lesen sie hier, damit die Zuordnungs-Fläche kein zweites,
    abweichendes Bild bekommt.
    """
    params = parameter or {}
    arbitrage_faehig = bool(params.get("arbitrage_faehig"))
    return {
        "getrennte_strommessung": bool(params.get("getrennte_strommessung")),
        "arbitrage_faehig": arbitrage_faehig,
        # Arbitrage impliziert Netzladung — das Flag ist nur ein Erfassungs-Schalter,
        # die UI für `ladung_netz_kwh` muss auch ohne Arbitrage sichtbar sein können.
        "laedt_aus_netz": bool(params.get("laedt_aus_netz")) or arbitrage_faehig,
        "v2h_faehig": bool(params.get("v2h_faehig") or params.get("nutzt_v2h")),
        "hat_speicher": bool(params.get("hat_speicher")),
    }


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

    Returns:
        Liste von Feld-Dicts ohne "bedingung"-Keys (bereits aufgelöst)
    """
    params = parameter or {}
    alle_felder = INVESTITION_FELDER.get(typ, [])

    if isinstance(alle_felder, dict):
        # Sonstiges — Kategorie-abhängig
        kategorie = params.get("kategorie", "erzeuger")
        return get_felder_fuer_sonstiges(kategorie)

    # Anlage-Kontext vorberechnen (einmalig, nicht pro Feld)
    anlage_typen: set[str] = set()
    if anlage_investitionen is not None:
        anlage_typen = {getattr(i, "typ", None) for i in anlage_investitionen}

    result = []
    bedingungs_werte = _bedingungs_werte(params)
    getrennte_strommessung = bedingungs_werte["getrennte_strommessung"]
    arbitrage_faehig = bedingungs_werte["arbitrage_faehig"]
    laedt_aus_netz = bedingungs_werte["laedt_aus_netz"]
    v2h_faehig = bedingungs_werte["v2h_faehig"]
    hat_speicher = bedingungs_werte["hat_speicher"]

    # Steuer-Schlüssel — hier ausgewertet bzw. nur für die Zuordnungs-Fläche
    # relevant, gehören nicht in die Eingabe-Antwort.
    SKIP_KEYS = {"bedingung", "bedingung_anlage", "label_wenn", "nur_manuell"}

    for feld in alle_felder:
        bedingung = feld.get("bedingung")
        bedingung_anlage = feld.get("bedingung_anlage")

        # ── Anlage-Kontext-Bedingung ─────────────────────────────────────────
        # Hier wird gefiltert (Monatsabschluss/Import-Kontext). Die Datenquellen-
        # Fläche nutzt bewusst `get_alle_felder_fuer_investition` und wertet
        # `bedingung_anlage` selbst aus — sie muss ein bereits ZUGEORDNETES Feld
        # weiter zeigen, sonst verschwindet die Zuordnung unsichtbar und lässt
        # sich nicht mehr entfernen (`_bedarf_einstufung` in routes/datenquellen.py).
        if bedingung_anlage and anlage_investitionen is not None:
            if bedingung_anlage == "keine_pv_module" and "pv-module" in anlage_typen:
                continue  # Feld ausblenden: PV-Module separat erfasst
            if bedingung_anlage == "keine_wallbox" and "wallbox" in anlage_typen:
                continue  # Feld ausblenden: Wallbox ist kanonische Heimladungs-Quelle

        # ── Investment-Parameter-Bedingung ───────────────────────────────────
        if bedingung is None:
            pass  # immer zeigen
        elif bedingung == "getrennte_strommessung" and not getrennte_strommessung:
            continue
        elif bedingung == "!getrennte_strommessung" and getrennte_strommessung:
            continue
        elif bedingung == "arbitrage_faehig" and not arbitrage_faehig:
            continue
        elif bedingung == "laedt_aus_netz" and not laedt_aus_netz:
            continue
        elif bedingung == "v2h_faehig" and not v2h_faehig:
            continue
        elif bedingung == "hat_speicher" and not hat_speicher:
            continue

        aufgeloest = {k: v for k, v in feld.items() if k not in SKIP_KEYS}
        aufgeloest["label"] = _label_aufgeloest(feld, bedingungs_werte)
        result.append(aufgeloest)

    return result


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
        # Sonstiges — Kategorie-abhängig
        params = parameter or {}
        kategorie = params.get("kategorie", "erzeuger")
        return list(get_felder_fuer_sonstiges(kategorie))

    # Kopie je Feld: die Dicts sind Modul-Konstanten, ein direktes Setzen des
    # Labels würde die Definition für alle folgenden Aufrufe umschreiben.
    bedingungs_werte = _bedingungs_werte(parameter)
    return [
        {**feld, "label": _label_aufgeloest(feld, bedingungs_werte)}
        for feld in alle_felder
    ]


def get_basis_felder(
    hat_dynamischen_tarif: bool = False,
    aktive_inv_typen: Optional[set[str]] = None,
) -> list[dict]:
    """
    Gibt alle Basis-Felder für eine Anlage zurück (inkl. aufgelöster bedingter Felder).

    Kombiniert BASIS_FELDER + BEDINGTE_BASIS_FELDER, wobei letztere nur bei
    erfüllter Bedingung enthalten sind.

    Args:
        hat_dynamischen_tarif: True wenn die Anlage einen dynamischen Stromtarif hat
        aktive_inv_typen: Set der aktiven Investitionstypen (z.B. {"pv-module", "e-auto"})

    Returns:
        Liste von Feld-Dicts (ohne bedingung_basis-Key)
    """
    typen = aktive_inv_typen or set()
    result = list(BASIS_FELDER)

    for feld in BEDINGTE_BASIS_FELDER:
        bedingung = feld.get("bedingung_basis")
        if bedingung == "dynamischer_tarif" and not hat_dynamischen_tarif:
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


def get_felder_fuer_sonstiges(kategorie: str) -> list[dict]:
    """
    Gibt Felder für eine Sonstiges-Investition nach Kategorie zurück.

    Args:
        kategorie: "erzeuger", "verbraucher" oder "speicher"

    Returns:
        Liste von Feld-Dicts
    """
    sonstiges = INVESTITION_FELDER.get("sonstiges", {})
    return sonstiges.get(kategorie, sonstiges.get("erzeuger", []))


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
    result = []
    getrennte_strommessung = bool(params.get("getrennte_strommessung"))

    for feld in alle:
        bedingung = feld.get("bedingung")
        if bedingung is None:
            result.append({k: v for k, v in feld.items() if k != "bedingung"})
        elif bedingung == "getrennte_strommessung" and getrennte_strommessung:
            result.append({k: v for k, v in feld.items() if k != "bedingung"})
        elif bedingung == "!getrennte_strommessung" and not getrennte_strommessung:
            result.append({k: v for k, v in feld.items() if k != "bedingung"})

    return result


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


def get_sonstiges_verbrauch_kwh(data: dict) -> float:
    """Sonstiges-Verbraucher-Energie. Liest `verbrauch_sonstig_kwh` (kanonisch),
    Legacy-Fallback `verbrauch_kwh`.
    """
    if not data:
        return 0.0
    return float(data.get("verbrauch_sonstig_kwh") or data.get("verbrauch_kwh") or 0)


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
    """
    if not data:
        return 0.0
    if params and params.get("getrennte_strommessung"):
        return float(
            (data.get("strom_heizen_kwh") or 0) +
            (data.get("strom_warmwasser_kwh") or 0)
        )
    return float(
        data.get("stromverbrauch_kwh") or
        data.get("strom_kwh") or
        data.get("verbrauch_kwh") or 0
    )
