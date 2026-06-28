import type { Payload, ValueType, NameType } from 'recharts/types/component/DefaultTooltipContent'
import { CHART_LABELS, SERIE_NEUTRAL, fmtZahl } from '../../lib'

export interface ChartTooltipProps {
  active?: boolean
  payload?: Payload<ValueType, NameType>[]
  label?: unknown
  formatter?: (value: number, name: string) => string | null
  labelFormatter?: (label: unknown) => string
  nameFormatter?: (name: string) => string
  itemSorter?: (item: Payload<ValueType, NameType>) => number
  unit?: string
  decimals?: number
  locale?: string
  /** Regel F (2026-06-25): dataKey im Payload, der das 100-%-Total trägt → je
   *  Zeile zusätzlich „(xx %)" (Anteil). Ersetzt die hellen Custom-%-Tooltips. */
  percentOf?: string
}

export default function ChartTooltip({
  active,
  payload,
  label,
  formatter,
  labelFormatter,
  nameFormatter,
  itemSorter,
  unit,
  decimals,
  locale = 'de-DE',
  percentOf,
}: ChartTooltipProps) {
  if (!active || !payload?.length) return null

  const displayLabel = labelFormatter ? labelFormatter(label) : label
  const hasLabel = displayLabel != null && displayLabel !== ''
  const sorted = itemSorter
    ? [...payload].sort((a, b) => (itemSorter(a) - itemSorter(b)))
    : payload

  // Default-`nameFormatter` aus dem zentralen Label-Kanon (Regel D) → nie Roh-Keys;
  // Tooltip-Label ≡ Legende-Label. Expliziter Formatter übersteuert.
  const resolveName = nameFormatter ?? ((n: string) => CHART_LABELS[n] ?? n)

  // Anteils-Modus (Regel F): Total vom ersten Payload-Punkt lesen.
  const ganz = percentOf
    ? Number((sorted[0]?.payload as Record<string, unknown> | undefined)?.[percentOf])
    : undefined

  // Single-Entry + Header → kompaktes Layout (kein Name, nur Wert)
  const compact = sorted.length === 1 && hasLabel

  return (
    // Tooltip-Kanon (P3): dunkel in beiden Modi, rounded-lg, text-sm (= FormelTooltip-Linie).
    <div className="bg-gray-900 dark:bg-gray-950 border border-gray-700 rounded-lg shadow-lg p-3 text-sm">
      {hasLabel && (
        <p className="font-medium text-white mb-1">{String(displayLabel)}</p>
      )}
      {sorted.map((entry, i) => {
        if (entry.type === 'none') return null
        const val = entry.value as number
        const p = entry.payload as Record<string, unknown> | undefined
        const color: string = entry.color || entry.fill || (typeof p?.fill === 'string' ? p.fill : undefined) || (typeof p?.color === 'string' ? p.color : undefined) || SERIE_NEUTRAL
        let formatted: string | null
        const isNum = typeof val === 'number' && Number.isFinite(val)
        if (formatter) {
          formatted = formatter(val, entry.name as string)
        } else if (isNum) {
          // #228: decimals werden konsistent angewandt — auch ohne unit.
          // Vorher fiel der Fall „decimals ohne unit" auf String(val) durch
          // und zeigte Roh-Floats wie 10.5252891704708 statt 10,5.
          const opts = decimals !== undefined
            ? { minimumFractionDigits: decimals, maximumFractionDigits: decimals }
            : undefined
          const num = val.toLocaleString(locale, opts)
          formatted = unit !== undefined ? `${num} ${unit}` : num
        } else {
          formatted = String(val)
        }
        if (formatted === null) return null
        const displayName = resolveName(entry.name as string)
        const anteil = ganz !== undefined && Number.isFinite(ganz) && ganz > 0 && isNum
          ? `${fmtZahl((val / ganz) * 100, 0)} %`
          : undefined
        return (
          <div key={i} className="flex items-center gap-2">
            {/* S1: Farbzuordnung NUR über das Viereck-Swatch — Text bleibt
                monochrom (Seriosität, app-weit einheitlich mit der Legende). */}
            <span
              className="w-2.5 h-2.5 rounded-sm flex-shrink-0"
              style={{ backgroundColor: color }}
            />
            {!compact && (
              <span className="text-gray-300">{displayName}:</span>
            )}
            <span className="font-medium text-white">{formatted}</span>
            {anteil && <span className="text-gray-400">({anteil})</span>}
          </div>
        )
      })}
    </div>
  )
}
