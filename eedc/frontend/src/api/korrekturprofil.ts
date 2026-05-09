/**
 * Korrekturprofil API
 *
 * Endpoints rund um das Korrekturprofil-Konzept:
 * - Wetter-Backfill aus Open-Meteo Archive
 * - Wetter-stratifizierte Stunden-Genauigkeit (interne eedc-Diagnose)
 *
 * Siehe docs/KONZEPT-KORREKTURPROFIL.md
 */

import { api } from './client'

// =============================================================================
// Wetter-Backfill
// =============================================================================

export interface WetterBackfillResponse {
  status: 'ok' | 'skipped' | 'error'
  grund?: string | null
  fehler?: string | null
  tage_geupdated?: number | null
  stunden_geupdated?: number | null
  von?: string | null
  bis?: string | null
}

export const wetterBackfill = async (
  anlageId: number,
  maxTage = 730,
): Promise<WetterBackfillResponse> => {
  return api.post<WetterBackfillResponse>(
    `/korrekturprofil/${anlageId}/wetter-backfill?max_tage=${maxTage}`,
  )
}

// =============================================================================
// Wetter-Stratifizierung
// =============================================================================

export type Wetterklasse = 'klar' | 'diffus' | 'wechselhaft'

export interface StratifizierungEintrag {
  stunden_count: number
  mae_pct: number | null
  mbe_pct: number | null
}

export interface StratifizierungResponse {
  anlage_id: number
  tage_zeitraum: number
  stunden_klassifiziert: number
  tage_mit_prognose: number
  tage_ohne_wetter: number
  tep_tage_ohne_wetter: number
  pro_klasse: Record<Wetterklasse, StratifizierungEintrag>
  pro_klasse_stunde: Record<string, StratifizierungEintrag>  // key "klasse.stunde"
}

export const getStratifizierung = async (
  anlageId: number,
  tage = 90,
): Promise<StratifizierungResponse> => {
  return api.get<StratifizierungResponse>(
    `/korrekturprofil/${anlageId}/stratifizierung?tage=${tage}`,
  )
}

// =============================================================================
// Korrekturprofil — Aggregator + Lesen
// =============================================================================

export type ProfilTyp =
  | 'sonnenstand_wetter'
  | 'sonnenstand'
  | 'stunde'
  | 'skalar'

export interface ProfilEintrag {
  profil_typ: ProfilTyp
  bin_definition: Record<string, unknown>
  faktoren: Record<string, number | Record<string, number>>
  datenpunkte_pro_bin: Record<string, number>
  tage_eingegangen: number
  faktor_skalar: number | null
  aktualisiert_am: string | null
}

export interface ProfilResponse {
  anlage_id: number
  profile: ProfilEintrag[]
}

export const getProfile = async (anlageId: number): Promise<ProfilResponse> => {
  return api.get<ProfilResponse>(`/korrekturprofil/${anlageId}/profile`)
}

export interface AggregateResponse {
  status: 'ok' | 'skipped' | 'error'
  grund?: string | null
  tage_eingegangen?: number | null
  bins_sonnenstand_wetter?: number | null
  bins_sonnenstand?: number | null
  skalar?: number | null
}

export const aggregateKorrekturprofil = async (
  anlageId: number,
  lookbackTage = 730,
): Promise<AggregateResponse> => {
  return api.post<AggregateResponse>(
    `/korrekturprofil/${anlageId}/aggregate?lookback_tage=${lookbackTage}`,
  )
}
