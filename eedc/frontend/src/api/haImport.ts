/**
 * HA Import API Client
 *
 * Ermöglicht den automatisierten Import von Monatsdaten aus Home Assistant.
 * Generiert YAML-Konfiguration für HA Template-Sensoren und Utility Meter.
 *
 * v0.9.8: Sensor-Auswahl aus HA mit Vorschlägen
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
  has_placeholders?: boolean
  hinweise: string[]
}

// v0.9.8: HA-Sensoren Types
export interface HASensor {
  entity_id: string
  friendly_name?: string
  state_class?: string
  unit_of_measurement?: string
  device_class?: string
}

export interface HASensorsResponse {
  sensoren: HASensor[]
  ha_url?: string
  connected: boolean
  fehler?: string
}

export interface BasisSensorMapping {
  einspeisung?: string
  netzbezug?: string
  pv_erzeugung?: string
}

export interface SensorSuggestion {
  vorschlag?: string
  score: number
  alle_sensoren?: string[]
}

export interface InvestitionSuggestion {
  bezeichnung: string
  typ: string
  felder: Record<string, SensorSuggestion>
}

export interface SensorSuggestionsResponse {
  connected: boolean
  ha_url?: string
  sensor_count?: number
  fehler?: string
  basis: Record<string, SensorSuggestion>
  investitionen: Record<string, InvestitionSuggestion>
}

export interface AnlageSensorMappingRequest {
  basis: BasisSensorMapping
  investitionen: SensorMapping[]
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
   * v0.9.8: Unterstützt Basis-Sensor-Parameter
   */
  async generateYaml(
    anlageId: number,
    basisSensors?: BasisSensorMapping
  ): Promise<YamlResponse> {
    const params = new URLSearchParams()
    if (basisSensors?.einspeisung) params.append('einspeisung_sensor', basisSensors.einspeisung)
    if (basisSensors?.netzbezug) params.append('netzbezug_sensor', basisSensors.netzbezug)
    if (basisSensors?.pv_erzeugung) params.append('pv_sensor', basisSensors.pv_erzeugung)

    const queryString = params.toString()
    const url = `/ha-import/yaml/${anlageId}${queryString ? `?${queryString}` : ''}`
    return api.get<YamlResponse>(url)
  },

  /**
   * Importiert Monatsdaten aus Home Assistant.
   * Wird normalerweise von einer HA-Automation aufgerufen.
   */
  async importFromHa(anlageId: number, data: MonatsdatenImportRequest): Promise<ImportResult> {
    return api.post<ImportResult>(`/ha-import/from-ha/${anlageId}`, data)
  },

  // v0.9.8: HA-Sensoren Funktionen

  /**
   * Ruft verfügbare Sensoren aus Home Assistant ab.
   */
  async getHASensors(filterTotalIncreasing = true, filterEnergy = true): Promise<HASensorsResponse> {
    const params = new URLSearchParams()
    params.append('filter_total_increasing', String(filterTotalIncreasing))
    params.append('filter_energy', String(filterEnergy))
    return api.get<HASensorsResponse>(`/ha-import/ha-sensors?${params}`)
  },

  /**
   * Gibt Sensor-Vorschläge für alle Felder einer Anlage zurück.
   */
  async getSensorSuggestions(anlageId: number): Promise<SensorSuggestionsResponse> {
    return api.get<SensorSuggestionsResponse>(`/ha-import/ha-sensors/suggestions/${anlageId}`)
  },

  /**
   * Speichert alle Sensor-Zuordnungen für eine Anlage (Basis + Investitionen).
   */
  async saveCompleteSensorMapping(
    anlageId: number,
    request: AnlageSensorMappingRequest
  ): Promise<{ status: string; message: string }> {
    return api.post(`/ha-import/sensor-mapping-complete/${anlageId}`, request)
  },
}
