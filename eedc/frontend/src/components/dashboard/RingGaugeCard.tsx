/**
 * Ring-Gauge Card: Kreisdiagramm-KPI (z.B. Autarkie, Eigenverbrauchsquote)
 */

import { Card, FormelTooltip } from '../../components/ui'

export default function RingGaugeCard({ title, value, subtitle, color, formel, berechnung, ergebnis }: {
  title: string; value: number; subtitle?: string; color: string
  formel?: string; berechnung?: string; ergebnis?: string
}) {
  const r = 32
  const circ = 2 * Math.PI * r
  const filled = Math.min(100, Math.max(0, value)) / 100 * circ

  const gauge = (
    <svg viewBox="0 0 80 80" className="w-12 h-12 sm:w-16 sm:h-16 flex-shrink-0">
      <circle cx="40" cy="40" r={r} fill="none" stroke="currentColor" strokeWidth="8"
        className="text-gray-200 dark:text-gray-700" />
      <circle cx="40" cy="40" r={r} fill="none" stroke={color} strokeWidth="8"
        strokeDasharray={`${filled} ${circ}`}
        strokeLinecap="round"
        transform="rotate(-90 40 40)" />
      <text x="40" y="45" textAnchor="middle" fontSize="15" fontWeight="bold"
        fill={color}>
        {value.toFixed(0)}
      </text>
    </svg>
  )

  return (
    <Card className="p-3">
      <div className="flex items-center gap-3">
        {gauge}
        <div className="min-w-0">
          <p className="text-xs text-gray-500 dark:text-gray-400">{title}</p>
          <p className="text-base sm:text-lg font-bold text-gray-900 dark:text-white whitespace-nowrap">
            {formel
              ? <FormelTooltip formel={formel} berechnung={berechnung} ergebnis={ergebnis}>{value.toFixed(1)} %</FormelTooltip>
              : <>{value.toFixed(1)} %</>
            }
          </p>
          {subtitle && <p className="text-xs text-gray-400 dark:text-gray-500 truncate">{subtitle}</p>}
        </div>
      </div>
    </Card>
  )
}
