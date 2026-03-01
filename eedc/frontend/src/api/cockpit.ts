/**
 * Cockpit API
 *
 * Aggregierte Übersicht für das Cockpit-Dashboard.
 */

import { api } from './client'

// =============================================================================
// Types
// =============================================================================

export interface CockpitUebersicht {
  // Energie-Bilanz (kWh)
  pv_erzeugung_kwh: number
  gesamtverbrauch_kwh: number
  netzbezug_kwh: number
  einspeisung_kwh: number
  direktverbrauch_kwh: number
  eigenverbrauch_kwh: number

  // Quoten (%)
  autarkie_prozent: number
  eigenverbrauch_quote_prozent: number
  direktverbrauch_quote_prozent: number
  spezifischer_ertrag_kwh_kwp: number | null
  anlagenleistung_kwp: number

  // Speicher aggregiert
  speicher_ladung_kwh: number
  speicher_entladung_kwh: number
  speicher_effizienz_prozent: number | null
  speicher_vollzyklen: number | null
  speicher_kapazitaet_kwh: number
  hat_speicher: boolean

  // Wärmepumpe aggregiert
  wp_waerme_kwh: number
  wp_strom_kwh: number
  wp_cop: number | null
  wp_ersparnis_euro: number
  hat_waermepumpe: boolean

  // E-Mobilität aggregiert
  emob_km: number
  emob_ladung_kwh: number
  emob_pv_anteil_prozent: number | null
  emob_ersparnis_euro: number
  hat_emobilitaet: boolean

  // Balkonkraftwerk aggregiert
  bkw_erzeugung_kwh: number
  bkw_eigenverbrauch_kwh: number
  hat_balkonkraftwerk: boolean

  // Finanzen (Euro)
  einspeise_erloes_euro: number
  ev_ersparnis_euro: number
  ust_eigenverbrauch_euro: number | null  // USt auf Eigenverbrauch (nur bei Regelbesteuerung)
  netto_ertrag_euro: number
  bkw_ersparnis_euro: number             // BKW Eigenverbrauch-Ersparnis
  sonstige_netto_euro: number            // Sonstige Positionen netto (BHKW, THG-Quote etc.)
  jahres_rendite_prozent: number | null  // Jahres-Ertrag / Investition (Rendite p.a.)
  investition_gesamt_euro: number
  steuerliche_behandlung: string | null  // 'regelbesteuerung' wenn aktiv

  // Umwelt (kg CO2)
  co2_pv_kg: number
  co2_wp_kg: number
  co2_emob_kg: number
  co2_gesamt_kg: number

  // Meta
  anzahl_monate: number
  zeitraum_von: string | null
  zeitraum_bis: string | null
}

// =============================================================================
// Prognose vs. IST Types
// =============================================================================

export interface MonatsvergleichItem {
  monat: number
  monat_name: string
  prognose_kwh: number
  ist_kwh: number
  abweichung_kwh: number
  abweichung_prozent: number | null
  performance_ratio: number | null
}

export interface PrognoseVsIst {
  anlage_id: number
  jahr: number
  hat_prognose: boolean
  prognose_jahresertrag_kwh: number
  ist_jahresertrag_kwh: number
  abweichung_kwh: number
  abweichung_prozent: number | null
  performance_ratio: number | null
  monatswerte: MonatsvergleichItem[]
  prognose_quelle: string | null
  prognose_datum: string | null
}

// =============================================================================
// Nachhaltigkeit Types
// =============================================================================

export interface NachhaltigkeitMonat {
  jahr: number
  monat: number
  monat_name: string
  co2_pv_kg: number
  co2_wp_kg: number
  co2_emob_kg: number
  co2_gesamt_kg: number
  co2_kumuliert_kg: number
  autarkie_prozent: number
}

export interface Nachhaltigkeit {
  anlage_id: number
  co2_gesamt_kg: number
  co2_pv_kg: number
  co2_wp_kg: number
  co2_emob_kg: number
  aequivalent_baeume: number
  aequivalent_auto_km: number
  aequivalent_fluege_km: number
  monatswerte: NachhaltigkeitMonat[]
  autarkie_durchschnitt_prozent: number
}

// =============================================================================
// Komponenten-Zeitreihe Types
// =============================================================================

export interface KomponentenMonat {
  jahr: number
  monat: number
  monat_name: string

  // Speicher
  speicher_ladung_kwh: number
  speicher_entladung_kwh: number
  speicher_effizienz_prozent: number | null
  speicher_arbitrage_kwh: number
  speicher_arbitrage_preis_cent: number | null

  // Wärmepumpe
  wp_waerme_kwh: number
  wp_strom_kwh: number
  wp_cop: number | null
  wp_heizung_kwh: number
  wp_warmwasser_kwh: number

  // E-Mobilität
  emob_km: number
  emob_ladung_kwh: number
  emob_pv_anteil_prozent: number | null
  emob_ladung_pv_kwh: number
  emob_ladung_netz_kwh: number
  emob_ladung_extern_kwh: number
  emob_ladung_extern_euro: number
  emob_v2h_kwh: number

  // Balkonkraftwerk
  bkw_erzeugung_kwh: number
  bkw_eigenverbrauch_kwh: number
  bkw_speicher_ladung_kwh: number
  bkw_speicher_entladung_kwh: number

  // Sonstiges
  sonstiges_erzeugung_kwh: number
  sonstiges_verbrauch_kwh: number

  // Sonstige Erträge & Ausgaben
  sonderkosten_euro: number
  sonstige_ertraege_euro: number
  sonstige_ausgaben_euro: number
  sonstige_netto_euro: number
}

export interface KomponentenZeitreihe {
  anlage_id: number
  hat_speicher: boolean
  hat_waermepumpe: boolean
  hat_emobilitaet: boolean
  hat_balkonkraftwerk: boolean
  hat_sonstiges: boolean
  hat_arbitrage: boolean
  hat_v2h: boolean
  monatswerte: KomponentenMonat[]
  anzahl_monate: number
}

// =============================================================================
// PV-String-Vergleich Types
// =============================================================================

export interface PVStringMonat {
  monat: number
  monat_name: string
  prognose_kwh: number
  ist_kwh: number
  abweichung_kwh: number
  abweichung_prozent: number | null
  performance_ratio: number | null
}

export interface PVStringDaten {
  investition_id: number
  bezeichnung: string
  leistung_kwp: number
  ausrichtung: string | null
  neigung_grad: number | null
  wechselrichter_id: number | null
  wechselrichter_name: string | null

  // Jahressummen
  prognose_jahr_kwh: number
  ist_jahr_kwh: number
  abweichung_jahr_kwh: number
  abweichung_jahr_prozent: number | null
  performance_ratio_jahr: number | null
  spezifischer_ertrag_kwh_kwp: number | null

  // Monatswerte
  monatswerte: PVStringMonat[]
}

export interface PVStringsResponse {
  anlage_id: number
  jahr: number
  hat_prognose: boolean
  anlagen_leistung_kwp: number

  // Gesamt-Summen
  prognose_gesamt_kwh: number
  ist_gesamt_kwh: number
  abweichung_gesamt_kwh: number
  abweichung_gesamt_prozent: number | null

  // Einzelne Strings
  strings: PVStringDaten[]

  // Beste/schlechteste Performance
  bester_string: string | null
  schlechtester_string: string | null
}

// =============================================================================
// Gesamtlaufzeit SOLL-IST Vergleich Types (NEU)
// =============================================================================

export interface PVStringJahreswert {
  jahr: number
  prognose_kwh: number
  ist_kwh: number
  abweichung_prozent: number | null
  performance_ratio: number | null
}

export interface PVStringSaisonalwert {
  monat: number
  monat_name: string
  prognose_kwh: number
  ist_durchschnitt_kwh: number
  ist_summe_kwh: number
  anzahl_jahre: number
}

export interface PVStringGesamtlaufzeit {
  investition_id: number
  bezeichnung: string
  leistung_kwp: number
  ausrichtung: string | null
  neigung_grad: number | null
  wechselrichter_name: string | null

  // Gesamtlaufzeit-Statistik
  prognose_gesamt_kwh: number
  ist_gesamt_kwh: number
  abweichung_gesamt_prozent: number | null
  performance_ratio_gesamt: number | null
  spezifischer_ertrag_kwh_kwp: number | null

  // Jahreswerte für Chart
  jahreswerte: PVStringJahreswert[]

  // Saisonale Werte (Jan-Dez)
  saisonalwerte: PVStringSaisonalwert[]
}

export interface PVStringsGesamtlaufzeitResponse {
  anlage_id: number
  hat_prognose: boolean
  anlagen_leistung_kwp: number

  // Zeitraum
  erstes_jahr: number
  letztes_jahr: number
  anzahl_jahre: number
  anzahl_monate: number

  // Gesamt-Summen
  prognose_gesamt_kwh: number
  ist_gesamt_kwh: number
  abweichung_gesamt_kwh: number
  abweichung_gesamt_prozent: number | null

  // Einzelne Strings
  strings: PVStringGesamtlaufzeit[]

  // Saisonale Aggregation
  saisonal_aggregiert: PVStringSaisonalwert[]

  // Performance-Ranking
  bester_string: string | null
  schlechtester_string: string | null
}

// =============================================================================
// Share-Text Types
// =============================================================================

export interface ShareTextResponse {
  text: string
  variante: string
}

// =============================================================================
// API Functions
// =============================================================================

export const cockpitApi = {
  /**
   * Holt die aggregierte Cockpit-Übersicht für eine Anlage.
   */
  async getUebersicht(anlageId: number, jahr?: number): Promise<CockpitUebersicht> {
    const params = jahr ? `?jahr=${jahr}` : ''
    return api.get<CockpitUebersicht>(`/cockpit/uebersicht/${anlageId}${params}`)
  },

  /**
   * Vergleicht PVGIS-Prognose mit IST-Daten für ein Jahr.
   */
  async getPrognoseVsIst(anlageId: number, jahr: number): Promise<PrognoseVsIst> {
    return api.get<PrognoseVsIst>(`/cockpit/prognose-vs-ist/${anlageId}?jahr=${jahr}`)
  },

  /**
   * Holt Nachhaltigkeits-Daten mit CO2-Zeitreihe.
   */
  async getNachhaltigkeit(anlageId: number): Promise<Nachhaltigkeit> {
    return api.get<Nachhaltigkeit>(`/cockpit/nachhaltigkeit/${anlageId}`)
  },

  /**
   * Holt Komponenten-Zeitreihe für Auswertungen.
   * Enthält Monatswerte für Speicher, WP, E-Auto, BKW, Sonstiges.
   */
  async getKomponentenZeitreihe(anlageId: number, jahr?: number): Promise<KomponentenZeitreihe> {
    const params = jahr ? `?jahr=${jahr}` : ''
    return api.get<KomponentenZeitreihe>(`/cockpit/komponenten-zeitreihe/${anlageId}${params}`)
  },

  /**
   * Holt PV-String-Vergleich (SOLL vs IST pro PV-Modul).
   * Vergleicht PVGIS-Prognose (anteilig nach kWp) mit tatsächlichen Erträgen.
   */
  async getPVStrings(anlageId: number, jahr?: number): Promise<PVStringsResponse> {
    const params = jahr ? `?jahr=${jahr}` : ''
    return api.get<PVStringsResponse>(`/cockpit/pv-strings/${anlageId}${params}`)
  },

  /**
   * Holt PV-String-Vergleich für die gesamte Laufzeit.
   * Enthält Jahresübersicht und saisonalen Vergleich.
   */
  async getPVStringsGesamtlaufzeit(anlageId: number): Promise<PVStringsGesamtlaufzeitResponse> {
    return api.get<PVStringsGesamtlaufzeitResponse>(`/cockpit/pv-strings-gesamtlaufzeit/${anlageId}`)
  },

  /**
   * Generiert kopierfertigen Social-Media-Text für einen Monat.
   */
  async getShareText(anlageId: number, monat: number, jahr: number, variante: 'kompakt' | 'ausfuehrlich'): Promise<ShareTextResponse> {
    return api.get<ShareTextResponse>(`/cockpit/share-text/${anlageId}?monat=${monat}&jahr=${jahr}&variante=${variante}`)
  },
}
