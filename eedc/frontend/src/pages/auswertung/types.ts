// Gemeinsame Types für Auswertungs-Tabs
import type { useAnlagen, useMonatsdaten, useMonatsdatenStats, useAktuellerStrompreis } from '../../hooks'

// Monatsnamen für Labels
export const monatNamen = ['', 'Jan', 'Feb', 'Mär', 'Apr', 'Mai', 'Jun', 'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Dez']

// Basis-Farben
export const COLORS = {
  solar: '#f59e0b',
  grid: '#ef4444',
  consumption: '#8b5cf6',
  battery: '#3b82f6',
  feedin: '#10b981',
}

// Distinct colors for charts
export const CHART_COLORS = {
  erzeugung: '#f59e0b',      // Amber
  eigenverbrauch: '#8b5cf6', // Purple
  einspeisung: '#10b981',    // Emerald
  netzbezug: '#ef4444',      // Red
  autarkie: '#3b82f6',       // Blue
  evQuote: '#a855f7',        // Purple-500 (different shade)
  direktverbrauch: '#f97316', // Orange
  spezErtrag: '#eab308',     // Yellow
  speicherLadung: '#22c55e', // Green
  speicherEntladung: '#3b82f6', // Blue
  speicherEffizienz: '#06b6d4', // Cyan
  wpWaerme: '#ef4444',       // Red
  wpStrom: '#8b5cf6',        // Purple
  wpCop: '#f97316',          // Orange
  emobKm: '#8b5cf6',         // Purple
  emobLadung: '#3b82f6',     // Blue
  emobPvAnteil: '#10b981',   // Green
  co2Pv: '#10b981',          // Emerald
  co2Wp: '#ef4444',          // Red
  co2Emob: '#8b5cf6',        // Purple
  einspeiseErloes: '#10b981', // Green
  evErsparnis: '#8b5cf6',    // Purple
  wpErsparnis: '#ef4444',    // Red
  emobErsparnis: '#3b82f6',  // Blue
  nettoErtrag: '#059669',    // Emerald-600
}

// Typ-Farben für Investitionen
export const TYP_COLORS: Record<string, string> = {
  'pv-module': '#f59e0b',
  'wechselrichter': '#eab308',
  'speicher': '#3b82f6',
  'e-auto': '#8b5cf6',
  'wallbox': '#06b6d4',
  'waermepumpe': '#ef4444',
  'balkonkraftwerk': '#10b981',
  'sonstiges': '#6b7280',
  'pv-system': '#f97316',
}

export const TYP_LABELS: Record<string, string> = {
  'pv-module': 'PV-Module',
  'wechselrichter': 'Wechselrichter',
  'speicher': 'Speicher',
  'e-auto': 'E-Auto',
  'wallbox': 'Wallbox',
  'waermepumpe': 'Wärmepumpe',
  'balkonkraftwerk': 'Balkonkraftwerk',
  'sonstiges': 'Sonstiges',
  'pv-system': 'PV-System',
}

// Tab Props
export interface TabProps {
  data: ReturnType<typeof useMonatsdaten>['monatsdaten']
  stats: ReturnType<typeof useMonatsdatenStats>
  anlage?: ReturnType<typeof useAnlagen>['anlagen'][0]
  strompreis?: ReturnType<typeof useAktuellerStrompreis>['strompreis']
}

// Interface für Monatsdaten-Zeitreihen
export interface MonatsZeitreihe {
  name: string  // z.B. "Jan 24"
  jahr: number
  monat: number
  // Energie
  erzeugung: number
  eigenverbrauch: number
  einspeisung: number
  netzbezug: number
  gesamtverbrauch: number
  direktverbrauch: number
  // Quoten
  autarkie: number
  evQuote: number
  spezErtrag: number
  // Speicher
  speicher_ladung: number
  speicher_entladung: number
  speicher_effizienz: number | null
  // Wärmepumpe
  wp_waerme: number
  wp_strom: number
  wp_cop: number | null
  // E-Auto
  eauto_km: number
  eauto_ladung: number
  eauto_pv_anteil: number | null
  // Finanzen
  einspeise_erloes: number
  ev_ersparnis: number
  netzbezug_kosten: number
  netto_ertrag: number
  // CO2
  co2_einsparung: number
}

// Helper-Funktion zum Erstellen der Monatszeitreihen
export function createMonatsZeitreihe(
  data: TabProps['data'],
  anlage?: TabProps['anlage'],
  strompreis?: TabProps['strompreis']
): MonatsZeitreihe[] {
  const sorted = [...data].sort((a, b) => {
    if (a.jahr !== b.jahr) return a.jahr - b.jahr
    return a.monat - b.monat
  })

  return sorted.map(md => {
    const erzeugung = md.pv_erzeugung_kwh || (md.einspeisung_kwh + (md.eigenverbrauch_kwh || 0))
    const eigenverbrauch = md.eigenverbrauch_kwh || 0
    const gesamtverbrauch = md.gesamtverbrauch_kwh || (eigenverbrauch + md.netzbezug_kwh)
    const direktverbrauch = md.direktverbrauch_kwh || 0

    // Quoten berechnen
    const autarkie = gesamtverbrauch > 0 ? (eigenverbrauch / gesamtverbrauch) * 100 : 0
    const evQuote = erzeugung > 0 ? (eigenverbrauch / erzeugung) * 100 : 0
    const spezErtrag = anlage?.leistung_kwp ? erzeugung / anlage.leistung_kwp : 0

    // Speicher (Batterie)
    const speicher_ladung = md.batterie_ladung_kwh || 0
    const speicher_entladung = md.batterie_entladung_kwh || 0
    const speicher_effizienz = speicher_ladung > 0 ? (speicher_entladung / speicher_ladung) * 100 : null

    // Wärmepumpe - aktuell nicht in Monatsdaten, placeholder für Erweiterung
    const wp_waerme = 0
    const wp_strom = 0
    const wp_cop = null

    // E-Auto - aktuell nicht in Monatsdaten, placeholder für Erweiterung
    const eauto_km = 0
    const eauto_ladung = 0
    const eauto_pv_anteil = null

    // Finanzen
    const einspeise_erloes = strompreis
      ? md.einspeisung_kwh * strompreis.einspeiseverguetung_cent_kwh / 100
      : 0
    const ev_ersparnis = strompreis
      ? eigenverbrauch * strompreis.netzbezug_arbeitspreis_cent_kwh / 100
      : 0
    const netzbezug_kosten = strompreis
      ? md.netzbezug_kwh * strompreis.netzbezug_arbeitspreis_cent_kwh / 100
      : 0
    const netto_ertrag = einspeise_erloes + ev_ersparnis

    // CO2
    const CO2_FAKTOR = 0.38 // kg CO2 pro kWh
    const co2_einsparung = erzeugung * CO2_FAKTOR

    return {
      name: `${monatNamen[md.monat]} ${md.jahr.toString().slice(-2)}`,
      jahr: md.jahr,
      monat: md.monat,
      erzeugung,
      eigenverbrauch,
      einspeisung: md.einspeisung_kwh,
      netzbezug: md.netzbezug_kwh,
      gesamtverbrauch,
      direktverbrauch,
      autarkie,
      evQuote,
      spezErtrag,
      speicher_ladung,
      speicher_entladung,
      speicher_effizienz,
      wp_waerme,
      wp_strom,
      wp_cop,
      eauto_km,
      eauto_ladung,
      eauto_pv_anteil,
      einspeise_erloes,
      ev_ersparnis,
      netzbezug_kosten,
      netto_ertrag,
      co2_einsparung,
    }
  })
}
