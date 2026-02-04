/**
 * PVGIS API Client
 *
 * Integration mit dem PVGIS Backend für PV-Ertragsprognosen.
 * Unterstützt Prognosen für einzelne PV-Module und Gesamt-Anlage.
 */

import { api } from './client'

// =============================================================================
// Types
// =============================================================================

export interface PVGISMonthlyData {
  monat: number
  e_m: number        // Monatlicher Ertrag kWh
  h_m: number        // Einstrahlung kWh/m²
  sd_m: number       // Standardabweichung
}

export interface PVModulPrognose {
  investition_id: number
  bezeichnung: string
  leistung_kwp: number
  ausrichtung: string
  ausrichtung_grad: number
  neigung_grad: number
  jahresertrag_kwh: number
  spezifischer_ertrag_kwh_kwp: number
  monatsdaten: PVGISMonthlyData[]
}

export interface PVGISPrognose {
  anlage_id: number
  anlage_name: string
  latitude: number
  longitude: number
  gesamt_leistung_kwp: number
  jahresertrag_kwh: number
  spezifischer_ertrag_kwh_kwp: number
  monatsdaten: PVGISMonthlyData[]
  module: PVModulPrognose[]
  system_losses: number
  abgerufen_am: string
  pvgis_version: string
}

export interface GespeichertePrognose {
  id: number
  anlage_id: number
  abgerufen_am: string
  jahresertrag_kwh: number
  spezifischer_ertrag_kwh_kwp: number
  neigung_grad: number
  ausrichtung_grad: number
  ist_aktiv: boolean
}

export interface AktivePrognoseResponse {
  id: number
  anlage_id: number
  abgerufen_am: string
  latitude: number
  longitude: number
  neigung_grad: number
  ausrichtung_grad: number
  ausrichtung_richtung: string
  system_losses: number
  jahresertrag_kwh: number
  spezifischer_ertrag_kwh_kwp: number
  monatswerte: Array<{
    monat: number
    e_m: number
    h_m: number
    sd_m: number
  }>
}

export interface PVGISOptimum {
  anlage_id: number
  anlage_name: string
  standort: {
    latitude: number
    longitude: number
  }
  optimal: {
    neigung_grad: number
    azimut_grad: number
    azimut_richtung: string
    spezifischer_ertrag_kwh_kwp: number
  }
  hinweis: string
}

export interface PVGISRequestParams {
  system_losses?: number
}

// =============================================================================
// API Client
// =============================================================================

export const pvgisApi = {
  /**
   * Ruft PVGIS Prognose für eine Anlage ab (Summe aller PV-Module)
   */
  async getPrognose(
    anlageId: number,
    params: PVGISRequestParams = {}
  ): Promise<PVGISPrognose> {
    const searchParams = new URLSearchParams()
    if (params.system_losses !== undefined) {
      searchParams.set('system_losses', params.system_losses.toString())
    }
    const query = searchParams.toString()
    return api.get(`/pvgis/prognose/${anlageId}${query ? `?${query}` : ''}`)
  },

  /**
   * Ruft PVGIS Prognose für ein einzelnes PV-Modul ab
   */
  async getModulPrognose(
    investitionId: number,
    params: PVGISRequestParams = {}
  ): Promise<PVModulPrognose> {
    const searchParams = new URLSearchParams()
    if (params.system_losses !== undefined) {
      searchParams.set('system_losses', params.system_losses.toString())
    }
    const query = searchParams.toString()
    return api.get(`/pvgis/modul/${investitionId}${query ? `?${query}` : ''}`)
  },

  /**
   * Ruft PVGIS Prognose ab und speichert sie in der Datenbank
   */
  async speicherePrognose(
    anlageId: number,
    params: PVGISRequestParams = {}
  ): Promise<GespeichertePrognose> {
    const searchParams = new URLSearchParams()
    if (params.system_losses !== undefined) {
      searchParams.set('system_losses', params.system_losses.toString())
    }
    const query = searchParams.toString()
    return api.post(`/pvgis/prognose/${anlageId}/speichern${query ? `?${query}` : ''}`)
  },

  /**
   * Listet alle gespeicherten Prognosen für eine Anlage
   */
  async listeGespeichertePrognosen(anlageId: number): Promise<GespeichertePrognose[]> {
    return api.get(`/pvgis/prognose/${anlageId}/gespeichert`)
  },

  /**
   * Gibt die aktive Prognose für eine Anlage zurück
   */
  async getAktivePrognose(anlageId: number): Promise<AktivePrognoseResponse | null> {
    return api.get(`/pvgis/prognose/${anlageId}/aktiv`)
  },

  /**
   * Aktiviert eine gespeicherte Prognose
   */
  async aktivierePrognose(prognoseId: number): Promise<{ message: string; id: number }> {
    return api.put(`/pvgis/prognose/${prognoseId}/aktivieren`, {})
  },

  /**
   * Löscht eine gespeicherte Prognose
   */
  async loeschePrognose(prognoseId: number): Promise<void> {
    return api.delete(`/pvgis/prognose/${prognoseId}`)
  },

  /**
   * Ermittelt optimale Ausrichtung für eine Anlage
   */
  async getOptimum(anlageId: number): Promise<PVGISOptimum> {
    return api.get(`/pvgis/optimum/${anlageId}`)
  }
}
