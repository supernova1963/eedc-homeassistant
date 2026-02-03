import { useState, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  BarChart, Bar, LineChart, Line, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer
} from 'recharts'
import {
  Sun, Zap, Battery, TrendingUp, Leaf, Euro, Calendar, ArrowRight
} from 'lucide-react'
import { Card, Button, LoadingSpinner, Alert } from '../components/ui'
import { useAnlagen, useMonatsdaten, useMonatsdatenStats, useAktuellerStrompreis } from '../hooks'

const monatNamen = ['', 'Jan', 'Feb', 'Mär', 'Apr', 'Mai', 'Jun', 'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Dez']

const COLORS = {
  solar: '#f59e0b',
  grid: '#ef4444',
  consumption: '#8b5cf6',
  battery: '#3b82f6',
  feedin: '#10b981',
}

type TabType = 'uebersicht' | 'pv' | 'finanzen' | 'co2'

export default function Auswertung() {
  const navigate = useNavigate()
  const [activeTab, setActiveTab] = useState<TabType>('uebersicht')
  const [selectedYear, setSelectedYear] = useState<number | 'all'>('all')

  const { anlagen, loading: anlagenLoading } = useAnlagen()
  const [selectedAnlageId, setSelectedAnlageId] = useState<number | null>(null)

  const anlageId = selectedAnlageId ?? anlagen[0]?.id
  const anlage = anlagen.find(a => a.id === anlageId)
  const { monatsdaten, loading: mdLoading } = useMonatsdaten(anlageId)
  useMonatsdatenStats(monatsdaten) // Für gefilterte Stats verwendet
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
    { key: 'finanzen', label: 'Finanzen' },
    { key: 'co2', label: 'CO2' },
  ]

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Auswertung</h1>
        <div className="flex items-center gap-3">
          {/* Jahr-Filter */}
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
        <UebersichtTab
          data={filteredData}
          stats={filteredStats}
          anlage={anlage}
          strompreis={strompreis}
        />
      )}
      {activeTab === 'pv' && (
        <PVTab data={filteredData} anlage={anlage} />
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

// Übersicht Tab
interface TabProps {
  data: ReturnType<typeof useMonatsdaten>['monatsdaten']
  stats: ReturnType<typeof useMonatsdatenStats>
  anlage?: ReturnType<typeof useAnlagen>['anlagen'][0]
  strompreis?: ReturnType<typeof useAktuellerStrompreis>['strompreis']
}

function UebersichtTab({ data, stats, anlage, strompreis }: TabProps) {
  // Chart-Daten
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
    }))
  }, [data])

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
    const nettoErtrag = einspeiseErloes + eigenverbrauchErsparnis - netzbezugKosten
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
        />
        <KPICard
          title="Eigenverbrauch"
          value={stats.gesamtErzeugung > 0 ? ((stats.gesamtEigenverbrauch / stats.gesamtErzeugung) * 100).toFixed(0) : '0'}
          unit="%"
          subtitle={`${(stats.gesamtEigenverbrauch / 1000).toFixed(1)} MWh`}
          icon={Zap}
          color="text-purple-500"
          bgColor="bg-purple-50 dark:bg-purple-900/20"
        />
        <KPICard
          title="Autarkie"
          value={stats.durchschnittAutarkie.toFixed(0)}
          unit="%"
          subtitle="Durchschnitt"
          icon={Battery}
          color="text-blue-500"
          bgColor="bg-blue-50 dark:bg-blue-900/20"
        />
        <KPICard
          title="Netto-Ertrag"
          value={finanzen ? finanzen.nettoErtrag.toFixed(0) : '---'}
          unit="€"
          subtitle={finanzen ? `${stats.anzahlMonate} Monate` : 'Strompreis fehlt'}
          icon={Euro}
          color="text-green-500"
          bgColor="bg-green-50 dark:bg-green-900/20"
        />
      </div>

      {/* Charts */}
      <div className="grid md:grid-cols-3 gap-6">
        {/* Bar Chart */}
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

// PV Tab
function PVTab({ data, anlage }: Omit<TabProps, 'strompreis' | 'stats'>) {
  const chartData = useMemo(() => {
    const sorted = [...data].sort((a, b) => {
      if (a.jahr !== b.jahr) return a.jahr - b.jahr
      return a.monat - b.monat
    })

    return sorted.map(md => ({
      name: `${monatNamen[md.monat]} ${md.jahr.toString().slice(-2)}`,
      Erzeugung: md.pv_erzeugung_kwh || (md.einspeisung_kwh + (md.eigenverbrauch_kwh || 0)),
      SpezErtrag: anlage?.leistung_kwp
        ? ((md.pv_erzeugung_kwh || md.einspeisung_kwh) / anlage.leistung_kwp)
        : 0,
    }))
  }, [data, anlage])

  // Jahresvergleich
  const jahresVergleich = useMemo(() => {
    const byYear: Record<number, number> = {}
    data.forEach(md => {
      const erzeugung = md.pv_erzeugung_kwh || (md.einspeisung_kwh + (md.eigenverbrauch_kwh || 0))
      byYear[md.jahr] = (byYear[md.jahr] || 0) + erzeugung
    })
    return Object.entries(byYear)
      .map(([jahr, erzeugung]) => ({ jahr: Number(jahr), erzeugung }))
      .sort((a, b) => a.jahr - b.jahr)
  }, [data])

  return (
    <div className="space-y-6">
      {/* PV Erzeugung Chart */}
      <Card>
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
          PV-Erzeugung
        </h3>
        <div className="h-72">
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

      {/* Jahresvergleich */}
      {jahresVergleich.length > 1 && (
        <Card>
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
            Jahresvergleich
          </h3>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={jahresVergleich}>
                <CartesianGrid strokeDasharray="3 3" className="stroke-gray-200 dark:stroke-gray-700" />
                <XAxis dataKey="jahr" />
                <YAxis unit=" kWh" />
                <Tooltip formatter={(value: number) => [`${value.toFixed(0)} kWh`, '']} />
                <Bar dataKey="erzeugung" name="Erzeugung" fill={COLORS.solar} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>
      )}

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
    </div>
  )
}

// Finanzen Tab
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
    const nettoErtrag = einspeiseErloes + eigenverbrauchErsparnis - netzbezugKosten
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
        />
        <KPICard
          title="EV-Ersparnis"
          value={gesamt.eigenverbrauchErsparnis.toFixed(0)}
          unit="€"
          subtitle="vermiedener Netzbezug"
          icon={Zap}
          color="text-purple-500"
          bgColor="bg-purple-50 dark:bg-purple-900/20"
        />
        <KPICard
          title="Netzbezug"
          value={gesamt.netzbezugKosten.toFixed(0)}
          unit="€"
          subtitle={`${strompreis.netzbezug_arbeitspreis_cent_kwh.toFixed(1)} ct/kWh`}
          icon={Battery}
          color="text-red-500"
          bgColor="bg-red-50 dark:bg-red-900/20"
        />
        <KPICard
          title="Netto-Ertrag"
          value={gesamt.nettoErtrag.toFixed(0)}
          unit="€"
          subtitle="Gesamt"
          icon={Euro}
          color="text-blue-500"
          bgColor="bg-blue-50 dark:bg-blue-900/20"
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

// CO2 Tab
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
        />
        <KPICard
          title="Bäume äquivalent"
          value={baeume.toFixed(0)}
          unit="Bäume/Jahr"
          subtitle="Bindungsleistung"
          icon={Leaf}
          color="text-emerald-500"
          bgColor="bg-emerald-50 dark:bg-emerald-900/20"
        />
        <KPICard
          title="Auto-km vermieden"
          value={(autoKm / 1000).toFixed(0)}
          unit="Tsd. km"
          subtitle="bei 120g CO2/km"
          icon={Calendar}
          color="text-teal-500"
          bgColor="bg-teal-50 dark:bg-teal-900/20"
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

// KPI Card Component
interface KPICardProps {
  title: string
  value: string
  unit: string
  subtitle?: string
  icon: React.ElementType
  color: string
  bgColor: string
}

function KPICard({ title, value, unit, subtitle, icon: Icon, color, bgColor }: KPICardProps) {
  return (
    <Card>
      <div className="flex items-start justify-between">
        <div>
          <p className="text-sm text-gray-500 dark:text-gray-400">{title}</p>
          <p className="text-2xl font-bold text-gray-900 dark:text-white mt-1">
            {value} <span className="text-sm font-normal">{unit}</span>
          </p>
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
