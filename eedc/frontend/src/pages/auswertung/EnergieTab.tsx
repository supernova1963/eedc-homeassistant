// Energie Tab - Monatszeitreihen für Energie-Bilanz und Effizienz
import { useMemo, useState } from 'react'
import {
  Bar, LineChart, Line, ComposedChart,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer
} from 'recharts'
import { Sun, Zap, TrendingUp, Download } from 'lucide-react'
import { Card, Button, fmtCalc } from '../../components/ui'
import { exportToCSV } from '../../utils/export'
import { KPICard } from './KPICard'
import { TabProps, CHART_COLORS, createMonatsZeitreihe } from './types'

export function EnergieTab({ data, stats, anlage, strompreis, zeitraumLabel }: TabProps) {
  const [bilanzView, setBilanzView] = useState<'erzeugung' | 'verbrauch'>('erzeugung')
  const [showAutarkie, setShowAutarkie] = useState(false)

  // Monatszeitreihen erstellen
  const zeitreihe = useMemo(
    () => createMonatsZeitreihe(data, anlage, strompreis),
    [data, anlage, strompreis]
  )

  // CSV Export
  const handleExportCSV = () => {
    const headers = [
      'Monat', 'Erzeugung (kWh)', 'Eigenverbrauch (kWh)', 'Einspeisung (kWh)',
      'Netzbezug (kWh)', 'Autarkie (%)', 'EV-Quote (%)', 'Spez. Ertrag (kWh/kWp)'
    ]
    const rows = zeitreihe.map(z => [
      z.name, z.erzeugung, z.eigenverbrauch, z.einspeisung,
      z.netzbezug, z.autarkie, z.evQuote, z.spezErtrag
    ])
    exportToCSV(headers, rows, `energie_${anlage?.anlagenname || 'export'}.csv`)
  }

  // Netto-Ertrag berechnen
  const nettoErtrag = useMemo(() => {
    if (!strompreis) return null
    const einspeiseErloes = stats.gesamtEinspeisung * strompreis.einspeiseverguetung_cent_kwh / 100
    const evErsparnis = stats.gesamtEigenverbrauch * strompreis.netzbezug_arbeitspreis_cent_kwh / 100
    return einspeiseErloes + evErsparnis
  }, [stats, strompreis])

  return (
    <div className="space-y-6">
      {/* Header mit Zeitraum und Export */}
      <div className="flex items-center justify-between">
        <p className="text-sm text-gray-500 dark:text-gray-400">
          <span className="font-medium text-gray-700 dark:text-gray-300">{zeitraumLabel}</span>
          {' '}&bull;{' '}{stats.anzahlMonate} Monate
        </p>
        <Button variant="secondary" size="sm" onClick={handleExportCSV}>
          <Download className="h-4 w-4 mr-2" />
          CSV Export
        </Button>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <KPICard
          title="PV-Erzeugung"
          value={(stats.gesamtErzeugung / 1000).toFixed(1)}
          unit="MWh"
          icon={Sun}
          color="text-yellow-500"
          bgColor="bg-yellow-50 dark:bg-yellow-900/20"
          formel="Σ PV-Erzeugung aller Monate"
          berechnung={`${fmtCalc(stats.gesamtErzeugung, 0)} kWh`}
          ergebnis={`= ${fmtCalc(stats.gesamtErzeugung / 1000, 1)} MWh`}
        />
        <KPICard
          title="Eigenverbrauch"
          value={stats.gesamtErzeugung > 0 ? ((stats.gesamtEigenverbrauch / stats.gesamtErzeugung) * 100).toFixed(0) : '0'}
          unit="%"
          subtitle={`${(stats.gesamtEigenverbrauch / 1000).toFixed(1)} MWh`}
          icon={Zap}
          color="text-purple-500"
          bgColor="bg-purple-50 dark:bg-purple-900/20"
          formel="Eigenverbrauch ÷ PV-Erzeugung × 100"
          berechnung={`${fmtCalc(stats.gesamtEigenverbrauch, 0)} kWh ÷ ${fmtCalc(stats.gesamtErzeugung, 0)} kWh × 100`}
          ergebnis={`= ${fmtCalc((stats.gesamtEigenverbrauch / stats.gesamtErzeugung) * 100, 1)} %`}
        />
        <KPICard
          title="Autarkie"
          value={stats.durchschnittAutarkie.toFixed(0)}
          unit="%"
          subtitle="Durchschnitt"
          icon={TrendingUp}
          color="text-blue-500"
          bgColor="bg-blue-50 dark:bg-blue-900/20"
          formel="Eigenverbrauch ÷ Gesamtverbrauch × 100"
          berechnung="Durchschnitt aller Monate"
          ergebnis={`= ${fmtCalc(stats.durchschnittAutarkie, 1)} %`}
        />
        <KPICard
          title="Spez. Ertrag"
          value={anlage?.leistung_kwp ? (stats.gesamtErzeugung / anlage.leistung_kwp).toFixed(0) : '---'}
          unit="kWh/kWp"
          subtitle={anlage?.leistung_kwp ? `${anlage.leistung_kwp} kWp` : undefined}
          icon={Sun}
          color="text-amber-500"
          bgColor="bg-amber-50 dark:bg-amber-900/20"
          formel="PV-Erzeugung ÷ Anlagenleistung"
          berechnung={anlage?.leistung_kwp ? `${fmtCalc(stats.gesamtErzeugung, 0)} kWh ÷ ${anlage.leistung_kwp} kWp` : undefined}
          ergebnis={anlage?.leistung_kwp ? `= ${fmtCalc(stats.gesamtErzeugung / anlage.leistung_kwp, 0)} kWh/kWp` : undefined}
        />
      </div>

      {/* Chart 1: Energie-Bilanz (Monatszeitreihe) */}
      <Card>
        <div className="flex items-center justify-between flex-wrap gap-2 mb-4">
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white flex items-center gap-2">
            <Zap className="h-5 w-5 text-blue-500" />
            Energie-Bilanz pro Monat
          </h3>
          <div className="flex items-center gap-2">
            {/* Ansicht-Toggle: Erzeugung / Verbrauch */}
            <div className="flex rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden">
              <button
                onClick={() => setBilanzView('erzeugung')}
                className={`px-3 py-1.5 text-xs font-medium transition-colors ${
                  bilanzView === 'erzeugung'
                    ? 'bg-primary-100 text-primary-700 dark:bg-primary-900/50 dark:text-primary-300'
                    : 'text-gray-600 hover:bg-gray-50 dark:text-gray-400 dark:hover:bg-gray-800'
                }`}
              >
                Erzeugung
              </button>
              <button
                onClick={() => setBilanzView('verbrauch')}
                className={`px-3 py-1.5 text-xs font-medium transition-colors ${
                  bilanzView === 'verbrauch'
                    ? 'bg-primary-100 text-primary-700 dark:bg-primary-900/50 dark:text-primary-300'
                    : 'text-gray-600 hover:bg-gray-50 dark:text-gray-400 dark:hover:bg-gray-800'
                }`}
              >
                Verbrauch
              </button>
            </div>
            {/* Autarkie-Toggle */}
            <button
              onClick={() => setShowAutarkie(!showAutarkie)}
              className={`px-3 py-1.5 text-xs font-medium rounded-lg border transition-colors ${
                showAutarkie
                  ? 'border-blue-300 bg-blue-50 text-blue-700 dark:border-blue-700 dark:bg-blue-900/30 dark:text-blue-300'
                  : 'border-gray-200 text-gray-600 hover:bg-gray-50 dark:border-gray-700 dark:text-gray-400 dark:hover:bg-gray-800'
              }`}
            >
              Autarkie %
            </button>
          </div>
        </div>
        <p className="text-xs text-gray-400 dark:text-gray-500 mb-2">
          {bilanzView === 'erzeugung'
            ? 'Gestapelt: Eigenverbrauch + Einspeisung = PV-Erzeugung'
            : 'Gestapelt: Eigenverbrauch + Netzbezug = Gesamtverbrauch'}
        </p>
        <div className="h-80">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={zeitreihe} margin={{ top: 10, right: 30, left: 0, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" className="stroke-gray-200 dark:stroke-gray-700" />
              <XAxis dataKey="name" tick={{ fontSize: 10 }} interval="preserveStartEnd" />
              <YAxis
                yAxisId="kwh"
                tickFormatter={(v) => `${v.toFixed(0)}`}
                unit=" kWh"
                tick={{ fontSize: 11 }}
              />
              {showAutarkie && (
                <YAxis
                  yAxisId="pct"
                  orientation="right"
                  domain={[0, 100]}
                  unit="%"
                  tick={{ fontSize: 11 }}
                />
              )}
              <Tooltip
                formatter={(value: number, name: string) => {
                  if (name === 'Autarkie') return [`${value.toFixed(1)}%`, name]
                  return [`${value.toFixed(0)} kWh`, name]
                }}
                contentStyle={{ borderRadius: 8, backgroundColor: 'var(--tooltip-bg)', color: 'var(--tooltip-fg)', border: '1px solid var(--tooltip-border)' }}
              />
              <Legend />

              {/* Erzeugung-Ansicht: Eigenverbrauch + Einspeisung gestapelt, Netzbezug separat */}
              {bilanzView === 'erzeugung' && (
                <>
                  <Bar yAxisId="kwh" dataKey="eigenverbrauch" name="Eigenverbrauch" fill={CHART_COLORS.eigenverbrauch} stackId="pv" />
                  <Bar yAxisId="kwh" dataKey="einspeisung" name="Einspeisung" fill={CHART_COLORS.einspeisung} stackId="pv" />
                  <Bar yAxisId="kwh" dataKey="netzbezug" name="Netzbezug" fill={CHART_COLORS.netzbezug} />
                </>
              )}

              {/* Verbrauch-Ansicht: Eigenverbrauch + Netzbezug gestapelt, Einspeisung separat */}
              {bilanzView === 'verbrauch' && (
                <>
                  <Bar yAxisId="kwh" dataKey="eigenverbrauch" name="Eigenverbrauch" fill={CHART_COLORS.eigenverbrauch} stackId="verbrauch" />
                  <Bar yAxisId="kwh" dataKey="netzbezug" name="Netzbezug" fill={CHART_COLORS.netzbezug} stackId="verbrauch" />
                  <Bar yAxisId="kwh" dataKey="einspeisung" name="Einspeisung" fill={CHART_COLORS.einspeisung} />
                </>
              )}

              {/* Optionale Autarkie-Linie */}
              {showAutarkie && (
                <Line
                  yAxisId="pct"
                  type="monotone"
                  dataKey="autarkie"
                  name="Autarkie"
                  stroke={CHART_COLORS.autarkie}
                  strokeWidth={2}
                  dot={false}
                />
              )}
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      </Card>

      {/* Chart 2: Effizienz-Trends (Monatszeitreihe) */}
      <Card>
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
          <TrendingUp className="h-5 w-5 text-green-500" />
          Effizienz-Trends
        </h3>
        <div className="h-72">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={zeitreihe} margin={{ top: 10, right: 30, left: 0, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" className="stroke-gray-200 dark:stroke-gray-700" />
              <XAxis dataKey="name" tick={{ fontSize: 10 }} interval="preserveStartEnd" />
              <YAxis yAxisId="left" domain={[0, 100]} unit="%" tick={{ fontSize: 11 }} />
              <YAxis yAxisId="right" orientation="right" tickFormatter={(v) => `${v.toFixed(0)}`} unit=" kWh/kWp" tick={{ fontSize: 11 }} />
              <Tooltip
                formatter={(value: number, name: string) => {
                  if (name.includes('kWh/kWp')) return [`${value.toFixed(0)} kWh/kWp`, name]
                  return [`${value.toFixed(1)}%`, name]
                }}
                contentStyle={{ borderRadius: 8, backgroundColor: 'var(--tooltip-bg)', color: 'var(--tooltip-fg)', border: '1px solid var(--tooltip-border)' }}
              />
              <Legend />
              <Line yAxisId="left" type="monotone" dataKey="autarkie" name="Autarkie (%)" stroke={CHART_COLORS.autarkie} strokeWidth={2} dot={false} />
              <Line yAxisId="left" type="monotone" dataKey="evQuote" name="EV-Quote (%)" stroke={CHART_COLORS.evQuote} strokeWidth={2} dot={false} />
              <Bar yAxisId="right" dataKey="spezErtrag" name="Spez. Ertrag (kWh/kWp)" fill={CHART_COLORS.spezErtrag} opacity={0.7} />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      </Card>

      {/* Chart 3: PV-Erzeugung Verlauf */}
      <Card>
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
          <Sun className="h-5 w-5 text-yellow-500" />
          PV-Erzeugung Verlauf
        </h3>
        <div className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={zeitreihe} margin={{ top: 10, right: 30, left: 0, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" className="stroke-gray-200 dark:stroke-gray-700" />
              <XAxis dataKey="name" tick={{ fontSize: 10 }} interval="preserveStartEnd" />
              <YAxis unit=" kWh" tick={{ fontSize: 11 }} />
              <Tooltip
                formatter={(value: number) => [`${value.toFixed(0)} kWh`, 'Erzeugung']}
                contentStyle={{ borderRadius: 8, backgroundColor: 'var(--tooltip-bg)', color: 'var(--tooltip-fg)', border: '1px solid var(--tooltip-border)' }}
              />
              <Line type="monotone" dataKey="erzeugung" name="PV-Erzeugung" stroke={CHART_COLORS.erzeugung} strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </Card>

      {/* Zusammenfassung */}
      <Card>
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
          Zusammenfassung
        </h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
          <div>
            <p className="text-gray-500 dark:text-gray-400">Zeitraum</p>
            <p className="font-medium text-gray-900 dark:text-white">{stats.anzahlMonate} Monate</p>
          </div>
          <div>
            <p className="text-gray-500 dark:text-gray-400">Anlagenleistung</p>
            <p className="font-medium text-gray-900 dark:text-white">{anlage?.leistung_kwp || '---'} kWp</p>
          </div>
          <div>
            <p className="text-gray-500 dark:text-gray-400">Netto-Ertrag</p>
            <p className="font-medium text-green-600 dark:text-green-400">
              {nettoErtrag ? `${nettoErtrag.toFixed(0)} €` : '---'}
            </p>
          </div>
          <div>
            <p className="text-gray-500 dark:text-gray-400">CO2 eingespart</p>
            <p className="font-medium text-green-600 dark:text-green-400">
              {(stats.gesamtErzeugung * 0.38 / 1000).toFixed(1)} t
            </p>
          </div>
        </div>
      </Card>
    </div>
  )
}
