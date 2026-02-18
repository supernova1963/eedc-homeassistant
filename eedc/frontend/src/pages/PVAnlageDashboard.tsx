/**
 * PV-Anlage Dashboard (Gesamtlaufzeit)
 *
 * Zeigt aggregierte PV-System-Daten über die gesamte Laufzeit:
 * - KPIs: Anlagenleistung, Gesamterzeugung, spez. Ertrag, Eigenverbrauch
 * - Jahresübersicht: Erzeugung/Eigenverbrauch/Einspeisung pro Jahr
 * - Energieverteilung: Pie-Chart Eigenverbrauch vs Einspeisung
 * - SOLL-IST Vergleich pro String (neue Gesamtlaufzeit-Komponente)
 */

import { useState, useEffect, useMemo } from 'react'
import { Sun, Zap, TrendingUp, Activity, BarChart3, AlertTriangle } from 'lucide-react'
import { Card, LoadingSpinner, Alert, Select, KPICard, fmtCalc } from '../components/ui'
import { useAnlagen, useInvestitionen } from '../hooks'
import { cockpitApi, type CockpitUebersicht } from '../api/cockpit'
import { monatsdatenApi, type AggregierteMonatsdaten } from '../api/monatsdaten'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
  PieChart, Pie, Cell
} from 'recharts'
import type { Investition } from '../types'
import { PVStringVergleich } from '../components/pv'

const COLORS = {
  solar: '#f59e0b',
  feedin: '#10b981',
  consumption: '#8b5cf6',
}

interface PVSystem {
  wechselrichter: Investition
  pvModule: Investition[]
  speicher: Investition[]
  gesamtKwp: number
}

export default function PVAnlageDashboard() {
  const { anlagen, loading: anlagenLoading } = useAnlagen()
  const [selectedAnlageId, setSelectedAnlageId] = useState<number | undefined>()
  const [cockpitData, setCockpitData] = useState<CockpitUebersicht | null>(null)
  const [aggregierteDaten, setAggregierteDaten] = useState<AggregierteMonatsdaten[]>([])
  const [cockpitLoading, setCockpitLoading] = useState(true)

  useEffect(() => {
    if (anlagen.length > 0 && !selectedAnlageId) {
      setSelectedAnlageId(anlagen[0].id)
    }
  }, [anlagen, selectedAnlageId])

  const { investitionen, loading: invLoading } = useInvestitionen(selectedAnlageId)

  // Cockpit-Daten und aggregierte Monatsdaten laden (Gesamtlaufzeit)
  useEffect(() => {
    if (!selectedAnlageId) return

    const loadData = async () => {
      setCockpitLoading(true)
      try {
        const [cockpit, aggregiert] = await Promise.all([
          cockpitApi.getUebersicht(selectedAnlageId),
          monatsdatenApi.listAggregiert(selectedAnlageId),
        ])
        setCockpitData(cockpit)
        setAggregierteDaten(aggregiert)
      } catch (err) {
        console.error('Fehler beim Laden der Daten:', err)
      } finally {
        setCockpitLoading(false)
      }
    }

    loadData()
  }, [selectedAnlageId])

  // PV-Systeme gruppieren (Wechselrichter + zugeordnete Module)
  const { pvSysteme, orphanModule } = useMemo(() => {
    const systeme: PVSystem[] = []
    const orphanMod: Investition[] = []

    const wechselrichter = investitionen.filter(i => i.typ === 'wechselrichter')
    const pvModule = investitionen.filter(i => i.typ === 'pv-module')
    const speicher = investitionen.filter(i => i.typ === 'speicher')

    for (const wr of wechselrichter) {
      const zugeordneteModule = pvModule.filter(m => m.parent_investition_id === wr.id)
      const zugeordneteSpeicher = speicher.filter(s => s.parent_investition_id === wr.id)
      const gesamtKwp = zugeordneteModule.reduce((sum, m) => sum + (m.leistung_kwp || 0), 0)

      systeme.push({
        wechselrichter: wr,
        pvModule: zugeordneteModule,
        speicher: zugeordneteSpeicher,
        gesamtKwp
      })
    }

    for (const m of pvModule) {
      if (!m.parent_investition_id || !wechselrichter.find(wr => wr.id === m.parent_investition_id)) {
        orphanMod.push(m)
      }
    }

    return { pvSysteme: systeme, orphanModule: orphanMod }
  }, [investitionen])

  // Daten aus Cockpit-API
  const gesamtKwp = cockpitData?.anlagenleistung_kwp || 0
  const gesamtErzeugung = cockpitData?.pv_erzeugung_kwh || 0
  const gesamtEigenverbrauch = cockpitData?.eigenverbrauch_kwh || 0
  const gesamtEinspeisung = cockpitData?.einspeisung_kwh || 0
  const spezifischerErtrag = cockpitData?.spezifischer_ertrag_kwh_kwp || 0
  const eigenverbrauchsQuote = cockpitData?.eigenverbrauch_quote_prozent || 0
  const anzahlMonate = cockpitData?.anzahl_monate || 0
  const zeitraumVon = cockpitData?.zeitraum_von
  const zeitraumBis = cockpitData?.zeitraum_bis

  // Chart-Daten: Jahresübersicht
  const jahresChartData = useMemo(() => {
    if (aggregierteDaten.length === 0) return []

    const byYear = new Map<number, { erzeugung: number; eigenverbrauch: number; einspeisung: number }>()

    for (const md of aggregierteDaten) {
      if (!byYear.has(md.jahr)) {
        byYear.set(md.jahr, { erzeugung: 0, eigenverbrauch: 0, einspeisung: 0 })
      }
      const y = byYear.get(md.jahr)!
      y.erzeugung += md.pv_erzeugung_kwh || 0
      y.eigenverbrauch += md.eigenverbrauch_kwh || 0
      y.einspeisung += md.einspeisung_kwh || 0
    }

    return [...byYear.entries()]
      .sort((a, b) => a[0] - b[0])
      .map(([jahr, data]) => ({
        name: jahr.toString(),
        Erzeugung: Math.round(data.erzeugung),
        Eigenverbrauch: Math.round(data.eigenverbrauch),
        Einspeisung: Math.round(data.einspeisung),
      }))
  }, [aggregierteDaten])

  // Pie-Chart: Energieverteilung
  const verteilungData = useMemo(() => {
    if (gesamtErzeugung === 0) return []
    return [
      { name: 'Eigenverbrauch', value: gesamtEigenverbrauch, color: COLORS.consumption },
      { name: 'Einspeisung', value: gesamtEinspeisung, color: COLORS.feedin },
    ]
  }, [gesamtErzeugung, gesamtEigenverbrauch, gesamtEinspeisung])

  const loading = anlagenLoading || invLoading || cockpitLoading
  const hasData = gesamtErzeugung > 0
  const hasPVSystem = pvSysteme.length > 0 || orphanModule.length > 0
  const hasMultipleYears = jahresChartData.length > 1

  if (loading) return <LoadingSpinner text="Lade PV-Anlage..." />

  if (anlagen.length === 0) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">PV-Anlage</h1>
        <Alert type="warning">Bitte zuerst eine Anlage anlegen.</Alert>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div className="flex items-center gap-3">
          <Sun className="h-8 w-8 text-yellow-500" />
          <div>
            <h1 className="text-2xl font-bold text-gray-900 dark:text-white">PV-Anlage</h1>
            {zeitraumVon && zeitraumBis && (
              <p className="text-sm text-gray-500 dark:text-gray-400">
                Gesamtlaufzeit: {zeitraumVon} bis {zeitraumBis} ({anzahlMonate} Monate)
              </p>
            )}
          </div>
        </div>
        {anlagen.length > 1 && (
          <Select
            value={selectedAnlageId?.toString() || ''}
            onChange={(e) => setSelectedAnlageId(parseInt(e.target.value))}
            options={anlagen.map(a => ({ value: a.id.toString(), label: a.anlagenname }))}
          />
        )}
      </div>

      {/* Warnungen */}
      {orphanModule.length > 0 && (
        <Alert type="warning">
          <div className="flex items-center gap-2">
            <AlertTriangle className="h-4 w-4" />
            <span>
              {orphanModule.length} PV-Modul(e) ohne Wechselrichter-Zuordnung.
            </span>
          </div>
        </Alert>
      )}

      {!hasPVSystem && (
        <Alert type="info">
          Keine PV-Komponenten gefunden. Bitte unter Einstellungen → Investitionen anlegen.
        </Alert>
      )}

      {/* KPI Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <KPICard
          title="Anlagenleistung"
          value={gesamtKwp > 0 ? gesamtKwp.toFixed(1) : '---'}
          unit="kWp"
          subtitle={`${pvSysteme.length} WR, ${pvSysteme.reduce((s, p) => s + p.pvModule.length, 0) + orphanModule.length} Module`}
          icon={Sun}
          color="yellow"
        />
        <KPICard
          title="Gesamterzeugung"
          value={gesamtErzeugung > 0 ? (gesamtErzeugung / 1000).toFixed(1) : '---'}
          unit="MWh"
          subtitle={anzahlMonate > 0 ? `${anzahlMonate} Monate Gesamtlaufzeit` : undefined}
          icon={Zap}
          color="green"
        />
        <KPICard
          title="Spez. Ertrag"
          value={spezifischerErtrag > 0 ? spezifischerErtrag.toFixed(0) : '---'}
          unit="kWh/kWp"
          subtitle="Durchschnitt Gesamtlaufzeit"
          icon={TrendingUp}
          color="blue"
          formel="Spez. Ertrag = Erzeugung ÷ Leistung"
          berechnung={`${fmtCalc(gesamtErzeugung, 0)} kWh ÷ ${fmtCalc(gesamtKwp, 1)} kWp`}
          ergebnis={`= ${fmtCalc(spezifischerErtrag, 0)} kWh/kWp`}
        />
        <KPICard
          title="Eigenverbrauch"
          value={eigenverbrauchsQuote > 0 ? eigenverbrauchsQuote.toFixed(1) : '---'}
          unit="%"
          subtitle={gesamtEigenverbrauch > 0 ? `${(gesamtEigenverbrauch / 1000).toFixed(1)} MWh` : undefined}
          icon={Activity}
          color="purple"
        />
      </div>

      {/* PV-Komponenten */}
      {hasPVSystem && (
        <Card>
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
            PV-Komponenten
          </h2>
          <div className="space-y-4">
            {pvSysteme.map((system) => (
              <div key={system.wechselrichter.id} className="border border-gray-200 dark:border-gray-700 rounded-lg p-4">
                <div className="flex items-center justify-between mb-2">
                  <h3 className="font-medium text-gray-900 dark:text-white">
                    {system.wechselrichter.bezeichnung}
                  </h3>
                  <span className="text-sm text-gray-500">{system.gesamtKwp.toFixed(1)} kWp</span>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-2 text-sm">
                  {system.pvModule.map(mod => (
                    <div key={mod.id} className="flex items-center gap-2 text-gray-600 dark:text-gray-400">
                      <Sun className="h-4 w-4 text-yellow-500" />
                      <span>{mod.bezeichnung}</span>
                      <span className="text-gray-400">
                        {mod.leistung_kwp?.toFixed(1)} kWp
                        {mod.ausrichtung && ` • ${mod.ausrichtung}`}
                      </span>
                    </div>
                  ))}
                  {system.speicher.map(sp => (
                    <div key={sp.id} className="flex items-center gap-2 text-gray-600 dark:text-gray-400">
                      <Zap className="h-4 w-4 text-blue-500" />
                      <span>{sp.bezeichnung}</span>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* Charts: Jahresübersicht + Energieverteilung */}
      {hasData && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <Card className="lg:col-span-2">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
              {hasMultipleYears ? 'Jahresübersicht (Gesamtlaufzeit)' : 'Jahresübersicht'}
            </h2>
            <div className="h-72">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={jahresChartData}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="name" />
                  <YAxis unit=" kWh" />
                  <Tooltip formatter={(value: number) => [`${value.toLocaleString()} kWh`]} />
                  <Legend />
                  <Bar dataKey="Erzeugung" fill={COLORS.solar} />
                  <Bar dataKey="Eigenverbrauch" fill={COLORS.consumption} />
                  <Bar dataKey="Einspeisung" fill={COLORS.feedin} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </Card>

          <Card>
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
              Energieverteilung
            </h2>
            <div className="h-72">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={verteilungData}
                    dataKey="value"
                    nameKey="name"
                    cx="50%"
                    cy="50%"
                    innerRadius={50}
                    outerRadius={80}
                    label={({ name, percent }) => `${name}: ${(percent * 100).toFixed(0)}%`}
                    labelLine={false}
                  >
                    {verteilungData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={entry.color} />
                    ))}
                  </Pie>
                  <Tooltip formatter={(value: number) => [`${value.toLocaleString()} kWh`]} />
                </PieChart>
              </ResponsiveContainer>
            </div>
            <div className="mt-4 space-y-2 text-sm">
              <div className="flex justify-between">
                <span className="text-gray-500">Eigenverbrauch:</span>
                <span className="font-medium">{(gesamtEigenverbrauch / 1000).toFixed(1)} MWh</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">Einspeisung:</span>
                <span className="font-medium">{(gesamtEinspeisung / 1000).toFixed(1)} MWh</span>
              </div>
            </div>
          </Card>
        </div>
      )}

      {!hasData && hasPVSystem && (
        <Card className="text-center py-12">
          <BarChart3 className="h-12 w-12 mx-auto text-gray-400 mb-4" />
          <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-2">
            Noch keine Monatsdaten vorhanden
          </h3>
          <p className="text-gray-500 dark:text-gray-400">
            Erfasse Monatsdaten, um Erzeugungsdaten zu sehen.
          </p>
        </Card>
      )}

      {/* SOLL-IST Vergleich (Gesamtlaufzeit) */}
      {hasPVSystem && hasData && selectedAnlageId && (
        <PVStringVergleich anlageId={selectedAnlageId} />
      )}
    </div>
  )
}
