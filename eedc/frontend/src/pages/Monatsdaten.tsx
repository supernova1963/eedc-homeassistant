import { Plus, Calendar } from 'lucide-react'

export default function Monatsdaten() {
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
          Monatsdaten
        </h1>
        <button className="btn btn-primary flex items-center gap-2">
          <Plus className="h-5 w-5" />
          Neuer Monat
        </button>
      </div>

      {/* Empty State */}
      <div className="card p-12 text-center">
        <div className="mx-auto w-12 h-12 rounded-full bg-gray-100 dark:bg-gray-700 flex items-center justify-center mb-4">
          <Calendar className="h-6 w-6 text-gray-400" />
        </div>
        <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-2">
          Keine Monatsdaten vorhanden
        </h3>
        <p className="text-gray-500 dark:text-gray-400 mb-4">
          Erfasse deine ersten Monatsdaten manuell oder importiere eine CSV-Datei.
        </p>
        <div className="flex justify-center gap-4">
          <button className="btn btn-primary">
            Manuell erfassen
          </button>
          <button className="btn btn-secondary">
            CSV importieren
          </button>
        </div>
      </div>
    </div>
  )
}
