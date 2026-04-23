/**
 * TagesverlaufChart — Butterfly-Chart (Quellen oben, Senken unten).
 *
 * Dynamische Serien aus Backend: Jede Investition wird einzeln dargestellt.
 * Positive Werte = Quellen (PV, Batterie-Entladung, Netzbezug)
 * Negative Werte = Senken (Haushalt, WP, Wallbox, Batterie-Ladung, Einspeisung)
 * Bidirektionale Serien (Speicher) werden in pos/neg aufgespalten.
 * Overlay-Serien (Strompreis) werden als Linie auf sekundärer Y-Achse gerendert.
 *
 * Stacking: Zwei getrennte stackIds ("quellen" / "senken") damit sich
 * positive und negative Werte nicht gegenseitig aufheben.
 */

import { useState, useCallback, useMemo } from 'react'
import {
  ComposedChart, Area, Line, XAxis, YAxis, ResponsiveContainer,
  Tooltip, ReferenceLine, Legend, CartesianGrid,
} from 'recharts'
import type { TagesverlaufSerie, TagesverlaufPunkt } from '../../api/liveDashboard'
import ChartTooltip from '../ui/ChartTooltip'

interface TagesverlaufChartProps {
  serien: TagesverlaufSerie[]
  punkte: TagesverlaufPunkt[]
  uebersprungen?: string[]
}

/** Interne Darstellung einer Render-Serie (nach Aufspaltung bidirektionaler Serien). */
interface RenderSerie {
  dataKey: string
  label: string
  farbe: string
  stackId: 'quellen' | 'senken'
  /** Originale Serie-Key (für Tooltip-Gruppierung) */
  origKey: string
}

export default function TagesverlaufChart({ serien, punkte, uebersprungen }: TagesverlaufChartProps) {
  const [hidden, setHidden] = useState<Set<string>>(new Set())

  const toggleSerie = useCallback((origKey: string) => {
    setHidden((prev) => {
      const next = new Set(prev)
      if (next.has(origKey)) next.delete(origKey)
      else next.add(origKey)
      return next
    })
  }, [])

  // Overlay-Serien (z.B. Strompreis) — separate Achse, als Linie
  const overlaySerien = useMemo(() => serien.filter((s) => s.seite === 'overlay'), [serien])

  // Render-Serien: Bidirektionale werden in _pos/_neg aufgespalten (ohne Overlays)
  const renderSerien = useMemo<RenderSerie[]>(() => {
    const result: RenderSerie[] = []
    for (const s of serien) {
      if (s.seite === 'overlay') continue  // Overlays separat behandelt

      if (s.bidirektional) {
        // Positiver Anteil → Quellen-Stack
        result.push({
          dataKey: `${s.key}_pos`,
          label: `${s.label} ↑`,
          farbe: s.farbe,
          stackId: 'quellen',
          origKey: s.key,
        })
        // Negativer Anteil → Senken-Stack
        result.push({
          dataKey: `${s.key}_neg`,
          label: `${s.label} ↓`,
          farbe: s.farbe,
          stackId: 'senken',
          origKey: s.key,
        })
      } else if (s.seite === 'quelle') {
        result.push({
          dataKey: s.key,
          label: s.label,
          farbe: s.farbe,
          stackId: 'quellen',
          origKey: s.key,
        })
      } else {
        result.push({
          dataKey: s.key,
          label: s.label,
          farbe: s.farbe,
          stackId: 'senken',
          origKey: s.key,
        })
      }
    }
    return result
  }, [serien])

  // Chart-Daten: Bidirektionale Serien in pos/neg splitten, Overlays direkt übernehmen.
  // Hide-Steuerung übernimmt Recharts via `hide`-Prop am Area/Line — nicht über 0-Daten,
  // sonst entfernt `hatDaten` versteckte Serien aus dem DOM und Re-Toggle bringt sie nicht zurück.
  const chartData = useMemo(() => {
    return punkte.map((p) => {
      const row: Record<string, string | number> = { zeit: p.zeit }
      for (const s of serien) {
        const val = p.werte[s.key] ?? 0
        if (s.seite === 'overlay') {
          row[s.key] = val
        } else if (s.bidirektional) {
          row[`${s.key}_pos`] = Math.max(0, val)
          row[`${s.key}_neg`] = Math.min(0, val)
        } else {
          row[s.key] = val
        }
      }
      return row
    })
  }, [punkte, serien])

  if (punkte.length === 0 || serien.length === 0) return null

  const now = new Date()
  const currentMinBucket = Math.floor(now.getMinutes() / 10) * 10
  const currentHour = `${now.getHours().toString().padStart(2, '0')}:${currentMinBucket.toString().padStart(2, '0')}`

  // Prüfen ob eine Render-Serie tatsächlich Daten hat
  const hatDaten = (dataKey: string) =>
    chartData.some((d) => Math.abs(d[dataKey] as number) > 0.001)

  return (
    <div>
      <div className="flex items-baseline gap-2 mb-3">
        <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300">
          Tagesverlauf (kW)
        </h3>
        <span className="text-[10px] text-gray-400 dark:text-gray-500">
          10-Min-Durchschnitte aus HA-History
        </span>
      </div>
      {uebersprungen && uebersprungen.length > 0 && (
        <p className="text-[10px] text-amber-500 dark:text-amber-400 mb-2">
          Nicht dargestellt (kein HA-Leistungssensor): {uebersprungen.join(', ')}
        </p>
      )}
      <div className="text-[10px] text-gray-400 dark:text-gray-500 mb-1 flex justify-between px-1">
        <span>▲ Quellen (Erzeugung, Bezug)</span>
        <span>▼ Senken (Verbrauch, Einspeisung)</span>
      </div>
      <ResponsiveContainer width="100%" height={320}>
        <ComposedChart data={chartData} margin={{ top: 5, right: overlaySerien.length > 0 ? 10 : 10, left: -10, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" className="stroke-gray-200 dark:stroke-gray-700" />
          <XAxis
            dataKey="zeit"
            tick={{ fontSize: 11 }}
            className="fill-gray-500 dark:fill-gray-400"
            interval="preserveStartEnd"
          />
          <YAxis
            yAxisId="left"
            tick={{ fontSize: 11 }}
            className="fill-gray-500 dark:fill-gray-400"
            tickFormatter={(v: number) => v.toFixed(1)}
          />
          {overlaySerien.length > 0 && (
            <YAxis
              yAxisId="right"
              orientation="right"
              tick={{ fontSize: 10 }}
              className="fill-gray-400 dark:fill-gray-500"
              tickFormatter={(v: number) => v.toFixed(0)}
              label={{ value: overlaySerien[0].einheit || '', angle: -90, position: 'insideRight', fontSize: 10, className: 'fill-gray-400 dark:fill-gray-500' }}
            />
          )}
          <Tooltip content={<ChartTooltip
            labelFormatter={(label) => `${label} Uhr`}
            itemSorter={(item) => -(Math.abs(item.value as number))}
            nameFormatter={(name) => {
              // Overlay-Serien direkt über key finden
              const overlay = overlaySerien.find((s) => s.key === name)
              if (overlay) return overlay.label
              const rs = renderSerien.find((r) => r.dataKey === name)
              const origSerie = serien.find((s) => s.key === rs?.origKey)
              return origSerie?.label || rs?.label || name
            }}
            formatter={(value, name) => {
              if (Math.abs(value) < 0.001) return null
              // Overlay-Serien: eigene Einheit
              const overlay = overlaySerien.find((s) => s.key === name)
              if (overlay) return `${value.toFixed(1)} ${overlay.einheit || ''}`
              const absVal = Math.abs(value).toFixed(2)
              const richtung = value > 0 ? '▲' : '▼'
              return `${richtung} ${absVal} kW`
            }}
          />} />
          <Legend
            formatter={(value: string) => {
              // Overlay-Serien direkt
              const overlay = overlaySerien.find((s) => s.key === value)
              if (overlay) return `${overlay.label} (${overlay.einheit || ''})`
              const rs = renderSerien.find((r) => r.dataKey === value)
              const origSerie = serien.find((s) => s.key === rs?.origKey)
              // Bidirektionale: nur einmal in Legende (pos zeigen, neg verstecken)
              return origSerie?.label || rs?.label || value
            }}
            wrapperStyle={{ fontSize: 11, cursor: 'pointer' }}
            onClick={(e) => {
              if (e && typeof e.dataKey === 'string') {
                // Overlay oder Render-Serie → Toggle
                const overlay = overlaySerien.find((s) => s.key === e.dataKey)
                if (overlay) { toggleSerie(overlay.key); return }
                const rs = renderSerien.find((r) => r.dataKey === e.dataKey)
                if (rs) toggleSerie(rs.origKey)
              }
            }}
          />

          {/* Null-Linie (Energiebilanz-Grenze) */}
          <ReferenceLine yAxisId="left" y={0} stroke="#9ca3af" strokeWidth={1.5} />

          {/* Dynamische Areas — getrennte Stacks für Quellen und Senken */}
          {renderSerien.map((rs) => {
            if (!hatDaten(rs.dataKey)) return null

            // Bidirektionale _neg Serien: in Legende verstecken (nur _pos zeigen)
            const legendHide = rs.dataKey.endsWith('_neg')

            return (
              <Area
                key={rs.dataKey}
                type="monotone"
                dataKey={rs.dataKey}
                name={rs.dataKey}
                yAxisId="left"
                fill={rs.farbe}
                stroke={rs.farbe}
                fillOpacity={0.3}
                strokeWidth={1.5}
                stackId={rs.stackId}
                isAnimationActive={false}
                legendType={legendHide ? 'none' : undefined}
                hide={hidden.has(rs.origKey)}
              />
            )
          })}

          {/* Overlay-Linien (z.B. Strompreis) — sekundäre Y-Achse */}
          {overlaySerien.map((s) => {
            if (!hatDaten(s.key)) return null
            return (
              <Line
                key={s.key}
                type="stepAfter"
                dataKey={s.key}
                name={s.key}
                yAxisId="right"
                stroke={s.farbe}
                strokeWidth={1.5}
                strokeDasharray="4 2"
                dot={false}
                isAnimationActive={false}
                connectNulls={false}
                hide={hidden.has(s.key)}
              />
            )
          })}

          {/* Aktuelle Stunde */}
          <ReferenceLine
            yAxisId="left"
            x={currentHour}
            stroke="#6b7280"
            strokeDasharray="3 3"
            label={{ value: 'Jetzt', position: 'top', fontSize: 10 }}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  )
}
