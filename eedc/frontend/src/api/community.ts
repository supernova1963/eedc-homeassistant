/**
 * Community API - Anonyme Datenübertragung an Community-Server
 */

import { api } from './client'

// =============================================================================
// Types
// =============================================================================

export interface MonatswertPreview {
  jahr: number
  monat: number
  ertrag_kwh: number
  einspeisung_kwh: number | null
  netzbezug_kwh: number | null
  autarkie_prozent: number | null
  eigenverbrauch_prozent: number | null
}

export interface CommunityDataPreview {
  region: string
  kwp: number
  ausrichtung: string
  neigung_grad: number
  speicher_kwh: number | null
  installation_jahr: number
  hat_waermepumpe: boolean
  hat_eauto: boolean
  hat_wallbox: boolean
  monatswerte: MonatswertPreview[]
}

export interface PreviewResponse {
  vorschau: CommunityDataPreview
  anzahl_monate: number
  community_url: string
  bereits_geteilt: boolean
}

export interface BenchmarkData {
  spez_ertrag_anlage: number
  spez_ertrag_durchschnitt: number
  spez_ertrag_region: number
  rang_gesamt: number
  anzahl_anlagen_gesamt: number
  rang_region: number
  anzahl_anlagen_region: number
}

export interface ShareResponse {
  success: boolean
  message: string
  anlage_hash: string | null
  anzahl_monate: number | null
  benchmark: BenchmarkData | null
}

export interface CommunityStatus {
  online: boolean
  url: string
  version?: string
  error?: string
}

export interface DeleteResponse {
  success: boolean
  message: string
  anzahl_geloeschte_monate: number
}

// =============================================================================
// API Client
// =============================================================================

export const communityApi = {
  /**
   * Prüft ob der Community-Server erreichbar ist
   */
  async getStatus(): Promise<CommunityStatus> {
    return api.get<CommunityStatus>('/community/status')
  },

  /**
   * Gibt eine Vorschau der zu teilenden Daten zurück
   */
  async getPreview(anlageId: number): Promise<PreviewResponse> {
    return api.get<PreviewResponse>(`/community/preview/${anlageId}`)
  },

  /**
   * Überträgt anonymisierte Anlagendaten an den Community-Server
   */
  async share(anlageId: number): Promise<ShareResponse> {
    return api.post<ShareResponse>(`/community/share/${anlageId}`)
  },

  /**
   * Löscht die geteilten Daten vom Community-Server
   */
  async delete(anlageId: number): Promise<DeleteResponse> {
    return api.delete<DeleteResponse>(`/community/delete/${anlageId}`)
  },
}
