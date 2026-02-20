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

// Zeitraum-Typ für Benchmark-Abfragen
export type ZeitraumTyp = 'letzter_monat' | 'letzte_12_monate' | 'letztes_vollstaendiges_jahr' | 'jahr' | 'seit_installation'

// =============================================================================
// Erweiterte Benchmark Types (vom Community-Server)
// =============================================================================

export interface KPIVergleich {
  wert: number
  community_avg?: number | null
  rang?: number | null
  von?: number | null
}

export interface PVBenchmark {
  spez_ertrag: KPIVergleich
}

export interface SpeicherBenchmark {
  kapazitaet?: KPIVergleich | null
  zyklen_jahr?: KPIVergleich | null
  wirkungsgrad?: KPIVergleich | null
  netz_anteil?: KPIVergleich | null
}

export interface WaermepumpeBenchmark {
  jaz?: KPIVergleich | null
  stromverbrauch?: KPIVergleich | null
  waermeerzeugung?: KPIVergleich | null
}

export interface EAutoBenchmark {
  ladung_gesamt?: KPIVergleich | null
  pv_anteil?: KPIVergleich | null
  km?: KPIVergleich | null
  verbrauch_100km?: KPIVergleich | null
  v2h?: KPIVergleich | null
}

export interface WallboxBenchmark {
  ladung?: KPIVergleich | null
  pv_anteil?: KPIVergleich | null
  ladevorgaenge?: KPIVergleich | null
}

export interface BKWBenchmark {
  erzeugung?: KPIVergleich | null
  spez_ertrag?: KPIVergleich | null
  eigenverbrauch?: KPIVergleich | null
}

export interface ErweiterteBenchmarkData {
  pv: PVBenchmark
  speicher?: SpeicherBenchmark | null
  waermepumpe?: WaermepumpeBenchmark | null
  eauto?: EAutoBenchmark | null
  wallbox?: WallboxBenchmark | null
  balkonkraftwerk?: BKWBenchmark | null
}

export interface MonatswertOutput {
  jahr: number
  monat: number
  ertrag_kwh: number
  einspeisung_kwh?: number | null
  netzbezug_kwh?: number | null
  autarkie_prozent?: number | null
  eigenverbrauch_prozent?: number | null
  spez_ertrag_kwh_kwp?: number | null
  // Komponenten-KPIs
  speicher_ladung_kwh?: number | null
  speicher_entladung_kwh?: number | null
  speicher_ladung_netz_kwh?: number | null
  wp_stromverbrauch_kwh?: number | null
  wp_heizwaerme_kwh?: number | null
  wp_warmwasser_kwh?: number | null
  eauto_ladung_gesamt_kwh?: number | null
  eauto_ladung_pv_kwh?: number | null
  eauto_ladung_extern_kwh?: number | null
  eauto_km?: number | null
  eauto_v2h_kwh?: number | null
  wallbox_ladung_kwh?: number | null
  wallbox_ladung_pv_kwh?: number | null
  wallbox_ladevorgaenge?: number | null
  bkw_erzeugung_kwh?: number | null
  bkw_eigenverbrauch_kwh?: number | null
  bkw_speicher_ladung_kwh?: number | null
  bkw_speicher_entladung_kwh?: number | null
  sonstiges_verbrauch_kwh?: number | null
}

export interface AnlageOutput {
  anlage_hash: string
  region: string
  kwp: number
  ausrichtung: string
  neigung_grad: number
  speicher_kwh?: number | null
  installation_jahr: number
  hat_waermepumpe: boolean
  hat_eauto: boolean
  hat_wallbox: boolean
  hat_balkonkraftwerk: boolean
  hat_sonstiges: boolean
  wallbox_kw?: number | null
  bkw_wp?: number | null
  sonstiges_bezeichnung?: string | null
  monatswerte: MonatswertOutput[]
}

export interface CommunityBenchmarkResponse {
  anlage: AnlageOutput
  benchmark: BenchmarkData
  benchmark_erweitert: ErweiterteBenchmarkData
  zeitraum: ZeitraumTyp
  zeitraum_label: string
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

  /**
   * Ruft erweiterte Benchmark-Daten vom Community-Server ab.
   * WICHTIG: Nur verfügbar wenn Anlage bereits mit Community geteilt wurde!
   */
  async getBenchmark(
    anlageId: number,
    zeitraum: ZeitraumTyp = 'letzte_12_monate',
    jahr?: number,
  ): Promise<CommunityBenchmarkResponse> {
    const params = new URLSearchParams({ zeitraum })
    if (jahr) {
      params.append('jahr', jahr.toString())
    }
    return api.get<CommunityBenchmarkResponse>(
      `/community/benchmark/${anlageId}?${params.toString()}`
    )
  },
}
