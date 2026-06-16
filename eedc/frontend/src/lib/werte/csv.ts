/**
 * CSV-Export der Werte-Tabelle — Header-/Zeilen-/Aggregat-Schema verhaltensgleich
 * aus `TabelleTab.handleExport`. Bei aktivem Vergleich wird jede Spalte zu drei
 * Spalten (aktuell · Vergleich · Δ), plus eine abschließende Aggregat-Zeile.
 */
import { MONAT_KURZ } from '../constants'
import { exportToCSV } from '../../utils/export'
import type { MonatsZeitreihe } from '../../pages/auswertung/types'
import type { WerteMetrik } from './registry'
import { getMonatWert } from './registry'
import { aggregiere } from './aggregate'

export interface WerteCsvOptions {
  rows: MonatsZeitreihe[]
  /** Vergleichs-Zeilen (Vorjahr o. Ä.); null = kein Vergleich. */
  vorjahrRows: MonatsZeitreihe[] | null
  /** Label der aktuellen Spalte (z. B. "2025"). */
  jahrLabel: string | number
  /** Label der Vergleichsspalte (z. B. "2024"); null = kein Vergleich. */
  vergleichLabel: string | number | null
  /** Aktive Metriken in Anzeige-Reihenfolge. */
  metriken: WerteMetrik[]
  dateiname: string
}

export function exportWerteCsv({ rows, vorjahrRows, jahrLabel, vergleichLabel, metriken, dateiname }: WerteCsvOptions) {
  const vergleich = vorjahrRows != null && vergleichLabel != null
  const vorjahrLookup: Record<number, MonatsZeitreihe> = {}
  if (vorjahrRows) for (const r of vorjahrRows) vorjahrLookup[r.monat] = r

  const headers: string[] = ['Jahr', 'Monat']
  metriken.forEach((m) => {
    const base = m.unit ? `${m.label} (${m.unit})` : m.label
    if (vergleich) {
      headers.push(`${base} ${jahrLabel}`)
      headers.push(`${base} ${vergleichLabel}`)
      headers.push(`Δ vs. ${vergleichLabel}`)
    } else {
      headers.push(base)
    }
  })

  const out: (string | number)[][] = rows.map((r) => {
    const prev = vergleich ? vorjahrLookup[r.monat] : undefined
    const zeile: (string | number)[] = [r.jahr, MONAT_KURZ[r.monat]]
    metriken.forEach((m) => {
      const v = getMonatWert(r, m.key)
      zeile.push(v != null ? v : '')
      if (vergleich) {
        const pv = prev ? getMonatWert(prev, m.key) : null
        zeile.push(pv != null ? pv : '')
        zeile.push(v != null && pv != null ? v - pv : '')
      }
    })
    return zeile
  })

  // Aggregat-Zeile (Jahres-Spanne + Monatszahl + Spalten-Aggregate)
  const agg = aggregiere(rows)
  const vorjahrAgg = vergleich && vorjahrRows ? aggregiere(vorjahrRows) : null
  const jahre = rows.map((r) => r.jahr)
  const aggZeile: (string | number)[] = [
    rows.length > 0 ? `${Math.min(...jahre)}–${Math.max(...jahre)}` : '',
    `${rows.length} Monate`,
  ]
  metriken.forEach((m) => {
    const v = agg[m.key]
    aggZeile.push(v != null ? v : '')
    if (vergleich) {
      const pv = vorjahrAgg?.[m.key] ?? null
      aggZeile.push(pv != null ? pv : '')
      aggZeile.push(v != null && pv != null ? v - pv : '')
    }
  })
  out.push(aggZeile)

  exportToCSV(headers, out, dateiname)
}
