/**
 * Investitionen API Client
 */

import { api } from './client'
import type { Investition, InvestitionTyp } from '../types'

export interface InvestitionCreate {
  anlage_id: number
  typ: InvestitionTyp
  bezeichnung: string
  anschaffungsdatum?: string
  anschaffungskosten_gesamt?: number
  anschaffungskosten_alternativ?: number
  betriebskosten_jahr?: number
  parameter?: Record<string, unknown>
  aktiv?: boolean
  parent_investition_id?: number
}

export interface InvestitionUpdate {
  bezeichnung?: string
  anschaffungsdatum?: string
  anschaffungskosten_gesamt?: number
  anschaffungskosten_alternativ?: number
  betriebskosten_jahr?: number
  parameter?: Record<string, unknown>
  aktiv?: boolean
  parent_investition_id?: number
}

export interface InvestitionTypInfo {
  typ: string
  label: string
  beschreibung: string
  parameter_schema: Record<string, {
    type: string
    label: string
    required?: boolean
    default?: unknown
    options?: string[]
  }>
}

export interface ROIBerechnung {
  investition_id: number
  investition_bezeichnung: string
  investition_typ: string
  anschaffungskosten: number
  anschaffungskosten_alternativ: number
  relevante_kosten: number
  jahres_einsparung: number
  roi_prozent: number | null
  amortisation_jahre: number | null
  co2_einsparung_kg: number | null
  detail_berechnung: Record<string, unknown>
}

export interface ROIDashboardResponse {
  anlage_id: number
  anlage_name: string
  gesamt_investition: number
  gesamt_relevante_kosten: number
  gesamt_jahres_einsparung: number
  gesamt_roi_prozent: number | null
  gesamt_amortisation_jahre: number | null
  gesamt_co2_einsparung_kg: number
  berechnungen: ROIBerechnung[]
}

// Investitions-Dashboard Types
export interface InvestitionMonatsdaten {
  id: number
  investition_id: number
  jahr: number
  monat: number
  verbrauch_daten: Record<string, number>
  einsparung_monat_euro: number | null
  co2_einsparung_kg: number | null
}

export interface EAutoDashboardResponse {
  investition: Investition
  monatsdaten: InvestitionMonatsdaten[]
  zusammenfassung: {
    gesamt_km: number
    gesamt_verbrauch_kwh: number
    durchschnitt_verbrauch_kwh_100km: number
    gesamt_ladung_kwh: number
    ladung_pv_kwh: number
    ladung_netz_kwh: number
    pv_anteil_prozent: number
    v2h_entladung_kwh: number
    v2h_ersparnis_euro: number
    benzin_kosten_alternativ_euro: number
    strom_kosten_euro: number
    ersparnis_vs_benzin_euro: number
    gesamt_ersparnis_euro: number
    co2_ersparnis_kg: number
    anzahl_monate: number
  }
}

export interface WaermepumpeDashboardResponse {
  investition: Investition
  monatsdaten: InvestitionMonatsdaten[]
  zusammenfassung: {
    gesamt_stromverbrauch_kwh: number
    gesamt_heizenergie_kwh: number
    gesamt_warmwasser_kwh: number
    gesamt_waerme_kwh: number
    durchschnitt_cop: number
    wp_kosten_euro: number
    alte_heizung_kosten_euro: number
    ersparnis_euro: number
    co2_ersparnis_kg: number
    anzahl_monate: number
  }
}

export interface SpeicherDashboardResponse {
  investition: Investition
  monatsdaten: InvestitionMonatsdaten[]
  zusammenfassung: {
    gesamt_ladung_kwh: number
    gesamt_entladung_kwh: number
    effizienz_prozent: number
    vollzyklen: number
    zyklen_pro_monat: number
    kapazitaet_kwh: number
    ersparnis_euro: number
    anzahl_monate: number
  }
}

export interface WallboxDashboardResponse {
  investition: Investition
  monatsdaten: InvestitionMonatsdaten[]
  zusammenfassung: {
    gesamt_ladung_kwh: number
    gesamt_ladevorgaenge: number
    durchschnitt_kwh_pro_vorgang: number
    ladevorgaenge_pro_monat: number
    anzahl_monate: number
  }
}

export const investitionenApi = {
  /**
   * Verfügbare Investitionstypen mit Schema abrufen
   */
  async getTypen(): Promise<InvestitionTypInfo[]> {
    return api.get<InvestitionTypInfo[]>('/investitionen/typen')
  },

  /**
   * Investitionen abrufen (optional gefiltert)
   */
  async list(anlageId?: number, typ?: string, aktiv?: boolean): Promise<Investition[]> {
    const params = new URLSearchParams()
    if (anlageId) params.append('anlage_id', anlageId.toString())
    if (typ) params.append('typ', typ)
    if (aktiv !== undefined) params.append('aktiv', aktiv.toString())
    const query = params.toString()
    return api.get<Investition[]>(`/investitionen/${query ? '?' + query : ''}`)
  },

  /**
   * Einzelne Investition abrufen
   */
  async get(id: number): Promise<Investition> {
    return api.get<Investition>(`/investitionen/${id}`)
  },

  /**
   * Neue Investition erstellen
   */
  async create(data: InvestitionCreate): Promise<Investition> {
    return api.post<Investition>('/investitionen/', data)
  },

  /**
   * Investition aktualisieren
   */
  async update(id: number, data: InvestitionUpdate): Promise<Investition> {
    return api.put<Investition>(`/investitionen/${id}`, data)
  },

  /**
   * Investition löschen
   */
  async delete(id: number): Promise<void> {
    return api.delete(`/investitionen/${id}`)
  },

  /**
   * ROI-Dashboard für eine Anlage abrufen
   */
  async getROIDashboard(
    anlageId: number,
    strompreisCent?: number,
    einspeiseverguetungCent?: number,
    benzinpreisEuro?: number
  ): Promise<ROIDashboardResponse> {
    const params = new URLSearchParams()
    if (strompreisCent) params.append('strompreis_cent', strompreisCent.toString())
    if (einspeiseverguetungCent) params.append('einspeiseverguetung_cent', einspeiseverguetungCent.toString())
    if (benzinpreisEuro) params.append('benzinpreis_euro', benzinpreisEuro.toString())
    const query = params.toString()
    return api.get<ROIDashboardResponse>(`/investitionen/roi/${anlageId}${query ? '?' + query : ''}`)
  },

  /**
   * E-Auto Dashboard
   */
  async getEAutoDashboard(anlageId: number, strompreisCent?: number, benzinpreisEuro?: number): Promise<EAutoDashboardResponse[]> {
    const params = new URLSearchParams()
    if (strompreisCent) params.append('strompreis_cent', strompreisCent.toString())
    if (benzinpreisEuro) params.append('benzinpreis_euro', benzinpreisEuro.toString())
    const query = params.toString()
    return api.get<EAutoDashboardResponse[]>(`/investitionen/dashboard/e-auto/${anlageId}${query ? '?' + query : ''}`)
  },

  /**
   * Wärmepumpe Dashboard
   */
  async getWaermepumpeDashboard(anlageId: number, strompreisCent?: number): Promise<WaermepumpeDashboardResponse[]> {
    const params = new URLSearchParams()
    if (strompreisCent) params.append('strompreis_cent', strompreisCent.toString())
    const query = params.toString()
    return api.get<WaermepumpeDashboardResponse[]>(`/investitionen/dashboard/waermepumpe/${anlageId}${query ? '?' + query : ''}`)
  },

  /**
   * Speicher Dashboard
   */
  async getSpeicherDashboard(anlageId: number, strompreisCent?: number, einspeiseverguetungCent?: number): Promise<SpeicherDashboardResponse[]> {
    const params = new URLSearchParams()
    if (strompreisCent) params.append('strompreis_cent', strompreisCent.toString())
    if (einspeiseverguetungCent) params.append('einspeiseverguetung_cent', einspeiseverguetungCent.toString())
    const query = params.toString()
    return api.get<SpeicherDashboardResponse[]>(`/investitionen/dashboard/speicher/${anlageId}${query ? '?' + query : ''}`)
  },

  /**
   * Wallbox Dashboard
   */
  async getWallboxDashboard(anlageId: number): Promise<WallboxDashboardResponse[]> {
    return api.get<WallboxDashboardResponse[]>(`/investitionen/dashboard/wallbox/${anlageId}`)
  },
}
