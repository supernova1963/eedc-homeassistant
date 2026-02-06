import { useState, FormEvent } from 'react'
import { Button, Input, Alert } from '../ui'
import type { Strompreis } from '../../types'

interface StrompreisFormProps {
  strompreis?: Strompreis | null
  anlageId: number
  onSubmit: (data: {
    anlage_id: number
    netzbezug_arbeitspreis_cent_kwh: number
    einspeiseverguetung_cent_kwh: number
    grundpreis_euro_monat?: number
    gueltig_ab: string
    gueltig_bis?: string
    tarifname?: string
    anbieter?: string
  }) => Promise<void>
  onCancel: () => void
}

export default function StrompreisForm({ strompreis, anlageId, onSubmit, onCancel }: StrompreisFormProps) {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [formData, setFormData] = useState({
    netzbezug_arbeitspreis_cent_kwh: strompreis?.netzbezug_arbeitspreis_cent_kwh?.toString() || '30',
    einspeiseverguetung_cent_kwh: strompreis?.einspeiseverguetung_cent_kwh?.toString() || '8.2',
    grundpreis_euro_monat: strompreis?.grundpreis_euro_monat?.toString() || '',
    gueltig_ab: strompreis?.gueltig_ab || new Date().toISOString().split('T')[0],
    gueltig_bis: strompreis?.gueltig_bis || '',
    tarifname: strompreis?.tarifname || '',
    anbieter: strompreis?.anbieter || '',
  })

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = e.target
    setFormData(prev => ({ ...prev, [name]: value }))
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)

    if (!formData.netzbezug_arbeitspreis_cent_kwh || parseFloat(formData.netzbezug_arbeitspreis_cent_kwh) < 0) {
      setError('Bitte einen gültigen Netzbezugspreis eingeben')
      return
    }

    if (!formData.gueltig_ab) {
      setError('Bitte ein Gültigkeitsdatum eingeben')
      return
    }

    try {
      setLoading(true)
      await onSubmit({
        anlage_id: anlageId,
        netzbezug_arbeitspreis_cent_kwh: parseFloat(formData.netzbezug_arbeitspreis_cent_kwh),
        einspeiseverguetung_cent_kwh: parseFloat(formData.einspeiseverguetung_cent_kwh) || 0,
        grundpreis_euro_monat: formData.grundpreis_euro_monat ? parseFloat(formData.grundpreis_euro_monat) : undefined,
        gueltig_ab: formData.gueltig_ab,
        gueltig_bis: formData.gueltig_bis || undefined,
        tarifname: formData.tarifname || undefined,
        anbieter: formData.anbieter || undefined,
      })
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Fehler beim Speichern')
    } finally {
      setLoading(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      {error && <Alert type="error">{error}</Alert>}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Input
          label="Netzbezugspreis (ct/kWh)"
          name="netzbezug_arbeitspreis_cent_kwh"
          type="number"
          step="0.01"
          min="0"
          value={formData.netzbezug_arbeitspreis_cent_kwh}
          onChange={handleChange}
          required
        />
        <Input
          label="Einspeisevergütung (ct/kWh)"
          name="einspeiseverguetung_cent_kwh"
          type="number"
          step="0.01"
          min="0"
          value={formData.einspeiseverguetung_cent_kwh}
          onChange={handleChange}
          required
        />
        <Input
          label="Grundpreis (€/Monat)"
          name="grundpreis_euro_monat"
          type="number"
          step="0.01"
          min="0"
          value={formData.grundpreis_euro_monat}
          onChange={handleChange}
        />
        <Input
          label="Gültig ab"
          name="gueltig_ab"
          type="date"
          min="2000-01-01"
          max="2099-12-31"
          value={formData.gueltig_ab}
          onChange={handleChange}
          required
        />
        <Input
          label="Gültig bis"
          name="gueltig_bis"
          type="date"
          min="2000-01-01"
          max="2099-12-31"
          value={formData.gueltig_bis}
          onChange={handleChange}
          hint="Leer lassen für aktuell gültigen Tarif"
        />
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

      <div className="flex justify-end gap-3 pt-4 border-t border-gray-200 dark:border-gray-700">
        <Button type="button" variant="secondary" onClick={onCancel}>
          Abbrechen
        </Button>
        <Button type="submit" loading={loading}>
          {strompreis ? 'Speichern' : 'Tarif erstellen'}
        </Button>
      </div>
    </form>
  )
}
