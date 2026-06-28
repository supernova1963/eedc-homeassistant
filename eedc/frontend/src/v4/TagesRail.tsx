/**
 * TagesRail — Tages-Zeitstrahl der Cockpit/Tag-Sicht (Pendant zu {@link MonatsRail}).
 *
 * Vertikal auf Desktop (links): Monats-Divider + Tagespunkte + Mini-PV-Balken +
 * „heute"-Badge. Nur Desktop (`hidden lg:block`) — mobil übernimmt der schwebende
 * {@link TagStepper}. Struktur/Styling 1:1 zu MonatsRail, nur Granularität = Tag
 * (gruppiert nach Monat statt Jahr).
 */
import { useMemo } from 'react'
import { MONAT_KURZ, DATENROLLE, fmtZahl } from '../lib'

export interface TagRailEintrag {
  datum: string   // YYYY-MM-DD
  pv_kwh: number
  heute?: boolean
}

interface TagesRailProps {
  entries: TagRailEintrag[]
  datum: string
  onSelect: (datum: string) => void
  /** Ältester verfügbarer Tag (jenseits der 90-Tage-Liste) — Untergrenze der
   *  Datumsauswahl, damit ALLE vorhandenen Tage direkt anspringbar sind. */
  aeltesterTag?: string
}

const WT_KURZ = ['So', 'Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa']
const monatKey = (d: string) => d.slice(0, 7)            // YYYY-MM
const wochentag = (d: string) => WT_KURZ[new Date(d + 'T12:00:00').getDay()]
const tagNr = (d: string) => new Date(d + 'T12:00:00').getDate()
const monatLabel = (key: string) => `${MONAT_KURZ[Number(key.slice(5, 7))]} ${key.slice(0, 4)}`

export function TagesRail({ entries, datum, onSelect, aeltesterTag }: TagesRailProps) {
  const byMonat = useMemo(() => {
    const map = new Map<string, TagRailEintrag[]>()
    const sorted = [...entries].sort((a, b) => (a.datum < b.datum ? 1 : -1)) // neueste zuerst
    sorted.forEach((e) => {
      const k = monatKey(e.datum)
      if (!map.has(k)) map.set(k, [])
      map.get(k)!.push(e)
    })
    return map
  }, [entries])

  const maxPvByMonat = useMemo(() => {
    const m = new Map<string, number>()
    byMonat.forEach((es, k) => m.set(k, Math.max(...es.map((e) => e.pv_kwh), 1)))
    return m
  }, [byMonat])

  const monate = useMemo(() => [...byMonat.keys()].sort((a, b) => (a < b ? 1 : -1)), [byMonat])
  const heuteISO = new Date().toISOString().slice(0, 10)
  const aeltesterListe = useMemo(() => entries.reduce((m, e) => (m && m < e.datum ? m : e.datum), entries[0]?.datum ?? ''), [entries])
  // Untergrenze der Datumsauswahl = ältester verfügbarer Tag (kann vor der 90-Tage-
  // Liste liegen → alle Tage erreichbar), Fallback = ältester Listen-Tag.
  const aeltester = aeltesterTag && (!aeltesterListe || aeltesterTag < aeltesterListe) ? aeltesterTag : aeltesterListe
  const titel = (e: TagRailEintrag) =>
    e.heute ? `${wochentag(e.datum)} ${tagNr(e.datum)}. — heute` : `${wochentag(e.datum)} ${tagNr(e.datum)}.: ${fmtZahl(e.pv_kwh, 0)} kWh`

  return (
    <div className="hidden lg:block lg:sticky lg:top-0 lg:max-h-[calc(100vh-8rem)] lg:overflow-y-auto scrollbar-none space-y-3 pr-1">
      {/* Direktsprung (Tage sind viele — anders als Monate). */}
      <input
        type="date" aria-label="Datum wählen" value={datum} max={heuteISO} min={aeltester || undefined}
        onChange={(e) => { if (e.target.value) onSelect(e.target.value) }}
        className="input w-full text-xs"
      />
      {monate.map((mk) => (
        <div key={mk}>
          <div className="flex items-center gap-2 mb-1 px-1">
            <div className="h-px flex-1 bg-gray-200 dark:bg-gray-700" />
            <span className="text-xs font-bold text-gray-400 dark:text-gray-500 uppercase tracking-wider">{monatLabel(mk)}</span>
            <div className="h-px flex-1 bg-gray-200 dark:bg-gray-700" />
          </div>
          <div className="relative ml-3">
            <div className="absolute left-[6px] top-3 bottom-0 w-px bg-gray-200 dark:bg-gray-700" />
            {byMonat.get(mk)!.map((e) => {
              const sel = e.datum === datum
              const maxPv = maxPvByMonat.get(mk) ?? 1
              const barW = Math.max(6, Math.round((e.pv_kwh / maxPv) * 100))
              return (
                <button
                  key={e.datum}
                  type="button"
                  onClick={() => onSelect(e.datum)}
                  title={titel(e)}
                  className={`relative flex items-start gap-2 w-full text-left py-1.5 pr-1 rounded-lg transition-colors group ${
                    sel ? 'text-blue-700 dark:text-blue-300' : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-200'
                  }`}
                >
                  <span className={`relative z-10 mt-1 h-3 w-3 rounded-full border-2 shrink-0 transition-all ${
                    e.heute
                      ? 'bg-emerald-400 border-emerald-500 animate-pulse'
                      : sel
                        ? 'bg-blue-600 border-blue-600 shadow shadow-blue-400/50'
                        : 'bg-white dark:bg-gray-800 border-gray-300 dark:border-gray-600 group-hover:border-blue-400'
                  }`} />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-baseline justify-between gap-1">
                      <span className={`text-sm font-medium ${sel ? 'text-blue-700 dark:text-blue-300' : ''}`}>
                        {wochentag(e.datum)} {tagNr(e.datum)}.
                      </span>
                      <span className={`text-xs tabular-nums ${
                        e.heute ? 'text-emerald-500 dark:text-emerald-400' : sel ? 'text-blue-500 dark:text-blue-400' : 'text-gray-400 dark:text-gray-500'
                      }`}>
                        {e.heute ? 'heute' : `${fmtZahl(e.pv_kwh, 0)} kWh`}
                      </span>
                    </div>
                    {!e.heute && (
                      <svg className="mt-0.5 w-full h-1" aria-hidden="true">
                        <rect width="100%" height="4" rx="1" className="fill-gray-100 dark:fill-gray-700" />
                        <rect width={`${barW}%`} height="4" rx="1" className={sel ? 'fill-blue-500' : DATENROLLE.pv.fill} />
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
  )
}
