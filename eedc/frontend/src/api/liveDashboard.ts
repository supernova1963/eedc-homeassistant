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

  gestern_pv_kwh: number | null
  gestern_einspeisung_kwh: number | null
  gestern_netzbezug_kwh: number | null
  gestern_eigenverbrauch_kwh: number | null
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

export interface TagesverlaufPunkt {
  zeit: string
  pv: number | null
  einspeisung: number | null
  netzbezug: number | null
  batterie: number | null
  eauto: number | null
  waermepumpe: number | null
  haushalt: number | null
  verbrauch_gesamt: number | null
}

export interface TagesverlaufResponse {
  anlage_id: number
  datum: string
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

export const liveDashboardApi = {
  getData: (anlageId: number, demo = false) =>
    api.get<LiveDashboardResponse>(`/live/${anlageId}${demo ? '?demo=true' : ''}`),

  getWetter: (anlageId: number, demo = false) =>
    api.get<LiveWetterResponse>(`/live/${anlageId}/wetter${demo ? '?demo=true' : ''}`),

  getTagesverlauf: (anlageId: number, demo = false) =>
    api.get<TagesverlaufResponse>(`/live/${anlageId}/tagesverlauf${demo ? '?demo=true' : ''}`),

  getMqttStatus: () =>
    api.get<MqttInboundStatus>('/live/mqtt/status'),

  getMqttSettings: () =>
    api.get<MqttSettings>('/live/mqtt/settings'),

  saveMqttSettings: (config: Partial<MqttSettings>) =>
    api.post<MqttSaveResult>('/live/mqtt/settings', config),

  testMqttConnection: (config: { host: string; port: number; username?: string; password?: string }) =>
    api.post<MqttTestResult>('/live/mqtt/test', config),

  getMqttTopics: (anlageId?: number) =>
    api.get<MqttTopicsResponse>(`/live/mqtt/topics${anlageId ? `?anlage_id=${anlageId}` : ''}`),
}
