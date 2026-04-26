import type { Payload, ValueType, NameType } from 'recharts/types/component/DefaultTooltipContent'

interface ChartTooltipProps {
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
  decimals = 0,
  locale = 'de-DE',
}: ChartTooltipProps) {
  if (!active || !payload?.length) return null

  const displayLabel = labelFormatter ? labelFormatter(label) : label
  const hasLabel = displayLabel != null && displayLabel !== ''
  const sorted = itemSorter
    ? [...payload].sort((a, b) => (itemSorter(a) - itemSorter(b)))
    : payload

  // Single-Entry + Header → kompaktes Layout (kein Name, nur Wert)
  const compact = sorted.length === 1 && hasLabel

  return (
    <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-lg shadow-lg p-3 text-sm">
      {hasLabel && (
        <p className="font-medium text-gray-900 dark:text-white mb-1">{String(displayLabel)}</p>
      )}
      {sorted.map((entry, i) => {
        if (entry.type === 'none') return null
        const val = entry.value as number
        const p = entry.payload as Record<string, unknown> | undefined
        const color: string = entry.color || entry.fill || (typeof p?.fill === 'string' ? p.fill : undefined) || (typeof p?.color === 'string' ? p.color : undefined) || '#888'
        let formatted: string | null
        if (formatter) {
          formatted = formatter(val, entry.name as string)
        } else if (unit !== undefined) {
          formatted = `${val.toLocaleString(locale, { minimumFractionDigits: decimals, maximumFractionDigits: decimals })} ${unit}`
        } else {
          formatted = String(val)
        }
        if (formatted === null) return null
        const displayName = nameFormatter ? nameFormatter(entry.name as string) : entry.name
        return (
          <div key={i} className="flex items-center gap-2">
            <span
              className="w-2.5 h-2.5 rounded-full flex-shrink-0"
              style={{ backgroundColor: color }}
            />
            {!compact && (
              <span className="text-gray-600 dark:text-gray-300">{displayName}:</span>
            )}
            <span className="font-medium" style={{ color }}>{formatted}</span>
          </div>
        )
      })}
    </div>
  )
}
