/**
 * SetupWizard - Geführte Ersteinrichtung für EEDC
 *
 * v1.0.0 - Standalone-Version (ohne HA-Abhängigkeit)
 *
 * Schritte:
 * 1. Willkommen
 * 2. Anlage erstellen (+ Geocoding)
 * 3. Strompreise konfigurieren
 * 4. Investitionen erfassen (PV-System, optional Speicher, BKW, WP, E-Auto)
 * 5. Zusammenfassung
 */

import { useEffect } from 'react'
import { Sun, CheckCircle2 } from 'lucide-react'
import { useSetupWizard, type WizardStep } from '../../hooks/useSetupWizard'
import { importApi } from '../../api'

// Schritt-Komponenten
import WelcomeStep from './steps/WelcomeStep'
import AnlageStep from './steps/AnlageStep'
import StrompreiseStep from './steps/StrompreiseStep'
import InvestitionenStep from './steps/InvestitionenStep'
import SummaryStep from './steps/SummaryStep'
import CompleteStep from './steps/CompleteStep'

interface SetupWizardProps {
  onComplete: () => void
}

// Schritt-Konfiguration für Fortschrittsanzeige (v1.0: ohne HA)
const STEPS_CONFIG: { key: WizardStep; label: string; shortLabel: string }[] = [
  { key: 'welcome', label: 'Willkommen', shortLabel: 'Start' },
  { key: 'anlage', label: 'Anlage erstellen', shortLabel: 'Anlage' },
  { key: 'strompreise', label: 'Strompreise', shortLabel: 'Preise' },
  { key: 'investitionen', label: 'Komponenten', shortLabel: 'Komp.' },
  { key: 'summary', label: 'Zusammenfassung', shortLabel: 'Fertig' },
]

export default function SetupWizard({ onComplete }: SetupWizardProps) {
  const wizard = useSetupWizard()

  // Demo-Daten laden Handler
  const handleLoadDemo = async () => {
    await importApi.createDemoData()
    // Nach erfolgreichem Laden direkt zum Dashboard
    onComplete()
  }

  // Bei Abschluss Callback aufrufen
  useEffect(() => {
    if (wizard.step === 'complete') {
      // Kleine Verzögerung für Animation
      const timer = setTimeout(onComplete, 100)
      return () => clearTimeout(timer)
    }
  }, [wizard.step, onComplete])

  // Aktueller Schritt-Index für Fortschrittsanzeige
  const currentStepIndex = STEPS_CONFIG.findIndex(s => s.key === wizard.step)
  const showProgress = wizard.step !== 'welcome' && wizard.step !== 'complete'

  return (
    <div className="min-h-screen bg-gradient-to-br from-amber-50 via-white to-orange-50 dark:from-gray-900 dark:via-gray-800 dark:to-gray-900">
      {/* Header */}
      <header className="bg-white/80 dark:bg-gray-800/80 backdrop-blur-sm border-b border-gray-200 dark:border-gray-700 sticky top-0 z-10">
        <div className="max-w-4xl mx-auto px-4 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 bg-gradient-to-br from-amber-400 to-orange-500 rounded-xl flex items-center justify-center shadow-lg">
                <Sun className="w-6 h-6 text-white" />
              </div>
              <div>
                <h1 className="text-lg font-bold text-gray-900 dark:text-white">
                  eedc Einrichtung
                </h1>
                <p className="text-xs text-gray-500 dark:text-gray-400">
                  Energie Effizienz Data Center
                </p>
              </div>
            </div>

            {/* Fortschritt */}
            {showProgress && (
              <div className="text-sm text-gray-500 dark:text-gray-400">
                Schritt {currentStepIndex + 1} von {STEPS_CONFIG.length}
              </div>
            )}
          </div>
        </div>
      </header>

      {/* Fortschrittsbalken */}
      {showProgress && (
        <div className="bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700">
          <div className="max-w-4xl mx-auto px-4">
            {/* Desktop: Alle Schritte */}
            <div className="hidden md:flex items-center py-4">
              {STEPS_CONFIG.map((stepConfig, index) => {
                const isCompleted = index < currentStepIndex
                const isCurrent = index === currentStepIndex

                return (
                  <div key={stepConfig.key} className="flex items-center flex-1">
                    {/* Schritt-Indikator */}
                    <div className="flex items-center">
                      <div
                        className={`
                          w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium
                          transition-all duration-300
                          ${isCompleted
                            ? 'bg-green-500 text-white'
                            : isCurrent
                              ? 'bg-amber-500 text-white ring-4 ring-amber-500/30'
                              : 'bg-gray-200 dark:bg-gray-700 text-gray-500 dark:text-gray-400'
                          }
                        `}
                      >
                        {isCompleted ? (
                          <CheckCircle2 className="w-5 h-5" />
                        ) : (
                          index + 1
                        )}
                      </div>
                      <span
                        className={`
                          ml-2 text-sm whitespace-nowrap
                          ${isCurrent
                            ? 'font-medium text-gray-900 dark:text-white'
                            : 'text-gray-500 dark:text-gray-400'
                          }
                        `}
                      >
                        {stepConfig.label}
                      </span>
                    </div>

                    {/* Verbindungslinie */}
                    {index < STEPS_CONFIG.length - 1 && (
                      <div
                        className={`
                          flex-1 h-0.5 mx-4
                          ${isCompleted
                            ? 'bg-green-500'
                            : 'bg-gray-200 dark:bg-gray-700'
                          }
                        `}
                      />
                    )}
                  </div>
                )
              })}
            </div>

            {/* Mobile: Kompakte Anzeige */}
            <div className="md:hidden py-3">
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-medium text-gray-900 dark:text-white">
                  {STEPS_CONFIG[currentStepIndex]?.label}
                </span>
                <span className="text-xs text-gray-500 dark:text-gray-400">
                  {currentStepIndex + 1}/{STEPS_CONFIG.length}
                </span>
              </div>
              <div className="h-1.5 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
                <div
                  className="h-full bg-gradient-to-r from-amber-400 to-orange-500 rounded-full transition-all duration-500"
                  style={{ width: `${wizard.progress}%` }}
                />
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Content */}
      <main className="max-w-4xl mx-auto px-4 py-8">
        <div className="bg-white dark:bg-gray-800 rounded-2xl shadow-xl border border-gray-200 dark:border-gray-700 overflow-hidden">
          {/* Schritt-Inhalt */}
          {wizard.step === 'welcome' && (
            <WelcomeStep onNext={wizard.nextStep} onLoadDemo={handleLoadDemo} />
          )}

          {wizard.step === 'anlage' && (
            <AnlageStep
              isLoading={wizard.isLoading}
              error={wizard.error}
              onSubmit={wizard.createAnlage}
              onGeocode={wizard.geocodeAddress}
              onBack={wizard.prevStep}
            />
          )}

          {wizard.step === 'strompreise' && (
            <StrompreiseStep
              anlage={wizard.anlage}
              isLoading={wizard.isLoading}
              error={wizard.error}
              onSubmit={wizard.createStrompreis}
              onUseDefaults={wizard.useDefaultStrompreise}
              onBack={wizard.prevStep}
            />
          )}

          {wizard.step === 'investitionen' && (
            <InvestitionenStep
              investitionen={wizard.investitionen}
              anlage={wizard.anlage}
              isLoading={wizard.isLoading}
              error={wizard.error}
              onUpdateInvestition={wizard.updateInvestition}
              onDeleteInvestition={wizard.deleteInvestition}
              onAddInvestition={wizard.addInvestition}
              onCreateDefaultPVSystem={wizard.createDefaultPVSystem}
              onNext={wizard.nextStep}
              onBack={wizard.prevStep}
            />
          )}

          {wizard.step === 'summary' && (
            <SummaryStep
              anlage={wizard.anlage}
              strompreis={wizard.strompreis}
              investitionen={wizard.investitionen}
              pvgisPrognose={wizard.pvgisPrognose}
              pvgisError={wizard.pvgisError}
              canFetchPvgis={wizard.canFetchPvgis}
              isLoading={wizard.isLoading}
              onFetchPvgis={wizard.fetchPvgisPrognose}
              onComplete={wizard.completeWizard}
              onBack={wizard.prevStep}
            />
          )}

          {wizard.step === 'complete' && (
            <CompleteStep
              anlage={wizard.anlage}
              onGoToDashboard={onComplete}
            />
          )}
        </div>
      </main>

      {/* Footer */}
      <footer className="text-center py-6 text-sm text-gray-400 dark:text-gray-500">
        eedc – Energie Effizienz Data Center
      </footer>
    </div>
  )
}
