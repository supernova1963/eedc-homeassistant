/**
 * WetterWidget — Aktuelles Wetter + Stundenprognose + PV/Verbrauch-Chart.
 *
 * Breites Layout (volle Breite): Hero links, Stundenverlauf Mitte, KPI rechts.
 * Darunter: PV-Ertrag vs. Verbrauch Flächendiagramm.
 */

import { AreaChart, Area, XAxis, YAxis, ResponsiveContainer, Tooltip, ReferenceLine } from 'recharts'
import { Sun, Cloud, CloudRain, CloudSnow, CloudDrizzle, CloudFog, CloudLightning, Droplets, Thermometer, CloudSun, Zap, BatteryCharging } from 'lucide-react'
import type { LiveWetterResponse } from '../../api/liveDashboard'

// Wetter-Symbol zu Lucide-Icon Mapping
function WetterIcon({ symbol, className = 'h-5 w-5' }: { symbol: string; className?: string }) {
  switch (symbol) {
    case 'sunny': return <Sun className={`${className} text-yellow-400`} />
    case 'partly_cloudy': return <CloudSun className={`${className} text-yellow-300`} />
    case 'cloudy': return <Cloud className={`${className} text-gray-400`} />
    case 'foggy': return <CloudFog className={`${className} text-gray-400`} />
    case 'drizzle': return <CloudDrizzle className={`${className} text-blue-300`} />
    case 'rainy':
    case 'showers': return <CloudRain className={`${className} text-blue-400`} />
    case 'snowy':
    case 'snow_showers': return <CloudSnow className={`${className} text-blue-200`} />
    case 'thunderstorm': return <CloudLightning className={`${className} text-purple-400`} />
    default: return <Cloud className={`${className} text-gray-400`} />
  }
}

interface WetterWidgetProps {
  wetter: LiveWetterResponse | null
  loading?: boolean
}

export default function WetterWidget({ wetter, loading }: WetterWidgetProps) {
  if (loading) {
    return (
      <div className="flex items-center justify-center py-8">
        <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-primary-600" />
      </div>
    )
  }

  if (!wetter?.verfuegbar) {
    return (
      <div className="text-center py-6">
        <Cloud className="h-8 w-8 text-gray-400 mx-auto mb-2" />
        <p className="text-sm text-gray-500 dark:text-gray-400">
          Keine Wetterdaten verfügbar
        </p>
        <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">
          Standort-Koordinaten in den Stammdaten hinterlegen
        </p>
      </div>
    )
  }

  const { aktuell, stunden, verbrauchsprofil } = wetter
  const now = new Date()
  const currentHour = now.getHours()

  // Chart-Daten: PV vs Verbrauch
  const chartData = verbrauchsprofil.map((v) => ({
    zeit: v.zeit.replace(':00', ''),
    pv: v.pv_ertrag_kw,
    verbrauch: v.verbrauch_kw,
  }))

  return (
    <div className="space-y-4">
      {/* Obere Zeile: Hero + Stundenverlauf + KPIs */}
      <div className="flex flex-col sm:flex-row gap-4 sm:gap-6">
        {/* Aktuelles Wetter — Hero */}
        {aktuell && (
          <div className="flex items-center gap-3 shrink-0">
            <WetterIcon symbol={aktuell.wetter_symbol} className="h-12 w-12" />
            <div>
              <div className="text-4xl font-bold text-gray-900 dark:text-white leading-none">
                {aktuell.temperatur_c !== null ? `${aktuell.temperatur_c.toFixed(0)}°` : '–'}
              </div>
              <div className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                {wetterBeschreibung(aktuell.wetter_symbol)}
              </div>
            </div>
          </div>
        )}

        {/* Stundenverlauf — kompakte Timeline */}
        <div className="flex-1 min-w-0">
          <div className="flex gap-0.5">
            {stunden.map((s) => {
              const h = parseInt(s.zeit.split(':')[0])
              const istJetzt = h === currentHour
              const istVergangen = h < currentHour

              return (
                <div
                  key={s.zeit}
                  className={`flex-1 flex flex-col items-center gap-0.5 py-1 rounded transition-opacity ${
                    istVergangen ? 'opacity-40' : ''
                  } ${istJetzt ? 'ring-1 ring-primary-400 rounded bg-primary-50 dark:bg-primary-900/20' : ''}`}
                  title={`${s.zeit}: ${s.temperatur_c?.toFixed(1)}°C, ${s.globalstrahlung_wm2?.toFixed(0)} W/m²`}
                >
                  <span className="text-[11px] text-gray-400 dark:text-gray-500 leading-none">
                    {h % 3 === 0 ? h : ''}
                  </span>
                  <WetterIcon symbol={s.wetter_symbol} className="h-5 w-5" />
                  <span className="text-[11px] text-gray-600 dark:text-gray-400 leading-none">
                    {s.temperatur_c !== null ? `${s.temperatur_c.toFixed(0)}°` : ''}
                  </span>
                </div>
              )
            })}
          </div>
          {/* Niederschlag-Hinweis */}
          {stunden.some((s) => (s.niederschlag_mm || 0) > 0) && (
            <div className="flex items-center gap-1 mt-1 text-xs text-blue-500 dark:text-blue-400">
              <Droplets className="h-3 w-3" />
              <span>
                {stunden.reduce((sum, s) => sum + (s.niederschlag_mm || 0), 0).toFixed(1)} mm
              </span>
            </div>
          )}
        </div>

        {/* KPIs rechts */}
        <div className="flex sm:flex-col gap-3 sm:gap-2 text-xs shrink-0">
          {wetter.temperatur_min_c !== null && wetter.temperatur_max_c !== null && (
            <div className="flex items-center gap-1.5 text-gray-500 dark:text-gray-400">
              <Thermometer className="h-3.5 w-3.5" />
              <span>{wetter.temperatur_min_c.toFixed(0)}° / {wetter.temperatur_max_c.toFixed(0)}°</span>
            </div>
          )}
          {wetter.sonnenstunden !== null && (
            <div className="flex items-center gap-1.5 text-yellow-600 dark:text-yellow-400">
              <Sun className="h-3.5 w-3.5" />
              <span>{wetter.sonnenstunden.toFixed(1)}h Sonne</span>
            </div>
          )}
          {wetter.pv_prognose_kwh !== null && (
            <div className="flex items-center gap-1.5 text-green-600 dark:text-green-400 font-medium">
              <BatteryCharging className="h-3.5 w-3.5" />
              <span>~{wetter.pv_prognose_kwh} kWh PV</span>
            </div>
          )}
          {wetter.grundlast_kw !== null && (
            <div className="flex items-center gap-1.5 text-gray-500 dark:text-gray-400">
              <Zap className="h-3.5 w-3.5" />
              <span>Grundlast {(wetter.grundlast_kw * 1000).toFixed(0)} W</span>
            </div>
          )}
        </div>
      </div>

      {/* PV-Ertrag vs. Verbrauch Chart */}
      {chartData.length > 0 && (
        <div>
          <div className="text-xs text-gray-500 dark:text-gray-400 mb-1">
            PV-Ertrag vs. Verbrauch (Prognose)
          </div>
          <ResponsiveContainer width="100%" height={120}>
            <AreaChart data={chartData} margin={{ top: 5, right: 5, left: -20, bottom: 0 }}>
              <defs>
                <linearGradient id="pvGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#eab308" stopOpacity={0.4} />
                  <stop offset="95%" stopColor="#eab308" stopOpacity={0.05} />
                </linearGradient>
                <linearGradient id="vrbGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#ef4444" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#ef4444" stopOpacity={0.05} />
                </linearGradient>
              </defs>
              <XAxis
                dataKey="zeit"
                tick={{ fontSize: 10 }}
                className="fill-gray-400 dark:fill-gray-500"
                interval={2}
              />
              <YAxis
                tick={{ fontSize: 10 }}
                className="fill-gray-400 dark:fill-gray-500"
                tickFormatter={(v: number) => `${v.toFixed(1)}`}
              />
              <Tooltip
                contentStyle={{
                  fontSize: 12,
                  borderRadius: 8,
                  backgroundColor: 'var(--tooltip-bg, #fff)',
                  color: 'var(--tooltip-fg, #1f2937)',
                  border: '1px solid var(--tooltip-border, #e5e7eb)',
                }}
                labelFormatter={(label: string) => `${label}:00 Uhr`}
                formatter={(value: number, name: string) => [
                  `${value.toFixed(2)} kW`,
                  name === 'pv' ? 'PV-Ertrag' : 'Verbrauch',
                ]}
              />
              {/* Aktuelle Stunde markieren */}
              {currentHour >= 6 && currentHour <= 20 && (
                <ReferenceLine x={String(currentHour)} stroke="#6366f1" strokeDasharray="3 3" strokeWidth={1} />
              )}
              <Area
                type="monotone"
                dataKey="pv"
                stroke="#eab308"
                fill="url(#pvGrad)"
                strokeWidth={2}
              />
              <Area
                type="monotone"
                dataKey="verbrauch"
                stroke="#ef4444"
                fill="url(#vrbGrad)"
                strokeWidth={1.5}
                strokeDasharray="4 2"
              />
            </AreaChart>
          </ResponsiveContainer>
          <div className="flex gap-4 text-[10px] text-gray-500 dark:text-gray-400 mt-1 justify-center">
            <span className="flex items-center gap-1">
              <span className="w-3 h-0.5 bg-yellow-500 rounded" /> PV-Ertrag
            </span>
            <span className="flex items-center gap-1">
              <span className="w-3 h-0.5 bg-red-400 rounded border-dashed" /> Verbrauch (BDEW H0)
            </span>
          </div>
        </div>
      )}
    </div>
  )
}

function wetterBeschreibung(symbol: string): string {
  switch (symbol) {
    case 'sunny': return 'Sonnig'
    case 'partly_cloudy': return 'Teilweise bewölkt'
    case 'cloudy': return 'Bewölkt'
    case 'foggy': return 'Nebelig'
    case 'drizzle': return 'Nieselregen'
    case 'rainy': return 'Regen'
    case 'showers': return 'Schauer'
    case 'snowy': return 'Schnee'
    case 'snow_showers': return 'Schneeschauer'
    case 'thunderstorm': return 'Gewitter'
    default: return 'Bewölkt'
  }
}
