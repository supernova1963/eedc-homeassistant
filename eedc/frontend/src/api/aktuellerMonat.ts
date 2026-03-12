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

  // Komponenten
  speicher_ladung_kwh: number | null
  speicher_entladung_kwh: number | null
  hat_speicher: boolean
  wp_strom_kwh: number | null
  wp_waerme_kwh: number | null
  hat_waermepumpe: boolean
  emob_ladung_kwh: number | null
  hat_emobilitaet: boolean
  bkw_erzeugung_kwh: number | null
  hat_balkonkraftwerk: boolean

  // Finanzen (Euro)
  einspeise_erloes_euro: number | null
  netzbezug_kosten_euro: number | null
  ev_ersparnis_euro: number | null
  netto_ertrag_euro: number | null

  // Vergleiche
  vorjahr: {
    pv_erzeugung_kwh?: number
    einspeisung_kwh?: number
    netzbezug_kwh?: number
    eigenverbrauch_kwh?: number
    autarkie_prozent?: number
  } | null
  soll_pv_kwh: number | null

  // Quellenangabe pro Feld
  feld_quellen: Record<string, DatenquelleInfo>
}

export const aktuellerMonatApi = {
  getData: (anlageId: number) =>
    api.get<AktuellerMonatResponse>(`/aktueller-monat/${anlageId}`),
}
