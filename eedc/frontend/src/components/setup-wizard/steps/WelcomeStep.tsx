/**
 * WelcomeStep - Willkommens-Bildschirm des Setup-Wizards
 */

import { useState } from 'react'
import { Sun, Zap, PiggyBank, BarChart3, ArrowRight, Play, Loader2 } from 'lucide-react'

interface WelcomeStepProps {
  onNext: () => void
  onLoadDemo?: () => Promise<void>
}

export default function WelcomeStep({ onNext, onLoadDemo }: WelcomeStepProps) {
  const [demoLoading, setDemoLoading] = useState(false)
  const [demoError, setDemoError] = useState<string | null>(null)

  const handleLoadDemo = async () => {
    if (!onLoadDemo) return
    setDemoLoading(true)
    setDemoError(null)
    try {
      await onLoadDemo()
    } catch (e) {
      setDemoError(e instanceof Error ? e.message : 'Fehler beim Laden der Demo-Daten')
      setDemoLoading(false)
    }
  }

  return (
    <div className="p-8 md:p-12">
      {/* Hero */}
      <div className="text-center mb-12">
        <div className="inline-flex items-center justify-center w-20 h-20 bg-gradient-to-br from-amber-400 to-orange-500 rounded-2xl shadow-xl mb-6">
          <Sun className="w-10 h-10 text-white" />
        </div>
        <h1 className="text-3xl md:text-4xl font-bold text-gray-900 dark:text-white mb-4">
          Willkommen bei eedc
        </h1>
        <p className="text-lg text-gray-600 dark:text-gray-300 max-w-2xl mx-auto">
          Ihr persönliches Energie Effizienz Data Center für die Analyse
          und Optimierung Ihrer PV-Anlage.
        </p>
      </div>

      {/* Features */}
      <div className="grid md:grid-cols-3 gap-6 mb-12">
        <FeatureCard
          icon={<BarChart3 className="w-6 h-6" />}
          title="Auswertungen"
          description="Detaillierte Analysen zu Erzeugung, Verbrauch und Autarkie"
        />
        <FeatureCard
          icon={<PiggyBank className="w-6 h-6" />}
          title="Wirtschaftlichkeit"
          description="ROI-Berechnungen für alle Ihre Energie-Investitionen"
        />
        <FeatureCard
          icon={<Zap className="w-6 h-6" />}
          title="Home Assistant"
          description="Automatischer Datenimport direkt aus Ihrem Smart Home"
        />
      </div>

      {/* Was wird eingerichtet */}
      <div className="bg-gray-50 dark:bg-gray-700/50 rounded-xl p-6 mb-8">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
          In wenigen Schritten eingerichtet:
        </h2>
        <ul className="space-y-3">
          <SetupItem number={1} text="PV-Anlage mit Leistung und Standort anlegen" />
          <SetupItem number={2} text="Home Assistant Verbindung prüfen" />
          <SetupItem number={3} text="Stromtarif konfigurieren (mit Vorschlägen)" />
          <SetupItem number={4} text="Geräte automatisch aus HA erkennen" />
          <SetupItem number={5} text="Investitionen vervollständigen" />
        </ul>
      </div>

      {/* CTA */}
      <div className="text-center space-y-4">
        <button
          onClick={onNext}
          className="inline-flex items-center gap-2 px-8 py-4 bg-gradient-to-r from-amber-500 to-orange-500 text-white font-semibold rounded-xl shadow-lg hover:shadow-xl hover:from-amber-600 hover:to-orange-600 transition-all"
        >
          Einrichtung starten
          <ArrowRight className="w-5 h-5" />
        </button>
        <p className="text-sm text-gray-500 dark:text-gray-400">
          Die Einrichtung dauert etwa 2-3 Minuten
        </p>

        {/* Demo-Daten Option */}
        {onLoadDemo && (
          <div className="pt-6 border-t border-gray-200 dark:border-gray-700 mt-6">
            <p className="text-sm text-gray-600 dark:text-gray-400 mb-3">
              Oder erkunden Sie die App mit vorbereiteten Demo-Daten:
            </p>
            <button
              onClick={handleLoadDemo}
              disabled={demoLoading}
              className="inline-flex items-center gap-2 px-6 py-3 bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 font-medium rounded-xl hover:bg-gray-200 dark:hover:bg-gray-600 transition-all disabled:opacity-50"
            >
              {demoLoading ? (
                <>
                  <Loader2 className="w-5 h-5 animate-spin" />
                  Demo wird geladen...
                </>
              ) : (
                <>
                  <Play className="w-5 h-5" />
                  Demo-Anlage laden
                </>
              )}
            </button>
            {demoError && (
              <p className="mt-2 text-sm text-red-500">{demoError}</p>
            )}
            <p className="mt-2 text-xs text-gray-400 dark:text-gray-500">
              Enthält 31 Monate Beispieldaten, 9 Investitionen inkl. E-Auto, Speicher, Wärmepumpe u.v.m.
            </p>
          </div>
        )}
      </div>
    </div>
  )
}

function FeatureCard({
  icon,
  title,
  description,
}: {
  icon: React.ReactNode
  title: string
  description: string
}) {
  return (
    <div className="bg-gray-50 dark:bg-gray-700/50 rounded-xl p-6 text-center">
      <div className="inline-flex items-center justify-center w-12 h-12 bg-amber-100 dark:bg-amber-900/30 text-amber-600 dark:text-amber-400 rounded-xl mb-4">
        {icon}
      </div>
      <h3 className="font-semibold text-gray-900 dark:text-white mb-2">
        {title}
      </h3>
      <p className="text-sm text-gray-600 dark:text-gray-400">
        {description}
      </p>
    </div>
  )
}

function SetupItem({ number, text }: { number: number; text: string }) {
  return (
    <li className="flex items-center gap-3">
      <span className="flex-shrink-0 w-6 h-6 bg-amber-500 text-white text-sm font-medium rounded-full flex items-center justify-center">
        {number}
      </span>
      <span className="text-gray-700 dark:text-gray-300">{text}</span>
    </li>
  )
}
