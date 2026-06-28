/**
 * JahresRail — Jahres-Zeitstrahl der Cockpit/Jahr-Sicht (Pendant zu {@link MonatsRail}
 * / {@link TagesRail}). Vertikal auf Desktop (links): Jahrespunkte + Mini-PV-Balken
 * + „läuft"-Badge. Nur Desktop (`hidden lg:block`) — mobil übernimmt der schwebende
 * {@link JahrStepper}. Granularität = Jahr (flache Liste, neueste zuerst).
 */
import { useMemo } from 'react'
import { DATENROLLE, fmtZahl } from '../lib'

export interface JahrRailEintrag {
  jahr: number
  pv_kwh: number
  laufend?: boolean
}

interface JahresRailProps {
  entries: JahrRailEintrag[]
  jahr: number
  onSelect: (jahr: number) => void
}

export function JahresRail({ entries, jahr, onSelect }: JahresRailProps) {
  const sorted = useMemo(() => [...entries].sort((a, b) => b.jahr - a.jahr), [entries])
  const maxPv = useMemo(() => Math.max(...entries.map((e) => e.pv_kwh), 1), [entries])

  const titel = (e: JahrRailEintrag) =>
    e.laufend ? `${e.jahr} — läuft` : `${e.jahr}: ${fmtZahl(e.pv_kwh, 0)} kWh`

  return (
    <div className="hidden lg:block lg:sticky lg:top-0 lg:max-h-[calc(100vh-8rem)] lg:overflow-y-auto scrollbar-none pr-1">
      <div className="relative ml-3">
        <div className="absolute left-[6px] top-3 bottom-0 w-px bg-gray-200 dark:bg-gray-700" />
        {sorted.map((e) => {
          const sel = e.jahr === jahr
          const barW = Math.max(6, Math.round((e.pv_kwh / maxPv) * 100))
          return (
            <button
              key={e.jahr}
              type="button"
              onClick={() => onSelect(e.jahr)}
              title={titel(e)}
              className={`relative flex items-start gap-2 w-full text-left py-1.5 pr-1 rounded-lg transition-colors group ${
                sel ? 'text-blue-700 dark:text-blue-300' : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-200'
              }`}
            >
              <span className={`relative z-10 mt-1 h-3 w-3 rounded-full border-2 shrink-0 transition-all ${
                e.laufend
                  ? 'bg-emerald-400 border-emerald-500 animate-pulse'
                  : sel
                    ? 'bg-blue-600 border-blue-600 shadow shadow-blue-400/50'
                    : 'bg-white dark:bg-gray-800 border-gray-300 dark:border-gray-600 group-hover:border-blue-400'
              }`} />
              <div className="flex-1 min-w-0">
                <div className="flex items-baseline justify-between gap-1">
                  <span className={`text-sm font-medium ${sel ? 'text-blue-700 dark:text-blue-300' : ''}`}>{e.jahr}</span>
                  <span className={`text-xs tabular-nums ${
                    e.laufend ? 'text-emerald-500 dark:text-emerald-400' : sel ? 'text-blue-500 dark:text-blue-400' : 'text-gray-400 dark:text-gray-500'
                  }`}>
                    {e.laufend ? 'läuft' : `${fmtZahl(e.pv_kwh, 0)} kWh`}
                  </span>
                </div>
                <svg className="mt-0.5 w-full h-1" aria-hidden="true">
                  <rect width="100%" height="4" rx="1" className="fill-gray-100 dark:fill-gray-700" />
                  <rect width={`${barW}%`} height="4" rx="1" className={sel ? 'fill-blue-500' : DATENROLLE.pv.fill} />
                </svg>
              </div>
            </button>
          )
        })}
      </div>
    </div>
  )
}
