/**
 * Balkonkraftwerk Dashboard
 * Zeigt Statistiken: Erzeugung, Eigenverbrauch, Einspeisung, Ersparnis
 */

import { useState, useEffect } from 'react'
import { Sun, Zap, TrendingUp, Home, Leaf, Battery } from 'lucide-react'
import { Card, LoadingSpinner, Alert, Select, KPICard } from '../components/ui'
import { useAnlagen } from '../hooks'
import { investitionenApi } from '../api'
import type { BalkonkraftwerkDashboardResponse } from '../api/investitionen'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
  PieChart, Pie, Cell, AreaChart, Area
} from 'recharts'

const monatNamen = ['', 'Jan', 'Feb', 'Mär', 'Apr', 'Mai', 'Jun', 'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Dez']

export default function BalkonkraftwerkDashboard() {
  const { anlagen, loading: anlagenLoading } = useAnlagen()
  const [selectedAnlageId, setSelectedAnlageId] = useState<number | undefined>()
  const [dashboards, setDashboards] = useState<BalkonkraftwerkDashboardResponse[]>([])
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
        const data = await investitionenApi.getBalkonkraftwerkDashboard(selectedAnlageId)
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
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Balkonkraftwerk Dashboard</h1>
        <Alert type="warning">Bitte zuerst eine Anlage anlegen.</Alert>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div className="flex items-center gap-3">
          <Sun className="h-8 w-8 text-yellow-500" />
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Balkonkraftwerk Dashboard</h1>
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
        <LoadingSpinner text="Lade Balkonkraftwerk Daten..." />
      ) : dashboards.length === 0 ? (
        <Card>
          <div className="text-center py-8 text-gray-500 dark:text-gray-400">
            <Sun className="h-12 w-12 mx-auto mb-4 opacity-50" />
            <p>Kein Balkonkraftwerk für diese Anlage erfasst.</p>
            <p className="text-sm mt-2">Füge ein Balkonkraftwerk unter "Investitionen" hinzu.</p>
          </div>
        </Card>
      ) : (
        dashboards.map((dashboard) => (
          <BalkonkraftwerkCard key={dashboard.investition.id} dashboard={dashboard} />
        ))
      )}
    </div>
  )
}

function BalkonkraftwerkCard({ dashboard }: { dashboard: BalkonkraftwerkDashboardResponse }) {
  const { investition, monatsdaten, zusammenfassung } = dashboard
  const z = zusammenfassung

  const monthlyData = monatsdaten.map(md => ({
    name: `${monatNamen[md.monat]} ${md.jahr.toString().slice(2)}`,
    erzeugung: md.verbrauch_daten.erzeugung_kwh || 0,
    eigenverbrauch: md.verbrauch_daten.eigenverbrauch_kwh || 0,
    einspeisung: md.verbrauch_daten.einspeisung_kwh || 0,
    speicher_ladung: md.verbrauch_daten.speicher_ladung_kwh || 0,
    speicher_entladung: md.verbrauch_daten.speicher_entladung_kwh || 0,
  }))

  const verbrauchPieData = [
    { name: 'Eigenverbrauch', value: z.gesamt_eigenverbrauch_kwh },
    { name: 'Einspeisung', value: z.gesamt_einspeisung_kwh },
  ]

  const COLORS = ['#22c55e', '#f59e0b']

  return (
    <Card className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-semibold text-gray-900 dark:text-white">
            {investition.bezeichnung}
          </h2>
          <p className="text-sm text-gray-500 dark:text-gray-400">
            {z.leistung_wp} Wp • {z.anzahl_module} Module • {z.anzahl_monate} Monate Daten
            {z.hat_speicher && ` • ${z.speicher_kapazitaet_wh} Wh Speicher`}
          </p>
        </div>
        <Sun className="h-10 w-10 text-yellow-500" />
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <KPICard
          title="Erzeugung"
          value={z.gesamt_erzeugung_kwh.toFixed(0)}
          unit="kWh"
          icon={Zap}
          color="yellow"
          formel="Σ Erzeugung alle Monate"
          berechnung={`${z.anzahl_monate} Monate`}
          ergebnis={`= ${z.gesamt_erzeugung_kwh.toFixed(0)} kWh`}
        />
        <KPICard
          title="Eigenverbrauch"
          value={z.eigenverbrauch_quote_prozent.toFixed(0)}
          unit="%"
          icon={Home}
          color="green"
          formel="EV-Quote = Eigenverbrauch ÷ Erzeugung × 100"
          berechnung={`${z.gesamt_eigenverbrauch_kwh.toFixed(0)} kWh ÷ ${z.gesamt_erzeugung_kwh.toFixed(0)} kWh × 100`}
          ergebnis={`= ${z.eigenverbrauch_quote_prozent.toFixed(1)} %`}
        />
        <KPICard
          title="Ersparnis"
          value={z.gesamt_ersparnis_euro.toFixed(0)}
          unit="€"
          icon={TrendingUp}
          color="green"
          trend={z.gesamt_ersparnis_euro > 0 ? 'up' : undefined}
          formel="Ersparnis = Eigenverbrauch × Strompreis"
          berechnung={`${z.gesamt_eigenverbrauch_kwh.toFixed(0)} kWh × Strompreis`}
          ergebnis={`= ${z.gesamt_ersparnis_euro.toFixed(2)} €`}
        />
        <KPICard
          title="CO₂ gespart"
          value={z.co2_ersparnis_kg.toFixed(0)}
          unit="kg"
          icon={Leaf}
          color="green"
          formel="CO₂ = Eigenverbrauch × 0.4 kg/kWh"
          berechnung={`${z.gesamt_eigenverbrauch_kwh.toFixed(0)} kWh × 0.4`}
          ergebnis={`= ${z.co2_ersparnis_kg.toFixed(0)} kg`}
        />
      </div>
      <p className="text-xs text-gray-400 dark:text-gray-500 italic -mt-2">
        Basis: tatsächlich erfasster Eigenverbrauch aus Monatsdaten
      </p>

      {/* Summary Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="bg-yellow-50 dark:bg-yellow-900/20 rounded-lg p-4">
          <p className="text-sm text-yellow-600 dark:text-yellow-400">Spez. Ertrag</p>
          <p className="text-2xl font-bold text-yellow-700 dark:text-yellow-300">
            {z.spezifischer_ertrag_kwh_kwp.toFixed(0)} kWh/kWp
          </p>
        </div>
        <div className="bg-green-50 dark:bg-green-900/20 rounded-lg p-4">
          <p className="text-sm text-green-600 dark:text-green-400">Eigenverbrauch</p>
          <p className="text-2xl font-bold text-green-700 dark:text-green-300">
            {z.gesamt_eigenverbrauch_kwh.toFixed(0)} kWh
          </p>
        </div>
        <div className="bg-orange-50 dark:bg-orange-900/20 rounded-lg p-4">
          <p className="text-sm text-orange-600 dark:text-orange-400">
            Einspeisung
            <span className="text-xs ml-1 opacity-70">(unvergütet)</span>
          </p>
          <p className="text-2xl font-bold text-orange-700 dark:text-orange-300">
            {z.gesamt_einspeisung_kwh.toFixed(0)} kWh
          </p>
        </div>
        <div className="bg-gray-50 dark:bg-gray-800/50 rounded-lg p-4">
          <p className="text-sm text-gray-600 dark:text-gray-400">
            Entgangener Erlös
            <span className="text-xs ml-1 opacity-70">(8 ct/kWh)</span>
          </p>
          <p className="text-2xl font-bold text-gray-500 dark:text-gray-400">
            {(z.gesamt_einspeisung_kwh * 0.08).toFixed(2)} €
          </p>
        </div>
      </div>

      {/* Charts Row 1 */}
      <div className="grid md:grid-cols-2 gap-6">
        {/* Verbrauchsverteilung Pie */}
        <div>
          <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-4">
            Verwendung der Erzeugung
          </h3>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={verbrauchPieData}
                  cx="50%"
                  cy="50%"
                  innerRadius={60}
                  outerRadius={80}
                  paddingAngle={5}
                  dataKey="value"
                  label={({ name, percent }) => `${name}: ${(percent * 100).toFixed(0)}%`}
                >
                  {verbrauchPieData.map((_, index) => (
                    <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip formatter={(v: number) => `${v.toFixed(0)} kWh`} />
              </PieChart>
            </ResponsiveContainer>
          </div>
          <div className="flex justify-center gap-6 text-sm">
            <span className="flex items-center gap-2">
              <span className="w-3 h-3 rounded-full bg-green-500"></span>
              Eigenverbrauch: {z.gesamt_eigenverbrauch_kwh.toFixed(0)} kWh
            </span>
            <span className="flex items-center gap-2">
              <span className="w-3 h-3 rounded-full bg-orange-500"></span>
              Einspeisung: {z.gesamt_einspeisung_kwh.toFixed(0)} kWh
            </span>
          </div>
        </div>

        {/* Erzeugung pro Monat */}
        <div>
          <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-4">
            Erzeugung pro Monat (kWh)
          </h3>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={monthlyData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="name" fontSize={10} />
                <YAxis />
                <Tooltip />
                <Legend />
                <Area type="monotone" dataKey="eigenverbrauch" stackId="1" fill="#22c55e" stroke="#16a34a" name="Eigenverbrauch" />
                <Area type="monotone" dataKey="einspeisung" stackId="1" fill="#f59e0b" stroke="#d97706" name="Einspeisung" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      {/* Speicher-Bereich (falls vorhanden) */}
      {z.hat_speicher && (
        <div className="border-t border-gray-200 dark:border-gray-700 pt-6">
          <div className="flex items-center gap-2 mb-4">
            <Battery className="h-5 w-5 text-purple-500" />
            <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300">
              Speicher ({z.speicher_kapazitaet_wh} Wh)
            </h3>
          </div>
          <div className="grid grid-cols-3 gap-4">
            <div className="bg-purple-50 dark:bg-purple-900/20 rounded-lg p-4">
              <p className="text-sm text-purple-600 dark:text-purple-400">Ladung gesamt</p>
              <p className="text-2xl font-bold text-purple-700 dark:text-purple-300">
                {z.speicher_ladung_kwh.toFixed(1)} kWh
              </p>
            </div>
            <div className="bg-purple-50 dark:bg-purple-900/20 rounded-lg p-4">
              <p className="text-sm text-purple-600 dark:text-purple-400">Entladung gesamt</p>
              <p className="text-2xl font-bold text-purple-700 dark:text-purple-300">
                {z.speicher_entladung_kwh.toFixed(1)} kWh
              </p>
            </div>
            <div className="bg-purple-50 dark:bg-purple-900/20 rounded-lg p-4">
              <p className="text-sm text-purple-600 dark:text-purple-400">Effizienz</p>
              <p className="text-2xl font-bold text-purple-700 dark:text-purple-300">
                {z.speicher_effizienz_prozent.toFixed(1)}%
              </p>
            </div>
          </div>

          {/* Speicher Chart */}
          <div className="mt-4">
            <div className="h-48">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={monthlyData}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="name" fontSize={10} />
                  <YAxis />
                  <Tooltip />
                  <Legend />
                  <Bar dataKey="speicher_ladung" fill="#8b5cf6" name="Ladung" />
                  <Bar dataKey="speicher_entladung" fill="#a855f7" name="Entladung" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>
      )}

      {/* CO2 Info */}
      <div className="bg-green-50 dark:bg-green-900/20 rounded-lg p-4 flex items-center gap-4">
        <Leaf className="h-8 w-8 text-green-500" />
        <div>
          <p className="text-sm text-green-600 dark:text-green-400">CO₂ Ersparnis durch Eigenverbrauch</p>
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
                <th className="text-right py-2 px-2">Erzeugung</th>
                <th className="text-right py-2 px-2">Eigenverbrauch</th>
                <th className="text-right py-2 px-2">Einspeisung</th>
                {z.hat_speicher && (
                  <>
                    <th className="text-right py-2 px-2">Sp. Ladung</th>
                    <th className="text-right py-2 px-2">Sp. Entl.</th>
                  </>
                )}
              </tr>
            </thead>
            <tbody>
              {monthlyData.map((md, idx) => (
                <tr key={idx} className="border-b border-gray-100 dark:border-gray-800">
                  <td className="py-2 px-2">{md.name}</td>
                  <td className="text-right py-2 px-2 text-yellow-600">{md.erzeugung.toFixed(1)}</td>
                  <td className="text-right py-2 px-2 text-green-600">{md.eigenverbrauch.toFixed(1)}</td>
                  <td className="text-right py-2 px-2 text-orange-600">{md.einspeisung.toFixed(1)}</td>
                  {z.hat_speicher && (
                    <>
                      <td className="text-right py-2 px-2 text-purple-600">{md.speicher_ladung.toFixed(1)}</td>
                      <td className="text-right py-2 px-2 text-purple-600">{md.speicher_entladung.toFixed(1)}</td>
                    </>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </Card>
  )
}
