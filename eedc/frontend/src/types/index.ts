/**
 * EEDC TypeScript Type Definitions
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
  ausrichtung?: string
  neigung_grad?: number
  wechselrichter_hersteller?: string
  // Home Assistant Sensor-Konfiguration
  ha_sensor_pv_erzeugung?: string
  ha_sensor_einspeisung?: string
  ha_sensor_netzbezug?: string
  ha_sensor_batterie_ladung?: string
  ha_sensor_batterie_entladung?: string
  // Erweiterte Stammdaten
  mastr_id?: string
  versorger_daten?: VersorgerDaten
  // Wetterdaten-Provider
  wetter_provider?: WetterProvider
  // Steuerliche Behandlung
  steuerliche_behandlung?: SteuerlicheBehandlung
  ust_satz_prozent?: number
  // Community-Sharing
  community_hash?: string | null
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
  globalstrahlung_kwh_m2?: number
  sonnenstunden?: number
  datenquelle?: string
  notizen?: string
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
  anschaffungsdatum?: string
  anschaffungskosten_gesamt?: number
  anschaffungskosten_alternativ?: number
  betriebskosten_jahr?: number
  parameter?: Record<string, unknown>
  einsparung_prognose_jahr?: number
  co2_einsparung_prognose_kg?: number
  aktiv: boolean
  parent_investition_id?: number
  // PV-Module spezifische Felder
  leistung_kwp?: number
  ausrichtung?: string
  neigung_grad?: number
  ha_entity_id?: string  // Home Assistant Sensor für String-Daten
}

// Strompreise
export type StrompreisVerwendung = 'allgemein' | 'waermepumpe' | 'wallbox'

export interface Strompreis {
  id: number
  anlage_id: number
  netzbezug_arbeitspreis_cent_kwh: number
  einspeiseverguetung_cent_kwh: number
  grundpreis_euro_monat?: number
  gueltig_ab: string
  gueltig_bis?: string
  tarifname?: string
  anbieter?: string
  vertragsart?: string
  verwendung: StrompreisVerwendung
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

// Home Assistant
export interface HASensor {
  entity_id: string
  friendly_name?: string
  unit_of_measurement?: string
  device_class?: string
  state?: string
}

export interface HASensorMapping {
  pv_erzeugung?: string
  einspeisung?: string
  netzbezug?: string
  batterie_ladung?: string
  batterie_entladung?: string
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
