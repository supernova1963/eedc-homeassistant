/**
 * HA Import API Client
 *
 * Ermöglicht den automatisierten Import von Monatsdaten aus Home Assistant.
 * Generiert YAML-Konfiguration für HA Template-Sensoren und Utility Meter.
 */

import { api } from './client'

// =============================================================================
// Types
// =============================================================================

export interface SensorFeld {
  key: string
  label: string
  unit: string
  required: boolean
  hint?: string
}

export interface InvestitionMitSensorFeldern {
  id: number
  bezeichnung: string
  typ: string
  felder: SensorFeld[]
  parameter?: Record<string, unknown>
}

export interface SensorMapping {
  investition_id: number
  mappings: Record<string, string>
}

export interface SensorMappingRequest {
  mappings: SensorMapping[]
}

export interface YamlResponse {
  anlage_id: number
  anlage_name: string
  yaml: string
  hinweise: string[]
}

export interface MonatsdatenImportRequest {
  jahr: number
  monat: number
  einspeisung_kwh: number
  netzbezug_kwh: number
  pv_erzeugung_kwh?: number
  globalstrahlung_kwh_m2?: number
  sonnenstunden?: number
  investitionen?: Record<string, Record<string, number>>
}

export interface ImportResult {
  erfolg: boolean
  monatsdaten_id?: number
  investitionen_importiert: number
  fehler: string[]
  hinweise: string[]
}

// =============================================================================
// API Functions
// =============================================================================

export const haImportApi = {
  /**
   * Gibt alle aktiven Investitionen einer Anlage mit den erwarteten Sensor-Feldern zurück.
   */
  async getInvestitionenMitFeldern(anlageId: number): Promise<InvestitionMitSensorFeldern[]> {
    return api.get<InvestitionMitSensorFeldern[]>(`/ha-import/investitionen/${anlageId}`)
  },

  /**
   * Speichert die Sensor-Zuordnungen für Investitionen.
   */
  async saveSensorMapping(anlageId: number, request: SensorMappingRequest): Promise<{ status: string; message: string }> {
    return api.post(`/ha-import/sensor-mapping/${anlageId}`, request)
  },

  /**
   * Generiert YAML-Konfiguration für Home Assistant.
   */
  async generateYaml(anlageId: number): Promise<YamlResponse> {
    return api.get<YamlResponse>(`/ha-import/yaml/${anlageId}`)
  },

  /**
   * Importiert Monatsdaten aus Home Assistant.
   * Wird normalerweise von einer HA-Automation aufgerufen.
   */
  async importFromHa(anlageId: number, data: MonatsdatenImportRequest): Promise<ImportResult> {
    return api.post<ImportResult>(`/ha-import/from-ha/${anlageId}`, data)
  },
}
