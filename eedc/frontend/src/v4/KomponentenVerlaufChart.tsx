/**
 * KomponentenVerlaufChart — gestapelter Monatsverlauf über die gesamte Historie
 * (Komponenten-Hub Block ④, IA v4 A.2). Generisch: `rows` (Monatszeilen) +
 * `bars` (Serien mit Rollenfarbe aus `lib/colors`). Hub = Gesamtzeitraum, daher
 * alle erfassten Monate; ein simpler Verlauf, kein Datums-Scope (K-B5).
 */
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from 'recharts'

export interface VerlaufBar { key: string; label: string; farbe: string }
export interface VerlaufRow { name: string; [serie: string]: number | string }

export function KomponentenVerlaufChart({
  rows, bars, einheit = 'kWh', tall,
}: { rows: VerlaufRow[]; bars: VerlaufBar[]; einheit?: string; tall?: boolean }) {
  if (rows.length === 0) {
    return <p className="text-sm text-gray-500 dark:text-gray-400">Keine Verlaufsdaten erfasst.</p>
  }
  return (
    <div className={tall ? 'h-[420px]' : 'h-72'}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={rows} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="name" fontSize={10} interval="preserveStartEnd" />
          <YAxis fontSize={10} width={44} unit={` ${einheit}`} />
          <Tooltip formatter={(v: number) => [`${Math.round(v)} ${einheit}`]} />
          <Legend wrapperStyle={{ fontSize: 11 }} />
          {bars.map((b) => (
            <Bar key={b.key} dataKey={b.key} name={b.label} stackId="a" fill={b.farbe} />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
