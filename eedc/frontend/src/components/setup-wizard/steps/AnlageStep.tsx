/**
 * AnlageStep - Anlage erstellen im Setup-Wizard
 * v0.8.0 - Mit Geocoding-Button
 */

import { useState, FormEvent } from 'react'
import { Sun, MapPin, ArrowLeft, ArrowRight, Search, CheckCircle2 } from 'lucide-react'
import { Alert, Button, Input, DatumFeld } from '../../ui'
import { IA_V4 } from '../../../lib/flags'

interface AnlageStepProps {
  isLoading: boolean
  error: string | null
  onSubmit: (data: AnlageCreateData) => Promise<void>
  onGeocode: (plz: string, ort?: string, strasse?: string) => Promise<{ latitude: number; longitude: number } | null>
  onBack: () => void
}

interface AnlageCreateData {
  anlagenname: string
  leistung_kwp: number
  installationsdatum?: string
  standort_plz?: string
  standort_ort?: string
  standort_strasse?: string
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
    standort_strasse: '',
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
    if (name === 'standort_plz' || name === 'standort_ort' || name === 'standort_strasse') {
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
      const result = await onGeocode(formData.standort_plz, formData.standort_ort || undefined, formData.standort_strasse || undefined)
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
      standort_strasse: formData.standort_strasse || undefined,
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
              {/* D2: EIN Feld Straße & Hausnummer → präzisere Koordinaten (standort_strasse).
                  Nur unter IA_V4 (v3.46-Scope-Entscheid) — ohne Feld bleibt der Wert ''
                  und Geocoding läuft wie vor D2 über PLZ/Ort. */}
              {IA_V4 && (
                <div className="md:col-span-3">
                  <Input
                    label="Straße & Hausnummer (optional)"
                    name="standort_strasse"
                    value={formData.standort_strasse}
                    onChange={handleChange}
                    placeholder="z.B. Musterweg 12"
                  />
                </div>
              )}
            </div>

            {/* Geocoding Button */}
            <div className="mb-4">
              <Button
                type="button"
                variant="secondary"
                onClick={handleGeocode}
                loading={isGeocoding}
                disabled={!formData.standort_plz}
              >
                {isGeocoding ? (
                  'Ermittle Koordinaten...'
                ) : geocodeSuccess ? (
                  <>
                    <CheckCircle2 className="w-4 h-4 mr-2 text-green-500" />
                    Koordinaten ermittelt
                  </>
                ) : (
                  <>
                    <Search className="w-4 h-4 mr-2 max-sm:hidden" />
                    Koordinaten aus PLZ ermitteln
                  </>
                )}
              </Button>
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
