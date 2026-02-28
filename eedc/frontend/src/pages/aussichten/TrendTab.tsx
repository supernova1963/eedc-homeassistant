/**
 * Trend-Tab: Historische Analyse und Degradation
 */
import { useState, useEffect } from 'react'
import { TrendingUp, TrendingDown, Minus, Calendar, Zap, AlertTriangle, Award } from 'lucide-react'
import { Card, LoadingSpinner, Alert } from '../../components/ui'
import { aussichtenApi, TrendAnalyseResponse } from '../../api/aussichten'
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  Cell,
} from 'recharts'

interface Props {
  anlageId: number
}

export default function TrendTab({ anlageId }: Props) {
  const [trend, setTrend] = useState<TrendAnalyseResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [jahre, setJahre] = useState(3)

  useEffect(() => {
    loadTrend()
  }, [anlageId, jahre])

  async function loadTrend() {
    setLoading(true)
    setError(null)
    try {
      const data = await aussichtenApi.getTrendAnalyse(anlageId, jahre)
      setTrend(data)
    } catch (err: any) {
      setError(err.message || 'Fehler beim Laden der Trend-Analyse')
    } finally {
      setLoading(false)
    }
  }

  if (loading) {
    return <LoadingSpinner text="Lade Trend-Analyse..." />
  }

  if (error) {
    return <Alert type="error">{error}</Alert>
  }

  if (!trend) {
    return <Alert type="warning">Keine Trend-Daten verfügbar</Alert>
  }

  // Prüfe ob genügend Daten vorhanden
  const hatDaten = trend.jahres_vergleich.some(j => j.gesamt_kwh > 0)

  if (!hatDaten) {
    return (
      <div className="space-y-6">
        <Card className="p-8 text-center">
          <AlertTriangle className="h-12 w-12 mx-auto text-yellow-500 mb-4" />
          <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-2">
            Noch keine historischen Daten
          </h3>
          <p className="text-gray-500 dark:text-gray-400">
            Für eine Trend-Analyse werden mindestens Daten aus einem Jahr benötigt.
            <br />
            Erfasse Monatsdaten, um Trends zu analysieren.
          </p>
        </Card>
      </div>
    )
  }

  // Chart-Daten
  const jahresChartData = trend.jahres_vergleich.map(j => ({
    jahr: j.jahr.toString(),
    kwh: j.gesamt_kwh,
    spez_ertrag: j.spezifischer_ertrag_kwh_kwp,
    pr: j.performance_ratio ? j.performance_ratio * 100 : null,
  }))

  // Bestes Jahr
  const aktivJahre = trend.jahres_vergleich.filter(j => j.gesamt_kwh > 0)
  const bestesJahr = aktivJahre.length > 0
    ? aktivJahre.reduce((best, j) => j.gesamt_kwh > best.gesamt_kwh ? j : best, aktivJahre[0])
    : null

  // Degradation Info
  const degradation = trend.degradation.geschaetzt_prozent_jahr

  return (
    <div className="space-y-6">
      {/* KPI Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {bestesJahr && (
          <Card className="p-4">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-green-100 dark:bg-green-900/30 rounded-lg">
                <Award className="h-5 w-5 text-green-600 dark:text-green-400" />
              </div>
              <div>
                <p className="text-sm text-gray-500 dark:text-gray-400">Bestes Jahr</p>
                <p className="text-xl font-bold text-gray-900 dark:text-white">
                  {bestesJahr.jahr}
                </p>
                <p className="text-sm text-green-600">
                  {bestesJahr.gesamt_kwh.toLocaleString('de-DE')} kWh
                </p>
              </div>
            </div>
          </Card>
        )}

        <Card className="p-4">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-blue-100 dark:bg-blue-900/30 rounded-lg">
              <Calendar className="h-5 w-5 text-blue-600 dark:text-blue-400" />
            </div>
            <div>
              <p className="text-sm text-gray-500 dark:text-gray-400">Analysezeitraum</p>
              <p className="text-xl font-bold text-gray-900 dark:text-white">
                {trend.analyse_zeitraum.von} - {trend.analyse_zeitraum.bis}
              </p>
            </div>
          </div>
        </Card>

        <Card className="p-4">
          <div className="flex items-center gap-3">
            {degradation !== null ? (
              degradation > 0 ? (
                <div className="p-2 bg-green-100 dark:bg-green-900/30 rounded-lg">
                  <TrendingUp className="h-5 w-5 text-green-600 dark:text-green-400" />
                </div>
              ) : degradation < -1 ? (
                <div className="p-2 bg-red-100 dark:bg-red-900/30 rounded-lg">
                  <TrendingDown className="h-5 w-5 text-red-600 dark:text-red-400" />
                </div>
              ) : (
                <div className="p-2 bg-gray-100 dark:bg-gray-800 rounded-lg">
                  <Minus className="h-5 w-5 text-gray-600 dark:text-gray-400" />
                </div>
              )
            ) : (
              <div className="p-2 bg-gray-100 dark:bg-gray-800 rounded-lg">
                <Minus className="h-5 w-5 text-gray-400" />
              </div>
            )}
            <div>
              <p className="text-sm text-gray-500 dark:text-gray-400">Degradation/Jahr</p>
              <p className="text-xl font-bold text-gray-900 dark:text-white">
                {degradation !== null ? (
                  <span className={degradation > 0 ? 'text-green-600' : degradation < -1 ? 'text-red-600' : ''}>
                    {degradation > 0 ? '+' : ''}{degradation.toFixed(1)}%
                  </span>
                ) : (
                  <span className="text-gray-400">-</span>
                )}
              </p>
            </div>
          </div>
        </Card>

        <Card className="p-4">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-yellow-100 dark:bg-yellow-900/30 rounded-lg">
              <Zap className="h-5 w-5 text-yellow-600 dark:text-yellow-400" />
            </div>
            <div>
              <p className="text-sm text-gray-500 dark:text-gray-400">Anlagenleistung</p>
              <p className="text-xl font-bold text-gray-900 dark:text-white">
                {trend.anlagenleistung_kwp.toFixed(1)} kWp
              </p>
            </div>
          </div>
        </Card>
      </div>

      {/* Jahre-Selector */}
      <Card className="p-4">
        <div className="flex items-center justify-between">
          <h3 className="font-semibold text-gray-900 dark:text-white">Jahresvergleich</h3>
          <select
            value={jahre}
            onChange={(e) => setJahre(Number(e.target.value))}
            className="input w-auto text-sm"
          >
            <option value={2}>2 Jahre</option>
            <option value={3}>3 Jahre</option>
            <option value={5}>5 Jahre</option>
            <option value={10}>10 Jahre</option>
          </select>
        </div>
      </Card>

      {/* Jahresvergleich Chart */}
      <Card className="p-4">
        <h3 className="font-semibold text-gray-900 dark:text-white mb-4">Jahreserträge</h3>
        <div className="h-[300px]">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={jahresChartData}>
              <CartesianGrid strokeDasharray="3 3" className="stroke-gray-200 dark:stroke-gray-700" />
              <XAxis
                dataKey="jahr"
                tick={{ fontSize: 12 }}
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
                formatter={(value: number) => [`${value.toLocaleString('de-DE')} kWh`, 'Ertrag']}
              />
              <Legend />
              <Bar dataKey="kwh" name="Jahresertrag" radius={[4, 4, 0, 0]}>
                {jahresChartData.map((entry, index) => (
                  <Cell
                    key={`cell-${index}`}
                    fill={entry.kwh === bestesJahr?.gesamt_kwh ? '#10b981' : '#eab308'}
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </Card>

      {/* Spezifischer Ertrag Chart */}
      <Card className="p-4">
        <h3 className="font-semibold text-gray-900 dark:text-white mb-4">Spezifischer Ertrag (kWh/kWp)</h3>
        <div className="h-[250px]">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={jahresChartData}>
              <CartesianGrid strokeDasharray="3 3" className="stroke-gray-200 dark:stroke-gray-700" />
              <XAxis
                dataKey="jahr"
                tick={{ fontSize: 12 }}
                className="text-gray-600 dark:text-gray-400"
              />
              <YAxis
                tick={{ fontSize: 12 }}
                className="text-gray-600 dark:text-gray-400"
                domain={['auto', 'auto']}
              />
              <Tooltip
                formatter={(value: number) => [`${value.toFixed(0)} kWh/kWp`, 'Spez. Ertrag']}
              />
              <Legend />
              <Line
                type="monotone"
                dataKey="spez_ertrag"
                name="Spez. Ertrag"
                stroke="#3b82f6"
                strokeWidth={2}
                dot={{ r: 5 }}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </Card>

      {/* Saisonale Muster */}
      <Card className="p-4">
        <h3 className="font-semibold text-gray-900 dark:text-white mb-4">Saisonale Muster</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div>
            <h4 className="text-sm font-medium text-gray-500 dark:text-gray-400 mb-2">
              Beste Monate
            </h4>
            <div className="flex flex-wrap gap-2">
              {trend.saisonale_muster.beste_monate.map((monat, index) => (
                <span
                  key={monat}
                  className={`px-3 py-1 rounded-full text-sm font-medium ${
                    index === 0
                      ? 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400'
                      : 'bg-green-50 text-green-700 dark:bg-green-900/20 dark:text-green-500'
                  }`}
                >
                  {monat}
                </span>
              ))}
            </div>
          </div>
          <div>
            <h4 className="text-sm font-medium text-gray-500 dark:text-gray-400 mb-2">
              Schwächste Monate
            </h4>
            <div className="flex flex-wrap gap-2">
              {trend.saisonale_muster.schlechteste_monate.map((monat, index) => (
                <span
                  key={monat}
                  className={`px-3 py-1 rounded-full text-sm font-medium ${
                    index === 0
                      ? 'bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-400'
                      : 'bg-orange-50 text-orange-700 dark:bg-orange-900/20 dark:text-orange-500'
                  }`}
                >
                  {monat}
                </span>
              ))}
            </div>
          </div>
        </div>
      </Card>

      {/* Degradation Info */}
      <Card className="p-4">
        <div className="flex items-center justify-between mb-3">
          <h3 className="font-semibold text-gray-900 dark:text-white">Degradation</h3>
          {trend.degradation.methode && (
            <span className={`text-xs px-2 py-1 rounded-full ${
              trend.degradation.methode === 'vollstaendig'
                ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
                : 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400'
            }`}>
              {trend.degradation.methode === 'vollstaendig' ? 'Vollständige Jahre' : 'TMY-ergänzt'}
            </span>
          )}
        </div>
        <div className="p-4 bg-gray-50 dark:bg-gray-800 rounded-lg">
          {degradation !== null ? (
            <div className="space-y-2">
              <p className="text-lg font-medium text-gray-900 dark:text-white">
                {degradation > 0 ? (
                  <span className="text-green-600">
                    +{degradation.toFixed(2)}% pro Jahr
                  </span>
                ) : degradation < -1 ? (
                  <span className="text-red-600">
                    {degradation.toFixed(2)}% pro Jahr
                  </span>
                ) : (
                  <span className="text-gray-600">
                    {degradation.toFixed(2)}% pro Jahr
                  </span>
                )}
              </p>
              <p className="text-sm text-gray-500 dark:text-gray-400">
                {trend.degradation.hinweis}
              </p>
              {trend.degradation.methode === 'tmy_ergaenzt' && (
                <p className="text-sm text-blue-600 dark:text-blue-400 mt-2">
                  Unvollständige Jahre wurden mit PVGIS TMY-Prognosewerten ergänzt.
                </p>
              )}
              {degradation < -1 && (
                <p className="text-sm text-yellow-600 dark:text-yellow-400 mt-2">
                  Eine Degradation von mehr als 1% pro Jahr kann auf Probleme hinweisen.
                  Typische Modul-Degradation liegt bei 0.3-0.5% pro Jahr.
                </p>
              )}
            </div>
          ) : (
            <p className="text-gray-500 dark:text-gray-400">
              {trend.degradation.hinweis}
            </p>
          )}
        </div>
      </Card>

      {/* Detail-Tabelle */}
      <Card className="p-4">
        <h3 className="font-semibold text-gray-900 dark:text-white mb-4">Jahresübersicht</h3>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-200 dark:border-gray-700">
                <th className="text-left py-2 px-3">Jahr</th>
                <th className="text-right py-2 px-3">Monate</th>
                <th className="text-right py-2 px-3">Ertrag</th>
                <th className="text-right py-2 px-3">Spez. Ertrag</th>
                <th className="text-right py-2 px-3">Performance-Ratio</th>
              </tr>
            </thead>
            <tbody>
              {trend.jahres_vergleich.map((j) => (
                <tr
                  key={j.jahr}
                  className={`border-b border-gray-100 dark:border-gray-800 ${
                    j.gesamt_kwh === bestesJahr?.gesamt_kwh && j.ist_vollstaendig ? 'bg-green-50 dark:bg-green-900/20' : ''
                  }`}
                >
                  <td className="py-2 px-3 font-medium">
                    {j.jahr}
                    {!j.ist_vollstaendig && j.anzahl_monate > 0 && (
                      <span className="ml-1 text-xs text-orange-500" title="Unvollständiges Jahr">*</span>
                    )}
                  </td>
                  <td className="py-2 px-3 text-right">
                    <span className={j.ist_vollstaendig ? 'text-green-600' : 'text-orange-500'}>
                      {j.anzahl_monate}/12
                    </span>
                  </td>
                  <td className="py-2 px-3 text-right">
                    {j.gesamt_kwh > 0 ? (
                      <span className="font-semibold text-yellow-600">
                        {j.gesamt_kwh.toLocaleString('de-DE')} kWh
                      </span>
                    ) : (
                      <span className="text-gray-400">-</span>
                    )}
                  </td>
                  <td className="py-2 px-3 text-right">
                    {j.spezifischer_ertrag_kwh_kwp > 0 ? (
                      `${j.spezifischer_ertrag_kwh_kwp.toFixed(0)} kWh/kWp`
                    ) : (
                      <span className="text-gray-400">-</span>
                    )}
                  </td>
                  <td className="py-2 px-3 text-right">
                    {j.performance_ratio !== null ? (
                      <span className={
                        j.performance_ratio > 1
                          ? 'text-green-600'
                          : j.performance_ratio < 0.9
                          ? 'text-red-600'
                          : 'text-gray-600'
                      }>
                        {(j.performance_ratio * 100).toFixed(0)}%
                      </span>
                    ) : (
                      <span className="text-gray-400">-</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      {/* Meta-Info */}
      <Card className="p-4 bg-gray-50 dark:bg-gray-800">
        <div className="flex flex-wrap gap-4 text-sm text-gray-500 dark:text-gray-400">
          <span>Datenquellen: {trend.datenquellen.join(', ')}</span>
          <span>Anlagenleistung: {trend.anlagenleistung_kwp.toFixed(1)} kWp</span>
        </div>
      </Card>
    </div>
  )
}
