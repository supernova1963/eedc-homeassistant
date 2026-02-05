/**
 * CompleteStep - Abschluss-Bildschirm des Setup-Wizards
 */

import { Sun, ArrowRight, PartyPopper } from 'lucide-react'
import type { Anlage } from '../../../types'

interface CompleteStepProps {
  anlage: Anlage | null
  onGoToDashboard: () => void
}

export default function CompleteStep({ anlage, onGoToDashboard }: CompleteStepProps) {
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

      {/* Quick Start Tips */}
      <div className="bg-gray-50 dark:bg-gray-700/50 rounded-xl p-6 mb-8 max-w-md mx-auto text-left">
        <h3 className="font-semibold text-gray-900 dark:text-white mb-4">
          Erste Schritte:
        </h3>
        <ul className="space-y-3">
          <QuickTip
            number={1}
            text="Monatsdaten erfassen oder aus HA importieren"
          />
          <QuickTip
            number={2}
            text="Dashboard und Kennzahlen erkunden"
          />
          <QuickTip
            number={3}
            text="ROI-Berechnungen für Investitionen prüfen"
          />
        </ul>
      </div>

      {/* CTA */}
      <button
        onClick={onGoToDashboard}
        className="inline-flex items-center gap-3 px-8 py-4 bg-gradient-to-r from-amber-500 to-orange-500 text-white font-semibold text-lg rounded-xl shadow-lg hover:shadow-xl hover:from-amber-600 hover:to-orange-600 transition-all"
      >
        Zum Dashboard
        <ArrowRight className="w-5 h-5" />
      </button>
    </div>
  )
}

function QuickTip({ number, text }: { number: number; text: string }) {
  return (
    <li className="flex items-center gap-3">
      <span className="flex-shrink-0 w-6 h-6 bg-amber-500 text-white text-sm font-medium rounded-full flex items-center justify-center">
        {number}
      </span>
      <span className="text-gray-700 dark:text-gray-300">{text}</span>
    </li>
  )
}
