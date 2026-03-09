/**
 * Daten-Checker API Client
 *
 * Endpoint für Datenqualitäts-Prüfung.
 */

import { api } from './client'

export interface CheckErgebnis {
  kategorie: 'stammdaten' | 'strompreise' | 'investitionen' | 'monatsdaten_vollstaendigkeit' | 'monatsdaten_plausibilitaet'
  schwere: 'error' | 'warning' | 'info' | 'ok'
  meldung: string
  details?: string
  link?: string
}

export interface MonatsdatenAbdeckung {
  vorhanden: number
  erwartet: number
  prozent: number
}

export interface DatenCheckResponse {
  anlage_id: number
  anlage_name: string
  ergebnisse: CheckErgebnis[]
  zusammenfassung: {
    error: number
    warning: number
    info: number
    ok: number
  }
  monatsdaten_abdeckung?: MonatsdatenAbdeckung
}

export const datenCheckerApi = {
  async check(anlageId: number): Promise<DatenCheckResponse> {
    return api.get<DatenCheckResponse>(`/system/daten-check/${anlageId}`)
  },
}
