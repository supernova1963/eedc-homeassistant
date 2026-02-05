/**
 * Anlagen API Client
 */

import { api } from './client'
import type { Anlage, AnlageCreate, AnlageUpdate, SensorConfig, GeocodeResult } from '../types'

export const anlagenApi = {
  /**
   * Alle Anlagen abrufen
   */
  async list(): Promise<Anlage[]> {
    return api.get<Anlage[]>('/anlagen/')
  },

  /**
   * Einzelne Anlage abrufen
   */
  async get(id: number): Promise<Anlage> {
    return api.get<Anlage>(`/anlagen/${id}`)
  },

  /**
   * Neue Anlage erstellen
   */
  async create(data: AnlageCreate): Promise<Anlage> {
    return api.post<Anlage>('/anlagen/', data)
  },

  /**
   * Anlage aktualisieren
   */
  async update(id: number, data: AnlageUpdate): Promise<Anlage> {
    return api.put<Anlage>(`/anlagen/${id}`, data)
  },

  /**
   * Anlage löschen
   */
  async delete(id: number): Promise<void> {
    return api.delete(`/anlagen/${id}`)
  },

  /**
   * Sensor-Konfiguration abrufen
   */
  async getSensorConfig(id: number): Promise<SensorConfig> {
    return api.get<SensorConfig>(`/anlagen/${id}/sensors`)
  },

  /**
   * Sensor-Konfiguration aktualisieren
   */
  async updateSensorConfig(id: number, config: SensorConfig): Promise<SensorConfig> {
    return api.patch<SensorConfig>(`/anlagen/${id}/sensors`, config)
  },

  /**
   * Koordinaten aus PLZ/Ort ermitteln
   */
  async geocode(plz: string, ort?: string): Promise<GeocodeResult> {
    const params = new URLSearchParams({ plz })
    if (ort) params.append('ort', ort)
    return api.get<GeocodeResult>(`/anlagen/geocode/lookup?${params}`)
  },
}
