import { Upload, FileSpreadsheet, Home } from 'lucide-react'

export default function Import() {
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
        Daten Import
      </h1>

      <div className="grid md:grid-cols-2 gap-6">
        {/* CSV Import */}
        <div className="card p-6">
          <div className="flex items-center gap-3 mb-4">
            <div className="p-2 rounded-lg bg-blue-50 dark:bg-blue-900/20">
              <FileSpreadsheet className="h-6 w-6 text-blue-500" />
            </div>
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
              CSV Import
            </h2>
          </div>
          <p className="text-gray-500 dark:text-gray-400 mb-4">
            Importiere Monatsdaten aus einer CSV-Datei. Das Template wird automatisch basierend auf deinen Investitionen generiert.
          </p>
          <div className="space-y-3">
            <button className="btn btn-secondary w-full">
              Template herunterladen
            </button>
            <div className="border-2 border-dashed border-gray-300 dark:border-gray-600 rounded-lg p-8 text-center hover:border-primary-500 transition-colors cursor-pointer">
              <Upload className="h-8 w-8 mx-auto text-gray-400 mb-2" />
              <p className="text-sm text-gray-500 dark:text-gray-400">
                CSV-Datei hierher ziehen oder klicken zum Auswählen
              </p>
            </div>
          </div>
        </div>

        {/* HA Import */}
        <div className="card p-6">
          <div className="flex items-center gap-3 mb-4">
            <div className="p-2 rounded-lg bg-cyan-50 dark:bg-cyan-900/20">
              <Home className="h-6 w-6 text-cyan-500" />
            </div>
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
              Home Assistant Import
            </h2>
          </div>
          <p className="text-gray-500 dark:text-gray-400 mb-4">
            Importiere Daten direkt aus deinem Home Assistant Energy Dashboard.
          </p>
          <div className="p-4 bg-yellow-50 dark:bg-yellow-900/20 rounded-lg text-sm text-yellow-700 dark:text-yellow-300 mb-4">
            Konfiguriere zuerst die Sensor-Zuordnung in den Einstellungen.
          </div>
          <button className="btn btn-secondary w-full" disabled>
            Aus Home Assistant importieren
          </button>
        </div>
      </div>
    </div>
  )
}
