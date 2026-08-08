/**
 * StrompreiseStep - Stromtarif konfigurieren im Setup-Wizard
 */

import { useState, FormEvent } from 'react'
import { Zap, ArrowLeft, ArrowRight, Sparkles } from 'lucide-react'
import { Alert, Button, Input, DatumFeld } from '../../ui'
import { DEFAULT_STROMPREISE } from '../../../hooks/useSetupWizard'
import { EINSPEISEVERGUETUNG_FLAT_HINWEIS } from '../../../lib'
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
  // Ein Startwert, KEINE Ableitung aus der Anlagengröße: die EEG-Sätze und
  // ihre Stufen ändern sich laufend, und welcher für diese Anlage gilt, weiß
  // nur der Betreiber (Entscheid 08.08.2026, T89667 #122).
  const defaultEinspeisung = DEFAULT_STROMPREISE.einspeiseverguetung_cent_kwh

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

        {/* Standard-Werte Auswahl-Karte — Struktur-Element (mehrzeilig), kein
            Aktions-Button: rohes <button> ist hier die Impl (ROH_INFRA-Freigabe
            Gernot 2026-07-17, Paket F). */}
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
          <div className="grid md:grid-cols-2 gap-4 items-start">
            <Input
              label="Netzbezugspreis (ct/kWh)"
              name="netzbezug_arbeitspreis_cent_kwh"
              type="number" step="0.01" min="0"
              value={formData.netzbezug_arbeitspreis_cent_kwh}
              onChange={handleChange}
              required
              hint="Aktueller Durchschnitt: ~30 ct/kWh"
            />
            <Input
              label="Einspeisevergütung (ct/kWh)"
              name="einspeiseverguetung_cent_kwh"
              type="number" step="0.01" min="0"
              value={formData.einspeiseverguetung_cent_kwh}
              onChange={handleChange}
              required
              hint={parseFloat(formData.einspeiseverguetung_cent_kwh) === 0
                ? `Deinen Satz findest du im Vergütungsbescheid — mit 0 ct wird kein Einspeise-Erlös berechnet. ${EINSPEISEVERGUETUNG_FLAT_HINWEIS}`
                : EINSPEISEVERGUETUNG_FLAT_HINWEIS}
            />
          </div>

          {/* Zusätzliche Felder */}
          <div className="grid md:grid-cols-2 gap-4 items-start">
            <Input
              label="Grundpreis (€/Monat)"
              name="grundpreis_euro_monat"
              type="number" step="0.01" min="0"
              value={formData.grundpreis_euro_monat}
              onChange={handleChange}
            />
            <DatumFeld
              label="Gültig ab"
              required
              value={formData.gueltig_ab}
              onChange={(v) => { setFormData(prev => ({ ...prev, gueltig_ab: v })); setValidationError(null) }}
            />
          </div>

          {/* Optionale Felder */}
          <div className="grid md:grid-cols-2 gap-4 items-start">
            <Input
              label="Tarifname"
              name="tarifname"
              value={formData.tarifname}
              onChange={handleChange}
              placeholder="z.B. Ökostrom Flex"
            />
            <Input
              label="Anbieter"
              name="anbieter"
              value={formData.anbieter}
              onChange={handleChange}
              placeholder="z.B. Stadtwerke"
            />
          </div>

          {/* Info-Box */}
          <Alert type="info">
            Sie können später weitere Stromtarife mit unterschiedlichen Gültigkeitszeiträumen
            hinzufügen, z.B. bei Tarifwechsel oder Preisänderungen.
            Spezialtarife für Wärmepumpe oder Wallbox können ebenfalls unter Strompreise angelegt werden.
          </Alert>
        </div>
      </div>

      {/* Footer */}
      <div className="px-6 md:px-8 py-4 bg-gray-50 dark:bg-gray-700/50 border-t border-gray-200 dark:border-gray-700 flex justify-between">
        <Button type="button" variant="ghost" onClick={onBack}>
          <ArrowLeft className="w-4 h-4 mr-2" />
          Zurück
        </Button>

        <Button type="submit" variant="amber" loading={isLoading}>
          {isLoading ? (
            'Speichern...'
          ) : (
            <>
              Weiter
              <ArrowRight className="w-4 h-4 ml-2" />
            </>
          )}
        </Button>
      </div>
    </form>
  )
}
