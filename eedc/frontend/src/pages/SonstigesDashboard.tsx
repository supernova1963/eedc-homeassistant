/**
 * Sonstiges Dashboard
 * Zeigt Statistiken für sonstige Investitionen (Mini-BHKW, Pelletofen, Mini-Wind, Brennstoffzelle, etc.)
 * Kategoriebasiert: Erzeuger, Verbraucher oder Speicher
 */

import { useState, useEffect } from 'react'
import { Wrench, Zap, TrendingUp, Home, Leaf, Battery, AlertCircle } from 'lucide-react'
import { Card, LoadingSpinner, Alert, Select, KPICard } from '../components/ui'
import { useAnlagen } from '../hooks'
import { investitionenApi } from '../api'
import type { SonstigesDashboardResponse } from '../api/investitionen'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
  PieChart, Pie, Cell, AreaChart, Area
} from 'recharts'

const monatNamen = ['', 'Jan', 'Feb', 'Mär', 'Apr', 'Mai', 'Jun', 'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Dez']

const kategorieLabels: Record<string, string> = {
  erzeuger: 'Erzeuger',
  verbraucher: 'Verbraucher',
  speicher: 'Speicher',
}

export default function SonstigesDashboard() {
  const { anlagen, loading: anlagenLoading } = useAnlagen()
  const [selectedAnlageId, setSelectedAnlageId] = useState<number | undefined>()
  const [dashboards, setDashboards] = useState<SonstigesDashboardResponse[]>([])
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
        const data = await investitionenApi.getSonstigesDashboard(selectedAnlageId)
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
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Sonstiges Dashboard</h1>
        <Alert type="warning">Bitte zuerst eine Anlage anlegen.</Alert>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div className="flex items-center gap-3">
          <Wrench className="h-8 w-8 text-gray-500" />
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Sonstiges Dashboard</h1>
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
        <LoadingSpinner text="Lade Daten..." />
      ) : dashboards.length === 0 ? (
        <Card>
          <div className="text-center py-8 text-gray-500 dark:text-gray-400">
            <Wrench className="h-12 w-12 mx-auto mb-4 opacity-50" />
            <p>Keine sonstigen Investitionen für diese Anlage erfasst.</p>
            <p className="text-sm mt-2">Füge eine sonstige Investition unter "Investitionen" hinzu.</p>
            <p className="text-xs mt-1 text-gray-400">z.B. Mini-BHKW, Pelletofen, Mini-Wind, Brennstoffzelle</p>
          </div>
        </Card>
      ) : (
        dashboards.map((dashboard) => (
          <SonstigesCard key={dashboard.investition.id} dashboard={dashboard} />
        ))
      )}
    </div>
  )
}

function SonstigesCard({ dashboard }: { dashboard: SonstigesDashboardResponse }) {
  const { investition, monatsdaten, zusammenfassung } = dashboard
  const z = zusammenfassung
  const kategorie = z.kategorie

  // Je nach Kategorie unterschiedliche Ansicht
  if (kategorie === 'erzeuger') {
    return <ErzeugerCard investition={investition} monatsdaten={monatsdaten} zusammenfassung={z} />
  } else if (kategorie === 'verbraucher') {
    return <VerbraucherCard investition={investition} monatsdaten={monatsdaten} zusammenfassung={z} />
  } else {
    return <SpeicherCard investition={investition} monatsdaten={monatsdaten} zusammenfassung={z} />
  }
}

function ErzeugerCard({ investition, monatsdaten, zusammenfassung: z }: {
  investition: SonstigesDashboardResponse['investition']
  monatsdaten: SonstigesDashboardResponse['monatsdaten']
  zusammenfassung: SonstigesDashboardResponse['zusammenfassung']
}) {
  const monthlyData = monatsdaten.map(md => ({
    name: `${monatNamen[md.monat]} ${md.jahr.toString().slice(2)}`,
    erzeugung: md.verbrauch_daten.erzeugung_kwh || 0,
    eigenverbrauch: md.verbrauch_daten.eigenverbrauch_kwh || 0,
    einspeisung: md.verbrauch_daten.einspeisung_kwh || 0,
  }))

  const verbrauchPieData = [
    { name: 'Eigenverbrauch', value: z.gesamt_eigenverbrauch_kwh || 0 },
    { name: 'Einspeisung', value: z.gesamt_einspeisung_kwh || 0 },
  ]

  return (
    <Card className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="text-xl font-semibold text-gray-900 dark:text-white">
              {investition.bezeichnung}
            </h2>
            <span className="px-2 py-0.5 text-xs bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200 rounded">
              {kategorieLabels[z.kategorie]}
            </span>
          </div>
          {z.beschreibung && (
            <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">{z.beschreibung}</p>
          )}
          <p className="text-sm text-gray-500 dark:text-gray-400">
            {z.anzahl_monate} Monate Daten
          </p>
        </div>
        <Zap className="h-10 w-10 text-yellow-500" />
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <KPICard
          title="Erzeugung"
          value={(z.gesamt_erzeugung_kwh || 0).toFixed(0)}
          unit="kWh"
          icon={Zap}
          color="yellow"
        />
        <KPICard
          title="Eigenverbrauch"
          value={(z.eigenverbrauch_quote_prozent || 0).toFixed(0)}
          unit="%"
          icon={Home}
          color="green"
        />
        <KPICard
          title="Ersparnis"
          value={(z.gesamt_ersparnis_euro || 0).toFixed(0)}
          unit="€"
          icon={TrendingUp}
          color="green"
          trend={(z.gesamt_ersparnis_euro || 0) > 0 ? 'up' : undefined}
        />
        <KPICard
          title="CO₂ gespart"
          value={(z.co2_ersparnis_kg || 0).toFixed(0)}
          unit="kg"
          icon={Leaf}
          color="green"
        />
      </div>

      {/* Sonderkosten Warnung */}
      {z.sonderkosten_euro > 0 && (
        <div className="bg-red-50 dark:bg-red-900/20 rounded-lg p-4 flex items-center gap-4">
          <AlertCircle className="h-6 w-6 text-red-500" />
          <div>
            <p className="text-sm text-red-600 dark:text-red-400">Sonderkosten (Reparaturen, Wartung)</p>
            <p className="text-xl font-bold text-red-700 dark:text-red-300">
              {z.sonderkosten_euro.toFixed(2)} €
            </p>
          </div>
        </div>
      )}

      {/* Charts */}
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
                  <Cell fill="#22c55e" />
                  <Cell fill="#f59e0b" />
                </Pie>
                <Tooltip formatter={(v: number) => `${v.toFixed(0)} kWh`} />
              </PieChart>
            </ResponsiveContainer>
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
              </tr>
            </thead>
            <tbody>
              {monthlyData.map((md, idx) => (
                <tr key={idx} className="border-b border-gray-100 dark:border-gray-800">
                  <td className="py-2 px-2">{md.name}</td>
                  <td className="text-right py-2 px-2 text-yellow-600">{md.erzeugung.toFixed(1)}</td>
                  <td className="text-right py-2 px-2 text-green-600">{md.eigenverbrauch.toFixed(1)}</td>
                  <td className="text-right py-2 px-2 text-orange-600">{md.einspeisung.toFixed(1)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </Card>
  )
}

function VerbraucherCard({ investition, monatsdaten, zusammenfassung: z }: {
  investition: SonstigesDashboardResponse['investition']
  monatsdaten: SonstigesDashboardResponse['monatsdaten']
  zusammenfassung: SonstigesDashboardResponse['zusammenfassung']
}) {
  const monthlyData = monatsdaten.map(md => ({
    name: `${monatNamen[md.monat]} ${md.jahr.toString().slice(2)}`,
    verbrauch: md.verbrauch_daten.verbrauch_kwh || 0,
    bezug_pv: md.verbrauch_daten.bezug_pv_kwh || 0,
    bezug_netz: md.verbrauch_daten.bezug_netz_kwh || 0,
  }))

  const bezugPieData = [
    { name: 'PV-Strom', value: z.bezug_pv_kwh || 0 },
    { name: 'Netzstrom', value: z.bezug_netz_kwh || 0 },
  ]

  return (
    <Card className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="text-xl font-semibold text-gray-900 dark:text-white">
              {investition.bezeichnung}
            </h2>
            <span className="px-2 py-0.5 text-xs bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200 rounded">
              {kategorieLabels[z.kategorie]}
            </span>
          </div>
          {z.beschreibung && (
            <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">{z.beschreibung}</p>
          )}
          <p className="text-sm text-gray-500 dark:text-gray-400">
            {z.anzahl_monate} Monate Daten
          </p>
        </div>
        <Zap className="h-10 w-10 text-blue-500" />
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <KPICard
          title="Verbrauch"
          value={(z.gesamt_verbrauch_kwh || 0).toFixed(0)}
          unit="kWh"
          icon={Zap}
          color="blue"
        />
        <KPICard
          title="PV-Anteil"
          value={(z.pv_anteil_prozent || 0).toFixed(0)}
          unit="%"
          icon={Home}
          color="green"
        />
        <KPICard
          title="Netzkosten"
          value={(z.kosten_netz_euro || 0).toFixed(0)}
          unit="€"
          icon={TrendingUp}
          color="red"
        />
        <KPICard
          title="PV-Ersparnis"
          value={(z.ersparnis_pv_euro || 0).toFixed(0)}
          unit="€"
          icon={Leaf}
          color="green"
          trend={(z.ersparnis_pv_euro || 0) > 0 ? 'up' : undefined}
        />
      </div>

      {/* Sonderkosten Warnung */}
      {z.sonderkosten_euro > 0 && (
        <div className="bg-red-50 dark:bg-red-900/20 rounded-lg p-4 flex items-center gap-4">
          <AlertCircle className="h-6 w-6 text-red-500" />
          <div>
            <p className="text-sm text-red-600 dark:text-red-400">Sonderkosten (Reparaturen, Wartung)</p>
            <p className="text-xl font-bold text-red-700 dark:text-red-300">
              {z.sonderkosten_euro.toFixed(2)} €
            </p>
          </div>
        </div>
      )}

      {/* Charts */}
      <div className="grid md:grid-cols-2 gap-6">
        {/* Strombezug Pie */}
        <div>
          <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-4">
            Strombezug-Aufteilung
          </h3>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={bezugPieData}
                  cx="50%"
                  cy="50%"
                  innerRadius={60}
                  outerRadius={80}
                  paddingAngle={5}
                  dataKey="value"
                  label={({ name, percent }) => `${name}: ${(percent * 100).toFixed(0)}%`}
                >
                  <Cell fill="#22c55e" />
                  <Cell fill="#ef4444" />
                </Pie>
                <Tooltip formatter={(v: number) => `${v.toFixed(0)} kWh`} />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Verbrauch pro Monat */}
        <div>
          <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-4">
            Verbrauch pro Monat (kWh)
          </h3>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={monthlyData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="name" fontSize={10} />
                <YAxis />
                <Tooltip />
                <Legend />
                <Bar dataKey="bezug_pv" stackId="1" fill="#22c55e" name="PV-Strom" />
                <Bar dataKey="bezug_netz" stackId="1" fill="#ef4444" name="Netzstrom" />
              </BarChart>
            </ResponsiveContainer>
          </div>
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
                <th className="text-right py-2 px-2">Verbrauch</th>
                <th className="text-right py-2 px-2">PV-Strom</th>
                <th className="text-right py-2 px-2">Netzstrom</th>
              </tr>
            </thead>
            <tbody>
              {monthlyData.map((md, idx) => (
                <tr key={idx} className="border-b border-gray-100 dark:border-gray-800">
                  <td className="py-2 px-2">{md.name}</td>
                  <td className="text-right py-2 px-2 text-blue-600">{md.verbrauch.toFixed(1)}</td>
                  <td className="text-right py-2 px-2 text-green-600">{md.bezug_pv.toFixed(1)}</td>
                  <td className="text-right py-2 px-2 text-red-600">{md.bezug_netz.toFixed(1)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </Card>
  )
}

function SpeicherCard({ investition, monatsdaten, zusammenfassung: z }: {
  investition: SonstigesDashboardResponse['investition']
  monatsdaten: SonstigesDashboardResponse['monatsdaten']
  zusammenfassung: SonstigesDashboardResponse['zusammenfassung']
}) {
  const monthlyData = monatsdaten.map(md => ({
    name: `${monatNamen[md.monat]} ${md.jahr.toString().slice(2)}`,
    ladung: md.verbrauch_daten.ladung_kwh || 0,
    entladung: md.verbrauch_daten.entladung_kwh || 0,
  }))

  return (
    <Card className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="text-xl font-semibold text-gray-900 dark:text-white">
              {investition.bezeichnung}
            </h2>
            <span className="px-2 py-0.5 text-xs bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-200 rounded">
              {kategorieLabels[z.kategorie]}
            </span>
          </div>
          {z.beschreibung && (
            <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">{z.beschreibung}</p>
          )}
          <p className="text-sm text-gray-500 dark:text-gray-400">
            {z.anzahl_monate} Monate Daten
          </p>
        </div>
        <Battery className="h-10 w-10 text-purple-500" />
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <KPICard
          title="Ladung"
          value={(z.gesamt_ladung_kwh || 0).toFixed(0)}
          unit="kWh"
          icon={Battery}
          color="purple"
        />
        <KPICard
          title="Entladung"
          value={(z.gesamt_entladung_kwh || 0).toFixed(0)}
          unit="kWh"
          icon={Zap}
          color="green"
        />
        <KPICard
          title="Effizienz"
          value={(z.effizienz_prozent || 0).toFixed(1)}
          unit="%"
          icon={TrendingUp}
          color="blue"
        />
        <KPICard
          title="Ersparnis"
          value={(z.ersparnis_euro || 0).toFixed(0)}
          unit="€"
          icon={TrendingUp}
          color="green"
          trend={(z.ersparnis_euro || 0) > 0 ? 'up' : undefined}
        />
      </div>

      {/* Sonderkosten Warnung */}
      {z.sonderkosten_euro > 0 && (
        <div className="bg-red-50 dark:bg-red-900/20 rounded-lg p-4 flex items-center gap-4">
          <AlertCircle className="h-6 w-6 text-red-500" />
          <div>
            <p className="text-sm text-red-600 dark:text-red-400">Sonderkosten (Reparaturen, Wartung)</p>
            <p className="text-xl font-bold text-red-700 dark:text-red-300">
              {z.sonderkosten_euro.toFixed(2)} €
            </p>
          </div>
        </div>
      )}

      {/* Chart */}
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
              <Bar dataKey="ladung" fill="#8b5cf6" name="Ladung" />
              <Bar dataKey="entladung" fill="#22c55e" name="Entladung" />
            </BarChart>
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
                <th className="text-right py-2 px-2">Effizienz</th>
              </tr>
            </thead>
            <tbody>
              {monthlyData.map((md, idx) => {
                const effizienz = md.ladung > 0 ? (md.entladung / md.ladung) * 100 : 0
                return (
                  <tr key={idx} className="border-b border-gray-100 dark:border-gray-800">
                    <td className="py-2 px-2">{md.name}</td>
                    <td className="text-right py-2 px-2 text-purple-600">{md.ladung.toFixed(1)}</td>
                    <td className="text-right py-2 px-2 text-green-600">{md.entladung.toFixed(1)}</td>
                    <td className="text-right py-2 px-2">{effizienz.toFixed(1)}%</td>
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
