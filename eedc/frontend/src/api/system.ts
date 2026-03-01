/**
 * System API Client
 *
 * Endpoints für Health, Settings und Statistics.
 */

import { api } from './client'

export interface HealthResponse {
  status: string
  version: string
  database: string
}

export interface SettingsResponse {
  version: string
  database_path: string
  ha_integration_enabled: boolean
  ha_sensors_configured: {
    pv_erzeugung: boolean
    einspeisung: boolean
    netzbezug: boolean
    batterie_ladung: boolean
    batterie_entladung: boolean
  }
  ha_sensors: {
    pv_erzeugung: string
    einspeisung: string
    netzbezug: string
    batterie_ladung: string
    batterie_entladung: string
  }
}

export interface StatsResponse {
  anlagen: number
  monatsdaten: number
  investitionen: number
  strompreise: number
  gesamt_erzeugung_kwh: number
  daten_zeitraum: {
    von: number
    bis: number
  } | null
  database_path: string
}

export interface UpdateCheckResponse {
  update_verfuegbar: boolean
  aktuelle_version: string
  neueste_version?: string
  release_url?: string
  veroeffentlicht_am?: string
}

export const systemApi = {
  /**
   * Health Check
   */
  async health(): Promise<HealthResponse> {
    return api.get<HealthResponse>('/health')
  },

  /**
   * Settings abrufen
   */
  async getSettings(): Promise<SettingsResponse> {
    return api.get<SettingsResponse>('/settings')
  },

  /**
   * Datenbank-Statistiken abrufen
   */
  async getStats(): Promise<StatsResponse> {
    return api.get<StatsResponse>('/stats')
  },

  /**
   * Prüft ob ein Update verfügbar ist
   */
  async checkUpdate(): Promise<UpdateCheckResponse> {
    return api.get<UpdateCheckResponse>('/updates/check')
  },
}
