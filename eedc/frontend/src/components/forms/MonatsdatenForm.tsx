import { useState, FormEvent } from 'react'
import { Button, Input, Alert, Select } from '../ui'
import type { Monatsdaten } from '../../types'

interface MonatsdatenFormProps {
  monatsdaten?: Monatsdaten | null
  anlageId: number
  onSubmit: (data: {
    anlage_id: number
    jahr: number
    monat: number
    einspeisung_kwh: number
    netzbezug_kwh: number
    pv_erzeugung_kwh?: number
    batterie_ladung_kwh?: number
    batterie_entladung_kwh?: number
    notizen?: string
  }) => Promise<void>
  onCancel: () => void
}

const monatOptions = [
  { value: '1', label: 'Januar' },
  { value: '2', label: 'Februar' },
  { value: '3', label: 'März' },
  { value: '4', label: 'April' },
  { value: '5', label: 'Mai' },
  { value: '6', label: 'Juni' },
  { value: '7', label: 'Juli' },
  { value: '8', label: 'August' },
  { value: '9', label: 'September' },
  { value: '10', label: 'Oktober' },
  { value: '11', label: 'November' },
  { value: '12', label: 'Dezember' },
]

export default function MonatsdatenForm({ monatsdaten, anlageId, onSubmit, onCancel }: MonatsdatenFormProps) {
  const currentYear = new Date().getFullYear()
  const currentMonth = new Date().getMonth() + 1

  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [formData, setFormData] = useState({
    jahr: monatsdaten?.jahr?.toString() || currentYear.toString(),
    monat: monatsdaten?.monat?.toString() || currentMonth.toString(),
    einspeisung_kwh: monatsdaten?.einspeisung_kwh?.toString() || '',
    netzbezug_kwh: monatsdaten?.netzbezug_kwh?.toString() || '',
    pv_erzeugung_kwh: monatsdaten?.pv_erzeugung_kwh?.toString() || '',
    batterie_ladung_kwh: monatsdaten?.batterie_ladung_kwh?.toString() || '',
    batterie_entladung_kwh: monatsdaten?.batterie_entladung_kwh?.toString() || '',
    notizen: monatsdaten?.notizen || '',
  })

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) => {
    const { name, value } = e.target
    setFormData(prev => ({ ...prev, [name]: value }))
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)

    if (!formData.einspeisung_kwh || !formData.netzbezug_kwh) {
      setError('Bitte Einspeisung und Netzbezug eingeben')
      return
    }

    try {
      setLoading(true)
      await onSubmit({
        anlage_id: anlageId,
        jahr: parseInt(formData.jahr),
        monat: parseInt(formData.monat),
        einspeisung_kwh: parseFloat(formData.einspeisung_kwh),
        netzbezug_kwh: parseFloat(formData.netzbezug_kwh),
        pv_erzeugung_kwh: formData.pv_erzeugung_kwh ? parseFloat(formData.pv_erzeugung_kwh) : undefined,
        batterie_ladung_kwh: formData.batterie_ladung_kwh ? parseFloat(formData.batterie_ladung_kwh) : undefined,
        batterie_entladung_kwh: formData.batterie_entladung_kwh ? parseFloat(formData.batterie_entladung_kwh) : undefined,
        notizen: formData.notizen || undefined,
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

      {/* Zeitraum */}
      <div className="space-y-4">
        <h3 className="text-sm font-medium text-gray-900 dark:text-white">Zeitraum</h3>
        <div className="grid grid-cols-2 gap-4">
          <Input
            label="Jahr"
            name="jahr"
            type="number"
            min="2000"
            max="2100"
            value={formData.jahr}
            onChange={handleChange}
            required
            disabled={!!monatsdaten}
          />
          <Select
            label="Monat"
            name="monat"
            value={formData.monat}
            onChange={handleChange}
            options={monatOptions}
            required
            disabled={!!monatsdaten}
          />
        </div>
      </div>

      {/* Energie-Daten */}
      <div className="space-y-4">
        <h3 className="text-sm font-medium text-gray-900 dark:text-white">Energie-Daten (kWh)</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <Input
            label="Einspeisung"
            name="einspeisung_kwh"
            type="number"
            step="0.1"
            min="0"
            value={formData.einspeisung_kwh}
            onChange={handleChange}
            placeholder="z.B. 450"
            required
          />
          <Input
            label="Netzbezug"
            name="netzbezug_kwh"
            type="number"
            step="0.1"
            min="0"
            value={formData.netzbezug_kwh}
            onChange={handleChange}
            placeholder="z.B. 120"
            required
          />
          <Input
            label="PV-Erzeugung (optional)"
            name="pv_erzeugung_kwh"
            type="number"
            step="0.1"
            min="0"
            value={formData.pv_erzeugung_kwh}
            onChange={handleChange}
            placeholder="z.B. 800"
            hint="Wird berechnet wenn leer"
          />
        </div>
      </div>

      {/* Batterie (optional) */}
      <div className="space-y-4">
        <h3 className="text-sm font-medium text-gray-900 dark:text-white">Batterie (optional)</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <Input
            label="Batterie Ladung"
            name="batterie_ladung_kwh"
            type="number"
            step="0.1"
            min="0"
            value={formData.batterie_ladung_kwh}
            onChange={handleChange}
            placeholder="z.B. 150"
          />
          <Input
            label="Batterie Entladung"
            name="batterie_entladung_kwh"
            type="number"
            step="0.1"
            min="0"
            value={formData.batterie_entladung_kwh}
            onChange={handleChange}
            placeholder="z.B. 140"
          />
        </div>
      </div>

      {/* Notizen */}
      <div>
        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
          Notizen
        </label>
        <textarea
          name="notizen"
          value={formData.notizen}
          onChange={handleChange}
          rows={2}
          className="input"
          placeholder="Optionale Bemerkungen..."
        />
      </div>

      {/* Actions */}
      <div className="flex justify-end gap-3 pt-4 border-t border-gray-200 dark:border-gray-700">
        <Button type="button" variant="secondary" onClick={onCancel}>
          Abbrechen
        </Button>
        <Button type="submit" loading={loading}>
          {monatsdaten ? 'Speichern' : 'Monat erfassen'}
        </Button>
      </div>
    </form>
  )
}
