import { useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { Sun, Zap, Battery, TrendingUp, ArrowRight } from 'lucide-react'
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts'
import { Card, Button, LoadingSpinner, Alert } from '../components/ui'
import { useAnlagen, useMonatsdaten, useMonatsdatenStats } from '../hooks'

const monatNamen = ['', 'Jan', 'Feb', 'Mär', 'Apr', 'Mai', 'Jun', 'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Dez']

export default function Dashboard() {
  const navigate = useNavigate()
  const { anlagen, loading: anlagenLoading } = useAnlagen()

  // Erste Anlage für Dashboard
  const erstesAnlageId = anlagen[0]?.id
  const { monatsdaten, loading: mdLoading } = useMonatsdaten(erstesAnlageId)
  const stats = useMonatsdatenStats(monatsdaten)

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

  const loading = anlagenLoading || mdLoading

  if (loading) {
    return <LoadingSpinner text="Lade Dashboard..." />
  }

  // Keine Anlage vorhanden
  if (anlagen.length === 0) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Dashboard</h1>
        <GettingStarted />
      </div>
    )
  }

  const anlage = anlagen[0]

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Dashboard</h1>
        <div className="text-sm text-gray-500 dark:text-gray-400">
          Anlage: <span className="font-medium text-gray-900 dark:text-white">{anlage.anlagenname}</span> ({anlage.leistung_kwp} kWp)
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <KPICard
          title="PV-Erzeugung"
          value={stats.gesamtErzeugung > 0 ? (stats.gesamtErzeugung / 1000).toFixed(1) : '---'}
          unit="MWh"
          subtitle={stats.anzahlMonate > 0 ? `${stats.anzahlMonate} Monate` : undefined}
          icon={Sun}
          color="text-energy-solar"
          bgColor="bg-yellow-50 dark:bg-yellow-900/20"
        />
        <KPICard
          title="Eigenverbrauch"
          value={stats.gesamtErzeugung > 0 ? ((stats.gesamtEigenverbrauch / stats.gesamtErzeugung) * 100).toFixed(1) : '---'}
          unit="%"
          subtitle={`${(stats.gesamtEigenverbrauch / 1000).toFixed(1)} MWh`}
          icon={Zap}
          color="text-energy-consumption"
          bgColor="bg-purple-50 dark:bg-purple-900/20"
        />
        <KPICard
          title="Autarkie"
          value={stats.durchschnittAutarkie > 0 ? stats.durchschnittAutarkie.toFixed(1) : '---'}
          unit="%"
          subtitle="Durchschnitt"
          icon={Battery}
          color="text-energy-battery"
          bgColor="bg-blue-50 dark:bg-blue-900/20"
        />
        <KPICard
          title="Netzbezug"
          value={stats.gesamtNetzbezug > 0 ? (stats.gesamtNetzbezug / 1000).toFixed(1) : '---'}
          unit="MWh"
          subtitle={`${stats.gesamtEinspeisung.toFixed(0)} kWh eingespeist`}
          icon={TrendingUp}
          color="text-energy-grid"
          bgColor="bg-red-50 dark:bg-red-900/20"
        />
      </div>

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
            <Button onClick={() => navigate('/monatsdaten')}>
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
          onClick={() => navigate('/monatsdaten')}
        />
        <QuickLink
          title="Auswertungen"
          description="Detaillierte Analysen und Kennzahlen"
          onClick={() => navigate('/auswertung')}
        />
        <QuickLink
          title="Investitionen"
          description="E-Auto, Speicher, Wärmepumpe verwalten"
          onClick={() => navigate('/investitionen')}
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
        Willkommen bei EEDC!
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
      <Button onClick={() => navigate('/anlagen')}>
        Jetzt starten
        <ArrowRight className="h-4 w-4 ml-2" />
      </Button>
    </Card>
  )
}
