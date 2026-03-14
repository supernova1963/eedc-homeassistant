/**
 * Live Dashboard API Client
 */

import { api } from './client'

export interface LiveKomponente {
  key: string
  label: string
  icon: string
  erzeugung_kw: number | null
  verbrauch_kw: number | null
}

export interface LiveGauge {
  key: string
  label: string
  wert: number
  min_wert: number
  max_wert: number
  einheit: string
}

export interface LiveDashboardResponse {
  anlage_id: number
  anlage_name: string
  zeitpunkt: string
  verfuegbar: boolean

  komponenten: LiveKomponente[]
  summe_erzeugung_kw: number
  summe_verbrauch_kw: number

  gauges: LiveGauge[]

  heute_pv_kwh: number | null
  heute_einspeisung_kwh: number | null
  heute_netzbezug_kwh: number | null
  heute_eigenverbrauch_kwh: number | null
}

export interface WetterStunde {
  zeit: string
  temperatur_c: number | null
  wetter_code: number | null
  wetter_symbol: string
  bewoelkung_prozent: number | null
  niederschlag_mm: number | null
  globalstrahlung_wm2: number | null
}

export interface VerbrauchsStunde {
  zeit: string
  pv_ertrag_kw: number
  verbrauch_kw: number
}

export interface LiveWetterResponse {
  anlage_id: number
  verfuegbar: boolean
  aktuell: WetterStunde | null
  stunden: WetterStunde[]
  temperatur_min_c: number | null
  temperatur_max_c: number | null
  sonnenstunden: number | null
  pv_prognose_kwh: number | null
  grundlast_kw: number | null
  verbrauchsprofil: VerbrauchsStunde[]
}

export const liveDashboardApi = {
  getData: (anlageId: number, demo = false) =>
    api.get<LiveDashboardResponse>(`/live/${anlageId}${demo ? '?demo=true' : ''}`),

  getWetter: (anlageId: number, demo = false) =>
    api.get<LiveWetterResponse>(`/live/${anlageId}/wetter${demo ? '?demo=true' : ''}`),
}
