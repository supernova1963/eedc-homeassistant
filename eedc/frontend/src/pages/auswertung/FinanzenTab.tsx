// Finanzen Tab - Monatszeitreihen für Erlöse und Ersparnisse
import { useMemo } from 'react'
import {
  BarChart, Bar, ComposedChart, AreaChart, Area, Line,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer
} from 'recharts'
import { Euro, TrendingUp, Download } from 'lucide-react'
import { Card, Button, fmtCalc } from '../../components/ui'
import { exportToCSV } from '../../utils/export'
import { KPICard } from './KPICard'
import { TabProps, COLORS, createMonatsZeitreihe } from './types'

interface FinanzenTabProps {
  data: TabProps['data']
  stats: TabProps['stats']
  strompreis: TabProps['strompreis']
}

export function FinanzenTab({ data, stats, strompreis }: FinanzenTabProps) {
  if (!strompreis) {
    return (
      <Card className="text-center py-8">
        <Euro className="h-12 w-12 mx-auto text-gray-400 mb-4" />
        <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-2">
          Strompreis erforderlich
        </h3>
        <p className="text-gray-500 dark:text-gray-400">
          Bitte konfiguriere einen Stromtarif, um Finanzauswertungen zu sehen.
        </p>
      </Card>
    )
  }

  // Monatszeitreihen erstellen
  const zeitreihe = useMemo(
    () => createMonatsZeitreihe(data, undefined, strompreis),
    [data, strompreis]
  )

  // Kumulierte Werte berechnen
  const chartDataWithKumuliert = useMemo(() => {
    let kumuliert = 0
    return zeitreihe.map(z => {
      kumuliert += z.netto_ertrag
      return {
        ...z,
        kumuliert_ertrag: kumuliert
      }
    })
  }, [zeitreihe])

  // Gesamt-Finanzen
  const gesamt = useMemo(() => {
    const einspeiseErloes = stats.gesamtEinspeisung * strompreis.einspeiseverguetung_cent_kwh / 100
    const netzbezugKosten = stats.gesamtNetzbezug * strompreis.netzbezug_arbeitspreis_cent_kwh / 100
    const eigenverbrauchErsparnis = stats.gesamtEigenverbrauch * strompreis.netzbezug_arbeitspreis_cent_kwh / 100
    const nettoErtrag = einspeiseErloes + eigenverbrauchErsparnis
    return { einspeiseErloes, netzbezugKosten, eigenverbrauchErsparnis, nettoErtrag }
  }, [stats, strompreis])

  // CSV Export
  const handleExportCSV = () => {
    const headers = [
      'Monat', 'Einspeiseerlös (€)', 'EV-Ersparnis (€)', 'Netzbezug-Kosten (€)',
      'Netto-Ertrag (€)', 'Kumulierter Ertrag (€)'
    ]
    const rows = chartDataWithKumuliert.map(z => [
      z.name, z.einspeise_erloes, z.ev_ersparnis, z.netzbezug_kosten,
      z.netto_ertrag, z.kumuliert_ertrag
    ])
    exportToCSV(headers, rows, `finanzen_export.csv`)
  }

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

      {/* Finanz-KPIs */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <KPICard
          title="Einspeiseerlös"
          value={gesamt.einspeiseErloes.toFixed(0)}
          unit="€"
          subtitle={`${strompreis.einspeiseverguetung_cent_kwh.toFixed(1)} ct/kWh`}
          icon={TrendingUp}
          color="text-green-500"
          bgColor="bg-green-50 dark:bg-green-900/20"
          formel="Einspeisung × Einspeisevergütung"
          berechnung={`${fmtCalc(stats.gesamtEinspeisung, 0)} kWh × ${fmtCalc(strompreis.einspeiseverguetung_cent_kwh, 2)} ct/kWh`}
          ergebnis={`= ${fmtCalc(gesamt.einspeiseErloes, 2)} €`}
        />
        <KPICard
          title="EV-Ersparnis"
          value={gesamt.eigenverbrauchErsparnis.toFixed(0)}
          unit="€"
          subtitle="vermiedener Netzbezug"
          icon={Euro}
          color="text-purple-500"
          bgColor="bg-purple-50 dark:bg-purple-900/20"
          formel="Eigenverbrauch × Netzbezugspreis"
          berechnung={`${fmtCalc(stats.gesamtEigenverbrauch, 0)} kWh × ${fmtCalc(strompreis.netzbezug_arbeitspreis_cent_kwh, 2)} ct/kWh`}
          ergebnis={`= ${fmtCalc(gesamt.eigenverbrauchErsparnis, 2)} €`}
        />
        <KPICard
          title="Netzbezug-Kosten"
          value={gesamt.netzbezugKosten.toFixed(0)}
          unit="€"
          subtitle={`${strompreis.netzbezug_arbeitspreis_cent_kwh.toFixed(1)} ct/kWh`}
          icon={Euro}
          color="text-red-500"
          bgColor="bg-red-50 dark:bg-red-900/20"
          formel="Netzbezug × Netzbezugspreis"
          berechnung={`${fmtCalc(stats.gesamtNetzbezug, 0)} kWh × ${fmtCalc(strompreis.netzbezug_arbeitspreis_cent_kwh, 2)} ct/kWh`}
          ergebnis={`= ${fmtCalc(gesamt.netzbezugKosten, 2)} €`}
        />
        <KPICard
          title="Netto-Ertrag"
          value={gesamt.nettoErtrag.toFixed(0)}
          unit="€"
          subtitle="Gesamt"
          icon={Euro}
          color="text-blue-500"
          bgColor="bg-blue-50 dark:bg-blue-900/20"
          formel="Einspeiseerlös + EV-Ersparnis"
          berechnung={`${fmtCalc(gesamt.einspeiseErloes, 2)} € + ${fmtCalc(gesamt.eigenverbrauchErsparnis, 2)} €`}
          ergebnis={`= ${fmtCalc(gesamt.nettoErtrag, 2)} €`}
        />
      </div>

      {/* Chart 1: Finanzielle Bilanz pro Monat */}
      <Card>
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
          <Euro className="h-5 w-5 text-green-500" />
          Finanzielle Bilanz pro Monat
        </h3>
        <div className="h-72">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={zeitreihe} margin={{ top: 10, right: 30, left: 0, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" className="stroke-gray-200 dark:stroke-gray-700" />
              <XAxis dataKey="name" tick={{ fontSize: 10 }} interval="preserveStartEnd" />
              <YAxis unit=" €" tick={{ fontSize: 11 }} />
              <Tooltip
                formatter={(value: number, name: string) => [`${value.toFixed(2)} €`, name]}
                contentStyle={{ backgroundColor: 'rgba(255,255,255,0.95)', border: '1px solid #e5e7eb' }}
              />
              <Legend />
              <Bar dataKey="einspeise_erloes" name="Einspeiseerlös" fill={COLORS.feedin} stackId="pos" />
              <Bar dataKey="ev_ersparnis" name="EV-Ersparnis" fill={COLORS.consumption} stackId="pos" />
              <Bar dataKey="netzbezug_kosten" name="Netzbezug (negativ)" fill={COLORS.grid} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </Card>

      {/* Chart 2: Kumulierter Ertrag */}
      <Card>
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
          <TrendingUp className="h-5 w-5 text-blue-500" />
          Kumulierter Netto-Ertrag
        </h3>
        <div className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={chartDataWithKumuliert} margin={{ top: 10, right: 30, left: 0, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" className="stroke-gray-200 dark:stroke-gray-700" />
              <XAxis dataKey="name" tick={{ fontSize: 10 }} interval="preserveStartEnd" />
              <YAxis unit=" €" tick={{ fontSize: 11 }} />
              <Tooltip
                formatter={(value: number) => [`${value.toFixed(0)} €`, 'Kumuliert']}
                contentStyle={{ backgroundColor: 'rgba(255,255,255,0.95)', border: '1px solid #e5e7eb' }}
              />
              <Area
                type="monotone"
                dataKey="kumuliert_ertrag"
                name="Kumulierter Ertrag"
                stroke={COLORS.feedin}
                fill={COLORS.feedin}
                fillOpacity={0.3}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
        <div className="mt-4 flex items-center justify-center gap-4 text-sm">
          <span className="text-gray-500">Gesamt nach {stats.anzahlMonate} Monaten:</span>
          <span className="text-lg font-bold text-green-600">
            {gesamt.nettoErtrag.toFixed(0)} €
          </span>
        </div>
      </Card>

      {/* Chart 3: Netto-Ertrag pro Monat (Line) */}
      <Card>
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
          Netto-Ertrag pro Monat
        </h3>
        <div className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={zeitreihe} margin={{ top: 10, right: 30, left: 0, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" className="stroke-gray-200 dark:stroke-gray-700" />
              <XAxis dataKey="name" tick={{ fontSize: 10 }} interval="preserveStartEnd" />
              <YAxis unit=" €" tick={{ fontSize: 11 }} />
              <Tooltip
                formatter={(value: number) => [`${value.toFixed(2)} €`, 'Netto-Ertrag']}
                contentStyle={{ backgroundColor: 'rgba(255,255,255,0.95)', border: '1px solid #e5e7eb' }}
              />
              <Bar dataKey="netto_ertrag" name="Netto-Ertrag" fill={COLORS.feedin} opacity={0.7} />
              <Line type="monotone" dataKey="netto_ertrag" name="Trend" stroke={COLORS.solar} strokeWidth={2} dot={false} />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      </Card>

      {/* Zusammenfassung */}
      <Card>
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
          Durchschnittswerte
        </h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
          <div>
            <p className="text-gray-500 dark:text-gray-400">Ø Einspeiseerlös/Monat</p>
            <p className="font-medium text-green-600">{(gesamt.einspeiseErloes / stats.anzahlMonate).toFixed(0)} €</p>
          </div>
          <div>
            <p className="text-gray-500 dark:text-gray-400">Ø EV-Ersparnis/Monat</p>
            <p className="font-medium text-purple-600">{(gesamt.eigenverbrauchErsparnis / stats.anzahlMonate).toFixed(0)} €</p>
          </div>
          <div>
            <p className="text-gray-500 dark:text-gray-400">Ø Netzbezug-Kosten/Monat</p>
            <p className="font-medium text-red-600">{(gesamt.netzbezugKosten / stats.anzahlMonate).toFixed(0)} €</p>
          </div>
          <div>
            <p className="text-gray-500 dark:text-gray-400">Ø Netto-Ertrag/Monat</p>
            <p className="font-medium text-blue-600">{(gesamt.nettoErtrag / stats.anzahlMonate).toFixed(0)} €</p>
          </div>
        </div>
      </Card>
    </div>
  )
}
