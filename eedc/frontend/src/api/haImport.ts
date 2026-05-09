/**
 * HA Import API Client
 *
 * HINWEIS: Diese Datei wurde in v0.9.9 stark vereinfacht.
 *
 * Die komplexe HA-Integration wurde entfernt zugunsten einer
 * Standalone-fokussierten Architektur.
 *
 * eedc funktioniert primär ohne Home Assistant:
 * - Monatsdaten per CSV-Import oder manuelles Formular erfassen
 * - Optional: MQTT Export für berechnete KPIs nach HA
 */

import { api } from './client'

// =============================================================================
// Types (vereinfacht)
// =============================================================================

export interface SensorFeld {
  key: string
  label: string
  unit: string
  required: boolean
  optional?: boolean
  hint?: string
}

export interface InvestitionMitFeldern {
  id: number
  bezeichnung: string
  typ: string
  felder: SensorFeld[]
}

// =============================================================================
// API Functions
// =============================================================================

export const haImportApi = {
  /**
   * Gibt alle aktiven Investitionen einer Anlage mit den erwarteten Feldern zurück.
   * Wird verwendet für CSV-Template und Monatsdaten-Formular.
   */
  async getInvestitionenMitFeldern(anlageId: number): Promise<InvestitionMitFeldern[]> {
    return api.get<InvestitionMitFeldern[]>(`/ha-import/investitionen/${anlageId}`)
  },
}
