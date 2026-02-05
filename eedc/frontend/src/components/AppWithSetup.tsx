/**
 * AppWithSetup - Wrapper für App mit Setup-Wizard beim ersten Start
 *
 * Zeigt den Setup-Wizard an wenn:
 * - Keine Anlagen vorhanden sind UND
 * - Wizard noch nicht abgeschlossen wurde
 */

import { useState, useEffect } from 'react'
import { SetupWizard } from './setup-wizard'
import { anlagenApi } from '../api/anlagen'

interface AppWithSetupProps {
  children: React.ReactNode
}

// LocalStorage Key für Wizard-Status
const WIZARD_COMPLETED_KEY = 'eedc_setup_wizard_completed'

export default function AppWithSetup({ children }: AppWithSetupProps) {
  const [isLoading, setIsLoading] = useState(true)
  const [showWizard, setShowWizard] = useState(false)

  useEffect(() => {
    checkIfWizardNeeded()
  }, [])

  const checkIfWizardNeeded = async () => {
    try {
      // WICHTIG: Datenbank hat Priorität über LocalStorage!
      // Bei Neuinstallation (keine Anlagen) soll Wizard IMMER starten,
      // auch wenn LocalStorage noch "completed" enthält.
      const anlagen = await anlagenApi.list()

      if (anlagen.length === 0) {
        // Keine Anlagen in DB -> Wizard anzeigen (LocalStorage ignorieren)
        // LocalStorage zurücksetzen für konsistenten Zustand
        localStorage.removeItem(WIZARD_COMPLETED_KEY)
        localStorage.removeItem('eedc_setup_wizard_state')
        setShowWizard(true)
      } else {
        // Anlagen vorhanden -> Wizard als abgeschlossen markieren
        localStorage.setItem(WIZARD_COMPLETED_KEY, 'true')
        setShowWizard(false)
      }
    } catch (error) {
      // Bei Fehler direkt zur App
      console.error('Fehler beim Prüfen des Setup-Status:', error)
      setShowWizard(false)
    } finally {
      setIsLoading(false)
    }
  }

  const handleWizardComplete = () => {
    localStorage.setItem(WIZARD_COMPLETED_KEY, 'true')
    setShowWizard(false)
  }

  // Loading State
  if (isLoading) {
    return (
      <div className="min-h-screen bg-gray-50 dark:bg-gray-900 flex items-center justify-center">
        <div className="text-center">
          <div className="w-12 h-12 border-4 border-amber-500/30 border-t-amber-500 rounded-full animate-spin mx-auto mb-4" />
          <p className="text-gray-500 dark:text-gray-400">Lade EEDC...</p>
        </div>
      </div>
    )
  }

  // Wizard anzeigen
  if (showWizard) {
    return <SetupWizard onComplete={handleWizardComplete} />
  }

  // Normale App anzeigen
  return <>{children}</>
}

/**
 * Hook um den Wizard manuell zu starten (z.B. aus Settings)
 */
export function useResetWizard() {
  const resetAndShowWizard = () => {
    localStorage.removeItem(WIZARD_COMPLETED_KEY)
    localStorage.removeItem('eedc_setup_wizard_state')
    // Seite neu laden um Wizard anzuzeigen
    window.location.reload()
  }

  return { resetAndShowWizard }
}
