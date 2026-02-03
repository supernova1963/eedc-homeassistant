import { Sun, Zap, Battery, TrendingUp } from 'lucide-react'

export default function Dashboard() {
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
        Dashboard
      </h1>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <KPICard
          title="PV-Erzeugung"
          value="---"
          unit="kWh"
          icon={Sun}
          color="text-energy-solar"
          bgColor="bg-yellow-50 dark:bg-yellow-900/20"
        />
        <KPICard
          title="Eigenverbrauch"
          value="---"
          unit="%"
          icon={Zap}
          color="text-energy-consumption"
          bgColor="bg-purple-50 dark:bg-purple-900/20"
        />
        <KPICard
          title="Autarkie"
          value="---"
          unit="%"
          icon={Battery}
          color="text-energy-battery"
          bgColor="bg-blue-50 dark:bg-blue-900/20"
        />
        <KPICard
          title="Ersparnis"
          value="---"
          unit="€"
          icon={TrendingUp}
          color="text-energy-export"
          bgColor="bg-green-50 dark:bg-green-900/20"
        />
      </div>

      {/* Placeholder for charts */}
      <div className="card p-6">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
          Monatlicher Verlauf
        </h2>
        <div className="h-64 flex items-center justify-center text-gray-400 dark:text-gray-500">
          <p>Chart wird hier angezeigt sobald Daten vorhanden sind.</p>
        </div>
      </div>

      {/* Getting Started */}
      <div className="card p-6 bg-primary-50 dark:bg-primary-900/20 border-primary-200 dark:border-primary-800">
        <h2 className="text-lg font-semibold text-primary-900 dark:text-primary-100 mb-2">
          Erste Schritte
        </h2>
        <ol className="list-decimal list-inside text-primary-700 dark:text-primary-300 space-y-1">
          <li>Lege eine Anlage unter "Anlagen" an</li>
          <li>Konfiguriere deine Strompreise</li>
          <li>Erfasse Monatsdaten oder importiere eine CSV</li>
          <li>Schau dir deine Auswertungen an</li>
        </ol>
      </div>
    </div>
  )
}

interface KPICardProps {
  title: string
  value: string
  unit: string
  icon: React.ElementType
  color: string
  bgColor: string
}

function KPICard({ title, value, unit, icon: Icon, color, bgColor }: KPICardProps) {
  return (
    <div className="card p-6">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm text-gray-500 dark:text-gray-400">{title}</p>
          <p className="text-2xl font-bold text-gray-900 dark:text-white mt-1">
            {value} <span className="text-sm font-normal">{unit}</span>
          </p>
        </div>
        <div className={`p-3 rounded-xl ${bgColor}`}>
          <Icon className={`h-6 w-6 ${color}`} />
        </div>
      </div>
    </div>
  )
}
