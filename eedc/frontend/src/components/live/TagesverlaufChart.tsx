/**
 * TagesverlaufChart — Stündlicher Leistungsverlauf als gestapeltes AreaChart.
 *
 * Zeigt PV-Erzeugung (gelb) vs. Verbrauchskomponenten (gestapelt) über den Tag.
 * Aktuelle Stunde wird per ReferenceLine markiert.
 */

import {
  AreaChart, Area, XAxis, YAxis, ResponsiveContainer,
  Tooltip, ReferenceLine, Legend, CartesianGrid,
} from 'recharts'
import type { TagesverlaufPunkt } from '../../api/liveDashboard'

interface TagesverlaufChartProps {
  punkte: TagesverlaufPunkt[]
}

const FARBEN = {
  pv: '#eab308',
  haushalt: '#10b981',
  waermepumpe: '#f97316',
  eauto: '#a855f7',
  netzbezug: '#ef4444',
  einspeisung: '#22c55e',
  batterie: '#3b82f6',
}

const LABELS: Record<string, string> = {
  pv: 'PV',
  haushalt: 'Haushalt',
  waermepumpe: 'Wärmepumpe',
  eauto: 'E-Auto',
  netzbezug: 'Netzbezug',
  einspeisung: 'Einspeisung',
  batterie: 'Batterie',
}

export default function TagesverlaufChart({ punkte }: TagesverlaufChartProps) {
  if (punkte.length === 0) return null

  const now = new Date()
  const currentHour = `${now.getHours().toString().padStart(2, '0')}:00`

  // Daten für Recharts aufbereiten — null → 0 für stacking
  const chartData = punkte.map((p) => ({
    zeit: p.zeit,
    pv: p.pv ?? 0,
    haushalt: p.haushalt ?? 0,
    waermepumpe: p.waermepumpe ?? 0,
    eauto: p.eauto ?? 0,
    netzbezug: p.netzbezug ?? 0,
    einspeisung: p.einspeisung ?? 0,
    batterie_ladung: p.batterie !== null && p.batterie > 0 ? p.batterie : 0,
    batterie_entladung: p.batterie !== null && p.batterie < 0 ? -p.batterie : 0,
  }))

  // Prüfen welche Serien tatsächlich Daten haben
  const hatDaten = (key: string) => chartData.some((d) => (d as Record<string, unknown>)[key] as number > 0)

  return (
    <div>
      <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3">
        Tagesverlauf (kW)
      </h3>
      <ResponsiveContainer width="100%" height={280}>
        <AreaChart data={chartData} margin={{ top: 5, right: 10, left: -10, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" className="stroke-gray-200 dark:stroke-gray-700" />
          <XAxis
            dataKey="zeit"
            tick={{ fontSize: 11 }}
            className="fill-gray-500 dark:fill-gray-400"
            interval="preserveStartEnd"
          />
          <YAxis
            tick={{ fontSize: 11 }}
            className="fill-gray-500 dark:fill-gray-400"
            tickFormatter={(v: number) => v.toFixed(1)}
          />
          <Tooltip
            contentStyle={{
              fontSize: 12,
              borderRadius: 8,
              backgroundColor: 'var(--tooltip-bg, #fff)',
              color: 'var(--tooltip-fg, #1f2937)',
              border: '1px solid var(--tooltip-border, #e5e7eb)',
            }}
            labelFormatter={(label: string) => `${label} Uhr`}
            formatter={(value: number, name: string) => {
              if (value === 0) return [null, null]
              const label = LABELS[name] || name
              return [`${value.toFixed(2)} kW`, label]
            }}
          />
          <Legend
            formatter={(value: string) => LABELS[value] || value}
            wrapperStyle={{ fontSize: 11 }}
          />

          {/* PV-Erzeugung */}
          {hatDaten('pv') && (
            <Area
              type="monotone"
              dataKey="pv"
              fill={FARBEN.pv}
              stroke={FARBEN.pv}
              fillOpacity={0.3}
              strokeWidth={2}
            />
          )}

          {/* Verbrauchskomponenten */}
          {hatDaten('haushalt') && (
            <Area
              type="monotone"
              dataKey="haushalt"
              fill={FARBEN.haushalt}
              stroke={FARBEN.haushalt}
              fillOpacity={0.3}
              strokeWidth={1.5}
            />
          )}
          {hatDaten('waermepumpe') && (
            <Area
              type="monotone"
              dataKey="waermepumpe"
              fill={FARBEN.waermepumpe}
              stroke={FARBEN.waermepumpe}
              fillOpacity={0.3}
              strokeWidth={1.5}
            />
          )}
          {hatDaten('eauto') && (
            <Area
              type="monotone"
              dataKey="eauto"
              fill={FARBEN.eauto}
              stroke={FARBEN.eauto}
              fillOpacity={0.3}
              strokeWidth={1.5}
            />
          )}
          {hatDaten('netzbezug') && (
            <Area
              type="monotone"
              dataKey="netzbezug"
              fill={FARBEN.netzbezug}
              stroke={FARBEN.netzbezug}
              fillOpacity={0.2}
              strokeWidth={1.5}
              strokeDasharray="4 2"
            />
          )}
          {hatDaten('einspeisung') && (
            <Area
              type="monotone"
              dataKey="einspeisung"
              fill={FARBEN.einspeisung}
              stroke={FARBEN.einspeisung}
              fillOpacity={0.2}
              strokeWidth={1.5}
              strokeDasharray="4 2"
            />
          )}

          {/* Aktuelle Stunde */}
          <ReferenceLine
            x={currentHour}
            stroke="#6b7280"
            strokeDasharray="3 3"
            label={{ value: 'Jetzt', position: 'top', fontSize: 10 }}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}
