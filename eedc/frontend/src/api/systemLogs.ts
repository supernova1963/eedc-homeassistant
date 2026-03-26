/**
 * System Logs & Activity Log API Client
 *
 * Endpoints für den Log-Viewer und das Aktivitätsprotokoll.
 */

import { api } from './client'

// ─── Types ─────────────────────────────────────────────────────────────────

export interface LogEntry {
  timestamp: string
  level: string
  logger_name: string
  message: string
  module: string
}

export interface ActivityEntry {
  id: number
  timestamp: string | null
  kategorie: string
  aktion: string
  erfolg: boolean
  details: string | null
  details_json: Record<string, unknown> | null
  anlage_id: number | null
}

export interface ActivityListResponse {
  items: ActivityEntry[]
  total: number
}

export interface ActivityKategorie {
  id: string
  label: string
}

// ─── API Client ────────────────────────────────────────────────────────────

export const systemLogsApi = {
  /**
   * System-Log-Einträge aus dem Ring Buffer abrufen.
   */
  async getLogs(params?: {
    level?: string
    module?: string
    search?: string
    limit?: number
  }): Promise<LogEntry[]> {
    const searchParams = new URLSearchParams()
    if (params?.level) searchParams.set('level', params.level)
    if (params?.module) searchParams.set('module', params.module)
    if (params?.search) searchParams.set('search', params.search)
    if (params?.limit) searchParams.set('limit', String(params.limit))
    const qs = searchParams.toString()
    return api.get<LogEntry[]>(`/system/logs${qs ? '?' + qs : ''}`)
  },

  /**
   * Aktivitätsprotokoll-Einträge abrufen.
   */
  async getActivities(params?: {
    kategorie?: string
    erfolg?: boolean
    anlage_id?: number
    search?: string
    limit?: number
    offset?: number
  }): Promise<ActivityListResponse> {
    const searchParams = new URLSearchParams()
    if (params?.kategorie) searchParams.set('kategorie', params.kategorie)
    if (params?.erfolg !== undefined) searchParams.set('erfolg', String(params.erfolg))
    if (params?.search) searchParams.set('search', params.search)
    if (params?.anlage_id) searchParams.set('anlage_id', String(params.anlage_id))
    if (params?.limit != null) searchParams.set('limit', String(params.limit))
    if (params?.offset != null) searchParams.set('offset', String(params.offset))
    const qs = searchParams.toString()
    return api.get<ActivityListResponse>(`/system/activities${qs ? '?' + qs : ''}`)
  },

  /**
   * Verfügbare Aktivitäts-Kategorien für Filter-Dropdown.
   */
  async getKategorien(): Promise<ActivityKategorie[]> {
    return api.get<ActivityKategorie[]>('/system/activities/kategorien')
  },

  /**
   * Alte Aktivitätsprotokoll-Einträge manuell bereinigen.
   */
  async cleanupActivities(): Promise<{ erfolg: boolean; message: string }> {
    return api.post('/system/activities/cleanup')
  },

  /**
   * Aktuelles Log-Level abfragen.
   */
  async getLogLevel(): Promise<{ level: string }> {
    return api.get<{ level: string }>('/system/log-level')
  },

  /**
   * Log-Level zur Laufzeit ändern (kein Restart nötig).
   */
  async setLogLevel(level: string): Promise<{ erfolg: boolean; level: string }> {
    return api.put<{ erfolg: boolean; level: string }>(`/system/log-level?level=${level}`, {})
  },

  /**
   * EEDC Add-on / Container neu starten.
   */
  async restart(): Promise<{ erfolg: boolean; message: string }> {
    return api.post('/system/restart')
  },
}
