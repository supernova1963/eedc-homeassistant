/**
 * Sparkline Chart: PV-Monatserträge als Balkendiagramm
 */

import { BarChart, Bar, ResponsiveContainer, Tooltip, Cell } from 'recharts'
import { ChartTooltip } from '../../components/ui'
import { MONAT_KURZ } from '../../lib'
import type { AggregierteMonatsdaten } from '../../api/monatsdaten'

export default function SparklineChart({ monatsdaten, selectedYear }: {
  monatsdaten: AggregierteMonatsdaten[]
  selectedYear?: number
}) {
  if (monatsdaten.length < 2) return null

  const sorted = [...monatsdaten].sort((a, b) =>
    a.jahr !== b.jahr ? a.jahr - b.jahr : a.monat - b.monat
  )
  const filtered = selectedYear
    ? sorted.filter(m => m.jahr === selectedYear)
    : sorted

  if (filtered.length < 2) return null

  const firstJahr = filtered[0].jahr
  const chartData = filtered.map(m => ({
    name: m.jahr !== firstJahr
      ? `${MONAT_KURZ[m.monat]} ${m.jahr}`
      : MONAT_KURZ[m.monat],
    kwh: Math.round(m.pv_erzeugung_kwh),
  }))
  const max = Math.max(...chartData.map(d => d.kwh))

  return (
    <div className="mt-4">
      <p className="text-xs text-gray-400 dark:text-gray-500 mb-2">
        PV-Monatserträge — {selectedYear ?? `${filtered[0].jahr}–${filtered[filtered.length - 1].jahr}`}
      </p>
      <div className="h-20">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={chartData} margin={{ top: 0, right: 0, bottom: 0, left: 0 }}>
            <Tooltip content={<ChartTooltip unit="kWh" />} />
            <Bar dataKey="kwh" name="PV-Ertrag" radius={[2, 2, 0, 0]}>
              {chartData.map((entry, i) => (
                <Cell
                  key={i}
                  fill={
                    entry.kwh >= max * 0.8 ? '#f59e0b'
                      : entry.kwh >= max * 0.5 ? '#fbbf24'
                        : '#fde68a'
                  }
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      <div className="flex justify-between text-xs text-gray-400 mt-0.5">
        <span>{chartData[0]?.name}</span>
        <span>{chartData[chartData.length - 1]?.name}</span>
      </div>
    </div>
  )
}
