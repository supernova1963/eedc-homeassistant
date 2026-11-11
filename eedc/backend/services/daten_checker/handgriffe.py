"""
Daten-Checker — Katalog der Handgriffe (Etappe E2 des Vorhabens «Daten-Checker: ein Handgriff je Befund», Konzept §3.1
R2/R3, §3.4; Erhebung `erhebung-daten-checker-befunde-2026-11-10.md` Teil B = Quelle jeder Zeile).

Je Befund-Schlüssel (`CheckErgebnis.code`, Wächter W-1) genau eine Zeile: die **Soll-Klasse** aus Teil B, der Knopf-Text
(Verb in Anwender-Sprache, keine Mechanik-Wörter), der Handbuch-Anker (`docs/HANDBUCH_DATEN_CHECKER.md`, bis E5 der
Abschnitt der Kategorie) und — nur für Auskünfte mit WARNING/ERROR — der Allowlist-Grund (Konzept §3.4, Wächter W-6:
genau zwei). Die Laufzeit-Klasse eines Befunds ist **abgeleitet** (`CheckErgebnis.klasse`: Aktion · Sprung · Auskunft);
bis E3/E4 behalten die Erzeuger ihr heutiges Verhalten, die Soll-Klasse steht nur hier.

**182 Codes seit E5** (Konzept §6): 194 Erzeuger − 6 Zusammenlegungen (V3: der Partner-Erzeuger ist entfallen, seine Zahlen
steht in der Zeile des Ziel-Codes) − 6 Restzeilen «… plus n weitere» (V2: entfallen, n steht als `weitere` in der
Gruppenzeile, `GRUPPEN`). Je Klasse: Sprung 117 · Aktion 18 · Auskunft 17 · OK 30.

`knopf_fuer` liefert den Knopf-Text der **Laufzeit**-Klasse (E5.7 L1): Aktion aus der Operation (`KNOPF_JE_OPERATION`),
Sprung aus dem Katalog (`knopf`, bei einem Aktion-Code im Zweig ohne Reparaturweg `knopf_sprung`), Auskunft «Was gilt».
"""

from dataclasses import dataclass
from typing import Optional

AKTION = "aktion"
SPRUNG = "sprung"
AUSKUNFT = "auskunft"
OK = "ok"
KLASSEN = (AKTION, SPRUNG, AUSKUNFT, OK)
#: Knopf-Text jeder Auskunft (Konzept §3.4): öffnet den Lösungsweg des Codes.
WAS_GILT = "Was gilt"


@dataclass(frozen=True)
class Handgriff:
    klasse: str
    knopf: Optional[str]
    handbuch_anker: Optional[str]
    allowlist_grund: Optional[str] = None
    #: E5 (E4 ⚑1, Master-Entscheid): Knopf eines Aktion-Codes, wenn der Erzeuger im Zweig ohne Reparaturweg auf das fehlende
    #: Feld springt (Laufzeit-Klasse Sprung).
    knopf_sprung: Optional[str] = None


#: Auskunft trotz WARNING/ERROR — genau diese zwei, mit Grund (Konzept §3.4; ein dritter Eintrag ist rot, W-6).
ALLOWLIST_AUSKUNFT_WARNUNG = ("pv_zaehler_steht", "zaehlerstand_reihe_bruch")

HANDGRIFFE: dict[str, Handgriff] = {
    'connector_monatswert_fehlt': Handgriff(SPRUNG, 'Zum Connector', '411-geraete-connector-ohne-monatswert'),  # Nr 1
    'ha_zaehler_rueckgang': Handgriff(AKTION, 'Aus Home Assistant neu übernehmen', '48c-zaehlerstaende--rueckgang-in-home-assistant'),  # Nr 2
    'ha_zaehlersprung': Handgriff(AKTION, 'Aus Home Assistant neu übernehmen', '48b-zaehlerstaende--sprung-in-home-assistant'),  # Nr 3
    'klima_modus_wert_unbekannt': Handgriff(AUSKUNFT, 'Was gilt', '414a-betriebsmodus--unbekannter-wert'),  # Nr 4
    'klima_kuehlanteil_geschaetzt': Handgriff(SPRUNG, 'Sensor zuordnen', '414-klimaanlage--betriebsmodus'),  # Nr 5
    'klima_modus_ok': Handgriff(OK, None, '414-klimaanlage--betriebsmodus'),  # Nr 6
    'klima_modus_quellen_mehrdeutig': Handgriff(SPRUNG, 'Zuordnung prüfen', '414-klimaanlage--betriebsmodus'),  # Nr 7
    'klima_modus_nicht_zugeordnet': Handgriff(SPRUNG, 'Sensor zuordnen', '414-klimaanlage--betriebsmodus'),  # Nr 8
    'messpunkt_anlagenzaehler_vs_strings': Handgriff(SPRUNG, 'Zur Zuordnung', '48d-pv--messpunkt'),  # Nr 9
    'messpunkt_bkw_nicht_im_anlagenzaehler': Handgriff(SPRUNG, 'Zur Zuordnung', '48d-pv--messpunkt'),  # Nr 10
    'messpunkt_zaehler_mehr_als_strings': Handgriff(SPRUNG, 'Zur Zuordnung', '48d-pv--messpunkt'),  # Nr 11
    'messpunkt_dc_speicher': Handgriff(SPRUNG, 'Gerät bearbeiten', '48d-pv--messpunkt'),  # Nr 12
    'messpunkt_pv_gesamt_inkl_bkw': Handgriff(AUSKUNFT, 'Was gilt', '48d-pv--messpunkt'),  # Nr 13
    'messpunkt_volleinspeisung_ac_zaehler_fehlt': Handgriff(SPRUNG, 'Sensor zuordnen', '48d-pv--messpunkt'),  # Nr 14
    'provenance_ok': Handgriff(OK, None, '416-quellen-konflikte'),  # Nr 15
    'provenance_konflikte': Handgriff(AUSKUNFT, 'Was gilt', '416-quellen-konflikte'),  # Nr 16
    'datenquelle_ha_lts_ok': Handgriff(OK, None, '49a-datenquellen--status'),  # Nr 17
    'datenquelle_kanal_ok': Handgriff(OK, None, '49a-datenquellen--status'),  # Nr 18
    'datenquelle_noch_keine_tageswerte': Handgriff(AUSKUNFT, 'Was gilt', '49a-datenquellen--status'),  # Nr 19
    'datenquelle_aggregate_aeltere_quelle': Handgriff(AKTION, 'Tage neu aufbauen', '49a-datenquellen--status'),  # Nr 20
    'betriebsart_standalone': Handgriff(AUSKUNFT, 'Was gilt', '49a-datenquellen--status'),  # Nr 21
    'drift_ok': Handgriff(OK, None, '417-datenquellen-drift'),  # Nr 22
    'drift_tag': Handgriff(AKTION, 'Aus Home Assistant neu übernehmen', '417-datenquellen-drift'),  # Nr 24
    'drift_komponente': Handgriff(AKTION, 'Aus Home Assistant neu übernehmen', '417-datenquellen-drift'),  # Nr 25
    'zaehler_ruecksprung': Handgriff(SPRUNG, 'Sensor wechseln', '48a-zaehlerstaende--ruecksprung'),  # Nr 26
    'batterie_vorzeichen_ok': Handgriff(OK, None, '421-batterie-vorzeichen-historie'),  # Nr 27
    'batterie_vorzeichen_tage': Handgriff(AKTION, 'Tage neu aufbauen', '421-batterie-vorzeichen-historie'),  # Nr 28
    'batterie_vorzeichen_tag': Handgriff(AKTION, 'Tag neu aufbauen', '421-batterie-vorzeichen-historie'),  # Nr 29
    'soc_ok': Handgriff(OK, None, '422-ladestand-mehrere-speicher'),  # Nr 31
    'soc_nur_ein_speicher_tage': Handgriff(AKTION, 'Tage neu aufbauen', '422-ladestand-mehrere-speicher'),  # Nr 32
    'tageswerte_ok': Handgriff(OK, None, '410-energieprofil--fehlende-tageswerte'),  # Nr 33
    'tageswerte_fehlen_tage': Handgriff(AKTION, 'Tage neu aufbauen', '410-energieprofil--fehlende-tageswerte', knopf_sprung='Sensor zuordnen'),  # Nr 35
    'tageswerte_fehlen_tag': Handgriff(AKTION, 'Tag neu aufbauen', '410-energieprofil--fehlende-tageswerte'),  # Nr 36
    'pv_zaehler_steht': Handgriff(AUSKUNFT, 'Was gilt', '48e-pv--zaehler-steht', 'Entscheid Gernot (N-662): die Anzeige bleibt, der Befund benennt die Ursache — Sensor oder Gerät prüfen; eedc kann den eingefrorenen Zähler nicht heilen (Konzept §3.4).'),  # Nr 38
    'zeitzone_abweichung': Handgriff(SPRUNG, 'Zum Neustart', '412-zeitzone--abweichung-zu-home-assistant'),  # Nr 39
    'emob_autos_mehr_als_wallbox': Handgriff(SPRUNG, 'Monat öffnen', '439-heimladung-je-auto'),  # Nr 40
    'emob_dienstwagen_heimladung_fehlt': Handgriff(SPRUNG, 'Monat öffnen', '439-heimladung-je-auto'),  # Nr 41
    'emob_pv_ladung_groesser_gesamt': Handgriff(SPRUNG, 'Monat öffnen', '45-monatsdaten--plausibilitaet'),  # Nr 42
    'phev_anteil_unbestimmt': Handgriff(SPRUNG, 'Gerät bearbeiten', '420-phev-anteil'),  # Nr 44
    'emob_gleicher_sensor_wallbox_eauto': Handgriff(SPRUNG, 'Zuordnung prüfen', '439-heimladung-je-auto'),  # Nr 45
    'emob_doppelzaehlung_ok': Handgriff(OK, None, '419-ladung-doppelt-gezaehlt'),  # Nr 46
    'emob_doppelzaehlung_tage': Handgriff(AKTION, 'Tage neu aufbauen', '419-ladung-doppelt-gezaehlt'),  # Nr 47
    'vergleichspreis_ok': Handgriff(OK, None, '424-vergleichspreise-benzinpreis'),  # Nr 48
    'vergleichspreis_fehlt': Handgriff(AKTION, 'Benzinpreise nachtragen', '424-vergleichspreise-benzinpreis'),  # Nr 49
    'emob_zustand_wert_unbekannt': Handgriff(AUSKUNFT, 'Was gilt', '426-e-mobilitaet--unbekannter-zustand'),  # Nr 50
    'emob_kennung_unbekannt': Handgriff(SPRUNG, 'Kennung eintragen', '427-e-mobilitaet--fahrzeug-unbekannt'),  # Nr 51
    'basis_zaehler_manuell_ok': Handgriff(OK, None, '46-energieprofil--zaehler-abdeckung'),  # Nr 52
    'basis_zaehler_fehlt': Handgriff(SPRUNG, 'Sensor zuordnen', '46-energieprofil--zaehler-abdeckung'),  # Nr 53
    'basis_zaehler_ok': Handgriff(OK, None, '46-energieprofil--zaehler-abdeckung'),  # Nr 54
    'komponenten_ohne_zaehler': Handgriff(SPRUNG, 'Sensor zuordnen', '46-energieprofil--zaehler-abdeckung'),  # Nr 55
    'bkw_ueber_module_ok': Handgriff(OK, None, '46-energieprofil--zaehler-abdeckung'),  # Nr 56
    'komponenten_zaehler_ok': Handgriff(OK, None, '46-energieprofil--zaehler-abdeckung'),  # Nr 57
    'erzeuger_ueber_anlagenzaehler_ok': Handgriff(OK, None, '46-energieprofil--zaehler-abdeckung'),  # Nr 58
    'komponenten_manuell_ok': Handgriff(OK, None, '46-energieprofil--zaehler-abdeckung'),  # Nr 59
    'komponenten_ohne_zusatzzaehler': Handgriff(SPRUNG, 'Sensor zuordnen', '46-energieprofil--zaehler-abdeckung'),  # Nr 60
    'tage_vor_umbau_ohne_regelmarke': Handgriff(AKTION, 'Tage neu aufbauen', '46-energieprofil--zaehler-abdeckung', knopf_sprung='Sensor zuordnen'),  # Nr 61
    'tage_ohne_kanal_deckung': Handgriff(AUSKUNFT, 'Was gilt', '46-energieprofil--zaehler-abdeckung'),  # Nr 62
    'einspeisung_groesser_erzeugung_tage': Handgriff(AKTION, 'Tage neu aufbauen', '47-energieprofil--plausibilitaet'),  # Nr 63
    'nachtrag_nach_eingefrorenem_zaehler': Handgriff(AUSKUNFT, 'Was gilt', '47-energieprofil--plausibilitaet'),  # Nr 64
    'counter_spikes_ok': Handgriff(OK, None, '47-energieprofil--plausibilitaet'),  # Nr 65
    'counter_spike_tag': Handgriff(AKTION, 'Tag neu aufbauen', '47-energieprofil--plausibilitaet'),  # Nr 66
    'pv_erzeugung_fehlt_monate': Handgriff(SPRUNG, 'Monat öffnen', '43-investitionen'),  # Nr 67
    'pv_erzeugung_unvollstaendig': Handgriff(SPRUNG, 'Monat öffnen', '43-investitionen'),  # Nr 68
    'pv_erzeugung_geschaetzt': Handgriff(AUSKUNFT, 'Was gilt', '43-investitionen'),  # Nr 69
    'pv_erzeugung_ok': Handgriff(OK, None, '43-investitionen'),  # Nr 70
    'pv_ueber_erfassung_spike_ueberdeckt': Handgriff(AUSKUNFT, 'Was gilt', '418-pv-doppelerfassung'),  # Nr 71
    'pv_ueber_erfassung_verdacht': Handgriff(SPRUNG, 'Zur Zuordnung', '418-pv-doppelerfassung'),  # Nr 72
    'geraetewerte_ohne_monatszeile': Handgriff(SPRUNG, 'Monat erfassen', '44a-messwerte-ohne-monatszeile'),  # Nr 73
    'keine_monatsdaten': Handgriff(SPRUNG, 'Monat erfassen', '44-monatsdaten--vollstaendigkeit'),  # Nr 74
    'monate_vollstaendig_ok': Handgriff(OK, None, '44-monatsdaten--vollstaendigkeit'),  # Nr 75
    'monat_fehlt': Handgriff(SPRUNG, 'Monat erfassen', '44-monatsdaten--vollstaendigkeit'),  # Nr 76
    'monatsdaten_plausi_ok': Handgriff(OK, None, '45-monatsdaten--plausibilitaet'),  # Nr 78
    'geraet_feld_fehlt_monate': Handgriff(SPRUNG, 'Monat öffnen', '43-investitionen'),  # Nr 79
    'geraet_monate_ok': Handgriff(OK, None, '43-investitionen'),  # Nr 80
    'feldwert_nicht_gefuehrt': Handgriff(AKTION, 'Wert entfernen', '43-investitionen'),  # Nr 81
    'wp_heiz_kuehl_groesser_gesamt': Handgriff(SPRUNG, 'Monat öffnen', '43-investitionen'),  # Nr 82
    'wp_gesamtwaerme_kleiner_teile': Handgriff(SPRUNG, 'Monat öffnen', '43-investitionen'),  # Nr 83
    'wp_waerme_gesamt_null': Handgriff(SPRUNG, 'Monat öffnen', '43-investitionen'),  # Nr 84
    'wp_gesamtzaehler_kleiner_achsen': Handgriff(SPRUNG, 'Monat öffnen', '43-investitionen'),  # Nr 85
    'wp_gesamtzaehler_mehr_als_achsen': Handgriff(SPRUNG, 'Zuordnung prüfen', '43-investitionen'),  # Nr 86
    'wp_strom_fehlt_monate': Handgriff(SPRUNG, 'Monat öffnen', '43-investitionen'),  # Nr 87
    'wp_seite_fehlt_monate': Handgriff(SPRUNG, 'Monat öffnen', '43-investitionen'),  # Nr 88
    'wp_heizwaerme_fehlt_monate': Handgriff(SPRUNG, 'Monat öffnen', '43-investitionen'),  # Nr 89
    'wp_monate_ok': Handgriff(OK, None, '43-investitionen'),  # Nr 90
    'monatsabschluss_hinweis_geraet': Handgriff(SPRUNG, 'Monat öffnen', '43-investitionen'),  # Nr 91
    'wetterreihe_nachziehen': Handgriff(AKTION, 'Wetterreihe nachziehen', '425-wetterwerte-fehlende-monatswerte'),  # Nr 92
    'temperatur_ok': Handgriff(OK, None, '425-wetterwerte-fehlende-monatswerte'),  # Nr 95
    'temperatur_fehlt_ohne_messreihe': Handgriff(SPRUNG, 'Monat öffnen', '425-wetterwerte-fehlende-monatswerte'),  # Nr 96
    'temperatur_aus_messung_moeglich': Handgriff(AKTION, 'Temperatur aus Messung übernehmen', '425-wetterwerte-fehlende-monatswerte'),  # Nr 97
    'position_doppelerfassung': Handgriff(SPRUNG, 'Gerät bearbeiten', '413-sonstige-positionen--der-erfassungsort'),  # Nr 98
    'position_wiederkehrend': Handgriff(SPRUNG, 'Gerät bearbeiten', '413-sonstige-positionen--der-erfassungsort'),  # Nr 99
    'md_feld_nicht_erfasst': Handgriff(SPRUNG, 'Monat öffnen', '45-monatsdaten--plausibilitaet'),  # Nr 100
    'md_batterie_ladung_fehlt': Handgriff(SPRUNG, 'Monat öffnen', '45-monatsdaten--plausibilitaet'),  # Nr 101
    'md_batterie_entladung_fehlt': Handgriff(SPRUNG, 'Monat öffnen', '45-monatsdaten--plausibilitaet'),  # Nr 102
    'md_geraet_entladung_fehlt': Handgriff(SPRUNG, 'Monat öffnen', '45-monatsdaten--plausibilitaet'),  # Nr 103
    'md_feld_negativ': Handgriff(SPRUNG, 'Monat öffnen', '45-monatsdaten--plausibilitaet'),  # Nr 104
    'md_pv_ungewoehnlich_hoch': Handgriff(SPRUNG, 'Monat öffnen', '45-monatsdaten--plausibilitaet'),  # Nr 105
    'md_einspeisung_netzbezug_null': Handgriff(SPRUNG, 'Monat öffnen', '45-monatsdaten--plausibilitaet'),  # Nr 106
    'md_negativer_gesamtverbrauch': Handgriff(SPRUNG, 'Monat öffnen', '45-monatsdaten--plausibilitaet'),  # Nr 107
    'md_einspeisung_groesser_pv': Handgriff(SPRUNG, 'Monat öffnen', '45-monatsdaten--plausibilitaet'),  # Nr 108
    'md_mehr_pv_verwendet_als_erzeugt': Handgriff(SPRUNG, 'Monat öffnen', '45-monatsdaten--plausibilitaet'),  # Nr 109
    'md_feld_dreifach_vorjahr': Handgriff(SPRUNG, 'Monat öffnen', '45-monatsdaten--plausibilitaet'),  # Nr 110
    'sensor_ohne_langzeitstatistik': Handgriff(AUSKUNFT, 'Was gilt', '415a-sensor-ohne-langzeitstatistik'),  # Nr 111
    'mqtt_subscriber_laeuft_nicht': Handgriff(SPRUNG, 'Zur Verbindung', '48-mqtt-topic-abdeckung'),  # Nr 112
    'mqtt_topics_nie_empfangen': Handgriff(SPRUNG, 'Topics prüfen', '48-mqtt-topic-abdeckung'),  # Nr 113
    'mqtt_topics_veraltet': Handgriff(SPRUNG, 'Topics prüfen', '48-mqtt-topic-abdeckung'),  # Nr 114
    'mqtt_ok': Handgriff(OK, None, '48-mqtt-topic-abdeckung'),  # Nr 115
    'kwh_sensoren_nicht_in_lts': Handgriff(SPRUNG, 'Anderen Sensor wählen', '49-sensor-mapping--ha-statistics'),  # Nr 117
    'counter_ohne_state_class': Handgriff(SPRUNG, 'Anderen Sensor wählen', '49-sensor-mapping--ha-statistics'),  # Nr 118
    'kwh_ohne_summen_spalte': Handgriff(SPRUNG, 'Anderen Sensor wählen', '49-sensor-mapping--ha-statistics'),  # Nr 119
    'counter_ohne_summen_spalte': Handgriff(SPRUNG, 'Anderen Sensor wählen', '49-sensor-mapping--ha-statistics'),  # Nr 120
    'stand_sensoren_nicht_in_lts': Handgriff(SPRUNG, 'Anderen Sensor wählen', '49-sensor-mapping--ha-statistics'),  # Nr 121
    'stand_sensoren_ok': Handgriff(OK, None, '49-sensor-mapping--ha-statistics'),  # Nr 122
    'leistungs_slot_energie_sensor': Handgriff(SPRUNG, 'Sensor wechseln', '415-sensor-zuordnung--leistung--energie'),  # Nr 124
    'energie_slot_leistungssensor': Handgriff(SPRUNG, 'Sensor wechseln', '415-sensor-zuordnung--leistung--energie'),  # Nr 125
    'installationsdatum_fehlt': Handgriff(SPRUNG, 'Anlage bearbeiten', '41-stammdaten'),  # Nr 126
    'installationsdatum_ok': Handgriff(OK, None, '41-stammdaten'),  # Nr 127
    'erzeuger_aelter_als_anlage': Handgriff(SPRUNG, 'Anlage bearbeiten', '41-stammdaten'),  # Nr 128
    'geraet_aelter_als_anlage': Handgriff(SPRUNG, 'Anlage bearbeiten', '41-stammdaten'),  # Nr 129
    'anlagenleistung_fehlt': Handgriff(SPRUNG, 'Anlage bearbeiten', '41-stammdaten'),  # Nr 130
    'anlagenleistung_ok': Handgriff(OK, None, '41-stammdaten'),  # Nr 131
    'standort_fehlt': Handgriff(SPRUNG, 'Anlage bearbeiten', '41-stammdaten'),  # Nr 132
    'keine_pv_module': Handgriff(SPRUNG, 'Komponente anlegen', '41-stammdaten'),  # Nr 134
    'pv_module_ok': Handgriff(OK, None, '41-stammdaten'),  # Nr 135
    'modul_details_passen_nicht': Handgriff(SPRUNG, 'Gerät bearbeiten', '41-stammdaten'),  # Nr 136
    'pvgis_systemverluste_hoch': Handgriff(SPRUNG, 'Prognose bearbeiten', '41-stammdaten'),  # Nr 137
    'anlagenleistung_passt_nicht_zu_modulen': Handgriff(SPRUNG, 'Anlage bearbeiten', '41-stammdaten'),  # Nr 138
    'wr_modulleistung_vielfach': Handgriff(SPRUNG, 'Gerät bearbeiten', '41-stammdaten'),  # Nr 139
    'kein_strompreis': Handgriff(SPRUNG, 'Tarif anlegen', '42-strompreise'),  # Nr 140
    'strompreise_ok': Handgriff(OK, None, '42-strompreise'),  # Nr 141
    'einspeisung_null_cent': Handgriff(SPRUNG, 'Tarif bearbeiten', '42-strompreise'),  # Nr 142
    'monate_vor_erstem_tarif': Handgriff(SPRUNG, 'Tarif bearbeiten', '42-strompreise'),  # Nr 143
    'strompreis_luecke': Handgriff(SPRUNG, 'Tarif anlegen', '42-strompreise'),  # Nr 144
    'zeittarif_ohne_stundenwerte': Handgriff(SPRUNG, 'Sensor zuordnen', '42-strompreise'),  # Nr 145
    'tarife_gleicher_tag': Handgriff(SPRUNG, 'Tarif bearbeiten', '42-strompreise'),  # Nr 146
    'wp_allgemeiner_tarif': Handgriff(AUSKUNFT, 'Was gilt', '42-strompreise'),  # Nr 147
    'kein_ladetarif': Handgriff(AUSKUNFT, 'Was gilt', '42-strompreise'),  # Nr 148
    'arbeitspreis_ungewoehnlich': Handgriff(SPRUNG, 'Tarif bearbeiten', '42-strompreise'),  # Nr 149
    'einspeiseverguetung_ungewoehnlich': Handgriff(SPRUNG, 'Tarif bearbeiten', '42-strompreise'),  # Nr 150
    'kapazitaet_wh_statt_kwh': Handgriff(SPRUNG, 'Gerät bearbeiten', '43-investitionen'),  # Nr 151
    'wp_strom_heizbetrieb_und_heizen_belegt': Handgriff(SPRUNG, 'Zuordnung prüfen', '43-investitionen'),  # Nr 152
    'wp_strom_zugeordnet_getrennte_messung_aus': Handgriff(SPRUNG, 'Gerät bearbeiten', '43-investitionen'),  # Nr 153
    'wr_pv_zuordnung_nicht_ausgewertet': Handgriff(SPRUNG, 'Zuordnung prüfen', '43-investitionen'),  # Nr 154
    'geraet_abgabe_an_dritte_frage': Handgriff(SPRUNG, 'Gerät bearbeiten', '43-investitionen'),  # Nr 155
    'akku_werte_nur_monatswert': Handgriff(SPRUNG, 'Sensor zuordnen', '43-investitionen'),  # Nr 156
    'keine_aktiven_investitionen': Handgriff(SPRUNG, 'Komponente anlegen', '43-investitionen'),  # Nr 157
    'pv_leistung_kwp_fehlt': Handgriff(SPRUNG, 'Gerät bearbeiten', '43-investitionen'),  # Nr 158
    'pv_ausrichtung_fehlt': Handgriff(SPRUNG, 'Gerät bearbeiten', '43-investitionen'),  # Nr 159
    'bkw_leistung_wp_fehlt': Handgriff(SPRUNG, 'Gerät bearbeiten', '43-investitionen'),  # Nr 160
    'wr_leistung_fehlt': Handgriff(SPRUNG, 'Gerät bearbeiten', '43-investitionen'),  # Nr 161
    'speicher_kapazitaet_fehlt': Handgriff(SPRUNG, 'Gerät bearbeiten', '43-investitionen'),  # Nr 162
    'arbitrage_ladepreis_fehlt': Handgriff(SPRUNG, 'Gerät bearbeiten', '43-investitionen'),  # Nr 163
    'arbitrage_entladepreis_fehlt': Handgriff(SPRUNG, 'Gerät bearbeiten', '43-investitionen'),  # Nr 164
    'speicher_netzladung_groesser_gesamt': Handgriff(SPRUNG, 'Jahresbilanz prüfen', '43-investitionen'),  # Nr 165
    'speicher_entladung_groesser_ladung': Handgriff(SPRUNG, 'Jahresbilanz prüfen', '43-investitionen'),  # Nr 166
    'eauto_fahrleistung_fehlt': Handgriff(SPRUNG, 'Gerät bearbeiten', '43-investitionen'),  # Nr 167
    'eauto_alternativkosten_fehlen': Handgriff(SPRUNG, 'Gerät bearbeiten', '43-investitionen'),  # Nr 168
    'wallbox_ladeleistung_fehlt': Handgriff(SPRUNG, 'Gerät bearbeiten', '43-investitionen'),  # Nr 169
    'geraet_leistung_kw_fehlt': Handgriff(SPRUNG, 'Gerät bearbeiten', '43-investitionen'),  # Nr 170
    'wp_alternativkosten_fehlen': Handgriff(SPRUNG, 'Gerät bearbeiten', '43-investitionen'),  # Nr 171
    'wp_jaz_fehlt': Handgriff(SPRUNG, 'Gerät bearbeiten', '43-investitionen'),  # Nr 172
    'wp_jaz_unplausibel': Handgriff(SPRUNG, 'Gerät bearbeiten', '43-investitionen'),  # Nr 173
    'wp_stammdatum_hinweis': Handgriff(SPRUNG, 'Gerät bearbeiten', '43-investitionen'),  # Nr 174
    'wp_alter_energiepreis_fehlt': Handgriff(SPRUNG, 'Gerät bearbeiten', '43-investitionen'),  # Nr 175
    'wp_heizwaermebedarf_fehlt': Handgriff(SPRUNG, 'Gerät bearbeiten', '43-investitionen'),  # Nr 176
    'wp_warmwasserbedarf_fehlt': Handgriff(SPRUNG, 'Gerät bearbeiten', '43-investitionen'),  # Nr 177
    'anschaffungsdatum_fehlt': Handgriff(SPRUNG, 'Gerät bearbeiten', '43-investitionen'),  # Nr 178
    'anschaffungskosten_fehlen': Handgriff(SPRUNG, 'Gerät bearbeiten', '43-investitionen'),  # Nr 179
    'wp_arbeitszahl_zu_hoch': Handgriff(SPRUNG, 'Monat öffnen', '45-monatsdaten--plausibilitaet'),  # Nr 180
    'wp_tarif_wallbox_netzbezug_zaehlt_nicht': Handgriff(SPRUNG, 'Tarif bearbeiten', '42a-eigener-waermepumpen-tarif'),  # Nr 182
    'paralleler_zaehler': Handgriff(SPRUNG, 'Zuordnung prüfen', '42a-eigener-waermepumpen-tarif'),  # Nr 183
    'evcc_netzladung_abweichung': Handgriff(SPRUNG, 'Zuordnung prüfen', '42a-eigener-waermepumpen-tarif'),  # Nr 184
    'eigener_tarif_vorrang': Handgriff(SPRUNG, 'Tarif bearbeiten', '42a-eigener-waermepumpen-tarif'),  # Nr 185
    'gemeinsamer_zaehler_tage_ohne_teilung': Handgriff(AUSKUNFT, 'Was gilt', '42a-eigener-waermepumpen-tarif'),  # Nr 186
    'wallbox_netzladung_groesser_gemeinsamer_netzbezug': Handgriff(SPRUNG, 'Zuordnung prüfen', '42a-eigener-waermepumpen-tarif'),  # Nr 187
    'wp_eigener_tarif_obergrenze': Handgriff(AUSKUNFT, 'Was gilt', '42a-eigener-waermepumpen-tarif'),  # Nr 188
    'tarif_mengenfeld_groesser_als_menge': Handgriff(SPRUNG, 'Zuordnung prüfen', '42a-eigener-waermepumpen-tarif'),  # Nr 189
    'tarif_mengenfeld_groesser_als_rest': Handgriff(SPRUNG, 'Zuordnung prüfen', '42a-eigener-waermepumpen-tarif'),  # Nr 190
    'zaehlerstand_ablesungen_ok': Handgriff(OK, None, '423-verbrauchszaehler-zaehlerstaende'),  # Nr 191
    'zaehlerstand_kein_stand': Handgriff(SPRUNG, 'Zählerstand erfassen', '423-verbrauchszaehler-zaehlerstaende'),  # Nr 192
    'zaehlerstand_reihe_bruch': Handgriff(AUSKUNFT, 'Was gilt', '423-verbrauchszaehler-zaehlerstaende', 'Konzept #377: drei Ursachen, drei Wege (Stilllegung/neuer Zähler im Formular · Sensorwechsel · Tage neu aufbauen über die Bruchstelle) — erklären, Weg daneben (Gegenprüfung Ü9).'),  # Nr 193
    'zaehler_nicht_aktiv': Handgriff(SPRUNG, 'Gerät bearbeiten', '423-verbrauchszaehler-zaehlerstaende'),  # Nr 194
}


def handgriff(code: Optional[str]) -> Optional[Handgriff]:
    """Katalog-Zeile eines Codes (None für einen Befund ohne Code)."""
    return HANDGRIFFE.get(code) if code else None


#: Knopf-Text je Operation einer Aktion (Etappe E3, Konzept §3.1 R4, Wächter W-4): Verb in Anwender-Sprache, keine
#: Mechanik-Wörter. Der Katalog führt je Code den Text seiner Teil-B-Operation; trägt ein Befund nach der Kanal-Lage-Weiche
#: (R7) eine andere Operation (Drift ohne Spiegel ⇒ Tag neu aufbauen), gilt der Text dieser Operation.
#: `CheckErgebnis.action_label` ist daraus abgeleitet.
KNOPF_JE_OPERATION: dict[str, str] = {
    "reaggregate_day": "Tag neu aufbauen",
    "reaggregate_range": "Tage neu aufbauen",
    "spiegel_abgleich_tag": "Aus Home Assistant neu übernehmen",
    "kraftstoffpreis_backfill": "Benzinpreise nachtragen",
    "wetter_backfill": "Wetterreihe nachziehen",
    "temperatur_aus_messung": "Temperatur aus Messung übernehmen",
    "feldwert_entfernen": "Wert entfernen",
}


def knopf_text(operation: Optional[str]) -> Optional[str]:
    """Knopf-Text einer Aktion (``None`` für eine Operation ohne Checker-Knopf)."""
    return KNOPF_JE_OPERATION.get(operation) if operation else None


def knopf_fuer(befund) -> Optional[str]:
    """Der Knopf-Text eines Befunds nach seiner Laufzeit-Klasse (E5.7 L1, ein Feld für alle drei Klassen): Aktion ⇒ Text
    der Operation; Sprung ⇒ Katalog-Text (`knopf_sprung` bei einem Aktion-Code ohne Reparaturweg); Auskunft ⇒ «Was gilt»;
    OK ⇒ kein Knopf. ``None`` bei einem Sprung ohne Katalog-Text — der Wächter W-4 macht das rot."""
    if getattr(befund.schwere, "value", befund.schwere) == "ok":
        return None
    if befund.action is not None:
        return knopf_text(befund.action.operation)
    if befund.ziel is not None:
        hg = handgriff(befund.code)
        if hg is None:
            return None
        return hg.knopf if hg.klasse == SPRUNG else hg.knopf_sprung
    return WAS_GILT


@dataclass(frozen=True)
class GruppenVorlage:
    """Wortlaut einer Gruppenzeile (E5 V2): ``titel`` mit ``{n}`` = Zahl der Befunde (Glieder + weitere); ``glied`` nennt,
    woraus das Glied entsteht (``datum`` aus ``werte.datum``, ``monat`` aus ``ziel.params.erfassen``); ``je`` trennt die
    Gruppen (``investition_id`` bzw. ``feld`` des Ziels)."""
    titel: str
    glied: str
    details: Optional[str] = None
    je: tuple[str, ...] = ()


#: Codes, deren Befunde die Oberfläche als **eine** Zeile mit Gliedern zeigt (Konzept §6 V2; Teil B «V2 Gruppe»). Die
#: Restzeilen der Erzeuger (Teil B Nr 23, 30, 37, 43, 77, 181) sind entfallen — ihre Zahl steht als ``werte.weitere``.
GRUPPEN: dict[str, GruppenVorlage] = {
    "monat_fehlt": GruppenVorlage(
        "{n} Monate fehlen", "monat",
        "Der Jahreswert und der Community-Vergleich bleiben ohne sie unvollständig. Ein Monat öffnet seine Erfassung."),
    "drift_tag": GruppenVorlage(
        "{n} Tage weichen von Home Assistant ab", "datum",
        "Ein Tag zeigt, was der Knopf an diesem Tag ändert; die größten Abweichungen stehen vorn."),
    "batterie_vorzeichen_tag": GruppenVorlage(
        "{n} Tage mit vertauschtem Batterie-Vorzeichen", "datum", "Ein Tag baut genau diesen Tag neu auf."),
    "tageswerte_fehlen_tag": GruppenVorlage(
        "{n} Tage ohne Tageswerte, Home Assistant hat Werte", "datum", "Ein Tag baut genau diesen Tag neu auf."),
    "emob_pv_ladung_groesser_gesamt": GruppenVorlage(
        "{n} Monate: PV-Ladung größer als Gesamtladung", "monat",
        "Ein Monat öffnet seine Erfassung am Feld der PV-Ladung.", je=("investition_id",)),
    "wp_arbeitszahl_zu_hoch": GruppenVorlage(
        "{n} Monate mit unplausibel hoher Arbeitszahl", "monat",
        "Ein Monat öffnet seine Erfassung an der Wärmemenge.", je=("investition_id",)),
    "md_feld_nicht_erfasst": GruppenVorlage(
        "{n} Monate ohne Pflichtwert", "monat", "Ein Monat öffnet seine Erfassung am fehlenden Feld.", je=("feld",)),
}

#: Wörter der Mechanik (Konzept §3.1 R4, Wächter W-4): verboten im Knopf-Text und in der einen Vorschau-Zeile je
#: Operation — erlaubt in den Werkbank-Warnungen, die der Vorschau-Kasten unverändert zeigt (Gegenprüfung Ü3).
MECHANIK_WOERTER = ("spiegel", "kanal", "lts", "statistics", "snapshot", "aggregier", "provenance", "resnap")
