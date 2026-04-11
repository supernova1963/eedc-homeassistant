/**
 * Aktueller Monat API Client
 *
 * Holt Live-Daten des laufenden Monats aus HA-Sensoren, Connectors und DB.
 */

import { api } from './client'

export interface DatenquelleInfo {
  quelle: string   // "ha_sensor" | "local_connector" | "gespeichert"
  konfidenz: number
  zeitpunkt: string | null
}

export interface InvestitionFinancialDetail {
  investition_id: number
  bezeichnung: string
  typ: string
  betriebskosten_monat_euro: number
  erloes_euro: number | null
  ersparnis_euro: number | null
  ersparnis_label: string
  formel: string | null
  berechnung: string | null
}

export interface AktuellerMonatResponse {
  anlage_id: number
  anlage_name: string
  jahr: number
  monat: number
  monat_name: string
  aktualisiert_um: string

  quellen: Record<string, boolean>

  // Energie-Bilanz (kWh)
  pv_erzeugung_kwh: number | null
  einspeisung_kwh: number | null
  netzbezug_kwh: number | null
  eigenverbrauch_kwh: number | null
  gesamtverbrauch_kwh: number | null

  // Quoten (%)
  autarkie_prozent: number | null
  eigenverbrauch_quote_prozent: number | null

  // Komponenten — Speicher
  speicher_ladung_kwh: number | null
  speicher_entladung_kwh: number | null
  speicher_ladung_netz_kwh: number | null
  speicher_wirkungsgrad_prozent: number | null
  speicher_vollzyklen: number | null
  speicher_kapazitaet_kwh: number | null
  hat_speicher: boolean

  // Komponenten — Wärmepumpe
  wp_strom_kwh: number | null
  wp_waerme_kwh: number | null
  wp_heizung_kwh: number | null
  wp_warmwasser_kwh: number | null
  hat_waermepumpe: boolean

  // Komponenten — E-Mobilität
  emob_ladung_kwh: number | null
  emob_km: number | null
  emob_ladung_pv_kwh: number | null
  emob_ladung_netz_kwh: number | null
  emob_ladung_extern_kwh: number | null
  emob_v2h_kwh: number | null
  hat_emobilitaet: boolean

  // Komponenten — BKW
  bkw_erzeugung_kwh: number | null
  bkw_eigenverbrauch_kwh: number | null
  hat_balkonkraftwerk: boolean

  // Komponenten — Sonstiges
  sonstiges_erzeugung_kwh: number | null
  sonstiges_eigenverbrauch_kwh: number | null
  sonstiges_einspeisung_kwh: number | null
  sonstiges_verbrauch_kwh: number | null
  sonstiges_bezug_pv_kwh: number | null
  sonstiges_bezug_netz_kwh: number | null
  hat_sonstiges: boolean

  // Finanzen (Euro)
  einspeise_erloes_euro: number | null
  netzbezug_kosten_euro: number | null
  ev_ersparnis_euro: number | null
  netto_ertrag_euro: number | null
  wp_ersparnis_euro: number | null
  emob_ersparnis_euro: number | null
  gesamtnettoertrag_euro: number | null
  betriebskosten_anteilig_euro: number | null

  // Tarif-Info
  netzbezug_preis_cent: number | null
  einspeise_preis_cent: number | null
  netzbezug_durchschnittspreis_cent: number | null

  // Vergleiche
  vorjahr: {
    pv_erzeugung_kwh?: number
    einspeisung_kwh?: number
    netzbezug_kwh?: number
    eigenverbrauch_kwh?: number
    autarkie_prozent?: number
    wp_strom_kwh?: number
    wp_waerme_kwh?: number
    emob_ladung_kwh?: number
    emob_km?: number
    speicher_ladung_kwh?: number
    speicher_entladung_kwh?: number
    einspeise_erloes_euro?: number
    netzbezug_kosten_euro?: number
    ev_ersparnis_euro?: number
    gesamtnettoertrag_euro?: number
    netzbezug_durchschnittspreis_cent?: number
  } | null
  soll_pv_kwh: number | null

  // Per-Investition Finanzdetails (T-Konto)
  investitionen_financials: InvestitionFinancialDetail[]

  // Quellenangabe pro Feld
  feld_quellen: Record<string, DatenquelleInfo>
}

export const aktuellerMonatApi = {
  getData: (anlageId: number, jahr?: number, monat?: number) => {
    const params = new URLSearchParams()
    if (jahr !== undefined) params.set('jahr', String(jahr))
    if (monat !== undefined) params.set('monat', String(monat))
    const query = params.toString()
    return api.get<AktuellerMonatResponse>(`/aktueller-monat/${anlageId}${query ? '?' + query : ''}`)
  },
}
