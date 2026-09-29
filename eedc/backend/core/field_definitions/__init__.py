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

Seit 18.09.2026 ein Paket (Vorlage 3 des Refactorings grosser Dateien, reiner Umzug):
``keys`` · ``registry`` · ``bedingungen`` · ``karten`` · ``auswahl`` · ``reader`` · ``wp_strom``.
Diese Fassade exportiert jeden bisherigen Namen weiter — private eingeschlossen, weil Tests sie importieren.
"""

from backend.core.field_definitions.keys import (  # noqa: F401 — Re-Export
    INNENGERAET_TRENNER,
    feld_je_innengeraet,
    basis_feld_key,
    innengeraet_id_von_feld,
    _je_innengeraet_keys,
    _mit_innengeraeten,
    resolve_legacy_key,
)
from backend.core.field_definitions.registry import (  # noqa: F401 — Re-Export
    BASIS_FELDER,
    BEDINGTE_BASIS_FELDER,
    OPTIONALE_FELDER,
    _BETRIEBSART_HINWEIS_STROM,
    _BETRIEBSART_HINWEIS_NUTZ,
    _BETRIEBSART_CSV,
    _betriebsart_felder,
    _BETRIEBSART_FELDER,
    _BETRIEBSART_STROM_FELDNAMEN,
    _BETRIEBSART_NUTZENERGIE_FELDNAMEN,
    INVESTITION_FELDER,
    LIVE_FELDER_INV,
    BASIS_LIVE_FELDER,
    BASIS_PREIS_FELDER,
    LEGACY_FELDNAMEN,
    IMPORT_SUMMEN_KEYS,
)
from backend.core.field_definitions.bedingungen import (  # noqa: F401 — Re-Export
    FELD_BEDARF,
    FELD_BEDARF_DEFAULT,
    BEDARF_GRUPPEN_ALTERNATIV,
    KLIMA_OHNE_WAERMEMENGE,
    get_feld_bedarf,
    feld_urteil,
    feld_herabgestuft,
    pflicht_felder_am_geraet,
    GERAETEKLASSEN_SCHLUESSEL,
    _ist_geraeteklasse,
    _bedingungs_werte,
    URTEIL_GILT,
    URTEIL_ERWEITERT,
    URTEIL_NEIN,
    BEDINGUNG_ANLAGE_VERDRAENGT,
    TYP_DIENSTLICHE_WALLBOX,
    anlage_typen_mit_kontext,
    bedingung_anlage_fuer,
    verdraengender_typ,
    bedingungs_urteil,
    bedingung_erfuellt,
    _WP_ACHSEN_FELD,
    WP_WAERME_ACHSEN_BEIDE,
    wp_waerme_achsen,
    groesse_gibt_es_am_geraet,
    _label_aufgeloest,
)
from backend.core.field_definitions.karten import (  # noqa: F401 — Re-Export
    SOC_TYPEN,
    ZUSTAND_LIVE_FELDER,
    ZUSTAND_FELD_KEYS,
    einheit_fuer,
    ist_zustand_feld,
    build_feld_labels,
    FELD_LABELS,
    build_feld_einheiten,
    FELD_EINHEITEN,
    _build_einheit_je_geraet,
    FELD_EINHEIT_JE_GERAET,
    _POWER_EINHEITEN,
    _ENERGY_EINHEITEN,
    einheit_klasse,
    _ZAEHLER_FELDER_OHNE_ENERGIE_EINHEIT,
    ist_zaehler_differenz_feld,
    _SNAPSHOT_AUSNAHMEN,
    _SNAPSHOT_KOMPATIBILITAET,
    _SNAPSHOT_OHNE_KOMPONENTEN_BEITRAG,
    kumulative_zaehler_felder_je_typ,
    stand_felder,
    STAND_FELDER,
    WETTER_FELDER,
    ist_stand_feld,
    ist_wetter_feld,
)
from backend.core.field_definitions.auswahl import (  # noqa: F401 — Re-Export
    get_feld_hinweise,
    get_felder_fuer_investition,
    get_alle_felder_fuer_investition,
    get_basis_felder,
    ALLE_MONATSDATEN_FELDNAMEN,
    SONSTIGES_KATEGORIE_UNGEPFLEGT,
    SONSTIGES_ZAEHLER_KATEGORIEN,
    SONSTIGES_ABGABE_KATEGORIE,
    ist_abgabe_kategorie,
    SONSTIGES_ABGABE_LABEL,
    ZAEHLERSTAND_FELD,
    ist_zaehler_kategorie,
    ist_gepflegte_sonstiges_kategorie,
    _sonstiges_felder_ungepflegt,
    get_felder_fuer_sonstiges,
    SONSTIGES_FELDER_UNGEPFLEGT,
    get_live_felder_fuer_investition,
)
from backend.core.field_definitions.reader import (  # noqa: F401 — Re-Export
    get_pv_erzeugung_kwh,
    get_wp_heizenergie_kwh,
    get_wp_warmwasser_kwh,
    hat_wp_warmwasser_wert,
    get_eauto_ladung_kwh,
    get_speicher_netzladung_kwh,
    get_emob_pv_netz_kwh,
    SONSTIGES_VERBRAUCH_FELDER,
    sonstiges_feld_reihenfolge,
    get_sonstiges_verbrauch_kwh,
)
from backend.core.field_definitions.heimladung import (  # noqa: F401 — Re-Export
    HEIMLADE_FELDER,
    HEIMLADE_MENGEN_FELDER,
    ist_heimlade_feld,
    ist_heimlade_mengen_feld,
    traegt_heimlade_wert,
    ALTWERT_HERKUNFT,
    HERKUNFT_LADUNG_KWH,
    herkunft_quelle,
    ist_heim_gesamt,
)
from backend.core.field_definitions.wp_strom import (  # noqa: F401 — Re-Export
    FEINE_STROM_FELDER,
    WP_GESAMT_STROM_FELDER,
    feine_strom_achsen,
    WP_STROM_TOLERANZ_ANTEIL,
    WP_STROM_TOLERANZ_MIN_MONAT_KWH,
    WP_STROM_TOLERANZ_MIN_TAG_KWH,
    wp_strom_toleranz_kwh,
    wp_strom_stufe,
    wp_feine_summe_kwh,
    wp_nicht_aufgeteilt_kwh,
    WpStromAufteilung,
    wp_strom_aufteilung,
    nenner_ist_feine_summe,
    get_wp_strom_kwh,
)

__all__ = [
    'INNENGERAET_TRENNER',
    'feld_je_innengeraet',
    'basis_feld_key',
    'innengeraet_id_von_feld',
    '_je_innengeraet_keys',
    '_mit_innengeraeten',
    'resolve_legacy_key',
    'BASIS_FELDER',
    'BEDINGTE_BASIS_FELDER',
    'OPTIONALE_FELDER',
    '_BETRIEBSART_HINWEIS_STROM',
    '_BETRIEBSART_HINWEIS_NUTZ',
    '_BETRIEBSART_CSV',
    '_betriebsart_felder',
    '_BETRIEBSART_FELDER',
    '_BETRIEBSART_STROM_FELDNAMEN',
    '_BETRIEBSART_NUTZENERGIE_FELDNAMEN',
    'INVESTITION_FELDER',
    'LIVE_FELDER_INV',
    'BASIS_LIVE_FELDER',
    'BASIS_PREIS_FELDER',
    'LEGACY_FELDNAMEN',
    'IMPORT_SUMMEN_KEYS',
    'FELD_BEDARF',
    'FELD_BEDARF_DEFAULT',
    'BEDARF_GRUPPEN_ALTERNATIV',
    'KLIMA_OHNE_WAERMEMENGE',
    'get_feld_bedarf',
    'feld_urteil',
    'feld_herabgestuft',
    'pflicht_felder_am_geraet',
    'GERAETEKLASSEN_SCHLUESSEL',
    '_ist_geraeteklasse',
    '_bedingungs_werte',
    'URTEIL_GILT',
    'URTEIL_ERWEITERT',
    'URTEIL_NEIN',
    'BEDINGUNG_ANLAGE_VERDRAENGT',
    'TYP_DIENSTLICHE_WALLBOX',
    'anlage_typen_mit_kontext',
    'bedingung_anlage_fuer',
    'verdraengender_typ',
    'bedingungs_urteil',
    'bedingung_erfuellt',
    '_WP_ACHSEN_FELD',
    'WP_WAERME_ACHSEN_BEIDE',
    'wp_waerme_achsen',
    'groesse_gibt_es_am_geraet',
    '_label_aufgeloest',
    'SOC_TYPEN',
    'ZUSTAND_LIVE_FELDER',
    'ZUSTAND_FELD_KEYS',
    'einheit_fuer',
    'ist_zustand_feld',
    'build_feld_labels',
    'FELD_LABELS',
    'build_feld_einheiten',
    'FELD_EINHEITEN',
    '_build_einheit_je_geraet',
    'FELD_EINHEIT_JE_GERAET',
    '_POWER_EINHEITEN',
    '_ENERGY_EINHEITEN',
    'einheit_klasse',
    '_ZAEHLER_FELDER_OHNE_ENERGIE_EINHEIT',
    'ist_zaehler_differenz_feld',
    '_SNAPSHOT_AUSNAHMEN',
    '_SNAPSHOT_KOMPATIBILITAET',
    '_SNAPSHOT_OHNE_KOMPONENTEN_BEITRAG',
    'kumulative_zaehler_felder_je_typ',
    'stand_felder',
    'STAND_FELDER',
    'WETTER_FELDER',
    'ist_stand_feld',
    'ist_wetter_feld',
    'get_feld_hinweise',
    'get_felder_fuer_investition',
    'get_alle_felder_fuer_investition',
    'get_basis_felder',
    'ALLE_MONATSDATEN_FELDNAMEN',
    'SONSTIGES_KATEGORIE_UNGEPFLEGT',
    'SONSTIGES_ZAEHLER_KATEGORIEN',
    'SONSTIGES_ABGABE_KATEGORIE',
    'ist_abgabe_kategorie',
    'SONSTIGES_ABGABE_LABEL',
    'ZAEHLERSTAND_FELD',
    'ist_zaehler_kategorie',
    'ist_gepflegte_sonstiges_kategorie',
    '_sonstiges_felder_ungepflegt',
    'get_felder_fuer_sonstiges',
    'SONSTIGES_FELDER_UNGEPFLEGT',
    'get_live_felder_fuer_investition',
    'get_pv_erzeugung_kwh',
    'get_wp_heizenergie_kwh',
    'get_wp_warmwasser_kwh',
    'hat_wp_warmwasser_wert',
    'get_eauto_ladung_kwh',
    'get_speicher_netzladung_kwh',
    'get_emob_pv_netz_kwh',
    'HEIMLADE_FELDER',
    'HEIMLADE_MENGEN_FELDER',
    'ist_heimlade_feld',
    'ist_heimlade_mengen_feld',
    'traegt_heimlade_wert',
    'ALTWERT_HERKUNFT',
    'HERKUNFT_LADUNG_KWH',
    'herkunft_quelle',
    'ist_heim_gesamt',
    'SONSTIGES_VERBRAUCH_FELDER',
    'sonstiges_feld_reihenfolge',
    'get_sonstiges_verbrauch_kwh',
    'FEINE_STROM_FELDER',
    'WP_GESAMT_STROM_FELDER',
    'feine_strom_achsen',
    'WP_STROM_TOLERANZ_ANTEIL',
    'WP_STROM_TOLERANZ_MIN_MONAT_KWH',
    'WP_STROM_TOLERANZ_MIN_TAG_KWH',
    'wp_strom_toleranz_kwh',
    'wp_strom_stufe',
    'wp_feine_summe_kwh',
    'wp_nicht_aufgeteilt_kwh',
    'WpStromAufteilung',
    'wp_strom_aufteilung',
    'nenner_ist_feine_summe',
    'get_wp_strom_kwh',
]
