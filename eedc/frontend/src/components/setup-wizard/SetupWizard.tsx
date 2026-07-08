/**
 * SetupWizard - Geführte Ersteinrichtung für eedc
 *
 * v2.0.0 - Mit JSON-Import für Backup-Wiederherstellung
 *
 * Schritte:
 * 1. Willkommen
 * 2. Anlage erstellen (+ Geocoding)
 * 3. Strompreise konfigurieren
 * 4. Investitionen erfassen (PV-System, optional Speicher, BKW, WP, E-Auto)
 * 5. Zusammenfassung
 */

import { useEffect } from 'react'
import Stepper from '../ui/Stepper'
import { useSetupWizard, type WizardStep } from '../../hooks/useSetupWizard'
import { importApi } from '../../api'
import eedcIcon from '../../assets/eedc-icon.svg'

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

  // JSON-Import abgeschlossen Handler
  const handleImportComplete = () => {
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
    <div className="h-dvh overflow-y-auto overscroll-contain bg-gradient-to-br from-amber-50 via-white to-orange-50 dark:from-gray-900 dark:via-gray-800 dark:to-gray-900">
      {/* Header */}
      <header className="bg-white/80 dark:bg-gray-800/80 backdrop-blur-sm border-b border-gray-200 dark:border-gray-700">
        <div className="max-w-4xl mx-auto px-3 sm:px-4 py-2 sm:py-4">
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-2 sm:gap-3 min-w-0">
              <img src={eedcIcon} alt="eedc" className="w-8 h-8 sm:w-10 sm:h-10 flex-shrink-0" />
              <div className="min-w-0">
                <h1 className="text-base sm:text-lg font-bold text-gray-900 dark:text-white truncate">
                  eedc Einrichtung
                </h1>
                <p className="hidden sm:block text-xs text-gray-500 dark:text-gray-400">
                  Energie Effizienz Data Center
                </p>
              </div>
            </div>

            {/* Fortschritt */}
            {showProgress && (
              <div className="text-xs sm:text-sm text-gray-500 dark:text-gray-400 whitespace-nowrap flex-shrink-0">
                <span className="hidden sm:inline">Schritt </span>{currentStepIndex + 1}<span className="hidden sm:inline"> von</span><span className="sm:hidden">/</span>{STEPS_CONFIG.length}
              </div>
            )}
          </div>
        </div>
      </header>

      {/* Fortschritt — kanonischer Stepper-SoT (W1), amber-Akzent für das Setup-Chrome */}
      {showProgress && (
        <div className="bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700">
          <div className="max-w-4xl mx-auto px-3 sm:px-4 py-4">
            <Stepper
              schritte={STEPS_CONFIG.map((s) => ({ titel: s.label }))}
              aktuell={currentStepIndex}
              akzent="amber"
            />
          </div>
        </div>
      )}

      {/* Content */}
      <main className="max-w-4xl mx-auto px-3 sm:px-4 py-4 sm:py-8">
        <div className="bg-white dark:bg-gray-800 rounded-xl sm:rounded-2xl shadow-xl border border-gray-200 dark:border-gray-700 overflow-hidden">
          {/* Schritt-Inhalt */}
          {wizard.step === 'welcome' && (
            <WelcomeStep
              onNext={wizard.nextStep}
              onLoadDemo={handleLoadDemo}
              onImportComplete={handleImportComplete}
            />
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
      <footer className="text-center py-3 sm:py-6 text-xs sm:text-sm text-gray-400 dark:text-gray-500">
        eedc – Energie Effizienz Data Center
      </footer>
    </div>
  )
}
