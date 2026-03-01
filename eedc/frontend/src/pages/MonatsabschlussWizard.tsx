/**
 * MonatsabschlussWizard - Geführte monatliche Dateneingabe
 *
 * Features:
 * - Vorschläge aus verschiedenen Quellen
 * - Plausibilitätsprüfungen
 * - Integration mit Sensor-Mapping
 */

import { useState, useEffect, useMemo } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import {
  ChevronLeft,
  ChevronRight,
  Save,
  AlertTriangle,
  CheckCircle,
  Info,
  Calendar,
  Zap,
  Sun,
  Battery,
  Thermometer,
  Car,
  Settings,
  Loader2,
  FileText,
  Database,
  Wrench,
} from 'lucide-react'
import { anlagenApi, monatsabschlussApi, haStatisticsApi } from '../api'
import type {
  MonatsabschlussResponse,
  FeldStatus,
  InvestitionStatus,
  MonatsabschlussInput,
  FeldWert,
  SonstigePosition,
} from '../api'
import Alert from '../components/ui/Alert'
import SonstigePositionenFields from '../components/forms/SonstigePositionenFields'
import { useHAAvailable } from '../hooks/useHAAvailable'

const MONAT_NAMEN = [
  '', 'Januar', 'Februar', 'März', 'April', 'Mai', 'Juni',
  'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember'
]

const TYP_ICONS: Record<string, React.ReactNode> = {
  'pv-module': <Sun className="w-5 h-5" />,
  speicher: <Battery className="w-5 h-5" />,
  waermepumpe: <Thermometer className="w-5 h-5" />,
  'e-auto': <Car className="w-5 h-5" />,
  wallbox: <Zap className="w-5 h-5" />,
  balkonkraftwerk: <Sun className="w-5 h-5" />,
  sonstiges: <Wrench className="w-5 h-5" />,
}

interface WizardState {
  basis: Record<string, number | null>
  optionale: Record<string, number | string | null>  // Sonderkosten, Notizen
  investitionen: Record<number, Record<string, number | null>>
  sonstigePositionen: Record<number, SonstigePosition[]>
}

export default function MonatsabschlussWizard() {
  const { anlageId, jahr, monat } = useParams<{
    anlageId?: string
    jahr?: string
    monat?: string
  }>()
  const navigate = useNavigate()
  const haAvailable = useHAAvailable()

  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [loadingHA, setLoadingHA] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)
  const [haInfo, setHaInfo] = useState<string | null>(null)

  const [anlageName, setAnlageName] = useState('')
  const [data, setData] = useState<MonatsabschlussResponse | null>(null)
  const [currentStep, setCurrentStep] = useState(0)
  const [values, setValues] = useState<WizardState>({
    basis: {},
    optionale: {},
    investitionen: {},
    sonstigePositionen: {},
  })

  // Jahr und Monat aus URL oder automatisch ermitteln
  // WICHTIG: getMonth() gibt 0-11 zurück, aber API erwartet 1-12
  const [selectedJahr, setSelectedJahr] = useState<number>(
    jahr ? parseInt(jahr) : new Date().getFullYear()
  )
  const [selectedMonat, setSelectedMonat] = useState<number>(
    monat ? parseInt(monat) : new Date().getMonth() + 1
  )

  // Daten laden
  useEffect(() => {
    const loadData = async () => {
      if (!anlageId) {
        // Erste Anlage laden
        try {
          const anlagen = await anlagenApi.list()
          if (anlagen.length > 0) {
            navigate(`/monatsabschluss/${anlagen[0].id}`)
          } else {
            setError('Keine Anlage gefunden')
          }
        } catch {
          setError('Fehler beim Laden der Anlagen')
        }
        setLoading(false)
        return
      }

      setLoading(true)
      setError(null)

      try {
        // Wenn kein Jahr/Monat in URL, nächsten unvollständigen Monat finden
        let targetJahr = selectedJahr
        let targetMonat = selectedMonat

        if (!jahr || !monat) {
          const naechster = await monatsabschlussApi.getNaechsterMonat(parseInt(anlageId))
          if (naechster) {
            targetJahr = naechster.jahr
            targetMonat = naechster.monat
            setSelectedJahr(targetJahr)
            setSelectedMonat(targetMonat)
          }
        }

        const response = await monatsabschlussApi.getStatus(
          parseInt(anlageId),
          targetJahr,
          targetMonat
        )
        setData(response)
        setAnlageName(response.anlage_name)

        // Werte aus aktuellen Daten initialisieren
        const basisValues: Record<string, number | null> = {}
        for (const feld of response.basis_felder) {
          basisValues[feld.feld] = feld.aktueller_wert
        }

        // Optionale Felder (Sonderkosten, Notizen)
        const optionaleValues: Record<string, number | string | null> = {}
        for (const feld of response.optionale_felder || []) {
          if (feld.typ === 'text') {
            optionaleValues[feld.feld] = feld.aktueller_text
          } else {
            optionaleValues[feld.feld] = feld.aktueller_wert
          }
        }

        const invValues: Record<number, Record<string, number | null>> = {}
        const invSonstigePos: Record<number, SonstigePosition[]> = {}
        for (const inv of response.investitionen) {
          invValues[inv.id] = {}
          for (const feld of inv.felder) {
            invValues[inv.id][feld.feld] = feld.aktueller_wert
          }
          invSonstigePos[inv.id] = inv.sonstige_positionen || []
        }

        setValues({
          basis: basisValues,
          optionale: optionaleValues,
          investitionen: invValues,
          sonstigePositionen: invSonstigePos,
        })
      } catch (e) {
        setError('Fehler beim Laden der Monatsdaten')
        console.error(e)
      } finally {
        setLoading(false)
      }
    }

    loadData()
  }, [anlageId, jahr, monat, selectedJahr, selectedMonat, navigate])

  // Step-Typ für TypeScript
  interface WizardStep {
    id: string
    title: string
    icon: React.ReactNode
  }

  // Steps dynamisch generieren
  const steps = useMemo((): WizardStep[] => {
    if (!data) return []

    const s: WizardStep[] = [
      { id: 'basis', title: 'Zählerdaten', icon: <Zap className="w-4 h-4" /> }
    ]

    // Pro Investitionstyp einen Step
    const typGroups: Record<string, InvestitionStatus[]> = {}
    for (const inv of data.investitionen) {
      if (!typGroups[inv.typ]) typGroups[inv.typ] = []
      typGroups[inv.typ].push(inv)
    }

    for (const typ of Object.keys(typGroups)) {
      s.push({
        id: typ,
        title: getTypLabel(typ),
        icon: TYP_ICONS[typ] || <Zap className="w-4 h-4" />,
      })
    }

    // Optionale Felder Step (Sonderkosten, Notizen)
    if (data.optionale_felder && data.optionale_felder.length > 0) {
      s.push({ id: 'optionale', title: 'Sonstiges', icon: <FileText className="w-4 h-4" /> })
    }

    s.push({ id: 'summary', title: 'Zusammenfassung', icon: <CheckCircle className="w-4 h-4" /> })

    return s
  }, [data])

  const handleValueChange = (
    feld: string,
    wert: number | null,
    investitionId?: number
  ) => {
    if (investitionId) {
      setValues(prev => ({
        ...prev,
        investitionen: {
          ...prev.investitionen,
          [investitionId]: {
            ...prev.investitionen[investitionId],
            [feld]: wert,
          },
        },
      }))
    } else {
      setValues(prev => ({
        ...prev,
        basis: {
          ...prev.basis,
          [feld]: wert,
        },
      }))
    }
  }

  const handleOptionalChange = (feld: string, wert: number | string | null) => {
    setValues(prev => ({
      ...prev,
      optionale: {
        ...prev.optionale,
        [feld]: wert,
      },
    }))
  }

  // HA-Werte für diesen Monat laden
  const handleLoadHAValues = async () => {
    if (!anlageId) return

    setLoadingHA(true)
    setError(null)
    setHaInfo(null)

    try {
      // Prüfen ob HA verfügbar
      const status = await haStatisticsApi.getStatus()
      if (!status.verfuegbar) {
        setError('Home Assistant Datenbank nicht verfügbar')
        return
      }

      // Monatswerte laden
      const monatswerte = await haStatisticsApi.getMonatswerte(
        parseInt(anlageId),
        selectedJahr,
        selectedMonat
      )

      // Werte in State übernehmen
      let geladenCount = 0

      // Basis-Felder
      const newBasis = { ...values.basis }
      for (const feld of monatswerte.basis) {
        if (feld.wert !== null && feld.wert !== undefined) {
          newBasis[feld.feld] = feld.wert
          geladenCount++
        }
      }

      // Investitionen
      const newInv = { ...values.investitionen }
      for (const inv of monatswerte.investitionen) {
        if (!newInv[inv.investition_id]) {
          newInv[inv.investition_id] = {}
        }
        for (const feld of inv.felder) {
          if (feld.wert !== null && feld.wert !== undefined) {
            newInv[inv.investition_id][feld.feld] = feld.wert
            geladenCount++
          }
        }
      }

      setValues(prev => ({
        ...prev,
        basis: newBasis,
        investitionen: newInv,
      }))

      setHaInfo(`${geladenCount} Werte aus HA-Statistik geladen`)
    } catch (e) {
      console.error(e)
      setError('Fehler beim Laden der HA-Werte. Ist das Sensor-Mapping konfiguriert?')
    } finally {
      setLoadingHA(false)
    }
  }

  const handleSave = async () => {
    if (!data || !anlageId) return

    setSaving(true)
    setError(null)
    setSuccess(null)

    try {
      const input: MonatsabschlussInput = {
        einspeisung_kwh: values.basis.einspeisung_kwh,
        netzbezug_kwh: values.basis.netzbezug_kwh,
        // direktverbrauch_kwh wird automatisch berechnet (PV - Einspeisung)
        globalstrahlung_kwh_m2: values.basis.globalstrahlung_kwh_m2,
        sonnenstunden: values.basis.sonnenstunden,
        durchschnittstemperatur: values.basis.durchschnittstemperatur,
        // Optionale Felder
        sonderkosten_euro: typeof values.optionale.sonderkosten_euro === 'number'
          ? values.optionale.sonderkosten_euro
          : null,
        sonderkosten_beschreibung: typeof values.optionale.sonderkosten_beschreibung === 'string'
          ? values.optionale.sonderkosten_beschreibung
          : null,
        notizen: typeof values.optionale.notizen === 'string'
          ? values.optionale.notizen
          : null,
        investitionen: [],
      }

      // Investitionen zusammenstellen
      for (const inv of data.investitionen) {
        const felder: FeldWert[] = []
        const invValues = values.investitionen[inv.id] || {}

        for (const [feld, wert] of Object.entries(invValues)) {
          if (wert !== null && wert !== undefined) {
            felder.push({ feld, wert })
          }
        }

        const positionen = values.sonstigePositionen[inv.id] || []
        const gueltigePositionen = positionen.filter(p => p.betrag > 0 && p.bezeichnung.trim())

        if (felder.length > 0 || gueltigePositionen.length > 0) {
          input.investitionen.push({
            investition_id: inv.id,
            felder,
            sonstige_positionen: gueltigePositionen.length > 0 ? gueltigePositionen : null,
          })
        }
      }

      const result = await monatsabschlussApi.save(
        parseInt(anlageId),
        selectedJahr,
        selectedMonat,
        input
      )

      if (result.success) {
        setSuccess(result.message)
        // Nach 2s zur nächsten Seite navigieren
        setTimeout(() => {
          navigate('/einstellungen/monatsdaten')
        }, 2000)
      } else {
        setError('Speichern fehlgeschlagen')
      }
    } catch (e) {
      setError('Fehler beim Speichern')
      console.error(e)
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="w-8 h-8 animate-spin text-primary-500" />
      </div>
    )
  }

  if (error && !data) {
    return (
      <div className="max-w-2xl mx-auto p-6">
        <Alert type="error">{error}</Alert>
      </div>
    )
  }

  if (!data) {
    return (
      <div className="max-w-2xl mx-auto p-6">
        <Alert type="info">Keine Daten verfügbar</Alert>
      </div>
    )
  }

  return (
    <div className="max-w-4xl mx-auto p-6">
      {/* Header */}
      <div className="mb-8">
        <div className="flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400 mb-2">
          <Calendar className="w-4 h-4" />
          <span>{anlageName}</span>
        </div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
          Monatsabschluss {MONAT_NAMEN[selectedMonat]} {selectedJahr}
        </h1>

        {/* HA-Mapping Hinweis oder HA-Laden Button */}
        {!data.ha_mapping_konfiguriert ? (
          haAvailable && (
            <Alert type="info" className="mt-4">
              <div className="flex items-center justify-between">
                <span>
                  Home Assistant Sensor-Zuordnung nicht konfiguriert.
                  Werte müssen manuell eingegeben werden.
                </span>
                <Link
                  to={`/einstellungen/sensor-mapping?anlageId=${anlageId}`}
                  className="flex items-center gap-1 text-primary-600 hover:underline"
                >
                  <Settings className="w-4 h-4" />
                  Konfigurieren
                </Link>
              </div>
            </Alert>
          )
        ) : (
          <div className="mt-4 flex items-center gap-4">
            <button
              onClick={handleLoadHAValues}
              disabled={loadingHA}
              className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 text-sm"
            >
              {loadingHA ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  Lade HA-Werte...
                </>
              ) : (
                <>
                  <Database className="w-4 h-4" />
                  Werte aus HA-Statistik laden
                </>
              )}
            </button>
            {haInfo && (
              <span className="text-sm text-green-600 dark:text-green-400">
                {haInfo}
              </span>
            )}
          </div>
        )}
      </div>

      {/* Step Navigation */}
      <div className="mb-8">
        <div className="flex items-center justify-between">
          {steps.map((step, idx) => (
            <button
              key={step.id}
              onClick={() => setCurrentStep(idx)}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg transition-colors ${
                currentStep === idx
                  ? 'bg-primary-100 text-primary-700 dark:bg-primary-900/50 dark:text-primary-300'
                  : 'text-gray-500 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-700'
              }`}
            >
              {step.icon}
              <span className="hidden sm:inline">{step.title}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Alerts */}
      {error && <Alert type="error" className="mb-6">{error}</Alert>}
      {success && <Alert type="success" className="mb-6">{success}</Alert>}

      {/* Step Content */}
      <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6 mb-8">
        {currentStep === 0 && (
          <BasisStep
            felder={data.basis_felder}
            values={values.basis}
            onChange={(feld, wert) => handleValueChange(feld, wert)}
          />
        )}

        {currentStep > 0 && currentStep < steps.length - 1 && steps[currentStep].id !== 'optionale' && (
          <InvestitionStep
            typ={steps[currentStep].id}
            investitionen={data.investitionen.filter(i => i.typ === steps[currentStep].id)}
            values={values.investitionen}
            onChange={(invId, feld, wert) => handleValueChange(feld, wert, invId)}
            sonstigePositionen={values.sonstigePositionen}
            onSonstigePositionenChange={(invId, pos) =>
              setValues(prev => ({
                ...prev,
                sonstigePositionen: { ...prev.sonstigePositionen, [invId]: pos },
              }))
            }
          />
        )}

        {steps[currentStep].id === 'optionale' && (
          <OptionaleStep
            felder={data.optionale_felder || []}
            values={values.optionale}
            onChange={handleOptionalChange}
          />
        )}

        {currentStep === steps.length - 1 && (
          <SummaryStep
            data={data}
            values={values}
          />
        )}
      </div>

      {/* Navigation Buttons */}
      <div className="flex items-center justify-between">
        <button
          onClick={() => setCurrentStep(s => Math.max(0, s - 1))}
          disabled={currentStep === 0}
          className="flex items-center gap-2 px-4 py-2 text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <ChevronLeft className="w-4 h-4" />
          Zurück
        </button>

        {currentStep < steps.length - 1 ? (
          <button
            onClick={() => setCurrentStep(s => Math.min(steps.length - 1, s + 1))}
            className="flex items-center gap-2 px-6 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700"
          >
            Weiter
            <ChevronRight className="w-4 h-4" />
          </button>
        ) : (
          <button
            onClick={handleSave}
            disabled={saving}
            className="flex items-center gap-2 px-6 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50"
          >
            {saving ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                Speichern...
              </>
            ) : (
              <>
                <Save className="w-4 h-4" />
                Speichern
              </>
            )}
          </button>
        )}
      </div>
    </div>
  )
}

// =============================================================================
// Step Components
// =============================================================================

function BasisStep({
  felder,
  values,
  onChange,
}: {
  felder: FeldStatus[]
  values: Record<string, number | null>
  onChange: (feld: string, wert: number | null) => void
}) {
  // Nur die wichtigsten Felder anzeigen
  // direktverbrauch_kwh wird automatisch berechnet (PV - Einspeisung), daher nicht hier
  const wichtigeFelder = ['einspeisung_kwh', 'netzbezug_kwh']
  const wetterdatenFelder = ['globalstrahlung_kwh_m2', 'sonnenstunden', 'durchschnittstemperatur']

  return (
    <div className="space-y-6">
      <h2 className="text-lg font-semibold text-gray-900 dark:text-white flex items-center gap-2">
        <Zap className="w-5 h-5 text-amber-500" />
        Zählerdaten
      </h2>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {felder
          .filter(f => wichtigeFelder.includes(f.feld))
          .map(feld => (
            <FeldInput
              key={feld.feld}
              feld={feld}
              value={values[feld.feld]}
              onChange={(wert) => onChange(feld.feld, wert)}
            />
          ))}
      </div>

      {/* Wetterdaten (optional) */}
      <details className="mt-6">
        <summary className="cursor-pointer text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white">
          Wetterdaten (optional)
        </summary>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mt-4">
          {felder
            .filter(f => wetterdatenFelder.includes(f.feld))
            .map(feld => (
              <FeldInput
                key={feld.feld}
                feld={feld}
                value={values[feld.feld]}
                onChange={(wert) => onChange(feld.feld, wert)}
                compact
              />
            ))}
        </div>
      </details>
    </div>
  )
}

function OptionaleStep({
  felder,
  values,
  onChange,
}: {
  felder: FeldStatus[]
  values: Record<string, number | string | null>
  onChange: (feld: string, wert: number | string | null) => void
}) {
  return (
    <div className="space-y-6">
      <h2 className="text-lg font-semibold text-gray-900 dark:text-white flex items-center gap-2">
        <FileText className="w-5 h-5 text-gray-500" />
        Sonstiges
      </h2>
      <p className="text-sm text-gray-500 dark:text-gray-400">
        Optionale Eingaben für diesen Monat - können auch leer bleiben.
      </p>

      <div className="space-y-4">
        {felder.map(feld => (
          <div key={feld.feld} className="space-y-2">
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
              {feld.label}
              {feld.einheit && <span className="text-gray-400 ml-1">({feld.einheit})</span>}
            </label>

            {feld.typ === 'text' ? (
              <textarea
                value={(values[feld.feld] as string) || ''}
                onChange={(e) => onChange(feld.feld, e.target.value || null)}
                rows={3}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 dark:bg-gray-700 dark:border-gray-600 dark:text-white"
                placeholder={feld.label}
              />
            ) : (
              <input
                type="number"
                step="0.01"
                value={values[feld.feld] ?? ''}
                onChange={(e) => onChange(feld.feld, e.target.value ? parseFloat(e.target.value) : null)}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 dark:bg-gray-700 dark:border-gray-600 dark:text-white"
                placeholder={feld.label}
              />
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

function InvestitionStep({
  typ,
  investitionen,
  values,
  onChange,
  sonstigePositionen,
  onSonstigePositionenChange,
}: {
  typ: string
  investitionen: InvestitionStatus[]
  values: Record<number, Record<string, number | null>>
  onChange: (invId: number, feld: string, wert: number | null) => void
  sonstigePositionen: Record<number, SonstigePosition[]>
  onSonstigePositionenChange: (invId: number, positionen: SonstigePosition[]) => void
}) {
  return (
    <div className="space-y-6">
      <h2 className="text-lg font-semibold text-gray-900 dark:text-white flex items-center gap-2">
        {TYP_ICONS[typ]}
        {getTypLabel(typ)}
      </h2>

      {investitionen.map(inv => (
        <div
          key={inv.id}
          className="border border-gray-200 dark:border-gray-700 rounded-xl overflow-hidden"
        >
          <div className="px-4 py-3 bg-gray-50 dark:bg-gray-700/50">
            <h3 className="font-medium text-gray-900 dark:text-white">
              {inv.bezeichnung}
              {inv.kategorie && (
                <span className="ml-2 text-xs font-normal text-gray-500 dark:text-gray-400">
                  ({inv.kategorie})
                </span>
              )}
            </h3>
          </div>
          <div className="p-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {inv.felder.map(feld => (
                <FeldInput
                  key={feld.feld}
                  feld={feld}
                  value={values[inv.id]?.[feld.feld]}
                  onChange={(wert) => onChange(inv.id, feld.feld, wert)}
                />
              ))}
            </div>
            <SonstigePositionenFields
              positionen={sonstigePositionen[inv.id] || []}
              onChange={(pos) => onSonstigePositionenChange(inv.id, pos)}
            />
          </div>
        </div>
      ))}
    </div>
  )
}

function SummaryStep({
  data,
  values,
}: {
  data: MonatsabschlussResponse
  values: WizardState
}) {
  // Statistiken berechnen
  let gefuellt = 0
  let gesamt = 0

  for (const feld of data.basis_felder) {
    // direktverbrauch_kwh wird automatisch berechnet, daher nicht zählen
    if (['einspeisung_kwh', 'netzbezug_kwh'].includes(feld.feld)) {
      gesamt++
      if (values.basis[feld.feld] !== null && values.basis[feld.feld] !== undefined) {
        gefuellt++
      }
    }
  }

  for (const inv of data.investitionen) {
    for (const feld of inv.felder) {
      gesamt++
      if (values.investitionen[inv.id]?.[feld.feld] !== null &&
          values.investitionen[inv.id]?.[feld.feld] !== undefined) {
        gefuellt++
      }
    }
  }

  return (
    <div className="space-y-6">
      <h2 className="text-lg font-semibold text-gray-900 dark:text-white flex items-center gap-2">
        <CheckCircle className="w-5 h-5 text-green-500" />
        Zusammenfassung
      </h2>

      {/* Statistik */}
      <div className="bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg p-4">
        <div className="flex items-center gap-2">
          <CheckCircle className="w-5 h-5 text-green-600 dark:text-green-400" />
          <span className="font-medium text-green-800 dark:text-green-200">
            {gefuellt} von {gesamt} Feldern ausgefüllt
          </span>
        </div>
      </div>

      {/* Basis-Werte */}
      <div className="border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden">
        <div className="px-4 py-3 bg-gray-50 dark:bg-gray-700/50">
          <h3 className="font-medium text-gray-900 dark:text-white">Zählerdaten</h3>
        </div>
        <div className="divide-y divide-gray-100 dark:divide-gray-700">
          {data.basis_felder
            .filter(f => ['einspeisung_kwh', 'netzbezug_kwh'].includes(f.feld))
            .map(feld => (
              <SummaryRow
                key={feld.feld}
                label={feld.label}
                wert={values.basis[feld.feld]}
                einheit={feld.einheit}
              />
            ))}
        </div>
      </div>

      {/* Investitionen */}
      {data.investitionen.map(inv => (
        <div
          key={inv.id}
          className="border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden"
        >
          <div className="px-4 py-3 bg-gray-50 dark:bg-gray-700/50 flex items-center gap-2">
            {TYP_ICONS[inv.typ]}
            <h3 className="font-medium text-gray-900 dark:text-white">{inv.bezeichnung}</h3>
          </div>
          <div className="divide-y divide-gray-100 dark:divide-gray-700">
            {inv.felder.map(feld => (
              <SummaryRow
                key={feld.feld}
                label={feld.label}
                wert={values.investitionen[inv.id]?.[feld.feld]}
                einheit={feld.einheit}
              />
            ))}
          </div>
        </div>
      ))}

      {/* Optionale Felder */}
      {data.optionale_felder && data.optionale_felder.length > 0 && (
        <div className="border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden">
          <div className="px-4 py-3 bg-gray-50 dark:bg-gray-700/50 flex items-center gap-2">
            <FileText className="w-5 h-5 text-gray-500" />
            <h3 className="font-medium text-gray-900 dark:text-white">Sonstiges</h3>
          </div>
          <div className="divide-y divide-gray-100 dark:divide-gray-700">
            {data.optionale_felder.map(feld => (
              <SummaryRow
                key={feld.feld}
                label={feld.label}
                wert={feld.typ === 'text'
                  ? (values.optionale[feld.feld] as string)
                  : (values.optionale[feld.feld] as number)}
                einheit={feld.einheit}
                isText={feld.typ === 'text'}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

// =============================================================================
// Helper Components
// =============================================================================

function FeldInput({
  feld,
  value,
  onChange,
  compact = false,
}: {
  feld: FeldStatus
  value: number | null | undefined
  onChange: (wert: number | null) => void
  compact?: boolean
}) {
  const hasWarnings = feld.warnungen.length > 0
  const hasVorschlaege = feld.vorschlaege.length > 0

  return (
    <div className={compact ? '' : 'space-y-2'}>
      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
        {feld.label}
        <span className="text-gray-400 ml-1">({feld.einheit})</span>
      </label>

      <div className="relative">
        <input
          type="number"
          step="0.01"
          value={value ?? ''}
          onChange={(e) => onChange(e.target.value ? parseFloat(e.target.value) : null)}
          className={`w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-primary-500 dark:bg-gray-700 dark:border-gray-600 dark:text-white ${
            hasWarnings
              ? 'border-amber-300 focus:border-amber-500'
              : 'border-gray-300'
          }`}
          placeholder={hasVorschlaege ? `Vorschlag: ${feld.vorschlaege[0].wert}` : ''}
        />

        {/* Vorschlag-Button */}
        {hasVorschlaege && value === null && (
          <button
            type="button"
            onClick={() => onChange(feld.vorschlaege[0].wert)}
            className="absolute right-2 top-1/2 -translate-y-1/2 text-xs text-primary-600 hover:text-primary-700 dark:text-primary-400"
          >
            Übernehmen
          </button>
        )}
      </div>

      {/* Vorschläge */}
      {hasVorschlaege && !compact && (
        <div className="flex flex-wrap gap-2 mt-1">
          {feld.vorschlaege.slice(0, 3).map((v, idx) => (
            <button
              key={idx}
              type="button"
              onClick={() => onChange(v.wert)}
              className="text-xs px-2 py-1 bg-gray-100 dark:bg-gray-700 rounded hover:bg-gray-200 dark:hover:bg-gray-600 text-gray-600 dark:text-gray-300"
              title={v.beschreibung}
            >
              {v.wert} {feld.einheit}
              <span className="text-gray-400 ml-1">({v.quelle})</span>
            </button>
          ))}
        </div>
      )}

      {/* Warnungen */}
      {hasWarnings && (
        <div className="mt-1">
          {feld.warnungen.map((w, idx) => (
            <div
              key={idx}
              className={`flex items-center gap-1 text-xs ${
                w.schwere === 'error'
                  ? 'text-red-600 dark:text-red-400'
                  : w.schwere === 'warning'
                  ? 'text-amber-600 dark:text-amber-400'
                  : 'text-blue-600 dark:text-blue-400'
              }`}
            >
              {w.schwere === 'error' ? (
                <AlertTriangle className="w-3 h-3" />
              ) : w.schwere === 'warning' ? (
                <AlertTriangle className="w-3 h-3" />
              ) : (
                <Info className="w-3 h-3" />
              )}
              {w.meldung}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function SummaryRow({
  label,
  wert,
  einheit,
  isText = false,
}: {
  label: string
  wert: number | string | null | undefined
  einheit: string
  isText?: boolean
}) {
  const hasValue = wert !== null && wert !== undefined && wert !== ''

  return (
    <div className="flex items-center justify-between px-4 py-2">
      <span className="text-sm text-gray-600 dark:text-gray-400">{label}</span>
      <span className="text-sm font-medium text-gray-900 dark:text-white">
        {hasValue ? (
          isText ? (
            <span className="max-w-xs truncate">{wert}</span>
          ) : (
            <>
              {typeof wert === 'number'
                ? wert.toLocaleString('de-DE', { maximumFractionDigits: 1 })
                : wert} {einheit}
            </>
          )
        ) : (
          <span className="text-gray-400 italic">nicht ausgefüllt</span>
        )}
      </span>
    </div>
  )
}

// =============================================================================
// Helpers
// =============================================================================

function getTypLabel(typ: string): string {
  const labels: Record<string, string> = {
    'pv-module': 'PV-Module',
    speicher: 'Speicher',
    waermepumpe: 'Wärmepumpe',
    'e-auto': 'E-Auto',
    wallbox: 'Wallbox',
    balkonkraftwerk: 'Balkonkraftwerk',
  }
  return labels[typ] || typ
}
