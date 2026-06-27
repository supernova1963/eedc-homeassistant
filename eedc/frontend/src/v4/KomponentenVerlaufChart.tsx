/**
 * KomponentenVerlaufChart — gestapelter Monatsverlauf über die gesamte Historie
 * (Komponenten-Hub Block ④, IA v4 A.2). Generisch: `rows` (Monatszeilen) +
 * `bars` (Serien mit Rollenfarbe aus `lib/colors`). Hub = Gesamtzeitraum, daher
 * alle erfassten Monate; ein simpler Verlauf, kein Datums-Scope (K-B5).
 */
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from 'recharts'
import { CHART_HOVER_CURSOR, xAchse, yAchse } from '../lib'
import { useSchmaleAchse } from '../hooks'
import { ChartTooltip, ChartLegende } from '../components/ui'

export interface VerlaufBar {
  key: string; label: string; farbe: string
  /** Stapel-Gruppe: Bars gleicher `stapel` stapeln sich; verschiedene stehen
   *  nebeneinander (z. B. PV „Erzeugung" je Modul ⟷ „Verwendung"). */
  stapel?: string
}
export interface VerlaufRow { name: string; [serie: string]: number | string }

/** Lange Serien-Bezeichnungen im Tooltip auf eine Zeile kürzen (mit „…"). */
function kuerze(label: string, max = 22): string {
  return label.length > max ? `${label.slice(0, max - 1)}…` : label
}

export function KomponentenVerlaufChart({
  rows, bars, einheit = 'kWh', tall, gestapelt = true,
}: { rows: VerlaufRow[]; bars: VerlaufBar[]; einheit?: string; tall?: boolean; gestapelt?: boolean }) {
  const schmal = useSchmaleAchse()
  if (rows.length === 0) {
    return <p className="text-sm text-gray-500 dark:text-gray-400">Keine Verlaufsdaten erfasst.</p>
  }
  return (
    <div className={tall ? 'h-[420px]' : 'h-72'}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={rows} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="name" {...xAchse(schmal)} interval="preserveStartEnd" />
          <YAxis {...yAchse(schmal, 44)} unit={` ${einheit}`} />
          {/* ChartTooltip-SoT (S1: Viereck-Swatch, monochromer Wert); Serien-Name
              gekürzt, Wert gerundet mit Einheit. */}
          <Tooltip cursor={CHART_HOVER_CURSOR} content={<ChartTooltip unit={einheit} decimals={0} nameFormatter={kuerze} />} />
          <Legend wrapperStyle={{ fontSize: 11 }} content={<ChartLegende />} />
          {bars.map((b) => (
            // stapel-Gruppe gewinnt (paarweise Stapel); sonst gestapelt=false → gruppiert, true → ein Stapel.
            <Bar key={b.key} dataKey={b.key} name={b.label} stackId={b.stapel ?? (gestapelt ? 'a' : undefined)} fill={b.farbe} />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
