import { Plus } from 'lucide-react'

export default function Anlagen() {
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
          Anlagen
        </h1>
        <button className="btn btn-primary flex items-center gap-2">
          <Plus className="h-5 w-5" />
          Neue Anlage
        </button>
      </div>

      {/* Empty State */}
      <div className="card p-12 text-center">
        <div className="mx-auto w-12 h-12 rounded-full bg-gray-100 dark:bg-gray-700 flex items-center justify-center mb-4">
          <Plus className="h-6 w-6 text-gray-400" />
        </div>
        <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-2">
          Keine Anlagen vorhanden
        </h3>
        <p className="text-gray-500 dark:text-gray-400 mb-4">
          Lege deine erste PV-Anlage an, um mit der Datenerfassung zu beginnen.
        </p>
        <button className="btn btn-primary">
          Erste Anlage anlegen
        </button>
      </div>
    </div>
  )
}
