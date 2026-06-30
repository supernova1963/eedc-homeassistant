/**
 * MonatPicker — Custom-Monatsauswahl (D12-7, detLAN R12).
 *
 * Ersetzt das native `<input type="month">`, das auf dem Desktop nur das
 * technische `YYYY-MM` zeigt (mobil rendert es „Januar 2026"). Dieser Picker
 * zeigt **app-weit** das ausgeschriebene Format „Januar 2026" + ein
 * touch-freundliches Monatsraster mit Jahres-Navigation und respektiert
 * `min`/`max` (Werte außerhalb sind deaktiviert — kein „1822", D12-8).
 *
 * Wert-Format = `YYYY-MM` (wie `type=month`), damit der Picker drop-in für die
 * bestehende von/bis-Logik bleibt.
 */
import { useEffect, useRef, useState } from 'react'
import { Calendar, ChevronLeft, ChevronRight } from 'lucide-react'

const MONAT_LANG = ['Januar', 'Februar', 'März', 'April', 'Mai', 'Juni', 'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember']
const MONAT_KURZ = ['Jan', 'Feb', 'Mär', 'Apr', 'Mai', 'Jun', 'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Dez']

function parse(v: string): { jahr: number; monat: number } | null {
  const m = /^(\d{4})-(\d{2})$/.exec(v || '')
  return m ? { jahr: Number(m[1]), monat: Number(m[2]) } : null
}
const toVal = (jahr: number, monat: number) => `${jahr}-${String(monat).padStart(2, '0')}`

export function MonatPicker({ value, onChange, min, max, ariaLabel, className = '' }: {
  /** `YYYY-MM`. */
  value: string
  onChange: (v: string) => void
  /** Untergrenze `YYYY-MM` (inkl.). Monate davor sind deaktiviert. */
  min?: string
  /** Obergrenze `YYYY-MM` (inkl.). Monate danach sind deaktiviert. */
  max?: string
  ariaLabel?: string
  /** Zusätzliche Klassen für den Trigger (Breite/Höhe). */
  className?: string
}) {
  const [offen, setOffen] = useState(false)
  const cur = parse(value)
  const [navJahr, setNavJahr] = useState(cur?.jahr ?? new Date().getFullYear())
  const wrapRef = useRef<HTMLDivElement>(null)

  // Beim Öffnen auf das gewählte Jahr springen.
  useEffect(() => { if (offen && cur) setNavJahr(cur.jahr) }, [offen]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!offen) return
    const onDoc = (e: MouseEvent) => { if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) setOffen(false) }
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOffen(false) }
    document.addEventListener('mousedown', onDoc)
    document.addEventListener('keydown', onKey)
    return () => { document.removeEventListener('mousedown', onDoc); document.removeEventListener('keydown', onKey) }
  }, [offen])

  const minP = min ? parse(min) : null
  const maxP = max ? parse(max) : null
  const istAus = (jahr: number, monat: number) => {
    const v = toVal(jahr, monat)
    return (min != null && v < min) || (max != null && v > max)
  }
  const minJahr = minP?.jahr ?? navJahr - 30
  const maxJahr = maxP?.jahr ?? navJahr + 5
  const label = cur ? `${MONAT_LANG[cur.monat - 1]} ${cur.jahr}` : 'Monat wählen'

  return (
    <div ref={wrapRef} className="relative">
      <button
        type="button" onClick={() => setOffen((o) => !o)}
        aria-label={ariaLabel} aria-haspopup="dialog" aria-expanded={offen}
        className={`inline-flex items-center justify-between gap-2 px-3 rounded-lg border bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-700 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent ${className}`}
      >
        <span className="truncate">{label}</span>
        <Calendar className="h-4 w-4 shrink-0 text-gray-400 dark:text-gray-500" />
      </button>

      {offen && (
        <div className="absolute left-0 top-full mt-1 z-30 w-64 rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 shadow-lg p-2">
          <div className="flex items-center justify-between mb-2">
            <button
              type="button" aria-label="Jahr zurück" disabled={navJahr <= minJahr}
              onClick={() => setNavJahr((j) => j - 1)}
              className="p-1 rounded text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 disabled:opacity-30 disabled:hover:bg-transparent"
            ><ChevronLeft className="h-4 w-4" /></button>
            <span className="text-sm font-semibold text-gray-900 dark:text-white tabular-nums">{navJahr}</span>
            <button
              type="button" aria-label="Jahr vor" disabled={navJahr >= maxJahr}
              onClick={() => setNavJahr((j) => j + 1)}
              className="p-1 rounded text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 disabled:opacity-30 disabled:hover:bg-transparent"
            ><ChevronRight className="h-4 w-4" /></button>
          </div>
          <div className="grid grid-cols-3 gap-1">
            {MONAT_KURZ.map((m, i) => {
              const monat = i + 1
              const aus = istAus(navJahr, monat)
              const gewaehlt = cur?.jahr === navJahr && cur?.monat === monat
              return (
                <button
                  key={m} type="button" disabled={aus}
                  onClick={() => { onChange(toVal(navJahr, monat)); setOffen(false) }}
                  className={`px-2 py-1.5 text-xs rounded transition-colors ${
                    gewaehlt
                      ? 'bg-primary-600 text-white'
                      : aus
                        ? 'text-gray-300 dark:text-gray-600 cursor-not-allowed'
                        : 'text-gray-700 dark:text-gray-300 hover:bg-primary-50 dark:hover:bg-primary-900/30'
                  }`}
                >{m}</button>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}

export default MonatPicker
