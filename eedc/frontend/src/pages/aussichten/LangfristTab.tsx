/**
 * Langfrist-Tab: Monatsprognosen basierend auf PVGIS und Trends
 */
import { useState, useEffect } from 'react'
import { TrendingUp, TrendingDown, Minus, Calendar, Zap, Info } from 'lucide-react'
import { Card, LoadingSpinner, Alert, KPICard, ChartLegende } from '../../components/ui'
import ChartTooltip from '../../components/ui/ChartTooltip'
import { aussichtenApi, LangfristPrognose } from '../../api/aussichten'
import { CHART_COLORS, SOLL_IST_COLORS, PROGNOSE_DASH, achsenEinheit, achsenTick, ACHSEN_MARGIN_TOP } from '../../lib'
import { useChartTheme } from '../../context/ThemeContext'
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

function TrendIcon({ richtung, className = 'h-5 w-5' }: { richtung: string; className?: string }) {
  switch (richtung) {
    case 'positiv':
      return <TrendingUp className={`${className} text-green-500`} />
    case 'negativ':
      return <TrendingDown className={`${className} text-red-500`} />
    default:
      return <Minus className={`${className} text-gray-400 dark:text-gray-500`} />
  }
}

export default function LangfristTab({ anlageId }: Props) {
  const [prognose, setPrognose] = useState<LangfristPrognose | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [monate, setMonate] = useState(12)
  const [showKonfidenz, setShowKonfidenz] = useState(true)
  const achsen = useChartTheme()

  useEffect(() => {
    loadPrognose()
  }, [anlageId, monate])

  async function loadPrognose() {
    setLoading(true)
    setError(null)
    try {
      const data = await aussichtenApi.getLangfristPrognose(anlageId, monate)
      setPrognose(data)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Fehler beim Laden der Prognose')
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
      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3 sm:gap-4">
        <KPICard
          title="Jahresprognose"
          value={prognose.jahresprognose_kwh.toLocaleString('de-DE')}
          unit="kWh"
          color="yellow"
          icon={Zap}
        />

        <KPICard
          title="Zeitraum"
          value={`${monate} Monate`}
          color="blue"
          icon={Calendar}
        />

        <KPICard
          title="Performance-Ratio"
          value={prString}
          color={trendAnalyse.trend_richtung === 'positiv' ? 'green' : trendAnalyse.trend_richtung === 'negativ' ? 'red' : 'gray'}
          icon={(p) => <TrendIcon richtung={trendAnalyse.trend_richtung} {...p} />}
        />

        <KPICard
          title="Datenbasis"
          value={`${trendAnalyse.datenbasis_monate} Monate`}
          color="gray"
          icon={Info}
        />
      </div>

      {/* Controls */}
      <Card className="p-4">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
          <h3 className="font-semibold text-gray-900 dark:text-white">Monatsprognose</h3>
          <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
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
            <ComposedChart data={chartData} margin={{ top: ACHSEN_MARGIN_TOP }}>
              <CartesianGrid strokeDasharray="3 3" className="stroke-gray-200 dark:stroke-gray-700" />
              <XAxis
                dataKey="name"
                tick={{ fontSize: 10 }}
                angle={-45}
                textAnchor="end"
                height={60}
                className="text-gray-600 dark:text-gray-400"
                /* achsen-allow: Zeit-/Kategorie-Achse */
              />
              <YAxis
                tick={{ fontSize: 10 }}
                tickFormatter={achsenTick}
                className="text-gray-600 dark:text-gray-400"
                label={achsenEinheit('kWh')}
              />
              <Tooltip content={<ChartTooltip formatter={(value: number, name: string) => {
                  if (name === 'Konfidenzband') return null
                  return `${value.toFixed(0)} kWh`
                }} />} />
              <Legend content={<ChartLegende />} />

              {/* Konfidenzband */}
              {showKonfidenz && (
                <Area
                  type="monotone"
                  dataKey="konfidenz"
                  name="Konfidenzband"
                  fill={SOLL_IST_COLORS.soll}
                  fillOpacity={0.1}
                  stroke="none"
                />
              )}

              {/* PVGIS-Prognose (Basislinie) */}
              <Bar
                dataKey="pvgis"
                name="PVGIS-Prognose"
                fill={achsen.referenz}
                stroke={achsen.referenz}
                strokeWidth={1}
                strokeDasharray={PROGNOSE_DASH}
                radius={[2, 2, 0, 0]}
              />

              {/* Trend-korrigierte Prognose */}
              <Bar
                dataKey="trend"
                name="Trend-korrigiert"
                fill={CHART_COLORS.erzeugung}
                radius={[2, 2, 0, 0]}
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
                  <td className="py-2 px-3 text-right text-gray-400 dark:text-gray-500">
                    {m.konfidenz_min_kwh.toFixed(0)} kWh
                  </td>
                  <td className="py-2 px-3 text-right text-gray-400 dark:text-gray-500">
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
                        {(m.historische_performance_ratio * 100).toFixed(0)} %
                      </span>
                    ) : (
                      <span className="text-gray-400 dark:text-gray-500">-</span>
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
