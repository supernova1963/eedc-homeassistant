/**
 * Zahl-Formatierung für die Werte-Tabelle (de-DE, feste Nachkommastellen).
 * Verhaltensgleich aus `TabelleTab.fmtVal` herausgelöst.
 */
export function fmtWert(v: number | null, decimals: number): string {
  if (v == null) return '—'
  return v.toLocaleString('de-DE', { minimumFractionDigits: decimals, maximumFractionDigits: decimals })
}
