/**
 * AnlageStep - Anlage erstellen im Setup-Wizard
 * v0.8.0 - Mit Geocoding-Button
 */

import { useState, FormEvent } from 'react'
import { Sun, MapPin, ArrowLeft, ArrowRight, Search, CheckCircle2 } from 'lucide-react'
import { Alert, Input, DatumFeld } from '../../ui'

interface AnlageStepProps {
  isLoading: boolean
  error: string | null
  onSubmit: (data: AnlageCreateData) => Promise<void>
  onGeocode: (plz: string, ort?: string) => Promise<{ latitude: number; longitude: number } | null>
  onBack: () => void
}

interface AnlageCreateData {
  anlagenname: string
  leistung_kwp: number
  installationsdatum?: string
  standort_plz?: string
  standort_ort?: string
  latitude?: number
  longitude?: number
}

export default function AnlageStep({ isLoading, error, onSubmit, onGeocode, onBack }: AnlageStepProps) {
  const [formData, setFormData] = useState({
    anlagenname: '',
    leistung_kwp: '',
    installationsdatum: '',
    standort_plz: '',
    standort_ort: '',
    latitude: '',
    longitude: '',
  })

  const [validationError, setValidationError] = useState<string | null>(null)
  const [isGeocoding, setIsGeocoding] = useState(false)
  const [geocodeSuccess, setGeocodeSuccess] = useState(false)

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    const { name, value } = e.target
    setFormData(prev => ({ ...prev, [name]: value }))
    setValidationError(null)
    // Reset geocode success wenn PLZ/Ort geändert wird
    if (name === 'standort_plz' || name === 'standort_ort') {
      setGeocodeSuccess(false)
    }
  }

  const handleGeocode = async () => {
    if (!formData.standort_plz) {
      setValidationError('Bitte geben Sie eine PLZ ein')
      return
    }

    setIsGeocoding(true)
    setValidationError(null)
    setGeocodeSuccess(false)

    try {
      const result = await onGeocode(formData.standort_plz, formData.standort_ort || undefined)
      if (result) {
        setFormData(prev => ({
          ...prev,
          latitude: result.latitude.toFixed(6), /* de-de-allow: Input-Value (editierbares number-Feld latitude) */
          longitude: result.longitude.toFixed(6), /* de-de-allow: Input-Value (editierbares number-Feld longitude) */
        }))
        setGeocodeSuccess(true)
      } else {
        setValidationError('Koordinaten konnten nicht ermittelt werden. Bitte prüfen Sie PLZ/Ort.')
      }
    } catch {
      setValidationError('Fehler beim Ermitteln der Koordinaten')
    } finally {
      setIsGeocoding(false)
    }
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setValidationError(null)

    // Validierung
    if (!formData.anlagenname.trim()) {
      setValidationError('Bitte geben Sie einen Namen für Ihre Anlage ein')
      return
    }

    if (!formData.leistung_kwp || parseFloat(formData.leistung_kwp) <= 0) {
      setValidationError('Bitte geben Sie die Anlagenleistung in kWp ein')
      return
    }

    await onSubmit({
      anlagenname: formData.anlagenname.trim(),
      leistung_kwp: parseFloat(formData.leistung_kwp),
      installationsdatum: formData.installationsdatum || undefined,
      standort_plz: formData.standort_plz || undefined,
      standort_ort: formData.standort_ort || undefined,
      latitude: formData.latitude ? parseFloat(formData.latitude) : undefined,
      longitude: formData.longitude ? parseFloat(formData.longitude) : undefined,
    })
  }

  const displayError = validationError || error

  return (
    <form onSubmit={handleSubmit}>
      <div className="p-6 md:p-8">
        {/* Header */}
        <div className="flex items-center gap-3 mb-6">
          <div className="w-10 h-10 bg-amber-100 dark:bg-amber-900/30 rounded-xl flex items-center justify-center">
            <Sun className="w-5 h-5 text-amber-600 dark:text-amber-400" />
          </div>
          <div>
            <h2 className="text-xl font-bold text-gray-900 dark:text-white">
              PV-Anlage anlegen
            </h2>
            <p className="text-sm text-gray-500 dark:text-gray-400">
              Grunddaten Ihrer Photovoltaikanlage
            </p>
          </div>
        </div>

        {displayError && (
          <Alert type="error" className="mb-6">{displayError}</Alert>
        )}

        {/* Pflichtfelder */}
        <div className="space-y-6">
          <div className="grid md:grid-cols-2 gap-4 items-start">
            <Input
              label="Anlagenname"
              name="anlagenname"
              value={formData.anlagenname}
              onChange={handleChange}
              placeholder="z.B. Meine PV-Anlage"
              required
            />
            <Input
              label="Leistung (kWp)"
              name="leistung_kwp"
              type="number" step="0.01" min="0.1"
              value={formData.leistung_kwp}
              onChange={handleChange}
              placeholder="z.B. 10.5"
              required
              hint="Gesamtleistung aller Module in Kilowatt-Peak"
            />
          </div>

          {/* Inbetriebnahme (Anlage) — R18-9: Stammdatum der Gesamt-Anlage, Label
              gegen die Fehldeutung „ältestes Gerät" geschärft. */}
          <div className="grid md:grid-cols-2 gap-4 items-start">
            <DatumFeld
              label="Inbetriebnahme (Anlage)"
              value={formData.installationsdatum}
              onChange={(v) => { setFormData(prev => ({ ...prev, installationsdatum: v })); setValidationError(null) }}
              hint="Stammdatum der Gesamt-Anlage (nicht das älteste Gerät) — für Stromtarif-Gültigkeit und Community-Vergleichszeitraum"
            />
          </div>

          {/* Standort */}
          <div className="border-t border-gray-200 dark:border-gray-700 pt-6">
            <h3 className="flex items-center gap-2 text-sm font-semibold text-gray-900 dark:text-white mb-4">
              <MapPin className="w-4 h-4 text-gray-500" />
              Standort (für PVGIS-Prognose)
            </h3>

            <div className="grid md:grid-cols-3 gap-4 mb-4 items-start">
              <Input
                label="PLZ"
                name="standort_plz"
                value={formData.standort_plz}
                onChange={handleChange}
                placeholder="z.B. 12345"
                maxLength={5}
              />
              <div className="md:col-span-2">
                <Input
                  label="Ort"
                  name="standort_ort"
                  value={formData.standort_ort}
                  onChange={handleChange}
                  placeholder="z.B. Berlin"
                />
              </div>
            </div>

            {/* Geocoding Button */}
            <div className="mb-4">
              <button
                type="button"
                onClick={handleGeocode}
                disabled={isGeocoding || !formData.standort_plz}
                className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-amber-700 dark:text-amber-300 bg-amber-100 dark:bg-amber-900/30 rounded-lg hover:bg-amber-200 dark:hover:bg-amber-900/50 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {isGeocoding ? (
                  <>
                    <span className="w-4 h-4 border-2 border-amber-500/30 border-t-amber-500 rounded-full animate-spin" />
                    Ermittle Koordinaten...
                  </>
                ) : geocodeSuccess ? (
                  <>
                    <CheckCircle2 className="w-4 h-4 text-green-500" />
                    Koordinaten ermittelt
                  </>
                ) : (
                  <>
                    <Search className="w-4 h-4" />
                    Koordinaten aus PLZ ermitteln
                  </>
                )}
              </button>
            </div>

            <div className="grid md:grid-cols-2 gap-4 items-start">
              <Input
                label="Breitengrad (Latitude)"
                name="latitude"
                type="number" step="0.000001"
                value={formData.latitude}
                onChange={handleChange}
                placeholder="z.B. 52.520008"
              />
              <Input
                label="Längengrad (Longitude)"
                name="longitude"
                type="number" step="0.000001"
                value={formData.longitude}
                onChange={handleChange}
                placeholder="z.B. 13.404954"
              />
            </div>

            <Alert type="info" className="mt-4">
              Die Koordinaten werden für die PVGIS-Ertragsprognose benötigt.
              Klicken Sie auf „Koordinaten aus PLZ ermitteln" oder geben Sie sie manuell ein.
            </Alert>
          </div>

          {/* Hinweis steuerliche Behandlung */}
          <Alert type="warning">
            Steuerliche Einstellungen (Regelbesteuerung/Kleinunternehmer) können
            unter <strong>Einstellungen &rarr; Anlage bearbeiten</strong> konfiguriert werden.
          </Alert>

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
