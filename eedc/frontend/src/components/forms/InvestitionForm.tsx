import { useState, useEffect, FormEvent } from 'react'
import { Button, Input, Alert } from '../ui'
import type { Investition, InvestitionTyp } from '../../types'
import type { InvestitionCreate, InvestitionUpdate } from '../../api'
import { haApi, investitionenApi } from '../../api'
import type { HASensor } from '../../api'
import { AlertCircle } from 'lucide-react'

// Parent-Kind Beziehungen (analog zu useSetupWizard.ts)
const PARENT_MAPPING: Partial<Record<InvestitionTyp, InvestitionTyp>> = {
  'pv-module': 'wechselrichter',  // Pflicht
  'speicher': 'wechselrichter',    // Optional
}
const PARENT_REQUIRED: InvestitionTyp[] = ['pv-module']

const PARENT_TYPE_LABELS: Record<string, string> = {
  'wechselrichter': 'Wechselrichter',
}

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

// Kontextabhängige Hints für Alternative Kosten
const alternativkostenHints: Record<InvestitionTyp, string> = {
  'e-auto': 'Kosten eines vergleichbaren Verbrenners (für ROI-Berechnung)',
  'waermepumpe': 'Kosten einer neuen Gas-/Ölheizung (für ROI-Berechnung)',
  'speicher': 'Meist 0 - es gibt keine echte Alternative',
  'wallbox': 'Meist 0 - es gibt keine echte Alternative',
  'wechselrichter': 'Meist 0 - es gibt keine echte Alternative',
  'pv-module': 'Meist 0 - es gibt keine echte Alternative',
  'balkonkraftwerk': 'Meist 0 - es gibt keine echte Alternative',
  'sonstiges': 'Kosten einer Alternative (falls vorhanden)',
}

export default function InvestitionForm({ investition, anlageId, typ, onSubmit, onCancel }: InvestitionFormProps) {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [stringSensors, setStringSensors] = useState<HASensor[]>([])
  const [loadingSensors, setLoadingSensors] = useState(false)
  const [possibleParents, setPossibleParents] = useState<Investition[]>([])
  const [loadingParents, setLoadingParents] = useState(false)

  const [formData, setFormData] = useState({
    bezeichnung: investition?.bezeichnung || `Mein ${typLabels[typ]}`,
    anschaffungsdatum: investition?.anschaffungsdatum || '',
    anschaffungskosten_gesamt: investition?.anschaffungskosten_gesamt?.toString() || '',
    anschaffungskosten_alternativ: investition?.anschaffungskosten_alternativ?.toString() || '',
    betriebskosten_jahr: investition?.betriebskosten_jahr?.toString() || '',
    aktiv: investition?.aktiv ?? true,
    parent_investition_id: investition?.parent_investition_id?.toString() || '',
    // PV-Module direkte Felder
    leistung_kwp: investition?.leistung_kwp?.toString() || '',
    ausrichtung: investition?.ausrichtung || 'Süd',
    neigung_grad: investition?.neigung_grad?.toString() || '30',
    ha_entity_id: investition?.ha_entity_id || '',
  })

  // Parent-Typ für diesen Investitions-Typ ermitteln
  const parentTyp = PARENT_MAPPING[typ]
  const isParentRequired = PARENT_REQUIRED.includes(typ)

  // Parent-Investitionen laden wenn nötig
  useEffect(() => {
    if (parentTyp) {
      setLoadingParents(true)
      investitionenApi.list(anlageId, parentTyp, true)
        .then(parents => setPossibleParents(parents.filter(p => p.id !== investition?.id)))
        .catch(() => setPossibleParents([]))
        .finally(() => setLoadingParents(false))
    }
  }, [parentTyp, anlageId, investition?.id])

  // String-Sensoren laden für PV-Module
  useEffect(() => {
    if (typ === 'pv-module') {
      setLoadingSensors(true)
      haApi.getStringSensors()
        .then(setStringSensors)
        .catch(() => setStringSensors([]))
        .finally(() => setLoadingSensors(false))
    }
  }, [typ])

  // Typ-spezifische Parameter
  const params = investition?.parameter || {}

  const getInitialParamData = (): Record<string, string | boolean> => {
    switch (typ) {
      case 'e-auto':
        return {
          batteriekapazitaet_kwh: params.batteriekapazitaet_kwh?.toString() || '',
          verbrauch_kwh_100km: params.verbrauch_kwh_100km?.toString() || '18',
          jahresfahrleistung_km: params.jahresfahrleistung_km?.toString() || '15000',
          pv_ladeanteil_prozent: params.pv_ladeanteil_prozent?.toString() || '60',
          vergleich_verbrauch_l_100km: params.vergleich_verbrauch_l_100km?.toString() || '7.5',
          benzinpreis_euro: params.benzinpreis_euro?.toString() || '1.65',
          v2h_faehig: (params.v2h_faehig as boolean) ?? false,
          v2h_entladeleistung_kw: params.v2h_entladeleistung_kw?.toString() || '',
        }
      case 'speicher':
        return {
          kapazitaet_kwh: params.kapazitaet_kwh?.toString() || '',
          nutzbare_kapazitaet_kwh: params.nutzbare_kapazitaet_kwh?.toString() || '',
          max_ladeleistung_kw: params.max_ladeleistung_kw?.toString() || '',
          max_entladeleistung_kw: params.max_entladeleistung_kw?.toString() || '',
          wirkungsgrad_prozent: params.wirkungsgrad_prozent?.toString() || '95',
          arbitrage_faehig: (params.arbitrage_faehig as boolean) ?? false,
        }
      case 'waermepumpe':
        return {
          leistung_kw: params.leistung_kw?.toString() || '',
          cop: params.cop?.toString() || '3.5',
          jahresarbeitszahl: params.jahresarbeitszahl?.toString() || '3.0',
          heizwaermebedarf_kwh: params.heizwaermebedarf_kwh?.toString() || '',
          warmwasserbedarf_kwh: params.warmwasserbedarf_kwh?.toString() || '',
          sg_ready: (params.sg_ready as boolean) ?? false,
        }
      case 'wallbox':
        return {
          max_ladeleistung_kw: params.max_ladeleistung_kw?.toString() || '11',
          bidirektional: (params.bidirektional as boolean) ?? false,
          pv_optimiert: (params.pv_optimiert as boolean) ?? true,
        }
      case 'wechselrichter':
        return {
          max_leistung_kw: params.max_leistung_kw?.toString() || '',
          wirkungsgrad_prozent: params.wirkungsgrad_prozent?.toString() || '97',
          hybrid: (params.hybrid as boolean) ?? false,
        }
      case 'pv-module':
        return {
          anzahl_module: params.anzahl_module?.toString() || '',
          modul_leistung_wp: params.modul_leistung_wp?.toString() || '',
          modul_typ: params.modul_typ?.toString() || '',
        }
      case 'balkonkraftwerk':
        return {
          leistung_wp: params.leistung_wp?.toString() || '',
          anzahl: params.anzahl?.toString() || '2',
          ausrichtung: params.ausrichtung?.toString() || 'Süd',
          neigung_grad: params.neigung_grad?.toString() || '30',
          hat_speicher: (params.hat_speicher as boolean) ?? false,
          speicher_kapazitaet_wh: params.speicher_kapazitaet_wh?.toString() || '',
        }
      case 'sonstiges':
        return {
          kategorie: params.kategorie?.toString() || 'erzeuger',
          beschreibung: params.beschreibung?.toString() || '',
        }
      default:
        return {}
    }
  }

  const [paramData, setParamData] = useState<Record<string, string | boolean>>(getInitialParamData)

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

      // Validierung: Parent erforderlich?
      if (isParentRequired && possibleParents.length > 0 && !formData.parent_investition_id) {
        setError(`${typLabels[typ]} müssen einem ${PARENT_TYPE_LABELS[parentTyp!] || parentTyp} zugeordnet werden`)
        return
      }

      // Balkonkraftwerk: leistung_kwp aus Anzahl × Wp berechnen
      let balkonkraftwerkKwp: number | undefined
      let balkonkraftwerkAusrichtung: string | undefined
      let balkonkraftwerkNeigung: number | undefined
      if (typ === 'balkonkraftwerk') {
        const anzahl = parseInt(paramData.anzahl as string) || 0
        const leistungWp = parseInt(paramData.leistung_wp as string) || 0
        if (anzahl > 0 && leistungWp > 0) {
          balkonkraftwerkKwp = (anzahl * leistungWp) / 1000
        }
        balkonkraftwerkAusrichtung = paramData.ausrichtung as string || undefined
        balkonkraftwerkNeigung = paramData.neigung_grad ? parseFloat(paramData.neigung_grad as string) : undefined
      }

      const data: InvestitionCreate | InvestitionUpdate = {
        ...(investition ? {} : { anlage_id: anlageId, typ }),
        bezeichnung: formData.bezeichnung.trim(),
        anschaffungsdatum: formData.anschaffungsdatum || undefined,
        anschaffungskosten_gesamt: formData.anschaffungskosten_gesamt ? parseFloat(formData.anschaffungskosten_gesamt) : undefined,
        anschaffungskosten_alternativ: formData.anschaffungskosten_alternativ ? parseFloat(formData.anschaffungskosten_alternativ) : undefined,
        betriebskosten_jahr: formData.betriebskosten_jahr ? parseFloat(formData.betriebskosten_jahr) : undefined,
        aktiv: formData.aktiv,
        parameter: Object.keys(convertedParams).length > 0 ? convertedParams : undefined,
        // Parent-Zuordnung (PV-Module → Wechselrichter, etc.)
        parent_investition_id: formData.parent_investition_id ? parseInt(formData.parent_investition_id) : undefined,
        // PV-Module spezifische Felder
        ...(typ === 'pv-module' && {
          leistung_kwp: formData.leistung_kwp ? parseFloat(formData.leistung_kwp) : undefined,
          ausrichtung: formData.ausrichtung || undefined,
          neigung_grad: formData.neigung_grad ? parseFloat(formData.neigung_grad) : undefined,
          ha_entity_id: formData.ha_entity_id || undefined,
        }),
        // Balkonkraftwerk: leistung_kwp berechnet, Ausrichtung/Neigung aus Parametern
        ...(typ === 'balkonkraftwerk' && {
          leistung_kwp: balkonkraftwerkKwp,
          ausrichtung: balkonkraftwerkAusrichtung,
          neigung_grad: balkonkraftwerkNeigung,
        }),
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
            min="2000-01-01"
            max="2099-12-31"
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
            hint={alternativkostenHints[typ]}
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

      {/* Parent-Zuordnung (z.B. PV-Module → Wechselrichter) */}
      {parentTyp && (
        <div className="space-y-4">
          <h3 className="text-sm font-medium text-gray-900 dark:text-white">Zuordnung</h3>
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              Gehört zu ({PARENT_TYPE_LABELS[parentTyp] || parentTyp})
              {isParentRequired ? ' *' : ' (optional)'}
              {loadingParents && <span className="text-xs text-gray-400 ml-2">(Laden...)</span>}
            </label>
            {possibleParents.length > 0 ? (
              <>
                <select
                  name="parent_investition_id"
                  value={formData.parent_investition_id}
                  onChange={(e) => setFormData(prev => ({ ...prev, parent_investition_id: e.target.value }))}
                  className={`input w-full ${
                    isParentRequired && !formData.parent_investition_id
                      ? 'border-amber-500 dark:border-amber-500'
                      : ''
                  }`}
                  required={isParentRequired}
                >
                  <option value="">{isParentRequired ? '-- Bitte wählen --' : '-- Keine Zuordnung --'}</option>
                  {possibleParents.map(p => (
                    <option key={p.id} value={p.id}>{p.bezeichnung}</option>
                  ))}
                </select>
                {isParentRequired && !formData.parent_investition_id && (
                  <p className="mt-1 text-sm text-amber-600 dark:text-amber-400 flex items-center gap-1">
                    <AlertCircle className="w-4 h-4" />
                    {typ === 'pv-module' ? 'PV-Module müssen einem Wechselrichter zugeordnet werden' : 'Pflichtfeld'}
                  </p>
                )}
              </>
            ) : !loadingParents ? (
              <div className="p-3 bg-amber-50 dark:bg-amber-900/20 rounded-lg border border-amber-200 dark:border-amber-800">
                <p className="text-sm text-amber-700 dark:text-amber-300 flex items-center gap-2">
                  <AlertCircle className="w-4 h-4 flex-shrink-0" />
                  {isParentRequired ? (
                    <span>
                      Bitte legen Sie zuerst einen <strong>{PARENT_TYPE_LABELS[parentTyp] || parentTyp}</strong> an,
                      bevor Sie {typLabels[typ]} erstellen können.
                    </span>
                  ) : (
                    <span>
                      Kein {PARENT_TYPE_LABELS[parentTyp] || parentTyp} vorhanden.
                      Zuordnung ist optional.
                    </span>
                  )}
                </p>
              </div>
            ) : null}
          </div>
        </div>
      )}

      {/* PV-Module spezifische Felder (direkte Felder, nicht in paramData) */}
      {typ === 'pv-module' && (
        <div className="space-y-4">
          <h3 className="text-sm font-medium text-gray-900 dark:text-white">PV-Modul Parameter</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Input
              label="Leistung (kWp)"
              name="leistung_kwp"
              type="number"
              step="0.1"
              min="0"
              value={formData.leistung_kwp}
              onChange={handleChange}
              required
              hint="Gesamtleistung dieses PV-Moduls/Strings"
            />
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Ausrichtung
              </label>
              <select
                name="ausrichtung"
                value={formData.ausrichtung}
                onChange={(e) => setFormData(prev => ({ ...prev, ausrichtung: e.target.value }))}
                className="input w-full"
              >
                <option value="Süd">Süd (0°)</option>
                <option value="Südost">Südost (-45°)</option>
                <option value="Ost">Ost (-90°)</option>
                <option value="Nordost">Nordost (-135°)</option>
                <option value="Nord">Nord (180°)</option>
                <option value="Nordwest">Nordwest (135°)</option>
                <option value="West">West (90°)</option>
                <option value="Südwest">Südwest (45°)</option>
                <option value="Ost-West">Ost-West (gemischt)</option>
              </select>
            </div>
            <Input
              label="Neigung (Grad)"
              name="neigung_grad"
              type="number"
              step="1"
              min="0"
              max="90"
              value={formData.neigung_grad}
              onChange={handleChange}
              hint="0° = flach, 90° = senkrecht"
            />
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Home Assistant Sensor
                {loadingSensors && <span className="text-xs text-gray-400 ml-2">(Laden...)</span>}
              </label>
              <select
                name="ha_entity_id"
                value={formData.ha_entity_id}
                onChange={(e) => setFormData(prev => ({ ...prev, ha_entity_id: e.target.value }))}
                className="input w-full"
              >
                <option value="">Kein Sensor (manuell)</option>
                {stringSensors.map(sensor => (
                  <option key={sensor.entity_id} value={sensor.entity_id}>
                    {sensor.friendly_name || sensor.entity_id}
                    {sensor.state && ` (${sensor.state} ${sensor.unit_of_measurement || ''})`}
                  </option>
                ))}
              </select>
              <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                Verknüpfe dieses PV-Modul mit einem String-Sensor für automatische IST-Daten
              </p>
            </div>
          </div>
        </div>
      )}

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
          <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mt-4">Vergleich mit Verbrenner</h4>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Input
              label="Verbrenner-Verbrauch (L/100km)"
              name="param_vergleich_verbrauch_l_100km"
              type="number"
              step="0.1"
              min="0"
              value={paramData.vergleich_verbrauch_l_100km as string}
              onChange={onChange}
              hint="Verbrauch des alternativen Verbrenners"
            />
            <Input
              label="Benzinpreis (€/L)"
              name="param_benzinpreis_euro"
              type="number"
              step="0.01"
              min="0"
              value={paramData.benzinpreis_euro as string}
              onChange={onChange}
              hint="Aktueller Benzin/Diesel-Preis"
            />
          </div>
          <label className="flex items-center gap-2 text-sm mt-4">
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
      // PV-Module: Anzahl und Modulleistung für Berechnung kWp = Anzahl × Wp / 1000
      return (
        <div className="space-y-4">
          <h3 className="text-sm font-medium text-gray-900 dark:text-white">
            Modul-Details (optional)
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Input
              label="Anzahl Module"
              name="param_anzahl_module"
              type="number"
              step="1"
              min="1"
              value={paramData.anzahl_module as string}
              onChange={onChange}
              hint="Anzahl der PV-Module in diesem String"
            />
            <Input
              label="Leistung pro Modul (Wp)"
              name="param_modul_leistung_wp"
              type="number"
              step="1"
              min="0"
              value={paramData.modul_leistung_wp as string}
              onChange={onChange}
              hint="z.B. 400 Wp, 500 Wp"
            />
            <Input
              label="Modul-Typ"
              name="param_modul_typ"
              type="text"
              value={paramData.modul_typ as string}
              onChange={onChange}
              placeholder="z.B. Longi Hi-MO 5"
              hint="Hersteller und Modell"
            />
          </div>
          {paramData.anzahl_module && paramData.modul_leistung_wp && (
            <p className="text-xs text-gray-500 dark:text-gray-400">
              Berechnete Leistung: {((parseInt(paramData.anzahl_module as string) || 0) * (parseInt(paramData.modul_leistung_wp as string) || 0) / 1000).toFixed(2)} kWp
            </p>
          )}
        </div>
      )

    case 'balkonkraftwerk':
      const bkwLeistungKwp = ((parseInt(paramData.anzahl as string) || 0) * (parseInt(paramData.leistung_wp as string) || 0) / 1000)
      return (
        <div className="space-y-4">
          <h3 className="text-sm font-medium text-gray-900 dark:text-white">
            Balkonkraftwerk Parameter
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
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
              label="Leistung pro Modul (Wp)"
              name="param_leistung_wp"
              type="number"
              step="1"
              min="0"
              value={paramData.leistung_wp as string}
              onChange={onChange}
              hint={bkwLeistungKwp > 0 ? `= ${bkwLeistungKwp.toFixed(2)} kWp` : undefined}
            />
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Ausrichtung
              </label>
              <select
                name="param_ausrichtung"
                value={paramData.ausrichtung as string}
                onChange={(e) => onChange({ target: { name: 'param_ausrichtung', value: e.target.value, type: 'text' } } as React.ChangeEvent<HTMLInputElement>)}
                className="input w-full"
              >
                <option value="Süd">Süd (0°)</option>
                <option value="Südost">Südost (-45°)</option>
                <option value="Ost">Ost (-90°)</option>
                <option value="Nordost">Nordost (-135°)</option>
                <option value="Nord">Nord (180°)</option>
                <option value="Nordwest">Nordwest (135°)</option>
                <option value="West">West (90°)</option>
                <option value="Südwest">Südwest (45°)</option>
                <option value="Ost-West">Ost-West (gemischt)</option>
              </select>
            </div>
            <Input
              label="Neigung (Grad)"
              name="param_neigung_grad"
              type="number"
              step="1"
              min="0"
              max="90"
              value={paramData.neigung_grad as string}
              onChange={onChange}
              hint="0° = flach, 90° = senkrecht"
            />
          </div>
          <label className="flex items-center gap-2 text-sm mt-4">
            <input
              type="checkbox"
              name="param_hat_speicher"
              checked={paramData.hat_speicher as boolean}
              onChange={onChange}
              className="rounded border-gray-300 text-primary-600 focus:ring-primary-500"
            />
            <span className="text-gray-700 dark:text-gray-300">Mit Speicher (z.B. Anker SOLIX)</span>
          </label>
          {paramData.hat_speicher && (
            <Input
              label="Speicher-Kapazität (Wh)"
              name="param_speicher_kapazitaet_wh"
              type="number"
              step="1"
              min="0"
              value={paramData.speicher_kapazitaet_wh as string}
              onChange={onChange}
              hint="z.B. 1600 Wh für Anker SOLIX"
            />
          )}
        </div>
      )

    case 'sonstiges':
      return (
        <div className="space-y-4">
          <h3 className="text-sm font-medium text-gray-900 dark:text-white">
            Sonstige Investition
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Kategorie
              </label>
              <select
                name="param_kategorie"
                value={paramData.kategorie as string}
                onChange={(e) => onChange({ target: { name: 'param_kategorie', value: e.target.value, type: 'text' } } as React.ChangeEvent<HTMLInputElement>)}
                className="input w-full"
              >
                <option value="erzeuger">Erzeuger (z.B. Mini-BHKW, Mini-Wind)</option>
                <option value="verbraucher">Verbraucher (z.B. Klimaanlage, Pool)</option>
                <option value="speicher">Speicher (z.B. Wasserstoff)</option>
              </select>
              <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                Bestimmt welche Monatsdaten erfasst werden
              </p>
            </div>
            <Input
              label="Beschreibung"
              name="param_beschreibung"
              value={paramData.beschreibung as string}
              onChange={onChange}
              placeholder="z.B. Mini-Blockheizkraftwerk Viessmann"
              hint="Kurze Beschreibung der Investition"
            />
          </div>
        </div>
      )

    default:
      return null
  }
}
