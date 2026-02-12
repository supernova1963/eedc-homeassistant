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

/**
 * Aggregierte Monatsdaten mit Werten aus InvestitionMonatsdaten
 */
export interface AggregierteMonatsdaten {
  id: number
  anlage_id: number
  jahr: number
  monat: number
  // Zählerwerte (aus Monatsdaten)
  einspeisung_kwh: number
  netzbezug_kwh: number
  globalstrahlung_kwh_m2: number | null
  sonnenstunden: number | null
  // Aggregiert aus InvestitionMonatsdaten - PV
  pv_erzeugung_kwh: number
  // Aggregiert aus InvestitionMonatsdaten - Speicher
  speicher_ladung_kwh: number
  speicher_entladung_kwh: number
  // Aggregiert aus InvestitionMonatsdaten - Wärmepumpe
  wp_strom_kwh: number
  wp_heizung_kwh: number
  wp_warmwasser_kwh: number
  // Aggregiert aus InvestitionMonatsdaten - E-Auto
  eauto_ladung_kwh: number
  eauto_km: number
  // Aggregiert aus InvestitionMonatsdaten - Wallbox
  wallbox_ladung_kwh: number
  // Berechnet
  direktverbrauch_kwh: number
  eigenverbrauch_kwh: number
  gesamtverbrauch_kwh: number
  autarkie_prozent: number
  eigenverbrauchsquote_prozent: number
  // Legacy-Marker
  hat_legacy_daten: boolean
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

  /**
   * Aggregierte Monatsdaten abrufen
   * PV-Erzeugung und Speicher-Daten werden aus InvestitionMonatsdaten summiert
   */
  async listAggregiert(anlageId: number, jahr?: number): Promise<AggregierteMonatsdaten[]> {
    const params = jahr ? `?jahr=${jahr}` : ''
    return api.get<AggregierteMonatsdaten[]>(`/monatsdaten/aggregiert/${anlageId}${params}`)
  },
}
