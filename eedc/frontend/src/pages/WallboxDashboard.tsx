/**
 * Wallbox Dashboard
 * Zeigt Statistiken: Ladevorgänge, Gesamtladung, Durchschnitt pro Ladung
 */

import { useState, useEffect } from 'react'
import { Plug, Zap, Hash, TrendingUp } from 'lucide-react'
import { Card, LoadingSpinner, Alert, Select, KPICard } from '../components/ui'
import { useAnlagen } from '../hooks'
import { investitionenApi } from '../api'
import type { WallboxDashboardResponse } from '../api/investitionen'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  LineChart, Line
} from 'recharts'

const monatNamen = ['', 'Jan', 'Feb', 'Mär', 'Apr', 'Mai', 'Jun', 'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Dez']

export default function WallboxDashboard() {
  const { anlagen, loading: anlagenLoading } = useAnlagen()
  const [selectedAnlageId, setSelectedAnlageId] = useState<number | undefined>()
  const [dashboards, setDashboards] = useState<WallboxDashboardResponse[]>([])
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
        const data = await investitionenApi.getWallboxDashboard(selectedAnlageId)
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
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Wallbox Dashboard</h1>
        <Alert type="warning">Bitte zuerst eine Anlage anlegen.</Alert>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div className="flex items-center gap-3">
          <Plug className="h-8 w-8 text-purple-500" />
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Wallbox Dashboard</h1>
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
        <LoadingSpinner text="Lade Wallbox Daten..." />
      ) : dashboards.length === 0 ? (
        <Card>
          <div className="text-center py-8 text-gray-500 dark:text-gray-400">
            <Plug className="h-12 w-12 mx-auto mb-4 opacity-50" />
            <p>Keine Wallbox für diese Anlage erfasst.</p>
            <p className="text-sm mt-2">Füge eine Wallbox unter "Investitionen" hinzu.</p>
          </div>
        </Card>
      ) : (
        dashboards.map((dashboard) => (
          <WallboxCard key={dashboard.investition.id} dashboard={dashboard} />
        ))
      )}
    </div>
  )
}

function WallboxCard({ dashboard }: { dashboard: WallboxDashboardResponse }) {
  const { investition, monatsdaten, zusammenfassung } = dashboard
  const z = zusammenfassung

  const monthlyData = monatsdaten.map(md => ({
    name: `${monatNamen[md.monat]} ${md.jahr.toString().slice(2)}`,
    ladung: md.verbrauch_daten.ladung_kwh || 0,
    vorgaenge: md.verbrauch_daten.ladevorgaenge || 0,
  }))

  // Leistung aus Parameter
  const params = investition.parameter as Record<string, number> | undefined
  const leistungKw = params?.ladeleistung_kw || 11

  return (
    <Card className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-semibold text-gray-900 dark:text-white">
            {investition.bezeichnung}
          </h2>
          <p className="text-sm text-gray-500 dark:text-gray-400">
            {leistungKw} kW Ladeleistung • {z.anzahl_monate} Monate Daten
          </p>
        </div>
        <Plug className="h-10 w-10 text-purple-500" />
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <KPICard
          title="Ladevorgänge"
          value={z.gesamt_ladevorgaenge.toString()}
          icon={Hash}
          color="purple"
        />
        <KPICard
          title="Gesamtladung"
          value={(z.gesamt_ladung_kwh / 1000).toFixed(1)}
          unit="MWh"
          icon={Zap}
          color="yellow"
        />
        <KPICard
          title="Ø pro Ladung"
          value={z.durchschnitt_kwh_pro_vorgang.toFixed(1)}
          unit="kWh"
          icon={TrendingUp}
          color="blue"
        />
        <KPICard
          title="Ø Vorgänge/Monat"
          value={z.ladevorgaenge_pro_monat.toFixed(1)}
          icon={Hash}
          color="green"
        />
      </div>

      {/* Charts */}
      <div className="grid md:grid-cols-2 gap-6">
        {/* Ladung pro Monat */}
        <div>
          <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-4">
            Ladung pro Monat (kWh)
          </h3>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={monthlyData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="name" fontSize={10} />
                <YAxis />
                <Tooltip />
                <Bar dataKey="ladung" fill="#8b5cf6" name="Ladung (kWh)" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Ladevorgänge pro Monat */}
        <div>
          <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-4">
            Ladevorgänge pro Monat
          </h3>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={monthlyData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="name" fontSize={10} />
                <YAxis />
                <Tooltip />
                <Line type="monotone" dataKey="vorgaenge" stroke="#22c55e" strokeWidth={2} dot={{ r: 4 }} name="Ladevorgänge" />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      {/* Info */}
      <div className="bg-purple-50 dark:bg-purple-900/20 rounded-lg p-4">
        <p className="text-sm text-purple-600 dark:text-purple-400">
          Die Wallbox ist primär ein Enabler für die E-Auto-Ladung.
          Die Ersparnis wird im E-Auto Dashboard berechnet.
        </p>
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
                <th className="text-right py-2 px-2">Ladung (kWh)</th>
                <th className="text-right py-2 px-2">Ladevorgänge</th>
                <th className="text-right py-2 px-2">Ø kWh/Ladung</th>
              </tr>
            </thead>
            <tbody>
              {monthlyData.map((md, idx) => (
                <tr key={idx} className="border-b border-gray-100 dark:border-gray-800">
                  <td className="py-2 px-2">{md.name}</td>
                  <td className="text-right py-2 px-2 text-purple-600">{md.ladung.toFixed(1)}</td>
                  <td className="text-right py-2 px-2">{md.vorgaenge}</td>
                  <td className="text-right py-2 px-2">{md.vorgaenge > 0 ? (md.ladung / md.vorgaenge).toFixed(1) : '-'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </Card>
  )
}
