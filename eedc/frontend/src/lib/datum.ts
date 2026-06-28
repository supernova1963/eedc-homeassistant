/**
 * Datums-/Boolean-Anzeige-SoT (de-DE, R1) — EINE Stelle für deutsche
 * Datumsformatierung (TT.MM.JJJJ) und Ja/Nein statt true/false.
 * Interne ISO-Keys (Sortierung, API-Parameter, `<input type="date">`-Values)
 * bleiben ISO — hier NICHT durchschleusen.
 */

const FALLBACK = '—'

/** ISO-Datum (`'2023-06-01'` oder voller ISO-String) → `'01.06.2023'` (de-DE). */
export function formatDatum(iso: string | null | undefined): string {
  if (!iso) return FALLBACK
  // reine Datums-ISO ohne Zeit → Mittag, damit keine TZ-Verschiebung den Tag kippt.
  const d = new Date(/^\d{4}-\d{2}-\d{2}$/.test(iso) ? `${iso}T12:00:00` : iso)
  if (Number.isNaN(d.getTime())) return String(iso)
  return d.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric' })
}

/** Boolean → deutsche Ja/Nein-Anzeige (statt roh „true"/„false"). */
export function jaNein(v: boolean | null | undefined): string {
  return v == null ? FALLBACK : v ? 'Ja' : 'Nein'
}
