/**
 * Infothek API Client
 */

import { api } from './client'
import type { InfothekEintrag, InfothekEintragCreate, InfothekEintragUpdate, InfothekDatei, KategorienResponse } from '../types/infothek'

export const infothekApi = {
  async list(anlageId: number, kategorie?: string, aktiv?: boolean): Promise<InfothekEintrag[]> {
    const params = new URLSearchParams({ anlage_id: String(anlageId) })
    if (kategorie) params.set('kategorie', kategorie)
    if (aktiv !== undefined) params.set('aktiv', String(aktiv))
    return api.get<InfothekEintrag[]>(`/infothek/?${params}`)
  },

  async get(id: number): Promise<InfothekEintrag> {
    return api.get<InfothekEintrag>(`/infothek/${id}`)
  },

  async create(data: InfothekEintragCreate): Promise<InfothekEintrag> {
    return api.post<InfothekEintrag>('/infothek/', data)
  },

  async update(id: number, data: InfothekEintragUpdate): Promise<InfothekEintrag> {
    return api.put<InfothekEintrag>(`/infothek/${id}`, data)
  },

  async delete(id: number): Promise<void> {
    return api.delete(`/infothek/${id}`)
  },

  async getKategorien(): Promise<KategorienResponse> {
    return api.get<KategorienResponse>('/infothek/kategorien')
  },

  async getCount(anlageId: number): Promise<number> {
    const result = await api.get<{ count: number }>(`/infothek/count?anlage_id=${anlageId}`)
    return result.count
  },

  async updateSortierung(items: { id: number; sortierung: number }[]): Promise<void> {
    await api.put('/infothek/sortierung/batch', items)
  },

  // Vorbelegung + Verknüpfung (Etappe 3)
  async getVorbelegung(kategorie: string, anlageId: number): Promise<{ parameter: Record<string, unknown> }> {
    return api.get(`/infothek/vorbelegung/${kategorie}?anlage_id=${anlageId}`)
  },

  async updateVerknuepfung(eintragId: number, investitionId: number | null): Promise<InfothekEintrag> {
    const params = investitionId !== null ? `?investition_id=${investitionId}` : ''
    return api.put<InfothekEintrag>(`/infothek/${eintragId}/verknuepfung${params}`, {})
  },

  async listFuerInvestition(investitionId: number): Promise<InfothekEintrag[]> {
    return api.get<InfothekEintrag[]>(`/infothek/investition/${investitionId}`)
  },

  // Datei-Endpunkte
  async listDateien(eintragId: number): Promise<InfothekDatei[]> {
    return api.get<InfothekDatei[]>(`/infothek/${eintragId}/dateien`)
  },

  async uploadDatei(eintragId: number, file: File): Promise<InfothekDatei> {
    return api.upload<InfothekDatei>(`/infothek/${eintragId}/dateien`, file, 'datei')
  },

  async deleteDatei(eintragId: number, dateiId: number): Promise<void> {
    return api.delete(`/infothek/${eintragId}/dateien/${dateiId}`)
  },

  /** URL für Bild/PDF (volle Auflösung) */
  dateiUrl(eintragId: number, dateiId: number): string {
    return `./api/infothek/${eintragId}/dateien/${dateiId}`
  },

  /** URL für Thumbnail */
  thumbnailUrl(eintragId: number, dateiId: number): string {
    return `./api/infothek/${eintragId}/dateien/${dateiId}/thumb`
  },
}
