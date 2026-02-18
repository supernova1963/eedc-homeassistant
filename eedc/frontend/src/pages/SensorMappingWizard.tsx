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
} from 'lucide-react'
import { sensorMappingApi, anlagenApi, haStatisticsApi } from '../api'
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
import MappingSummaryStep from '../components/sensor-mapping/MappingSummaryStep'

// =============================================================================
// Types
// =============================================================================

interface WizardState {
  basis: {
    einspeisung: FeldMapping | null
    netzbezug: FeldMapping | null
    pv_gesamt: FeldMapping | null
  }
  investitionen: Record<string, Record<string, FeldMapping>>
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
  },
  investitionen: {},
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
  const [showInitDialog, setShowInitDialog] = useState(false)
  const [isInitializing, setIsInitializing] = useState(false)
  const [initResult, setInitResult] = useState<{
    success: boolean
    message: string
    updated_fields: number
  } | null>(null)
  const [haDbVerfuegbar, setHaDbVerfuegbar] = useState<boolean | null>(null)
  const [loadingHaStatus, setLoadingHaStatus] = useState(false)
  const [isInitializingFromDb, setIsInitializingFromDb] = useState(false)

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
        // Load anlagen if no anlageId
        if (!anlageId) {
          const anlagenList = await anlagenApi.list()
          setAnlagen(anlagenList)
          if (!anlagenList.length) {
            setIsLoading(false)
            return
          }
        }

        const targetAnlageId = anlageId || (anlagen?.[0]?.id)
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
            basis?: Record<string, FeldMapping>
            investitionen?: Record<string, { felder: Record<string, FeldMapping> }>
          }

          setState({
            basis: {
              einspeisung: existingMapping.basis?.einspeisung || null,
              netzbezug: existingMapping.basis?.netzbezug || null,
              pv_gesamt: existingMapping.basis?.pv_gesamt || null,
            },
            investitionen: Object.fromEntries(
              Object.entries(existingMapping.investitionen || {}).map(([id, inv]) => [
                id,
                inv.felder || {},
              ])
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
  }, [anlageId, anlagen?.[0]?.id])

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

  // Save handler
  const handleSave = useCallback(async () => {
    if (!effectiveAnlageId) return

    setIsSaving(true)
    setSaveError(null)

    try {
      const request: SensorMappingRequest = {
        basis: {
          einspeisung: state.basis.einspeisung,
          netzbezug: state.basis.netzbezug,
          pv_gesamt: state.basis.pv_gesamt,
        },
        investitionen: Object.fromEntries(
          Object.entries(state.investitionen).map(([id, felder]) => [
            id,
            { felder },
          ])
        ),
      }

      await sensorMappingApi.saveMapping(effectiveAnlageId, request)
      // Nach erfolgreichem Speichern: Dialog zum Initialisieren anzeigen
      setShowInitDialog(true)
    } catch (err) {
      setSaveError((err as Error).message || 'Fehler beim Speichern')
    } finally {
      setIsSaving(false)
    }
  }, [state, effectiveAnlageId])

  // Handler zum Initialisieren der Startwerte
  const handleInitStartValues = useCallback(async () => {
    if (!effectiveAnlageId) return

    setIsInitializing(true)
    try {
      const result = await sensorMappingApi.initStartValues(effectiveAnlageId)
      setInitResult(result)
    } catch (err) {
      setInitResult({
        success: false,
        message: (err as Error).message || 'Fehler beim Initialisieren',
        updated_fields: 0,
      })
    } finally {
      setIsInitializing(false)
    }
  }, [effectiveAnlageId])

  // Prüfe HA-DB-Verfügbarkeit wenn Init-Dialog geöffnet wird
  useEffect(() => {
    if (showInitDialog && haDbVerfuegbar === null) {
      setLoadingHaStatus(true)
      haStatisticsApi.getStatus()
        .then(status => setHaDbVerfuegbar(status.verfuegbar))
        .catch(() => setHaDbVerfuegbar(false))
        .finally(() => setLoadingHaStatus(false))
    }
  }, [showInitDialog, haDbVerfuegbar])

  // Handler zum Initialisieren aus HA-Statistik-DB (Monatsanfang)
  const handleInitFromHaDb = useCallback(async () => {
    if (!effectiveAnlageId) return

    setIsInitializingFromDb(true)
    try {
      // Aktueller Monat
      const now = new Date()
      const jahr = now.getFullYear()
      const monat = now.getMonth() + 1

      const result = await haStatisticsApi.getMonatsanfangWerte(effectiveAnlageId, jahr, monat)
      const startwerte = result.startwerte || {}
      const feldCount = Object.keys(startwerte).length

      if (feldCount > 0) {
        // Werte wurden geladen, jetzt an MQTT senden
        // Das macht der Backend-Endpoint automatisch
        setInitResult({
          success: true,
          message: `Startwerte für ${monat}/${jahr} aus HA-Statistik geladen`,
          updated_fields: feldCount,
        })
      } else {
        setInitResult({
          success: false,
          message: 'Keine Daten in HA-Statistik für diesen Monat gefunden. Möglicherweise sind noch keine Langzeit-Statistiken für die konfigurierten Sensoren vorhanden.',
          updated_fields: 0,
        })
      }
    } catch (err) {
      setInitResult({
        success: false,
        message: (err as Error).message || 'Fehler beim Laden aus HA-Statistik',
        updated_fields: 0,
      })
    } finally {
      setIsInitializingFromDb(false)
    }
  }, [effectiveAnlageId])

  // Handler zum Abschließen (nach Init-Dialog)
  const handleFinish = useCallback(() => {
    navigate('/einstellungen/ha-export?saved=true')
  }, [navigate])

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

  // Init-Dialog nach erfolgreichem Speichern
  if (showInitDialog) {
    return (
      <div className="max-w-2xl mx-auto p-6 space-y-6">
        <Card>
          <CardHeader
            title="Sensor-Zuordnung gespeichert"
            subtitle="MQTT-Sensoren wurden erfolgreich erstellt"
          />

          <div className="mt-6 space-y-4">
            {!initResult ? (
              <>
                <Alert type="info">
                  <div className="space-y-2">
                    <p className="font-medium">Möchten Sie die Monatsstart-Werte jetzt initialisieren?</p>
                    <p className="text-sm opacity-80">
                      Die Startwerte werden als Basis für die monatliche Berechnung benötigt.
                      Der berechnete Monatswert startet dann bei 0 und steigt mit der Zeit.
                    </p>
                  </div>
                </Alert>

                <div className="space-y-3">
                  {/* Option 1: Aus HA-Statistik (empfohlen wenn verfügbar) */}
                  {loadingHaStatus ? (
                    <div className="flex items-center gap-2 text-gray-500">
                      <Loader2 className="w-4 h-4 animate-spin" />
                      Prüfe HA-Statistik-Verfügbarkeit...
                    </div>
                  ) : haDbVerfuegbar && (
                    <div className="p-4 border border-green-200 dark:border-green-800 bg-green-50 dark:bg-green-900/20 rounded-lg">
                      <p className="text-sm text-green-800 dark:text-green-200 mb-2">
                        <strong>Empfohlen:</strong> Startwerte aus HA-Langzeitstatistik laden
                      </p>
                      <p className="text-xs text-green-600 dark:text-green-400 mb-3">
                        Verwendet die gespeicherten Zählerstände vom Monatsanfang aus der HA-Datenbank.
                      </p>
                      <Button
                        onClick={handleInitFromHaDb}
                        disabled={isInitializingFromDb}
                      >
                        {isInitializingFromDb ? (
                          <>
                            <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                            Lade aus HA-DB...
                          </>
                        ) : (
                          <>
                            <CheckCircle2 className="w-4 h-4 mr-2" />
                            Aus HA-Statistik laden (empfohlen)
                          </>
                        )}
                      </Button>
                    </div>
                  )}

                  {/* Option 2: Aktuelle Sensorwerte */}
                  <div className="p-4 border border-gray-200 dark:border-gray-700 rounded-lg">
                    <p className="text-sm text-gray-700 dark:text-gray-300 mb-2">
                      Aktuelle Sensor-Werte als Startwerte setzen
                    </p>
                    <p className="text-xs text-gray-500 dark:text-gray-400 mb-3">
                      Verwendet die aktuellen Zählerstände. Der Monatswert startet dann bei 0.
                    </p>
                    <Button
                      variant="secondary"
                      onClick={handleInitStartValues}
                      disabled={isInitializing}
                    >
                      {isInitializing ? (
                        <>
                          <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                          Initialisiere...
                        </>
                      ) : (
                        <>
                          <Zap className="w-4 h-4 mr-2" />
                          Aktuelle Werte verwenden
                        </>
                      )}
                    </Button>
                  </div>

                  <Button variant="secondary" onClick={handleFinish} className="mt-2">
                    Überspringen
                  </Button>
                </div>
              </>
            ) : (
              <>
                <Alert type={initResult.success ? 'success' : 'error'}>
                  <div className="space-y-1">
                    <p className="font-medium">{initResult.message}</p>
                    {initResult.updated_fields > 0 && (
                      <p className="text-sm opacity-80">
                        {initResult.updated_fields} Startwert(e) wurden in Home Assistant gesetzt.
                      </p>
                    )}
                  </div>
                </Alert>

                <Button onClick={handleFinish}>
                  <CheckCircle2 className="w-4 h-4 mr-2" />
                  Fertig
                </Button>
              </>
            )}
          </div>
        </Card>
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

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
            Sensor-Zuordnung
          </h1>
          <p className="text-gray-500 dark:text-gray-400 mt-1">
            {mappingData?.anlage_name} - Home Assistant Sensoren konfigurieren
          </p>
        </div>
        <Button variant="secondary" onClick={() => navigate(-1)}>
          Abbrechen
        </Button>
      </div>

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
            />
          )}

          {currentStepConfig.id === 'speicher' && (
            <SpeicherStep
              investitionen={currentStepConfig.investitionen || []}
              mappings={state.investitionen}
              onChange={updateInvestition}
              availableSensors={availableSensors}
            />
          )}

          {currentStepConfig.id === 'wp' && (
            <WaermepumpeStep
              investitionen={currentStepConfig.investitionen || []}
              mappings={state.investitionen}
              onChange={updateInvestition}
              availableSensors={availableSensors}
            />
          )}

          {currentStepConfig.id === 'eauto' && (
            <EAutoStep
              investitionen={currentStepConfig.investitionen || []}
              mappings={state.investitionen}
              onChange={updateInvestition}
              availableSensors={availableSensors}
            />
          )}

          {currentStepConfig.id === 'summary' && (
            <MappingSummaryStep
              state={state}
              investitionen={mappingData?.investitionen || []}
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
