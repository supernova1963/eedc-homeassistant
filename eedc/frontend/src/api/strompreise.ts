/**
 * Strompreise API Client
 */

import { api } from './client'
import type { Strompreis, StrompreisVerwendung } from '../types'

export interface StrompreisCreate {
  anlage_id: number
  netzbezug_arbeitspreis_cent_kwh: number
  einspeiseverguetung_cent_kwh: number
  grundpreis_euro_monat?: number
  gueltig_ab: string
  gueltig_bis?: string
  tarifname?: string
  anbieter?: string
  vertragsart?: string
  verwendung?: StrompreisVerwendung
}

export interface StrompreisUpdate {
  netzbezug_arbeitspreis_cent_kwh?: number
  einspeiseverguetung_cent_kwh?: number
  grundpreis_euro_monat?: number
  gueltig_ab?: string
  gueltig_bis?: string
  tarifname?: string
  anbieter?: string
  vertragsart?: string
  verwendung?: StrompreisVerwendung
}

export const strompreiseApi = {
  /**
   * Strompreise abrufen (optional gefiltert)
   */
  async list(anlageId?: number, aktuell?: boolean): Promise<Strompreis[]> {
    const params = new URLSearchParams()
    if (anlageId) params.append('anlage_id', anlageId.toString())
    if (aktuell) params.append('aktuell', 'true')
    const query = params.toString()
    return api.get<Strompreis[]>(`/strompreise/${query ? '?' + query : ''}`)
  },

  /**
   * Aktuellen Strompreis einer Anlage abrufen
   */
  async getAktuell(anlageId: number): Promise<Strompreis> {
    return api.get<Strompreis>(`/strompreise/aktuell/${anlageId}`)
  },

  /**
   * Aktuellen Strompreis für eine bestimmte Verwendung abrufen (mit Fallback auf allgemein)
   */
  async getAktuellFuer(anlageId: number, verwendung: StrompreisVerwendung): Promise<Strompreis> {
    return api.get<Strompreis>(`/strompreise/aktuell/${anlageId}/${verwendung}`)
  },

  /**
   * Einzelnen Strompreis abrufen
   */
  async get(id: number): Promise<Strompreis> {
    return api.get<Strompreis>(`/strompreise/${id}`)
  },

  /**
   * Neuen Strompreis erstellen
   */
  async create(data: StrompreisCreate): Promise<Strompreis> {
    return api.post<Strompreis>('/strompreise/', data)
  },

  /**
   * Strompreis aktualisieren
   */
  async update(id: number, data: StrompreisUpdate): Promise<Strompreis> {
    return api.put<Strompreis>(`/strompreise/${id}`, data)
  },

  /**
   * Strompreis löschen
   */
  async delete(id: number): Promise<void> {
    return api.delete(`/strompreise/${id}`)
  },
}
