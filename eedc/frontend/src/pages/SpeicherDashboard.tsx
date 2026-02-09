/**
 * Speicher Dashboard
 * Zeigt Statistiken: Zyklen, Effizienz, Ladung/Entladung, Eigenverbrauchserhöhung
 */

import { useState, useEffect } from 'react'
import { Battery, Zap, TrendingUp, Activity, RotateCw } from 'lucide-react'
import { Card, LoadingSpinner, Alert, Select, KPICard } from '../components/ui'
import { useAnlagen } from '../hooks'
import { investitionenApi } from '../api'
import type { SpeicherDashboardResponse } from '../api/investitionen'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
  AreaChart, Area, LineChart, Line
} from 'recharts'

const monatNamen = ['', 'Jan', 'Feb', 'Mär', 'Apr', 'Mai', 'Jun', 'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Dez']

export default function SpeicherDashboard() {
  const { anlagen, loading: anlagenLoading } = useAnlagen()
  const [selectedAnlageId, setSelectedAnlageId] = useState<number | undefined>()
  const [dashboards, setDashboards] = useState<SpeicherDashboardResponse[]>([])
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
        const data = await investitionenApi.getSpeicherDashboard(selectedAnlageId)
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
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Speicher Dashboard</h1>
        <Alert type="warning">Bitte zuerst eine Anlage anlegen.</Alert>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div className="flex items-center gap-3">
          <Battery className="h-8 w-8 text-green-500" />
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Speicher Dashboard</h1>
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
        <LoadingSpinner text="Lade Speicher Daten..." />
      ) : dashboards.length === 0 ? (
        <Card>
          <div className="text-center py-8 text-gray-500 dark:text-gray-400">
            <Battery className="h-12 w-12 mx-auto mb-4 opacity-50" />
            <p>Kein Speicher für diese Anlage erfasst.</p>
            <p className="text-sm mt-2">Füge einen Speicher unter "Investitionen" hinzu.</p>
          </div>
        </Card>
      ) : (
        dashboards.map((dashboard) => (
          <SpeicherCard key={dashboard.investition.id} dashboard={dashboard} />
        ))
      )}
    </div>
  )
}

function SpeicherCard({ dashboard }: { dashboard: SpeicherDashboardResponse }) {
  const { investition, monatsdaten, zusammenfassung } = dashboard
  const z = zusammenfassung

  const monthlyData = monatsdaten.map(md => {
    const ladung = md.verbrauch_daten.ladung_kwh || 0
    const entladung = md.verbrauch_daten.entladung_kwh || 0
    return {
      name: `${monatNamen[md.monat]} ${md.jahr.toString().slice(2)}`,
      ladung,
      entladung,
      zyklen: z.kapazitaet_kwh > 0 ? ladung / z.kapazitaet_kwh : 0,
      effizienz: ladung > 0 ? (entladung / ladung) * 100 : 0,
    }
  })

  return (
    <Card className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-semibold text-gray-900 dark:text-white">
            {investition.bezeichnung}
          </h2>
          <p className="text-sm text-gray-500 dark:text-gray-400">
            {z.kapazitaet_kwh} kWh Kapazität • {z.anzahl_monate} Monate Daten
          </p>
        </div>
        <Battery className="h-10 w-10 text-green-500" />
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <KPICard
          title="Vollzyklen"
          value={z.vollzyklen.toFixed(0)}
          icon={RotateCw}
          color="blue"
          formel="Vollzyklen = Ladung ÷ Kapazität"
          berechnung={`${z.gesamt_ladung_kwh.toFixed(0)} kWh ÷ ${z.kapazitaet_kwh} kWh`}
          ergebnis={`= ${z.vollzyklen.toFixed(1)} Zyklen`}
        />
        <KPICard
          title="Effizienz"
          value={z.effizienz_prozent.toFixed(1)}
          unit="%"
          icon={Activity}
          color="green"
          formel="Effizienz = Entladung ÷ Ladung × 100"
          berechnung={`${z.gesamt_entladung_kwh.toFixed(0)} kWh ÷ ${z.gesamt_ladung_kwh.toFixed(0)} kWh × 100`}
          ergebnis={`= ${z.effizienz_prozent.toFixed(1)} %`}
        />
        <KPICard
          title="Durchsatz"
          value={(z.gesamt_entladung_kwh / 1000).toFixed(1)}
          unit="MWh"
          icon={Zap}
          color="yellow"
          formel="Durchsatz = Σ Entladung"
          berechnung={`${z.gesamt_entladung_kwh.toFixed(0)} kWh`}
          ergebnis={`= ${(z.gesamt_entladung_kwh / 1000).toFixed(2)} MWh`}
        />
        <KPICard
          title="Ersparnis"
          value={z.ersparnis_euro.toFixed(0)}
          unit="€"
          icon={TrendingUp}
          color="green"
          trend={z.ersparnis_euro > 0 ? 'up' : undefined}
          formel="Ersparnis = Entladung × Strompreis"
          berechnung={`${z.gesamt_entladung_kwh.toFixed(0)} kWh × Strompreis`}
          ergebnis={`= ${z.ersparnis_euro.toFixed(2)} €`}
        />
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="bg-blue-50 dark:bg-blue-900/20 rounded-lg p-4">
          <p className="text-sm text-blue-600 dark:text-blue-400">Ladung gesamt</p>
          <p className="text-2xl font-bold text-blue-700 dark:text-blue-300">
            {z.gesamt_ladung_kwh.toFixed(0)} kWh
          </p>
        </div>
        <div className="bg-green-50 dark:bg-green-900/20 rounded-lg p-4">
          <p className="text-sm text-green-600 dark:text-green-400">Entladung gesamt</p>
          <p className="text-2xl font-bold text-green-700 dark:text-green-300">
            {z.gesamt_entladung_kwh.toFixed(0)} kWh
          </p>
        </div>
        <div className="bg-purple-50 dark:bg-purple-900/20 rounded-lg p-4">
          <p className="text-sm text-purple-600 dark:text-purple-400">Zyklen/Monat</p>
          <p className="text-2xl font-bold text-purple-700 dark:text-purple-300">
            {z.zyklen_pro_monat.toFixed(1)}
          </p>
        </div>
        <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-4">
          <p className="text-sm text-gray-600 dark:text-gray-400">Verlust</p>
          <p className="text-2xl font-bold text-gray-700 dark:text-gray-300">
            {(z.gesamt_ladung_kwh - z.gesamt_entladung_kwh).toFixed(0)} kWh
          </p>
        </div>
      </div>

      {/* Charts */}
      <div className="grid md:grid-cols-2 gap-6">
        {/* Ladung/Entladung pro Monat */}
        <div>
          <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-4">
            Ladung & Entladung pro Monat (kWh)
          </h3>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={monthlyData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="name" fontSize={10} />
                <YAxis />
                <Tooltip />
                <Legend />
                <Bar dataKey="ladung" fill="#3b82f6" name="Ladung" />
                <Bar dataKey="entladung" fill="#22c55e" name="Entladung" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Zyklen pro Monat */}
        <div>
          <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-4">
            Vollzyklen pro Monat
          </h3>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={monthlyData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="name" fontSize={10} />
                <YAxis />
                <Tooltip formatter={(v: number) => v.toFixed(1)} />
                <Area type="monotone" dataKey="zyklen" fill="#8b5cf6" stroke="#7c3aed" name="Zyklen" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      {/* Effizienz Chart */}
      <div>
        <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-4">
          Effizienz pro Monat (%)
        </h3>
        <div className="h-48">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={monthlyData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="name" fontSize={10} />
              <YAxis domain={[80, 100]} />
              <Tooltip formatter={(v: number) => `${v.toFixed(1)}%`} />
              <Line type="monotone" dataKey="effizienz" stroke="#22c55e" strokeWidth={2} dot={{ r: 4 }} name="Effizienz" />
            </LineChart>
          </ResponsiveContainer>
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
                <th className="text-right py-2 px-2">Ladung</th>
                <th className="text-right py-2 px-2">Entladung</th>
                <th className="text-right py-2 px-2">Zyklen</th>
                <th className="text-right py-2 px-2">Effizienz</th>
              </tr>
            </thead>
            <tbody>
              {monthlyData.map((md, idx) => (
                <tr key={idx} className="border-b border-gray-100 dark:border-gray-800">
                  <td className="py-2 px-2">{md.name}</td>
                  <td className="text-right py-2 px-2 text-blue-600">{md.ladung.toFixed(1)}</td>
                  <td className="text-right py-2 px-2 text-green-600">{md.entladung.toFixed(1)}</td>
                  <td className="text-right py-2 px-2">{md.zyklen.toFixed(1)}</td>
                  <td className="text-right py-2 px-2">{md.effizienz.toFixed(1)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </Card>
  )
}
