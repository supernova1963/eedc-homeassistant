import { useState, FormEvent } from 'react'
import { Button, Input, Select, Alert } from '../ui'
import type { Anlage, AnlageCreate } from '../../types'

interface AnlageFormProps {
  anlage?: Anlage | null
  onSubmit: (data: AnlageCreate) => Promise<void>
  onCancel: () => void
}

const ausrichtungOptions = [
  { value: 'Süd', label: 'Süd' },
  { value: 'Südost', label: 'Südost' },
  { value: 'Südwest', label: 'Südwest' },
  { value: 'Ost', label: 'Ost' },
  { value: 'West', label: 'West' },
  { value: 'Ost-West', label: 'Ost-West' },
]

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
    ausrichtung: anlage?.ausrichtung || '',
    neigung_grad: anlage?.neigung_grad?.toString() || '',
  })

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
        ausrichtung: formData.ausrichtung || undefined,
        neigung_grad: formData.neigung_grad ? parseFloat(formData.neigung_grad) : undefined,
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

      {/* Technische Daten */}
      <div className="space-y-4">
        <h3 className="text-sm font-medium text-gray-900 dark:text-white">Technische Daten</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <Select
            label="Ausrichtung"
            name="ausrichtung"
            value={formData.ausrichtung}
            onChange={handleChange}
            options={ausrichtungOptions}
            placeholder="-- Auswählen --"
          />
          <Input
            label="Neigung (Grad)"
            name="neigung_grad"
            type="number"
            step="1"
            min="0"
            max="90"
            value={formData.neigung_grad}
            onChange={handleChange}
            placeholder="z.B. 30"
          />
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
