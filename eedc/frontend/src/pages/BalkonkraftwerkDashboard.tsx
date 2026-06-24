/**
 * Balkonkraftwerk
 * Zeigt Statistiken: Erzeugung, Eigenverbrauch, Einspeisung, Ersparnis
 */

import { Fragment, useState, useEffect } from 'react'
import { Sun, Zap, TrendingUp, Home, Leaf, Battery } from 'lucide-react'
import { Card, LoadingSpinner, Alert, Select, KPICard } from '../components/ui'
import ChartTooltip from '../components/ui/ChartTooltip'
import { useSelectedAnlage } from '../hooks'
import type { Anlage } from '../types'
import { CHART_COLORS } from '../lib'
import { investitionenApi } from '../api'
import type { BalkonkraftwerkDashboardResponse } from '../api/investitionen'
import { BkwErzeugungVerlauf, BkwSpeicherVerlauf, BkwMonatsTabelle } from '../components/balkonkraftwerk'
import { Tooltip, ResponsiveContainer, PieChart, Pie, Cell } from 'recharts'

export default function BalkonkraftwerkDashboard() {
  const { anlagen, selectedAnlageId, setSelectedAnlageId, loading: anlagenLoading } = useSelectedAnlage()
  const [dashboards, setDashboards] = useState<BalkonkraftwerkDashboardResponse[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

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
        <Alert type="warning">Bitte zuerst eine Anlage anlegen.</Alert>
      </div>
    )
  }

  const showSelector = anlagen.length > 1
  const selectorProps = { anlagen, selectedAnlageId, setSelectedAnlageId }

  return (
    <div className="space-y-6">
      {error && <Alert type="error">{error}</Alert>}

      {loading ? (
        <LoadingSpinner text="Lade Balkonkraftwerk Daten..." />
      ) : dashboards.length === 0 ? (
        <>
          <PlaceholderHeader showSelector={showSelector} {...selectorProps} />
          <Card>
            <div className="text-center py-8 text-gray-500 dark:text-gray-400">
              <Sun className="h-12 w-12 mx-auto mb-4 opacity-50" />
              <p>Kein Balkonkraftwerk für diese Anlage erfasst.</p>
              <p className="text-sm mt-2">Füge ein Balkonkraftwerk unter "Investitionen" hinzu.</p>
            </div>
          </Card>
        </>
      ) : (
        dashboards.map((dashboard, idx) => (
          <Fragment key={dashboard.investition.id}>
            {idx > 0 && <hr className="border-t border-gray-200 dark:border-gray-700" />}
            <BalkonkraftwerkBlock
              dashboard={dashboard}
              showSelector={idx === 0 && showSelector}
              {...selectorProps}
            />
          </Fragment>
        ))
      )}
    </div>
  )
}

interface SelectorProps {
  anlagen: Anlage[]
  selectedAnlageId: number | undefined
  setSelectedAnlageId: (id: number) => void
  showSelector: boolean
}

function AnlageSelector({ anlagen, selectedAnlageId, setSelectedAnlageId, showSelector }: SelectorProps) {
  if (!showSelector) return null
  return (
    <Select
      compact
      value={selectedAnlageId?.toString() || ''}
      onChange={(e) => setSelectedAnlageId(parseInt(e.target.value))}
      options={anlagen.map(a => ({ value: a.id.toString(), label: a.anlagenname }))}
    />
  )
}

function PlaceholderHeader(props: SelectorProps) {
  return (
    <div className="flex items-center justify-end flex-wrap gap-4">
      <AnlageSelector {...props} />
    </div>
  )
}

function BalkonkraftwerkBlock({ dashboard, ...selectorProps }: { dashboard: BalkonkraftwerkDashboardResponse } & SelectorProps) {
  const { investition, monatsdaten, zusammenfassung } = dashboard
  const z = zusammenfassung

  const verbrauchPieData = [
    { name: 'Eigenverbrauch', value: z.gesamt_eigenverbrauch_kwh, fill: CHART_COLORS.eigenverbrauch },
    { name: 'Einspeisung', value: z.gesamt_einspeisung_kwh, fill: CHART_COLORS.einspeisung },
  ]

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div className="flex items-center gap-3 min-w-0">
          <Sun className="h-8 w-8 text-amber-400 flex-shrink-0" />
          <div className="min-w-0">
            <h1 className="text-2xl font-bold text-gray-900 dark:text-white truncate">
              {investition.bezeichnung}
            </h1>
            <p className="text-sm text-gray-500 dark:text-gray-400">
              {z.leistung_wp} Wp • {z.anzahl_module} Module • {z.anzahl_monate} Monate Daten
              {z.hat_speicher && ` • ${z.speicher_kapazitaet_wh} Wh Speicher`}
            </p>
          </div>
        </div>
        <AnlageSelector {...selectorProps} />
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3 sm:gap-4">
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
      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3 sm:gap-4">
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
                  label={({ name, percent }) => `${name}: ${(percent * 100).toFixed(0)} %`}
                >
                  {verbrauchPieData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={entry.fill} />
                  ))}
                </Pie>
                <Tooltip content={<ChartTooltip unit="kWh" />} />
              </PieChart>
            </ResponsiveContainer>
          </div>
          <div className="flex justify-center gap-6 text-sm">
            <span className="flex items-center gap-2">
              <span className="w-3 h-3 rounded-full bg-violet-500"></span>
              Eigenverbrauch: {z.gesamt_eigenverbrauch_kwh.toFixed(0)} kWh
            </span>
            <span className="flex items-center gap-2">
              <span className="w-3 h-3 rounded-full bg-emerald-500"></span>
              Einspeisung: {z.gesamt_einspeisung_kwh.toFixed(0)} kWh
            </span>
          </div>
        </div>

        {/* Erzeugung pro Monat */}
        <div>
          <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-4">
            Erzeugung pro Monat (kWh)
          </h3>
          <BkwErzeugungVerlauf monatsdaten={monatsdaten} />
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
                {z.speicher_effizienz_prozent.toFixed(1)} %
              </p>
            </div>
          </div>

          {/* Speicher Chart */}
          <div className="mt-4">
            <BkwSpeicherVerlauf monatsdaten={monatsdaten} />
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
        <div className="mt-4">
          <BkwMonatsTabelle monatsdaten={monatsdaten} hatSpeicher={z.hat_speicher} />
        </div>
      </details>
    </div>
  )
}
