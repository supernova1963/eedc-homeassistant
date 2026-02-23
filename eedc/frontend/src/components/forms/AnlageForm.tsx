import { useState, useEffect, FormEvent } from 'react'
import { Info, ExternalLink, Cloud, Sun } from 'lucide-react'
import { Button, Input, Alert } from '../ui'
import VersorgerSection from './VersorgerSection'
import { wetterApi, type WetterProvider, type WetterProviderOption } from '../../api/wetter'
import type { Anlage, AnlageCreate, VersorgerDaten } from '../../types'

interface AnlageFormProps {
  anlage?: Anlage | null
  onSubmit: (data: AnlageCreate) => Promise<void>
  onCancel: () => void
}

export default function AnlageForm({ anlage, onSubmit, onCancel }: AnlageFormProps) {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [formData, setFormData] = useState({
    anlagenname: anlage?.anlagenname || '',
    leistung_kwp: anlage?.leistung_kwp?.toString() || '',
    installationsdatum: anlage?.installationsdatum || '',
    standort_land: anlage?.standort_land || 'DE',
    standort_plz: anlage?.standort_plz || '',
    standort_ort: anlage?.standort_ort || '',
    standort_strasse: anlage?.standort_strasse || '',
    latitude: anlage?.latitude?.toString() || '',
    longitude: anlage?.longitude?.toString() || '',
    mastr_id: anlage?.mastr_id || '',
    wetter_provider: (anlage as any)?.wetter_provider || 'auto',
  })

  const [versorgerDaten, setVersorgerDaten] = useState<VersorgerDaten>(
    anlage?.versorger_daten || {}
  )

  const [wetterProviderOptions, setWetterProviderOptions] = useState<WetterProviderOption[]>([])
  const [loadingProvider, setLoadingProvider] = useState(false)

  // Wetter-Provider laden wenn Anlage existiert und Koordinaten hat
  useEffect(() => {
    if (anlage?.id && anlage.latitude && anlage.longitude) {
      setLoadingProvider(true)
      wetterApi.getProvider(anlage.id)
        .then(data => setWetterProviderOptions(data.provider))
        .catch(err => console.warn('Wetter-Provider laden fehlgeschlagen:', err))
        .finally(() => setLoadingProvider(false))
    }
  }, [anlage?.id, anlage?.latitude, anlage?.longitude])

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    const { name, value } = e.target
    setFormData(prev => ({ ...prev, [name]: value }))
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)

    if (!formData.anlagenname.trim()) {
      setError('Bitte einen Namen eingeben')
      return
    }

    if (!formData.leistung_kwp || parseFloat(formData.leistung_kwp) <= 0) {
      setError('Bitte eine gültige Leistung eingeben')
      return
    }

    try {
      setLoading(true)
      await onSubmit({
        anlagenname: formData.anlagenname.trim(),
        leistung_kwp: parseFloat(formData.leistung_kwp),
        installationsdatum: formData.installationsdatum || undefined,
        standort_land: formData.standort_land || 'DE',
        standort_plz: formData.standort_plz || undefined,
        standort_ort: formData.standort_ort || undefined,
        standort_strasse: formData.standort_strasse || undefined,
        latitude: formData.latitude ? parseFloat(formData.latitude) : undefined,
        longitude: formData.longitude ? parseFloat(formData.longitude) : undefined,
        mastr_id: formData.mastr_id || undefined,
        versorger_daten: Object.keys(versorgerDaten).length > 0 ? versorgerDaten : undefined,
        wetter_provider: formData.wetter_provider as WetterProvider,
      } as AnlageCreate)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Fehler beim Speichern')
    } finally {
      setLoading(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      {error && <Alert type="error">{error}</Alert>}

      {/* Basis-Daten */}
      <div className="space-y-4">
        <h3 className="text-sm font-medium text-gray-900 dark:text-white">Basis-Daten</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
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
            type="number"
            step="0.01"
            min="0.1"
            value={formData.leistung_kwp}
            onChange={handleChange}
            placeholder="z.B. 10.5"
            required
          />
          <Input
            label="Installationsdatum"
            name="installationsdatum"
            type="date"
            min="2000-01-01"
            max="2099-12-31"
            value={formData.installationsdatum}
            onChange={handleChange}
          />
        </div>
      </div>

      {/* Hinweis zu technischen Daten */}
      <div className="p-3 bg-blue-50 dark:bg-blue-900/20 rounded-lg flex gap-2">
        <Info className="w-4 h-4 text-blue-500 flex-shrink-0 mt-0.5" />
        <div className="text-xs text-blue-700 dark:text-blue-300">
          <p className="font-medium mb-1">Ausrichtung & Neigung</p>
          <p>
            Diese Werte werden pro <strong>PV-Modul</strong> unter <strong>Einstellungen → Investitionen</strong> gepflegt.
            So können auch Anlagen mit mehreren Dachflächen korrekt abgebildet werden.
          </p>
        </div>
      </div>

      {/* Standort */}
      <div className="space-y-4">
        <h3 className="text-sm font-medium text-gray-900 dark:text-white">Standort</h3>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Land</label>
            <select
              name="standort_land"
              value={formData.standort_land}
              onChange={handleChange}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="DE">Deutschland</option>
              <option value="AT">Österreich</option>
              <option value="CH">Schweiz</option>
            </select>
          </div>
          <Input
            label="PLZ"
            name="standort_plz"
            value={formData.standort_plz}
            onChange={handleChange}
            placeholder={formData.standort_land === 'DE' ? 'z.B. 12345' : 'z.B. 1234'}
          />
          <Input
            label="Ort"
            name="standort_ort"
            value={formData.standort_ort}
            onChange={handleChange}
            placeholder="z.B. Wien"
          />
          <Input
            label="Straße"
            name="standort_strasse"
            value={formData.standort_strasse}
            onChange={handleChange}
            placeholder="z.B. Musterstraße 1"
          />
        </div>
      </div>

      {/* Geokoordinaten */}
      <div className="space-y-4">
        <h3 className="text-sm font-medium text-gray-900 dark:text-white">
          Geokoordinaten
          <span className="text-xs font-normal text-gray-500 ml-2">(für PVGIS-Prognose)</span>
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <Input
            label="Breitengrad (Latitude)"
            name="latitude"
            type="number"
            step="0.000001"
            value={formData.latitude}
            onChange={handleChange}
            placeholder="z.B. 52.520008"
            hint="Nördliche Breite (positiv)"
          />
          <Input
            label="Längengrad (Longitude)"
            name="longitude"
            type="number"
            step="0.000001"
            value={formData.longitude}
            onChange={handleChange}
            placeholder="z.B. 13.404954"
            hint="Östliche Länge (positiv)"
          />
        </div>
      </div>

      {/* Erweiterte Stammdaten */}
      <div className="space-y-4">
        <h3 className="text-sm font-medium text-gray-900 dark:text-white">
          Erweiterte Stammdaten
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <Input
              label="MaStR-ID"
              name="mastr_id"
              value={formData.mastr_id}
              onChange={handleChange}
              placeholder="z.B. SEE123456789"
              hint="Marktstammdatenregister-ID der Anlage"
            />
            {formData.mastr_id && (
              <a
                href={`https://www.marktstammdatenregister.de/MaStR/Einheit/Detail/IndexOeffentlich/${formData.mastr_id}`}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 mt-1 text-xs text-blue-600 hover:text-blue-700 dark:text-blue-400"
              >
                <ExternalLink className="w-3 h-3" />
                Im MaStR öffnen
              </a>
            )}
          </div>
        </div>
      </div>

      {/* Wetterdaten-Quelle */}
      <div className="space-y-4">
        <h3 className="text-sm font-medium text-gray-900 dark:text-white flex items-center gap-2">
          <Cloud className="w-4 h-4 text-blue-500" />
          Wetterdaten-Quelle
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="w-full">
            <label
              htmlFor="wetter_provider"
              className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1"
            >
              Bevorzugter Provider
            </label>
            <select
              id="wetter_provider"
              name="wetter_provider"
              value={formData.wetter_provider}
              onChange={handleChange}
              disabled={loadingProvider}
              className="w-full px-3 py-2 rounded-lg border bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent disabled:bg-gray-100 dark:disabled:bg-gray-700 disabled:cursor-not-allowed border-gray-300 dark:border-gray-600"
            >
              {wetterProviderOptions.length > 0 ? (
                wetterProviderOptions.map(p => (
                  <option
                    key={p.id}
                    value={p.id}
                    disabled={!p.verfuegbar}
                  >
                    {p.name}
                    {p.empfohlen ? ' (empfohlen)' : ''}
                    {!p.verfuegbar ? ' (nicht verfügbar)' : ''}
                  </option>
                ))
              ) : (
                <>
                  <option value="auto">Automatisch (empfohlen)</option>
                  <option value="open-meteo">Open-Meteo</option>
                  <option value="brightsky">Bright Sky (DWD)</option>
                  <option value="open-meteo-solar">Open-Meteo Solar</option>
                </>
              )}
            </select>
          </div>
          <div className="flex items-end pb-1">
            <div className="text-xs text-gray-500 dark:text-gray-400">
              {formData.wetter_provider === 'auto' && (
                <span>Automatische Auswahl: Bright Sky für DE, Open-Meteo sonst</span>
              )}
              {formData.wetter_provider === 'brightsky' && (
                <span>DWD-Daten über Bright Sky API (nur Deutschland)</span>
              )}
              {formData.wetter_provider === 'open-meteo' && (
                <span>Open-Meteo Archive API (weltweit verfügbar)</span>
              )}
              {formData.wetter_provider === 'open-meteo-solar' && (
                <span>GTI-Berechnung für geneigte PV-Module</span>
              )}
            </div>
          </div>
        </div>
        {!anlage?.latitude && !anlage?.longitude && (
          <div className="p-3 bg-amber-50 dark:bg-amber-900/20 rounded-lg flex gap-2">
            <Sun className="w-4 h-4 text-amber-500 flex-shrink-0 mt-0.5" />
            <p className="text-xs text-amber-700 dark:text-amber-300">
              Bitte zuerst Geokoordinaten eintragen, um die verfügbaren Provider zu sehen.
            </p>
          </div>
        )}
      </div>

      {/* Versorger & Zähler */}
      <VersorgerSection value={versorgerDaten} onChange={setVersorgerDaten} />

      {/* Actions */}
      <div className="flex justify-end gap-3 pt-4 border-t border-gray-200 dark:border-gray-700">
        <Button type="button" variant="secondary" onClick={onCancel}>
          Abbrechen
        </Button>
        <Button type="submit" loading={loading}>
          {anlage ? 'Speichern' : 'Anlage erstellen'}
        </Button>
      </div>
    </form>
  )
}
