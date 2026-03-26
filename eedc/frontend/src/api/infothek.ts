/**
 * Infothek API Client
 */

import { api } from './client'
import type { InfothekEintrag, InfothekEintragCreate, InfothekEintragUpdate, KategorienResponse } from '../types/infothek'

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
}
