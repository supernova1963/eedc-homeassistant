/**
 * MonatsRail — Monats-Zeitstrahl der Cockpit/Monat-Sicht (IA v4 E3 Slice 2e, B2).
 *
 * Vertikal auf Desktop (links, Jahres-Divider + Monatspunkte + Mini-PV-Balken +
 * „läuft"-Badge), horizontal scrollbar auf Mobile. Ersetzt den interimistischen
 * Dropdown-Selektor. Verhaltensgleich zum Donor `MonatsabschlussView`
 * (`VerticalTimeline`), aber als eigenständige, responsive /v4-Komponente.
 */
import { useEffect, useMemo, useRef } from 'react'
import { MONAT_KURZ } from '../lib'

export interface RailEintrag {
  jahr: number
  monat: number
  pv_kwh: number
  laufend?: boolean
}

interface MonatsRailProps {
  entries: RailEintrag[]
  jahr: number
  monat: number
  onSelect: (jahr: number, monat: number) => void
}

export function MonatsRail({ entries, jahr, monat, onSelect }: MonatsRailProps) {
  const byJahr = useMemo(() => {
    const map = new Map<number, RailEintrag[]>()
    const sorted = [...entries].sort((a, b) => (b.jahr !== a.jahr ? b.jahr - a.jahr : b.monat - a.monat))
    sorted.forEach((e) => {
      if (!map.has(e.jahr)) map.set(e.jahr, [])
      map.get(e.jahr)!.push(e)
    })
    return map
  }, [entries])

  const maxPvByJahr = useMemo(() => {
    const m = new Map<number, number>()
    byJahr.forEach((es, j) => m.set(j, Math.max(...es.map((e) => e.pv_kwh), 1)))
    return m
  }, [byJahr])

  const jahre = useMemo(() => [...byJahr.keys()].sort((a, b) => b - a), [byJahr])
  const istSel = (e: RailEintrag) => e.jahr === jahr && e.monat === monat
  const titel = (e: RailEintrag) =>
    e.laufend ? `${MONAT_KURZ[e.monat]} ${e.jahr} — laufender Monat` : `${MONAT_KURZ[e.monat]} ${e.jahr}: ${Math.round(e.pv_kwh)} kWh`

  // ── Mobile: horizontale Chip-Leiste ──────────────────────────────────────
  // Absteigend (neueste zuerst) wie der Desktop-Zweig — generelle Datums-Listen-
  // Regel (CLAUDE.md). Das scrollIntoView zentriert die Auswahl ohnehin.
  const mobilSorted = useMemo(
    () => [...entries].sort((a, b) => (b.jahr !== a.jahr ? b.jahr - a.jahr : b.monat - a.monat)),
    [entries],
  )
  const selChipRef = useRef<HTMLButtonElement>(null)
  useEffect(() => {
    selChipRef.current?.scrollIntoView({ block: 'nearest', inline: 'center', behavior: 'smooth' })
  }, [jahr, monat])

  return (
    <>
      {/* Mobile (horizontal) */}
      <div className="lg:hidden -mx-3 px-3 overflow-x-auto scrollbar-none">
        <div className="flex gap-1.5 w-max pb-1">
          {mobilSorted.map((e) => {
            const sel = istSel(e)
            return (
              <button
                key={`${e.jahr}-${e.monat}`}
                ref={sel ? selChipRef : null}
                type="button"
                onClick={() => onSelect(e.jahr, e.monat)}
                title={titel(e)}
                className={`min-h-[44px] flex flex-col items-center justify-center px-3 rounded-lg border text-xs font-medium whitespace-nowrap transition-colors ${
                  sel
                    ? 'border-primary-400 bg-primary-50 text-primary-700 dark:border-primary-500 dark:bg-primary-900/30 dark:text-primary-300'
                    : 'border-gray-200 dark:border-gray-700 text-gray-600 dark:text-gray-400'
                }`}
              >
                <span>{MONAT_KURZ[e.monat]} ’{String(e.jahr).slice(-2)}</span>
                <span className={e.laufend ? 'text-emerald-500 dark:text-emerald-400' : 'text-gray-400 dark:text-gray-500'}>
                  {e.laufend ? 'läuft' : `${Math.round(e.pv_kwh)} kWh`}
                </span>
              </button>
            )
          })}
        </div>
      </div>

      {/* Desktop (vertikal) */}
      <div className="hidden lg:block lg:sticky lg:top-0 lg:max-h-[calc(100vh-8rem)] lg:overflow-y-auto scrollbar-none space-y-3 pr-1">
        {jahre.map((j) => (
          <div key={j}>
            <div className="flex items-center gap-2 mb-1 px-1">
              <div className="h-px flex-1 bg-gray-200 dark:bg-gray-700" />
              <span className="text-xs font-bold text-gray-400 dark:text-gray-500 uppercase tracking-wider">{j}</span>
              <div className="h-px flex-1 bg-gray-200 dark:bg-gray-700" />
            </div>
            <div className="relative ml-3">
              <div className="absolute left-[6px] top-3 bottom-0 w-px bg-gray-200 dark:bg-gray-700" />
              {byJahr.get(j)!.map((e) => {
                const sel = istSel(e)
                const maxPv = maxPvByJahr.get(j) ?? 1
                const barW = Math.max(6, Math.round((e.pv_kwh / maxPv) * 100))
                return (
                  <button
                    key={e.monat}
                    type="button"
                    onClick={() => onSelect(e.jahr, e.monat)}
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
                        <span className={`text-sm font-medium ${sel ? 'text-blue-700 dark:text-blue-300' : ''}`}>{MONAT_KURZ[e.monat]}</span>
                        <span className={`text-xs tabular-nums ${
                          e.laufend ? 'text-emerald-500 dark:text-emerald-400' : sel ? 'text-blue-500 dark:text-blue-400' : 'text-gray-400 dark:text-gray-500'
                        }`}>
                          {e.laufend ? 'läuft' : `${Math.round(e.pv_kwh)} kWh`}
                        </span>
                      </div>
                      {!e.laufend && (
                        <svg className="mt-0.5 w-full h-1" aria-hidden="true">
                          <rect width="100%" height="4" rx="2" className="fill-gray-100 dark:fill-gray-700" />
                          <rect width={`${barW}%`} height="4" rx="2" className={sel ? 'fill-blue-500' : 'fill-yellow-400 dark:fill-yellow-500'} />
                        </svg>
                      )}
                    </div>
                  </button>
                )
              })}
            </div>
          </div>
        ))}
      </div>
    </>
  )
}
