/**
 * E-Auto Dashboard
 * Zeigt Statistiken zu E-Autos: km, Verbrauch, PV-Anteil, Ersparnis vs. Benzin, V2H
 */

import { useState, useEffect } from 'react'
import { Car, Zap, Leaf, TrendingUp, Battery } from 'lucide-react'
import { Card, LoadingSpinner, Alert, Select, KPICard } from '../components/ui'
import { useAnlagen } from '../hooks'
import { investitionenApi } from '../api'
import type { EAutoDashboardResponse } from '../api/investitionen'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
  PieChart, Pie, Cell
} from 'recharts'

const monatNamen = ['', 'Jan', 'Feb', 'Mär', 'Apr', 'Mai', 'Jun', 'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Dez']

export default function EAutoDashboard() {
  const { anlagen, loading: anlagenLoading } = useAnlagen()
  const [selectedAnlageId, setSelectedAnlageId] = useState<number | undefined>()
  const [dashboards, setDashboards] = useState<EAutoDashboardResponse[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Erste Anlage automatisch auswählen
  useEffect(() => {
    if (anlagen.length > 0 && !selectedAnlageId) {
      setSelectedAnlageId(anlagen[0].id)
    }
  }, [anlagen, selectedAnlageId])

  // Dashboard laden
  useEffect(() => {
    if (!selectedAnlageId) return

    const loadDashboard = async () => {
      setLoading(true)
      setError(null)
      try {
        const data = await investitionenApi.getEAutoDashboard(selectedAnlageId)
        setDashboards(data)
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Fehler beim Laden')
      } finally {
        setLoading(false)
      }
    }

    loadDashboard()
  }, [selectedAnlageId])

  if (anlagenLoading) {
    return <LoadingSpinner text="Lade..." />
  }

  if (anlagen.length === 0) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">E-Auto Dashboard</h1>
        <Alert type="warning">Bitte zuerst eine Anlage anlegen.</Alert>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div className="flex items-center gap-3">
          <Car className="h-8 w-8 text-blue-500" />
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">E-Auto Dashboard</h1>
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
        <LoadingSpinner text="Lade E-Auto Daten..." />
      ) : dashboards.length === 0 ? (
        <Card>
          <div className="text-center py-8 text-gray-500 dark:text-gray-400">
            <Car className="h-12 w-12 mx-auto mb-4 opacity-50" />
            <p>Kein E-Auto für diese Anlage erfasst.</p>
            <p className="text-sm mt-2">Füge ein E-Auto unter "Investitionen" hinzu.</p>
          </div>
        </Card>
      ) : (
        dashboards.map((dashboard) => (
          <EAutoCard key={dashboard.investition.id} dashboard={dashboard} />
        ))
      )}
    </div>
  )
}

function EAutoCard({ dashboard }: { dashboard: EAutoDashboardResponse }) {
  const { investition, monatsdaten, zusammenfassung } = dashboard
  const z = zusammenfassung

  // Daten für Charts vorbereiten
  const monthlyData = monatsdaten.map(md => ({
    name: `${monatNamen[md.monat]} ${md.jahr.toString().slice(2)}`,
    km: md.verbrauch_daten.km_gefahren || 0,
    verbrauch: md.verbrauch_daten.verbrauch_kwh || 0,
    pv: md.verbrauch_daten.ladung_pv_kwh || 0,
    netz: md.verbrauch_daten.ladung_netz_kwh || 0,
    extern: md.verbrauch_daten.ladung_extern_kwh || 0,
    v2h: md.verbrauch_daten.v2h_entladung_kwh || 0,
  }))

  // Ladequelle: Heim (PV + Netz) vs Extern
  const ladungPieData = [
    { name: 'Heim: PV', value: z.ladung_pv_kwh || 0 },
    { name: 'Heim: Netz', value: z.ladung_netz_kwh || 0 },
    { name: 'Extern', value: z.ladung_extern_kwh || 0 },
  ].filter(d => d.value > 0)

  const kostenVergleichData = [
    { name: 'E-Auto (Strom)', value: z.strom_kosten_gesamt_euro || 0, fill: '#22c55e' },
    { name: 'Verbrenner (Benzin)', value: z.benzin_kosten_alternativ_euro || 0, fill: '#ef4444' },
  ]

  return (
    <Card className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-semibold text-gray-900 dark:text-white">
            {investition.bezeichnung}
          </h2>
          <p className="text-sm text-gray-500 dark:text-gray-400">
            {z.anzahl_monate} Monate Daten
          </p>
        </div>
        <Car className="h-10 w-10 text-blue-500" />
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <KPICard
          title="Gefahren"
          value={z.gesamt_km?.toLocaleString('de-DE') || '0'}
          unit="km"
          icon={Car}
          color="blue"
        />
        <KPICard
          title="Verbrauch"
          value={(z.durchschnitt_verbrauch_kwh_100km || 0).toFixed(1)}
          unit="kWh/100km"
          icon={Zap}
          color="yellow"
        />
        <KPICard
          title="PV-Anteil (Heim)"
          value={(z.pv_anteil_heim_prozent || 0).toFixed(0)}
          unit="%"
          subtitle={`Gesamt: ${(z.pv_anteil_gesamt_prozent || 0).toFixed(0)}%`}
          icon={Leaf}
          color="green"
        />
        <KPICard
          title="Ersparnis vs. Benzin"
          value={(z.gesamt_ersparnis_euro || 0).toFixed(0)}
          unit="€"
          subtitle={`+ Wallbox: ${(z.wallbox_ersparnis_euro || 0).toFixed(0)} €`}
          icon={TrendingUp}
          color="green"
          trend={(z.gesamt_ersparnis_euro || 0) > 0 ? 'up' : undefined}
        />
      </div>

      {/* Charts Row 1 */}
      <div className="grid md:grid-cols-2 gap-6">
        {/* Ladung PV vs Netz */}
        <div>
          <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-4">
            Ladequelle
          </h3>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={ladungPieData}
                  cx="50%"
                  cy="50%"
                  innerRadius={60}
                  outerRadius={80}
                  paddingAngle={5}
                  dataKey="value"
                  label={({ name, percent }) => `${name}: ${(percent * 100).toFixed(0)}%`}
                >
                  <Cell fill="#22c55e" /> {/* PV: grün */}
                  <Cell fill="#f97316" /> {/* Netz: orange */}
                  <Cell fill="#ef4444" /> {/* Extern: rot */}
                </Pie>
                <Tooltip formatter={(v: number) => `${v.toFixed(1)} kWh`} />
              </PieChart>
            </ResponsiveContainer>
          </div>
          <div className="flex justify-center gap-4 text-sm flex-wrap">
            <span className="flex items-center gap-2">
              <span className="w-3 h-3 rounded-full bg-green-500"></span>
              PV: {(z.ladung_pv_kwh || 0).toFixed(0)} kWh
            </span>
            <span className="flex items-center gap-2">
              <span className="w-3 h-3 rounded-full bg-orange-500"></span>
              Netz: {(z.ladung_netz_kwh || 0).toFixed(0)} kWh
            </span>
            {(z.ladung_extern_kwh || 0) > 0 && (
              <span className="flex items-center gap-2">
                <span className="w-3 h-3 rounded-full bg-red-500"></span>
                Extern: {(z.ladung_extern_kwh || 0).toFixed(0)} kWh ({(z.ladung_extern_euro || 0).toFixed(2)} €)
              </span>
            )}
          </div>
        </div>

        {/* Kostenvergleich */}
        <div>
          <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-4">
            Kostenvergleich E-Auto vs. Verbrenner
          </h3>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={kostenVergleichData} layout="vertical">
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis type="number" tickFormatter={(v) => `${v}€`} />
                <YAxis type="category" dataKey="name" width={120} />
                <Tooltip formatter={(v: number) => `${v.toFixed(2)} €`} />
                <Bar dataKey="value" />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <div className="text-center mt-2">
            <span className="text-lg font-semibold text-green-600 dark:text-green-400">
              Ersparnis: {(z.ersparnis_vs_benzin_euro || 0).toFixed(2)} €
            </span>
          </div>
        </div>
      </div>

      {/* Charts Row 2 */}
      <div className="grid md:grid-cols-2 gap-6">
        {/* km pro Monat */}
        <div>
          <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-4">
            Kilometer pro Monat
          </h3>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={monthlyData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="name" fontSize={10} />
                <YAxis />
                <Tooltip />
                <Bar dataKey="km" fill="#3b82f6" name="km" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

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
                <Legend />
                <Bar dataKey="pv" stackId="a" fill="#22c55e" name="Heim: PV" />
                <Bar dataKey="netz" stackId="a" fill="#f97316" name="Heim: Netz" />
                <Bar dataKey="extern" stackId="a" fill="#ef4444" name="Extern" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      {/* V2H Section (wenn aktiv) */}
      {(z.v2h_entladung_kwh || 0) > 0 && (
        <div className="border-t border-gray-200 dark:border-gray-700 pt-6">
          <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-4 flex items-center gap-2">
            <Battery className="h-5 w-5 text-purple-500" />
            Vehicle-to-Home (V2H)
          </h3>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
            <div className="bg-purple-50 dark:bg-purple-900/20 rounded-lg p-4">
              <p className="text-sm text-purple-600 dark:text-purple-400">V2H Entladung</p>
              <p className="text-2xl font-bold text-purple-700 dark:text-purple-300">
                {(z.v2h_entladung_kwh || 0).toFixed(1)} kWh
              </p>
            </div>
            <div className="bg-purple-50 dark:bg-purple-900/20 rounded-lg p-4">
              <p className="text-sm text-purple-600 dark:text-purple-400">V2H Ersparnis</p>
              <p className="text-2xl font-bold text-purple-700 dark:text-purple-300">
                {(z.v2h_ersparnis_euro || 0).toFixed(2)} €
              </p>
            </div>
            <div className="bg-green-50 dark:bg-green-900/20 rounded-lg p-4">
              <p className="text-sm text-green-600 dark:text-green-400">CO₂ Ersparnis</p>
              <p className="text-2xl font-bold text-green-700 dark:text-green-300">
                {(z.co2_ersparnis_kg || 0).toFixed(0)} kg
              </p>
            </div>
          </div>
        </div>
      )}

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
                <th className="text-right py-2 px-2">km</th>
                <th className="text-right py-2 px-2">kWh</th>
                <th className="text-right py-2 px-2">PV</th>
                <th className="text-right py-2 px-2">Netz</th>
                <th className="text-right py-2 px-2">V2H</th>
              </tr>
            </thead>
            <tbody>
              {monatsdaten.map((md) => (
                <tr key={md.id} className="border-b border-gray-100 dark:border-gray-800">
                  <td className="py-2 px-2">{monatNamen[md.monat]} {md.jahr}</td>
                  <td className="text-right py-2 px-2">{md.verbrauch_daten.km_gefahren || 0}</td>
                  <td className="text-right py-2 px-2">{(md.verbrauch_daten.verbrauch_kwh || 0).toFixed(1)}</td>
                  <td className="text-right py-2 px-2 text-green-600">{(md.verbrauch_daten.ladung_pv_kwh || 0).toFixed(1)}</td>
                  <td className="text-right py-2 px-2 text-red-600">{(md.verbrauch_daten.ladung_netz_kwh || 0).toFixed(1)}</td>
                  <td className="text-right py-2 px-2 text-purple-600">{(md.verbrauch_daten.v2h_entladung_kwh || 0).toFixed(1)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </Card>
  )
}
