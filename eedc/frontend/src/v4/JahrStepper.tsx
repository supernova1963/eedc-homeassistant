/**
 * JahrStepper — schwebende „Player"-Jahresauswahl der Cockpit/Jahr-Sicht (mobil),
 * Pendant zu {@link MonatStepper} / {@link TagStepper}. Desktop behält die
 * {@link JahresRail}, mobil ersetzt dieser sticky Stepper sie:
 *   ⏮ ältestes · ◀ −1 Jahr · [Jahr ▾ → Liste] · ▶ +1 Jahr · ⏭ neuestes
 * (Jahre sind wenige → kein ±N-Sprung, kein Datumsfeld nötig.)
 */
import { useMemo, useState } from 'react'
import type { LucideIcon } from 'lucide-react'
import { ChevronFirst, ChevronLeft, ChevronRight, ChevronLast, ChevronDown } from 'lucide-react'
import type { JahrRailEintrag } from './JahresRail'

interface JahrStepperProps {
  entries: JahrRailEintrag[]
  jahr: number
  onSelect: (jahr: number) => void
}

export function JahrStepper({ entries, jahr, onSelect }: JahrStepperProps) {
  const [offen, setOffen] = useState(false)
  const desc = useMemo(() => [...entries].sort((a, b) => b.jahr - a.jahr), [entries])
  const oldest = useMemo(() => entries.reduce((m, e) => Math.min(m, e.jahr), entries[0]?.jahr ?? jahr), [entries, jahr])
  const newest = useMemo(() => entries.reduce((m, e) => Math.max(m, e.jahr), entries[0]?.jahr ?? jahr), [entries, jahr])

  const ziel = (j: number): number | null => {
    const c = j < oldest ? oldest : j > newest ? newest : j
    return c === jahr ? null : c
  }
  const aktuell = entries.find((e) => e.jahr === jahr) ?? null

  const Btn = ({ ziel: z, icon: Icon, lbl }: { ziel: number | null; icon: LucideIcon; lbl: string }) => (
    <button
      type="button"
      disabled={z == null}
      onClick={() => z != null && onSelect(z)}
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
        <Btn ziel={ziel(oldest)} icon={ChevronFirst} lbl="ältestes Jahr" />
        <Btn ziel={ziel(jahr - 1)} icon={ChevronLeft} lbl="voriges Jahr" />
        <button
          type="button"
          onClick={() => setOffen((o) => !o)}
          aria-expanded={offen}
          className="flex-1 flex items-center justify-center gap-1.5 h-9 min-w-0 rounded-md text-sm font-semibold text-gray-900 dark:text-white hover:bg-gray-100 dark:hover:bg-gray-700/50 transition-colors"
        >
          <span className="truncate">{jahr}</span>
          {aktuell?.laufend && (
            <span className="text-[10px] leading-none px-1 py-0.5 rounded-full bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300">läuft</span>
          )}
          <ChevronDown className={`h-4 w-4 shrink-0 transition-transform ${offen ? 'rotate-180' : ''}`} />
        </button>
        <Btn ziel={ziel(jahr + 1)} icon={ChevronRight} lbl="nächstes Jahr" />
        <Btn ziel={ziel(newest)} icon={ChevronLast} lbl="neuestes Jahr" />
      </div>

      {offen && (
        <div className="mt-1 max-h-72 overflow-y-auto rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 shadow-lg">
          <div className="divide-y divide-gray-100 dark:divide-gray-700/50">
            {desc.map((e) => {
              const sel = e.jahr === jahr
              return (
                <button
                  key={e.jahr}
                  type="button"
                  onClick={() => { onSelect(e.jahr); setOffen(false) }}
                  className={`flex w-full items-center justify-between gap-3 px-3 py-2 text-sm transition-colors ${
                    sel
                      ? 'bg-primary-50 dark:bg-primary-900/30 text-primary-700 dark:text-primary-300 font-semibold'
                      : 'text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700/40'
                  }`}
                >
                  <span>{e.jahr}</span>
                  <span className={`text-xs ${e.laufend ? 'text-emerald-500 dark:text-emerald-400' : 'text-gray-400 dark:text-gray-500 tabular-nums'}`}>
                    {e.laufend ? 'läuft' : `${Math.round(e.pv_kwh)} kWh`}
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
