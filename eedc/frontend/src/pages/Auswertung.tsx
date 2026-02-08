import { useState, useMemo, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  BarChart, Bar, LineChart, Line, PieChart, Pie, Cell, AreaChart, Area,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer
} from 'recharts'
import {
  Sun, Zap, Battery, TrendingUp, Leaf, Euro, Calendar, ArrowRight,
  PiggyBank, Wallet
} from 'lucide-react'
import { Card, Button, LoadingSpinner, Alert, FormelTooltip, fmtCalc } from '../components/ui'
import { useAnlagen, useMonatsdaten, useMonatsdatenStats, useAktuellerStrompreis, useInvestitionen } from '../hooks'
import { investitionenApi, type ROIDashboardResponse } from '../api'

const monatNamen = ['', 'Jan', 'Feb', 'Mär', 'Apr', 'Mai', 'Jun', 'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Dez']

const COLORS = {
  solar: '#f59e0b',
  grid: '#ef4444',
  consumption: '#8b5cf6',
  battery: '#3b82f6',
  feedin: '#10b981',
}

const JAHR_COLORS = ['#f59e0b', '#3b82f6', '#10b981', '#8b5cf6', '#ef4444', '#06b6d4']

const TYP_COLORS: Record<string, string> = {
  'pv-module': '#f59e0b',
  'wechselrichter': '#eab308',
  'speicher': '#3b82f6',
  'e-auto': '#8b5cf6',
  'wallbox': '#06b6d4',
  'waermepumpe': '#ef4444',
  'balkonkraftwerk': '#10b981',
  'sonstiges': '#6b7280',
}

const TYP_LABELS: Record<string, string> = {
  'pv-module': 'PV-Module',
  'wechselrichter': 'Wechselrichter',
  'speicher': 'Speicher',
  'e-auto': 'E-Auto',
  'wallbox': 'Wallbox',
  'waermepumpe': 'Wärmepumpe',
  'balkonkraftwerk': 'Balkonkraftwerk',
  'sonstiges': 'Sonstiges',
}

type TabType = 'uebersicht' | 'pv' | 'investitionen' | 'finanzen' | 'co2'

export default function Auswertung() {
  const navigate = useNavigate()
  const [activeTab, setActiveTab] = useState<TabType>('uebersicht')
  const [selectedYear, setSelectedYear] = useState<number | 'all'>('all')

  const { anlagen, loading: anlagenLoading } = useAnlagen()
  const [selectedAnlageId, setSelectedAnlageId] = useState<number | null>(null)

  const anlageId = selectedAnlageId ?? anlagen[0]?.id
  const anlage = anlagen.find(a => a.id === anlageId)
  const { monatsdaten, loading: mdLoading } = useMonatsdaten(anlageId)
  const { strompreis } = useAktuellerStrompreis(anlageId ?? null)

  // Verfügbare Jahre
  const verfuegbareJahre = useMemo(() => {
    const jahre = [...new Set(monatsdaten.map(m => m.jahr))].sort((a, b) => b - a)
    return jahre
  }, [monatsdaten])

  // Gefilterte Daten nach Jahr
  const filteredData = useMemo(() => {
    if (selectedYear === 'all') return monatsdaten
    return monatsdaten.filter(m => m.jahr === selectedYear)
  }, [monatsdaten, selectedYear])

  // Stats für gefilterte Daten
  const filteredStats = useMonatsdatenStats(filteredData)

  const loading = anlagenLoading || mdLoading

  if (loading) {
    return <LoadingSpinner text="Lade Auswertungen..." />
  }

  if (anlagen.length === 0) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Auswertung</h1>
        <Alert type="warning">
          Bitte lege zuerst eine PV-Anlage an.
        </Alert>
      </div>
    )
  }

  if (monatsdaten.length === 0) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Auswertung</h1>
        <Card className="text-center py-12">
          <Sun className="h-12 w-12 mx-auto text-gray-400 mb-4" />
          <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-2">
            Noch keine Daten vorhanden
          </h3>
          <p className="text-gray-500 dark:text-gray-400 mb-4">
            Erfasse Monatsdaten, um Auswertungen zu sehen.
          </p>
          <Button onClick={() => navigate('/monatsdaten')}>
            Monatsdaten erfassen
            <ArrowRight className="h-4 w-4 ml-2" />
          </Button>
        </Card>
      </div>
    )
  }

  const tabs: { key: TabType; label: string }[] = [
    { key: 'uebersicht', label: 'Übersicht' },
    { key: 'pv', label: 'PV-Anlage' },
    { key: 'investitionen', label: 'Investitionen' },
    { key: 'finanzen', label: 'Finanzen' },
    { key: 'co2', label: 'CO2' },
  ]

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Auswertung</h1>
        <div className="flex items-center gap-3">
          {/* Jahr-Filter - nicht für Übersicht (Jahresvergleich braucht alle Jahre) */}
          {activeTab !== 'uebersicht' && (
            <select
              value={selectedYear}
              onChange={(e) => setSelectedYear(e.target.value === 'all' ? 'all' : Number(e.target.value))}
              className="input w-auto"
            >
              <option value="all">Alle Jahre</option>
              {verfuegbareJahre.map(j => (
                <option key={j} value={j}>{j}</option>
              ))}
            </select>
          )}

          {/* Anlagen-Filter */}
          {anlagen.length > 1 && (
            <select
              value={anlageId ?? ''}
              onChange={(e) => setSelectedAnlageId(Number(e.target.value))}
              className="input w-auto"
            >
              {anlagen.map((a) => (
                <option key={a.id} value={a.id}>{a.anlagenname}</option>
              ))}
            </select>
          )}
        </div>
      </div>

      {/* Tabs */}
      <div className="border-b border-gray-200 dark:border-gray-700">
        <nav className="flex gap-4">
          {tabs.map((tab) => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`py-3 px-1 border-b-2 text-sm font-medium transition-colors ${
                activeTab === tab.key
                  ? 'border-primary-500 text-primary-600 dark:text-primary-400'
                  : 'border-transparent text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-300'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </nav>
      </div>

      {/* Tab Content */}
      {activeTab === 'uebersicht' && (
        <UebersichtTab data={monatsdaten} anlage={anlage} strompreis={strompreis} />
      )}
      {activeTab === 'pv' && (
        <PVTab data={filteredData} stats={filteredStats} anlage={anlage} strompreis={strompreis} />
      )}
      {activeTab === 'investitionen' && anlageId && (
        <InvestitionenTab anlageId={anlageId} strompreis={strompreis} selectedYear={selectedYear} />
      )}
      {activeTab === 'finanzen' && (
        <FinanzenTab data={filteredData} stats={filteredStats} strompreis={strompreis} />
      )}
      {activeTab === 'co2' && (
        <CO2Tab data={filteredData} stats={filteredStats} />
      )}
    </div>
  )
}

// Tab Props
interface TabProps {
  data: ReturnType<typeof useMonatsdaten>['monatsdaten']
  stats: ReturnType<typeof useMonatsdatenStats>
  anlage?: ReturnType<typeof useAnlagen>['anlagen'][0]
  strompreis?: ReturnType<typeof useAktuellerStrompreis>['strompreis']
}

// ============================================================================
// ÜBERSICHT TAB - Jahresvergleich (ehemals JahresvergleichTab)
// ============================================================================
function UebersichtTab({ data, anlage, strompreis }: Omit<TabProps, 'stats'>) {
  // Alle verfügbaren Jahre
  const verfuegbareJahre = useMemo(() => {
    return [...new Set(data.map(m => m.jahr))].sort((a, b) => a - b)
  }, [data])

  // Jahresstatistiken berechnen
  const jahresStats = useMemo(() => {
    const stats: Record<number, {
      jahr: number
      erzeugung: number
      eigenverbrauch: number
      einspeisung: number
      netzbezug: number
      gesamtverbrauch: number
      autarkie: number
      eigenverbrauchQuote: number
      spezErtrag: number
      monate: number
      nettoErtrag: number
    }> = {}

    data.forEach(md => {
      if (!stats[md.jahr]) {
        stats[md.jahr] = {
          jahr: md.jahr,
          erzeugung: 0,
          eigenverbrauch: 0,
          einspeisung: 0,
          netzbezug: 0,
          gesamtverbrauch: 0,
          autarkie: 0,
          eigenverbrauchQuote: 0,
          spezErtrag: 0,
          monate: 0,
          nettoErtrag: 0,
        }
      }
      const s = stats[md.jahr]
      const erzeugung = md.pv_erzeugung_kwh || (md.einspeisung_kwh + (md.eigenverbrauch_kwh || 0))
      s.erzeugung += erzeugung
      s.eigenverbrauch += md.eigenverbrauch_kwh || 0
      s.einspeisung += md.einspeisung_kwh
      s.netzbezug += md.netzbezug_kwh
      s.gesamtverbrauch += md.gesamtverbrauch_kwh || 0
      s.monate += 1
    })

    // Quoten berechnen
    Object.values(stats).forEach(s => {
      if (s.erzeugung > 0) {
        s.eigenverbrauchQuote = (s.eigenverbrauch / s.erzeugung) * 100
      }
      if (s.gesamtverbrauch > 0) {
        s.autarkie = (s.eigenverbrauch / s.gesamtverbrauch) * 100
      }
      if (anlage?.leistung_kwp) {
        s.spezErtrag = s.erzeugung / anlage.leistung_kwp
      }
      if (strompreis) {
        const einspeiseErloes = s.einspeisung * strompreis.einspeiseverguetung_cent_kwh / 100
        const evErsparnis = s.eigenverbrauch * strompreis.netzbezug_arbeitspreis_cent_kwh / 100
        s.nettoErtrag = einspeiseErloes + evErsparnis
      }
    })

    return Object.values(stats).sort((a, b) => a.jahr - b.jahr)
  }, [data, anlage, strompreis])

  // Monatsvergleich-Daten (Jan-Dez für jedes Jahr)
  const monatsVergleichData = useMemo(() => {
    const result: Array<Record<string, string | number>> = []

    for (let m = 1; m <= 12; m++) {
      const row: Record<string, string | number> = {
        monat: monatNamen[m],
        monatNr: m,
      }

      verfuegbareJahre.forEach(jahr => {
        const md = data.find(d => d.jahr === jahr && d.monat === m)
        const erzeugung = md ? (md.pv_erzeugung_kwh || (md.einspeisung_kwh + (md.eigenverbrauch_kwh || 0))) : 0
        row[`erzeugung_${jahr}`] = erzeugung
        row[`autarkie_${jahr}`] = md && md.gesamtverbrauch_kwh ? ((md.eigenverbrauch_kwh || 0) / md.gesamtverbrauch_kwh) * 100 : 0
      })

      result.push(row)
    }

    return result
  }, [data, verfuegbareJahre])

  // Delta zum Vorjahr berechnen
  const getDelta = (current: number, previous: number | undefined): { value: number; percent: number } | null => {
    if (previous === undefined || previous === 0) return null
    const value = current - previous
    const percent = (value / previous) * 100
    return { value, percent }
  }

  if (verfuegbareJahre.length < 2) {
    // Fallback: Zeige einfache Jahresübersicht wenn nur 1 Jahr
    const stats = jahresStats[0]
    if (!stats) {
      return (
        <Card className="text-center py-8">
          <Calendar className="h-12 w-12 mx-auto text-gray-400 mb-4" />
          <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-2">
            Keine Daten vorhanden
          </h3>
        </Card>
      )
    }

    return (
      <div className="space-y-6">
        <Alert type="info">
          Für einen detaillierten Jahresvergleich werden Daten aus mindestens 2 Jahren benötigt.
          Aktuell: {verfuegbareJahre[0] || 'Keine Daten'}
        </Alert>

        {/* Einfache KPI-Übersicht für 1 Jahr */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <KPICard
            title="Erzeugung"
            value={(stats.erzeugung / 1000).toFixed(1)}
            unit="MWh"
            icon={Sun}
            color="text-yellow-500"
            bgColor="bg-yellow-50 dark:bg-yellow-900/20"
          />
          <KPICard
            title="Autarkie"
            value={stats.autarkie.toFixed(0)}
            unit="%"
            icon={Battery}
            color="text-blue-500"
            bgColor="bg-blue-50 dark:bg-blue-900/20"
          />
          <KPICard
            title="EV-Quote"
            value={stats.eigenverbrauchQuote.toFixed(0)}
            unit="%"
            icon={Zap}
            color="text-purple-500"
            bgColor="bg-purple-50 dark:bg-purple-900/20"
          />
          {strompreis && (
            <KPICard
              title="Netto-Ertrag"
              value={stats.nettoErtrag.toFixed(0)}
              unit="€"
              icon={Euro}
              color="text-green-500"
              bgColor="bg-green-50 dark:bg-green-900/20"
            />
          )}
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Jahres-KPIs mit Delta */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {jahresStats.slice(-4).reverse().map((js, idx) => {
          const prevStats = jahresStats.find(s => s.jahr === js.jahr - 1)
          const deltaErzeugung = getDelta(js.erzeugung, prevStats?.erzeugung)

          return (
            <Card key={js.jahr} className={idx === 0 ? 'ring-2 ring-primary-500' : ''}>
              <div className="flex items-center justify-between mb-3">
                <span className="text-lg font-bold text-gray-900 dark:text-white">{js.jahr}</span>
                {idx === 0 && (
                  <span className="text-xs bg-primary-100 text-primary-700 dark:bg-primary-900 dark:text-primary-300 px-2 py-1 rounded">
                    Aktuell
                  </span>
                )}
              </div>
              <div className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-gray-500">Erzeugung</span>
                  <span className="font-medium text-gray-900 dark:text-white">
                    {(js.erzeugung / 1000).toFixed(1)} MWh
                    {deltaErzeugung && (
                      <span className={`ml-2 text-xs ${deltaErzeugung.percent >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                        {deltaErzeugung.percent >= 0 ? '↑' : '↓'} {Math.abs(deltaErzeugung.percent).toFixed(0)}%
                      </span>
                    )}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-500">Autarkie</span>
                  <span className="font-medium text-gray-900 dark:text-white">{js.autarkie.toFixed(0)}%</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-500">EV-Quote</span>
                  <span className="font-medium text-gray-900 dark:text-white">{js.eigenverbrauchQuote.toFixed(0)}%</span>
                </div>
                {anlage?.leistung_kwp && (
                  <div className="flex justify-between">
                    <span className="text-gray-500">Spez. Ertrag</span>
                    <span className="font-medium text-gray-900 dark:text-white">{js.spezErtrag.toFixed(0)} kWh/kWp</span>
                  </div>
                )}
                {strompreis && (
                  <div className="flex justify-between pt-2 border-t border-gray-200 dark:border-gray-700">
                    <span className="text-gray-500">Netto-Ertrag</span>
                    <span className="font-medium text-green-600">{js.nettoErtrag.toFixed(0)} €</span>
                  </div>
                )}
              </div>
            </Card>
          )
        })}
      </div>

      {/* Monatsvergleich Erzeugung */}
      <Card>
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
          Monatliche Erzeugung im Jahresvergleich
        </h3>
        <div className="h-72">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={monatsVergleichData}>
              <CartesianGrid strokeDasharray="3 3" className="stroke-gray-200 dark:stroke-gray-700" />
              <XAxis dataKey="monat" tick={{ fontSize: 11 }} />
              <YAxis unit=" kWh" tick={{ fontSize: 11 }} />
              <Tooltip
                formatter={(value: number, name: string) => {
                  const jahr = name.replace('erzeugung_', '')
                  return [`${value.toFixed(0)} kWh`, `${jahr}`]
                }}
              />
              <Legend formatter={(value) => value.replace('erzeugung_', '')} />
              {verfuegbareJahre.map((jahr, idx) => (
                <Bar
                  key={jahr}
                  dataKey={`erzeugung_${jahr}`}
                  name={`erzeugung_${jahr}`}
                  fill={JAHR_COLORS[idx % JAHR_COLORS.length]}
                />
              ))}
            </BarChart>
          </ResponsiveContainer>
        </div>
      </Card>

      {/* Autarkie-Verlauf */}
      <Card>
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
          Autarkie im Jahresvergleich
        </h3>
        <div className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={monatsVergleichData}>
              <CartesianGrid strokeDasharray="3 3" className="stroke-gray-200 dark:stroke-gray-700" />
              <XAxis dataKey="monat" tick={{ fontSize: 11 }} />
              <YAxis unit="%" domain={[0, 100]} tick={{ fontSize: 11 }} />
              <Tooltip
                formatter={(value: number, name: string) => {
                  const jahr = name.replace('autarkie_', '')
                  return [`${value.toFixed(0)}%`, `${jahr}`]
                }}
              />
              <Legend formatter={(value) => value.replace('autarkie_', '')} />
              {verfuegbareJahre.map((jahr, idx) => (
                <Line
                  key={jahr}
                  type="monotone"
                  dataKey={`autarkie_${jahr}`}
                  name={`autarkie_${jahr}`}
                  stroke={JAHR_COLORS[idx % JAHR_COLORS.length]}
                  strokeWidth={2}
                  dot={{ r: 3 }}
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>
      </Card>

      {/* Jahresvergleich Tabelle */}
      <Card>
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
          Jahresübersicht
        </h3>
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
            <thead>
              <tr>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Jahr</th>
                <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">Erzeugung</th>
                <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">Δ</th>
                <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">Eigenverbr.</th>
                <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">Einspeisung</th>
                <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">Netzbezug</th>
                <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">Autarkie</th>
                {strompreis && (
                  <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">Netto-Ertrag</th>
                )}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
              {jahresStats.map((js, idx) => {
                const prevStats = idx > 0 ? jahresStats[idx - 1] : undefined
                const delta = getDelta(js.erzeugung, prevStats?.erzeugung)

                return (
                  <tr key={js.jahr} className="hover:bg-gray-50 dark:hover:bg-gray-800">
                    <td className="px-4 py-3 text-sm font-medium text-gray-900 dark:text-white">
                      {js.jahr}
                      <span className="ml-2 text-xs text-gray-400">({js.monate} Mon.)</span>
                    </td>
                    <td className="px-4 py-3 text-sm text-right text-gray-900 dark:text-white">
                      {(js.erzeugung / 1000).toFixed(1)} MWh
                    </td>
                    <td className="px-4 py-3 text-sm text-right">
                      {delta ? (
                        <span className={delta.percent >= 0 ? 'text-green-600' : 'text-red-600'}>
                          {delta.percent >= 0 ? '+' : ''}{delta.percent.toFixed(1)}%
                        </span>
                      ) : (
                        <span className="text-gray-400">—</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-sm text-right text-gray-900 dark:text-white">
                      {js.eigenverbrauch.toFixed(0)} kWh
                    </td>
                    <td className="px-4 py-3 text-sm text-right text-gray-900 dark:text-white">
                      {js.einspeisung.toFixed(0)} kWh
                    </td>
                    <td className="px-4 py-3 text-sm text-right text-gray-900 dark:text-white">
                      {js.netzbezug.toFixed(0)} kWh
                    </td>
                    <td className="px-4 py-3 text-sm text-right text-gray-900 dark:text-white">
                      {js.autarkie.toFixed(0)}%
                    </td>
                    {strompreis && (
                      <td className="px-4 py-3 text-sm text-right font-medium text-green-600">
                        {js.nettoErtrag.toFixed(0)} €
                      </td>
                    )}
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  )
}

// ============================================================================
// PV-ANLAGE TAB - Kombiniert bisherige Übersicht + PV-Details
// ============================================================================
function PVTab({ data, stats, anlage, strompreis }: TabProps) {
  // Chart-Daten für monatlichen Verlauf
  const chartData = useMemo(() => {
    const sorted = [...data].sort((a, b) => {
      if (a.jahr !== b.jahr) return a.jahr - b.jahr
      return a.monat - b.monat
    })

    return sorted.map(md => ({
      name: `${monatNamen[md.monat]} ${md.jahr.toString().slice(-2)}`,
      Erzeugung: md.pv_erzeugung_kwh || 0,
      Eigenverbrauch: md.eigenverbrauch_kwh || 0,
      Einspeisung: md.einspeisung_kwh,
      Netzbezug: md.netzbezug_kwh,
      SpezErtrag: anlage?.leistung_kwp
        ? ((md.pv_erzeugung_kwh || md.einspeisung_kwh) / anlage.leistung_kwp)
        : 0,
    }))
  }, [data, anlage])

  // Pie Chart Daten
  const pieData = useMemo(() => [
    { name: 'Eigenverbrauch', value: stats.gesamtEigenverbrauch, color: COLORS.consumption },
    { name: 'Einspeisung', value: stats.gesamtEinspeisung, color: COLORS.feedin },
  ], [stats])

  // Finanzielle Berechnung
  const finanzen = useMemo(() => {
    if (!strompreis) return null
    const einspeiseErloes = stats.gesamtEinspeisung * strompreis.einspeiseverguetung_cent_kwh / 100
    const netzbezugKosten = stats.gesamtNetzbezug * strompreis.netzbezug_arbeitspreis_cent_kwh / 100
    const eigenverbrauchErsparnis = stats.gesamtEigenverbrauch * strompreis.netzbezug_arbeitspreis_cent_kwh / 100
    const nettoErtrag = einspeiseErloes + eigenverbrauchErsparnis
    return { einspeiseErloes, netzbezugKosten, eigenverbrauchErsparnis, nettoErtrag }
  }, [stats, strompreis])

  return (
    <div className="space-y-6">
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
          icon={Battery}
          color="text-blue-500"
          bgColor="bg-blue-50 dark:bg-blue-900/20"
          formel="Eigenverbrauch ÷ Gesamtverbrauch × 100"
          berechnung="Durchschnitt aller Monate"
          ergebnis={`= ${fmtCalc(stats.durchschnittAutarkie, 1)} %`}
        />
        <KPICard
          title="Netto-Ertrag"
          value={finanzen ? finanzen.nettoErtrag.toFixed(0) : '---'}
          unit="€"
          subtitle={finanzen ? `${stats.anzahlMonate} Monate` : 'Strompreis fehlt'}
          icon={Euro}
          color="text-green-500"
          bgColor="bg-green-50 dark:bg-green-900/20"
          formel="Einspeiseerlös + EV-Ersparnis"
          berechnung={finanzen ? `${fmtCalc(finanzen.einspeiseErloes, 2)} € + ${fmtCalc(finanzen.eigenverbrauchErsparnis, 2)} €` : undefined}
          ergebnis={finanzen ? `= ${fmtCalc(finanzen.nettoErtrag, 2)} €` : undefined}
        />
      </div>

      {/* Charts */}
      <div className="grid md:grid-cols-3 gap-6">
        {/* Bar Chart - Monatlicher Verlauf */}
        <Card className="md:col-span-2">
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
            Monatlicher Verlauf
          </h3>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" className="stroke-gray-200 dark:stroke-gray-700" />
                <XAxis dataKey="name" tick={{ fontSize: 11 }} />
                <YAxis unit=" kWh" tick={{ fontSize: 11 }} />
                <Tooltip formatter={(value: number) => [`${value.toFixed(0)} kWh`, '']} />
                <Legend />
                <Bar dataKey="Eigenverbrauch" fill={COLORS.consumption} stackId="a" />
                <Bar dataKey="Einspeisung" fill={COLORS.feedin} stackId="a" />
                <Bar dataKey="Netzbezug" fill={COLORS.grid} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>

        {/* Pie Chart */}
        <Card>
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
            Verteilung PV-Strom
          </h3>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={pieData}
                  cx="50%"
                  cy="50%"
                  innerRadius={50}
                  outerRadius={80}
                  dataKey="value"
                  label={({ name, percent }) => `${name}: ${(percent * 100).toFixed(0)}%`}
                  labelLine={false}
                >
                  {pieData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={entry.color} />
                  ))}
                </Pie>
                <Tooltip formatter={(value: number) => [`${(value / 1000).toFixed(1)} MWh`, '']} />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </Card>
      </div>

      {/* PV Erzeugung Line Chart */}
      <Card>
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
          PV-Erzeugung Verlauf
        </h3>
        <div className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" className="stroke-gray-200 dark:stroke-gray-700" />
              <XAxis dataKey="name" tick={{ fontSize: 11 }} />
              <YAxis unit=" kWh" tick={{ fontSize: 11 }} />
              <Tooltip formatter={(value: number) => [`${value.toFixed(0)} kWh`, '']} />
              <Legend />
              <Line type="monotone" dataKey="Erzeugung" stroke={COLORS.solar} strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </Card>

      {/* Spez. Ertrag */}
      {anlage?.leistung_kwp && (
        <Card>
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
            Spezifischer Ertrag (kWh/kWp)
          </h3>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" className="stroke-gray-200 dark:stroke-gray-700" />
                <XAxis dataKey="name" tick={{ fontSize: 11 }} />
                <YAxis unit=" kWh/kWp" tick={{ fontSize: 11 }} />
                <Tooltip formatter={(value: number) => [`${value.toFixed(1)} kWh/kWp`, '']} />
                <Bar dataKey="SpezErtrag" name="Spez. Ertrag" fill={COLORS.solar} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>
      )}

      {/* Kennzahlen-Tabelle */}
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
            <p className="text-gray-500 dark:text-gray-400">Spez. Ertrag</p>
            <p className="font-medium text-gray-900 dark:text-white">
              {anlage?.leistung_kwp ? (stats.gesamtErzeugung / anlage.leistung_kwp).toFixed(0) : '---'} kWh/kWp
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

// ============================================================================
// INVESTITIONEN TAB - NEU
// ============================================================================
interface InvestitionenTabProps {
  anlageId: number
  strompreis?: ReturnType<typeof useAktuellerStrompreis>['strompreis']
  selectedYear?: number | 'all'
}

function InvestitionenTab({ anlageId, strompreis, selectedYear = 'all' }: InvestitionenTabProps) {
  const { investitionen, loading: invLoading } = useInvestitionen(anlageId)
  const [roiData, setRoiData] = useState<ROIDashboardResponse | null>(null)
  const [roiLoading, setRoiLoading] = useState(true)

  useEffect(() => {
    const loadROI = async () => {
      try {
        setRoiLoading(true)
        const data = await investitionenApi.getROIDashboard(
          anlageId,
          strompreis?.netzbezug_arbeitspreis_cent_kwh,
          strompreis?.einspeiseverguetung_cent_kwh,
          undefined, // benzinpreisEuro
          selectedYear
        )
        setRoiData(data)
      } catch (e) {
        console.error('ROI-Dashboard Fehler:', e)
      } finally {
        setRoiLoading(false)
      }
    }
    loadROI()
  }, [anlageId, strompreis, selectedYear])

  // Investitionen nach Typ gruppieren
  const invByTyp = useMemo(() => {
    const grouped: Record<string, typeof investitionen> = {}
    investitionen.forEach(inv => {
      if (!grouped[inv.typ]) grouped[inv.typ] = []
      grouped[inv.typ].push(inv)
    })
    return grouped
  }, [investitionen])

  // Investitionskosten nach Typ
  const kostenByTyp = useMemo(() => {
    return Object.entries(invByTyp).map(([typ, invs]) => ({
      typ,
      label: TYP_LABELS[typ] || typ,
      kosten: invs.reduce((sum, inv) => sum + (inv.anschaffungskosten_gesamt || 0), 0),
      color: TYP_COLORS[typ] || '#6b7280',
    })).filter(t => t.kosten > 0).sort((a, b) => b.kosten - a.kosten)
  }, [invByTyp])

  // Amortisationskurve berechnen
  const amortisationData = useMemo(() => {
    if (!roiData || !roiData.gesamt_jahres_einsparung) return []

    const gesamtInvestition = roiData.gesamt_relevante_kosten
    const jahresErsparnis = roiData.gesamt_jahres_einsparung
    const result = []

    for (let jahr = 0; jahr <= 25; jahr++) {
      const kumulierteErsparnis = jahr * jahresErsparnis
      result.push({
        jahr,
        investition: gesamtInvestition,
        ersparnis: kumulierteErsparnis,
        bilanz: kumulierteErsparnis - gesamtInvestition,
      })
    }
    return result
  }, [roiData])

  if (invLoading || roiLoading) {
    return <LoadingSpinner text="Lade Investitionsdaten..." />
  }

  if (investitionen.length === 0) {
    return (
      <Card className="text-center py-8">
        <PiggyBank className="h-12 w-12 mx-auto text-gray-400 mb-4" />
        <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-2">
          Keine Investitionen erfasst
        </h3>
        <p className="text-gray-500 dark:text-gray-400">
          Erfasse Investitionen in den Einstellungen, um die ROI-Auswertung zu sehen.
        </p>
      </Card>
    )
  }

  // Berechnungsdetails für Tooltips extrahieren
  const pvModulDetails = roiData?.berechnungen.find(b => b.investition_typ === 'pv-module')?.detail_berechnung as Record<string, unknown> | undefined
  const hochrechnungsHinweis = pvModulDetails?.hinweis as string | undefined

  return (
    <div className="space-y-6">
      {/* Gesamt-KPIs */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <KPICard
          title="Gesamtinvestition"
          value={(roiData?.gesamt_relevante_kosten || 0).toFixed(0)}
          unit="€"
          subtitle={`${investitionen.length} Komponenten`}
          icon={Wallet}
          color="text-blue-500"
          bgColor="bg-blue-50 dark:bg-blue-900/20"
          formel="Σ Anschaffungskosten − Alternativkosten"
          berechnung={roiData ? `${fmtCalc(roiData.gesamt_investition, 0)} € − ${fmtCalc(roiData.gesamt_investition - roiData.gesamt_relevante_kosten, 0)} € Alternativ` : undefined}
          ergebnis={roiData ? `= ${fmtCalc(roiData.gesamt_relevante_kosten, 0)} € relevante Kosten` : undefined}
        />
        <KPICard
          title="Jahresersparnis"
          value={(roiData?.gesamt_jahres_einsparung || 0).toFixed(0)}
          unit="€/Jahr"
          icon={TrendingUp}
          color="text-green-500"
          bgColor="bg-green-50 dark:bg-green-900/20"
          formel="Einspeiseerlös + Eigenverbrauch-Ersparnis"
          berechnung={pvModulDetails ? `${fmtCalc(pvModulDetails.einspeise_erloes_euro as number, 2)} € + ${fmtCalc(pvModulDetails.ev_ersparnis_euro as number, 2)} €` : 'Σ aller Investitions-Einsparungen'}
          ergebnis={hochrechnungsHinweis || (roiData ? `= ${fmtCalc(roiData.gesamt_jahres_einsparung, 0)} €/Jahr` : undefined)}
        />
        <KPICard
          title="ROI"
          value={roiData?.gesamt_roi_prozent?.toFixed(1) || '---'}
          unit="%"
          subtitle="pro Jahr"
          icon={TrendingUp}
          color="text-purple-500"
          bgColor="bg-purple-50 dark:bg-purple-900/20"
          formel="Jahresersparnis ÷ Relevante Kosten × 100"
          berechnung={roiData && roiData.gesamt_relevante_kosten > 0 ? `${fmtCalc(roiData.gesamt_jahres_einsparung, 0)} € ÷ ${fmtCalc(roiData.gesamt_relevante_kosten, 0)} € × 100` : undefined}
          ergebnis={roiData?.gesamt_roi_prozent ? `= ${roiData.gesamt_roi_prozent}% ROI p.a.` : undefined}
        />
        <KPICard
          title="Amortisation"
          value={roiData?.gesamt_amortisation_jahre?.toFixed(1) || '---'}
          unit="Jahre"
          icon={Calendar}
          color="text-amber-500"
          bgColor="bg-amber-50 dark:bg-amber-900/20"
          formel="Relevante Kosten ÷ Jahresersparnis"
          berechnung={roiData && roiData.gesamt_jahres_einsparung > 0 ? `${fmtCalc(roiData.gesamt_relevante_kosten, 0)} € ÷ ${fmtCalc(roiData.gesamt_jahres_einsparung, 0)} €/Jahr` : undefined}
          ergebnis={roiData?.gesamt_amortisation_jahre ? `= ${roiData.gesamt_amortisation_jahre} Jahre bis zur Kostendeckung` : undefined}
        />
      </div>

      {/* Investitionen nach Typ - Pie Chart */}
      <div className="grid md:grid-cols-2 gap-6">
        <Card>
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
            Investitionen nach Kategorie
          </h3>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={kostenByTyp}
                  cx="50%"
                  cy="50%"
                  outerRadius={80}
                  dataKey="kosten"
                  nameKey="label"
                  label={({ label, percent }) => `${label}: ${(percent * 100).toFixed(0)}%`}
                  labelLine={false}
                >
                  {kostenByTyp.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={entry.color} />
                  ))}
                </Pie>
                <Tooltip formatter={(value: number) => [`${value.toFixed(0)} €`, '']} />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </Card>

        {/* Investitionen Bar Chart */}
        <Card>
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
            Kosten nach Kategorie
          </h3>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={kostenByTyp} layout="vertical">
                <CartesianGrid strokeDasharray="3 3" className="stroke-gray-200 dark:stroke-gray-700" />
                <XAxis type="number" unit=" €" tick={{ fontSize: 11 }} />
                <YAxis type="category" dataKey="label" tick={{ fontSize: 11 }} width={100} />
                <Tooltip formatter={(value: number) => [`${value.toFixed(0)} €`, '']} />
                <Bar dataKey="kosten" name="Kosten">
                  {kostenByTyp.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={entry.color} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>
      </div>

      {/* Amortisationskurve */}
      {amortisationData.length > 0 && (
        <Card>
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
            Amortisationsverlauf
          </h3>
          <div className="h-72">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={amortisationData}>
                <CartesianGrid strokeDasharray="3 3" className="stroke-gray-200 dark:stroke-gray-700" />
                <XAxis dataKey="jahr" unit=" J." tick={{ fontSize: 11 }} />
                <YAxis unit=" €" tick={{ fontSize: 11 }} />
                <Tooltip formatter={(value: number) => [`${value.toFixed(0)} €`, '']} />
                <Legend />
                <Area
                  type="monotone"
                  dataKey="investition"
                  name="Investition"
                  stroke={COLORS.grid}
                  fill={COLORS.grid}
                  fillOpacity={0.3}
                />
                <Area
                  type="monotone"
                  dataKey="ersparnis"
                  name="Kum. Ersparnis"
                  stroke={COLORS.feedin}
                  fill={COLORS.feedin}
                  fillOpacity={0.3}
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
          {roiData?.gesamt_amortisation_jahre && (
            <p className="text-sm text-gray-500 mt-2">
              Break-Even nach ca. {roiData.gesamt_amortisation_jahre.toFixed(1)} Jahren
            </p>
          )}
        </Card>
      )}

      {/* ROI pro Investition */}
      {roiData?.berechnungen && roiData.berechnungen.length > 0 && (
        <Card>
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
            ROI pro Investition
          </h3>
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
              <thead>
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Bezeichnung</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Typ</th>
                  <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">Kosten</th>
                  <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">Ersparnis/Jahr</th>
                  <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">ROI</th>
                  <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">Amortisation</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
                {roiData.berechnungen.map((b) => (
                  <tr key={b.investition_id} className="hover:bg-gray-50 dark:hover:bg-gray-800">
                    <td className="px-4 py-3 text-sm font-medium text-gray-900 dark:text-white">
                      {b.investition_bezeichnung}
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-500">
                      <span
                        className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium"
                        style={{ backgroundColor: `${TYP_COLORS[b.investition_typ] || '#6b7280'}20`, color: TYP_COLORS[b.investition_typ] || '#6b7280' }}
                      >
                        {TYP_LABELS[b.investition_typ] || b.investition_typ}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-sm text-right text-gray-900 dark:text-white">
                      {b.relevante_kosten.toFixed(0)} €
                    </td>
                    <td className="px-4 py-3 text-sm text-right text-green-600">
                      {b.jahres_einsparung.toFixed(0)} €
                    </td>
                    <td className="px-4 py-3 text-sm text-right text-gray-900 dark:text-white">
                      {b.roi_prozent?.toFixed(1) || '---'}%
                    </td>
                    <td className="px-4 py-3 text-sm text-right text-gray-900 dark:text-white">
                      {b.amortisation_jahre?.toFixed(1) || '---'} J.
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {/* Investitionen-Liste */}
      <Card>
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
          Alle Investitionen
        </h3>
        <div className="grid gap-3">
          {Object.entries(invByTyp).map(([typ, invs]) => (
            <div key={typ} className="border border-gray-200 dark:border-gray-700 rounded-lg p-4">
              <div className="flex items-center gap-2 mb-3">
                <div
                  className="w-3 h-3 rounded-full"
                  style={{ backgroundColor: TYP_COLORS[typ] || '#6b7280' }}
                />
                <h4 className="font-medium text-gray-900 dark:text-white">
                  {TYP_LABELS[typ] || typ}
                </h4>
                <span className="text-sm text-gray-500">({invs.length})</span>
              </div>
              <div className="grid gap-2">
                {invs.map(inv => (
                  <div key={inv.id} className="flex justify-between items-center text-sm py-1">
                    <span className="text-gray-700 dark:text-gray-300">{inv.bezeichnung}</span>
                    <span className="text-gray-900 dark:text-white font-medium">
                      {inv.anschaffungskosten_gesamt?.toFixed(0) || '0'} €
                    </span>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </Card>
    </div>
  )
}

// ============================================================================
// FINANZEN TAB
// ============================================================================
function FinanzenTab({ data, stats, strompreis }: Omit<TabProps, 'anlage'>) {
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

  const chartData = useMemo(() => {
    const sorted = [...data].sort((a, b) => {
      if (a.jahr !== b.jahr) return a.jahr - b.jahr
      return a.monat - b.monat
    })

    return sorted.map(md => {
      const eigenverbrauch = md.eigenverbrauch_kwh || 0
      const einspeiseErloes = md.einspeisung_kwh * strompreis.einspeiseverguetung_cent_kwh / 100
      const netzbezugKosten = md.netzbezug_kwh * strompreis.netzbezug_arbeitspreis_cent_kwh / 100
      const evErsparnis = eigenverbrauch * strompreis.netzbezug_arbeitspreis_cent_kwh / 100

      return {
        name: `${monatNamen[md.monat]} ${md.jahr.toString().slice(-2)}`,
        Einspeiseerlös: einspeiseErloes,
        Ersparnis: evErsparnis,
        Netzbezug: -netzbezugKosten,
      }
    })
  }, [data, strompreis])

  // Gesamt-Finanzen
  const gesamt = useMemo(() => {
    const einspeiseErloes = stats.gesamtEinspeisung * strompreis.einspeiseverguetung_cent_kwh / 100
    const netzbezugKosten = stats.gesamtNetzbezug * strompreis.netzbezug_arbeitspreis_cent_kwh / 100
    const eigenverbrauchErsparnis = stats.gesamtEigenverbrauch * strompreis.netzbezug_arbeitspreis_cent_kwh / 100
    const nettoErtrag = einspeiseErloes + eigenverbrauchErsparnis
    return { einspeiseErloes, netzbezugKosten, eigenverbrauchErsparnis, nettoErtrag }
  }, [stats, strompreis])

  return (
    <div className="space-y-6">
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
          icon={Zap}
          color="text-purple-500"
          bgColor="bg-purple-50 dark:bg-purple-900/20"
          formel="Eigenverbrauch × Netzbezugspreis"
          berechnung={`${fmtCalc(stats.gesamtEigenverbrauch, 0)} kWh × ${fmtCalc(strompreis.netzbezug_arbeitspreis_cent_kwh, 2)} ct/kWh`}
          ergebnis={`= ${fmtCalc(gesamt.eigenverbrauchErsparnis, 2)} €`}
        />
        <KPICard
          title="Netzbezug"
          value={gesamt.netzbezugKosten.toFixed(0)}
          unit="€"
          subtitle={`${strompreis.netzbezug_arbeitspreis_cent_kwh.toFixed(1)} ct/kWh`}
          icon={Battery}
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

      {/* Finanzen Chart */}
      <Card>
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
          Finanzielle Bilanz pro Monat
        </h3>
        <div className="h-72">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" className="stroke-gray-200 dark:stroke-gray-700" />
              <XAxis dataKey="name" tick={{ fontSize: 11 }} />
              <YAxis unit=" €" tick={{ fontSize: 11 }} />
              <Tooltip formatter={(value: number) => [`${value.toFixed(2)} €`, '']} />
              <Legend />
              <Bar dataKey="Einspeiseerlös" fill={COLORS.feedin} stackId="pos" />
              <Bar dataKey="Ersparnis" fill={COLORS.consumption} stackId="pos" />
              <Bar dataKey="Netzbezug" fill={COLORS.grid} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </Card>
    </div>
  )
}

// ============================================================================
// CO2 TAB
// ============================================================================
function CO2Tab({ data, stats }: Omit<TabProps, 'anlage' | 'strompreis'>) {
  const CO2_FAKTOR = 0.38 // kg CO2 pro kWh (deutscher Strommix)

  const chartData = useMemo(() => {
    const sorted = [...data].sort((a, b) => {
      if (a.jahr !== b.jahr) return a.jahr - b.jahr
      return a.monat - b.monat
    })

    return sorted.map(md => {
      const erzeugung = md.pv_erzeugung_kwh || (md.einspeisung_kwh + (md.eigenverbrauch_kwh || 0))
      return {
        name: `${monatNamen[md.monat]} ${md.jahr.toString().slice(-2)}`,
        CO2: erzeugung * CO2_FAKTOR,
      }
    })
  }, [data])

  const gesamtCO2 = stats.gesamtErzeugung * CO2_FAKTOR
  const baeume = gesamtCO2 / 12.5 // Ein Baum bindet ca. 12.5 kg CO2/Jahr
  const autoKm = gesamtCO2 / 0.12 // ca. 120g CO2/km

  return (
    <div className="space-y-6">
      {/* CO2 KPIs */}
      <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
        <KPICard
          title="CO2 eingespart"
          value={(gesamtCO2 / 1000).toFixed(2)}
          unit="t"
          subtitle={`${stats.anzahlMonate} Monate`}
          icon={Leaf}
          color="text-green-500"
          bgColor="bg-green-50 dark:bg-green-900/20"
          formel="PV-Erzeugung × CO2-Faktor"
          berechnung={`${fmtCalc(stats.gesamtErzeugung, 0)} kWh × ${CO2_FAKTOR * 1000} g/kWh`}
          ergebnis={`= ${fmtCalc(gesamtCO2, 0)} kg = ${fmtCalc(gesamtCO2 / 1000, 2)} t`}
        />
        <KPICard
          title="Bäume äquivalent"
          value={baeume.toFixed(0)}
          unit="Bäume/Jahr"
          subtitle="Bindungsleistung"
          icon={Leaf}
          color="text-emerald-500"
          bgColor="bg-emerald-50 dark:bg-emerald-900/20"
          formel="CO2-Einsparung ÷ 12,5 kg/Baum/Jahr"
          berechnung={`${fmtCalc(gesamtCO2, 0)} kg ÷ 12,5 kg/Baum`}
          ergebnis={`= ${fmtCalc(baeume, 0)} Bäume`}
        />
        <KPICard
          title="Auto-km vermieden"
          value={(autoKm / 1000).toFixed(0)}
          unit="Tsd. km"
          subtitle="bei 120g CO2/km"
          icon={Calendar}
          color="text-teal-500"
          bgColor="bg-teal-50 dark:bg-teal-900/20"
          formel="CO2-Einsparung ÷ 120 g/km"
          berechnung={`${fmtCalc(gesamtCO2 * 1000, 0)} g ÷ 120 g/km`}
          ergebnis={`= ${fmtCalc(autoKm, 0)} km`}
        />
      </div>

      {/* CO2 Chart */}
      <Card>
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
          CO2-Einsparung pro Monat
        </h3>
        <div className="h-72">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" className="stroke-gray-200 dark:stroke-gray-700" />
              <XAxis dataKey="name" tick={{ fontSize: 11 }} />
              <YAxis unit=" kg" tick={{ fontSize: 11 }} />
              <Tooltip formatter={(value: number) => [`${value.toFixed(0)} kg CO2`, '']} />
              <Bar dataKey="CO2" name="CO2 eingespart" fill="#10b981" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </Card>

      {/* Info */}
      <Card>
        <h3 className="font-medium text-gray-900 dark:text-white mb-2">Berechnungsgrundlage</h3>
        <p className="text-sm text-gray-600 dark:text-gray-400">
          Die CO2-Einsparung wird mit dem deutschen Strommix von {CO2_FAKTOR * 1000} g CO2/kWh berechnet.
          Jede kWh selbst erzeugter Solarstrom, die fossilen Strom ersetzt, spart entsprechend CO2 ein.
        </p>
      </Card>
    </div>
  )
}

// ============================================================================
// KPI CARD COMPONENT
// ============================================================================
interface KPICardProps {
  title: string
  value: string
  unit: string
  subtitle?: string
  icon: React.ElementType
  color: string
  bgColor: string
  // Tooltip-Props
  formel?: string
  berechnung?: string
  ergebnis?: string
}

function KPICard({ title, value, unit, subtitle, icon: Icon, color, bgColor, formel, berechnung, ergebnis }: KPICardProps) {
  const valueContent = (
    <span className="text-2xl font-bold text-gray-900 dark:text-white">
      {value} <span className="text-sm font-normal">{unit}</span>
    </span>
  )

  return (
    <Card>
      <div className="flex items-start justify-between">
        <div>
          <p className="text-sm text-gray-500 dark:text-gray-400">{title}</p>
          <div className="mt-1">
            {formel ? (
              <FormelTooltip formel={formel} berechnung={berechnung} ergebnis={ergebnis}>
                {valueContent}
              </FormelTooltip>
            ) : (
              valueContent
            )}
          </div>
          {subtitle && (
            <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">{subtitle}</p>
          )}
        </div>
        <div className={`p-3 rounded-xl ${bgColor}`}>
          <Icon className={`h-6 w-6 ${color}`} />
        </div>
      </div>
    </Card>
  )
}
