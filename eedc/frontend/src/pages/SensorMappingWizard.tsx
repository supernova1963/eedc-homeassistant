/**
 * SensorMappingWizard - Zuordnung HA-Sensoren zu EEDC-Feldern
 *
 * Schritte:
 * 1. Basis-Sensoren (Einspeisung, Netzbezug, PV gesamt)
 * 2. PV-Module
 * 3. Speicher (falls vorhanden)
 * 4. Wärmepumpe (falls vorhanden)
 * 5. E-Auto & Wallbox (falls vorhanden)
 * 6. Zusammenfassung
 */

import { useState, useMemo, useCallback, useEffect } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import {
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  AlertCircle,
  Loader2,
  Settings2,
  Zap,
  Battery,
  Thermometer,
  Car,
  Sun,
  Trash2,
} from 'lucide-react'
import { sensorMappingApi, anlagenApi } from '../api'
import { energieProfilApi, type VollbackfillResult } from '../api/energie_profil'
import type {
  FeldMapping,
  SensorMappingRequest,
  InvestitionInfo,
  SensorMappingResponse,
  HASensorInfo,
} from '../api/sensorMapping'
import Card, { CardHeader } from '../components/ui/Card'
import Button from '../components/ui/Button'
import Alert from '../components/ui/Alert'

// Step Components
import BasisSensorenStep from '../components/sensor-mapping/BasisSensorenStep'
import PVModuleStep from '../components/sensor-mapping/PVModuleStep'
import SpeicherStep from '../components/sensor-mapping/SpeicherStep'
import WaermepumpeStep from '../components/sensor-mapping/WaermepumpeStep'
import EAutoStep from '../components/sensor-mapping/EAutoStep'
import BalkonkraftwerkStep from '../components/sensor-mapping/BalkonkraftwerkStep'
import SonstigesStep from '../components/sensor-mapping/SonstigesStep'
import MappingSummaryStep from '../components/sensor-mapping/MappingSummaryStep'

// =============================================================================
// Types
// =============================================================================

interface WizardState {
  basis: {
    einspeisung: FeldMapping | null
    netzbezug: FeldMapping | null
    pv_gesamt: FeldMapping | null
    strompreis: FeldMapping | null
  }
  basisLive: Record<string, string | null>  // {einspeisung_w: entity_id, netzbezug_w: entity_id}
  basisLiveInvert: Record<string, boolean>  // {einspeisung_w: true} — Vorzeichen invertieren
  investitionen: Record<string, Record<string, FeldMapping>>
  investitionenLive: Record<string, Record<string, string | null>>  // {inv_id: {leistung_w: entity_id, soc: entity_id}}
  investitionenLiveInvert: Record<string, Record<string, boolean>>  // {inv_id: {leistung_w: true}}
}

interface StepConfig {
  id: string
  title: string
  icon: React.ReactNode
  investitionen?: InvestitionInfo[]
}

// =============================================================================
// Initial State
// =============================================================================

const initialState: WizardState = {
  basis: {
    einspeisung: null,
    netzbezug: null,
    pv_gesamt: null,
    strompreis: null,
  },
  basisLive: {},
  basisLiveInvert: {},
  investitionen: {},
  investitionenLive: {},
  investitionenLiveInvert: {},
}

// =============================================================================
// Component
// =============================================================================

export default function SensorMappingWizard() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()

  // Anlage ID aus URL
  const anlageIdParam = searchParams.get('anlage')
  const anlageId = anlageIdParam ? parseInt(anlageIdParam, 10) : null

  // State
  const [currentStep, setCurrentStep] = useState(0)
  const [state, setState] = useState<WizardState>(initialState)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [isSaving, setIsSaving] = useState(false)
  const [isDeleting, setIsDeleting] = useState(false)

  // Post-Save Dialog
  const [postSave, setPostSave] = useState<{
    liveChanged: boolean
    felderChanged: boolean
    backfillRunning: boolean
    backfillResult: VollbackfillResult | null
    backfillError: string | null
  } | null>(null)
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)

  // Data loading states
  const [anlagen, setAnlagen] = useState<{ id: number; anlagenname: string }[] | null>(null)
  const [mappingData, setMappingData] = useState<SensorMappingResponse | null>(null)
  const [availableSensors, setAvailableSensors] = useState<HASensorInfo[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)

  const effectiveAnlageId = anlageId || anlagen?.[0]?.id

  // Load data
  useEffect(() => {
    async function loadData() {
      setIsLoading(true)
      setLoadError(null)

      try {
        // Anlagen-Liste immer laden (für Dropdown bei Multi-Anlage)
        const anlagenList = await anlagenApi.list()
        setAnlagen(anlagenList)
        if (!anlagenList.length) {
          setIsLoading(false)
          return
        }

        const targetAnlageId = anlageId || anlagenList[0]?.id
        if (!targetAnlageId) {
          // Need to wait for anlagen to load first
          return
        }

        // Load mapping and sensors in parallel
        const [mapping, sensors] = await Promise.all([
          sensorMappingApi.getMapping(targetAnlageId),
          sensorMappingApi.getAvailableSensors(targetAnlageId).catch(() => []),
        ])

        setMappingData(mapping)
        setAvailableSensors(sensors)

        // Initialize state from existing mapping
        if (mapping?.mapping) {
          const existingMapping = mapping.mapping as {
            basis?: Record<string, FeldMapping> & { live?: Record<string, string | null>; live_invert?: Record<string, boolean> }
            investitionen?: Record<string, { felder: Record<string, FeldMapping>; live?: Record<string, string | null>; live_invert?: Record<string, boolean> }>
          }

          setState({
            basis: {
              einspeisung: existingMapping.basis?.einspeisung || null,
              netzbezug: existingMapping.basis?.netzbezug || null,
              pv_gesamt: existingMapping.basis?.pv_gesamt || null,
              strompreis: existingMapping.basis?.strompreis || null,
            },
            basisLive: existingMapping.basis?.live || {},
            basisLiveInvert: existingMapping.basis?.live_invert || {},
            investitionen: Object.fromEntries(
              Object.entries(existingMapping.investitionen || {}).map(([id, inv]) => [
                id,
                inv.felder || {},
              ])
            ),
            investitionenLive: Object.fromEntries(
              Object.entries(existingMapping.investitionen || {})
                .filter(([, inv]) => inv.live && Object.keys(inv.live).length > 0)
                .map(([id, inv]) => [id, inv.live!])
            ),
            investitionenLiveInvert: Object.fromEntries(
              Object.entries(existingMapping.investitionen || {})
                .filter(([, inv]) => inv.live_invert && Object.keys(inv.live_invert).length > 0)
                .map(([id, inv]) => [id, inv.live_invert!])
            ),
          })
        }
      } catch (err) {
        setLoadError((err as Error).message || 'Fehler beim Laden')
      } finally {
        setIsLoading(false)
      }
    }

    loadData()
  }, [anlageId])

  // Steps dynamisch generieren basierend auf Investitionen
  const steps = useMemo<StepConfig[]>(() => {
    if (!mappingData) return []

    const s: StepConfig[] = [
      { id: 'basis', title: 'Basis-Sensoren', icon: <Zap className="w-5 h-5" /> },
    ]

    const invByTyp = mappingData.investitionen.reduce<Record<string, InvestitionInfo[]>>(
      (acc, inv) => {
        if (!acc[inv.typ]) acc[inv.typ] = []
        acc[inv.typ].push(inv)
        return acc
      },
      {}
    )

    if (invByTyp['pv-module']?.length) {
      s.push({
        id: 'pv',
        title: 'PV-Module',
        icon: <Sun className="w-5 h-5" />,
        investitionen: invByTyp['pv-module'],
      })
    }

    if (invByTyp['speicher']?.length) {
      s.push({
        id: 'speicher',
        title: 'Speicher',
        icon: <Battery className="w-5 h-5" />,
        investitionen: invByTyp['speicher'],
      })
    }

    if (invByTyp['waermepumpe']?.length) {
      s.push({
        id: 'wp',
        title: 'Wärmepumpe',
        icon: <Thermometer className="w-5 h-5" />,
        investitionen: invByTyp['waermepumpe'],
      })
    }

    if (invByTyp['e-auto']?.length || invByTyp['wallbox']?.length) {
      s.push({
        id: 'eauto',
        title: 'E-Auto & Wallbox',
        icon: <Car className="w-5 h-5" />,
        investitionen: [...(invByTyp['e-auto'] || []), ...(invByTyp['wallbox'] || [])],
      })
    }

    if (invByTyp['balkonkraftwerk']?.length) {
      s.push({
        id: 'bkw',
        title: 'Balkonkraftwerk',
        icon: <Sun className="w-5 h-5" />,
        investitionen: invByTyp['balkonkraftwerk'],
      })
    }

    if (invByTyp['sonstiges']?.length) {
      s.push({
        id: 'sonstiges',
        title: 'Sonstige',
        icon: <Settings2 className="w-5 h-5" />,
        investitionen: invByTyp['sonstiges'],
      })
    }

    s.push({ id: 'summary', title: 'Zusammenfassung', icon: <CheckCircle2 className="w-5 h-5" /> })

    return s
  }, [mappingData])

  // Update handlers
  const updateBasis = useCallback((field: keyof WizardState['basis'], mapping: FeldMapping | null) => {
    setState(prev => ({
      ...prev,
      basis: { ...prev.basis, [field]: mapping },
    }))
  }, [])

  const updateInvestition = useCallback((invId: number, field: string, mapping: FeldMapping | null) => {
    if (!mapping) return
    setState(prev => ({
      ...prev,
      investitionen: {
        ...prev.investitionen,
        [invId.toString()]: {
          ...prev.investitionen[invId.toString()],
          [field]: mapping,
        },
      },
    }))
  }, [])

  const updateBasisLive = useCallback((key: string, entityId: string | null) => {
    setState(prev => {
      const next = { ...prev, basisLive: { ...prev.basisLive, [key]: entityId } }
      // Invert-Flag entfernen wenn Sensor gelöscht wird
      if (!entityId && prev.basisLiveInvert[key]) {
        const { [key]: _, ...rest } = prev.basisLiveInvert
        next.basisLiveInvert = rest
      }
      return next
    })
  }, [])

  const updateBasisLiveInvert = useCallback((key: string, invert: boolean) => {
    setState(prev => ({
      ...prev,
      basisLiveInvert: { ...prev.basisLiveInvert, [key]: invert },
    }))
  }, [])

  const updateInvestitionLive = useCallback((invId: number, sensorKey: string, entityId: string | null) => {
    setState(prev => {
      const id = invId.toString()
      const next = {
        ...prev,
        investitionenLive: {
          ...prev.investitionenLive,
          [id]: { ...prev.investitionenLive[id], [sensorKey]: entityId },
        },
      }
      // Invert-Flag entfernen wenn Sensor gelöscht wird
      if (!entityId && prev.investitionenLiveInvert[id]?.[sensorKey]) {
        const invInvert = { ...prev.investitionenLiveInvert[id] }
        delete invInvert[sensorKey]
        next.investitionenLiveInvert = { ...prev.investitionenLiveInvert, [id]: invInvert }
      }
      return next
    })
  }, [])

  const updateInvestitionLiveInvert = useCallback((invId: number, sensorKey: string, invert: boolean) => {
    setState(prev => {
      const id = invId.toString()
      return {
        ...prev,
        investitionenLiveInvert: {
          ...prev.investitionenLiveInvert,
          [id]: { ...prev.investitionenLiveInvert[id], [sensorKey]: invert },
        },
      }
    })
  }, [])

  // Save handler
  const handleSave = useCallback(async () => {
    if (!effectiveAnlageId) return

    setIsSaving(true)
    setSaveError(null)

    try {
      // Live-Felder bereinigen: leere Werte + veraltete Sensoren entfernen
      // Nur filtern wenn HA erreichbar (availableSensors nicht leer)
      const validEntityIds = availableSensors.length > 0
        ? new Set(availableSensors.map(s => s.entity_id))
        : null
      const cleanLive = (live: Record<string, string | null>): Record<string, string | null> | undefined => {
        const cleaned = Object.fromEntries(
          Object.entries(live).filter(([, v]) => v && (!validEntityIds || validEntityIds.has(v)))
        )
        return Object.keys(cleaned).length > 0 ? cleaned : undefined
      }

      // Invert-Flags bereinigen (nur true-Werte behalten)
      const cleanInvert = (invert: Record<string, boolean>): Record<string, boolean> | undefined => {
        const cleaned = Object.fromEntries(
          Object.entries(invert).filter(([, v]) => v)
        )
        return Object.keys(cleaned).length > 0 ? cleaned : undefined
      }

      // Änderungen erkennen (vor dem Save, gegen Original-Mapping)
      const origInv = mappingData?.mapping?.investitionen || {}
      const origBasis = mappingData?.mapping?.basis || {}

      const origLive = Object.fromEntries(
        Object.entries(origInv).map(([id, inv]) => [id, (inv as { live?: Record<string, string> }).live || {}])
      )
      const origFelder = Object.fromEntries(
        Object.entries(origInv).map(([id, inv]) => [id, (inv as { felder?: Record<string, unknown> }).felder || {}])
      )

      const liveChanged =
        JSON.stringify(state.investitionenLive) !== JSON.stringify(origLive) ||
        JSON.stringify(state.basisLive) !== JSON.stringify((origBasis as { live?: unknown }).live || {})

      const felderChanged =
        JSON.stringify(state.investitionen) !== JSON.stringify(origFelder) ||
        JSON.stringify(state.basis) !== JSON.stringify({
          einspeisung: (origBasis as Record<string, unknown>).einspeisung || null,
          netzbezug: (origBasis as Record<string, unknown>).netzbezug || null,
          pv_gesamt: (origBasis as Record<string, unknown>).pv_gesamt || null,
          strompreis: (origBasis as Record<string, unknown>).strompreis || null,
        })

      const request: SensorMappingRequest = {
        basis: {
          einspeisung: state.basis.einspeisung,
          netzbezug: state.basis.netzbezug,
          pv_gesamt: state.basis.pv_gesamt,
          strompreis: state.basis.strompreis,
          live: cleanLive(state.basisLive) || null,
          live_invert: cleanInvert(state.basisLiveInvert) || null,
        },
        investitionen: Object.fromEntries(
          Object.entries(state.investitionen).map(([id, felder]) => [
            id,
            {
              felder,
              live: cleanLive(state.investitionenLive[id] || {}) || null,
              live_invert: cleanInvert(state.investitionenLiveInvert[id] || {}) || null,
            },
          ])
        ),
      }

      await sensorMappingApi.saveMapping(effectiveAnlageId, request)

      // Post-Save-Dialog anzeigen wenn etwas geändert wurde
      if (liveChanged || felderChanged) {
        setPostSave({ liveChanged, felderChanged, backfillRunning: false, backfillResult: null, backfillError: null })
      } else {
        navigate('/einstellungen/ha-export?saved=true')
      }
    } catch (err) {
      setSaveError((err as Error).message || 'Fehler beim Speichern')
    } finally {
      setIsSaving(false)
    }
  }, [state, effectiveAnlageId, mappingData, availableSensors])

  // Handler zum Löschen des Mappings
  const handleDeleteMapping = useCallback(async () => {
    if (!effectiveAnlageId) return

    setIsDeleting(true)
    try {
      await sensorMappingApi.deleteMapping(effectiveAnlageId)
      // State zurücksetzen
      setState(initialState)
      setMappingData(prev => prev ? { ...prev, mapping: null } : null)
      setShowDeleteConfirm(false)
      // Seite neu laden um frischen State zu haben
      window.location.reload()
    } catch (err) {
      setSaveError((err as Error).message || 'Fehler beim Löschen')
    } finally {
      setIsDeleting(false)
    }
  }, [effectiveAnlageId])

  // Navigation
  const canGoNext = currentStep < steps.length - 1
  const canGoBack = currentStep > 0
  const isLastStep = currentStep === steps.length - 1

  const handleNext = () => {
    if (canGoNext) {
      setCurrentStep(prev => prev + 1)
    }
  }

  const handleBack = () => {
    if (canGoBack) {
      setCurrentStep(prev => prev - 1)
    }
  }

  // Loading / Error states
  if (!effectiveAnlageId && !isLoading) {
    return (
      <div className="p-6">
        <Alert type="warning">
          Keine Anlage vorhanden. Bitte zuerst eine Anlage erstellen.
        </Alert>
      </div>
    )
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <Loader2 className="w-8 h-8 animate-spin text-amber-500" />
      </div>
    )
  }

  if (loadError) {
    return (
      <div className="p-6">
        <Alert type="error">
          Fehler beim Laden: {loadError}
        </Alert>
      </div>
    )
  }

  if (steps.length === 0) {
    return (
      <div className="p-6">
        <Alert type="info">
          Keine Konfiguration erforderlich. Bitte zuerst Investitionen (PV-Module, Speicher, etc.) anlegen.
        </Alert>
      </div>
    )
  }

  const currentStepConfig = steps[currentStep]

  // Post-Save-Dialog: anzeigen wenn Mapping geändert und gespeichert wurde
  if (postSave) {
    const handleBackfill = async () => {
      if (!effectiveAnlageId) return
      setPostSave(prev => prev ? { ...prev, backfillRunning: true, backfillError: null } : null)
      try {
        const result = await energieProfilApi.vollbackfill(effectiveAnlageId)
        setPostSave(prev => prev ? { ...prev, backfillRunning: false, backfillResult: result } : null)
      } catch (err) {
        setPostSave(prev => prev ? { ...prev, backfillRunning: false, backfillError: (err as Error).message || 'Fehler beim Backfill' } : null)
      }
    }

    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Sensor-Zuordnung</h1>
            <p className="text-sm text-gray-500 dark:text-gray-400">{mappingData?.anlage_name}</p>
          </div>
        </div>

        <Card>
          <div className="p-6 space-y-6">
            <div className="flex items-center gap-3">
              <CheckCircle2 className="w-6 h-6 text-green-500 flex-shrink-0" />
              <div>
                <p className="font-semibold text-gray-900 dark:text-white">Sensor-Zuordnung gespeichert</p>
                <p className="text-sm text-gray-500 dark:text-gray-400">Die Änderungen sind aktiv für zukünftige Importe und das Live-Dashboard.</p>
              </div>
            </div>

            {postSave.liveChanged && (
              <div className="border border-blue-200 dark:border-blue-800 rounded-lg p-4 space-y-3">
                <p className="text-sm font-medium text-gray-900 dark:text-white">
                  Live-Sensoren wurden geändert
                </p>
                <p className="text-sm text-gray-600 dark:text-gray-400">
                  Das Energieprofil (stündliche Verlaufsdaten) kann mit den neuen Sensoren neu berechnet werden.
                  Bereits vorhandene Tage werden dabei überschrieben.
                </p>
                {postSave.backfillResult ? (
                  <Alert type="success">
                    ✓ {postSave.backfillResult.geschrieben} Tage neu berechnet ({postSave.backfillResult.von} – {postSave.backfillResult.bis})
                  </Alert>
                ) : postSave.backfillError ? (
                  <Alert type="error">{postSave.backfillError}</Alert>
                ) : (
                  <Button
                    onClick={handleBackfill}
                    disabled={postSave.backfillRunning}
                    variant="secondary"
                  >
                    {postSave.backfillRunning ? (
                      <><Loader2 className="w-4 h-4 mr-2 animate-spin" />Wird berechnet…</>
                    ) : (
                      <>Energieprofil-Verlauf neu berechnen</>
                    )}
                  </Button>
                )}
              </div>
            )}

            {postSave.felderChanged && (
              <div className="border border-amber-200 dark:border-amber-800 rounded-lg p-4 space-y-3">
                <p className="text-sm font-medium text-gray-900 dark:text-white">
                  Felder-Sensoren wurden geändert
                </p>
                <p className="text-sm text-gray-600 dark:text-gray-400">
                  Vergangene Monatsabschlüsse können mit den neuen Sensoren neu importiert werden.
                  Nur sinnvoll wenn sich der Sensor-Name geändert hat und die Daten korrekt sein sollen.
                </p>
                <Button
                  onClick={() => navigate('/einstellungen/ha-statistik-import?ueberschreiben=true')}
                  variant="secondary"
                >
                  Zum HA Statistik-Import (mit Überschreiben)
                </Button>
              </div>
            )}

            <div className="pt-2">
              <Button onClick={() => navigate('/einstellungen/ha-export?saved=true')}>
                Fertig
              </Button>
            </div>
          </div>
        </Card>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
            Sensor-Zuordnung
          </h1>
          <p className="text-gray-500 dark:text-gray-400 mt-1">
            {anlagen && anlagen.length > 1 ? (
              <span className="inline-flex items-center gap-2">
                <select
                  title="Anlage auswählen"
                  value={effectiveAnlageId ?? ''}
                  onChange={(e) => {
                    const id = Number(e.target.value)
                    navigate(`/einstellungen/sensor-mapping?anlage=${id}`, { replace: true })
                  }}
                  className="text-sm border border-gray-300 dark:border-gray-600 rounded px-2 py-0.5 bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
                >
                  {anlagen.map((a) => (
                    <option key={a.id} value={a.id}>{a.anlagenname}</option>
                  ))}
                </select>
                <span>— Home Assistant Sensoren konfigurieren</span>
              </span>
            ) : (
              <>{mappingData?.anlage_name} — Home Assistant Sensoren konfigurieren</>
            )}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {/* Löschen-Button nur anzeigen wenn Mapping existiert */}
          {mappingData?.mapping && Object.keys(mappingData.mapping).length > 0 && (
            <Button
              variant="secondary"
              onClick={() => setShowDeleteConfirm(true)}
              className="text-red-600 hover:text-red-700 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-900/20"
            >
              <Trash2 className="w-4 h-4 mr-2" />
              Mapping löschen
            </Button>
          )}
          <Button variant="secondary" onClick={() => navigate(-1)}>
            Abbrechen
          </Button>
        </div>
      </div>

      {/* Lösch-Bestätigung */}
      {showDeleteConfirm && (
        <Alert type="warning">
          <div className="flex items-center justify-between">
            <div>
              <p className="font-medium">Sensor-Mapping wirklich löschen?</p>
              <p className="text-sm mt-1">
                Alle Sensor-Zuordnungen und MQTT-Entities werden entfernt.
                Die Monatsdaten bleiben erhalten.
              </p>
            </div>
            <div className="flex gap-2 ml-4">
              <Button
                variant="secondary"
                size="sm"
                onClick={() => setShowDeleteConfirm(false)}
                disabled={isDeleting}
              >
                Abbrechen
              </Button>
              <Button
                size="sm"
                onClick={handleDeleteMapping}
                disabled={isDeleting}
                className="bg-red-600 hover:bg-red-700"
              >
                {isDeleting ? (
                  <>
                    <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                    Lösche...
                  </>
                ) : (
                  <>
                    <Trash2 className="w-4 h-4 mr-2" />
                    Löschen
                  </>
                )}
              </Button>
            </div>
          </div>
        </Alert>
      )}

      {/* Progress */}
      <Card padding="sm">
        <div className="flex items-center overflow-x-auto py-2">
          {steps.map((step, index) => {
            const isCompleted = index < currentStep
            const isCurrent = index === currentStep

            return (
              <div key={step.id} className="flex items-center flex-shrink-0">
                <button
                  onClick={() => setCurrentStep(index)}
                  className={`
                    flex items-center gap-2 px-3 py-2 rounded-lg transition-all
                    ${isCurrent
                      ? 'bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-400'
                      : isCompleted
                        ? 'text-green-600 dark:text-green-400 hover:bg-gray-100 dark:hover:bg-gray-700'
                        : 'text-gray-400 dark:text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-700'
                    }
                  `}
                >
                  <div
                    className={`
                      w-7 h-7 rounded-full flex items-center justify-center text-sm
                      ${isCompleted
                        ? 'bg-green-500 text-white'
                        : isCurrent
                          ? 'bg-amber-500 text-white'
                          : 'bg-gray-200 dark:bg-gray-700'
                      }
                    `}
                  >
                    {isCompleted ? <CheckCircle2 className="w-4 h-4" /> : index + 1}
                  </div>
                  <span className="text-sm font-medium whitespace-nowrap">{step.title}</span>
                </button>
                {index < steps.length - 1 && (
                  <ChevronRight className="w-5 h-5 text-gray-300 dark:text-gray-600 mx-1" />
                )}
              </div>
            )
          })}
        </div>
      </Card>

      {/* Step Content */}
      <Card>
        <CardHeader
          title={currentStepConfig.title}
          subtitle={
            currentStepConfig.id === 'basis'
              ? 'Ordne die grundlegenden Energie-Sensoren zu'
              : currentStepConfig.id === 'summary'
                ? 'Überprüfe deine Einstellungen'
                : `Konfiguriere die Sensoren für ${currentStepConfig.investitionen?.length || 0} Komponente(n)`
          }
          action={
            <div className="flex items-center gap-2 text-gray-400">
              {currentStepConfig.icon}
              <span className="text-sm">
                {currentStep + 1} / {steps.length}
              </span>
            </div>
          }
        />

        <div className="mt-6">
          {currentStepConfig.id === 'basis' && (
            <BasisSensorenStep
              value={state.basis}
              onChange={updateBasis}
              availableSensors={availableSensors}
              basisLive={state.basisLive}
              onBasisLiveChange={updateBasisLive}
              basisLiveInvert={state.basisLiveInvert}
              onBasisLiveInvertChange={updateBasisLiveInvert}
            />
          )}

          {currentStepConfig.id === 'pv' && (
            <PVModuleStep
              investitionen={currentStepConfig.investitionen || []}
              mappings={state.investitionen}
              onChange={updateInvestition}
              availableSensors={availableSensors}
              gesamtKwp={mappingData?.gesamt_kwp || 0}
              basisPvGesamt={state.basis.pv_gesamt}
              liveMappings={state.investitionenLive}
              onLiveChange={updateInvestitionLive}
              liveInvertMappings={state.investitionenLiveInvert}
              onLiveInvertChange={updateInvestitionLiveInvert}
            />
          )}

          {currentStepConfig.id === 'speicher' && (
            <SpeicherStep
              investitionen={currentStepConfig.investitionen || []}
              mappings={state.investitionen}
              onChange={updateInvestition}
              availableSensors={availableSensors}
              liveMappings={state.investitionenLive}
              onLiveChange={updateInvestitionLive}
              liveInvertMappings={state.investitionenLiveInvert}
              onLiveInvertChange={updateInvestitionLiveInvert}
            />
          )}

          {currentStepConfig.id === 'wp' && (
            <WaermepumpeStep
              investitionen={currentStepConfig.investitionen || []}
              mappings={state.investitionen}
              onChange={updateInvestition}
              availableSensors={availableSensors}
              liveMappings={state.investitionenLive}
              onLiveChange={updateInvestitionLive}
              liveInvertMappings={state.investitionenLiveInvert}
              onLiveInvertChange={updateInvestitionLiveInvert}
            />
          )}

          {currentStepConfig.id === 'eauto' && (
            <EAutoStep
              investitionen={currentStepConfig.investitionen || []}
              mappings={state.investitionen}
              onChange={updateInvestition}
              availableSensors={availableSensors}
              liveMappings={state.investitionenLive}
              onLiveChange={updateInvestitionLive}
              liveInvertMappings={state.investitionenLiveInvert}
              onLiveInvertChange={updateInvestitionLiveInvert}
            />
          )}

          {currentStepConfig.id === 'bkw' && (
            <BalkonkraftwerkStep
              investitionen={currentStepConfig.investitionen || []}
              mappings={state.investitionen}
              onChange={updateInvestition}
              availableSensors={availableSensors}
              liveMappings={state.investitionenLive}
              onLiveChange={updateInvestitionLive}
              liveInvertMappings={state.investitionenLiveInvert}
              onLiveInvertChange={updateInvestitionLiveInvert}
            />
          )}

          {currentStepConfig.id === 'sonstiges' && (
            <SonstigesStep
              investitionen={currentStepConfig.investitionen || []}
              mappings={state.investitionen}
              onChange={updateInvestition}
              availableSensors={availableSensors}
              liveMappings={state.investitionenLive}
              onLiveChange={updateInvestitionLive}
              liveInvertMappings={state.investitionenLiveInvert}
              onLiveInvertChange={updateInvestitionLiveInvert}
            />
          )}

          {currentStepConfig.id === 'summary' && (
            <MappingSummaryStep
              state={state}
              investitionen={mappingData?.investitionen || []}
              anlageId={effectiveAnlageId}
            />
          )}
        </div>

        {/* Error Message */}
        {saveError && (
          <Alert type="error" className="mt-6">
            <AlertCircle className="w-4 h-4 inline mr-2" />
            {saveError}
          </Alert>
        )}

        {/* Navigation */}
        <div className="flex items-center justify-between mt-8 pt-6 border-t border-gray-200 dark:border-gray-700">
          <Button
            variant="secondary"
            onClick={handleBack}
            disabled={!canGoBack}
          >
            <ChevronLeft className="w-4 h-4 mr-2" />
            Zurück
          </Button>

          {isLastStep ? (
            <Button
              onClick={handleSave}
              disabled={isSaving}
            >
              {isSaving ? (
                <>
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  Speichern...
                </>
              ) : (
                <>
                  <Settings2 className="w-4 h-4 mr-2" />
                  Speichern & Abschließen
                </>
              )}
            </Button>
          ) : (
            <Button onClick={handleNext}>
              Weiter
              <ChevronRight className="w-4 h-4 ml-2" />
            </Button>
          )}
        </div>
      </Card>
    </div>
  )
}
