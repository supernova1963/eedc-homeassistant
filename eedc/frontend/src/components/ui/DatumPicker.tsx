/**
 * DatumPicker — der EINE Custom-Datums-/Monatspicker (SoT, D13-4/9/11/12).
 *
 * Löst den app-weiten Picker-Zwiespalt, den detLAN meldete (#105/#106/#107):
 * bis dato standen ein helles Custom-Monatsraster (D12-7) UND native
 * `<input type=date/month>` (dunkler OS-Kalender, anderes Icon) nebeneinander.
 * Diese Komponente ersetzt BEIDE — ein Trigger-Stil, ein lucide-Icon, ein helles
 * Popover, ausgeschriebenes Format app-weit; `modus` schaltet zwischen:
 *   • `modus='monat'` → 3×4-Monatsraster, Wert `YYYY-MM`   („Januar 2026")
 *   • `modus='tag'`   → Tages-Kalender (Wochenraster),  Wert `YYYY-MM-DD` („23. Juni 2026")
 *
 * D13-11 (Popover im Leer-Zustand abgeschnitten): das Popover hängt per
 * `createPortal` an `document.body` und positioniert sich `fixed` am Trigger
 * (analog {@link FokusVollbild}) → kein `overflow-hidden`-Ancestor kann es mehr
 * clippen. D13-9 (mobile Felder zu groß): der Trigger ist ein normaler Button
 * fester Höhe + Touch-Raster statt eines großen nativen Feldes.
 *
 * Wert-Format bleibt `YYYY-MM`(-`DD`) wie die nativen Inputs → drop-in für die
 * bestehende von/bis-Logik. `min`/`max` (inkl.) klemmen die Auswahl (D12-8).
 */
import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { Calendar, ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight } from 'lucide-react'

const MONAT_LANG = ['Januar', 'Februar', 'März', 'April', 'Mai', 'Juni', 'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember']
const MONAT_KURZ = ['Jan', 'Feb', 'Mär', 'Apr', 'Mai', 'Jun', 'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Dez']
const WT_KURZ = ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So']

const pad = (n: number) => String(n).padStart(2, '0')
const monatVal = (jahr: number, monat: number) => `${jahr}-${pad(monat)}`
const tagVal = (jahr: number, monat: number, tag: number) => `${jahr}-${pad(monat)}-${pad(tag)}`

interface Parsed { jahr: number; monat: number; tag?: number }
function parse(v: string): Parsed | null {
  const dm = /^(\d{4})-(\d{2})-(\d{2})$/.exec(v || '')
  if (dm) return { jahr: Number(dm[1]), monat: Number(dm[2]), tag: Number(dm[3]) }
  const m = /^(\d{4})-(\d{2})$/.exec(v || '')
  if (m) return { jahr: Number(m[1]), monat: Number(m[2]) }
  return null
}

function triggerLabel(modus: 'monat' | 'tag', cur: Parsed | null): string {
  if (!cur) return modus === 'tag' ? 'Tag wählen' : 'Monat wählen'
  if (modus === 'tag' && cur.tag != null) {
    return new Date(`${tagVal(cur.jahr, cur.monat, cur.tag)}T12:00:00`)
      .toLocaleDateString('de-DE', { day: 'numeric', month: 'long', year: 'numeric' })
  }
  return `${MONAT_LANG[cur.monat - 1]} ${cur.jahr}`
}

export function DatumPicker({ modus, value, onChange, min, max, ariaLabel, className = '' }: {
  modus: 'monat' | 'tag'
  /** `YYYY-MM` (monat) bzw. `YYYY-MM-DD` (tag). */
  value: string
  onChange: (v: string) => void
  /** Untergrenze (inkl.), gleiches Format wie `value`. Werte davor sind deaktiviert. */
  min?: string
  /** Obergrenze (inkl.), gleiches Format wie `value`. Werte danach sind deaktiviert. */
  max?: string
  ariaLabel?: string
  /** Zusätzliche Klassen für den Trigger (Breite/Höhe). */
  className?: string
}) {
  const [offen, setOffen] = useState(false)
  const cur = parse(value)
  const heute = new Date()
  const [navJahr, setNavJahr] = useState(cur?.jahr ?? heute.getFullYear())
  const [navMonat, setNavMonat] = useState(cur?.monat ?? heute.getMonth() + 1)
  const wrapRef = useRef<HTMLDivElement>(null)
  const popRef = useRef<HTMLDivElement>(null)
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null)

  // Beim Öffnen auf das gewählte Datum springen.
  useEffect(() => {
    if (offen && cur) { setNavJahr(cur.jahr); setNavMonat(cur.monat) }
  }, [offen]) // eslint-disable-line react-hooks/exhaustive-deps

  // D13-11: Popover per Portal `fixed` am Trigger positionieren (kein Clip durch
  // overflow-hidden-Ancestor). Nach unten, sonst nach oben; horizontal in den
  // Viewport geklemmt. Re-Messung bei Scroll/Resize.
  const platziere = () => {
    const anker = wrapRef.current
    if (!anker) return
    const r = anker.getBoundingClientRect()
    const ph = popRef.current?.offsetHeight ?? 300
    const pw = popRef.current?.offsetWidth ?? 256
    let top = r.bottom + 4
    if (top + ph > window.innerHeight - 8 && r.top - ph - 4 > 8) top = r.top - ph - 4
    let left = r.left
    if (left + pw > window.innerWidth - 8) left = window.innerWidth - pw - 8
    if (left < 8) left = 8
    setPos({ top, left })
  }
  useLayoutEffect(() => { if (offen) platziere() }, [offen, navJahr, navMonat]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!offen) { setPos(null); return }
    const onDoc = (e: MouseEvent) => {
      const t = e.target as Node
      if (wrapRef.current?.contains(t) || popRef.current?.contains(t)) return
      setOffen(false)
    }
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOffen(false) }
    const onMove = () => platziere()
    document.addEventListener('mousedown', onDoc)
    document.addEventListener('keydown', onKey)
    window.addEventListener('resize', onMove)
    window.addEventListener('scroll', onMove, true)
    return () => {
      document.removeEventListener('mousedown', onDoc)
      document.removeEventListener('keydown', onKey)
      window.removeEventListener('resize', onMove)
      window.removeEventListener('scroll', onMove, true)
    }
  }, [offen]) // eslint-disable-line react-hooks/exhaustive-deps

  const istAusMonat = (jahr: number, monat: number) => {
    const v = monatVal(jahr, monat)
    return (min != null && v < min) || (max != null && v > max)
  }
  const istAusTag = (iso: string) => (min != null && iso < min) || (max != null && iso > max)

  const waehle = (v: string) => { onChange(v); setOffen(false) }

  // ── Monatsraster ──────────────────────────────────────────────────────────
  const minP = min ? parse(min) : null
  const maxP = max ? parse(max) : null
  const minJahr = minP?.jahr ?? navJahr - 30
  const maxJahr = maxP?.jahr ?? navJahr + 5

  // ── Tages-Kalender ────────────────────────────────────────────────────────
  // Montag-first-Index (JS getDay(): 0=So…6=Sa → (d+6)%7).
  const ersterWt = (new Date(navJahr, navMonat - 1, 1).getDay() + 6) % 7
  const tageImMonat = new Date(navJahr, navMonat, 0).getDate()
  const heuteISO = `${heute.getFullYear()}-${pad(heute.getMonth() + 1)}-${pad(heute.getDate())}`
  const letzterTagVorMonat = tagVal(
    navMonat === 1 ? navJahr - 1 : navJahr,
    navMonat === 1 ? 12 : navMonat - 1,
    new Date(navJahr, navMonat - 1, 0).getDate(),
  )
  const ersterTagNachMonat = tagVal(navMonat === 12 ? navJahr + 1 : navJahr, navMonat === 12 ? 1 : navMonat + 1, 1)
  const monatZurueckAus = min != null && letzterTagVorMonat < min
  const monatVorAus = max != null && ersterTagNachMonat > max
  const jahrZurueckAus = min != null && `${navJahr - 1}-12-31` < min
  const jahrVorAus = max != null && `${navJahr + 1}-01-01` > max
  const geheMonat = (delta: number) => {
    let j = navJahr, m = navMonat + delta
    while (m < 1) { m += 12; j-- }
    while (m > 12) { m -= 12; j++ }
    setNavJahr(j); setNavMonat(m)
  }

  const label = triggerLabel(modus, cur)

  const popover = (
    <div
      ref={popRef}
      role="dialog"
      style={pos ? { position: 'fixed', top: pos.top, left: pos.left } : { position: 'fixed', top: 0, left: 0 }}
      className={`z-[60] w-64 rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 shadow-lg p-2 ${pos ? '' : 'opacity-0 pointer-events-none'}`}
    >
      {modus === 'monat' ? (
        <>
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
            {MONAT_KURZ.map((mk, i) => {
              const monat = i + 1
              const aus = istAusMonat(navJahr, monat)
              const gewaehlt = cur?.jahr === navJahr && cur?.monat === monat
              return (
                <button
                  key={mk} type="button" disabled={aus}
                  onClick={() => waehle(monatVal(navJahr, monat))}
                  className={`px-2 py-1.5 text-xs rounded transition-colors ${
                    gewaehlt
                      ? 'bg-primary-600 text-white'
                      : aus
                        ? 'text-gray-300 dark:text-gray-600 cursor-not-allowed'
                        : 'text-gray-700 dark:text-gray-300 hover:bg-primary-50 dark:hover:bg-primary-900/30'
                  }`}
                >{mk}</button>
              )
            })}
          </div>
        </>
      ) : (
        <>
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center">
              <button
                type="button" aria-label="Jahr zurück" disabled={jahrZurueckAus}
                onClick={() => geheMonat(-12)}
                className="p-1 rounded text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 disabled:opacity-30 disabled:hover:bg-transparent"
              ><ChevronsLeft className="h-4 w-4" /></button>
              <button
                type="button" aria-label="Monat zurück" disabled={monatZurueckAus}
                onClick={() => geheMonat(-1)}
                className="p-1 rounded text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 disabled:opacity-30 disabled:hover:bg-transparent"
              ><ChevronLeft className="h-4 w-4" /></button>
            </div>
            <span className="text-sm font-semibold text-gray-900 dark:text-white">{MONAT_LANG[navMonat - 1]} {navJahr}</span>
            <div className="flex items-center">
              <button
                type="button" aria-label="Monat vor" disabled={monatVorAus}
                onClick={() => geheMonat(1)}
                className="p-1 rounded text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 disabled:opacity-30 disabled:hover:bg-transparent"
              ><ChevronRight className="h-4 w-4" /></button>
              <button
                type="button" aria-label="Jahr vor" disabled={jahrVorAus}
                onClick={() => geheMonat(12)}
                className="p-1 rounded text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 disabled:opacity-30 disabled:hover:bg-transparent"
              ><ChevronsRight className="h-4 w-4" /></button>
            </div>
          </div>
          <div className="grid grid-cols-7 gap-0.5 mb-1">
            {WT_KURZ.map((wt) => (
              <span key={wt} className="text-center text-[10px] font-medium text-gray-400 dark:text-gray-500">{wt}</span>
            ))}
          </div>
          <div className="grid grid-cols-7 gap-0.5">
            {Array.from({ length: ersterWt }).map((_, i) => <span key={`b${i}`} />)}
            {Array.from({ length: tageImMonat }).map((_, i) => {
              const tag = i + 1
              const iso = tagVal(navJahr, navMonat, tag)
              const aus = istAusTag(iso)
              const gewaehlt = cur?.jahr === navJahr && cur?.monat === navMonat && cur?.tag === tag
              const istHeute = iso === heuteISO
              return (
                <button
                  key={tag} type="button" disabled={aus}
                  onClick={() => waehle(iso)}
                  className={`h-7 text-xs rounded transition-colors tabular-nums ${
                    gewaehlt
                      ? 'bg-primary-600 text-white'
                      : aus
                        ? 'text-gray-300 dark:text-gray-600 cursor-not-allowed'
                        : `text-gray-700 dark:text-gray-300 hover:bg-primary-50 dark:hover:bg-primary-900/30 ${istHeute ? 'ring-1 ring-inset ring-primary-400 dark:ring-primary-500' : ''}`
                  }`}
                >{tag}</button>
              )
            })}
          </div>
        </>
      )}
    </div>
  )

  return (
    <div ref={wrapRef} className="relative inline-flex">
      <button
        type="button" onClick={() => setOffen((o) => !o)}
        aria-label={ariaLabel} aria-haspopup="dialog" aria-expanded={offen}
        className={`inline-flex items-center justify-between gap-2 px-3 py-1.5 rounded-lg border bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-700 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-inset focus:ring-primary-500 ${className}`}
      >
        <span className="truncate">{label}</span>
        <Calendar className="h-4 w-4 shrink-0 text-gray-400 dark:text-gray-500" />
      </button>
      {offen && typeof document !== 'undefined' && createPortal(popover, document.body)}
    </div>
  )
}

/**
 * MonatPicker — Rückwärtskompatibler Alias (Monats-Modus des {@link DatumPicker}).
 * Bestandscode importiert weiterhin `MonatPicker`; neue Sites nutzen direkt
 * `<DatumPicker modus="monat|tag">`.
 */
export function MonatPicker(props: Omit<Parameters<typeof DatumPicker>[0], 'modus'>) {
  return <DatumPicker modus="monat" {...props} />
}

export default DatumPicker
