/**
 * TagStepper — Tages-Adapter der generischen {@link ZeitStepper}-SoT (mobil).
 * Desktop behält die {@link TagesRail}; mobil:
 *   ⏮ ältester · ⏪ −7 Tage · ◀ −1 Tag · [Datum ▾ → Liste + Date-Picker] · ▶ +1 Tag · ⏩ +7 Tage · ⏭ neuester
 * Tag-Spezifika: ISO-Datums-Navigation + ein Date-Picker als Direktsprung (Tage
 * sind viele — anders als Monate/Jahre).
 */
import { useMemo } from 'react'
import { ChevronFirst, ChevronsLeft, ChevronLeft, ChevronRight, ChevronsRight, ChevronLast } from 'lucide-react'
import type { TagRailEintrag } from './TagesRail'
import { ZeitStepper, type ZeitStepperEintrag } from './ZeitStepper'
import { fmtZahl } from '../lib'

interface TagStepperProps {
  entries: TagRailEintrag[]
  datum: string
  onSelect: (datum: string) => void
  /** Ältester verfügbarer Tag (jenseits der 90-Tage-Liste) — Untergrenze für die
   *  Datumsauswahl, damit ALLE vorhandenen Tage direkt anspringbar sind. */
  aeltesterTag?: string
  /** D10-2: im Fokus/Vollbild-Kopf auf jeder Breite sichtbar (durchgereicht). */
  immerSichtbar?: boolean
}

const WT_KURZ = ['So', 'Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa']
const verschieben = (iso: string, n: number) => {
  const d = new Date(iso + 'T12:00:00'); d.setDate(d.getDate() + n); return d.toISOString().slice(0, 10)
}
const label = (iso: string) => {
  const d = new Date(iso + 'T12:00:00')
  return `${WT_KURZ[d.getDay()]} ${d.getDate()}. ${d.toLocaleDateString('de-DE', { month: 'short', year: 'numeric' })}`
}

export function TagStepper({ entries, datum, onSelect, aeltesterTag, immerSichtbar }: TagStepperProps) {
  const desc = useMemo(() => [...entries].sort((a, b) => (a.datum < b.datum ? 1 : -1)), [entries])
  const oldest = useMemo(() => entries.reduce((m, e) => (m && m < e.datum ? m : e.datum), entries[0]?.datum ?? datum), [entries, datum])
  const newest = useMemo(() => entries.reduce((m, e) => (m && m > e.datum ? m : e.datum), entries[0]?.datum ?? datum), [entries, datum])
  // Untergrenze für Navigation/Datumsauswahl = ältester verfügbarer Tag (kann vor
  // der 90-Tage-Liste liegen); Fallback = ältester Listen-Tag.
  const untergrenze = aeltesterTag && aeltesterTag < oldest ? aeltesterTag : oldest

  const clamp = (iso: string) => (iso < untergrenze ? untergrenze : iso > newest ? newest : iso)
  // Ziel-Aktion oder null (am Rand / auf sich selbst deaktiviert).
  const go = (iso: string) => {
    const c = clamp(iso)
    return c === datum ? null : () => onSelect(c)
  }
  const aktuell = entries.find((e) => e.datum === datum) ?? null

  const eintraege: ZeitStepperEintrag[] = desc.map((e) => ({
    key: e.datum,
    label: label(e.datum),
    wert: e.heute ? 'heute' : `${fmtZahl(e.pv_kwh, 0)} kWh`,
    aktiv: !!e.heute,
    gewaehlt: e.datum === datum,
    onClick: () => onSelect(e.datum),
  }))

  return (
    <ZeitStepper
      zurueck={[
        { icon: ChevronFirst, label: 'ältester Tag', go: go(untergrenze) },
        { icon: ChevronsLeft, label: '7 Tage zurück', go: go(verschieben(datum, -7)) },
        { icon: ChevronLeft, label: 'voriger Tag', go: go(verschieben(datum, -1)) },
      ]}
      vor={[
        { icon: ChevronRight, label: 'nächster Tag', go: go(verschieben(datum, 1)) },
        { icon: ChevronsRight, label: '7 Tage vor', go: go(verschieben(datum, 7)) },
        { icon: ChevronLast, label: 'neuester Tag', go: go(newest) },
      ]}
      titel={label(datum)}
      badge={aktuell?.heute ? 'heute' : null}
      eintraege={eintraege}
      direktsprung={(close) => (
        <div className="space-y-2">
          {/* Datumsauswahl erreicht ALLE verfügbaren Tage (min = ältester Tag). */}
          <input
            type="date" aria-label="Datum wählen" value={datum} max={newest} min={untergrenze}
            onChange={(e) => { if (e.target.value) { onSelect(clamp(e.target.value)); close() } }}
            className="input w-full text-sm"
          />
          {/* Zurücksetzen → neuester Tag (Ausgangs-Ansicht), wenn man in die
              Historie gesprungen ist (Gernot 2026-06-26). */}
          {datum !== newest && (
            <button
              type="button"
              onClick={() => { onSelect(newest); close() }}
              className="w-full text-xs px-2 py-1 rounded-lg border border-gray-200 dark:border-gray-700 text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors"
            >
              ↺ Zurücksetzen (neuester Tag)
            </button>
          )}
        </div>
      )}
      immerSichtbar={immerSichtbar}
    />
  )
}
