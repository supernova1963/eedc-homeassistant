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
// Erweiterte Statistik Types (Phase 5)
// =============================================================================

export interface AusstattungsQuoten {
  speicher: number
  waermepumpe: number
  eauto: number
  wallbox: number
  balkonkraftwerk: number
}

export interface TypischeAnlage {
  kwp: number
  ausrichtung: string
  neigung_grad: number
  speicher_kwh: number | null
}

export interface GlobaleStatistik {
  anzahl_anlagen: number
  anzahl_regionen: number
  durchschnitt: {
    kwp: number
    spez_ertrag: number
    speicher_kwh: number | null
    autarkie_prozent: number | null
    eigenverbrauch_prozent: number | null
  }
  ausstattungsquoten: AusstattungsQuoten
  typische_anlage: TypischeAnlage
  stand: string
}

export interface MonatsDurchschnitt {
  jahr: number
  monat: number
  spez_ertrag_avg: number
  anzahl_anlagen: number
}

export interface MonatlicheDurchschnitte {
  monate: MonatsDurchschnitt[]
}

export interface RegionStatistik {
  region: string
  anzahl_anlagen: number
  durchschnitt_kwp: number
  durchschnitt_spez_ertrag: number
  ausstattung: AusstattungsQuoten
}

export interface VerteilungsBin {
  von: number
  bis: number
  anzahl: number
}

export interface VerteilungsStatistik {
  min: number
  max: number
  median: number
  durchschnitt: number
  stdabweichung: number
}

export interface Verteilung {
  metric: string
  einheit: string
  bins: VerteilungsBin[]
  statistik: VerteilungsStatistik
}

export interface RankingEintrag {
  rang: number
  wert: number
  region: string
  kwp: number
}

export interface Ranking {
  category: string
  label: string
  einheit: string
  zeitraum: string
  ranking: RankingEintrag[]
  eigener_rang?: number | null
  eigener_wert?: number | null
}

// Komponenten Types - angepasst an tatsächliche Server-Antwort
export interface SpeicherKlasse {
  von_kwh: number
  bis_kwh: number | null
  anzahl: number
  durchschnitt_wirkungsgrad: number | null
  durchschnitt_zyklen: number | null
  durchschnitt_netz_anteil: number | null
}

export interface SpeicherByClass {
  klassen: SpeicherKlasse[]
}

export interface WPRegion {
  region: string
  anzahl: number
  durchschnitt_jaz: number | null
  durchschnitt_stromverbrauch: number | null
}

export interface WPByRegion {
  regionen: WPRegion[]
}

export interface EAutoKlasse {
  klasse: string
  beschreibung: string
  anzahl: number
  durchschnitt_pv_anteil: number | null
  durchschnitt_verbrauch_100km: number | null
}

export interface EAutoByUsage {
  klassen: EAutoKlasse[]
}

// Trend Types
export interface TrendPunkt {
  monat: string
  wert: number
}

export interface TrendDaten {
  period: string
  trends: {
    anzahl_anlagen: TrendPunkt[]
    durchschnitt_kwp: TrendPunkt[]
    speicher_quote: TrendPunkt[]
    waermepumpe_quote: TrendPunkt[]
    eauto_quote: TrendPunkt[]
  }
}

export interface AlterErtrag {
  alter_jahre: number
  anzahl: number
  durchschnitt_spez_ertrag: number
}

export interface DegradationsAnalyse {
  nach_alter: AlterErtrag[]
  durchschnittliche_degradation_prozent_jahr: number
}

export type TrendPeriod = '12_monate' | '24_monate' | 'gesamt'

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

  // =============================================================================
  // Erweiterte Statistiken (Phase 5)
  // =============================================================================

  /**
   * Globale Community-Statistiken
   */
  async getGlobalStatistics(): Promise<GlobaleStatistik> {
    return api.get<GlobaleStatistik>('/community/statistics/global')
  },

  /**
   * Monatliche Community-Durchschnitte
   */
  async getMonthlyAverages(monate: number = 12): Promise<MonatlicheDurchschnitte> {
    return api.get<MonatlicheDurchschnitte>(`/community/statistics/monthly-averages?monate=${monate}`)
  },

  /**
   * Regionale Statistiken (alle Bundesländer)
   */
  async getRegionalStatistics(): Promise<RegionStatistik[]> {
    return api.get<RegionStatistik[]>('/community/statistics/regional')
  },

  /**
   * Details zu einer Region
   */
  async getRegionalDetails(region: string): Promise<RegionStatistik> {
    return api.get<RegionStatistik>(`/community/statistics/regional/${region}`)
  },

  /**
   * Verteilungsdaten für Histogramme
   */
  async getDistribution(metric: string, bins: number = 10): Promise<Verteilung> {
    return api.get<Verteilung>(`/community/statistics/distributions/${metric}?bins=${bins}`)
  },

  /**
   * Top-N Ranglisten
   */
  async getRanking(category: string, limit: number = 10): Promise<Ranking> {
    return api.get<Ranking>(`/community/statistics/rankings/${category}?limit=${limit}`)
  },

  // =============================================================================
  // Komponenten Deep-Dives
  // =============================================================================

  /**
   * Speicher-Statistiken nach Kapazitätsklasse
   */
  async getSpeicherByClass(): Promise<SpeicherByClass> {
    return api.get<SpeicherByClass>('/community/components/speicher/by-class')
  },

  /**
   * Wärmepumpen-Statistiken nach Region
   */
  async getWaermepumpeByRegion(): Promise<WPByRegion> {
    return api.get<WPByRegion>('/community/components/waermepumpe/by-region')
  },

  /**
   * E-Auto-Statistiken nach Nutzungsintensität
   */
  async getEAutoByUsage(): Promise<EAutoByUsage> {
    return api.get<EAutoByUsage>('/community/components/eauto/by-usage')
  },

  // =============================================================================
  // Trends
  // =============================================================================

  /**
   * Zeitliche Trends der Community-Daten
   */
  async getTrends(period: TrendPeriod): Promise<TrendDaten> {
    return api.get<TrendDaten>(`/community/trends/${period}`)
  },

  /**
   * Degradations-Analyse nach Anlagenalter
   */
  async getDegradation(): Promise<DegradationsAnalyse> {
    return api.get<DegradationsAnalyse>('/community/trends/degradation')
  },
}
