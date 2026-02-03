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
}
