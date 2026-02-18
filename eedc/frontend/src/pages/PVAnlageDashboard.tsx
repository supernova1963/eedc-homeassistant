/**
 * PV-Anlage Dashboard
 * Zeigt aggregierte PV-System-Daten: Wechselrichter + PV-Module + DC-Speicher
 * Inkl. Erzeugung, spezifischer Ertrag, String-Vergleich, PVGIS-Abweichung
 *
 * Datenquellen:
 * - Cockpit-API: Aggregierte KPIs (pv_erzeugung aus InvestitionMonatsdaten)
 * - Aggregierte Monatsdaten-API: Jahresübersicht
 */

import { useState, useEffect, useMemo } from 'react'
import { Sun, Zap, TrendingUp, Activity, BarChart3, AlertTriangle, GitCompare, Calendar } from 'lucide-react'
import { Card, LoadingSpinner, Alert, Select, KPICard, fmtCalc } from '../components/ui'
import { useAnlagen, useInvestitionen } from '../hooks'
import { cockpitApi, type CockpitUebersicht } from '../api/cockpit'
import { monatsdatenApi, type AggregierteMonatsdaten } from '../api/monatsdaten'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
  AreaChart, Area, PieChart, Pie, Cell
} from 'recharts'
import type { Investition } from '../types'
import { PVStringVergleich } from '../components/pv'

const monatNamen = ['', 'Jan', 'Feb', 'Mär', 'Apr', 'Mai', 'Jun', 'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Dez']

const COLORS = {
  solar: '#f59e0b',
  feedin: '#10b981',
  consumption: '#8b5cf6',
  grid: '#ef4444',
}

const STRING_COLORS = ['#f59e0b', '#3b82f6', '#10b981', '#8b5cf6', '#06b6d4', '#ec4899']

interface PVSystem {
  wechselrichter: Investition
  pvModule: Investition[]
  speicher: Investition[]
  gesamtKwp: number
}

export default function PVAnlageDashboard() {
  const { anlagen, loading: anlagenLoading } = useAnlagen()
  const [selectedAnlageId, setSelectedAnlageId] = useState<number | undefined>()

  // Cockpit-Daten (aggregierte KPIs aus InvestitionMonatsdaten)
  const [cockpitData, setCockpitData] = useState<CockpitUebersicht | null>(null)
  const [aggregierteDaten, setAggregierteDaten] = useState<AggregierteMonatsdaten[]>([])
  const [cockpitLoading, setCockpitLoading] = useState(true)

  useEffect(() => {
    if (anlagen.length > 0 && !selectedAnlageId) {
      setSelectedAnlageId(anlagen[0].id)
    }
  }, [anlagen, selectedAnlageId])

  const { investitionen, loading: invLoading } = useInvestitionen(selectedAnlageId)

  // Verfügbare Jahre und neuestes Jahr für String-Vergleich
  const { availableYears, latestYear } = useMemo(() => {
    if (aggregierteDaten.length === 0) {
      return { availableYears: [], latestYear: new Date().getFullYear() }
    }
    const years = [...new Set(aggregierteDaten.map(md => md.jahr))].sort((a, b) => b - a)
    return { availableYears: years, latestYear: years[0] }
  }, [aggregierteDaten])

  // Jahr-Auswahl für String-Vergleich (Standard: neuestes Jahr)
  const [selectedStringYear, setSelectedStringYear] = useState<number | undefined>(undefined)
  useEffect(() => {
    if (latestYear && !selectedStringYear) {
      setSelectedStringYear(latestYear)
    }
  }, [latestYear, selectedStringYear])

  // Cockpit-Daten und aggregierte Monatsdaten laden
  // WICHTIG: OHNE Jahr-Filter für Gesamtlaufzeit-Übersicht
  useEffect(() => {
    if (!selectedAnlageId) return

    const loadData = async () => {
      setCockpitLoading(true)
      try {
        // Cockpit-Übersicht für ALLE Jahre (Gesamtlaufzeit)
        const cockpit = await cockpitApi.getUebersicht(selectedAnlageId, undefined)
        setCockpitData(cockpit)

        // Aggregierte Monatsdaten für Charts (alle Jahre)
        const aggregiert = await monatsdatenApi.listAggregiert(selectedAnlageId)
        setAggregierteDaten(aggregiert)
      } catch (err) {
        console.error('Fehler beim Laden der Daten:', err)
      } finally {
        setCockpitLoading(false)
      }
    }

    loadData()
  }, [selectedAnlageId])

  // PV-Systeme gruppieren (Wechselrichter + zugeordnete Module + Speicher)
  const { pvSysteme, orphanModule } = useMemo(() => {
    const systeme: PVSystem[] = []
    const orphanMod: Investition[] = []

    // Wechselrichter finden
    const wechselrichter = investitionen.filter(i => i.typ === 'wechselrichter')
    const pvModule = investitionen.filter(i => i.typ === 'pv-module')
    const speicher = investitionen.filter(i => i.typ === 'speicher')

    // Für jeden Wechselrichter: zugeordnete Module und Speicher sammeln
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

    // Orphan Module (ohne Wechselrichter-Zuordnung)
    for (const m of pvModule) {
      if (!m.parent_investition_id || !wechselrichter.find(wr => wr.id === m.parent_investition_id)) {
        orphanMod.push(m)
      }
    }

    return { pvSysteme: systeme, orphanModule: orphanMod }
  }, [investitionen])

  // Gesamt-kWp aus Cockpit-Daten (oder Investitionen als Fallback)
  const gesamtKwp = cockpitData?.anlagenleistung_kwp || (
    pvSysteme.reduce((sum, sys) => sum + sys.gesamtKwp, 0) +
    orphanModule.reduce((sum, m) => sum + (m.leistung_kwp || 0), 0)
  )

  // Daten aus Cockpit-API (aus InvestitionMonatsdaten aggregiert)
  const gesamtErzeugung = cockpitData?.pv_erzeugung_kwh || 0
  const gesamtEigenverbrauch = cockpitData?.eigenverbrauch_kwh || 0
  const gesamtEinspeisung = cockpitData?.einspeisung_kwh || 0
  const spezifischerErtrag = cockpitData?.spezifischer_ertrag_kwh_kwp || 0
  const eigenverbrauchsQuote = cockpitData?.eigenverbrauch_quote_prozent || 0
  const anzahlMonate = cockpitData?.anzahl_monate || 0
  const zeitraumVon = cockpitData?.zeitraum_von
  const zeitraumBis = cockpitData?.zeitraum_bis

  // Chart-Daten: Jahresübersicht (Gesamtlaufzeit)
  const jahresChartData = useMemo(() => {
    if (aggregierteDaten.length === 0) return []

    // Nach Jahren gruppieren
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

  // Chart-Daten: Monatlicher Verlauf (für gewähltes Jahr im String-Vergleich)
  const monatsChartData = useMemo(() => {
    if (aggregierteDaten.length === 0 || !selectedStringYear) return []

    return aggregierteDaten
      .filter(md => md.jahr === selectedStringYear)
      .sort((a, b) => a.monat - b.monat)
      .map(md => ({
        name: monatNamen[md.monat],
        Erzeugung: Math.round(md.pv_erzeugung_kwh || 0),
        Eigenverbrauch: Math.round(md.eigenverbrauch_kwh || 0),
        Einspeisung: Math.round(md.einspeisung_kwh || 0),
      }))
  }, [aggregierteDaten, selectedStringYear])

  // Energieverteilung Pie-Chart
  const verteilungData = useMemo(() => {
    if (gesamtErzeugung === 0) return []
    return [
      { name: 'Eigenverbrauch', value: gesamtEigenverbrauch, color: COLORS.consumption },
      { name: 'Einspeisung', value: gesamtEinspeisung, color: COLORS.feedin },
    ]
  }, [gesamtErzeugung, gesamtEigenverbrauch, gesamtEinspeisung])

  // String-Vergleich (wenn mehrere PV-Module mit unterschiedlicher Ausrichtung)
  const stringVergleich = useMemo(() => {
    const alleModule = pvSysteme.flatMap(s => s.pvModule).concat(orphanModule)
    const byAusrichtung: Record<string, { kwp: number; count: number }> = {}

    for (const mod of alleModule) {
      const ausrichtung = mod.ausrichtung || 'Unbekannt'
      if (!byAusrichtung[ausrichtung]) {
        byAusrichtung[ausrichtung] = { kwp: 0, count: 0 }
      }
      byAusrichtung[ausrichtung].kwp += mod.leistung_kwp || 0
      byAusrichtung[ausrichtung].count += 1
    }

    return Object.entries(byAusrichtung).map(([ausrichtung, data], idx) => ({
      ausrichtung,
      kwp: data.kwp,
      count: data.count,
      color: STRING_COLORS[idx % STRING_COLORS.length]
    }))
  }, [pvSysteme, orphanModule])

  const loading = anlagenLoading || invLoading || cockpitLoading

  if (loading) return <LoadingSpinner text="Lade PV-Anlage..." />

  if (anlagen.length === 0) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">PV-Anlage</h1>
        <Alert type="warning">Bitte zuerst eine Anlage anlegen.</Alert>
      </div>
    )
  }

  const hasData = gesamtErzeugung > 0
  const hasPVSystem = pvSysteme.length > 0 || orphanModule.length > 0
  const hasMultipleYears = availableYears.length > 1

  return (
    <div className="space-y-6">
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
              Bitte unter Einstellungen → Investitionen zuordnen.
            </span>
          </div>
        </Alert>
      )}

      {!hasPVSystem && (
        <Alert type="info">
          Keine PV-Komponenten gefunden. Bitte unter Einstellungen → Investitionen
          Wechselrichter und PV-Module anlegen.
        </Alert>
      )}

      {/* KPI Cards - Daten aus Cockpit-API (Gesamtlaufzeit) */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <KPICard
          title="Anlagenleistung"
          value={gesamtKwp > 0 ? gesamtKwp.toFixed(1) : '---'}
          unit="kWp"
          subtitle={`${pvSysteme.length} Wechselrichter, ${pvSysteme.reduce((s, p) => s + p.pvModule.length, 0) + orphanModule.length} Module`}
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
          formel="Eigenverbrauchsquote = Eigenverbrauch ÷ Erzeugung × 100"
          berechnung={`${fmtCalc(gesamtEigenverbrauch, 0)} kWh ÷ ${fmtCalc(gesamtErzeugung, 0)} kWh × 100`}
          ergebnis={`= ${fmtCalc(eigenverbrauchsQuote, 1)} %`}
        />
      </div>

      {/* PV-Systeme Details */}
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
                        {mod.neigung_grad && ` • ${mod.neigung_grad}°`}
                      </span>
                    </div>
                  ))}
                  {system.speicher.map(sp => (
                    <div key={sp.id} className="flex items-center gap-2 text-gray-600 dark:text-gray-400">
                      <Zap className="h-4 w-4 text-blue-500" />
                      <span>{sp.bezeichnung}</span>
                      <span className="text-gray-400">
                        {(sp.parameter as Record<string, number>)?.kapazitaet_kwh?.toFixed(1)} kWh
                      </span>
                    </div>
                  ))}
                  {system.pvModule.length === 0 && (
                    <div className="flex items-center gap-2 text-amber-600 dark:text-amber-400">
                      <AlertTriangle className="h-4 w-4" />
                      <span>Keine PV-Module zugeordnet</span>
                    </div>
                  )}
                </div>
              </div>
            ))}

            {/* Orphan Module */}
            {orphanModule.length > 0 && (
              <div className="border border-amber-200 dark:border-amber-700 bg-amber-50 dark:bg-amber-900/20 rounded-lg p-4">
                <h3 className="font-medium text-amber-800 dark:text-amber-200 mb-2 flex items-center gap-2">
                  <AlertTriangle className="h-4 w-4" />
                  Nicht zugeordnete PV-Module
                </h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-2 text-sm">
                  {orphanModule.map(mod => (
                    <div key={mod.id} className="flex items-center gap-2 text-amber-700 dark:text-amber-300">
                      <Sun className="h-4 w-4" />
                      <span>{mod.bezeichnung}</span>
                      <span className="text-amber-500">
                        {mod.leistung_kwp?.toFixed(1)} kWp
                        {mod.ausrichtung && ` • ${mod.ausrichtung}`}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </Card>
      )}

      {/* String-Vergleich nach Ausrichtung */}
      {stringVergleich.length > 1 && (
        <Card>
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
            Leistung nach Ausrichtung
          </h2>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={stringVergleich} layout="vertical">
                <CartesianGrid strokeDasharray="3 3" className="stroke-gray-200 dark:stroke-gray-700" />
                <XAxis type="number" unit=" kWp" />
                <YAxis type="category" dataKey="ausrichtung" width={100} />
                <Tooltip formatter={(value: number) => [`${value.toFixed(1)} kWp`, 'Leistung']} />
                <Bar dataKey="kwp" fill={COLORS.solar} radius={[0, 4, 4, 0]}>
                  {stringVergleich.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={entry.color} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>
      )}

      {/* Charts */}
      {hasData && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Jahresübersicht (Gesamtlaufzeit) */}
          <Card className="lg:col-span-2">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
              {hasMultipleYears ? 'Jahresübersicht (Gesamtlaufzeit)' : `Jahresübersicht ${latestYear}`}
            </h2>
            <div className="h-72">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={jahresChartData}>
                  <CartesianGrid strokeDasharray="3 3" className="stroke-gray-200 dark:stroke-gray-700" />
                  <XAxis dataKey="name" className="text-xs" />
                  <YAxis unit=" kWh" className="text-xs" />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: 'var(--tooltip-bg, #fff)',
                      borderColor: 'var(--tooltip-border, #e5e7eb)',
                    }}
                    formatter={(value: number) => [`${value.toLocaleString()} kWh`, '']}
                  />
                  <Legend />
                  <Bar dataKey="Erzeugung" fill={COLORS.solar} />
                  <Bar dataKey="Eigenverbrauch" fill={COLORS.consumption} />
                  <Bar dataKey="Einspeisung" fill={COLORS.feedin} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </Card>

          {/* Energieverteilung */}
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
                  <Tooltip formatter={(value: number) => [`${value.toLocaleString()} kWh`, '']} />
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

      {/* SOLL-IST String-Vergleich mit Jahr-Auswahl */}
      {hasPVSystem && hasData && selectedAnlageId && (
        <Card>
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white flex items-center gap-2">
              <GitCompare className="h-5 w-5 text-blue-500" />
              SOLL-IST Vergleich pro String
            </h2>
            {availableYears.length > 1 && (
              <div className="flex items-center gap-2">
                <Calendar className="h-4 w-4 text-gray-400" />
                <select
                  value={selectedStringYear || ''}
                  onChange={(e) => setSelectedStringYear(parseInt(e.target.value))}
                  className="input py-1.5 text-sm"
                >
                  {availableYears.map(y => (
                    <option key={y} value={y}>{y}</option>
                  ))}
                </select>
              </div>
            )}
          </div>

          {/* Monatlicher Verlauf für gewähltes Jahr */}
          {monatsChartData.length > 0 && (
            <div className="mb-6">
              <h3 className="text-sm font-medium text-gray-600 dark:text-gray-400 mb-2">
                Monatlicher Verlauf {selectedStringYear}
              </h3>
              <div className="h-48">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={monatsChartData}>
                    <CartesianGrid strokeDasharray="3 3" className="stroke-gray-200 dark:stroke-gray-700" />
                    <XAxis dataKey="name" className="text-xs" />
                    <YAxis unit=" kWh" className="text-xs" />
                    <Tooltip
                      contentStyle={{
                        backgroundColor: 'var(--tooltip-bg, #fff)',
                        borderColor: 'var(--tooltip-border, #e5e7eb)',
                      }}
                      formatter={(value: number) => [`${value.toLocaleString()} kWh`, '']}
                    />
                    <Legend />
                    <Area type="monotone" dataKey="Erzeugung" stroke={COLORS.solar} fill={COLORS.solar} fillOpacity={0.3} />
                    <Area type="monotone" dataKey="Eigenverbrauch" stroke={COLORS.consumption} fill={COLORS.consumption} fillOpacity={0.3} />
                    <Area type="monotone" dataKey="Einspeisung" stroke={COLORS.feedin} fill={COLORS.feedin} fillOpacity={0.3} />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </div>
          )}

          <PVStringVergleich anlageId={selectedAnlageId} jahr={selectedStringYear || latestYear} />
        </Card>
      )}
    </div>
  )
}
