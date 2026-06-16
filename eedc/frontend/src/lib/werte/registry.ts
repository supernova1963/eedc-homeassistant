/**
 * W1 — Metrik-Registry (Werte/Tabelle-SoT, IA v4 E3 Slice 3.1).
 *
 * Eine Quelle der Wahrheit für alle tabellarischen Kennzahl-Spalten: Label,
 * Einheit, Format, Aggregation, Gruppe und Richtung („mehr ist besser").
 * Verhaltensgleich aus `pages/auswertung/TabelleTab.tsx` (23 Spalten)
 * herausgelöst — die Werkbank UND die read-only Embeds (Cockpit-Zeitsichten,
 * Komponenten) speisen sich künftig aus dieser Registry.
 *
 * Granularitäts-Naht: aktuell nur der Monats-Accessor `getMonatWert`. Tag/
 * Stunde (`get.tag`/`get.stunde`) docken später an dieselbe Registry an
 * (Plan 3.2), ohne die Spalten-Definition zu duplizieren.
 */
import type { MonatsZeitreihe } from '../../pages/auswertung/types'

export type WerteGruppe = 'basis' | 'quoten' | 'speicher' | 'waermepumpe' | 'eauto' | 'finanzen' | 'co2'
export type WerteAggregation = 'sum' | 'avg' | 'none'

export interface WerteMetrik {
  key: string
  label: string
  unit: string
  gruppe: WerteGruppe
  decimals: number
  aggregation: WerteAggregation
  defaultVisible: boolean
  /** true=höher besser, false=niedriger besser, undefined=neutral (Δ grau). */
  higherIsBetter?: boolean
}

// Reihenfolge + Werte 1:1 aus TabelleTab.COLUMNS (verhaltensgleich).
export const WERTE_METRIKEN: WerteMetrik[] = [
  // Energie
  { key: 'erzeugung',          label: 'PV-Erzeugung',      unit: 'kWh',     gruppe: 'basis',       decimals: 0, aggregation: 'sum', defaultVisible: true,  higherIsBetter: true },
  { key: 'eigenverbrauch',     label: 'Eigenverbrauch',    unit: 'kWh',     gruppe: 'basis',       decimals: 0, aggregation: 'sum', defaultVisible: true,  higherIsBetter: true },
  { key: 'einspeisung',        label: 'Einspeisung',       unit: 'kWh',     gruppe: 'basis',       decimals: 0, aggregation: 'sum', defaultVisible: true,  higherIsBetter: true },
  { key: 'netzbezug',          label: 'Netzbezug',         unit: 'kWh',     gruppe: 'basis',       decimals: 0, aggregation: 'sum', defaultVisible: true,  higherIsBetter: false },
  { key: 'gesamtverbrauch',    label: 'Gesamtverbrauch',   unit: 'kWh',     gruppe: 'basis',       decimals: 0, aggregation: 'sum', defaultVisible: false, higherIsBetter: undefined },
  { key: 'direktverbrauch',    label: 'Direktverbrauch',   unit: 'kWh',     gruppe: 'basis',       decimals: 0, aggregation: 'sum', defaultVisible: false, higherIsBetter: true },
  // Quoten
  { key: 'autarkie',           label: 'Autarkie',          unit: '%',       gruppe: 'quoten',      decimals: 1, aggregation: 'avg', defaultVisible: true,  higherIsBetter: true },
  { key: 'evQuote',            label: 'EV-Quote',          unit: '%',       gruppe: 'quoten',      decimals: 1, aggregation: 'avg', defaultVisible: true,  higherIsBetter: true },
  { key: 'spezErtrag',         label: 'Spez. Ertrag',      unit: 'kWh/kWp', gruppe: 'quoten',      decimals: 0, aggregation: 'sum', defaultVisible: false, higherIsBetter: true },
  // Speicher
  { key: 'speicher_ladung',    label: 'Speicher Ladung',    unit: 'kWh',    gruppe: 'speicher',    decimals: 0, aggregation: 'sum', defaultVisible: false, higherIsBetter: undefined },
  { key: 'speicher_entladung', label: 'Speicher Entladung', unit: 'kWh',    gruppe: 'speicher',    decimals: 0, aggregation: 'sum', defaultVisible: false, higherIsBetter: undefined },
  { key: 'speicher_effizienz', label: 'Speicher Effizienz', unit: '%',      gruppe: 'speicher',    decimals: 1, aggregation: 'avg', defaultVisible: false, higherIsBetter: true },
  // Wärmepumpe
  { key: 'wp_strom',           label: 'WP Strom',          unit: 'kWh',     gruppe: 'waermepumpe', decimals: 0, aggregation: 'sum', defaultVisible: false, higherIsBetter: undefined },
  { key: 'wp_waerme',          label: 'WP Wärme',          unit: 'kWh',     gruppe: 'waermepumpe', decimals: 0, aggregation: 'sum', defaultVisible: false, higherIsBetter: true },
  { key: 'wp_cop',             label: 'WP COP',            unit: '',        gruppe: 'waermepumpe', decimals: 1, aggregation: 'avg', defaultVisible: false, higherIsBetter: true },
  // E-Auto
  { key: 'eauto_km',           label: 'E-Auto',            unit: 'km',      gruppe: 'eauto',       decimals: 0, aggregation: 'sum', defaultVisible: false, higherIsBetter: undefined },
  { key: 'eauto_ladung',       label: 'E-Auto Ladung',     unit: 'kWh',     gruppe: 'eauto',       decimals: 0, aggregation: 'sum', defaultVisible: false, higherIsBetter: undefined },
  // Finanzen — Berechnung via createMonatsZeitreihe mit historisch korrektem Tarif pro Monat
  { key: 'einspeise_erloes',   label: 'Einspeise-Erlös',   unit: '€',       gruppe: 'finanzen',    decimals: 2, aggregation: 'sum', defaultVisible: true,  higherIsBetter: true },
  { key: 'ev_ersparnis',       label: 'EV-Ersparnis',      unit: '€',       gruppe: 'finanzen',    decimals: 2, aggregation: 'sum', defaultVisible: true,  higherIsBetter: true },
  { key: 'netzbezug_kosten',   label: 'Netzbezug-Kosten',  unit: '€',       gruppe: 'finanzen',    decimals: 2, aggregation: 'sum', defaultVisible: true,  higherIsBetter: false },
  { key: 'netto_ertrag',       label: 'Netto-Ertrag',      unit: '€',       gruppe: 'finanzen',    decimals: 2, aggregation: 'sum', defaultVisible: false, higherIsBetter: true },
  { key: 'netto_bilanz',       label: 'Netto-Bilanz',      unit: '€',       gruppe: 'finanzen',    decimals: 2, aggregation: 'sum', defaultVisible: true,  higherIsBetter: true },
  // CO2
  { key: 'co2_einsparung',     label: 'CO₂-Einsparung',    unit: 'kg',      gruppe: 'co2',         decimals: 1, aggregation: 'sum', defaultVisible: false, higherIsBetter: true },
]

export const WERTE_GRUPPEN: WerteGruppe[] = ['basis', 'quoten', 'speicher', 'waermepumpe', 'eauto', 'finanzen', 'co2']

export const GRUPPE_LABELS: Record<WerteGruppe, string> = {
  basis:       'Energie',
  quoten:      'Quoten',
  speicher:    'Speicher',
  waermepumpe: 'Wärmepumpe',
  eauto:       'E-Auto',
  finanzen:    'Finanzen',
  co2:         'CO₂',
}

/** Schnell-Lookup Metrik per key. */
export const METRIK_BY_KEY: Record<string, WerteMetrik> = Object.fromEntries(
  WERTE_METRIKEN.map((m) => [m.key, m]),
)

/**
 * Granularitäts-Accessor „Monat": liest den Spalten-Wert aus einer
 * `MonatsZeitreihe`-Zeile. Die Registry-keys sind deckungsgleich mit den
 * Zeilen-Properties (verhaltensgleich zu TabelleTab `row[col.key]`).
 */
export function getMonatWert(row: MonatsZeitreihe, key: string): number | null {
  const v = (row as unknown as Record<string, number | null | undefined>)[key]
  return v == null ? null : v
}
