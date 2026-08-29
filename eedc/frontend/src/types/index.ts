/**
 * eedc TypeScript Type Definitions
 */

// Versorger & Zähler Typen
export interface Zaehler {
  bezeichnung: string
  nummer: string
  notizen?: string
}

export interface Versorger {
  name: string
  kundennummer: string
  portal_url?: string
  notizen?: string
  zaehler: Zaehler[]
}

export interface VersorgerDaten {
  strom?: Versorger
  gas?: Versorger
  wasser?: Versorger
  [key: string]: Versorger | undefined  // Für weitere Versorgertypen
}

// Wetter-Provider
export type WetterProvider = 'auto' | 'open-meteo' | 'brightsky' | 'open-meteo-solar'

// Wettermodell für Solar-Prognose (Open-Meteo Forecast Model)
export type WetterModell =
  | 'auto'
  // Seamless (empfohlen — interne Kaskade bei Open-Meteo)
  | 'icon_seamless'
  | 'meteoswiss_seamless'
  | 'ecmwf_seamless'
  // Einzelmodelle
  | 'meteoswiss_icon_ch2'
  | 'icon_d2'
  | 'icon_eu'
  | 'ecmwf_ifs04'

// Prognosequelle pro Anlage
export type PrognoseQuelle = 'eedc' | 'solcast' | 'sfml'

// Steuerliche Behandlung
export type SteuerlicheBehandlung = 'keine_ust' | 'regelbesteuerung'

// Anlage
export interface Anlage {
  id: number
  anlagenname: string
  leistung_kwp: number
  installationsdatum?: string
  standort_land?: string
  standort_plz?: string
  standort_ort?: string
  standort_strasse?: string
  latitude?: number
  longitude?: number
  wechselrichter_hersteller?: string
  // Home Assistant Sensor-Konfiguration
  ha_sensor_pv_erzeugung?: string
  ha_sensor_einspeisung?: string
  ha_sensor_netzbezug?: string
  ha_sensor_batterie_ladung?: string
  ha_sensor_batterie_entladung?: string
  // Erweiterte Stammdaten
  mastr_id?: string
  versorger_daten?: VersorgerDaten | null
  // Wetterdaten-Provider
  wetter_provider?: WetterProvider
  // Wettermodell für Solar-Prognose
  wetter_modell?: WetterModell
  // Steuerliche Behandlung
  steuerliche_behandlung?: SteuerlicheBehandlung
  ust_satz_prozent?: number
  // §51 EEG: Wegfall der Einspeisevergütung in Negativpreis-Stunden (manueller Schalter)
  unterliegt_eeg_51?: boolean
  // Community-Sharing
  community_hash?: string | null
  community_auto_share?: boolean
  // Energiefluss-Anzeige
  netz_puffer_w?: number
  // Prognosequelle
  prognose_quelle?: PrognoseQuelle
  // Günstig-Schwelle der Börsenpreis-Sensoren (% unter Ø ohne 3 Peaks, Default 10)
  guenstig_schwelle_prozent?: number | null
}

// Sensor-Konfiguration
export interface SensorConfig {
  pv_erzeugung?: string
  einspeisung?: string
  netzbezug?: string
  batterie_ladung?: string
  batterie_entladung?: string
}

// Geocoding
export interface GeocodeResult {
  latitude: number
  longitude: number
  display_name: string
  /** Ländercode aus der Nominatim-Antwort (DE/AT/CH/IT), sonst null (#386). */
  erkanntes_land?: string | null
}

export type AnlageCreate = Omit<Anlage, 'id'>
export type AnlageUpdate = Partial<AnlageCreate>

// Monatsdaten
export interface Monatsdaten {
  id: number
  anlage_id: number
  jahr: number
  monat: number
  einspeisung_kwh: number
  netzbezug_kwh: number
  pv_erzeugung_kwh?: number
  direktverbrauch_kwh?: number
  eigenverbrauch_kwh?: number
  gesamtverbrauch_kwh?: number
  batterie_ladung_kwh?: number
  batterie_entladung_kwh?: number
  batterie_ladung_netz_kwh?: number
  batterie_ladepreis_cent?: number
  netzbezug_durchschnittspreis_cent?: number
  // #392: Monatssatz der variablen Einspeisevergütung (ct/kWh)
  einspeise_durchschnittspreis_cent?: number
  kraftstoffpreis_euro?: number
  gaspreis_cent_kwh?: number
  globalstrahlung_kwh_m2?: number
  sonnenstunden?: number
  durchschnittstemperatur?: number
  // Legacy (deprecated seit G19-1) — nur noch lesbar, neuer Kanal ist sonstige_positionen
  sonderkosten_euro?: number
  sonderkosten_beschreibung?: string
  // G19-1: Strukturierte sonstige Erträge & Ausgaben auf Anlage-Ebene
  sonstige_positionen?: SonstigePosition[]
  datenquelle?: string
  notizen?: string
}

// G19-1: KANONISCHE Definition der Positions-Mechanik (Ertrag/Ausgabe) —
// forms/SonstigePositionenFields, forms/sections/types und api/monatsabschluss
// re-exportieren von hier (vorher 3 strukturgleiche Duplikate, Regel 0a).
export interface SonstigePosition {
  bezeichnung: string
  betrag: number
  typ: 'ertrag' | 'ausgabe'
}

export interface MonatsKennzahlen {
  direktverbrauch_kwh: number
  gesamtverbrauch_kwh: number
  eigenverbrauch_kwh: number
  eigenverbrauchsquote_prozent: number
  autarkiegrad_prozent: number
  spezifischer_ertrag_kwh_kwp?: number
  einspeise_erloes_euro: number
  netzbezug_kosten_euro: number
  eigenverbrauch_ersparnis_euro: number
  netto_ertrag_euro: number
  co2_einsparung_kg: number
}

// Investitionen
export type InvestitionTyp =
  | 'e-auto'
  | 'waermepumpe'
  | 'speicher'
  | 'wallbox'
  | 'wechselrichter'
  | 'pv-module'
  | 'balkonkraftwerk'
  | 'sonstiges'

export interface Investition {
  id: number
  anlage_id: number
  typ: InvestitionTyp
  bezeichnung: string
  // `null` = „Feld leeren" (Update-Nutzlast, siehe InvestitionUpdate); vom
  // Server kommt entweder ein Wert oder der Schlüssel fehlt.
  anschaffungsdatum?: string | null
  stilllegungsdatum?: string | null
  anschaffungskosten_gesamt?: number
  anschaffungskosten_alternativ?: number
  betriebskosten_jahr?: number
  parameter?: Record<string, unknown>
  einsparung_prognose_jahr?: number
  co2_einsparung_prognose_kg?: number
  aktiv: boolean
  parent_investition_id?: number | null
  // PV-Module spezifische Felder
  /**
   * ROHSPALTE — für FORMULARE und WIZARDS, nicht für die Anzeige.
   *
   * Wer die Nennleistung nur im `parameter`-JSON gepflegt hat (Import-/
   * Altbestand, #229), hat hier `undefined`. Zum ANZEIGEN und RECHNEN
   * deshalb {@link Investition.leistung_kwp_effektiv} lesen.
   */
  leistung_kwp?: number
  /**
   * Effektive Nennleistung — für ANZEIGE und RECHNUNG (A26/N106).
   *
   * Vom Server berechnet (`InvestitionResponse.leistung_kwp_effektiv`): bei
   * Erzeugern inkl. Fallback auf das `parameter`-JSON, bei allen anderen Typen
   * unverändert die Rohspalte (dieselbe Mehrzweck-Einheit — Speicher kWh,
   * Wechselrichter kW AC).
   *
   * **Nicht in ein Eingabefeld schreiben.** Läse ein Formular diesen Wert,
   * schriebe das nächste Speichern den abgeleiteten Wert in die Spalte — der
   * Client machte aus einer Ableitung dauerhaft Stammdaten. Der Schreibpfad
   * (`InvestitionCreate`/`InvestitionUpdate`) kennt das Feld deshalb nicht.
   * Gewächtert von `npm run check:kennwert-roh`.
   */
  leistung_kwp_effektiv?: number | null
  ausrichtung?: string
  neigung_grad?: number
  ha_entity_id?: string  // Home Assistant Sensor für String-Daten
  graue_last_kg?: number  // #284: Override graue Herstellungs-Last (CO2)
}

// Strompreise
export type StrompreisVerwendung = 'allgemein' | 'waermepumpe' | 'wallbox'

export interface Strompreis {
  id: number
  anlage_id: number
  netzbezug_arbeitspreis_cent_kwh: number
  einspeiseverguetung_cent_kwh: number
  grundpreis_euro_monat?: number
  // G19-1 K3: jährliche Zähler-/Messstellengebühr (Ausweis in der Jahresaufstellung)
  zaehlergebuehr_euro_jahr?: number
  gueltig_ab: string
  gueltig_bis?: string
  tarifname?: string
  anbieter?: string
  vertragsart?: string
  // #392: „Einspeisevergütung wechselt monatlich"
  einspeisung_variabel?: boolean
  verwendung: StrompreisVerwendung
  // N-267: HT/NT-Zeitfenster (Discussion #380, MeinerB). Leer = Einpreistarif.
  zeitfenster?: StrompreisZeitfenster[]
}

/** Ein Zeitfenster mit abweichendem Arbeitspreis (N-267).
 *
 * `von_stunde`/`bis_stunde` sind **Uhrzeiten** (0–23 bzw. 1–24), keine
 * Slot-Indizes — die Umrechnung auf die Backward-Slots macht das Backend.
 * `von > bis` läuft über Mitternacht (Nachtstrom 22–06).
 */
export interface StrompreisZeitfenster {
  id?: number
  von_stunde: number
  bis_stunde: number
  /** Montag = „0" … Sonntag = „6"; Vorbelegung „0123456" = jeden Tag. */
  wochentage: string
  arbeitspreis_cent_kwh: number
}

// Import
export interface ImportResult {
  erfolg: boolean
  importiert: number
  uebersprungen: number
  fehler: string[]
  warnungen?: string[]
}

export interface JSONImportResult {
  erfolg: boolean
  anlage_id?: number
  anlage_name?: string
  importiert: Record<string, number>
  warnungen: string[]
  fehler: string[]
}

// Investition Create/Update
export interface InvestitionCreate {
  anlage_id: number
  typ: InvestitionTyp
  bezeichnung: string
  hersteller?: string
  kaufdatum?: string
  kaufpreis?: number
  aktiv?: boolean
  // PV-Module spezifische Felder
  leistung_kwp?: number
  ausrichtung?: string
  neigung_grad?: number
  // E-Auto
  batterie_kwh?: number
}
