/**
 * Langfrist-Tab: Monatsprognosen basierend auf PVGIS und Trends
 */
import { useState, useEffect } from 'react'
import { TrendingUp, TrendingDown, Minus, Calendar, Zap, Info } from 'lucide-react'
import { Card, LoadingSpinner, Alert } from '../../components/ui'
import { aussichtenApi, LangfristPrognose } from '../../api/aussichten'
import {
  ResponsiveContainer,
  ComposedChart,
  Bar,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
} from 'recharts'

interface Props {
  anlageId: number
}

function TrendIcon({ richtung }: { richtung: string }) {
  switch (richtung) {
    case 'positiv':
      return <TrendingUp className="h-5 w-5 text-green-500" />
    case 'negativ':
      return <TrendingDown className="h-5 w-5 text-red-500" />
    default:
      return <Minus className="h-5 w-5 text-gray-400" />
  }
}

export default function LangfristTab({ anlageId }: Props) {
  const [prognose, setPrognose] = useState<LangfristPrognose | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [monate, setMonate] = useState(12)
  const [showKonfidenz, setShowKonfidenz] = useState(true)

  useEffect(() => {
    loadPrognose()
  }, [anlageId, monate])

  async function loadPrognose() {
    setLoading(true)
    setError(null)
    try {
      const data = await aussichtenApi.getLangfristPrognose(anlageId, monate)
      setPrognose(data)
    } catch (err: any) {
      setError(err.message || 'Fehler beim Laden der Prognose')
    } finally {
      setLoading(false)
    }
  }

  if (loading) {
    return <LoadingSpinner text="Lade Langfrist-Prognose..." />
  }

  if (error) {
    return <Alert type="error">{error}</Alert>
  }

  if (!prognose) {
    return <Alert type="warning">Keine Prognose verfügbar</Alert>
  }

  // Chart-Daten vorbereiten
  const chartData = prognose.monatswerte.map(m => ({
    name: `${m.monat_name.substring(0, 3)} ${m.jahr}`,
    monat_name: m.monat_name,
    jahr: m.jahr,
    pvgis: m.pvgis_prognose_kwh,
    trend: m.trend_korrigiert_kwh,
    min: m.konfidenz_min_kwh,
    max: m.konfidenz_max_kwh,
    konfidenz: [m.konfidenz_min_kwh, m.konfidenz_max_kwh],
    pr: m.historische_performance_ratio,
  }))

  const trendAnalyse = prognose.trend_analyse
  const prString = (trendAnalyse.durchschnittliche_performance_ratio * 100).toFixed(0) + '%'

  return (
    <div className="space-y-6">
      {/* KPI Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Card className="p-4">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-yellow-100 dark:bg-yellow-900/30 rounded-lg">
              <Zap className="h-5 w-5 text-yellow-600 dark:text-yellow-400" />
            </div>
            <div>
              <p className="text-sm text-gray-500 dark:text-gray-400">Jahresprognose</p>
              <p className="text-xl font-bold text-gray-900 dark:text-white">
                {prognose.jahresprognose_kwh.toLocaleString('de-DE')} kWh
              </p>
            </div>
          </div>
        </Card>

        <Card className="p-4">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-blue-100 dark:bg-blue-900/30 rounded-lg">
              <Calendar className="h-5 w-5 text-blue-600 dark:text-blue-400" />
            </div>
            <div>
              <p className="text-sm text-gray-500 dark:text-gray-400">Zeitraum</p>
              <p className="text-xl font-bold text-gray-900 dark:text-white">
                {monate} Monate
              </p>
            </div>
          </div>
        </Card>

        <Card className="p-4">
          <div className="flex items-center gap-3">
            <TrendIcon richtung={trendAnalyse.trend_richtung} />
            <div>
              <p className="text-sm text-gray-500 dark:text-gray-400">Performance-Ratio</p>
              <p className="text-xl font-bold text-gray-900 dark:text-white">
                {prString}
              </p>
            </div>
          </div>
        </Card>

        <Card className="p-4">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-gray-100 dark:bg-gray-800 rounded-lg">
              <Info className="h-5 w-5 text-gray-600 dark:text-gray-400" />
            </div>
            <div>
              <p className="text-sm text-gray-500 dark:text-gray-400">Datenbasis</p>
              <p className="text-xl font-bold text-gray-900 dark:text-white">
                {trendAnalyse.datenbasis_monate} Monate
              </p>
            </div>
          </div>
        </Card>
      </div>

      {/* Controls */}
      <Card className="p-4">
        <div className="flex items-center justify-between">
          <h3 className="font-semibold text-gray-900 dark:text-white">Monatsprognose</h3>
          <div className="flex items-center gap-4">
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={showKonfidenz}
                onChange={(e) => setShowKonfidenz(e.target.checked)}
                className="rounded border-gray-300"
              />
              <span className="text-gray-600 dark:text-gray-400">Konfidenzband</span>
            </label>
            <select
              value={monate}
              onChange={(e) => setMonate(Number(e.target.value))}
              className="input w-auto text-sm"
            >
              <option value={6}>6 Monate</option>
              <option value={12}>12 Monate</option>
              <option value={24}>24 Monate</option>
            </select>
          </div>
        </div>
      </Card>

      {/* Chart */}
      <Card className="p-4">
        <div className="h-[350px]">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" className="stroke-gray-200 dark:stroke-gray-700" />
              <XAxis
                dataKey="name"
                tick={{ fontSize: 11 }}
                angle={-45}
                textAnchor="end"
                height={60}
                className="text-gray-600 dark:text-gray-400"
              />
              <YAxis
                tick={{ fontSize: 12 }}
                className="text-gray-600 dark:text-gray-400"
                label={{ value: 'kWh', angle: -90, position: 'insideLeft' }}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: 'var(--tooltip-bg, white)',
                  borderColor: 'var(--tooltip-border, #e5e7eb)',
                }}
                formatter={(value: number | number[], name: string) => {
                  if (name === 'trend') return [`${(value as number).toFixed(0)} kWh`, 'Trend-korrigiert']
                  if (name === 'pvgis') return [`${(value as number).toFixed(0)} kWh`, 'PVGIS-Prognose']
                  if (name === 'konfidenz' && Array.isArray(value)) return [`${value[0].toFixed(0)} - ${value[1].toFixed(0)} kWh`, 'Konfidenzband']
                  return [value, name]
                }}
              />
              <Legend />

              {/* Konfidenzband */}
              {showKonfidenz && (
                <Area
                  type="monotone"
                  dataKey="konfidenz"
                  name="Konfidenzband"
                  fill="#3b82f6"
                  fillOpacity={0.1}
                  stroke="none"
                />
              )}

              {/* PVGIS-Prognose (Basislinie) */}
              <Bar
                dataKey="pvgis"
                name="PVGIS-Prognose"
                fill="#9ca3af"
                fillOpacity={0.5}
                radius={[4, 4, 0, 0]}
              />

              {/* Trend-korrigierte Prognose */}
              <Bar
                dataKey="trend"
                name="Trend-korrigiert"
                fill="#eab308"
                radius={[4, 4, 0, 0]}
              />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      </Card>

      {/* Trend-Info */}
      <Card className="p-4">
        <h3 className="font-semibold text-gray-900 dark:text-white mb-3">Trend-Analyse</h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="flex items-center gap-3 p-3 bg-gray-50 dark:bg-gray-800 rounded-lg">
            <TrendIcon richtung={trendAnalyse.trend_richtung} />
            <div>
              <p className="text-sm text-gray-500 dark:text-gray-400">Trend</p>
              <p className="font-medium text-gray-900 dark:text-white capitalize">
                {trendAnalyse.trend_richtung}
              </p>
            </div>
          </div>
          <div className="p-3 bg-gray-50 dark:bg-gray-800 rounded-lg">
            <p className="text-sm text-gray-500 dark:text-gray-400">Performance-Ratio</p>
            <p className="font-medium text-gray-900 dark:text-white">
              {prString}
              <span className="text-sm text-gray-500 ml-2">
                (IST / SOLL)
              </span>
            </p>
          </div>
          <div className="p-3 bg-gray-50 dark:bg-gray-800 rounded-lg">
            <p className="text-sm text-gray-500 dark:text-gray-400">Datenquellen</p>
            <p className="font-medium text-gray-900 dark:text-white">
              {prognose.datenquellen.join(', ')}
            </p>
          </div>
        </div>
      </Card>

      {/* Detail-Tabelle */}
      <Card className="p-4">
        <h3 className="font-semibold text-gray-900 dark:text-white mb-4">Monatswerte</h3>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-200 dark:border-gray-700">
                <th className="text-left py-2 px-3">Monat</th>
                <th className="text-right py-2 px-3">PVGIS</th>
                <th className="text-right py-2 px-3">Trend-korrigiert</th>
                <th className="text-right py-2 px-3">Min</th>
                <th className="text-right py-2 px-3">Max</th>
                <th className="text-right py-2 px-3">Hist. PR</th>
              </tr>
            </thead>
            <tbody>
              {prognose.monatswerte.map((m) => (
                <tr
                  key={`${m.jahr}-${m.monat}`}
                  className="border-b border-gray-100 dark:border-gray-800"
                >
                  <td className="py-2 px-3 font-medium">
                    {m.monat_name} {m.jahr}
                  </td>
                  <td className="py-2 px-3 text-right text-gray-500">
                    {m.pvgis_prognose_kwh.toFixed(0)} kWh
                  </td>
                  <td className="py-2 px-3 text-right font-semibold text-yellow-600">
                    {m.trend_korrigiert_kwh.toFixed(0)} kWh
                  </td>
                  <td className="py-2 px-3 text-right text-gray-400">
                    {m.konfidenz_min_kwh.toFixed(0)} kWh
                  </td>
                  <td className="py-2 px-3 text-right text-gray-400">
                    {m.konfidenz_max_kwh.toFixed(0)} kWh
                  </td>
                  <td className="py-2 px-3 text-right">
                    {m.historische_performance_ratio !== null ? (
                      <span className={
                        m.historische_performance_ratio > 1
                          ? 'text-green-600'
                          : m.historische_performance_ratio < 0.9
                          ? 'text-red-600'
                          : 'text-gray-600'
                      }>
                        {(m.historische_performance_ratio * 100).toFixed(0)}%
                      </span>
                    ) : (
                      <span className="text-gray-400">-</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr className="border-t-2 border-gray-300 dark:border-gray-600 font-semibold">
                <td className="py-2 px-3">Gesamt</td>
                <td className="py-2 px-3 text-right text-gray-500">
                  {prognose.monatswerte.reduce((s, m) => s + m.pvgis_prognose_kwh, 0).toFixed(0)} kWh
                </td>
                <td className="py-2 px-3 text-right text-yellow-600">
                  {prognose.jahresprognose_kwh.toLocaleString('de-DE')} kWh
                </td>
                <td colSpan={3}></td>
              </tr>
            </tfoot>
          </table>
        </div>
      </Card>

      {/* Meta-Info */}
      <Card className="p-4 bg-gray-50 dark:bg-gray-800">
        <div className="flex flex-wrap gap-4 text-sm text-gray-500 dark:text-gray-400">
          <span>Anlagenleistung: {prognose.anlagenleistung_kwp.toFixed(1)} kWp</span>
          <span>Spez. Ertrag: {(prognose.jahresprognose_kwh / prognose.anlagenleistung_kwp).toFixed(0)} kWh/kWp</span>
          <span>
            Zeitraum: {prognose.prognose_zeitraum.von} bis {prognose.prognose_zeitraum.bis}
          </span>
        </div>
      </Card>
    </div>
  )
}
