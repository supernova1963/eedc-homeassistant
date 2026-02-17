/**
 * Sensor-Mapping API Client
 *
 * Ermöglicht die Zuordnung von Home Assistant Sensoren zu EEDC-Feldern.
 */

import { api } from './client'

// =============================================================================
// Types
// =============================================================================

export type StrategieTyp =
  | 'sensor'           // Direkter HA-Sensor
  | 'kwp_verteilung'   // Anteilig nach kWp
  | 'ev_quote'         // Nach Eigenverbrauchsquote
  | 'cop_berechnung'   // COP × Stromverbrauch
  | 'manuell'          // Manuelle Eingabe im Wizard
  | 'keine'            // Nicht erfassen

export interface FeldMapping {
  strategie: StrategieTyp
  sensor_id?: string | null
  parameter?: Record<string, number | string> | null
}

export interface BasisMapping {
  einspeisung?: FeldMapping | null
  netzbezug?: FeldMapping | null
  pv_gesamt?: FeldMapping | null
}

export interface InvestitionFelder {
  felder: Record<string, FeldMapping>
}

export interface SensorMappingRequest {
  basis: BasisMapping
  investitionen: Record<string, InvestitionFelder>
}

export interface InvestitionInfo {
  id: number
  typ: string
  bezeichnung: string
  erwartete_felder: string[]
  kwp?: number | null
  cop?: number | null
}

export interface SensorMappingResponse {
  anlage_id: number
  anlage_name: string
  mapping: Record<string, unknown> | null
  mqtt_setup_complete: boolean
  mqtt_setup_timestamp?: string | null
  investitionen: InvestitionInfo[]
  gesamt_kwp: number
}

export interface HASensorInfo {
  entity_id: string
  friendly_name?: string | null
  unit?: string | null
  device_class?: string | null
  state?: string | null
}

export interface SetupResult {
  success: boolean
  message: string
  created_sensors: number
  errors: string[]
}

export interface MappingStatus {
  configured: boolean
  mqtt_setup_complete: boolean
  mqtt_setup_timestamp?: string | null
  updated_at?: string | null
  counts: {
    sensor: number
    kwp_verteilung: number
    cop_berechnung: number
    manuell: number
  }
}

// =============================================================================
// API Client
// =============================================================================

export const sensorMappingApi = {
  /**
   * Sensor-Mapping und Investitionen einer Anlage abrufen
   */
  async getMapping(anlageId: number): Promise<SensorMappingResponse> {
    return api.get<SensorMappingResponse>(`/sensor-mapping/${anlageId}`)
  },

  /**
   * Verfügbare HA-Sensoren für Dropdown abrufen
   */
  async getAvailableSensors(anlageId: number, filterEnergy = true): Promise<HASensorInfo[]> {
    const params = new URLSearchParams()
    if (!filterEnergy) {
      params.set('filter_energy', 'false')
    }
    const query = params.toString() ? `?${params.toString()}` : ''
    return api.get<HASensorInfo[]>(`/sensor-mapping/${anlageId}/available-sensors${query}`)
  },

  /**
   * Sensor-Mapping speichern
   */
  async saveMapping(anlageId: number, mapping: SensorMappingRequest): Promise<SetupResult> {
    return api.post<SetupResult>(`/sensor-mapping/${anlageId}`, mapping)
  },

  /**
   * Sensor-Mapping löschen
   */
  async deleteMapping(anlageId: number): Promise<void> {
    await api.delete(`/sensor-mapping/${anlageId}`)
  },

  /**
   * Mapping-Status abfragen (schnelle Prüfung)
   */
  async getStatus(anlageId: number): Promise<MappingStatus> {
    return api.get<MappingStatus>(`/sensor-mapping/${anlageId}/status`)
  },
}
