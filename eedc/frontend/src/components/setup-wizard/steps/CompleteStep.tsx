/**
 * CompleteStep - Abschluss-Bildschirm des Setup-Wizards
 *
 * v1.0.0 - Leitet zur Monatsdaten-Erfassung weiter
 */

import { Sun, PartyPopper, FileSpreadsheet, LayoutDashboard, Plug } from 'lucide-react'
import { Button } from '../../ui'
import { v3RouteZuV4 } from '../../../config/v3ZuV4Route'
import type { Anlage } from '../../../types'

interface CompleteStepProps {
  anlage: Anlage | null
  onGoToDashboard: () => void
}

export default function CompleteStep({ anlage, onGoToDashboard }: CompleteStepProps) {
  // Navigation zur Monatsdaten-Seite. Das Gate rendert VOR dem Router (kein
  // navigate) — die Alt-Route-Strings werden über die Re-Kategorisierungs-Map
  // (v3RouteZuV4-SoT) auf die V4-Kategorie umgebogen (z. B. „Daten").
  const springeZu = (v3Ziel: string) => {
    // Wizard als abgeschlossen markieren (wird von onGoToDashboard gemacht)
    onGoToDashboard()
    const ziel = v3RouteZuV4(v3Ziel) ?? v3Ziel
    // Nach kurzem Delay zur Zielseite navigieren
    setTimeout(() => {
      window.location.hash = '#' + ziel
    }, 100)
  }
  const handleGoToMonatsdaten = () => springeZu('/einstellungen/monatsdaten')
  // D2: direkter Absprung in die Sensor-/Topic-Pflege (Datenquellen-Fläche).
  // V3-Bereinigung 2026-08: direkt statt über den sensor-mapping-Redirect.
  const handleGoToDatenquellen = () => springeZu('/einstellungen/datenquellen')

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
          'eedc ist bereit zur Nutzung.'
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
        <Button variant="amber" size="lg" onClick={handleGoToMonatsdaten}>
          <FileSpreadsheet className="w-5 h-5 mr-2 max-sm:hidden" />
          Monatsdaten erfassen
        </Button>

        {/* D2-Absprung in die Datenquellen-Fläche (Sensor-/Topic-Pflege). */}
        <Button variant="secondary" size="lg" onClick={handleGoToDatenquellen}>
          <Plug className="w-5 h-5 mr-2 max-sm:hidden" />
          Sensor- & Topic-Pflege
        </Button>

        <Button variant="secondary" size="lg" onClick={onGoToDashboard}>
          <LayoutDashboard className="w-5 h-5 mr-2 max-sm:hidden" />
          Zum Cockpit
        </Button>
      </div>
    </div>
  )
}
