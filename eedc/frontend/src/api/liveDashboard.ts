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
  parent_key?: string | null
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

  gestern_pv_kwh: number | null
  gestern_einspeisung_kwh: number | null
  gestern_netzbezug_kwh: number | null
  gestern_eigenverbrauch_kwh: number | null

  heute_kwh_pro_komponente: Record<string, number> | null
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
  profil_typ?: string  // "individuell_werktag", "individuell_wochenende", "bdew_h0"
  profil_quelle?: string | null  // "ha", "mqtt"
  profil_tage?: number | null  // Anzahl Tage im individuellen Profil
}

export interface TagesverlaufSerie {
  key: string          // z.B. "pv_3", "batterie_5", "wallbox_6", "netz", "haushalt"
  label: string        // z.B. "PV Süd", "BYD HVS 10.2"
  kategorie: string    // "pv", "batterie", "wallbox", "waermepumpe", "sonstige", "netz", "haushalt"
  farbe: string        // Hex-Farbe
  seite: string        // "quelle" (positiv) oder "senke" (negativ)
  bidirektional: boolean
}

export interface TagesverlaufPunkt {
  zeit: string
  werte: Record<string, number>  // {serie_key: kW-Wert mit Vorzeichen}
}

export interface TagesverlaufResponse {
  anlage_id: number
  datum: string
  serien: TagesverlaufSerie[]
  punkte: TagesverlaufPunkt[]
}

export interface MqttInboundStatus {
  verfuegbar: boolean
  subscriber_aktiv: boolean
  empfangene_nachrichten?: number
  letzte_nachricht?: string | null
  anlagen_mit_daten?: number[]
  broker?: string
  grund?: string
}

export interface MqttSettings {
  enabled: boolean
  host: string
  port: number
  username: string
  password: string
  quelle?: string
}

export interface MqttTestResult {
  connected: boolean
  broker?: string
  message?: string
  error?: string
}

export interface MqttSaveResult {
  gespeichert: boolean
  subscriber_gestartet: boolean
  broker?: string
}

export interface MqttTopic {
  topic: string
  label: string
  anlage: string
  typ: string
}

export interface MqttTopicsResponse {
  topics: MqttTopic[]
}

export interface MqttCacheWert {
  topic: string
  wert: number
  zeitpunkt: string
  kategorie: 'live' | 'energy'
}

export interface MqttValuesResponse {
  werte: MqttCacheWert[]
}

export const liveDashboardApi = {
  getData: (anlageId: number, demo = false) =>
    api.get<LiveDashboardResponse>(`/live/${anlageId}${demo ? '?demo=true' : ''}`),

  getWetter: (anlageId: number, demo = false) =>
    api.get<LiveWetterResponse>(`/live/${anlageId}/wetter${demo ? '?demo=true' : ''}`),

  getTagesverlauf: (anlageId: number, demo = false) =>
    api.get<TagesverlaufResponse>(`/live/${anlageId}/tagesverlauf${demo ? '?demo=true' : ''}`),

  getMqttStatus: () =>
    api.get<MqttInboundStatus>('/live/mqtt/status'),

  getMqttValues: () =>
    api.get<MqttValuesResponse>('/live/mqtt/values'),

  getMqttSettings: () =>
    api.get<MqttSettings>('/live/mqtt/settings'),

  saveMqttSettings: (config: Partial<MqttSettings>) =>
    api.post<MqttSaveResult>('/live/mqtt/settings', config),

  testMqttConnection: (config: { host: string; port: number; username?: string; password?: string }) =>
    api.post<MqttTestResult>('/live/mqtt/test', config),

  getMqttTopics: (anlageId?: number) =>
    api.get<MqttTopicsResponse>(`/live/mqtt/topics${anlageId ? `?anlage_id=${anlageId}` : ''}`),

  deleteMqttCache: (anlageId?: number, clearRetained = false) => {
    const params = new URLSearchParams()
    if (anlageId) params.set('anlage_id', String(anlageId))
    if (clearRetained) params.set('clear_retained', 'true')
    const qs = params.toString()
    return api.delete<{ geloescht: number; retained_geloescht: number; anlage_id: number | null }>(
      `/live/mqtt/cache${qs ? `?${qs}` : ''}`,
    )
  },
}
