/**
 * HA Statistics API Client
 *
 * Ermöglicht den Zugriff auf Home Assistant Langzeitstatistiken
 * für historischen Datenimport.
 */

import { api } from './client'

// =============================================================================
// Types
// =============================================================================

export interface HAStatisticsStatus {
  verfuegbar: boolean
  pfad?: string
  fehler?: string
}

export interface FeldWert {
  feld: string
  label: string
  wert: number
  einheit: string
  sensor_id?: string
}

export interface InvestitionWerte {
  investition_id: number
  bezeichnung: string
  typ: string
  felder: FeldWert[]
}

export interface Monatswerte {
  jahr: number
  monat: number
  monat_name: string
  basis: FeldWert[]
  investitionen: InvestitionWerte[]
}

export interface VerfuegbarerMonat {
  jahr: number
  monat: number
  monat_name: string
  hat_daten: boolean
}

export interface AlleMonatswerte {
  anlage_id: number
  anlage_name: string
  monate: Monatswerte[]
  sensor_count: number
  zeitraum?: {
    von: string
    bis: string
  }
}

export interface MonatsanfangWerte {
  anlage_id: number
  jahr: number
  monat: number
  werte: Record<string, number>
  timestamp: string
}

export type ImportAktion = 'importieren' | 'ueberspringen' | 'ueberschreiben' | 'konflikt'

export interface MonatImportStatus {
  jahr: number
  monat: number
  monat_name: string
  aktion: ImportAktion
  grund: string
  ha_werte: Record<string, number | null>
  vorhandene_werte?: Record<string, number | null>
}

export interface ImportVorschau {
  anlage_id: number
  anlage_name: string
  verfuegbare_monate: number
  zum_import: number
  konflikte: number
  uebersprungen: number
  monate: MonatImportStatus[]
}

export interface ImportRequest {
  ueberschreiben_erlauben: boolean
  ausgewaehlte_monate?: Array<{ jahr: number; monat: number }>
}

export interface ImportResult {
  success: boolean
  message: string
  importiert: number
  uebersprungen: number
  fehler: number
  details: Array<{
    jahr: number
    monat: number
    status: string
    fehler?: string
  }>
}

// =============================================================================
// API Client
// =============================================================================

export const haStatisticsApi = {
  /**
   * Prüft ob HA-Datenbank verfügbar ist
   */
  async getStatus(): Promise<HAStatisticsStatus> {
    return api.get<HAStatisticsStatus>('/ha-statistics/status')
  },

  /**
   * Monatswerte für einen einzelnen Monat abrufen
   */
  async getMonatswerte(
    anlageId: number,
    jahr: number,
    monat: number
  ): Promise<Monatswerte> {
    return api.get<Monatswerte>(`/ha-statistics/monatswerte/${anlageId}/${jahr}/${monat}`)
  },

  /**
   * Alle verfügbaren Monate mit Daten abrufen
   */
  async getVerfuegbareMonate(anlageId: number): Promise<VerfuegbarerMonat[]> {
    return api.get<VerfuegbarerMonat[]>(`/ha-statistics/verfuegbare-monate/${anlageId}`)
  },

  /**
   * Alle Monatswerte (Bulk-Abfrage)
   */
  async getAlleMonatswerte(anlageId: number): Promise<AlleMonatswerte> {
    return api.get<AlleMonatswerte>(`/ha-statistics/alle-monatswerte/${anlageId}`)
  },

  /**
   * Zählerstände am Monatsanfang (für MQTT Startwerte)
   */
  async getMonatsanfangWerte(
    anlageId: number,
    jahr: number,
    monat: number
  ): Promise<MonatsanfangWerte> {
    return api.get<MonatsanfangWerte>(`/ha-statistics/monatsanfang/${anlageId}/${jahr}/${monat}`)
  },

  /**
   * Import-Vorschau mit Konflikt-Erkennung
   */
  async getImportVorschau(anlageId: number): Promise<ImportVorschau> {
    return api.get<ImportVorschau>(`/ha-statistics/import-vorschau/${anlageId}`)
  },

  /**
   * Import durchführen mit Überschreib-Schutz
   */
  async importieren(anlageId: number, request: ImportRequest): Promise<ImportResult> {
    return api.post<ImportResult>(`/ha-statistics/import/${anlageId}`, request)
  },
}
