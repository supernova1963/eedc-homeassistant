/**
 * Monatsabschluss API Client
 *
 * Endpoints für den Monatsabschluss-Wizard.
 */

import { api } from './client'

// =============================================================================
// Types
// =============================================================================

export interface Vorschlag {
  wert: number
  quelle: 'ha_sensor' | 'cron_snapshot' | 'local_connector' | 'portal_import' | 'vormonat' | 'vorjahr' | 'berechnung' | 'durchschnitt' | 'parameter'
  konfidenz: number
  beschreibung: string
  details?: Record<string, unknown>
}

export interface Warnung {
  typ: 'negativ' | 'zu_hoch' | 'zu_niedrig' | 'sensor_unavailable'
  schwere: 'error' | 'warning' | 'info'
  meldung: string
  details?: Record<string, unknown>
}

export interface FeldStatus {
  feld: string
  label: string
  einheit: string
  aktueller_wert: number | null
  aktueller_text: string | null  // Für Textfelder
  quelle: 'ha_sensor' | 'snapshot' | 'manuell' | 'berechnet' | 'portal_import' | 'cloud_import' | 'local_connector' | 'csv' | 'ha_import' | 'cron_snapshot' | null
  vorschlaege: Vorschlag[]
  warnungen: Warnung[]
  strategie: string | null
  sensor_id: string | null
  typ: 'number' | 'text'  // Feldtyp
}

export interface SonstigePosition {
  bezeichnung: string
  betrag: number
  typ: 'ertrag' | 'ausgabe'
}

export interface InvestitionStatus {
  id: number
  typ: string
  bezeichnung: string
  felder: FeldStatus[]
  kategorie?: string             // Für Typ "sonstiges": erzeuger/verbraucher/speicher
  sonstige_positionen: SonstigePosition[]
}

export interface MonatsabschlussResponse {
  anlage_id: number
  anlage_name: string
  jahr: number
  monat: number
  ist_abgeschlossen: boolean
  ha_mapping_konfiguriert: boolean
  connector_konfiguriert: boolean
  cloud_import_konfiguriert: boolean
  mqtt_inbound_konfiguriert: boolean
  portal_import_vorhanden: boolean
  datenquelle: string | null
  basis_felder: FeldStatus[]
  optionale_felder: FeldStatus[]  // Sonderkosten, Notizen
  investitionen: InvestitionStatus[]
}

export interface FeldWert {
  feld: string
  wert: number
}

export interface InvestitionWerte {
  investition_id: number
  felder: FeldWert[]
  sonstige_positionen?: SonstigePosition[] | null
}

export interface MonatsabschlussInput {
  einspeisung_kwh?: number | null
  netzbezug_kwh?: number | null
  // direktverbrauch_kwh wird automatisch berechnet (PV - Einspeisung)
  globalstrahlung_kwh_m2?: number | null
  sonnenstunden?: number | null
  durchschnittstemperatur?: number | null
  // Optionale manuelle Felder
  sonderkosten_euro?: number | null
  sonderkosten_beschreibung?: string | null
  notizen?: string | null
  investitionen: InvestitionWerte[]
  datenquelle?: string | null
}

export interface MonatsabschlussResult {
  success: boolean
  message: string
  monatsdaten_id: number | null
  investition_monatsdaten_ids: number[]
  warnungen: Warnung[]
}

export interface NaechsterMonat {
  anlage_id: number
  anlage_name: string
  jahr: number
  monat: number
  monat_name: string
  ha_mapping_konfiguriert: boolean
}

export interface MonatHistorie {
  id: number
  jahr: number
  monat: number
  monat_name: string
  einspeisung_kwh: number | null
  netzbezug_kwh: number | null
  direktverbrauch_kwh: number | null
}

export interface CloudMonatswertFeld {
  feld: string
  label: string
  wert: number
  einheit: string
}

export interface CloudMonatswerteResponse {
  basis: CloudMonatswertFeld[]
  investitionen: Array<{
    investition_id: number
    bezeichnung: string
    typ: string
    felder: CloudMonatswertFeld[]
  }>
}

// =============================================================================
// API Client
// =============================================================================

export const monatsabschlussApi = {
  /**
   * Status für einen Monat abrufen
   */
  async getStatus(
    anlageId: number,
    jahr: number,
    monat: number
  ): Promise<MonatsabschlussResponse> {
    return api.get<MonatsabschlussResponse>(`/monatsabschluss/${anlageId}/${jahr}/${monat}`)
  },

  /**
   * Monatsdaten speichern
   */
  async save(
    anlageId: number,
    jahr: number,
    monat: number,
    daten: MonatsabschlussInput
  ): Promise<MonatsabschlussResult> {
    return api.post<MonatsabschlussResult>(`/monatsabschluss/${anlageId}/${jahr}/${monat}`, daten)
  },

  /**
   * Nächsten unvollständigen Monat ermitteln
   */
  async getNaechsterMonat(anlageId: number): Promise<NaechsterMonat | null> {
    try {
      return await api.get<NaechsterMonat>(`/monatsabschluss/naechster/${anlageId}`)
    } catch {
      return null
    }
  },

  /**
   * Cloud-Daten für einen Monat abrufen (ohne in DB zu schreiben)
   */
  async cloudFetch(
    anlageId: number,
    jahr: number,
    monat: number
  ): Promise<CloudMonatswerteResponse> {
    return api.post<CloudMonatswerteResponse>(`/monatsabschluss/${anlageId}/${jahr}/${monat}/cloud-fetch`, {})
  },

  /**
   * Historie der letzten Monate
   */
  async getHistorie(anlageId: number, limit = 12): Promise<MonatHistorie[]> {
    return api.get<MonatHistorie[]>(`/monatsabschluss/historie/${anlageId}?limit=${limit}`)
  },
}
