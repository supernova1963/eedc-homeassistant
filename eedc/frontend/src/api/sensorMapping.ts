/**
 * Sensor-Mapping API Client — Rest nach der V3-Bereinigung 2026-08.
 *
 * Der frühere Wizard-Client (getMapping/saveMapping/deleteMapping/
 * getAvailableSensors/getStatus/getFeldHinweise) ist gefallen: seine
 * Backend-Routen wurden mit N-241 (13.08.) stillgelegt, die Zuordnung läuft
 * seit dem IA-V4-Flip über die Datenquellen-Fläche (`api/datenquellen`).
 * Geblieben ist der einzige lebende Weg: die HA-Energy-Vorschläge für den
 * Setup-Wizard (#197 Olli0103, `IntegrationStep`).
 */

import { api } from './client'

// HA-Energy Auto-Vorbefüllung (#197 Olli0103)
export interface HAEnergyDeviceCandidate {
  entity_id: string
  name?: string | null
  suggested_inv_typ?: 'wallbox' | 'waermepumpe' | 'e-auto' | null
}

export interface HAEnergyInvestitionMatch {
  inv_id: number
  typ: string
  bezeichnung: string
  feld: string
  sensor_id: string
  source_name?: string | null
}

export interface HAEnergySuggestResponse {
  available: boolean
  reason_unavailable?: string | null
  basis: Record<string, string>
  investitionen: Record<string, Record<string, string>>
  device_consumption_raw: HAEnergyDeviceCandidate[]
  investition_matches: HAEnergyInvestitionMatch[]
}

export const sensorMappingApi = {
  /**
   * Vorschläge aus der HA-Energiekonfiguration abrufen (#197).
   * Add-on-only: gibt available=false zurück wenn kein SUPERVISOR_TOKEN
   * gesetzt ist oder /config/.storage/core.energy fehlt.
   */
  async getHAEnergySuggestions(anlageId: number): Promise<HAEnergySuggestResponse> {
    return api.get<HAEnergySuggestResponse>(`/sensor-mapping/${anlageId}/suggest`)
  },
}
