import { useState, FormEvent } from 'react'
import { Button, Input, Alert } from '../ui'
import type { Investition, InvestitionTyp } from '../../types'
import type { InvestitionCreate, InvestitionUpdate } from '../../api'

interface InvestitionFormProps {
  investition?: Investition | null
  anlageId: number
  typ: InvestitionTyp
  onSubmit: (data: InvestitionCreate | InvestitionUpdate) => Promise<void>
  onCancel: () => void
}

// Typ-Label Mapping
const typLabels: Record<InvestitionTyp, string> = {
  'e-auto': 'E-Auto',
  'waermepumpe': 'Wärmepumpe',
  'speicher': 'Speicher',
  'wallbox': 'Wallbox',
  'wechselrichter': 'Wechselrichter',
  'pv-module': 'PV-Module',
  'balkonkraftwerk': 'Balkonkraftwerk',
  'sonstiges': 'Sonstiges',
}

export default function InvestitionForm({ investition, anlageId, typ, onSubmit, onCancel }: InvestitionFormProps) {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [formData, setFormData] = useState({
    bezeichnung: investition?.bezeichnung || `Mein ${typLabels[typ]}`,
    anschaffungsdatum: investition?.anschaffungsdatum || '',
    anschaffungskosten_gesamt: investition?.anschaffungskosten_gesamt?.toString() || '',
    anschaffungskosten_alternativ: investition?.anschaffungskosten_alternativ?.toString() || '',
    betriebskosten_jahr: investition?.betriebskosten_jahr?.toString() || '',
    aktiv: investition?.aktiv ?? true,
  })

  // Typ-spezifische Parameter
  const params = investition?.parameter || {}
  const [paramData, setParamData] = useState<Record<string, string | boolean>>(() => {
    switch (typ) {
      case 'e-auto':
        return {
          batteriekapazitaet_kwh: params.batteriekapazitaet_kwh?.toString() || '',
          verbrauch_kwh_100km: params.verbrauch_kwh_100km?.toString() || '18',
          jahresfahrleistung_km: params.jahresfahrleistung_km?.toString() || '15000',
          pv_ladeanteil_prozent: params.pv_ladeanteil_prozent?.toString() || '60',
          v2h_faehig: params.v2h_faehig ?? false,
          v2h_entladeleistung_kw: params.v2h_entladeleistung_kw?.toString() || '',
        }
      case 'speicher':
        return {
          kapazitaet_kwh: params.kapazitaet_kwh?.toString() || '',
          nutzbare_kapazitaet_kwh: params.nutzbare_kapazitaet_kwh?.toString() || '',
          max_ladeleistung_kw: params.max_ladeleistung_kw?.toString() || '',
          max_entladeleistung_kw: params.max_entladeleistung_kw?.toString() || '',
          wirkungsgrad_prozent: params.wirkungsgrad_prozent?.toString() || '95',
          arbitrage_faehig: params.arbitrage_faehig ?? false,
        }
      case 'waermepumpe':
        return {
          leistung_kw: params.leistung_kw?.toString() || '',
          cop: params.cop?.toString() || '3.5',
          jahresarbeitszahl: params.jahresarbeitszahl?.toString() || '3.0',
          heizwaermebedarf_kwh: params.heizwaermebedarf_kwh?.toString() || '',
          warmwasserbedarf_kwh: params.warmwasserbedarf_kwh?.toString() || '',
          sg_ready: params.sg_ready ?? false,
        }
      case 'wallbox':
        return {
          max_ladeleistung_kw: params.max_ladeleistung_kw?.toString() || '11',
          bidirektional: params.bidirektional ?? false,
          pv_optimiert: params.pv_optimiert ?? true,
        }
      case 'wechselrichter':
        return {
          max_leistung_kw: params.max_leistung_kw?.toString() || '',
          wirkungsgrad_prozent: params.wirkungsgrad_prozent?.toString() || '97',
          hybrid: params.hybrid ?? false,
        }
      case 'pv-module':
      case 'balkonkraftwerk':
        return {
          leistung_wp: params.leistung_wp?.toString() || '',
          anzahl: params.anzahl?.toString() || '',
          ausrichtung: params.ausrichtung?.toString() || 'Süd',
          neigung_grad: params.neigung_grad?.toString() || '30',
        }
      default:
        return {}
    }
  })

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value, type, checked } = e.target
    if (name.startsWith('param_')) {
      const paramName = name.replace('param_', '')
      setParamData(prev => ({
        ...prev,
        [paramName]: type === 'checkbox' ? checked : value
      }))
    } else {
      setFormData(prev => ({
        ...prev,
        [name]: type === 'checkbox' ? checked : value
      }))
    }
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)

    if (!formData.bezeichnung.trim()) {
      setError('Bitte eine Bezeichnung eingeben')
      return
    }

    try {
      setLoading(true)

      // Parameter konvertieren
      const convertedParams: Record<string, unknown> = {}
      Object.entries(paramData).forEach(([key, value]) => {
        if (typeof value === 'boolean') {
          convertedParams[key] = value
        } else if (value !== '') {
          const num = parseFloat(value)
          convertedParams[key] = isNaN(num) ? value : num
        }
      })

      const data: InvestitionCreate | InvestitionUpdate = {
        ...(investition ? {} : { anlage_id: anlageId, typ }),
        bezeichnung: formData.bezeichnung.trim(),
        anschaffungsdatum: formData.anschaffungsdatum || undefined,
        anschaffungskosten_gesamt: formData.anschaffungskosten_gesamt ? parseFloat(formData.anschaffungskosten_gesamt) : undefined,
        anschaffungskosten_alternativ: formData.anschaffungskosten_alternativ ? parseFloat(formData.anschaffungskosten_alternativ) : undefined,
        betriebskosten_jahr: formData.betriebskosten_jahr ? parseFloat(formData.betriebskosten_jahr) : undefined,
        aktiv: formData.aktiv,
        parameter: Object.keys(convertedParams).length > 0 ? convertedParams : undefined,
      }

      await onSubmit(data)
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
        <h3 className="text-sm font-medium text-gray-900 dark:text-white">Allgemein</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <Input
            label="Bezeichnung"
            name="bezeichnung"
            value={formData.bezeichnung}
            onChange={handleChange}
            required
          />
          <Input
            label="Anschaffungsdatum"
            name="anschaffungsdatum"
            type="date"
            value={formData.anschaffungsdatum}
            onChange={handleChange}
          />
          <Input
            label="Anschaffungskosten (€)"
            name="anschaffungskosten_gesamt"
            type="number"
            step="0.01"
            min="0"
            value={formData.anschaffungskosten_gesamt}
            onChange={handleChange}
            hint="Gesamtkosten inkl. Installation"
          />
          <Input
            label="Alternative Kosten (€)"
            name="anschaffungskosten_alternativ"
            type="number"
            step="0.01"
            min="0"
            value={formData.anschaffungskosten_alternativ}
            onChange={handleChange}
            hint="z.B. Verbrenner-Kosten bei E-Auto"
          />
          <Input
            label="Betriebskosten/Jahr (€)"
            name="betriebskosten_jahr"
            type="number"
            step="0.01"
            min="0"
            value={formData.betriebskosten_jahr}
            onChange={handleChange}
            hint="Wartung, Versicherung, etc."
          />
        </div>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            name="aktiv"
            checked={formData.aktiv}
            onChange={handleChange}
            className="rounded border-gray-300 text-primary-600 focus:ring-primary-500"
          />
          <span className="text-gray-700 dark:text-gray-300">Aktiv (in Berechnungen berücksichtigen)</span>
        </label>
      </div>

      {/* Typ-spezifische Parameter */}
      <TypSpecificFields typ={typ} paramData={paramData} onChange={handleChange} />

      {/* Actions */}
      <div className="flex justify-end gap-3 pt-4 border-t border-gray-200 dark:border-gray-700">
        <Button type="button" variant="secondary" onClick={onCancel}>
          Abbrechen
        </Button>
        <Button type="submit" loading={loading}>
          {investition ? 'Speichern' : 'Erstellen'}
        </Button>
      </div>
    </form>
  )
}

interface TypSpecificFieldsProps {
  typ: InvestitionTyp
  paramData: Record<string, string | boolean>
  onChange: (e: React.ChangeEvent<HTMLInputElement>) => void
}

function TypSpecificFields({ typ, paramData, onChange }: TypSpecificFieldsProps) {
  switch (typ) {
    case 'e-auto':
      return (
        <div className="space-y-4">
          <h3 className="text-sm font-medium text-gray-900 dark:text-white">E-Auto Parameter</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Input
              label="Batteriekapazität (kWh)"
              name="param_batteriekapazitaet_kwh"
              type="number"
              step="0.1"
              min="0"
              value={paramData.batteriekapazitaet_kwh as string}
              onChange={onChange}
            />
            <Input
              label="Verbrauch (kWh/100km)"
              name="param_verbrauch_kwh_100km"
              type="number"
              step="0.1"
              min="0"
              value={paramData.verbrauch_kwh_100km as string}
              onChange={onChange}
            />
            <Input
              label="Jahresfahrleistung (km)"
              name="param_jahresfahrleistung_km"
              type="number"
              step="100"
              min="0"
              value={paramData.jahresfahrleistung_km as string}
              onChange={onChange}
            />
            <Input
              label="PV-Ladeanteil (%)"
              name="param_pv_ladeanteil_prozent"
              type="number"
              step="1"
              min="0"
              max="100"
              value={paramData.pv_ladeanteil_prozent as string}
              onChange={onChange}
              hint="Anteil der Ladung aus PV-Strom"
            />
          </div>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              name="param_v2h_faehig"
              checked={paramData.v2h_faehig as boolean}
              onChange={onChange}
              className="rounded border-gray-300 text-primary-600 focus:ring-primary-500"
            />
            <span className="text-gray-700 dark:text-gray-300">V2H-fähig (Vehicle-to-Home)</span>
          </label>
          {paramData.v2h_faehig && (
            <Input
              label="V2H Entladeleistung (kW)"
              name="param_v2h_entladeleistung_kw"
              type="number"
              step="0.1"
              min="0"
              value={paramData.v2h_entladeleistung_kw as string}
              onChange={onChange}
            />
          )}
        </div>
      )

    case 'speicher':
      return (
        <div className="space-y-4">
          <h3 className="text-sm font-medium text-gray-900 dark:text-white">Speicher Parameter</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Input
              label="Kapazität (kWh)"
              name="param_kapazitaet_kwh"
              type="number"
              step="0.1"
              min="0"
              value={paramData.kapazitaet_kwh as string}
              onChange={onChange}
            />
            <Input
              label="Nutzbare Kapazität (kWh)"
              name="param_nutzbare_kapazitaet_kwh"
              type="number"
              step="0.1"
              min="0"
              value={paramData.nutzbare_kapazitaet_kwh as string}
              onChange={onChange}
              hint="Typisch 90-95% der Gesamtkapazität"
            />
            <Input
              label="Max. Ladeleistung (kW)"
              name="param_max_ladeleistung_kw"
              type="number"
              step="0.1"
              min="0"
              value={paramData.max_ladeleistung_kw as string}
              onChange={onChange}
            />
            <Input
              label="Max. Entladeleistung (kW)"
              name="param_max_entladeleistung_kw"
              type="number"
              step="0.1"
              min="0"
              value={paramData.max_entladeleistung_kw as string}
              onChange={onChange}
            />
            <Input
              label="Wirkungsgrad (%)"
              name="param_wirkungsgrad_prozent"
              type="number"
              step="0.1"
              min="0"
              max="100"
              value={paramData.wirkungsgrad_prozent as string}
              onChange={onChange}
            />
          </div>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              name="param_arbitrage_faehig"
              checked={paramData.arbitrage_faehig as boolean}
              onChange={onChange}
              className="rounded border-gray-300 text-primary-600 focus:ring-primary-500"
            />
            <span className="text-gray-700 dark:text-gray-300">Arbitrage-fähig (Netzladen bei Niedrigtarif)</span>
          </label>
        </div>
      )

    case 'waermepumpe':
      return (
        <div className="space-y-4">
          <h3 className="text-sm font-medium text-gray-900 dark:text-white">Wärmepumpe Parameter</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Input
              label="Nennleistung (kW)"
              name="param_leistung_kw"
              type="number"
              step="0.1"
              min="0"
              value={paramData.leistung_kw as string}
              onChange={onChange}
            />
            <Input
              label="COP (Leistungszahl)"
              name="param_cop"
              type="number"
              step="0.1"
              min="1"
              max="10"
              value={paramData.cop as string}
              onChange={onChange}
              hint="Typisch 3-5 bei Luft-WP"
            />
            <Input
              label="Jahresarbeitszahl"
              name="param_jahresarbeitszahl"
              type="number"
              step="0.1"
              min="1"
              max="10"
              value={paramData.jahresarbeitszahl as string}
              onChange={onChange}
            />
            <Input
              label="Heizwärmebedarf (kWh/Jahr)"
              name="param_heizwaermebedarf_kwh"
              type="number"
              step="100"
              min="0"
              value={paramData.heizwaermebedarf_kwh as string}
              onChange={onChange}
            />
            <Input
              label="Warmwasserbedarf (kWh/Jahr)"
              name="param_warmwasserbedarf_kwh"
              type="number"
              step="100"
              min="0"
              value={paramData.warmwasserbedarf_kwh as string}
              onChange={onChange}
            />
          </div>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              name="param_sg_ready"
              checked={paramData.sg_ready as boolean}
              onChange={onChange}
              className="rounded border-gray-300 text-primary-600 focus:ring-primary-500"
            />
            <span className="text-gray-700 dark:text-gray-300">SG Ready (Smart Grid fähig)</span>
          </label>
        </div>
      )

    case 'wallbox':
      return (
        <div className="space-y-4">
          <h3 className="text-sm font-medium text-gray-900 dark:text-white">Wallbox Parameter</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Input
              label="Max. Ladeleistung (kW)"
              name="param_max_ladeleistung_kw"
              type="number"
              step="0.1"
              min="0"
              value={paramData.max_ladeleistung_kw as string}
              onChange={onChange}
              hint="Typisch 11 kW oder 22 kW"
            />
          </div>
          <div className="space-y-2">
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                name="param_bidirektional"
                checked={paramData.bidirektional as boolean}
                onChange={onChange}
                className="rounded border-gray-300 text-primary-600 focus:ring-primary-500"
              />
              <span className="text-gray-700 dark:text-gray-300">Bidirektional (V2H/V2G)</span>
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                name="param_pv_optimiert"
                checked={paramData.pv_optimiert as boolean}
                onChange={onChange}
                className="rounded border-gray-300 text-primary-600 focus:ring-primary-500"
              />
              <span className="text-gray-700 dark:text-gray-300">PV-Überschussladen möglich</span>
            </label>
          </div>
        </div>
      )

    case 'wechselrichter':
      return (
        <div className="space-y-4">
          <h3 className="text-sm font-medium text-gray-900 dark:text-white">Wechselrichter Parameter</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Input
              label="Max. Leistung (kW)"
              name="param_max_leistung_kw"
              type="number"
              step="0.1"
              min="0"
              value={paramData.max_leistung_kw as string}
              onChange={onChange}
            />
            <Input
              label="Wirkungsgrad (%)"
              name="param_wirkungsgrad_prozent"
              type="number"
              step="0.1"
              min="0"
              max="100"
              value={paramData.wirkungsgrad_prozent as string}
              onChange={onChange}
            />
          </div>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              name="param_hybrid"
              checked={paramData.hybrid as boolean}
              onChange={onChange}
              className="rounded border-gray-300 text-primary-600 focus:ring-primary-500"
            />
            <span className="text-gray-700 dark:text-gray-300">Hybrid-Wechselrichter (mit Speicher-Anschluss)</span>
          </label>
        </div>
      )

    case 'pv-module':
    case 'balkonkraftwerk':
      return (
        <div className="space-y-4">
          <h3 className="text-sm font-medium text-gray-900 dark:text-white">
            {typ === 'balkonkraftwerk' ? 'Balkonkraftwerk' : 'PV-Module'} Parameter
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Input
              label="Leistung pro Modul (Wp)"
              name="param_leistung_wp"
              type="number"
              step="1"
              min="0"
              value={paramData.leistung_wp as string}
              onChange={onChange}
            />
            <Input
              label="Anzahl Module"
              name="param_anzahl"
              type="number"
              step="1"
              min="1"
              value={paramData.anzahl as string}
              onChange={onChange}
            />
            <Input
              label="Ausrichtung"
              name="param_ausrichtung"
              value={paramData.ausrichtung as string}
              onChange={onChange}
              hint="z.B. Süd, Ost-West"
            />
            <Input
              label="Neigung (Grad)"
              name="param_neigung_grad"
              type="number"
              step="1"
              min="0"
              max="90"
              value={paramData.neigung_grad as string}
              onChange={onChange}
            />
          </div>
        </div>
      )

    default:
      return null
  }
}
