/**
 * Wallbox
 * Zeigt: Heimladung (aus E-Auto-Daten), PV-Anteil, Ersparnis vs. externe Ladung
 * Die Wallbox ist Infrastruktur - ihr ROI entsteht durch günstiges Heimladen.
 */

import { Fragment, useState, useEffect } from 'react'
import { Plug, Zap, Leaf, TrendingUp, Home, MapPin } from 'lucide-react'
import { Card, LoadingSpinner, Alert, Select, KPICard } from '../components/ui'
import { useSelectedAnlage } from '../hooks'
import type { Anlage } from '../types'
import { investitionenApi } from '../api'
import { LADEQUELLEN_FARBEN } from '../lib'
import type { WallboxDashboardResponse } from '../api/investitionen'
import { WallboxWirtschaftlichkeit } from '../components/wallbox'
import { Tooltip, ResponsiveContainer, PieChart, Pie, Cell } from 'recharts'
import ChartTooltip from '../components/ui/ChartTooltip'

export default function WallboxDashboard() {
  const { anlagen, selectedAnlageId, setSelectedAnlageId, loading: anlagenLoading } = useSelectedAnlage()
  const [dashboards, setDashboards] = useState<WallboxDashboardResponse[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

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
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Wallbox</h1>
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
        <LoadingSpinner text="Lade Wallbox Daten..." />
      ) : dashboards.length === 0 ? (
        <>
          <PlaceholderHeader showSelector={showSelector} {...selectorProps} />
          <Card>
            <div className="text-center py-8 text-gray-500 dark:text-gray-400">
              <Plug className="h-12 w-12 mx-auto mb-4 opacity-50" />
              <p>Keine Wallbox für diese Anlage erfasst.</p>
              <p className="text-sm mt-2">Füge eine Wallbox unter "Einstellungen → Investitionen" hinzu.</p>
            </div>
          </Card>
        </>
      ) : (
        dashboards.map((dashboard, idx) => (
          <Fragment key={dashboard.investition.id}>
            {idx > 0 && <hr className="border-t border-gray-200 dark:border-gray-700" />}
            <WallboxBlock
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
    <div className="flex items-center justify-between flex-wrap gap-4">
      <div className="flex items-center gap-3 min-w-0">
        <Plug className="h-8 w-8 text-cyan-500 flex-shrink-0" />
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white truncate">Wallbox</h1>
      </div>
      <AnlageSelector {...props} />
    </div>
  )
}

function WallboxBlock({ dashboard, ...selectorProps }: { dashboard: WallboxDashboardResponse } & SelectorProps) {
  const { investition, zusammenfassung } = dashboard
  const z = zusammenfassung

  // PieChart Daten: Heimladung vs Extern
  const ladungPieData = [
    { name: 'Heim: PV', value: z.ladung_pv_kwh || 0 },
    { name: 'Heim: Netz', value: z.ladung_netz_kwh || 0 },
    { name: 'Extern', value: z.extern_ladung_kwh || 0 },
  ].filter(d => d.value > 0)

  const leistungKw = z.leistung_kw || 11
  const hatDaten = (z.gesamt_heim_ladung_kwh || 0) > 0

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div className="flex items-center gap-3 min-w-0">
          <Plug className="h-8 w-8 text-cyan-500 flex-shrink-0" />
          <div className="min-w-0">
            <h1 className="text-2xl font-bold text-gray-900 dark:text-white truncate">
              {investition.bezeichnung}
            </h1>
            <p className="text-sm text-gray-500 dark:text-gray-400">
              {leistungKw} kW Ladeleistung • {z.anzahl_monate || 0} Monate Daten
            </p>
          </div>
        </div>
        <AnlageSelector {...selectorProps} />
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
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3 sm:gap-4">
            <KPICard
              title="Heimladung"
              value={((z.gesamt_heim_ladung_kwh || 0) / 1000).toFixed(2)}
              unit="MWh"
              subtitle="PV + Netz"
              icon={Home}
              color="purple"
              formel="Heimladung = PV + Netz"
              berechnung={`${(z.ladung_pv_kwh || 0).toFixed(0)} + ${(z.ladung_netz_kwh || 0).toFixed(0)} kWh`}
              ergebnis={`= ${(z.gesamt_heim_ladung_kwh || 0).toFixed(0)} kWh`}
            />
            <KPICard
              title="PV-Anteil"
              value={(z.pv_anteil_prozent || 0).toFixed(0)}
              unit="%"
              subtitle={`${(z.ladung_pv_kwh || 0).toFixed(0)} kWh`}
              icon={Leaf}
              color="green"
              formel="PV-Anteil = PV ÷ Heimladung × 100"
              berechnung={`${(z.ladung_pv_kwh || 0).toFixed(0)} kWh ÷ ${(z.gesamt_heim_ladung_kwh || 0).toFixed(0)} kWh × 100`}
              ergebnis={`= ${(z.pv_anteil_prozent || 0).toFixed(1)} %`}
            />
            <KPICard
              title="Ersparnis vs. Extern"
              value={(z.ersparnis_vs_extern_euro || 0).toFixed(0)}
              unit="€"
              subtitle="Wallbox-ROI"
              icon={TrendingUp}
              color="green"
              trend={(z.ersparnis_vs_extern_euro || 0) > 0 ? 'up' : undefined}
              formel="Ersparnis = Extern-Kosten − Heim-Kosten"
              berechnung={`${(z.heim_als_extern_kosten_euro || 0).toFixed(0)} € − ${(z.heim_kosten_euro || 0).toFixed(0)} €`}
              ergebnis={`= ${(z.ersparnis_vs_extern_euro || 0).toFixed(2)} €`}
            />
            <KPICard
              title="Ladevorgänge"
              value={(z.gesamt_ladevorgaenge || 0).toString()}
              subtitle={`Ø ${(z.ladevorgaenge_pro_monat || 0).toFixed(1)}/Monat`}
              icon={Zap}
              color="blue"
              formel="Σ Ladevorgänge"
              berechnung={`${z.anzahl_monate || 0} Monate`}
              ergebnis={`= ${z.gesamt_ladevorgaenge || 0} Vorgänge`}
            />
          </div>

          {/* Ladequelle */}
          <div>
            <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-4">
              Ladequelle
            </h3>
            <div className="h-64 max-w-md">
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
                    label={({ name, percent }) => `${name}: ${(percent * 100).toFixed(0)} %`}
                  >
                    <Cell fill={LADEQUELLEN_FARBEN.pv} /> {/* PV: grün */}
                    <Cell fill={LADEQUELLEN_FARBEN.netz} /> {/* Netz: dunkelrot */}
                    <Cell fill={LADEQUELLEN_FARBEN.extern} /> {/* Extern: orange */}
                  </Pie>
                  <Tooltip content={<ChartTooltip unit="kWh" decimals={1} />} />
                </PieChart>
              </ResponsiveContainer>
            </div>
            <div className="flex gap-4 text-sm flex-wrap">
              <span className="flex items-center gap-2">
                <Home className="h-4 w-4 text-purple-500" />
                Heim: {(z.gesamt_heim_ladung_kwh || 0).toFixed(0)} kWh
              </span>
              {(z.extern_ladung_kwh || 0) > 0 && (
                <span className="flex items-center gap-2">
                  <MapPin className="h-4 w-4 text-orange-500" />
                  Extern: {(z.extern_ladung_kwh || 0).toFixed(0)} kWh
                </span>
              )}
            </div>
          </div>

          {/* Wirtschaftlichkeit: Kostenvergleich + ROI-Erklärung + Amortisation */}
          <WallboxWirtschaftlichkeit zusammenfassung={z} investition={investition} />
        </>
      )}
    </div>
  )
}
