/**
 * StrompreiseStep - Stromtarif konfigurieren im Setup-Wizard
 */

import { useState, FormEvent } from 'react'
import { Zap, ArrowLeft, ArrowRight, Info, Sparkles } from 'lucide-react'
import { Alert } from '../../ui'
import { DEFAULT_STROMPREISE, getEinspeiseverguetung } from '../../../hooks/useSetupWizard'
import type { Anlage } from '../../../types'

interface StrompreiseStepProps {
  anlage: Anlage | null
  isLoading: boolean
  error: string | null
  onSubmit: (data: StrompreisCreateData) => Promise<void>
  onUseDefaults: () => Promise<void>
  onBack: () => void
}

interface StrompreisCreateData {
  netzbezug_arbeitspreis_cent_kwh: number
  einspeiseverguetung_cent_kwh: number
  grundpreis_euro_monat?: number
  gueltig_ab: string
  tarifname?: string
  anbieter?: string
}

export default function StrompreiseStep({
  anlage,
  isLoading,
  error,
  onSubmit,
  onUseDefaults,
  onBack,
}: StrompreiseStepProps) {
  // Einspeisevergütung basierend auf Anlagengröße
  const defaultEinspeisung = anlage
    ? getEinspeiseverguetung(anlage.leistung_kwp)
    : DEFAULT_STROMPREISE.einspeiseverguetung_cent_kwh

  const [formData, setFormData] = useState({
    netzbezug_arbeitspreis_cent_kwh: DEFAULT_STROMPREISE.netzbezug_arbeitspreis_cent_kwh.toString(),
    einspeiseverguetung_cent_kwh: defaultEinspeisung.toString(),
    grundpreis_euro_monat: DEFAULT_STROMPREISE.grundpreis_euro_monat.toString(),
    gueltig_ab: anlage?.installationsdatum || new Date().toISOString().split('T')[0],
    tarifname: '',
    anbieter: '',
  })

  const [validationError, setValidationError] = useState<string | null>(null)

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = e.target
    setFormData(prev => ({ ...prev, [name]: value }))
    setValidationError(null)
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setValidationError(null)

    if (!formData.netzbezug_arbeitspreis_cent_kwh || parseFloat(formData.netzbezug_arbeitspreis_cent_kwh) < 0) {
      setValidationError('Bitte geben Sie einen gültigen Netzbezugspreis ein')
      return
    }

    if (!formData.gueltig_ab) {
      setValidationError('Bitte geben Sie ein Gültigkeitsdatum ein')
      return
    }

    await onSubmit({
      netzbezug_arbeitspreis_cent_kwh: parseFloat(formData.netzbezug_arbeitspreis_cent_kwh),
      einspeiseverguetung_cent_kwh: parseFloat(formData.einspeiseverguetung_cent_kwh) || 0,
      grundpreis_euro_monat: formData.grundpreis_euro_monat
        ? parseFloat(formData.grundpreis_euro_monat)
        : undefined,
      gueltig_ab: formData.gueltig_ab,
      tarifname: formData.tarifname || undefined,
      anbieter: formData.anbieter || undefined,
    })
  }

  const displayError = validationError || error

  return (
    <form onSubmit={handleSubmit}>
      <div className="p-6 md:p-8">
        {/* Header */}
        <div className="flex items-center gap-3 mb-6">
          <div className="w-10 h-10 bg-amber-100 dark:bg-amber-900/30 rounded-xl flex items-center justify-center">
            <Zap className="w-5 h-5 text-amber-600 dark:text-amber-400" />
          </div>
          <div>
            <h2 className="text-xl font-bold text-gray-900 dark:text-white">
              Stromtarif konfigurieren
            </h2>
            <p className="text-sm text-gray-500 dark:text-gray-400">
              Für korrekte Wirtschaftlichkeitsberechnungen
            </p>
          </div>
        </div>

        {displayError && (
          <Alert type="error" className="mb-6">{displayError}</Alert>
        )}

        {/* Standard-Werte Button */}
        <div className="mb-6">
          <button
            type="button"
            onClick={onUseDefaults}
            disabled={isLoading}
            className="w-full p-4 bg-gradient-to-r from-amber-50 to-orange-50 dark:from-amber-900/20 dark:to-orange-900/20 border-2 border-dashed border-amber-300 dark:border-amber-700 rounded-xl hover:border-amber-400 dark:hover:border-amber-600 transition-colors group"
          >
            <div className="flex items-center justify-center gap-3">
              <Sparkles className="w-5 h-5 text-amber-500 group-hover:text-amber-600" />
              <span className="font-medium text-amber-700 dark:text-amber-300">
                Deutsche Standardwerte verwenden
              </span>
            </div>
            <p className="text-sm text-amber-600 dark:text-amber-400 mt-1">
              {DEFAULT_STROMPREISE.netzbezug_arbeitspreis_cent_kwh} ct Netzbezug |{' '}
              {defaultEinspeisung} ct Einspeisung |{' '}
              {DEFAULT_STROMPREISE.grundpreis_euro_monat} € Grundpreis
            </p>
          </button>
        </div>

        <div className="relative mb-6">
          <div className="absolute inset-0 flex items-center">
            <div className="w-full border-t border-gray-200 dark:border-gray-700" />
          </div>
          <div className="relative flex justify-center text-sm">
            <span className="px-3 bg-white dark:bg-gray-800 text-gray-500 dark:text-gray-400">
              oder anpassen
            </span>
          </div>
        </div>

        {/* Formular */}
        <div className="space-y-6">
          {/* Hauptpreise */}
          <div className="grid md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Netzbezugspreis (ct/kWh) <span className="text-red-500">*</span>
              </label>
              <input
                type="number"
                name="netzbezug_arbeitspreis_cent_kwh"
                value={formData.netzbezug_arbeitspreis_cent_kwh}
                onChange={handleChange}
                step="0.01"
                min="0"
                className="w-full px-4 py-2.5 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-amber-500 focus:border-transparent"
                required
              />
              <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                Aktueller Durchschnitt: ~30 ct/kWh
              </p>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Einspeisevergütung (ct/kWh) <span className="text-red-500">*</span>
              </label>
              <input
                type="number"
                name="einspeiseverguetung_cent_kwh"
                value={formData.einspeiseverguetung_cent_kwh}
                onChange={handleChange}
                step="0.01"
                min="0"
                className="w-full px-4 py-2.5 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-amber-500 focus:border-transparent"
                required
              />
              <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                {anlage && anlage.leistung_kwp <= 10
                  ? '≤10 kWp: 8,2 ct'
                  : anlage && anlage.leistung_kwp <= 40
                    ? '10-40 kWp: 7,1 ct'
                    : '>40 kWp: 5,8 ct'
                }
              </p>
            </div>
          </div>

          {/* Zusätzliche Felder */}
          <div className="grid md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Grundpreis (€/Monat)
              </label>
              <input
                type="number"
                name="grundpreis_euro_monat"
                value={formData.grundpreis_euro_monat}
                onChange={handleChange}
                step="0.01"
                min="0"
                className="w-full px-4 py-2.5 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-amber-500 focus:border-transparent"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Gültig ab <span className="text-red-500">*</span>
              </label>
              <input
                type="date"
                name="gueltig_ab"
                value={formData.gueltig_ab}
                onChange={handleChange}
                className="w-full px-4 py-2.5 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-amber-500 focus:border-transparent"
                required
              />
            </div>
          </div>

          {/* Optionale Felder */}
          <div className="grid md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Tarifname
              </label>
              <input
                type="text"
                name="tarifname"
                value={formData.tarifname}
                onChange={handleChange}
                placeholder="z.B. Ökostrom Flex"
                className="w-full px-4 py-2.5 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-amber-500 focus:border-transparent"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Anbieter
              </label>
              <input
                type="text"
                name="anbieter"
                value={formData.anbieter}
                onChange={handleChange}
                placeholder="z.B. Stadtwerke"
                className="w-full px-4 py-2.5 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-amber-500 focus:border-transparent"
              />
            </div>
          </div>

          {/* Info-Box */}
          <div className="bg-blue-50 dark:bg-blue-900/20 rounded-lg p-4">
            <p className="text-sm text-blue-700 dark:text-blue-300 flex items-start gap-2">
              <Info className="w-4 h-4 flex-shrink-0 mt-0.5" />
              <span>
                Sie können später weitere Stromtarife mit unterschiedlichen Gültigkeitszeiträumen
                hinzufügen, z.B. bei Tarifwechsel oder Preisänderungen.
              </span>
            </p>
          </div>
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

        <button
          type="submit"
          disabled={isLoading}
          className="inline-flex items-center gap-2 px-6 py-2.5 bg-amber-500 text-white font-medium rounded-lg hover:bg-amber-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {isLoading ? (
            <>
              <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              Speichern...
            </>
          ) : (
            <>
              Weiter
              <ArrowRight className="w-4 h-4" />
            </>
          )}
        </button>
      </div>
    </form>
  )
}
