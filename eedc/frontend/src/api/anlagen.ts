/**
 * Anlagen API Client
 */

import { api } from './client'
import type { Anlage, AnlageCreate, AnlageUpdate } from '../types'

export const anlagenApi = {
  /**
   * Alle Anlagen abrufen
   */
  async list(): Promise<Anlage[]> {
    return api.get<Anlage[]>('/anlagen/')
  },

  /**
   * Einzelne Anlage abrufen
   */
  async get(id: number): Promise<Anlage> {
    return api.get<Anlage>(`/anlagen/${id}`)
  },

  /**
   * Neue Anlage erstellen
   */
  async create(data: AnlageCreate): Promise<Anlage> {
    return api.post<Anlage>('/anlagen/', data)
  },

  /**
   * Anlage aktualisieren
   */
  async update(id: number, data: AnlageUpdate): Promise<Anlage> {
    return api.put<Anlage>(`/anlagen/${id}`, data)
  },

  /**
   * Anlage löschen
   */
  async delete(id: number): Promise<void> {
    return api.delete(`/anlagen/${id}`)
  },
}
