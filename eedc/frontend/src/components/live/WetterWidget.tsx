/**
 * WetterWidget — Aktuelles Wetter + Stundenprognose + PV/Verbrauch-Chart.
 *
 * Breites Layout (volle Breite): Hero links, Stundenverlauf Mitte, KPI rechts.
 * Darunter: PV-Ertrag vs. Verbrauch — IST (solid) + Prognose (dashed), volle 24h.
 */

import { useMemo } from 'react'
import { AreaChart, Area, XAxis, YAxis, ResponsiveContainer, Tooltip, ReferenceLine } from 'recharts'
import { Sun, Cloud, CloudRain, CloudSnow, CloudDrizzle, CloudFog, CloudLightning, Droplets, Thermometer, CloudSun, Zap, BatteryCharging } from 'lucide-react'
import type { LiveWetterResponse, TagesverlaufResponse } from '../../api/liveDashboard'

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
  tagesverlauf?: TagesverlaufResponse | null
  loading?: boolean
}

export default function WetterWidget({ wetter, tagesverlauf, loading }: WetterWidgetProps) {
  const now = new Date()
  const currentHour = now.getHours()

  // IST-Daten aus Tagesverlauf aggregieren:
  //   PV = Σ PV-Serien (positiv)
  //   Verbrauch = PV + Netzbezug - Einspeisung (Energiebilanz)
  //   Netz-Wert im Butterfly: positiv=Bezug, negativ=Einspeisung
  //   → Verbrauch = pvSum + netzValue
  const istDaten = useMemo(() => {
    if (!tagesverlauf?.punkte?.length || !tagesverlauf?.serien?.length) return null

    const pvKeys = tagesverlauf.serien
      .filter(s => s.kategorie === 'pv')
      .map(s => s.key)

    const result: Record<number, { pv: number; verbrauch: number }> = {}

    for (const punkt of tagesverlauf.punkte) {
      const h = parseInt(punkt.zeit.split(':')[0])
      if (h > currentHour) continue // Nur vergangene Stunden

      let pvSum = 0
      const netzValue = punkt.werte['netz'] ?? 0 // positiv=Bezug, negativ=Einspeisung

      for (const [key, val] of Object.entries(punkt.werte)) {
        if (pvKeys.includes(key)) {
          pvSum += val // PV ist positiv
        }
      }

      // Energiebilanz: Verbrauch = PV + Netzbezug - Einspeisung = pvSum + netzValue
      const verbrauch = pvSum + netzValue
      result[h] = { pv: pvSum, verbrauch: Math.max(0, verbrauch) }
    }

    return Object.keys(result).length > 0 ? result : null
  }, [tagesverlauf, currentHour])

  // Chart-Daten: 24h mit IST + Prognose
  const chartData = useMemo(() => {
    if (!wetter?.verfuegbar) return []

    // Prognose-Daten indexieren
    const prognoseMap: Record<number, { pv: number; verbrauch: number }> = {}
    for (const v of wetter.verbrauchsprofil) {
      const h = parseInt(v.zeit.replace(':00', ''))
      prognoseMap[h] = { pv: v.pv_ertrag_kw, verbrauch: v.verbrauch_kw }
    }

    const data: Array<Record<string, number | string | null>> = []

    for (let h = 0; h < 24; h++) {
      const punkt: Record<string, number | string | null> = { zeit: String(h) }
      const prognose = prognoseMap[h]
      const ist = istDaten?.[h]

      if (h < currentHour) {
        // Vergangene Stunden: IST (solid) + PV-Prognose (dashed, zum Vergleich)
        if (ist) {
          punkt.pv_ist = ist.pv
          punkt.verbrauch_ist = ist.verbrauch
        } else if (prognose) {
          // Fallback auf Prognose wenn kein IST
          punkt.pv_ist = prognose.pv
          punkt.verbrauch_ist = prognose.verbrauch
        }
        punkt.pv_prognose = prognose?.pv ?? null
        punkt.verbrauch_prognose = null
      } else if (h === currentHour) {
        // Aktuelle Stunde: Beide zeigen für nahtlosen Übergang
        if (ist) {
          punkt.pv_ist = ist.pv
          punkt.verbrauch_ist = ist.verbrauch
        }
        if (prognose) {
          punkt.pv_prognose = prognose.pv
          punkt.verbrauch_prognose = prognose.verbrauch
        }
        // Falls IST fehlt, Prognose auch als IST (Übergang)
        if (!ist && prognose) {
          punkt.pv_ist = prognose.pv
          punkt.verbrauch_ist = prognose.verbrauch
        }
      } else {
        // Zukünftige Stunden: Nur Prognose (dashed)
        punkt.pv_ist = null
        punkt.verbrauch_ist = null
        if (prognose) {
          punkt.pv_prognose = prognose.pv
          punkt.verbrauch_prognose = prognose.verbrauch
        }
      }

      data.push(punkt)
    }

    return data
  }, [wetter, istDaten, currentHour])

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

  const { aktuell, stunden } = wetter

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

      {/* PV-Ertrag vs. Verbrauch — IST + Prognose */}
      {chartData.length > 0 && (
        <div>
          <div className="text-xs text-gray-500 dark:text-gray-400 mb-1">
            PV-Ertrag vs. Verbrauch — IST + Prognose
          </div>
          <ResponsiveContainer width="100%" height={140}>
            <AreaChart data={chartData} margin={{ top: 5, right: 5, left: -20, bottom: 0 }}>
              <defs>
                {/* IST-Gradienten (kräftiger) */}
                <linearGradient id="pvIstGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#eab308" stopOpacity={0.5} />
                  <stop offset="95%" stopColor="#eab308" stopOpacity={0.1} />
                </linearGradient>
                <linearGradient id="vrbIstGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#ef4444" stopOpacity={0.35} />
                  <stop offset="95%" stopColor="#ef4444" stopOpacity={0.05} />
                </linearGradient>
                {/* Prognose-Gradienten (blasser) */}
                <linearGradient id="pvProgGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#eab308" stopOpacity={0.2} />
                  <stop offset="95%" stopColor="#eab308" stopOpacity={0.02} />
                </linearGradient>
                <linearGradient id="vrbProgGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#ef4444" stopOpacity={0.15} />
                  <stop offset="95%" stopColor="#ef4444" stopOpacity={0.02} />
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
                formatter={(value: number, name: string) => {
                  if (value === null || value === undefined) return [null, null]
                  const labels: Record<string, string> = {
                    pv_ist: 'PV (IST)',
                    pv_prognose: 'PV (Prognose)',
                    verbrauch_ist: 'Verbrauch (IST)',
                    verbrauch_prognose: 'Verbrauch (Prognose)',
                  }
                  return [`${value.toFixed(2)} kW`, labels[name] ?? name]
                }}
                itemSorter={() => 0}
              />
              {/* Aktuelle Stunde — Trennlinie IST/Prognose */}
              <ReferenceLine
                x={String(currentHour)}
                stroke="#6366f1"
                strokeDasharray="3 3"
                strokeWidth={1}
                label={{ value: 'Jetzt', position: 'top', fontSize: 9, fill: '#6366f1' }}
              />

              {/* IST: PV — solid, kräftig */}
              <Area
                type="monotone"
                dataKey="pv_ist"
                stroke="#eab308"
                fill="url(#pvIstGrad)"
                strokeWidth={2}
                connectNulls={false}
                dot={false}
              />
              {/* IST: Verbrauch — solid */}
              <Area
                type="monotone"
                dataKey="verbrauch_ist"
                stroke="#ef4444"
                fill="url(#vrbIstGrad)"
                strokeWidth={1.5}
                connectNulls={false}
                dot={false}
              />

              {/* Prognose: PV — dashed, blass */}
              <Area
                type="monotone"
                dataKey="pv_prognose"
                stroke="#eab308"
                fill="url(#pvProgGrad)"
                strokeWidth={1.5}
                strokeDasharray="6 3"
                connectNulls={false}
                dot={false}
              />
              {/* Prognose: Verbrauch — dashed, blass */}
              <Area
                type="monotone"
                dataKey="verbrauch_prognose"
                stroke="#ef4444"
                fill="url(#vrbProgGrad)"
                strokeWidth={1}
                strokeDasharray="4 2"
                connectNulls={false}
                dot={false}
              />
            </AreaChart>
          </ResponsiveContainer>
          <div className="flex gap-4 text-[10px] text-gray-500 dark:text-gray-400 mt-1 justify-center">
            <span className="flex items-center gap-1">
              <span className="w-3 h-0.5 bg-yellow-500 rounded" /> PV (IST)
            </span>
            <span className="flex items-center gap-1">
              <span className="w-3 h-0.5 bg-yellow-500/40 rounded border-dashed" /> PV (Prognose)
            </span>
            <span className="flex items-center gap-1">
              <span className="w-3 h-0.5 bg-red-500 rounded" /> Verbrauch (IST)
            </span>
            <span className="flex items-center gap-1"
                  title={wetter.profil_typ?.startsWith('individuell')
                    ? `Basiert auf ${wetter.profil_tage ?? '?'} Tagen ${wetter.profil_typ === 'individuell_wochenende' ? 'Wochenende' : 'Werktag'}-History (${wetter.profil_quelle === 'mqtt' ? 'MQTT' : 'HA'})`
                    : 'Standardlastprofil — wird durch individuelles Profil ersetzt sobald History verfügbar'
                  }>
              <span className="w-3 h-0.5 bg-red-400/40 rounded border-dashed" />
              {wetter.profil_typ?.startsWith('individuell')
                ? `Verbr. (ind., ${wetter.profil_typ === 'individuell_wochenende' ? 'WE' : 'WT'})`
                : 'Verbr. (BDEW H0)'
              }
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
