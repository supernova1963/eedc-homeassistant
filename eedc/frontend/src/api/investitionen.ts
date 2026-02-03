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
}
