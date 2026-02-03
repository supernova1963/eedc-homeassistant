import { Plus, Car, Flame, Battery, Plug } from 'lucide-react'

const investitionTypen = [
  { typ: 'e-auto', label: 'E-Auto', icon: Car, color: 'text-blue-500' },
  { typ: 'waermepumpe', label: 'Wärmepumpe', icon: Flame, color: 'text-orange-500' },
  { typ: 'speicher', label: 'Speicher', icon: Battery, color: 'text-green-500' },
  { typ: 'wallbox', label: 'Wallbox', icon: Plug, color: 'text-purple-500' },
]

export default function Investitionen() {
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
          Investitionen
        </h1>
        <button className="btn btn-primary flex items-center gap-2">
          <Plus className="h-5 w-5" />
          Neue Investition
        </button>
      </div>

      {/* Typ-Übersicht */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {investitionTypen.map((typ) => (
          <div key={typ.typ} className="card p-4 text-center hover:shadow-md transition-shadow cursor-pointer">
            <typ.icon className={`h-8 w-8 mx-auto ${typ.color}`} />
            <p className="mt-2 text-sm font-medium text-gray-900 dark:text-white">
              {typ.label}
            </p>
            <p className="text-xs text-gray-500 dark:text-gray-400">
              0 vorhanden
            </p>
          </div>
        ))}
      </div>

      {/* Empty State */}
      <div className="card p-12 text-center">
        <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-2">
          Keine Investitionen vorhanden
        </h3>
        <p className="text-gray-500 dark:text-gray-400 mb-4">
          Erfasse deine Investitionen (E-Auto, Wärmepumpe, Speicher, etc.) um deren Wirtschaftlichkeit zu analysieren.
        </p>
        <button className="btn btn-primary">
          Erste Investition anlegen
        </button>
      </div>
    </div>
  )
}
