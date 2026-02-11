/**
 * Datenerfassung - Informationsseite
 *
 * v0.9.9: Vereinfacht - EEDC ist primär Standalone
 *
 * Diese Seite erklärt die Möglichkeiten zur Datenerfassung:
 * 1. Manuelles Formular (empfohlen für Einsteiger)
 * 2. CSV-Import (empfohlen für regelmäßige Erfassung)
 * 3. Optional: MQTT Export für KPIs nach HA
 */

import {
  FileSpreadsheet,
  PenLine,
  Upload,
  ArrowRight,
  Info,
  ExternalLink,
} from 'lucide-react'

export default function HAImportSettings() {
  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
          <FileSpreadsheet className="w-6 h-6" />
          Datenerfassung
        </h1>
        <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
          So erfassen Sie Ihre monatlichen Energiedaten in EEDC
        </p>
      </div>

      {/* Hauptinhalt */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Option 1: Manuelles Formular */}
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6 border-2 border-blue-200 dark:border-blue-800">
          <div className="flex items-center gap-3 mb-4">
            <div className="p-3 bg-blue-100 dark:bg-blue-900 rounded-lg">
              <PenLine className="w-6 h-6 text-blue-600 dark:text-blue-400" />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
                Manuelles Formular
              </h2>
              <span className="text-xs bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300 px-2 py-0.5 rounded">
                Empfohlen für Einsteiger
              </span>
            </div>
          </div>

          <p className="text-gray-600 dark:text-gray-400 mb-4">
            Geben Sie Ihre Monatsdaten direkt im Formular ein.
            Ideal für gelegentliche Erfassung oder wenn Sie nur wenige Werte haben.
          </p>

          <ul className="space-y-2 text-sm text-gray-600 dark:text-gray-400 mb-4">
            <li className="flex items-center gap-2">
              <ArrowRight className="w-4 h-4 text-blue-500" />
              Einstellungen → Monatsdaten → Neu
            </li>
            <li className="flex items-center gap-2">
              <ArrowRight className="w-4 h-4 text-blue-500" />
              Wetterdaten können automatisch geladen werden
            </li>
            <li className="flex items-center gap-2">
              <ArrowRight className="w-4 h-4 text-blue-500" />
              Investitions-Daten pro Komponente erfassen
            </li>
          </ul>

          <a
            href="#/einstellungen/monatsdaten"
            className="btn btn-primary w-full flex items-center justify-center gap-2"
          >
            <PenLine className="w-4 h-4" />
            Zur Monatsdaten-Erfassung
          </a>
        </div>

        {/* Option 2: CSV-Import */}
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6 border-2 border-green-200 dark:border-green-800">
          <div className="flex items-center gap-3 mb-4">
            <div className="p-3 bg-green-100 dark:bg-green-900 rounded-lg">
              <Upload className="w-6 h-6 text-green-600 dark:text-green-400" />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
                CSV-Import
              </h2>
              <span className="text-xs bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300 px-2 py-0.5 rounded">
                Empfohlen für regelmäßige Erfassung
              </span>
            </div>
          </div>

          <p className="text-gray-600 dark:text-gray-400 mb-4">
            Laden Sie Monatsdaten per CSV-Datei hoch.
            Perfekt für größere Datenmengen oder historische Daten.
          </p>

          <ul className="space-y-2 text-sm text-gray-600 dark:text-gray-400 mb-4">
            <li className="flex items-center gap-2">
              <ArrowRight className="w-4 h-4 text-green-500" />
              Einstellungen → Import/Export
            </li>
            <li className="flex items-center gap-2">
              <ArrowRight className="w-4 h-4 text-green-500" />
              Vorlage herunterladen (passt zu Ihren Investitionen)
            </li>
            <li className="flex items-center gap-2">
              <ArrowRight className="w-4 h-4 text-green-500" />
              Wetterdaten werden automatisch ergänzt
            </li>
          </ul>

          <a
            href="#/einstellungen/import"
            className="btn btn-primary w-full flex items-center justify-center gap-2 bg-green-600 hover:bg-green-700"
          >
            <Upload className="w-4 h-4" />
            Zum CSV-Import
          </a>
        </div>
      </div>

      {/* Info-Box für HA-User */}
      <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-6">
        <div className="flex items-start gap-4">
          <Info className="w-6 h-6 text-blue-500 flex-shrink-0 mt-0.5" />
          <div>
            <h3 className="font-semibold text-blue-800 dark:text-blue-200 mb-2">
              Hinweis für Home Assistant Benutzer
            </h3>
            <p className="text-blue-700 dark:text-blue-300 text-sm mb-3">
              EEDC ist als Standalone-Anwendung konzipiert und benötigt keine Home Assistant Integration
              für die Datenerfassung. Sie können Ihre Daten aus HA manuell in eine CSV-Datei exportieren
              und in EEDC importieren.
            </p>
            <p className="text-blue-700 dark:text-blue-300 text-sm mb-3">
              <strong>Optional:</strong> Unter Einstellungen → HA-Export können Sie berechnete KPIs
              (Autarkie, Eigenverbrauch, etc.) per MQTT zurück an Home Assistant senden.
            </p>
            <div className="flex flex-wrap gap-2 mt-4">
              <a
                href="#/einstellungen/ha-export"
                className="text-sm text-blue-600 dark:text-blue-400 hover:underline flex items-center gap-1"
              >
                <ExternalLink className="w-3 h-3" />
                HA-Export Einstellungen
              </a>
            </div>
          </div>
        </div>
      </div>

      {/* Tipps */}
      <div className="bg-gray-50 dark:bg-gray-900 rounded-lg p-6">
        <h3 className="font-semibold text-gray-900 dark:text-white mb-4">
          💡 Tipps für die Datenerfassung
        </h3>
        <ul className="space-y-3 text-sm text-gray-600 dark:text-gray-400">
          <li className="flex items-start gap-2">
            <span className="text-lg">📅</span>
            <span>
              <strong>Regelmäßigkeit:</strong> Erfassen Sie Ihre Daten am besten immer am
              gleichen Tag im Monat (z.B. am 1. oder letzten Tag).
            </span>
          </li>
          <li className="flex items-start gap-2">
            <span className="text-lg">📊</span>
            <span>
              <strong>Zählerstände:</strong> Notieren Sie die Zählerstände Ihrer Wechselrichter,
              Speicher und Wallbox. EEDC erwartet Monatswerte (Differenz zum Vormonat).
            </span>
          </li>
          <li className="flex items-start gap-2">
            <span className="text-lg">☀️</span>
            <span>
              <strong>Wetterdaten:</strong> Globalstrahlung und Sonnenstunden werden automatisch
              aus Open-Meteo geladen, wenn Ihre Anlage Koordinaten hat.
            </span>
          </li>
          <li className="flex items-start gap-2">
            <span className="text-lg">🚗</span>
            <span>
              <strong>E-Auto:</strong> Bei externem Laden (öffentliche Säulen) können Sie
              Ladung und Kosten separat erfassen.
            </span>
          </li>
        </ul>
      </div>
    </div>
  )
}
