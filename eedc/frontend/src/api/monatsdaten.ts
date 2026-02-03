/**
 * Monatsdaten API Client
 */

import { api } from './client'
import type { Monatsdaten, MonatsKennzahlen } from '../types'

export interface MonatsdatenCreate {
  anlage_id: number
  jahr: number
  monat: number
  einspeisung_kwh: number
  netzbezug_kwh: number
  pv_erzeugung_kwh?: number
  batterie_ladung_kwh?: number
  batterie_entladung_kwh?: number
  batterie_ladung_netz_kwh?: number
  batterie_ladepreis_cent?: number
  globalstrahlung_kwh_m2?: number
  sonnenstunden?: number
  datenquelle?: string
  notizen?: string
}

export interface MonatsdatenUpdate {
  einspeisung_kwh?: number
  netzbezug_kwh?: number
  pv_erzeugung_kwh?: number
  batterie_ladung_kwh?: number
  batterie_entladung_kwh?: number
  batterie_ladung_netz_kwh?: number
  batterie_ladepreis_cent?: number
  globalstrahlung_kwh_m2?: number
  sonnenstunden?: number
  notizen?: string
}

export interface MonatsdatenMitKennzahlen extends Monatsdaten {
  kennzahlen?: MonatsKennzahlen
}

export const monatsdatenApi = {
  /**
   * Monatsdaten abrufen (optional gefiltert)
   */
  async list(anlageId?: number, jahr?: number): Promise<Monatsdaten[]> {
    const params = new URLSearchParams()
    if (anlageId) params.append('anlage_id', anlageId.toString())
    if (jahr) params.append('jahr', jahr.toString())
    const query = params.toString()
    return api.get<Monatsdaten[]>(`/monatsdaten/${query ? '?' + query : ''}`)
  },

  /**
   * Einzelne Monatsdaten mit Kennzahlen abrufen
   */
  async get(id: number): Promise<MonatsdatenMitKennzahlen> {
    return api.get<MonatsdatenMitKennzahlen>(`/monatsdaten/${id}`)
  },

  /**
   * Neue Monatsdaten erstellen
   */
  async create(data: MonatsdatenCreate): Promise<Monatsdaten> {
    return api.post<Monatsdaten>('/monatsdaten/', data)
  },

  /**
   * Monatsdaten aktualisieren
   */
  async update(id: number, data: MonatsdatenUpdate): Promise<Monatsdaten> {
    return api.put<Monatsdaten>(`/monatsdaten/${id}`, data)
  },

  /**
   * Monatsdaten löschen
   */
  async delete(id: number): Promise<void> {
    return api.delete(`/monatsdaten/${id}`)
  },
}
