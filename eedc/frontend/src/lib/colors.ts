/**
 * Zentrale Farbdefinitionen für Charts und Investitionstypen.
 *
 * Alle Hex-Farbwerte an einer Stelle. Vermeidet inline #hex-Duplikate
 * über 30+ Dateien hinweg.
 */

// ─── Basis-Farben ────────────────────────────────────────────────────────────

export const COLORS = {
  solar: '#f59e0b',
  grid: '#ef4444',
  consumption: '#8b5cf6',
  battery: '#3b82f6',
  feedin: '#10b981',
}

// ─── Chart-Farben (nach Metrik) ──────────────────────────────────────────────

export const CHART_COLORS = {
  // Energie
  erzeugung: '#f59e0b',          // Amber
  eigenverbrauch: '#8b5cf6',     // Purple
  einspeisung: '#10b981',        // Emerald
  netzbezug: '#ef4444',          // Red
  autarkie: '#3b82f6',           // Blue
  evQuote: '#a855f7',            // Purple-500
  direktverbrauch: '#f97316',    // Orange
  spezErtrag: '#eab308',         // Yellow
  // Speicher
  speicherLadung: '#22c55e',     // Green
  speicherEntladung: '#3b82f6',  // Blue
  speicherEffizienz: '#06b6d4',  // Cyan
  // Wärmepumpe
  wpWaerme: '#ef4444',           // Red
  wpStrom: '#8b5cf6',            // Purple
  wpCop: '#f97316',              // Orange
  // E-Mobilität
  emobKm: '#8b5cf6',             // Purple
  emobLadung: '#3b82f6',         // Blue
  emobPvAnteil: '#10b981',       // Green
  // CO2
  co2Pv: '#10b981',              // Emerald
  co2Wp: '#ef4444',              // Red
  co2Emob: '#8b5cf6',            // Purple
  // Finanzen
  einspeiseErloes: '#10b981',    // Green
  evErsparnis: '#8b5cf6',        // Purple
  wpErsparnis: '#ef4444',        // Red
  emobErsparnis: '#3b82f6',      // Blue
  nettoErtrag: '#059669',        // Emerald-600
}

// ─── Tagesverlauf-Kategorien ─────────────────────────────────────────────────

/** Farben für Energiefluss- und Bilanz-Visualisierungen (nach Tagesverlauf-Kategorie) */
export const KATEGORIE_FARBEN: Record<string, string> = {
  pv: '#eab308',
  netz: '#ef4444',
  batterie: '#3b82f6',
  eauto: '#a855f7',
  wallbox: '#a855f7',
  waermepumpe: '#f97316',
  sonstige: '#6b7280',
  haushalt: '#10b981',
}

/**
 * Kategorien die KEINE Energieflüsse darstellen (z.B. Preise, virtuelle Serien).
 * Werden im Verbrauchs-Stacking (WetterWidget etc.) ignoriert.
 * → Neue nicht-Energie-Kategorien hier ergänzen, nicht in einzelnen Komponenten.
 */
export const NICHT_ENERGIE_KATEGORIEN = new Set(['preis', 'virtual'])

/** Kategorien die dedizierte DB-Felder/Spalten haben (kein Extra-Tracking nötig) */
export const DEDIZIERTE_KATEGORIEN = new Set([
  'pv', 'batterie', 'netz', 'haushalt', 'waermepumpe', 'wallbox', 'eauto', 'virtual',
])

// ─── Typ-Farben (für Investitionstypen) ──────────────────────────────────────

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
