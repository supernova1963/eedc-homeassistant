/**
 * Home Assistant Integration API Client
 *
 * Zugriff auf HA-Sensoren und String-Monatsdaten.
 */

import { api } from './client'

export interface HASensor {
  entity_id: string
  friendly_name: string | null
  unit_of_measurement: string | null
  device_class: string | null
  state: string | null
}

export interface HAStatus {
  connected: boolean
  message: string
}

export interface StringMonatsdaten {
  id: number
  investition_id: number
  investition_bezeichnung: string
  leistung_kwp: number
  ausrichtung: string | null
  jahr: number
  monat: number
  pv_erzeugung_kwh: number
}

export interface StringMonatsdatenCreate {
  investition_id: number
  jahr: number
  monat: number
  pv_erzeugung_kwh: number
}

export const haApi = {
  /**
   * HA-Verbindungsstatus prüfen
   */
  async getStatus(): Promise<HAStatus> {
    return api.get<HAStatus>('/ha/status')
  },

  /**
   * Alle Energy-relevanten Sensoren abrufen
   */
  async getSensors(): Promise<HASensor[]> {
    return api.get<HASensor[]>('/ha/sensors')
  },

  /**
   * String/MPPT-Sensoren abrufen
   */
  async getStringSensors(): Promise<HASensor[]> {
    return api.get<HASensor[]>('/ha/string-sensors')
  },

  /**
   * String-Monatsdaten für eine Anlage abrufen
   */
  async getStringMonatsdaten(anlageId: number, jahr?: number): Promise<StringMonatsdaten[]> {
    const params = jahr ? `?jahr=${jahr}` : ''
    return api.get<StringMonatsdaten[]>(`/ha/string-monatsdaten/${anlageId}${params}`)
  },

  /**
   * String-Monatsdaten erstellen/aktualisieren
   */
  async createStringMonatsdaten(data: StringMonatsdatenCreate): Promise<StringMonatsdaten> {
    return api.post<StringMonatsdaten>('/ha/string-monatsdaten', data)
  },

  /**
   * String-Monatsdaten löschen
   */
  async deleteStringMonatsdaten(id: number): Promise<void> {
    return api.delete(`/ha/string-monatsdaten/${id}`)
  },
}
