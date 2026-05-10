/**
 * Zentrale Konstanten für das gesamte Frontend.
 *
 * Monatsnamen, Investitionstyp-Labels und andere wiederverwendbare
 * Definitionen, die in vielen Seiten dupliziert waren.
 */

import type { InvestitionTyp } from '../types'

// ─── Monatsnamen ─────────────────────────────────────────────────────────────

/** Kurze Monatsnamen, 1-basiert (Index 0 = leer). Für Chart-Labels, Tabellen. */
export const MONAT_KURZ = ['', 'Jan', 'Feb', 'Mär', 'Apr', 'Mai', 'Jun', 'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Dez']

/** Volle Monatsnamen, 1-basiert (Index 0 = leer). Für Überschriften, Formulare. */
export const MONAT_NAMEN = ['', 'Januar', 'Februar', 'März', 'April', 'Mai', 'Juni', 'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember']

// ─── Investitionstyp-Labels ──────────────────────────────────────────────────

/** Lesbare Labels für Investitionstypen. */
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

/**
 * Anzeige-Reihenfolge der DB-Investitions-Typen — Single Source of Truth.
 * Reihenfolge: Wechselrichter → PV-Module → Speicher → Balkonkraftwerk →
 * Verbraucher nach Wirkung auf Hausverbrauch (#214 detLAN: WP vor Wallbox).
 * `pv-system` ist nicht enthalten — virtueller Aggregat-Typ in der ROI-Tabelle
 * mit eigenem Container, wird nicht in dieser Reihe sortiert.
 * Spiegel im Backend: `backend/utils/investition_filter.py:INVESTITION_TYP_ORDER`.
 */
export const INVESTITION_TYP_ORDER: InvestitionTyp[] = [
  'wechselrichter',
  'pv-module',
  'speicher',
  'balkonkraftwerk',
  'waermepumpe',
  'wallbox',
  'e-auto',
  'sonstiges',
]

/** Sort-Comparator für Listen mit `.typ`-Feld. Unbekannte Typen ans Ende. */
export function compareTyp(a: { typ?: string | null }, b: { typ?: string | null }): number {
  const len = INVESTITION_TYP_ORDER.length
  const idxA = a.typ ? (INVESTITION_TYP_ORDER as readonly string[]).indexOf(a.typ) : -1
  const idxB = b.typ ? (INVESTITION_TYP_ORDER as readonly string[]).indexOf(b.typ) : -1
  return (idxA === -1 ? len : idxA) - (idxB === -1 ? len : idxB)
}

// ─── Regionen (Bundesländer + DACH) ─────────────────────────────────────────

/** Kurzcode → Klartext für deutsche Bundesländer + AT/CH. */
export const REGION_NAMEN: Record<string, string> = {
  BW: 'Baden-Württemberg',
  BY: 'Bayern',
  BE: 'Berlin',
  BB: 'Brandenburg',
  HB: 'Bremen',
  HH: 'Hamburg',
  HE: 'Hessen',
  MV: 'Mecklenburg-Vorpommern',
  NI: 'Niedersachsen',
  NW: 'Nordrhein-Westfalen',
  RP: 'Rheinland-Pfalz',
  SL: 'Saarland',
  SN: 'Sachsen',
  ST: 'Sachsen-Anhalt',
  SH: 'Schleswig-Holstein',
  TH: 'Thüringen',
  AT: 'Österreich',
  CH: 'Schweiz',
  XX: 'Unbekannt',
}

// ─── Sonstige Konstanten ─────────────────────────────────────────────────────

/** CO2-Emissionsfaktor Strommix Deutschland (kg CO2 pro kWh). */
export const CO2_FAKTOR_KG_KWH = 0.38
