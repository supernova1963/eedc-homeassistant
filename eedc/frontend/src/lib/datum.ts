/**
 * Datums-/Boolean-Anzeige-SoT (de-DE, R1) — EINE Stelle für deutsche
 * Datumsformatierung (TT.MM.JJJJ) und Ja/Nein statt true/false.
 * Interne ISO-Keys (Sortierung, API-Parameter, `<input type="date">`-Values)
 * bleiben ISO — hier NICHT durchschleusen.
 */

const FALLBACK = '—'

/** ISO → Date nach EINER Parse-Regel (beide Formatierer nutzen sie). */
function parseIso(iso: string): Date {
  // reine Datums-ISO ohne Zeit → Mittag, damit keine TZ-Verschiebung den Tag kippt.
  return new Date(/^\d{4}-\d{2}-\d{2}$/.test(iso) ? `${iso}T12:00:00` : iso)
}

/** ISO-Datum (`'2023-06-01'` oder voller ISO-String) → `'01.06.2023'` (de-DE). */
export function formatDatum(iso: string | null | undefined): string {
  if (!iso) return FALLBACK
  const d = parseIso(iso)
  if (Number.isNaN(d.getTime())) return String(iso)
  return d.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric' })
}

/**
 * Zeitraum kompakt (de-DE, #360): `28.–30.07.2025` bei gleichem Monat,
 * `28.06.–03.07.2025` bei gleichem Jahr, sonst beide Daten voll
 * (`28.12.2024–03.01.2025`). Das Bis-Datum steht IMMER vollständig — es trägt
 * die Einordnung, das Von-Datum kürzt nur, was daraus schon hervorgeht.
 *
 * Fehlt bzw. kippt das Bis-Datum, bleibt das Von-Datum allein stehen (kein
 * halber Bindestrich, der einen offenen Zeitraum behauptet).
 */
export function formatZeitraumKurz(
  vonIso: string | null | undefined,
  bisIso: string | null | undefined,
): string {
  if (!vonIso) return FALLBACK
  const von = parseIso(vonIso)
  if (Number.isNaN(von.getTime())) return String(vonIso)
  if (!bisIso) return formatDatum(vonIso)
  const bis = parseIso(bisIso)
  if (Number.isNaN(bis.getTime())) return formatDatum(vonIso)

  const zwei = (n: number) => String(n).padStart(2, '0')
  if (von.getFullYear() !== bis.getFullYear()) {
    return `${formatDatum(vonIso)}–${formatDatum(bisIso)}`
  }
  if (von.getMonth() === bis.getMonth()) {
    return `${zwei(von.getDate())}.–${formatDatum(bisIso)}`
  }
  return `${zwei(von.getDate())}.${zwei(von.getMonth() + 1)}.–${formatDatum(bisIso)}`
}

/** Boolean → deutsche Ja/Nein-Anzeige (statt roh „true"/„false"). */
export function jaNein(v: boolean | null | undefined): string {
  return v == null ? FALLBACK : v ? 'Ja' : 'Nein'
}
