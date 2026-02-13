import { useState, FormEvent } from 'react'
import { Info, ExternalLink } from 'lucide-react'
import { Button, Input, Alert } from '../ui'
import VersorgerSection from './VersorgerSection'
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
    standort_plz: anlage?.standort_plz || '',
    standort_ort: anlage?.standort_ort || '',
    standort_strasse: anlage?.standort_strasse || '',
    latitude: anlage?.latitude?.toString() || '',
    longitude: anlage?.longitude?.toString() || '',
    mastr_id: anlage?.mastr_id || '',
  })

  const [versorgerDaten, setVersorgerDaten] = useState<VersorgerDaten>(
    anlage?.versorger_daten || {}
  )

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
        standort_plz: formData.standort_plz || undefined,
        standort_ort: formData.standort_ort || undefined,
        standort_strasse: formData.standort_strasse || undefined,
        latitude: formData.latitude ? parseFloat(formData.latitude) : undefined,
        longitude: formData.longitude ? parseFloat(formData.longitude) : undefined,
        mastr_id: formData.mastr_id || undefined,
        versorger_daten: Object.keys(versorgerDaten).length > 0 ? versorgerDaten : undefined,
      })
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
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <Input
            label="PLZ"
            name="standort_plz"
            value={formData.standort_plz}
            onChange={handleChange}
            placeholder="z.B. 12345"
          />
          <Input
            label="Ort"
            name="standort_ort"
            value={formData.standort_ort}
            onChange={handleChange}
            placeholder="z.B. Berlin"
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
