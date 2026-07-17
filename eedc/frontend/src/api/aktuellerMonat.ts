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
  // Sonstige Positionen (z.B. AG-Vergütung Dienstwagen, THG-Quote)
  sonstige_ertraege_euro: number
  sonstige_ausgaben_euro: number
}

export interface SonstigesGeraet {
  bezeichnung: string
  kategorie: 'erzeuger' | 'verbraucher' | string
  erzeugung_kwh?: number | null
  eigenverbrauch_kwh?: number | null
  einspeisung_kwh?: number | null
  verbrauch_kwh?: number | null
  bezug_pv_kwh?: number | null
  bezug_netz_kwh?: number | null
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
  direktverbrauch_kwh: number | null  // PV direkt verbraucht (ohne Speicher) = EV − Speicher-Entladung
  gesamtverbrauch_kwh: number | null

  // Quoten (%)
  autarkie_prozent: number | null
  eigenverbrauch_quote_prozent: number | null
  // Spez. Ertrag kWh/kWp (Community-Basis) — für die Median-Abweichung im Community-Block.
  spez_ertrag?: number | null

  // Komponenten — Speicher
  speicher_ladung_kwh: number | null
  speicher_entladung_kwh: number | null
  speicher_ladung_netz_kwh: number | null
  speicher_wirkungsgrad_prozent: number | null
  speicher_vollzyklen: number | null
  speicher_kapazitaet_kwh: number | null
  hat_speicher: boolean
  // Etappe C (#264): SoC-Drift-Flag + TEP-basierter effektiver Ladepreis
  speicher_soc_drift_signifikant: boolean
  speicher_effektiver_ladepreis_cent: number | null
  speicher_effektiver_ladepreis_quelle: string | null
  // R15-1 (Rainer-Kostenkacheln): Kosten der Netzladung + verwendeter Preis
  speicher_ladung_netz_kosten_euro: number | null
  speicher_ladung_netz_preis_cent: number | null
  speicher_ladung_netz_preis_quelle: string | null

  // Komponenten — Wärmepumpe
  wp_strom_kwh: number | null
  wp_waerme_kwh: number | null
  wp_heizung_kwh: number | null
  wp_warmwasser_kwh: number | null
  // #191: Strom-Aufteilung Heizung/Warmwasser. Nur befüllt wenn mindestens
  // eine WP-Investition `getrennte_strommessung=true` hat.
  wp_strom_heizen_kwh: number | null
  wp_strom_warmwasser_kwh: number | null
  // Issue #169: Kompressor-Starts (aus TagesZusammenfassung über die Tage des Monats)
  wp_starts_max_tag: number | null
  wp_starts_summe_monat: number | null
  // Issue #238: Betriebsstunden analog zu den Starts (gleiche Counter-Quelle)
  wp_betriebsstunden_max_tag: number | null
  wp_betriebsstunden_summe_monat: number | null
  hat_waermepumpe: boolean

  // Komponenten — E-Mobilität
  emob_ladung_kwh: number | null
  emob_km: number | null
  emob_verbrauch_100km: number | null
  emob_verbrauch_quelle: 'gemessen' | 'ladung' | 'keine'
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
  // Pro-Gerät-Aufschlüsselung (2 Blöcke Erzeuger/Verbraucher, je Gerät eine Zeile)
  sonstiges_geraete?: SonstigesGeraet[]
  hat_sonstiges: boolean

  // Finanzen (Euro)
  einspeise_erloes_euro: number | null
  netzbezug_kosten_euro: number | null
  ev_ersparnis_euro: number | null
  netto_ertrag_euro: number | null
  wp_ersparnis_euro: number | null
  emob_ersparnis_euro: number | null
  // Sonstige Positionen aggregiert (z.B. AG-Vergütung Dienstwagen, THG-Quote).
  // Detail-Zeilen pro Investition stehen in investitionen_financials.
  sonstige_ertraege_euro: number
  sonstige_ausgaben_euro: number
  sonstige_netto_euro: number
  // G19-1: davon Anlage-Ebene (Monatsdaten.sonstige_positionen) — reiner
  // Ausweis für die T-Konto-Zeile „Anlage — Sonstige …", bereits in den
  // sonstige_*-Totals enthalten.
  anlage_sonstige_ertraege_euro: number
  anlage_sonstige_ausgaben_euro: number
  gesamtnettoertrag_euro: number | null
  betriebskosten_anteilig_euro: number | null

  // Tarif-Info
  netzbezug_preis_cent: number | null
  einspeise_preis_cent: number | null
  netzbezug_durchschnittspreis_cent: number | null
  // G19-1 K3: Grundgebühr des Monats (steckt bereits in netzbezug_kosten_euro,
  // reiner Ausweis) + jährliche Zählergebühr vom Tarif (nur Jahresaufstellung,
  // nicht verrechnet).
  grundgebuehr_euro: number | null
  zaehlergebuehr_euro_jahr: number | null

  // Vergleiche
  vorjahr: {
    pv_erzeugung_kwh?: number
    einspeisung_kwh?: number
    netzbezug_kwh?: number
    eigenverbrauch_kwh?: number
    direktverbrauch_kwh?: number
    gesamtverbrauch_kwh?: number
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

  // Grundlast (Nacht-Sockel; R12-1 ersetzt PVGIS-SOLL/IST). grundlast_kwh additiv
  // → Cockpit/Jahr (JahrAggregat) summiert die Monate.
  grundlast_kw?: number | null              // Median der Nacht-Stunden-Leistung
  grundlast_kwh?: number | null             // geschätzte Grundlast-Energie (kW × 24 × Tage)
  grundlast_anteil_prozent?: number | null  // Anteil am Gesamtverbrauch

  // Per-Investition Finanzdetails (T-Konto)
  investitionen_financials: InvestitionFinancialDetail[]
  // Aktive Geräte je Typ im Monat (Namen) — für „aggregiert aus …"-Hinweise
  komponenten_geraete: Record<string, string[]>

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
