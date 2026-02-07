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
  // PV-Module Felder
  leistung_kwp?: number
  ausrichtung?: string
  neigung_grad?: number
  ha_entity_id?: string  // Home Assistant Sensor für String-Daten
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
  // PV-Module Felder
  leistung_kwp?: number
  ausrichtung?: string
  neigung_grad?: number
  ha_entity_id?: string
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
    // Ladung aufgeschlüsselt
    gesamt_ladung_kwh: number
    ladung_heim_kwh: number
    ladung_pv_kwh: number
    ladung_netz_kwh: number
    ladung_extern_kwh: number
    ladung_extern_euro: number
    // PV-Anteile
    pv_anteil_heim_prozent: number
    pv_anteil_gesamt_prozent: number
    // V2H
    v2h_entladung_kwh: number
    v2h_ersparnis_euro: number
    // Kosten-Vergleich
    benzin_kosten_alternativ_euro: number
    strom_kosten_heim_euro: number
    strom_kosten_extern_euro: number
    strom_kosten_gesamt_euro: number
    ersparnis_vs_benzin_euro: number
    // Wallbox-Ersparnis
    wallbox_ersparnis_euro: number
    // Gesamt
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
    // Heimladung (aus E-Auto-Daten)
    gesamt_heim_ladung_kwh: number
    ladung_pv_kwh: number
    ladung_netz_kwh: number
    pv_anteil_prozent: number
    // Externe Ladung zum Vergleich
    extern_ladung_kwh: number
    extern_kosten_euro: number
    extern_preis_kwh_euro: number
    // Kostenvergleich
    heim_kosten_euro: number
    heim_als_extern_kosten_euro: number
    ersparnis_vs_extern_euro: number
    // Wallbox-Info
    leistung_kw: number
    gesamt_ladevorgaenge: number
    ladevorgaenge_pro_monat: number
    anzahl_monate: number
  }
}

export interface BalkonkraftwerkDashboardResponse {
  investition: Investition
  monatsdaten: InvestitionMonatsdaten[]
  zusammenfassung: {
    gesamt_erzeugung_kwh: number
    gesamt_eigenverbrauch_kwh: number
    gesamt_einspeisung_kwh: number
    eigenverbrauch_quote_prozent: number
    spezifischer_ertrag_kwh_kwp: number
    // Leistung
    leistung_wp: number
    anzahl_module: number
    // Speicher
    hat_speicher: boolean
    speicher_kapazitaet_wh: number
    speicher_ladung_kwh: number
    speicher_entladung_kwh: number
    speicher_effizienz_prozent: number
    // Finanzen
    ersparnis_eigenverbrauch_euro: number
    erloes_einspeisung_euro: number
    gesamt_ersparnis_euro: number
    // CO2
    co2_ersparnis_kg: number
    anzahl_monate: number
  }
}

export interface SonstigesDashboardResponse {
  investition: Investition
  monatsdaten: InvestitionMonatsdaten[]
  zusammenfassung: {
    kategorie: 'erzeuger' | 'verbraucher' | 'speicher'
    beschreibung: string
    // Erzeuger-Felder
    gesamt_erzeugung_kwh?: number
    gesamt_eigenverbrauch_kwh?: number
    gesamt_einspeisung_kwh?: number
    eigenverbrauch_quote_prozent?: number
    ersparnis_eigenverbrauch_euro?: number
    erloes_einspeisung_euro?: number
    // Verbraucher-Felder
    gesamt_verbrauch_kwh?: number
    bezug_pv_kwh?: number
    bezug_netz_kwh?: number
    pv_anteil_prozent?: number
    kosten_netz_euro?: number
    ersparnis_pv_euro?: number
    // Speicher-Felder
    gesamt_ladung_kwh?: number
    gesamt_entladung_kwh?: number
    effizienz_prozent?: number
    ersparnis_euro?: number
    // Gemeinsame Felder
    gesamt_ersparnis_euro?: number
    co2_ersparnis_kg?: number
    sonderkosten_euro: number
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

  /**
   * Balkonkraftwerk Dashboard
   */
  async getBalkonkraftwerkDashboard(anlageId: number, strompreisCent?: number, einspeiseverguetungCent?: number): Promise<BalkonkraftwerkDashboardResponse[]> {
    const params = new URLSearchParams()
    if (strompreisCent) params.append('strompreis_cent', strompreisCent.toString())
    if (einspeiseverguetungCent) params.append('einspeiseverguetung_cent', einspeiseverguetungCent.toString())
    const query = params.toString()
    return api.get<BalkonkraftwerkDashboardResponse[]>(`/investitionen/dashboard/balkonkraftwerk/${anlageId}${query ? '?' + query : ''}`)
  },

  /**
   * Sonstiges Dashboard
   */
  async getSonstigesDashboard(anlageId: number, strompreisCent?: number, einspeiseverguetungCent?: number): Promise<SonstigesDashboardResponse[]> {
    const params = new URLSearchParams()
    if (strompreisCent) params.append('strompreis_cent', strompreisCent.toString())
    if (einspeiseverguetungCent) params.append('einspeiseverguetung_cent', einspeiseverguetungCent.toString())
    const query = params.toString()
    return api.get<SonstigesDashboardResponse[]>(`/investitionen/dashboard/sonstiges/${anlageId}${query ? '?' + query : ''}`)
  },

  /**
   * InvestitionMonatsdaten für einen bestimmten Monat laden
   * Wird vom MonatsdatenForm benötigt, um beim Bearbeiten die vorhandenen Daten zu laden
   */
  async getMonatsdatenByMonth(anlageId: number, jahr: number, monat: number): Promise<InvestitionMonatsdaten[]> {
    return api.get<InvestitionMonatsdaten[]>(`/investitionen/monatsdaten/${anlageId}/${jahr}/${monat}`)
  },
}
