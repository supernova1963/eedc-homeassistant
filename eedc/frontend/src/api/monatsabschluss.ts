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
  quelle: 'ha_sensor' | 'cron_snapshot' | 'vormonat' | 'vorjahr' | 'berechnung' | 'durchschnitt' | 'parameter'
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
  quelle: 'ha_sensor' | 'snapshot' | 'manuell' | 'berechnet' | null
  vorschlaege: Vorschlag[]
  warnungen: Warnung[]
  strategie: string | null
  sensor_id: string | null
}

export interface InvestitionStatus {
  id: number
  typ: string
  bezeichnung: string
  felder: FeldStatus[]
}

export interface MonatsabschlussResponse {
  anlage_id: number
  anlage_name: string
  jahr: number
  monat: number
  ist_abgeschlossen: boolean
  ha_mapping_konfiguriert: boolean
  basis_felder: FeldStatus[]
  investitionen: InvestitionStatus[]
}

export interface FeldWert {
  feld: string
  wert: number
}

export interface InvestitionWerte {
  investition_id: number
  felder: FeldWert[]
}

export interface MonatsabschlussInput {
  einspeisung_kwh?: number | null
  netzbezug_kwh?: number | null
  direktverbrauch_kwh?: number | null
  globalstrahlung_kwh_m2?: number | null
  sonnenstunden?: number | null
  durchschnittstemperatur?: number | null
  sonderkosten_euro?: number | null
  sonderkosten_beschreibung?: string | null
  investitionen: InvestitionWerte[]
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
   * Historie der letzten Monate
   */
  async getHistorie(anlageId: number, limit = 12): Promise<MonatHistorie[]> {
    return api.get<MonatHistorie[]>(`/monatsabschluss/historie/${anlageId}?limit=${limit}`)
  },
}
