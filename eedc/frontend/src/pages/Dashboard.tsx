/**
 * Dashboard (Cockpit Übersicht)
 * Zeigt aggregierte Übersicht ALLER Komponenten: PV, Wärmepumpe, Speicher, E-Auto, Balkonkraftwerk
 */

import { useState, useEffect, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { Sun, Zap, Battery, TrendingUp, ArrowRight, Flame, Car, Home } from 'lucide-react'
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts'
import { Card, Button, LoadingSpinner, FormelTooltip, fmtCalc } from '../components/ui'
import { useAnlagen, useMonatsdaten, useMonatsdatenStats, useInvestitionen } from '../hooks'
import { investitionenApi } from '../api'
import type {
  WaermepumpeDashboardResponse,
  SpeicherDashboardResponse,
  EAutoDashboardResponse,
  BalkonkraftwerkDashboardResponse
} from '../api/investitionen'

const monatNamen = ['', 'Jan', 'Feb', 'Mär', 'Apr', 'Mai', 'Jun', 'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Dez']

export default function Dashboard() {
  const navigate = useNavigate()
  const { anlagen, loading: anlagenLoading } = useAnlagen()

  // Erste Anlage für Dashboard
  const erstesAnlageId = anlagen[0]?.id
  const { monatsdaten, loading: mdLoading } = useMonatsdaten(erstesAnlageId)
  const { loading: invLoading } = useInvestitionen(erstesAnlageId)
  const stats = useMonatsdatenStats(monatsdaten)

  // Investitions-Dashboards laden
  const [wpData, setWpData] = useState<WaermepumpeDashboardResponse[]>([])
  const [spData, setSpData] = useState<SpeicherDashboardResponse[]>([])
  const [eaData, setEaData] = useState<EAutoDashboardResponse[]>([])
  const [bkData, setBkData] = useState<BalkonkraftwerkDashboardResponse[]>([])
  const [, setCompLoading] = useState(false)

  useEffect(() => {
    if (!erstesAnlageId) return

    const loadComponentData = async () => {
      setCompLoading(true)
      try {
        const [wp, sp, ea, bk] = await Promise.all([
          investitionenApi.getWaermepumpeDashboard(erstesAnlageId).catch(() => []),
          investitionenApi.getSpeicherDashboard(erstesAnlageId).catch(() => []),
          investitionenApi.getEAutoDashboard(erstesAnlageId).catch(() => []),
          investitionenApi.getBalkonkraftwerkDashboard(erstesAnlageId).catch(() => []),
        ])
        setWpData(wp)
        setSpData(sp)
        setEaData(ea)
        setBkData(bk)
      } finally {
        setCompLoading(false)
      }
    }

    loadComponentData()
  }, [erstesAnlageId])

  // Chart-Daten vorbereiten
  const chartData = useMemo(() => {
    const sorted = [...monatsdaten].sort((a, b) => {
      if (a.jahr !== b.jahr) return a.jahr - b.jahr
      return a.monat - b.monat
    })

    return sorted.slice(-12).map(md => ({
      name: `${monatNamen[md.monat]} ${md.jahr.toString().slice(-2)}`,
      Einspeisung: md.einspeisung_kwh,
      Eigenverbrauch: md.eigenverbrauch_kwh || 0,
      Netzbezug: md.netzbezug_kwh,
    }))
  }, [monatsdaten])

  // Komponenten-Zusammenfassung
  const komponenten = useMemo(() => {
    const result: {
      name: string
      icon: React.ElementType
      color: string
      value: string
      unit: string
      subtitle: string
      href: string
    }[] = []

    // Wärmepumpe
    if (wpData.length > 0) {
      const gesamt = wpData.reduce((sum, wp) => sum + wp.zusammenfassung.gesamt_stromverbrauch_kwh, 0)
      const cop = wpData.reduce((sum, wp) => sum + (wp.zusammenfassung.durchschnitt_cop || 0), 0) / wpData.length
      result.push({
        name: 'Wärmepumpe',
        icon: Flame,
        color: 'text-red-500',
        value: (gesamt / 1000).toFixed(1),
        unit: 'MWh',
        subtitle: cop > 0 ? `COP Ø ${cop.toFixed(1)}` : 'Stromverbrauch',
        href: '/cockpit/waermepumpe'
      })
    }

    // Speicher
    if (spData.length > 0) {
      const zyklen = spData.reduce((sum, sp) => sum + sp.zusammenfassung.vollzyklen, 0)
      const ladung = spData.reduce((sum, sp) => sum + sp.zusammenfassung.gesamt_ladung_kwh, 0)
      result.push({
        name: 'Speicher',
        icon: Battery,
        color: 'text-green-500',
        value: (ladung / 1000).toFixed(1),
        unit: 'MWh',
        subtitle: `${zyklen.toFixed(0)} Zyklen`,
        href: '/cockpit/speicher'
      })
    }

    // E-Auto
    if (eaData.length > 0) {
      const km = eaData.reduce((sum, ea) => sum + ea.zusammenfassung.gesamt_km, 0)
      const pvAnteil = eaData.reduce((sum, ea) => sum + ea.zusammenfassung.pv_anteil_gesamt_prozent, 0) / eaData.length
      result.push({
        name: 'E-Auto',
        icon: Car,
        color: 'text-purple-500',
        value: (km / 1000).toFixed(1),
        unit: 'Tkm',
        subtitle: `${pvAnteil.toFixed(0)}% PV-Anteil`,
        href: '/cockpit/e-auto'
      })
    }

    // Balkonkraftwerk
    if (bkData.length > 0) {
      const erzeugung = bkData.reduce((sum, bk) => sum + bk.zusammenfassung.gesamt_erzeugung_kwh, 0)
      result.push({
        name: 'Balkonkraftwerk',
        icon: Sun,
        color: 'text-orange-500',
        value: erzeugung.toFixed(0),
        unit: 'kWh',
        subtitle: 'Erzeugung',
        href: '/cockpit/balkonkraftwerk'
      })
    }

    return result
  }, [wpData, spData, eaData, bkData])

  const loading = anlagenLoading || mdLoading || invLoading

  if (loading) {
    return <LoadingSpinner text="Lade Dashboard..." />
  }

  // Keine Anlage vorhanden
  if (anlagen.length === 0) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Übersicht</h1>
        <GettingStarted />
      </div>
    )
  }

  const anlage = anlagen[0]

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Home className="h-8 w-8 text-primary-500" />
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Übersicht</h1>
        </div>
        <div className="text-sm text-gray-500 dark:text-gray-400">
          Anlage: <span className="font-medium text-gray-900 dark:text-white">{anlage.anlagenname}</span> ({anlage.leistung_kwp} kWp)
        </div>
      </div>

      {/* Haupt-KPIs */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <KPICard
          title="PV-Erzeugung"
          value={stats.gesamtErzeugung > 0 ? (stats.gesamtErzeugung / 1000).toFixed(1) : '---'}
          unit="MWh"
          subtitle={stats.anzahlMonate > 0 ? `${stats.anzahlMonate} Monate` : undefined}
          icon={Sun}
          color="text-energy-solar"
          bgColor="bg-yellow-50 dark:bg-yellow-900/20"
          onClick={() => navigate('/cockpit/pv-anlage')}
          formel="Σ PV-Erzeugung aller Monate"
          berechnung={`${fmtCalc(stats.gesamtErzeugung, 0)} kWh`}
          ergebnis={`= ${fmtCalc(stats.gesamtErzeugung / 1000, 1)} MWh`}
        />
        <KPICard
          title="Eigenverbrauch"
          value={stats.gesamtErzeugung > 0 ? ((stats.gesamtEigenverbrauch / stats.gesamtErzeugung) * 100).toFixed(1) : '---'}
          unit="%"
          subtitle={`${(stats.gesamtEigenverbrauch / 1000).toFixed(1)} MWh`}
          icon={Zap}
          color="text-energy-consumption"
          bgColor="bg-purple-50 dark:bg-purple-900/20"
          formel="Eigenverbrauch ÷ PV-Erzeugung × 100"
          berechnung={`${fmtCalc(stats.gesamtEigenverbrauch, 0)} kWh ÷ ${fmtCalc(stats.gesamtErzeugung, 0)} kWh × 100`}
          ergebnis={`= ${fmtCalc((stats.gesamtEigenverbrauch / stats.gesamtErzeugung) * 100, 1)} %`}
        />
        <KPICard
          title="Autarkie"
          value={stats.durchschnittAutarkie > 0 ? stats.durchschnittAutarkie.toFixed(1) : '---'}
          unit="%"
          subtitle="Durchschnitt"
          icon={Battery}
          color="text-energy-battery"
          bgColor="bg-blue-50 dark:bg-blue-900/20"
          formel="Eigenverbrauch ÷ Gesamtverbrauch × 100"
          berechnung="Durchschnitt aller Monate"
          ergebnis={`= ${fmtCalc(stats.durchschnittAutarkie, 1)} %`}
        />
        <KPICard
          title="Netzbezug"
          value={stats.gesamtNetzbezug > 0 ? (stats.gesamtNetzbezug / 1000).toFixed(1) : '---'}
          unit="MWh"
          subtitle={`${stats.gesamtEinspeisung.toFixed(0)} kWh eingespeist`}
          icon={TrendingUp}
          color="text-energy-grid"
          bgColor="bg-red-50 dark:bg-red-900/20"
          formel="Σ Netzbezug aller Monate"
          berechnung={`${fmtCalc(stats.gesamtNetzbezug, 0)} kWh`}
          ergebnis={`= ${fmtCalc(stats.gesamtNetzbezug / 1000, 1)} MWh`}
        />
      </div>

      {/* Komponenten-Kacheln */}
      {komponenten.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {komponenten.map((komp) => (
            <button
              key={komp.name}
              onClick={() => navigate(komp.href)}
              className="card p-4 text-left hover:shadow-md transition-shadow group"
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className={`p-2 rounded-lg bg-gray-100 dark:bg-gray-800`}>
                    <komp.icon className={`h-5 w-5 ${komp.color}`} />
                  </div>
                  <div>
                    <p className="text-sm text-gray-500 dark:text-gray-400">{komp.name}</p>
                    <p className="text-lg font-bold text-gray-900 dark:text-white">
                      {komp.value} <span className="text-sm font-normal">{komp.unit}</span>
                    </p>
                    <p className="text-xs text-gray-400 dark:text-gray-500">{komp.subtitle}</p>
                  </div>
                </div>
                <ArrowRight className="h-5 w-5 text-gray-400 group-hover:text-primary-600 transition-colors" />
              </div>
            </button>
          ))}
        </div>
      )}

      {/* Chart */}
      {chartData.length > 0 ? (
        <Card>
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
            Monatlicher Verlauf
          </h2>
          <div className="h-72">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" className="stroke-gray-200 dark:stroke-gray-700" />
                <XAxis dataKey="name" className="text-xs" />
                <YAxis unit=" kWh" className="text-xs" />
                <Tooltip
                  contentStyle={{
                    backgroundColor: 'var(--tooltip-bg, #fff)',
                    borderColor: 'var(--tooltip-border, #e5e7eb)',
                  }}
                  formatter={(value: number) => [`${value.toFixed(0)} kWh`, '']}
                />
                <Legend />
                <Bar dataKey="Eigenverbrauch" fill="#8b5cf6" stackId="a" />
                <Bar dataKey="Einspeisung" fill="#10b981" stackId="a" />
                <Bar dataKey="Netzbezug" fill="#ef4444" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>
      ) : (
        <Card>
          <div className="text-center py-8">
            <p className="text-gray-500 dark:text-gray-400 mb-4">
              Noch keine Monatsdaten vorhanden. Erfasse deine ersten Daten!
            </p>
            <Button onClick={() => navigate('/einstellungen/monatsdaten')}>
              Monatsdaten erfassen
              <ArrowRight className="h-4 w-4 ml-2" />
            </Button>
          </div>
        </Card>
      )}

      {/* Quick Links */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <QuickLink
          title="Monatsdaten"
          description="Neue Daten erfassen oder CSV importieren"
          onClick={() => navigate('/einstellungen/monatsdaten')}
        />
        <QuickLink
          title="Auswertungen"
          description="Detaillierte Analysen und Kennzahlen"
          onClick={() => navigate('/auswertungen')}
        />
        <QuickLink
          title="Investitionen"
          description="E-Auto, Speicher, Wärmepumpe verwalten"
          onClick={() => navigate('/einstellungen/investitionen')}
        />
      </div>
    </div>
  )
}

interface KPICardProps {
  title: string
  value: string
  unit: string
  subtitle?: string
  icon: React.ElementType
  color: string
  bgColor: string
  onClick?: () => void
  // Tooltip-Props
  formel?: string
  berechnung?: string
  ergebnis?: string
}

function KPICard({ title, value, unit, subtitle, icon: Icon, color, bgColor, onClick, formel, berechnung, ergebnis }: KPICardProps) {
  const valueContent = (
    <span className="text-2xl font-bold text-gray-900 dark:text-white">
      {value} <span className="text-sm font-normal">{unit}</span>
    </span>
  )

  const content = (
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
  )

  if (onClick) {
    return (
      <button onClick={onClick} className="card p-4 text-left hover:shadow-md transition-shadow">
        {content}
      </button>
    )
  }

  return <Card>{content}</Card>
}

function QuickLink({ title, description, onClick }: { title: string; description: string; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="card p-4 text-left hover:shadow-md transition-shadow group"
    >
      <div className="flex items-center justify-between">
        <div>
          <h3 className="font-medium text-gray-900 dark:text-white">{title}</h3>
          <p className="text-sm text-gray-500 dark:text-gray-400">{description}</p>
        </div>
        <ArrowRight className="h-5 w-5 text-gray-400 group-hover:text-primary-600 transition-colors" />
      </div>
    </button>
  )
}

function GettingStarted() {
  const navigate = useNavigate()

  return (
    <Card className="bg-primary-50 dark:bg-primary-900/20 border-primary-200 dark:border-primary-800">
      <h2 className="text-lg font-semibold text-primary-900 dark:text-primary-100 mb-4">
        Willkommen bei eedc!
      </h2>
      <p className="text-primary-700 dark:text-primary-300 mb-4">
        Starte mit diesen Schritten, um deine PV-Anlage zu analysieren:
      </p>
      <ol className="list-decimal list-inside text-primary-700 dark:text-primary-300 space-y-2 mb-6">
        <li>Lege deine PV-Anlage unter "Anlagen" an</li>
        <li>Konfiguriere deine Strompreise</li>
        <li>Erfasse Monatsdaten oder importiere eine CSV</li>
        <li>Analysiere deine Ergebnisse in den Auswertungen</li>
      </ol>
      <Button onClick={() => navigate('/einstellungen/anlage')}>
        Jetzt starten
        <ArrowRight className="h-4 w-4 ml-2" />
      </Button>
    </Card>
  )
}
