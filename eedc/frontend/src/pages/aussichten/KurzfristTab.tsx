/**
 * Kurzfrist-Tab: 7-14 Tage PV-Prognose basierend auf Wettervorhersage
 *
 * Nutzt Open-Meteo Solar API mit GTI-Berechnung (Global Tilted Irradiance),
 * die Modulneigung und -ausrichtung für genauere Prognosen berücksichtigt.
 */
import { useState, useEffect } from 'react'
import { Sun, Cloud, CloudSun, CloudRain, CloudSnow, CloudLightning, Thermometer, Zap } from 'lucide-react'
import { Card, LoadingSpinner, Alert } from '../../components/ui'
import ChartTooltip from '../../components/ui/ChartTooltip'
import { wetterApi, SolarPrognose } from '../../api/wetter'
import {
  ResponsiveContainer,
  ComposedChart,
  Bar,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
} from 'recharts'

interface Props {
  anlageId: number
}

// Wetter-Symbol zu Icon
function WetterIcon({ symbol, className = "h-6 w-6" }: { symbol: string; className?: string }) {
  switch (symbol) {
    case 'sunny':
      return <Sun className={`${className} text-yellow-500`} />
    case 'mostly_sunny':
      return <CloudSun className={`${className} text-yellow-400`} />
    case 'partly_cloudy':
      return <CloudSun className={`${className} text-yellow-300`} />
    case 'cloudy':
      return <Cloud className={`${className} text-gray-500`} />
    case 'rainy':
    case 'drizzle':
    case 'showers':
      return <CloudRain className={`${className} text-blue-500`} />
    case 'snowy':
    case 'snow_showers':
      return <CloudSnow className={`${className} text-blue-300`} />
    case 'thunderstorm':
      return <CloudLightning className={`${className} text-purple-500`} />
    case 'foggy':
      return <Cloud className={`${className} text-gray-300`} />
    default:
      return <Sun className={`${className} text-yellow-400`} />
  }
}

// Datum formatieren
function formatDatum(datum: string): string {
  const d = new Date(datum)
  return d.toLocaleDateString('de-DE', { weekday: 'short', day: '2-digit', month: '2-digit' })
}

function formatDatumKurz(datum: string): string {
  const d = new Date(datum)
  return d.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit' })
}

// Quellen-Kürzel für Tabellen-Anzeige
const QUELLEN_KUERZEL: Record<string, { label: string; color: string }> = {
  // Seamless
  icon_seamless:        { label: 'ICON-SL', color: 'text-cyan-400' },
  meteoswiss_seamless:  { label: 'MS-SL',   color: 'text-blue-400' },
  ecmwf_seamless:       { label: 'ECMWF-SL', color: 'text-purple-400' },
  // Einzelmodelle
  meteoswiss_icon_ch2:  { label: 'MeteoSwiss', color: 'text-blue-400' },
  icon_d2:              { label: 'ICON-D2', color: 'text-cyan-400' },
  icon_eu:              { label: 'ICON-EU', color: 'text-green-400' },
  ecmwf_ifs04:          { label: 'ECMWF', color: 'text-purple-400' },
  best_match:           { label: 'Best Match', color: 'text-gray-400' },
}


export default function KurzfristTab({ anlageId }: Props) {
  const [prognose, setPrognose] = useState<SolarPrognose | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const tage = 14

  useEffect(() => {
    loadPrognose()
  }, [anlageId])

  async function loadPrognose() {
    setLoading(true)
    setError(null)
    try {
      const data = await wetterApi.getSolarPrognose(anlageId, tage, false)
      setPrognose(data)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Fehler beim Laden der Prognose')
    } finally {
      setLoading(false)
    }
  }

  if (loading) {
    return <LoadingSpinner text="Lade Kurzfrist-Prognose..." />
  }

  if (error) {
    return <Alert type="error">{error}</Alert>
  }

  if (!prognose) {
    return <Alert type="warning">Keine Prognose verfügbar</Alert>
  }

  // Kaskade aktiv wenn mindestens ein Tag eine spezifische Quelle hat
  const hasKaskade = prognose.tage.some(t => t.datenquelle && t.datenquelle !== 'best_match')

  // Chart-Daten vorbereiten — Vor-/Nachmittag gestapelt
  const hasVmNm = prognose.tage.some(t => t.pv_ertrag_morgens_kwh != null)
  const chartData = prognose.tage.map(tag => ({
    datum: formatDatumKurz(tag.datum),
    datumFull: formatDatum(tag.datum),
    pv_kwh: tag.pv_ertrag_kwh,
    pv_morgens: tag.pv_ertrag_morgens_kwh ?? 0,
    pv_nachmittags: tag.pv_ertrag_nachmittags_kwh ?? 0,
    temperatur: tag.temperatur_max_c,
    gti: tag.gti_kwh_m2,
  }))

  // Heute und morgen
  const heute = prognose.tage[0]
  const morgen = prognose.tage[1]

  // Summen berechnen
  const summeKwh = prognose.tage.reduce((sum, t) => sum + (t.pv_ertrag_kwh || 0), 0)
  const durchschnittKwh = chartData.length > 0 ? summeKwh / chartData.length : 0

  return (
    <div className="space-y-6">
      {/* KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3 sm:gap-4">
        <Card className="p-4">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-yellow-100 dark:bg-yellow-900/30 rounded-lg">
              <Zap className="h-5 w-5 text-yellow-600 dark:text-yellow-400" />
            </div>
            <div>
              <p className="text-sm text-gray-500 dark:text-gray-400">Summe {chartData.length} Tage</p>
              <p className="text-xl font-bold text-gray-900 dark:text-white">
                {summeKwh.toFixed(0)} kWh
              </p>
            </div>
          </div>
        </Card>

        <Card className="p-4">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-blue-100 dark:bg-blue-900/30 rounded-lg">
              <Sun className="h-5 w-5 text-blue-600 dark:text-blue-400" />
            </div>
            <div>
              <p className="text-sm text-gray-500 dark:text-gray-400">Durchschnitt/Tag</p>
              <p className="text-xl font-bold text-gray-900 dark:text-white">
                {durchschnittKwh.toFixed(1)} kWh
              </p>
            </div>
          </div>
        </Card>

        {heute && (
          <Card className="p-4">
            <div className="flex items-center gap-3">
              <WetterIcon symbol={heute.wetter_symbol} className="h-8 w-8" />
              <div>
                <p className="text-sm text-gray-500 dark:text-gray-400">Heute</p>
                <p className="text-xl font-bold text-gray-900 dark:text-white">
                  {(heute.pv_ertrag_kwh ?? 0).toFixed(1)} kWh
                </p>
                {heute.pv_ertrag_morgens_kwh != null && (
                  <p className="text-xs text-gray-400 dark:text-gray-500">
                    VM {heute.pv_ertrag_morgens_kwh.toFixed(1)} · NM {(heute.pv_ertrag_nachmittags_kwh ?? 0).toFixed(1)}
                  </p>
                )}
              </div>
            </div>
          </Card>
        )}

        {morgen && (
          <Card className="p-4">
            <div className="flex items-center gap-3">
              <WetterIcon symbol={morgen.wetter_symbol} className="h-8 w-8" />
              <div>
                <p className="text-sm text-gray-500 dark:text-gray-400">Morgen</p>
                <p className="text-xl font-bold text-gray-900 dark:text-white">
                  {(morgen.pv_ertrag_kwh ?? 0).toFixed(1)} kWh
                </p>
                {morgen.pv_ertrag_morgens_kwh != null && (
                  <p className="text-xs text-gray-400 dark:text-gray-500">
                    VM {morgen.pv_ertrag_morgens_kwh.toFixed(1)} · NM {(morgen.pv_ertrag_nachmittags_kwh ?? 0).toFixed(1)}
                  </p>
                )}
              </div>
            </div>
          </Card>
        )}
      </div>

      {/* Wetter-Streifen */}
      <Card className="p-4">
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-semibold text-gray-900 dark:text-white">Solar-Prognose</h3>
        </div>
        <div className="overflow-x-auto">
          <div className="flex gap-2 min-w-max pb-2">
            {prognose.tage.map((tag, index) => (
              <div
                key={tag.datum}
                className={`flex flex-col items-center p-3 rounded-lg min-w-[80px] ${
                  index === 0
                    ? 'bg-primary-50 dark:bg-primary-900/30 border-2 border-primary-500'
                    : 'bg-gray-50 dark:bg-gray-800'
                }`}
              >
                <span className="text-xs text-gray-500 dark:text-gray-400 mb-1">
                  {formatDatum(tag.datum)}
                </span>
                <WetterIcon symbol={tag.wetter_symbol} className="h-8 w-8 my-1" />
                <span className="text-sm font-semibold text-gray-900 dark:text-white">
                  {tag.pv_ertrag_kwh.toFixed(1)} kWh
                </span>
                {tag.pv_ertrag_morgens_kwh != null && (
                  <span className="text-[10px] text-gray-400 dark:text-gray-500">
                    {tag.pv_ertrag_morgens_kwh.toFixed(1)} · {(tag.pv_ertrag_nachmittags_kwh ?? 0).toFixed(1)}
                  </span>
                )}
                <div className="flex items-center gap-1 mt-1">
                  <Thermometer className="h-3 w-3 text-gray-400" />
                  <span className="text-xs text-gray-500">
                    {tag.temperatur_max_c?.toFixed(0) ?? '-'}°C
                  </span>
                </div>
                {tag.gti_kwh_m2 !== null && tag.gti_kwh_m2 > 0 && (
                  <div className="flex items-center gap-1 mt-1">
                    <Sun className="h-3 w-3 text-orange-500" />
                    <span className="text-xs text-gray-500">
                      {tag.gti_kwh_m2.toFixed(1)} kWh/m²
                    </span>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      </Card>

      {/* Chart */}
      <Card className="p-4">
        <h3 className="font-semibold text-gray-900 dark:text-white mb-4">PV-Prognose</h3>
        <div className="h-[300px]">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" className="stroke-gray-200 dark:stroke-gray-700" />
              <XAxis
                dataKey="datum"
                tick={{ fontSize: 12 }}
                className="text-gray-600 dark:text-gray-400"
              />
              <YAxis
                yAxisId="left"
                tick={{ fontSize: 12 }}
                className="text-gray-600 dark:text-gray-400"
                label={{ value: 'kWh', angle: -90, position: 'insideLeft' }}
              />
              <YAxis
                yAxisId="right"
                orientation="right"
                tick={{ fontSize: 12 }}
                className="text-gray-600 dark:text-gray-400"
                label={{ value: '°C', angle: 90, position: 'insideRight' }}
              />
              <Tooltip content={<ChartTooltip formatter={(value: number, name: string) => {
                  if (name === 'Vormittag' || name === 'Nachmittag' || name === 'PV-Prognose') return `${value.toFixed(1)} kWh`
                  if (name === 'Temperatur') return `${value.toFixed(0)} °C`
                  return `${value.toFixed(1)}`
                }} />} />
              <Legend />
              {hasVmNm ? (
                <>
                  <Bar
                    yAxisId="left"
                    dataKey="pv_morgens"
                    name="Vormittag"
                    stackId="pv"
                    fill="#f59e0b"
                  />
                  <Bar
                    yAxisId="left"
                    dataKey="pv_nachmittags"
                    name="Nachmittag"
                    stackId="pv"
                    fill="#eab308"
                    radius={[4, 4, 0, 0]}
                  />
                </>
              ) : (
                <Bar
                  yAxisId="left"
                  dataKey="pv_kwh"
                  name="PV-Prognose"
                  fill="#eab308"
                  radius={[4, 4, 0, 0]}
                />
              )}
              <Line
                yAxisId="right"
                type="monotone"
                dataKey="temperatur"
                name="Temperatur"
                stroke="#ef4444"
                strokeWidth={2}
                dot={{ r: 3 }}
              />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      </Card>

      {/* Detail-Tabelle */}
      <Card className="p-4">
        <h3 className="font-semibold text-gray-900 dark:text-white mb-4">Details</h3>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-200 dark:border-gray-700">
                <th className="text-left py-2 px-3">Datum</th>
                <th className="text-left py-2 px-3">Wetter</th>
                <th className="text-right py-2 px-3">PV-Prognose</th>
                {hasVmNm && <th className="text-right py-2 px-3">VM</th>}
                {hasVmNm && <th className="text-right py-2 px-3">NM</th>}
                <th className="text-right py-2 px-3">GTI</th>
                <th className="text-right py-2 px-3">Bewölkung</th>
                <th className="text-right py-2 px-3">Temperatur</th>
                <th className="text-right py-2 px-3">Niederschlag</th>
                {hasKaskade && <th className="text-right py-2 px-3">Quelle</th>}
              </tr>
            </thead>
            <tbody>
              {prognose.tage.map((tag, index) => (
                <tr
                  key={tag.datum}
                  className={`border-b border-gray-100 dark:border-gray-800 ${
                    index === 0 ? 'bg-primary-50 dark:bg-primary-900/20' : ''
                  }`}
                >
                  <td className="py-2 px-3 font-medium">{formatDatum(tag.datum)}</td>
                  <td className="py-2 px-3">
                    <WetterIcon symbol={tag.wetter_symbol} className="h-5 w-5" />
                  </td>
                  <td className="py-2 px-3 text-right font-semibold text-yellow-600">
                    {tag.pv_ertrag_kwh.toFixed(1)} kWh
                  </td>
                  {hasVmNm && (
                    <td className="py-2 px-3 text-right text-amber-500">
                      {tag.pv_ertrag_morgens_kwh?.toFixed(1) ?? '-'}
                    </td>
                  )}
                  {hasVmNm && (
                    <td className="py-2 px-3 text-right text-yellow-600">
                      {tag.pv_ertrag_nachmittags_kwh?.toFixed(1) ?? '-'}
                    </td>
                  )}
                  <td className="py-2 px-3 text-right">
                    {tag.gti_kwh_m2?.toFixed(2) ?? '-'} kWh/m²
                  </td>
                  <td className="py-2 px-3 text-right">
                    {tag.bewoelkung_prozent?.toFixed(0) ?? '-'} %
                  </td>
                  <td className="py-2 px-3 text-right">
                    {tag.temperatur_max_c?.toFixed(0) ?? '-'}°C
                  </td>
                  <td className="py-2 px-3 text-right">
                    {tag.niederschlag_mm !== null && tag.niederschlag_mm !== undefined && tag.niederschlag_mm > 0 ? (
                      <span className="text-blue-500">{tag.niederschlag_mm.toFixed(1)} mm</span>
                    ) : (
                      '-'
                    )}
                  </td>
                  {hasKaskade && (
                    <td className="py-2 px-3 text-right">
                      <span className={`text-xs font-mono ${QUELLEN_KUERZEL[tag.datenquelle || 'best_match']?.color || 'text-gray-400'}`}>
                        {QUELLEN_KUERZEL[tag.datenquelle || 'best_match']?.label || tag.datenquelle}
                      </span>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      {/* Meta-Info */}
      <Card className="p-4 bg-gray-50 dark:bg-gray-800">
        <div className="flex flex-wrap gap-4 text-sm text-gray-500 dark:text-gray-400">
          <span>Anlagenleistung: {prognose.anlage.leistung_kwp.toFixed(1)} kWp</span>
          {prognose.string_prognosen && prognose.string_prognosen.length > 1 ? (
            prognose.string_prognosen.map((s, i) => (
              <span key={i}>{s.name}: {s.kwp} kWp, {s.neigung}°/{s.ausrichtung}°</span>
            ))
          ) : (
            <>
              <span>Neigung: {prognose.anlage.neigung}°</span>
              <span>Ausrichtung: {prognose.anlage.azimut}°</span>
            </>
          )}
          <span>Datenquelle: {prognose.datenquelle || 'Open-Meteo Solar (GTI)'}</span>
          <span>Abgerufen: {new Date(prognose.abgerufen_am).toLocaleString('de-DE')}</span>
        </div>
      </Card>
    </div>
  )
}
