// Energie Tab - Monatszeitreihen für Energie-Bilanz und Effizienz
import { useMemo } from 'react'
import {
  BarChart, Bar, LineChart, Line, ComposedChart,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer
} from 'recharts'
import { Sun, Zap, TrendingUp, Download } from 'lucide-react'
import { Card, Button, fmtCalc } from '../../components/ui'
import { exportToCSV } from '../../utils/export'
import { KPICard } from './KPICard'
import { TabProps, CHART_COLORS, createMonatsZeitreihe } from './types'

export function EnergieTab({ data, stats, anlage, strompreis }: TabProps) {
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
      {/* Header mit Export */}
      <div className="flex items-center justify-between">
        <p className="text-sm text-gray-500 dark:text-gray-400">
          {stats.anzahlMonate} Monate Daten
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
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
          <Zap className="h-5 w-5 text-blue-500" />
          Energie-Bilanz pro Monat
        </h3>
        <div className="h-80">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={zeitreihe} margin={{ top: 10, right: 30, left: 0, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" className="stroke-gray-200 dark:stroke-gray-700" />
              <XAxis dataKey="name" tick={{ fontSize: 10 }} interval="preserveStartEnd" />
              <YAxis tickFormatter={(v) => `${v.toFixed(0)}`} unit=" kWh" tick={{ fontSize: 11 }} />
              <Tooltip
                formatter={(value: number, name: string) => [`${value.toFixed(0)} kWh`, name]}
                contentStyle={{ backgroundColor: 'rgba(255,255,255,0.95)', border: '1px solid #e5e7eb' }}
              />
              <Legend />
              <Bar dataKey="eigenverbrauch" name="Eigenverbrauch" fill={CHART_COLORS.eigenverbrauch} stackId="pv" />
              <Bar dataKey="einspeisung" name="Einspeisung" fill={CHART_COLORS.einspeisung} stackId="pv" />
              <Bar dataKey="netzbezug" name="Netzbezug" fill={CHART_COLORS.netzbezug} />
            </BarChart>
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
                contentStyle={{ backgroundColor: 'rgba(255,255,255,0.95)', border: '1px solid #e5e7eb' }}
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
                contentStyle={{ backgroundColor: 'rgba(255,255,255,0.95)', border: '1px solid #e5e7eb' }}
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
