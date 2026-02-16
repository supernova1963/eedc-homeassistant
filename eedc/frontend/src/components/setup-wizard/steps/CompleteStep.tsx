/**
 * CompleteStep - Abschluss-Bildschirm des Setup-Wizards
 *
 * v1.0.0 - Leitet zur Monatsdaten-Erfassung weiter
 */

import { Sun, PartyPopper, FileSpreadsheet, LayoutDashboard } from 'lucide-react'
import type { Anlage } from '../../../types'

interface CompleteStepProps {
  anlage: Anlage | null
  onGoToDashboard: () => void
}

export default function CompleteStep({ anlage, onGoToDashboard }: CompleteStepProps) {
  // Navigation zur Monatsdaten-Seite
  const handleGoToMonatsdaten = () => {
    // Wizard als abgeschlossen markieren (wird von onGoToDashboard gemacht)
    onGoToDashboard()
    // Nach kurzem Delay zur Monatsdaten-Seite navigieren
    setTimeout(() => {
      window.location.href = '/einstellungen/monatsdaten'
    }, 100)
  }

  return (
    <div className="p-8 md:p-12 text-center">
      {/* Celebration Animation */}
      <div className="relative inline-block mb-8">
        <div className="w-24 h-24 bg-gradient-to-br from-amber-400 to-orange-500 rounded-2xl shadow-xl flex items-center justify-center animate-bounce">
          <Sun className="w-12 h-12 text-white" />
        </div>
        <div className="absolute -top-2 -right-2">
          <PartyPopper className="w-8 h-8 text-amber-500" />
        </div>
      </div>

      {/* Title */}
      <h1 className="text-3xl md:text-4xl font-bold text-gray-900 dark:text-white mb-4">
        Einrichtung abgeschlossen!
      </h1>

      <p className="text-lg text-gray-600 dark:text-gray-300 mb-8 max-w-lg mx-auto">
        {anlage ? (
          <>
            Ihre Anlage <span className="font-semibold text-amber-600 dark:text-amber-400">"{anlage.anlagenname}"</span> ist
            bereit zur Nutzung.
          </>
        ) : (
          'EEDC ist bereit zur Nutzung.'
        )}
      </p>

      {/* Info Box */}
      <div className="bg-blue-50 dark:bg-blue-900/20 rounded-xl p-6 mb-8 max-w-md mx-auto text-left border border-blue-200 dark:border-blue-800">
        <div className="flex items-start gap-3">
          <FileSpreadsheet className="w-5 h-5 text-blue-600 dark:text-blue-400 flex-shrink-0 mt-0.5" />
          <div>
            <h3 className="font-semibold text-gray-900 dark:text-white mb-2">
              Nächster Schritt: Monatsdaten erfassen
            </h3>
            <p className="text-sm text-gray-600 dark:text-gray-400">
              Erfassen Sie Ihre monatlichen Zählerstände (Einspeisung, Netzbezug) und
              Verbrauchsdaten. Die Daten können manuell eingegeben oder per CSV importiert werden.
            </p>
          </div>
        </div>
      </div>

      {/* CTAs */}
      <div className="flex flex-col sm:flex-row gap-4 justify-center">
        <button
          onClick={handleGoToMonatsdaten}
          className="inline-flex items-center justify-center gap-3 px-8 py-4 bg-gradient-to-r from-amber-500 to-orange-500 text-white font-semibold text-lg rounded-xl shadow-lg hover:shadow-xl hover:from-amber-600 hover:to-orange-600 transition-all"
        >
          <FileSpreadsheet className="w-5 h-5" />
          Monatsdaten erfassen
        </button>

        <button
          onClick={onGoToDashboard}
          className="inline-flex items-center justify-center gap-3 px-6 py-4 bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 font-medium rounded-xl hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors"
        >
          <LayoutDashboard className="w-5 h-5" />
          Zum Cockpit
        </button>
      </div>
    </div>
  )
}
