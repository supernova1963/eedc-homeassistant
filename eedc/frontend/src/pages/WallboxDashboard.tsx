/**
 * Wallbox Dashboard
 * Zeigt: Heimladung (aus E-Auto-Daten), PV-Anteil, Ersparnis vs. externe Ladung
 * Die Wallbox ist Infrastruktur - ihr ROI entsteht durch günstiges Heimladen.
 */

import { useState, useEffect } from 'react'
import { Plug, Zap, Leaf, TrendingUp, Home, MapPin } from 'lucide-react'
import { Card, LoadingSpinner, Alert, Select, KPICard } from '../components/ui'
import { useAnlagen } from '../hooks'
import { investitionenApi } from '../api'
import type { WallboxDashboardResponse } from '../api/investitionen'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, Legend
} from 'recharts'

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
            <p className="text-sm mt-2">Füge eine Wallbox unter "Einstellungen → Investitionen" hinzu.</p>
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
  const { investition, zusammenfassung } = dashboard
  const z = zusammenfassung

  // PieChart Daten: Heimladung vs Extern
  const ladungPieData = [
    { name: 'Heim: PV', value: z.ladung_pv_kwh || 0 },
    { name: 'Heim: Netz', value: z.ladung_netz_kwh || 0 },
    { name: 'Extern', value: z.extern_ladung_kwh || 0 },
  ].filter(d => d.value > 0)

  // Kostenvergleich: Was die Heimladung extern gekostet hätte vs. tatsächliche Kosten
  const kostenVergleichData = [
    { name: 'Heimladung (tatsächlich)', value: z.heim_kosten_euro || 0, fill: '#22c55e' },
    { name: 'Heimladung (als extern)', value: z.heim_als_extern_kosten_euro || 0, fill: '#ef4444' },
  ]

  const leistungKw = z.leistung_kw || 11
  const hatDaten = (z.gesamt_heim_ladung_kwh || 0) > 0

  return (
    <Card className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-semibold text-gray-900 dark:text-white">
            {investition.bezeichnung}
          </h2>
          <p className="text-sm text-gray-500 dark:text-gray-400">
            {leistungKw} kW Ladeleistung • {z.anzahl_monate || 0} Monate Daten
          </p>
        </div>
        <Plug className="h-10 w-10 text-purple-500" />
      </div>

      {!hatDaten ? (
        <div className="bg-yellow-50 dark:bg-yellow-900/20 rounded-lg p-4">
          <p className="text-sm text-yellow-700 dark:text-yellow-400">
            Noch keine Ladedaten vorhanden. Die Wallbox-Statistik wird aus den E-Auto-Monatsdaten berechnet.
            Erfasse E-Auto-Daten unter "Einstellungen → Monatsdaten".
          </p>
        </div>
      ) : (
        <>
          {/* KPIs */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <KPICard
              title="Heimladung"
              value={((z.gesamt_heim_ladung_kwh || 0) / 1000).toFixed(2)}
              unit="MWh"
              subtitle="PV + Netz"
              icon={Home}
              color="purple"
            />
            <KPICard
              title="PV-Anteil"
              value={(z.pv_anteil_prozent || 0).toFixed(0)}
              unit="%"
              subtitle={`${(z.ladung_pv_kwh || 0).toFixed(0)} kWh`}
              icon={Leaf}
              color="green"
            />
            <KPICard
              title="Ersparnis vs. Extern"
              value={(z.ersparnis_vs_extern_euro || 0).toFixed(0)}
              unit="€"
              subtitle="Wallbox-ROI"
              icon={TrendingUp}
              color="green"
              trend={(z.ersparnis_vs_extern_euro || 0) > 0 ? 'up' : undefined}
            />
            <KPICard
              title="Ladevorgänge"
              value={(z.gesamt_ladevorgaenge || 0).toString()}
              subtitle={`Ø ${(z.ladevorgaenge_pro_monat || 0).toFixed(1)}/Monat`}
              icon={Zap}
              color="blue"
            />
          </div>

          {/* Charts */}
          <div className="grid md:grid-cols-2 gap-6">
            {/* Ladequelle */}
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
                  <Home className="h-4 w-4 text-purple-500" />
                  Heim: {(z.gesamt_heim_ladung_kwh || 0).toFixed(0)} kWh
                </span>
                {(z.extern_ladung_kwh || 0) > 0 && (
                  <span className="flex items-center gap-2">
                    <MapPin className="h-4 w-4 text-red-500" />
                    Extern: {(z.extern_ladung_kwh || 0).toFixed(0)} kWh
                  </span>
                )}
              </div>
            </div>

            {/* Kostenvergleich */}
            <div>
              <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-4">
                Kostenvergleich: Heimladung vs. Externe Preise
              </h3>
              <div className="h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={kostenVergleichData} layout="vertical">
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis type="number" tickFormatter={(v) => `${v}€`} />
                    <YAxis type="category" dataKey="name" width={150} />
                    <Tooltip formatter={(v: number) => `${v.toFixed(2)} €`} />
                    <Legend />
                    <Bar dataKey="value" name="Kosten" />
                  </BarChart>
                </ResponsiveContainer>
              </div>
              <div className="text-center mt-2">
                <span className="text-lg font-semibold text-green-600 dark:text-green-400">
                  Ersparnis durch Wallbox: {(z.ersparnis_vs_extern_euro || 0).toFixed(2)} €
                </span>
              </div>
            </div>
          </div>

          {/* Erklärung */}
          <div className="bg-purple-50 dark:bg-purple-900/20 rounded-lg p-4 space-y-2">
            <p className="text-sm font-medium text-purple-700 dark:text-purple-300">
              Wallbox-ROI erklärt
            </p>
            <p className="text-sm text-purple-600 dark:text-purple-400">
              Die Ersparnis errechnet sich aus dem Unterschied zwischen Heimladen und externem Laden:
            </p>
            <ul className="text-sm text-purple-600 dark:text-purple-400 list-disc list-inside">
              <li>PV-Ladung zuhause: kostenlos ({(z.ladung_pv_kwh || 0).toFixed(0)} kWh)</li>
              <li>Netz-Ladung zuhause: Haushaltsstrom ({(z.ladung_netz_kwh || 0).toFixed(0)} kWh = {(z.heim_kosten_euro || 0).toFixed(2)} €)</li>
              <li>Vergleichspreis extern: {(z.extern_preis_kwh_euro || 0.50).toFixed(2)} €/kWh</li>
            </ul>
            {(z.extern_ladung_kwh || 0) > 0 && (
              <p className="text-sm text-purple-600 dark:text-purple-400 mt-2">
                Tatsächliche externe Ladung: {(z.extern_ladung_kwh || 0).toFixed(0)} kWh für {(z.extern_kosten_euro || 0).toFixed(2)} €
              </p>
            )}
          </div>

          {/* Anschaffungskosten und Amortisation */}
          {investition.anschaffungskosten_gesamt && investition.anschaffungskosten_gesamt > 0 && (
            <div className="border-t border-gray-200 dark:border-gray-700 pt-4">
              <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
                <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-4">
                  <p className="text-sm text-gray-500 dark:text-gray-400">Anschaffungskosten</p>
                  <p className="text-2xl font-bold text-gray-900 dark:text-white">
                    {investition.anschaffungskosten_gesamt.toLocaleString('de-DE')} €
                  </p>
                </div>
                <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-4">
                  <p className="text-sm text-gray-500 dark:text-gray-400">Ersparnis/Jahr (hochgerechnet)</p>
                  <p className="text-2xl font-bold text-green-600 dark:text-green-400">
                    {(z.anzahl_monate && z.anzahl_monate > 0
                      ? ((z.ersparnis_vs_extern_euro || 0) / z.anzahl_monate * 12).toFixed(0)
                      : 0
                    )} €
                  </p>
                </div>
                <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-4">
                  <p className="text-sm text-gray-500 dark:text-gray-400">Amortisation (ca.)</p>
                  <p className="text-2xl font-bold text-blue-600 dark:text-blue-400">
                    {(() => {
                      const jahresErsparnis = z.anzahl_monate && z.anzahl_monate > 0
                        ? ((z.ersparnis_vs_extern_euro || 0) / z.anzahl_monate * 12)
                        : 0
                      if (jahresErsparnis <= 0) return '∞'
                      const jahre = investition.anschaffungskosten_gesamt! / jahresErsparnis
                      return `${jahre.toFixed(1)} Jahre`
                    })()}
                  </p>
                </div>
              </div>
            </div>
          )}
        </>
      )}
    </Card>
  )
}
