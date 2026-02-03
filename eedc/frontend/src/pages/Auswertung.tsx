import { BarChart3 } from 'lucide-react'

export default function Auswertung() {
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
        Auswertung
      </h1>

      {/* Tabs placeholder */}
      <div className="border-b border-gray-200 dark:border-gray-700">
        <nav className="flex gap-4">
          {['Übersicht', 'PV-Anlage', 'Investitionen', 'ROI', 'CO2'].map((tab, i) => (
            <button
              key={tab}
              className={`py-3 px-1 border-b-2 text-sm font-medium transition-colors ${
                i === 0
                  ? 'border-primary-500 text-primary-600 dark:text-primary-400'
                  : 'border-transparent text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-300'
              }`}
            >
              {tab}
            </button>
          ))}
        </nav>
      </div>

      {/* Empty State */}
      <div className="card p-12 text-center">
        <div className="mx-auto w-12 h-12 rounded-full bg-gray-100 dark:bg-gray-700 flex items-center justify-center mb-4">
          <BarChart3 className="h-6 w-6 text-gray-400" />
        </div>
        <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-2">
          Noch keine Auswertungen möglich
        </h3>
        <p className="text-gray-500 dark:text-gray-400">
          Erfasse zuerst Monatsdaten, um Auswertungen und Analysen zu sehen.
        </p>
      </div>
    </div>
  )
}
