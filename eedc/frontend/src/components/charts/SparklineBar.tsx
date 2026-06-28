/**
 * Kompakter Mini-Balkenchart für KPI-Cards und Dashboard-Widgets.
 *
 * Extrahiert aus Dashboard.tsx. Zeigt eine Zeile kleiner Balken
 * mit 3-Stufen-Farbgradient (niedrig → mittel → hoch).
 */

import { BarChart, Bar, Cell, XAxis, Tooltip, ResponsiveContainer } from 'recharts'
import { eedcTooltipProps } from '../ui'
import { SOLAR_INTENSITAET } from '../../lib'

interface SparklineBarProps {
  /** Chart-Daten mit `name` (Label) und einem numerischen Wert. */
  data: Array<{ name: string; value: number }>
  /** Farben für niedrig/mittel/hoch (Default: Amber-Skala). */
  colors?: [string, string, string]
  /** Einheit für Tooltip (Default: "kWh"). */
  unit?: string
  /** Höhe in Pixel (Default: 80). */
  height?: number
}

export default function SparklineBar({
  data,
  colors = SOLAR_INTENSITAET as [string, string, string],
  unit = 'kWh',
  height = 80,
}: SparklineBarProps) {
  if (data.length < 2) return null

  const max = Math.max(...data.map(d => d.value))

  return (
    <div>
      <div style={{ height }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 0, right: 0, bottom: 0, left: 0 }}>
            {/* Hidden XAxis → Tooltip-Header zeigt die Kategorie statt Bar-Index. */}
            <XAxis dataKey="name" hide tick={{ fontSize: 10 }} /* achsen-allow: Sparkline ohne Achsenbeschriftung */ />
            <Tooltip {...eedcTooltipProps({ unit })} />
            <Bar dataKey="value" name="Wert" radius={[2, 2, 0, 0]}>
              {data.map((entry, i) => (
                <Cell
                  key={i}
                  fill={
                    entry.value >= max * 0.8 ? colors[2]
                      : entry.value >= max * 0.5 ? colors[1]
                        : colors[0]
                  }
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      <div className="flex justify-between text-xs text-gray-400 dark:text-gray-500 mt-0.5">
        <span>{data[0]?.name}</span>
        <span>{data[data.length - 1]?.name}</span>
      </div>
    </div>
  )
}
