/**
 * ChartLegende — SoT-Renderer für ALLE Recharts-Legenden (S1, Triage 2026-06-24).
 *
 * Eine app-weite Bildsprache, identisch zum {@link ChartTooltip}: Farbzuordnung
 * NUR über ein Farb-**Viereck** (Swatch), Text **monochrom** — keine farbige
 * Schrift, keine Kreise (detLAN/Rainer: „farbige Legenden-Schrift wirkt unseriös").
 *
 * Recharts färbt die Default-Legenden-Schrift per Inline-`color` ein (eine
 * Tailwind-Textklasse überschriebe das nicht, Inline-Hex ist verboten) — daher
 * ein vollständiger `content`-Renderer statt eines bloßen `formatter`. Einsatz:
 *
 *   <Legend content={<ChartLegende />} />
 *   <Legend content={<ChartLegende formatter={(v) => LABELS[v] ?? v} />} />
 *   <Legend content={<ChartLegende onItemClick={(e) => toggle(e.dataKey)} />} />  // Serie an/aus
 *
 * Recharts injiziert `payload` (+ Layout-Props) via `cloneElement`; die hier
 * gesetzten `formatter`/`onItemClick` bleiben erhalten. Inaktive Serien
 * (`hide` am Series-Element → `entry.inactive`) werden gedimmt.
 */
import type { ReactNode } from 'react'
import { CHART_LABELS } from '../../lib'

export interface LegendEintrag {
  value: string
  color?: string
  dataKey?: string | number
  inactive?: boolean
  type?: string
  payload?: unknown
}

interface ChartLegendeProps {
  /** Von Recharts injiziert. */
  payload?: LegendEintrag[]
  /** Anzeigetext je Eintrag (z. B. dataKey → Label). Default: `entry.value`. */
  formatter?: (value: string, entry: LegendEintrag) => ReactNode
  /** Klick auf einen Eintrag (z. B. Serie an/aus). Macht die Einträge klickbar. */
  onItemClick?: (entry: LegendEintrag) => void
}

export default function ChartLegende({ payload, formatter, onItemClick }: ChartLegendeProps) {
  if (!payload?.length) return null
  const items = payload.filter((e) => e.type !== 'none')
  if (!items.length) return null
  const klickbar = !!onItemClick

  return (
    <ul className="flex flex-wrap justify-center items-center gap-x-4 gap-y-1 m-0 p-0 list-none text-xs">
      {items.map((entry, i) => {
        // Default-`formatter` aus dem zentralen Label-Kanon (Regel D) → Legende ≡ Tooltip.
        const text = formatter ? formatter(entry.value, entry) : (CHART_LABELS[entry.value] ?? entry.value)
        if (text == null || text === '') return null
        return (
          <li
            key={`${entry.dataKey ?? entry.value}-${i}`}
            {...(klickbar
              ? { role: 'button', tabIndex: 0, onClick: () => onItemClick!(entry),
                  onKeyDown: (e: React.KeyboardEvent) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onItemClick!(entry) } } }
              : {})}
            className={`inline-flex items-center gap-1.5 ${klickbar ? 'cursor-pointer select-none' : ''} ${entry.inactive ? 'opacity-40' : ''}`}
          >
            {/* S1: Farbe NUR als Viereck-Swatch (dynamische Serienfarbe, kein Inline-Hex-Literal). */}
            <span className="w-2.5 h-2.5 rounded-sm shrink-0" style={{ backgroundColor: entry.color }} />
            <span className="text-gray-600 dark:text-gray-300">{text}</span>
          </li>
        )
      })}
    </ul>
  )
}
