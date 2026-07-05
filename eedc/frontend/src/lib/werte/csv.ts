/**
 * CSV-Export der Werte-Tabelle — Header-/Zeilen-/Aggregat-Schema verhaltensgleich
 * aus `TabelleTab.handleExport`, jetzt granularitäts-agnostisch über `WerteZeile`.
 * Bei aktivem Vergleich wird jede Spalte zu drei Spalten (aktuell · Vergleich · Δ),
 * plus eine abschließende Aggregat-Zeile.
 */
import { exportToCSV } from '../../utils/export'
import type { WerteMetrik } from './registry'
import type { WerteZeile } from './zeile'
import { aggregiere } from './aggregate'

export interface WerteCsvOptions {
  rows: WerteZeile[]
  /** Vergleichs-Zeilen (Vorjahr/Vergleichsmonat); null = kein Vergleich. */
  vorjahrRows: WerteZeile[] | null
  /** Label der aktuellen Spalte (z. B. "2025"). */
  jahrLabel: string | number
  /** Label der Vergleichsspalte (z. B. "2024"); null = kein Vergleich. */
  vergleichLabel: string | number | null
  /** Aktive Metriken in Anzeige-Reihenfolge. */
  metriken: WerteMetrik[]
  /** Einheit der Aggregat-Zeile ("Monate" / "Tage"). */
  einheitLabel: string
  dateiname: string
}

export function exportWerteCsv({
  rows, vorjahrRows, jahrLabel, vergleichLabel, metriken, einheitLabel, dateiname,
}: WerteCsvOptions) {
  const vergleich = vorjahrRows != null && vergleichLabel != null
  const vorjahrLookup: Record<number, WerteZeile> = {}
  if (vorjahrRows) for (const r of vorjahrRows) vorjahrLookup[r.vergleichKey] = r

  const headers: string[] = ['Zeitraum']
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

  // C3/S20 (R3b, 2026-07-05): Rundung VOR dem Export — max. 4 NK. Kappt
  // Float-Artefakte (0.4−0.1 → „0,30000000000000004") ohne Datenverlust
  // (bewusst NICHT die Anzeige-decimals der Registry: die würden kWh auf 0 NK
  // stutzen — CSV bleibt maschinenlesbar präziser als die Tabelle).
  const rund = (v: number) => Math.round(v * 1e4) / 1e4

  const out: (string | number)[][] = rows.map((r) => {
    const prev = vergleich ? vorjahrLookup[r.vergleichKey] : undefined
    const zeile: (string | number)[] = [r.label]
    metriken.forEach((m) => {
      const v = r.wert(m.key)
      zeile.push(v != null ? rund(v) : '')
      if (vergleich) {
        const pv = prev ? prev.wert(m.key) : null
        zeile.push(pv != null ? rund(pv) : '')
        zeile.push(v != null && pv != null ? rund(v - pv) : '')
      }
    })
    return zeile
  })

  // Aggregat-Zeile (Anzahl + Spalten-Aggregate)
  const agg = aggregiere(rows, metriken)
  const vorjahrAgg = vergleich && vorjahrRows ? aggregiere(vorjahrRows, metriken) : null
  const aggZeile: (string | number)[] = [`${rows.length} ${einheitLabel}`]
  metriken.forEach((m) => {
    const v = agg[m.key]
    aggZeile.push(v != null ? rund(v) : '')
    if (vergleich) {
      const pv = vorjahrAgg?.[m.key] ?? null
      aggZeile.push(pv != null ? rund(pv) : '')
      aggZeile.push(v != null && pv != null ? rund(v - pv) : '')
    }
  })
  out.push(aggZeile)

  exportToCSV(headers, out, dateiname)
}
