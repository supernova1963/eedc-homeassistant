/**
 * Wärmepumpe Dashboard
 * Zeigt Statistiken: COP, Stromverbrauch, Heizenergie, Ersparnis vs. Gas/Öl
 */

import { useState, useEffect } from 'react'
import { Flame, Zap, Leaf, TrendingUp, Thermometer } from 'lucide-react'
import { Card, LoadingSpinner, Alert, Select, KPICard } from '../components/ui'
import { useAnlagen } from '../hooks'
import { investitionenApi } from '../api'
import type { WaermepumpeDashboardResponse } from '../api/investitionen'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
  PieChart, Pie, Cell, AreaChart, Area
} from 'recharts'

const monatNamen = ['', 'Jan', 'Feb', 'Mär', 'Apr', 'Mai', 'Jun', 'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Dez']

export default function WaermepumpeDashboard() {
  const { anlagen, loading: anlagenLoading } = useAnlagen()
  const [selectedAnlageId, setSelectedAnlageId] = useState<number | undefined>()
  const [dashboards, setDashboards] = useState<WaermepumpeDashboardResponse[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (anlagen.length > 0 && !selectedAnlageId) {
      setSelectedAnlageId(anlagen[0].id)
    }
  }, [anlagen, selectedAnlageId])

  useEffect(() => {
    if (!selectedAnlageId) return

    const loadDashboard = async () => {
      setLoading(true)
      setError(null)
      try {
        const data = await investitionenApi.getWaermepumpeDashboard(selectedAnlageId)
        setDashboards(data)
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Fehler beim Laden')
      } finally {
        setLoading(false)
      }
    }

    loadDashboard()
  }, [selectedAnlageId])

  if (anlagenLoading) return <LoadingSpinner text="Lade..." />

  if (anlagen.length === 0) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Wärmepumpe Dashboard</h1>
        <Alert type="warning">Bitte zuerst eine Anlage anlegen.</Alert>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div className="flex items-center gap-3">
          <Flame className="h-8 w-8 text-orange-500" />
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Wärmepumpe Dashboard</h1>
        </div>
        {anlagen.length > 1 && (
          <Select
            value={selectedAnlageId?.toString() || ''}
            onChange={(e) => setSelectedAnlageId(parseInt(e.target.value))}
            options={anlagen.map(a => ({ value: a.id.toString(), label: a.anlagenname }))}
          />
        )}
      </div>

      {error && <Alert type="error">{error}</Alert>}

      {loading ? (
        <LoadingSpinner text="Lade Wärmepumpe Daten..." />
      ) : dashboards.length === 0 ? (
        <Card>
          <div className="text-center py-8 text-gray-500 dark:text-gray-400">
            <Flame className="h-12 w-12 mx-auto mb-4 opacity-50" />
            <p>Keine Wärmepumpe für diese Anlage erfasst.</p>
            <p className="text-sm mt-2">Füge eine Wärmepumpe unter "Investitionen" hinzu.</p>
          </div>
        </Card>
      ) : (
        dashboards.map((dashboard) => (
          <WaermepumpeCard key={dashboard.investition.id} dashboard={dashboard} />
        ))
      )}
    </div>
  )
}

function WaermepumpeCard({ dashboard }: { dashboard: WaermepumpeDashboardResponse }) {
  const { investition, monatsdaten, zusammenfassung } = dashboard
  const z = zusammenfassung

  const monthlyData = monatsdaten.map(md => ({
    name: `${monatNamen[md.monat]} ${md.jahr.toString().slice(2)}`,
    strom: md.verbrauch_daten.stromverbrauch_kwh || 0,
    heizung: md.verbrauch_daten.heizenergie_kwh || 0,
    warmwasser: md.verbrauch_daten.warmwasser_kwh || 0,
    cop: ((md.verbrauch_daten.heizenergie_kwh || 0) + (md.verbrauch_daten.warmwasser_kwh || 0)) /
         (md.verbrauch_daten.stromverbrauch_kwh || 1),
  }))

  const waermePieData = [
    { name: 'Heizung', value: z.gesamt_heizenergie_kwh },
    { name: 'Warmwasser', value: z.gesamt_warmwasser_kwh },
  ]

  const kostenVergleichData = [
    { name: 'Wärmepumpe', value: z.wp_kosten_euro, fill: '#22c55e' },
    { name: 'Gas/Öl', value: z.alte_heizung_kosten_euro, fill: '#ef4444' },
  ]

  return (
    <Card className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-semibold text-gray-900 dark:text-white">
            {investition.bezeichnung}
          </h2>
          <p className="text-sm text-gray-500 dark:text-gray-400">
            {z.anzahl_monate} Monate Daten
          </p>
        </div>
        <Flame className="h-10 w-10 text-orange-500" />
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <KPICard
          title="Ø COP"
          value={z.durchschnitt_cop.toFixed(2)}
          icon={Thermometer}
          color="orange"
        />
        <KPICard
          title="Wärme erzeugt"
          value={(z.gesamt_waerme_kwh / 1000).toFixed(1)}
          unit="MWh"
          icon={Flame}
          color="red"
        />
        <KPICard
          title="Strom verbraucht"
          value={(z.gesamt_stromverbrauch_kwh / 1000).toFixed(1)}
          unit="MWh"
          icon={Zap}
          color="yellow"
        />
        <KPICard
          title="Ersparnis"
          value={z.ersparnis_euro.toFixed(0)}
          unit="€"
          icon={TrendingUp}
          color="green"
          trend={z.ersparnis_euro > 0 ? 'up' : undefined}
        />
      </div>

      {/* Charts Row 1 */}
      <div className="grid md:grid-cols-2 gap-6">
        {/* Wärme-Verteilung */}
        <div>
          <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-4">
            Wärme-Verteilung
          </h3>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={waermePieData}
                  cx="50%"
                  cy="50%"
                  innerRadius={60}
                  outerRadius={80}
                  paddingAngle={5}
                  dataKey="value"
                  label={({ name, percent }) => `${name}: ${(percent * 100).toFixed(0)}%`}
                >
                  <Cell fill="#ef4444" />
                  <Cell fill="#3b82f6" />
                </Pie>
                <Tooltip formatter={(v: number) => `${v.toFixed(0)} kWh`} />
              </PieChart>
            </ResponsiveContainer>
          </div>
          <div className="flex justify-center gap-6 text-sm">
            <span className="flex items-center gap-2">
              <span className="w-3 h-3 rounded-full bg-red-500"></span>
              Heizung: {z.gesamt_heizenergie_kwh.toFixed(0)} kWh
            </span>
            <span className="flex items-center gap-2">
              <span className="w-3 h-3 rounded-full bg-blue-500"></span>
              Warmwasser: {z.gesamt_warmwasser_kwh.toFixed(0)} kWh
            </span>
          </div>
        </div>

        {/* Kostenvergleich */}
        <div>
          <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-4">
            Kostenvergleich WP vs. Gas/Öl
          </h3>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={kostenVergleichData} layout="vertical">
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis type="number" tickFormatter={(v) => `${v}€`} />
                <YAxis type="category" dataKey="name" width={100} />
                <Tooltip formatter={(v: number) => `${v.toFixed(2)} €`} />
                <Bar dataKey="value" />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <div className="text-center mt-2">
            <span className="text-lg font-semibold text-green-600 dark:text-green-400">
              Ersparnis: {z.ersparnis_euro.toFixed(2)} €
            </span>
          </div>
        </div>
      </div>

      {/* Charts Row 2 */}
      <div className="grid md:grid-cols-2 gap-6">
        {/* Wärme pro Monat */}
        <div>
          <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-4">
            Wärmeerzeugung pro Monat (kWh)
          </h3>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={monthlyData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="name" fontSize={10} />
                <YAxis />
                <Tooltip />
                <Legend />
                <Area type="monotone" dataKey="heizung" stackId="1" fill="#ef4444" stroke="#dc2626" name="Heizung" />
                <Area type="monotone" dataKey="warmwasser" stackId="1" fill="#3b82f6" stroke="#2563eb" name="Warmwasser" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* COP pro Monat */}
        <div>
          <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-4">
            COP pro Monat
          </h3>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={monthlyData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="name" fontSize={10} />
                <YAxis domain={[0, 6]} />
                <Tooltip formatter={(v: number) => v.toFixed(2)} />
                <Bar dataKey="cop" fill="#f59e0b" name="COP" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      {/* CO2 Info */}
      <div className="bg-green-50 dark:bg-green-900/20 rounded-lg p-4 flex items-center gap-4">
        <Leaf className="h-8 w-8 text-green-500" />
        <div>
          <p className="text-sm text-green-600 dark:text-green-400">CO₂ Ersparnis gegenüber fossiler Heizung</p>
          <p className="text-2xl font-bold text-green-700 dark:text-green-300">
            {z.co2_ersparnis_kg.toFixed(0)} kg
          </p>
        </div>
      </div>

      {/* Detail-Tabelle */}
      <details className="border-t border-gray-200 dark:border-gray-700 pt-4">
        <summary className="cursor-pointer text-sm text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white">
          Monatsdaten anzeigen
        </summary>
        <div className="mt-4 overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead>
              <tr className="border-b border-gray-200 dark:border-gray-700">
                <th className="text-left py-2 px-2">Monat</th>
                <th className="text-right py-2 px-2">Strom</th>
                <th className="text-right py-2 px-2">Heizung</th>
                <th className="text-right py-2 px-2">Warmwasser</th>
                <th className="text-right py-2 px-2">COP</th>
              </tr>
            </thead>
            <tbody>
              {monatsdaten.map((md) => {
                const strom = md.verbrauch_daten.stromverbrauch_kwh || 0
                const heiz = md.verbrauch_daten.heizenergie_kwh || 0
                const ww = md.verbrauch_daten.warmwasser_kwh || 0
                const cop = strom > 0 ? (heiz + ww) / strom : 0
                return (
                  <tr key={md.id} className="border-b border-gray-100 dark:border-gray-800">
                    <td className="py-2 px-2">{monatNamen[md.monat]} {md.jahr}</td>
                    <td className="text-right py-2 px-2">{strom.toFixed(0)}</td>
                    <td className="text-right py-2 px-2 text-red-600">{heiz.toFixed(0)}</td>
                    <td className="text-right py-2 px-2 text-blue-600">{ww.toFixed(0)}</td>
                    <td className="text-right py-2 px-2 text-orange-600">{cop.toFixed(2)}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </details>
    </Card>
  )
}
