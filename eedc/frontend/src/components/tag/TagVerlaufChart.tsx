/**
 * TagVerlaufChart — Butterfly-Stundenchart eines Tages (Quellen ▲ / Senken ▼).
 *
 * Aus der IST-„Tagesdetail"-Sicht (`pages/auswertung/EnergieprofilTab.tsx`)
 * extrahiert, damit Cockpit/Tag (v4) und die IST-Seite EINE Code-Wahrheit teilen
 * (Konvergenz-Leitprinzip, wie Aussicht ↔ EnergieprofilPrognose). Reine
 * Darstellung aus `StundenWert[]` + `SerieInfo[]` (extra Serien) — kein Daten-Laden.
 * Farben ausschließlich aus `lib` (kein Inline-Hex, Regel 0a).
 */
import { useMemo } from 'react'
import {
  ComposedChart, Area, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer, ReferenceLine,
} from 'recharts'
import { Card, ChartLegende, eedcTooltipProps } from '../ui'
import { EXTRA_SERIEN_FARBEN, KATEGORIE_FARBEN, COLORS, HILFSLINIE_DASH, AREA_FILL_OPACITY } from '../../lib'
import { useChartTheme } from '../../context/ThemeContext'
import type { StundenWert, SerieInfo } from '../../api/energie_profil'

function round2(v: number): number {
  return Math.round(v * 100) / 100
}

interface ChartSerie { dataKey: string; label: string; farbe: string; stackId: 'quellen' | 'senken'; hideLabel?: boolean }

export function TagVerlaufChart({ daten, extraSerien }: { daten: StundenWert[]; extraSerien: SerieInfo[] }) {
  const achsen = useChartTheme()
  const extraErzeuger    = useMemo(() => extraSerien.filter(s => s.seite === 'quelle'), [extraSerien])
  const extraVerbraucher = useMemo(() => extraSerien.filter(s => s.seite === 'senke'), [extraSerien])

  // Chart-Serien analog Live-TagesverlaufChart: bidirektionale in _pos/_neg aufgespalten.
  const chartSerien = useMemo<ChartSerie[]>(() => {
    const r: ChartSerie[] = []
    r.push({ dataKey: 'pv', label: 'PV', farbe: KATEGORIE_FARBEN.pv, stackId: 'quellen' })
    extraErzeuger.forEach((es, i) =>
      r.push({ dataKey: es.key, label: es.label, farbe: EXTRA_SERIEN_FARBEN[i % EXTRA_SERIEN_FARBEN.length], stackId: 'quellen' }))
    r.push({ dataKey: 'bat_pos', label: 'Batterie', farbe: KATEGORIE_FARBEN.batterie, stackId: 'quellen' })
    r.push({ dataKey: 'bat_neg', label: 'Batterie ↓', farbe: KATEGORIE_FARBEN.batterie, stackId: 'senken', hideLabel: true })
    r.push({ dataKey: 'netz_pos', label: 'Stromnetz', farbe: KATEGORIE_FARBEN.netz, stackId: 'quellen' })
    r.push({ dataKey: 'netz_neg', label: 'Stromnetz ↓', farbe: KATEGORIE_FARBEN.netz, stackId: 'senken', hideLabel: true })
    r.push({ dataKey: 'hausverbrauch', label: 'Hausverbrauch', farbe: KATEGORIE_FARBEN.haushalt, stackId: 'senken' })
    r.push({ dataKey: 'wp', label: 'Wärmepumpe', farbe: KATEGORIE_FARBEN.waermepumpe, stackId: 'senken' })
    r.push({ dataKey: 'wb', label: 'Wallbox', farbe: KATEGORIE_FARBEN.wallbox, stackId: 'senken' })
    extraVerbraucher.forEach((es, i) =>
      r.push({ dataKey: es.key, label: es.label, farbe: EXTRA_SERIEN_FARBEN[(extraErzeuger.length + i) % EXTRA_SERIEN_FARBEN.length], stackId: 'senken' }))
    return r
  }, [extraErzeuger, extraVerbraucher])

  const chartDaten = useMemo(() =>
    Array.from({ length: 24 }, (_, h) => {
      const s   = daten.find(d => d.stunde === h)
      const bat = s?.batterie_kw ?? 0
      const ntz = (s?.netzbezug_kw ?? 0) - (s?.einspeisung_kw ?? 0)
      const vbrSons = extraVerbraucher.reduce((a, es) => a + Math.abs(Math.min(0, s?.komponenten?.[es.key] ?? 0)), 0)
      const erzSons = extraErzeuger.reduce((a, es) => a + Math.max(0, s?.komponenten?.[es.key] ?? 0), 0)
      const punkt: Record<string, number | string> = {
        stunde:       `${h}:00`,
        pv:           s?.pv_kw ?? 0,
        bat_pos:      Math.max(0, bat),
        bat_neg:      Math.min(0, bat),
        netz_pos:     Math.max(0, ntz),
        netz_neg:     Math.min(0, ntz),
        hausverbrauch: -Math.max(0, (s?.verbrauch_kw ?? 0) - (s?.waermepumpe_kw ?? 0) - (s?.wallbox_kw ?? 0) - vbrSons),
        wp:           -(s?.waermepumpe_kw ?? 0),
        wb:           -(s?.wallbox_kw ?? 0),
        gesamterzeugung: round2((s?.pv_kw ?? 0) + Math.max(0, bat) + erzSons),
      }
      for (const es of extraErzeuger)    punkt[es.key] = Math.max(0, s?.komponenten?.[es.key] ?? 0)
      for (const es of extraVerbraucher) punkt[es.key] = Math.min(0, s?.komponenten?.[es.key] ?? 0)
      return punkt
    }), [daten, extraErzeuger, extraVerbraucher])

  return (
    <Card>
      <div className="text-[10px] text-gray-400 dark:text-gray-500 mb-1 flex justify-between">
        <span>▲ Quellen (Erzeugung, Bezug)</span>
        <span>Stundenmittelwerte aus Energieprofil · gestrichelt = Verfügbare Energie</span>
        <span>▼ Senken (Verbrauch, Einspeisung)</span>
      </div>
      <ResponsiveContainer width="100%" height={320}>
        <ComposedChart data={chartDaten} margin={{ top: 5, right: 10, left: -10, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" className="stroke-gray-200 dark:stroke-gray-700" />
          <XAxis dataKey="stunde" tick={{ fontSize: 10 }} interval={2} />
          <YAxis tick={{ fontSize: 10 }} tickFormatter={(v: number) => v.toFixed(1)} />
          <ReferenceLine y={0} stroke={achsen.referenz} strokeWidth={1.5} />
          <Tooltip {...eedcTooltipProps({
            unit: ' kW', decimals: 2,
            nameFormatter: (name) => chartSerien.find(cs => cs.dataKey === name)?.label ?? name,
            formatter: (v) => Math.abs(v) < 0.001 ? null : `${v > 0 ? '▲' : '▼'} ${Math.abs(v).toFixed(2)} kW`,
          })} />
          <Legend content={<ChartLegende
            formatter={(value) => chartSerien.find(cs => cs.dataKey === value)?.label ?? value}
          />} />

          {chartSerien.map(cs => (
            <Area
              key={cs.dataKey}
              type="monotone"
              dataKey={cs.dataKey}
              name={cs.dataKey}
              fill={cs.farbe}
              stroke={cs.farbe}
              fillOpacity={AREA_FILL_OPACITY}
              strokeWidth={1.5}
              stackId={cs.stackId}
              isAnimationActive={false}
              legendType={cs.hideLabel ? 'none' : undefined}
            />
          ))}

          {/* Summen-/Hilfslinie (keine Prognose) → HILFSLINIE_DASH, nicht PROGNOSE_DASH (Regel C). */}
          <Line dataKey="gesamterzeugung" name="gesamterzeugung"
            stroke={COLORS.solar} strokeWidth={2} strokeDasharray={HILFSLINIE_DASH}
            dot={false} connectNulls legendType="none" />
        </ComposedChart>
      </ResponsiveContainer>
    </Card>
  )
}
