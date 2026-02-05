/**
 * HAConnectionStep - Home Assistant Verbindung prüfen
 */

import { Wifi, WifiOff, RefreshCw, ArrowLeft, ArrowRight, SkipForward, CheckCircle2, Info } from 'lucide-react'

interface HAConnectionStepProps {
  isLoading: boolean
  error: string | null
  haConnected: boolean
  haVersion: string | null
  onRetry: () => void
  onNext: () => void
  onSkip: () => void
  onBack: () => void
}

export default function HAConnectionStep({
  isLoading,
  error,
  haConnected,
  haVersion,
  onRetry,
  onNext,
  onSkip,
  onBack,
}: HAConnectionStepProps) {
  return (
    <div>
      <div className="p-6 md:p-8">
        {/* Header */}
        <div className="flex items-center gap-3 mb-6">
          <div className={`w-10 h-10 rounded-xl flex items-center justify-center ${
            haConnected
              ? 'bg-green-100 dark:bg-green-900/30'
              : 'bg-gray-100 dark:bg-gray-700'
          }`}>
            {haConnected ? (
              <Wifi className="w-5 h-5 text-green-600 dark:text-green-400" />
            ) : (
              <WifiOff className="w-5 h-5 text-gray-400" />
            )}
          </div>
          <div>
            <h2 className="text-xl font-bold text-gray-900 dark:text-white">
              Home Assistant Verbindung
            </h2>
            <p className="text-sm text-gray-500 dark:text-gray-400">
              Automatischer Datenimport aus Ihrem Smart Home
            </p>
          </div>
        </div>

        {/* Status */}
        <div className="space-y-6">
          {isLoading ? (
            <div className="text-center py-12">
              <div className="inline-flex items-center justify-center w-16 h-16 mb-4">
                <RefreshCw className="w-8 h-8 text-amber-500 animate-spin" />
              </div>
              <p className="text-gray-600 dark:text-gray-400">
                Verbindung wird geprüft...
              </p>
            </div>
          ) : haConnected ? (
            <div className="text-center py-8">
              <div className="inline-flex items-center justify-center w-20 h-20 bg-green-100 dark:bg-green-900/30 rounded-full mb-4">
                <CheckCircle2 className="w-10 h-10 text-green-500" />
              </div>
              <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-2">
                Verbindung erfolgreich!
              </h3>
              {haVersion && (
                <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">
                  Home Assistant Version: {haVersion}
                </p>
              )}

              <div className="max-w-md mx-auto bg-green-50 dark:bg-green-900/20 rounded-lg p-4 text-left">
                <h4 className="font-medium text-green-800 dark:text-green-300 mb-2">
                  Folgende Funktionen sind verfügbar:
                </h4>
                <ul className="space-y-2 text-sm text-green-700 dark:text-green-400">
                  <li className="flex items-center gap-2">
                    <CheckCircle2 className="w-4 h-4" />
                    Automatische Geräte-Erkennung
                  </li>
                  <li className="flex items-center gap-2">
                    <CheckCircle2 className="w-4 h-4" />
                    Sensor-Zuordnung für Energy-Daten
                  </li>
                  <li className="flex items-center gap-2">
                    <CheckCircle2 className="w-4 h-4" />
                    Monatsdaten-Import aus HA History
                  </li>
                </ul>
              </div>
            </div>
          ) : (
            <div className="text-center py-8">
              <div className="inline-flex items-center justify-center w-20 h-20 bg-amber-100 dark:bg-amber-900/30 rounded-full mb-4">
                <WifiOff className="w-10 h-10 text-amber-500" />
              </div>
              <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-2">
                Keine Verbindung zu Home Assistant
              </h3>

              {error && (
                <p className="text-sm text-red-600 dark:text-red-400 mb-4">
                  {error}
                </p>
              )}

              <div className="max-w-md mx-auto">
                <div className="bg-amber-50 dark:bg-amber-900/20 rounded-lg p-4 text-left mb-6">
                  <h4 className="font-medium text-amber-800 dark:text-amber-300 mb-2 flex items-center gap-2">
                    <Info className="w-4 h-4" />
                    Mögliche Ursachen:
                  </h4>
                  <ul className="space-y-1 text-sm text-amber-700 dark:text-amber-400">
                    <li>• EEDC läuft nicht als Home Assistant Add-on</li>
                    <li>• Home Assistant API nicht erreichbar</li>
                    <li>• Supervisor Token fehlt</li>
                  </ul>
                </div>

                <button
                  onClick={onRetry}
                  className="inline-flex items-center gap-2 px-4 py-2 bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300 rounded-lg hover:bg-amber-200 dark:hover:bg-amber-900/50 transition-colors"
                >
                  <RefreshCw className="w-4 h-4" />
                  Erneut prüfen
                </button>
              </div>
            </div>
          )}

          {/* Info-Box */}
          {!isLoading && !haConnected && (
            <div className="bg-blue-50 dark:bg-blue-900/20 rounded-lg p-4">
              <p className="text-sm text-blue-700 dark:text-blue-300">
                <strong>Hinweis:</strong> Sie können EEDC auch ohne Home Assistant nutzen.
                Monatsdaten können manuell oder per CSV-Import erfasst werden.
                Die HA-Integration kann jederzeit später aktiviert werden.
              </p>
            </div>
          )}
        </div>
      </div>

      {/* Footer */}
      <div className="px-6 md:px-8 py-4 bg-gray-50 dark:bg-gray-700/50 border-t border-gray-200 dark:border-gray-700 flex justify-between">
        <button
          type="button"
          onClick={onBack}
          className="inline-flex items-center gap-2 px-4 py-2 text-gray-700 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          Zurück
        </button>

        <div className="flex gap-3">
          {!haConnected && (
            <button
              type="button"
              onClick={onSkip}
              className="inline-flex items-center gap-2 px-4 py-2 text-gray-600 dark:text-gray-400 hover:text-gray-800 dark:hover:text-gray-200 transition-colors"
            >
              <SkipForward className="w-4 h-4" />
              Überspringen
            </button>
          )}

          <button
            type="button"
            onClick={onNext}
            disabled={isLoading}
            className="inline-flex items-center gap-2 px-6 py-2.5 bg-amber-500 text-white font-medium rounded-lg hover:bg-amber-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Weiter
            <ArrowRight className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  )
}
