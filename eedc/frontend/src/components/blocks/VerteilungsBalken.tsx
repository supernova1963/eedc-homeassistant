/**
 * VerteilungsBalken — SoT für 2..n-Wege-Aufteilungen (PV EV/Einspeisung, WP
 * Heizung/Warmwasser, Lade-Mix, BKW): Label · proportionaler Balken · Wert + %.
 *
 * Ersetzt den früheren Aufteilungs-Donut (B7-Revision 2026-06-19) UND die
 * Inline-Balken der PV-Verteilung — EINE Bildsprache für alle Aufteilungen
 * (konsistenter + vollständiger als ein Donut: Werte inline statt Legende/Hover).
 *
 * Farben als Tailwind-bg-Klassen (Inline-Hex verboten); der Aufrufer gibt die
 * Rollenfarbe je Segment. Prozent = Anteil an der Segment-Summe; rendert nichts,
 * wenn die Summe 0 ist.
 */
import { fmtCalc } from '../ui'

export interface VerteilungSegment {
  label: string
  wert: number | null | undefined
  /** Tailwind-bg-Klasse, z. B. 'bg-purple-500' (Rollenfarbe, keine Inline-Hex). */
  farbe: string
}

export function VerteilungsBalken({
  segmente,
  einheit = 'kWh',
  titel,
}: {
  segmente: VerteilungSegment[]
  einheit?: string
  titel?: string
}) {
  const werte = segmente.map((s) => Math.max(0, s.wert ?? 0))
  const total = werte.reduce((a, b) => a + b, 0)
  if (total <= 0) return null
  return (
    <div>
      {titel && (
        <p className="text-xs font-semibold text-gray-400 dark:text-gray-500 uppercase tracking-wider mb-2">{titel}</p>
      )}
      <div className="space-y-2.5">
        {segmente.map((s, i) => {
          const pct = Math.round((werte[i] / total) * 100)
          return (
            <div key={s.label} className="flex items-center gap-2 text-xs">
              <span className="w-20 text-gray-600 dark:text-gray-400 shrink-0">{s.label}</span>
              <div className="flex-1 bg-gray-200 dark:bg-gray-700 rounded-full h-2 min-w-[2rem]">
                <div className={`h-2 rounded-full ${s.farbe}`} style={{ width: `${pct}%` }} />
              </div>
              <span className="text-right text-gray-700 dark:text-gray-300 font-medium tabular-nums whitespace-nowrap shrink-0">
                {fmtCalc(werte[i], 0)} {einheit} · {pct} %
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}
