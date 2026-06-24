/**
 * TagStepper — schwebende „Player"-Tagesauswahl der Cockpit/Tag-Sicht (mobil),
 * Pendant zu {@link MonatStepper}. Desktop behält die {@link TagesRail}, mobil
 * ersetzt dieser sticky Stepper sie:
 *   ⏮ ältester · ⏪ −7 Tage · ◀ −1 Tag · [Datum ▾ → Liste] · ▶ +1 Tag · ⏩ +7 Tage · ⏭ neuester
 * Antippbare Mitte öffnet die Tagesliste (PV/„heute") + ein Datumsfeld für den
 * Direktsprung. Buttons ohne Ziel sind an den Rändern deaktiviert.
 */
import { useMemo, useState } from 'react'
import type { LucideIcon } from 'lucide-react'
import { ChevronFirst, ChevronsLeft, ChevronLeft, ChevronRight, ChevronsRight, ChevronLast, ChevronDown } from 'lucide-react'
import type { TagRailEintrag } from './TagesRail'

interface TagStepperProps {
  entries: TagRailEintrag[]
  datum: string
  onSelect: (datum: string) => void
}

const WT_KURZ = ['So', 'Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa']
const verschieben = (iso: string, n: number) => {
  const d = new Date(iso + 'T12:00:00'); d.setDate(d.getDate() + n); return d.toISOString().slice(0, 10)
}
const label = (iso: string) => {
  const d = new Date(iso + 'T12:00:00')
  return `${WT_KURZ[d.getDay()]} ${d.getDate()}. ${d.toLocaleDateString('de-DE', { month: 'short', year: 'numeric' })}`
}

export function TagStepper({ entries, datum, onSelect }: TagStepperProps) {
  const [offen, setOffen] = useState(false)
  const desc = useMemo(() => [...entries].sort((a, b) => (a.datum < b.datum ? 1 : -1)), [entries])
  const oldest = useMemo(() => entries.reduce((m, e) => (m && m < e.datum ? m : e.datum), entries[0]?.datum ?? datum), [entries, datum])
  const newest = useMemo(() => entries.reduce((m, e) => (m && m > e.datum ? m : e.datum), entries[0]?.datum ?? datum), [entries, datum])

  const clamp = (iso: string) => (iso < oldest ? oldest : iso > newest ? newest : iso)
  const ziel = (iso: string): string | null => {
    const c = clamp(iso)
    return c === datum ? null : c
  }
  const aktuell = entries.find((e) => e.datum === datum) ?? null

  const Btn = ({ ziel: z, icon: Icon, lbl }: { ziel: string | null; icon: LucideIcon; lbl: string }) => (
    <button
      type="button"
      disabled={!z}
      onClick={() => z && onSelect(z)}
      aria-label={lbl}
      title={lbl}
      className="flex items-center justify-center h-9 w-8 shrink-0 rounded-md text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700/50 transition-colors disabled:opacity-30 disabled:cursor-default disabled:hover:bg-transparent"
    >
      <Icon className="h-4 w-4" />
    </button>
  )

  return (
    <div className="lg:hidden sticky top-0 z-20 -mx-3 px-3 pt-1 pb-2 mb-3 bg-gray-50/80 dark:bg-gray-900/80 backdrop-blur-sm">
      <div className="flex items-center gap-0.5 max-w-md mx-auto rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 px-1 py-1 shadow-sm">
        <Btn ziel={ziel(oldest)} icon={ChevronFirst} lbl="ältester Tag" />
        <Btn ziel={ziel(verschieben(datum, -7))} icon={ChevronsLeft} lbl="7 Tage zurück" />
        <Btn ziel={ziel(verschieben(datum, -1))} icon={ChevronLeft} lbl="voriger Tag" />
        <button
          type="button"
          onClick={() => setOffen((o) => !o)}
          aria-expanded={offen}
          className="flex-1 flex items-center justify-center gap-1.5 h-9 min-w-0 rounded-md text-sm font-semibold text-gray-900 dark:text-white hover:bg-gray-100 dark:hover:bg-gray-700/50 transition-colors"
        >
          <span className="truncate">{label(datum)}</span>
          {aktuell?.heute && (
            <span className="text-[10px] leading-none px-1 py-0.5 rounded-full bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300">heute</span>
          )}
          <ChevronDown className={`h-4 w-4 shrink-0 transition-transform ${offen ? 'rotate-180' : ''}`} />
        </button>
        <Btn ziel={ziel(verschieben(datum, 1))} icon={ChevronRight} lbl="nächster Tag" />
        <Btn ziel={ziel(verschieben(datum, 7))} icon={ChevronsRight} lbl="7 Tage vor" />
        <Btn ziel={ziel(newest)} icon={ChevronLast} lbl="neuester Tag" />
      </div>

      {offen && (
        <div className="mt-1 max-h-72 overflow-y-auto rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 shadow-lg">
          {/* Direktsprung per Datumsfeld (Tage sind viele — anders als Monate). */}
          <div className="px-3 py-2 border-b border-gray-100 dark:border-gray-700/50">
            <input
              type="date" aria-label="Datum wählen" value={datum} max={newest} min={oldest}
              onChange={(e) => { if (e.target.value) { onSelect(clamp(e.target.value)); setOffen(false) } }}
              className="input w-full text-sm"
            />
          </div>
          <div className="divide-y divide-gray-100 dark:divide-gray-700/50">
            {desc.map((e) => {
              const sel = e.datum === datum
              return (
                <button
                  key={e.datum}
                  type="button"
                  onClick={() => { onSelect(e.datum); setOffen(false) }}
                  className={`flex w-full items-center justify-between gap-3 px-3 py-2 text-sm transition-colors ${
                    sel
                      ? 'bg-primary-50 dark:bg-primary-900/30 text-primary-700 dark:text-primary-300 font-semibold'
                      : 'text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700/40'
                  }`}
                >
                  <span>{label(e.datum)}</span>
                  <span className={`text-xs ${e.heute ? 'text-emerald-500 dark:text-emerald-400' : 'text-gray-400 dark:text-gray-500 tabular-nums'}`}>
                    {e.heute ? 'heute' : `${Math.round(e.pv_kwh)} kWh`}
                  </span>
                </button>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}
