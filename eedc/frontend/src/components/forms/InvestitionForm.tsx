import { useState, useEffect, useRef, FormEvent } from 'react'
import { Button, Input, Select, Alert, DatumFeld, FormSection } from '../ui'
import type { SelectItem } from '../ui/Select'
import type { Investition, InvestitionTyp } from '../../types'
import type { InvestitionCreate, InvestitionUpdate } from '../../api'
import { investitionenApi } from '../../api'
import {
  ausrichtungToGrad,
  gradToAusrichtung,
  AUSRICHTUNG_OPTIONEN,
  PARENT_MAPPING,
  PARENT_REQUIRED,
  PARENT_TYPE_LABELS,
  typLabels,
  alternativkostenHints,
  getInitialParamData,
} from './sections/investitionFormHelpers'
import { SchalterZeile } from './sections/SchalterZeile'
import { InvestitionTypFelder } from './sections/InvestitionTypFelder'
import { InfothekVerknuepfungen } from './sections/InfothekVerknuepfungen'

interface InvestitionFormProps {
  investition?: Investition | null
  anlageId: number
  typ: InvestitionTyp
  onSubmit: (data: InvestitionCreate | InvestitionUpdate) => Promise<void>
  onCancel: () => void
}

export default function InvestitionForm({ investition, anlageId, typ, onSubmit, onCancel }: InvestitionFormProps) {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [possibleParents, setPossibleParents] = useState<Investition[]>([])
  const [loadingParents, setLoadingParents] = useState(false)

  const [formData, setFormData] = useState({
    bezeichnung: investition?.bezeichnung || `Mein ${typLabels[typ]}`,
    anschaffungsdatum: investition?.anschaffungsdatum || '',
    stilllegungsdatum: investition?.stilllegungsdatum || '',
    anschaffungskosten_gesamt: investition?.anschaffungskosten_gesamt?.toString() || '',
    anschaffungskosten_alternativ: investition?.anschaffungskosten_alternativ?.toString() || '',
    betriebskosten_jahr: investition?.betriebskosten_jahr?.toString() || '',
    graue_last_kg: investition?.graue_last_kg?.toString() || '',
    aktiv: investition?.aktiv ?? true,
    parent_investition_id: investition?.parent_investition_id?.toString() || '',
    // PV-Module direkte Felder
    leistung_kwp: investition?.leistung_kwp?.toString() || '',
    ausrichtung: investition?.ausrichtung || 'Süd',
    ausrichtung_grad: investition?.parameter?.ausrichtung_grad?.toString()
      ?? ausrichtungToGrad(investition?.ausrichtung || 'Süd'),
    neigung_grad: investition?.neigung_grad?.toString() || '30',
    ha_entity_id: investition?.ha_entity_id || '',
  })

  const [paramData, setParamData] = useState<Record<string, string | boolean>>(
    () => getInitialParamData(typ, investition?.parameter ?? {}),
  )

  // V1/V2: Inline-Fehler erst nach Berührung (touched) bzw. Absende-Versuch (Muster Slice 1–3).
  const [touched, setTouched] = useState<Set<string>>(new Set())
  const [submitted, setSubmitted] = useState(false)
  const feldRefs = useRef<Record<string, HTMLDivElement | null>>({})
  const setFeldRef = (name: string) => (el: HTMLDivElement | null) => { feldRefs.current[name] = el }
  const markTouched = (name: string) => setTouched(prev => new Set(prev).add(name))

  // Parent-Typ(en) für diesen Investitions-Typ ermitteln
  const parentTypRaw = PARENT_MAPPING[typ]
  const parentTypen: InvestitionTyp[] = parentTypRaw
    ? (Array.isArray(parentTypRaw) ? parentTypRaw : [parentTypRaw])
    : []
  const isParentRequired = PARENT_REQUIRED.includes(typ)
  const parentLabel = parentTypen.map(t => PARENT_TYPE_LABELS[t] || t).join(' / ')

  // Parent-Investitionen laden wenn nötig (alle erlaubten Parent-Typen)
  useEffect(() => {
    if (parentTypen.length === 0) return
    setLoadingParents(true)
    Promise.all(parentTypen.map(t => investitionenApi.list(anlageId, t, true)))
      .then(results => {
        const merged = results.flat().filter(p => p.id !== investition?.id)
        setPossibleParents(merged)
      })
      .catch(() => setPossibleParents([]))
      .finally(() => setLoadingParents(false))
  }, [typ, anlageId, investition?.id])

  // ── Parameter-Setter (Switch/Select/RadioGroup) + Input-Event-Bridge ──
  const applyParam = (paramName: string, value: string | boolean) => {
    setParamData(prev => {
      const next = { ...prev, [paramName]: value }
      // Speicher: Arbitrage impliziert Netzladung — Flag mitziehen, damit das
      // Monatsdaten-Feld `ladung_netz_kwh` sichtbar bleibt.
      if (paramName === 'arbitrage_faehig' && value === true) next.laedt_aus_netz = true
      return next
    })
  }
  const setParam = (name: string, value: string | boolean) => applyParam(name, value)
  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = e.target
    if (name.startsWith('param_')) applyParam(name.slice(6), value)
    else setFormData(prev => ({ ...prev, [name]: value }))
  }

  // ── Validierung (V2): Pflichtfelder in DOM-Reihenfolge ──
  const numFehler = (raw: string): string | undefined => {
    if (!raw) return 'Pflichtfeld'
    const n = parseFloat(raw)
    if (Number.isNaN(n) || n <= 0) return 'Bitte einen gültigen Wert eingeben'
    return undefined
  }
  const requiredParamNames = (): string[] => {
    if (typ !== 'waermepumpe') return []
    const m = paramData.effizienz_modus
    if (m === 'gesamt_jaz') return ['jaz']
    if (m === 'scop') return ['scop_heizung', 'scop_warmwasser']
    if (m === 'getrennte_cops') return ['cop_heizung', 'cop_warmwasser']
    return []
  }
  const pflichtFelder = (): { name: string; fehler: string | undefined }[] => {
    const list = [{
      name: 'bezeichnung',
      fehler: formData.bezeichnung.trim() ? undefined : 'Bitte eine Bezeichnung eingeben',
    }]
    if (isParentRequired && possibleParents.length > 0) {
      list.push({
        name: 'parent',
        fehler: formData.parent_investition_id ? undefined : 'PV-Module müssen einem Wechselrichter zugeordnet werden',
      })
    }
    if (typ === 'pv-module') {
      list.push({ name: 'leistung_kwp', fehler: numFehler(formData.leistung_kwp) })
    }
    for (const n of requiredParamNames()) {
      list.push({ name: n, fehler: numFehler((paramData[n] as string) ?? '') })
    }
    return list
  }
  const fehlerMap: Record<string, string | undefined> = Object.fromEntries(
    pflichtFelder().map(p => [p.name, p.fehler]),
  )
  const zeige = (name: string): string | undefined =>
    (submitted || touched.has(name)) ? fehlerMap[name] : undefined

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    setSubmitted(true)

    const ersterFehler = pflichtFelder().find(p => p.fehler)
    if (ersterFehler) {
      feldRefs.current[ersterFehler.name]?.scrollIntoView({ behavior: 'smooth', block: 'center' })
      return
    }

    try {
      setLoading(true)

      // Parameter konvertieren
      const dateFields: string[] = []
      const convertedParams: Record<string, unknown> = {}
      Object.entries(paramData).forEach(([key, value]) => {
        if (typeof value === 'boolean') {
          convertedParams[key] = value
        } else if (value !== '') {
          // Datumsfelder als String behalten
          if (dateFields.includes(key)) {
            convertedParams[key] = value
          } else {
            if (value === 'true') {
              convertedParams[key] = true
            } else if (value === 'false') {
              convertedParams[key] = false
            } else {
              const num = parseFloat(value)
              convertedParams[key] = isNaN(num) ? value : num
            }
          }
        }
      })

      // PV-Module: exakten Azimut-Grad in parameter JSON speichern
      if (typ === 'pv-module' && formData.ausrichtung !== 'Ost-West') {
        const gradNum = parseFloat(formData.ausrichtung_grad)
        if (!isNaN(gradNum)) {
          convertedParams.ausrichtung_grad = gradNum
        }
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
        stilllegungsdatum: formData.stilllegungsdatum || undefined,
        anschaffungskosten_gesamt: formData.anschaffungskosten_gesamt ? parseFloat(formData.anschaffungskosten_gesamt) : undefined,
        anschaffungskosten_alternativ: formData.anschaffungskosten_alternativ ? parseFloat(formData.anschaffungskosten_alternativ) : undefined,
        betriebskosten_jahr: formData.betriebskosten_jahr ? parseFloat(formData.betriebskosten_jahr) : undefined,
        graue_last_kg: formData.graue_last_kg ? parseFloat(formData.graue_last_kg) : undefined,
        aktiv: formData.aktiv,
        // Wizard-only-Keys (von sensor_mapping.py oder anderen Pfaden in parameter
        // geschrieben) mit existing parameter mergen — sonst löscht jeder Form-Save
        // unsichtbare Felder.
        parameter: Object.keys(convertedParams).length > 0
          ? { ...(investition?.parameter ?? {}), ...convertedParams }
          : undefined,
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

  // Parent-Auswahl (Select-SoT): Optionen aus möglichen Eltern-Investitionen.
  const parentOptionen: SelectItem[] = possibleParents.map(p => ({ value: String(p.id), label: p.bezeichnung }))

  return (
    <form onSubmit={handleSubmit} className="space-y-4" noValidate>
      {error && <Alert type="error">{error}</Alert>}

      {/* ── Kern: Allgemein ── */}
      <FormSection title="Allgemein">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 items-start">
          <div ref={setFeldRef('bezeichnung')}>
            <Input
              label="Bezeichnung"
              name="bezeichnung"
              value={formData.bezeichnung}
              onChange={handleInputChange}
              onBlur={() => markTouched('bezeichnung')}
              required
              error={zeige('bezeichnung')}
            />
          </div>
          <DatumFeld
            label="Anschaffungsdatum"
            value={formData.anschaffungsdatum}
            onChange={(v) => setFormData(prev => ({ ...prev, anschaffungsdatum: v }))}
          />
          <Input
            label="Anschaffungskosten (€)"
            name="anschaffungskosten_gesamt"
            type="number" step="0.01" min="0"
            value={formData.anschaffungskosten_gesamt}
            onChange={handleInputChange}
            hint="Gesamtkosten inkl. Installation"
          />
        </div>
      </FormSection>

      {/* ── Erweitert: Weitere Angaben & Kosten ── */}
      <FormSection variant="erweitert" title="Weitere Angaben & Kosten">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 items-start">
          <DatumFeld
            label="Stilllegungsdatum (optional)"
            min={formData.anschaffungsdatum || '2000-01-01'}
            value={formData.stilllegungsdatum}
            onChange={(v) => setFormData(prev => ({ ...prev, stilllegungsdatum: v }))}
            hint="Ab diesem Datum zählt die Komponente nicht mehr für Live/Prognose. Historische Werte bleiben erhalten."
          />
          <Input
            label="Alternative Kosten (€)"
            name="anschaffungskosten_alternativ"
            type="number" step="0.01" min="0"
            value={formData.anschaffungskosten_alternativ}
            onChange={handleInputChange}
            hint={alternativkostenHints[typ]}
          />
          <Input
            label="Betriebskosten/Jahr (€)"
            name="betriebskosten_jahr"
            type="number" step="0.01" min="0"
            value={formData.betriebskosten_jahr}
            onChange={handleInputChange}
            hint="Wartung, Versicherung, etc."
          />
          <Input
            label="Graue CO2-Last (kg)"
            name="graue_last_kg"
            type="number" step="1" min="0"
            value={formData.graue_last_kg}
            onChange={handleInputChange}
            hint="Herstellungs-CO2 (Datenblatt). Leer = Richtwert nach Typ/Größe (PV 1000 kg/kWp, Speicher 85 kg/kWh, WP 1100 kg, E-Auto 5000 kg)."
          />
        </div>
        <div className="mt-4">
          <SchalterZeile
            checked={formData.aktiv}
            onChange={(an) => setFormData(prev => ({ ...prev, aktiv: an }))}
            label="Aktiv (in Berechnungen berücksichtigen)"
          />
        </div>
      </FormSection>

      {/* ── Kern: Zuordnung (z.B. PV-Module → Wechselrichter) ── */}
      {parentTypen.length > 0 && (
        <FormSection title="Zuordnung">
          {possibleParents.length > 0 ? (
            <div ref={setFeldRef('parent')}>
              <Select
                label={`Gehört zu (${parentLabel})${isParentRequired ? '' : ' (optional)'}`}
                name="parent_investition_id"
                value={formData.parent_investition_id}
                onChange={(e) => setFormData(prev => ({ ...prev, parent_investition_id: e.target.value }))}
                onBlur={() => markTouched('parent')}
                options={parentOptionen}
                placeholder={isParentRequired ? '-- Bitte wählen --' : '-- Keine Zuordnung --'}
                required={isParentRequired}
                error={zeige('parent')}
                hint={loadingParents ? 'Laden…' : undefined}
              />
            </div>
          ) : !loadingParents ? (
            <Alert type="warning">
              {isParentRequired ? (
                <>Bitte legen Sie zuerst einen <strong>{parentLabel}</strong> an, bevor Sie {typLabels[typ]} erstellen können.</>
              ) : (
                <>Kein {parentLabel} vorhanden. Zuordnung ist optional.</>
              )}
            </Alert>
          ) : (
            <p className="text-xs text-gray-400 dark:text-gray-500">Laden…</p>
          )}
        </FormSection>
      )}

      {/* ── Kern: PV-Modul-Parameter (direkte Felder, nicht in paramData) ── */}
      {typ === 'pv-module' && (
        <FormSection title="PV-Modul-Parameter">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 items-start">
            <div ref={setFeldRef('leistung_kwp')}>
              <Input
                label="Leistung (kWp)"
                name="leistung_kwp"
                type="number" step="0.01" min="0"
                value={formData.leistung_kwp}
                onChange={handleInputChange}
                onBlur={() => markTouched('leistung_kwp')}
                required
                error={zeige('leistung_kwp')}
                hint="Gesamtleistung dieses PV-Moduls/Strings"
              />
            </div>
            <Select
              label="Ausrichtung"
              name="ausrichtung"
              value={formData.ausrichtung}
              onChange={(e) => {
                const val = e.target.value
                setFormData(prev => ({
                  ...prev,
                  ausrichtung: val,
                  ...(val !== 'Ost-West' && { ausrichtung_grad: ausrichtungToGrad(val) }),
                }))
              }}
              options={AUSRICHTUNG_OPTIONEN}
            />
            {formData.ausrichtung !== 'Ost-West' && (
              <Input
                label="Azimut (°)"
                name="ausrichtung_grad"
                type="number" step="1" min="-180" max="180"
                value={formData.ausrichtung_grad}
                onChange={(e) => {
                  const gradValue = e.target.value
                  const gradNum = parseFloat(gradValue)
                  setFormData(prev => ({
                    ...prev,
                    ausrichtung_grad: gradValue,
                    ...(!isNaN(gradNum) && { ausrichtung: gradToAusrichtung(gradNum) }),
                  }))
                }}
                hint="0=Süd, -90=Ost, 90=West, ±180=Nord"
              />
            )}
            <Input
              label="Neigung (Grad)"
              name="neigung_grad"
              type="number" step="1" min="0" max="90"
              value={formData.neigung_grad}
              onChange={handleInputChange}
              hint="0° = flach, 90° = senkrecht"
            />
          </div>
        </FormSection>
      )}

      {/* ── Typ-spezifische Parameter ── */}
      <InvestitionTypFelder
        typ={typ}
        paramData={paramData}
        onInputChange={handleInputChange}
        setParam={setParam}
        zeige={zeige}
        markTouched={markTouched}
        setFeldRef={setFeldRef}
      />

      {/* ── Verknüpfte Infothek-Einträge (nur beim Bearbeiten) ── */}
      {investition && <InfothekVerknuepfungen investitionId={investition.id} />}

      {/* ── Actions ── */}
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
