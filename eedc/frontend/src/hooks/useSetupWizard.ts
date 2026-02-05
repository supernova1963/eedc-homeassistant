/**
 * React Hook für den Setup-Wizard State Management
 *
 * Verwaltet den gesamten Einrichtungsprozess für neue Benutzer:
 * 1. Anlage erstellen
 * 2. HA-Verbindung prüfen
 * 3. Strompreise konfigurieren
 * 4. Auto-Discovery (Geräte erkennen)
 * 5. Investitionen vervollständigen
 * 6. Zusammenfassung
 */

import { useState, useCallback, useEffect } from 'react'
import { anlagenApi } from '../api/anlagen'
import { strompreiseApi } from '../api/strompreise'
import { haApi } from '../api/ha'
import { investitionenApi, type InvestitionCreate } from '../api/investitionen'
import type { Anlage, Strompreis, Investition } from '../types'
import type { DiscoveryResult, DiscoveredDevice } from '../api/ha'

// Wizard-Schritte
export type WizardStep =
  | 'welcome'
  | 'anlage'
  | 'ha-connection'
  | 'strompreise'
  | 'pv-module'
  | 'discovery'
  | 'investitionen'
  | 'summary'
  | 'complete'

// PV-Modul Daten für Wizard
export interface PVModulData {
  id: string  // Temporäre ID für UI
  bezeichnung: string
  leistung_kwp: number
  ausrichtung: string
  neigung_grad: number
  ha_entity_id?: string
}

// Wizard-State der in DB/LocalStorage gespeichert wird
export interface WizardState {
  completed: boolean
  currentStep: WizardStep
  anlageId: number | null
  strompreisId: number | null
  createdInvestitionen: number[]
  skippedSteps: WizardStep[]
  pvModule: PVModulData[]
}

// Standard-Strompreise für Deutschland (2026)
export const DEFAULT_STROMPREISE = {
  netzbezug_arbeitspreis_cent_kwh: 30.0,
  einspeiseverguetung_cent_kwh: 8.2,  // Für Anlagen < 10 kWp
  grundpreis_euro_monat: 12.0,
}

// Einspeisevergütung nach Anlagengröße (Stand 2026)
export function getEinspeiseverguetung(leistungKwp: number): number {
  if (leistungKwp <= 10) return 8.2
  if (leistungKwp <= 40) return 7.1
  return 5.8
}

interface UseSetupWizardReturn {
  // State
  step: WizardStep
  wizardState: WizardState
  isLoading: boolean
  error: string | null

  // Daten
  anlage: Anlage | null
  strompreis: Strompreis | null
  haConnected: boolean
  haVersion: string | null
  discoveryResult: DiscoveryResult | null
  selectedDevices: Set<string>
  createdInvestitionen: Investition[]

  // Investitions-Bearbeitung
  investitionenToEdit: DiscoveredDevice[]
  investitionFormData: Record<string, InvestitionFormData>

  // Actions
  goToStep: (step: WizardStep) => void
  nextStep: () => void
  prevStep: () => void
  skipStep: () => void

  // Anlage
  createAnlage: (data: AnlageCreateData) => Promise<void>

  // HA-Verbindung
  checkHAConnection: () => Promise<void>

  // Strompreise
  createStrompreis: (data: StrompreisCreateData) => Promise<void>
  useDefaultStrompreise: () => Promise<void>

  // Discovery
  runDiscovery: () => Promise<void>
  toggleDevice: (deviceId: string) => void
  selectAllDevices: () => void
  deselectAllDevices: () => void

  // Investitionen
  updateInvestitionFormData: (deviceId: string, data: Partial<InvestitionFormData>) => void
  createInvestitionen: () => Promise<void>

  // PV-Module
  pvModule: PVModulData[]
  addPVModul: (modul: Omit<PVModulData, 'id'>) => void
  updatePVModul: (id: string, data: Partial<PVModulData>) => void
  removePVModul: (id: string) => void
  savePVModule: () => Promise<void>

  // Abschluss
  completeWizard: () => void
  resetWizard: () => void

  // Computed
  canProceed: boolean
  progress: number
}

// Anlage-Daten für Wizard (vereinfacht)
interface AnlageCreateData {
  anlagenname: string
  leistung_kwp: number
  installationsdatum?: string
  standort_plz?: string
  standort_ort?: string
  latitude?: number
  longitude?: number
  ausrichtung?: string
  neigung_grad?: number
}

// Strompreis-Daten für Wizard
interface StrompreisCreateData {
  netzbezug_arbeitspreis_cent_kwh: number
  einspeiseverguetung_cent_kwh: number
  grundpreis_euro_monat?: number
  gueltig_ab: string
  tarifname?: string
  anbieter?: string
}

// Investition-Formular-Daten im Wizard
export interface InvestitionFormData {
  bezeichnung: string
  kaufdatum: string
  kaufpreis: number
  // Typ-spezifische Felder
  batterie_kwh?: number  // E-Auto, Speicher
  leistung_kw?: number   // Wallbox, Wechselrichter
  kapazitaet_kwh?: number // Speicher
}

// LocalStorage Key
const WIZARD_STATE_KEY = 'eedc_setup_wizard_state'

// Initiale State
const INITIAL_STATE: WizardState = {
  completed: false,
  currentStep: 'welcome',
  anlageId: null,
  strompreisId: null,
  createdInvestitionen: [],
  skippedSteps: [],
  pvModule: [],
}

// Schritt-Reihenfolge
const STEP_ORDER: WizardStep[] = [
  'welcome',
  'anlage',
  'ha-connection',
  'strompreise',
  'pv-module',
  'discovery',
  'investitionen',
  'summary',
  'complete',
]

export function useSetupWizard(): UseSetupWizardReturn {
  // Persistierter State
  const [wizardState, setWizardState] = useState<WizardState>(() => {
    try {
      const saved = localStorage.getItem(WIZARD_STATE_KEY)
      if (saved) {
        return JSON.parse(saved)
      }
    } catch {
      // Ignore
    }
    return INITIAL_STATE
  })

  // Lokaler State
  const [step, setStep] = useState<WizardStep>(wizardState.currentStep)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Daten
  const [anlage, setAnlage] = useState<Anlage | null>(null)
  const [strompreis, setStrompreis] = useState<Strompreis | null>(null)
  const [haConnected, setHaConnected] = useState(false)
  const [haVersion, setHaVersion] = useState<string | null>(null)
  const [discoveryResult, setDiscoveryResult] = useState<DiscoveryResult | null>(null)
  const [selectedDevices, setSelectedDevices] = useState<Set<string>>(new Set())
  const [createdInvestitionen, setCreatedInvestitionen] = useState<Investition[]>([])

  // Investitions-Bearbeitung
  const [investitionFormData, setInvestitionFormData] = useState<Record<string, InvestitionFormData>>({})

  // State in LocalStorage speichern
  useEffect(() => {
    localStorage.setItem(WIZARD_STATE_KEY, JSON.stringify({
      ...wizardState,
      currentStep: step,
    }))
  }, [wizardState, step])

  // Anlage laden wenn ID vorhanden
  useEffect(() => {
    if (wizardState.anlageId && !anlage) {
      anlagenApi.get(wizardState.anlageId).then(setAnlage).catch(() => {})
    }
  }, [wizardState.anlageId, anlage])

  // Navigation
  const goToStep = useCallback((newStep: WizardStep) => {
    setStep(newStep)
    setError(null)
  }, [])

  const nextStep = useCallback(() => {
    const currentIndex = STEP_ORDER.indexOf(step)
    if (currentIndex < STEP_ORDER.length - 1) {
      goToStep(STEP_ORDER[currentIndex + 1])
    }
  }, [step, goToStep])

  const prevStep = useCallback(() => {
    const currentIndex = STEP_ORDER.indexOf(step)
    if (currentIndex > 0) {
      goToStep(STEP_ORDER[currentIndex - 1])
    }
  }, [step, goToStep])

  const skipStep = useCallback(() => {
    setWizardState(prev => ({
      ...prev,
      skippedSteps: [...prev.skippedSteps, step],
    }))
    nextStep()
  }, [step, nextStep])

  // Anlage erstellen
  const createAnlage = useCallback(async (data: AnlageCreateData) => {
    setIsLoading(true)
    setError(null)

    try {
      const newAnlage = await anlagenApi.create(data)
      setAnlage(newAnlage)
      setWizardState(prev => ({
        ...prev,
        anlageId: newAnlage.id,
      }))
      nextStep()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Fehler beim Erstellen der Anlage')
    } finally {
      setIsLoading(false)
    }
  }, [nextStep])

  // HA-Verbindung prüfen
  const checkHAConnection = useCallback(async () => {
    setIsLoading(true)
    setError(null)

    try {
      const status = await haApi.getStatus()
      setHaConnected(status.connected)
      setHaVersion(status.ha_version || null)

      if (!status.connected) {
        setError('Keine Verbindung zu Home Assistant. Sie können diesen Schritt überspringen und später konfigurieren.')
      }
    } catch (e) {
      setHaConnected(false)
      setError('Home Assistant nicht erreichbar. Läuft EEDC als Add-on?')
    } finally {
      setIsLoading(false)
    }
  }, [])

  // Strompreis erstellen
  const createStrompreis = useCallback(async (data: StrompreisCreateData) => {
    if (!wizardState.anlageId) {
      setError('Keine Anlage vorhanden')
      return
    }

    setIsLoading(true)
    setError(null)

    try {
      const newStrompreis = await strompreiseApi.create({
        anlage_id: wizardState.anlageId,
        ...data,
      })
      setStrompreis(newStrompreis)
      setWizardState(prev => ({
        ...prev,
        strompreisId: newStrompreis.id,
      }))
      nextStep()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Fehler beim Erstellen des Stromtarifs')
    } finally {
      setIsLoading(false)
    }
  }, [wizardState.anlageId, nextStep])

  // Standard-Strompreise verwenden
  const useDefaultStrompreise = useCallback(async () => {
    if (!wizardState.anlageId || !anlage) {
      setError('Keine Anlage vorhanden')
      return
    }

    const einspeiseverguetung = getEinspeiseverguetung(anlage.leistung_kwp)

    await createStrompreis({
      netzbezug_arbeitspreis_cent_kwh: DEFAULT_STROMPREISE.netzbezug_arbeitspreis_cent_kwh,
      einspeiseverguetung_cent_kwh: einspeiseverguetung,
      grundpreis_euro_monat: DEFAULT_STROMPREISE.grundpreis_euro_monat,
      gueltig_ab: anlage.installationsdatum || new Date().toISOString().split('T')[0],
      tarifname: 'Standard-Tarif',
    })
  }, [wizardState.anlageId, anlage, createStrompreis])

  // Discovery ausführen
  const runDiscovery = useCallback(async () => {
    if (!wizardState.anlageId) {
      setError('Keine Anlage vorhanden')
      return
    }

    setIsLoading(true)
    setError(null)

    try {
      // Hersteller aus Anlage-Daten für gezieltere Suche
      const manufacturer = anlage?.wechselrichter_hersteller || undefined
      const result = await haApi.discover(wizardState.anlageId, manufacturer)
      setDiscoveryResult(result)

      if (!result.ha_connected) {
        setError('Keine Verbindung zu Home Assistant')
        return
      }

      // Automatisch alle nicht-konfigurierten Geräte auswählen
      const autoSelected = new Set<string>()
      const formData: Record<string, InvestitionFormData> = {}

      for (const device of result.devices) {
        if (!device.already_configured && device.suggested_investition_typ) {
          autoSelected.add(device.id)

          // Initiale Formulardaten
          formData[device.id] = {
            bezeichnung: device.suggested_parameters.bezeichnung as string || device.name,
            kaufdatum: new Date().toISOString().split('T')[0],
            kaufpreis: 0,
            batterie_kwh: device.suggested_parameters.batterie_kwh as number,
            leistung_kw: device.suggested_parameters.leistung_kw as number,
            kapazitaet_kwh: device.suggested_parameters.kapazitaet_kwh as number,
          }
        }
      }

      setSelectedDevices(autoSelected)
      setInvestitionFormData(formData)

    } catch (e) {
      setError(e instanceof Error ? e.message : 'Discovery fehlgeschlagen')
    } finally {
      setIsLoading(false)
    }
  }, [wizardState.anlageId])

  // Gerät auswählen/abwählen
  const toggleDevice = useCallback((deviceId: string) => {
    setSelectedDevices(prev => {
      const next = new Set(prev)
      if (next.has(deviceId)) {
        next.delete(deviceId)
      } else {
        next.add(deviceId)
      }
      return next
    })
  }, [])

  const selectAllDevices = useCallback(() => {
    if (!discoveryResult) return
    const all = new Set(
      discoveryResult.devices
        .filter(d => !d.already_configured && d.suggested_investition_typ)
        .map(d => d.id)
    )
    setSelectedDevices(all)
  }, [discoveryResult])

  const deselectAllDevices = useCallback(() => {
    setSelectedDevices(new Set())
  }, [])

  // Investitions-Formular aktualisieren
  const updateInvestitionFormData = useCallback((deviceId: string, data: Partial<InvestitionFormData>) => {
    setInvestitionFormData(prev => ({
      ...prev,
      [deviceId]: {
        ...prev[deviceId],
        ...data,
      },
    }))
  }, [])

  // Investitionen erstellen
  const createInvestitionen = useCallback(async () => {
    if (!wizardState.anlageId || !discoveryResult) {
      setError('Keine Anlage oder Discovery-Daten vorhanden')
      return
    }

    setIsLoading(true)
    setError(null)

    const created: Investition[] = []
    const createdIds: number[] = []

    try {
      for (const deviceId of selectedDevices) {
        const device = discoveryResult.devices.find(d => d.id === deviceId)
        if (!device || device.already_configured || !device.suggested_investition_typ) continue

        const formData = investitionFormData[deviceId]
        if (!formData) continue

        // Parameter für typ-spezifische Felder
        const parameter: Record<string, unknown> = {}

        // E-Auto / Speicher: Batteriekapazität
        if (formData.batterie_kwh) {
          parameter.batterie_kwh = formData.batterie_kwh
          if (device.suggested_investition_typ === 'speicher') {
            parameter.kapazitaet_kwh = formData.batterie_kwh
          }
        }

        // Wallbox / Wechselrichter: Leistung
        if (formData.leistung_kw) {
          parameter.leistung_kw = formData.leistung_kw
          if (device.suggested_investition_typ === 'wechselrichter') {
            parameter.leistung_ac_kw = formData.leistung_kw
          }
        }

        const investitionData: InvestitionCreate = {
          anlage_id: wizardState.anlageId,
          typ: device.suggested_investition_typ as InvestitionCreate['typ'],
          bezeichnung: formData.bezeichnung,
          anschaffungsdatum: formData.kaufdatum || undefined,
          anschaffungskosten_gesamt: formData.kaufpreis || undefined,
          parameter: Object.keys(parameter).length > 0 ? parameter : undefined,
          aktiv: true,
        }

        const newInvestition = await investitionenApi.create(investitionData)
        created.push(newInvestition)
        createdIds.push(newInvestition.id)
      }

      setCreatedInvestitionen(created)
      setWizardState(prev => ({
        ...prev,
        createdInvestitionen: [...prev.createdInvestitionen, ...createdIds],
      }))

      nextStep()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Fehler beim Erstellen der Investitionen')
    } finally {
      setIsLoading(false)
    }
  }, [wizardState.anlageId, discoveryResult, selectedDevices, investitionFormData, nextStep])

  // PV-Modul hinzufügen
  const addPVModul = useCallback((modul: Omit<PVModulData, 'id'>) => {
    const newModul: PVModulData = {
      ...modul,
      id: `pv-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`,
    }
    setWizardState(prev => ({
      ...prev,
      pvModule: [...prev.pvModule, newModul],
    }))
  }, [])

  // PV-Modul aktualisieren
  const updatePVModul = useCallback((id: string, data: Partial<PVModulData>) => {
    setWizardState(prev => ({
      ...prev,
      pvModule: prev.pvModule.map(m =>
        m.id === id ? { ...m, ...data } : m
      ),
    }))
  }, [])

  // PV-Modul entfernen
  const removePVModul = useCallback((id: string) => {
    setWizardState(prev => ({
      ...prev,
      pvModule: prev.pvModule.filter(m => m.id !== id),
    }))
  }, [])

  // PV-Module als Investitionen speichern
  const savePVModule = useCallback(async () => {
    if (!wizardState.anlageId) {
      setError('Keine Anlage vorhanden')
      return
    }

    if (wizardState.pvModule.length === 0) {
      // Keine Module, einfach weiter
      nextStep()
      return
    }

    setIsLoading(true)
    setError(null)

    const createdIds: number[] = []

    try {
      for (const modul of wizardState.pvModule) {
        const investitionData: InvestitionCreate = {
          anlage_id: wizardState.anlageId,
          typ: 'pv-module',
          bezeichnung: modul.bezeichnung,
          ha_entity_id: modul.ha_entity_id,
          parameter: {
            leistung_kwp: modul.leistung_kwp,
            ausrichtung: modul.ausrichtung,
            neigung_grad: modul.neigung_grad,
          },
          aktiv: true,
        }

        const newInvestition = await investitionenApi.create(investitionData)
        createdIds.push(newInvestition.id)
      }

      setWizardState(prev => ({
        ...prev,
        createdInvestitionen: [...prev.createdInvestitionen, ...createdIds],
      }))

      nextStep()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Fehler beim Speichern der PV-Module')
    } finally {
      setIsLoading(false)
    }
  }, [wizardState.anlageId, wizardState.pvModule, nextStep])

  // Wizard abschließen
  const completeWizard = useCallback(() => {
    setWizardState(prev => ({
      ...prev,
      completed: true,
      currentStep: 'complete',
    }))
    setStep('complete')
  }, [])

  // Wizard zurücksetzen
  const resetWizard = useCallback(() => {
    localStorage.removeItem(WIZARD_STATE_KEY)
    setWizardState(INITIAL_STATE)
    setStep('welcome')
    setAnlage(null)
    setStrompreis(null)
    setDiscoveryResult(null)
    setSelectedDevices(new Set())
    setCreatedInvestitionen([])
    setInvestitionFormData({})
    setError(null)
  }, [])

  // Computed: Kann zum nächsten Schritt?
  const canProceed = (() => {
    switch (step) {
      case 'welcome':
        return true
      case 'anlage':
        return !!wizardState.anlageId
      case 'ha-connection':
        return true // Kann immer weitergehen (überspringen möglich)
      case 'strompreise':
        return !!wizardState.strompreisId
      case 'pv-module':
        return true // PV-Module sind optional aber empfohlen
      case 'discovery':
        return true // Kann weitergehen auch ohne Auswahl
      case 'investitionen':
        return true // Investitionen sind optional
      case 'summary':
        return true
      default:
        return false
    }
  })()

  // Computed: Fortschritt in Prozent
  const progress = Math.round((STEP_ORDER.indexOf(step) / (STEP_ORDER.length - 1)) * 100)

  // Computed: Investitionen die bearbeitet werden sollen
  const investitionenToEdit = discoveryResult?.devices.filter(
    d => selectedDevices.has(d.id) && !d.already_configured && d.suggested_investition_typ
  ) ?? []

  return {
    // State
    step,
    wizardState,
    isLoading,
    error,

    // Daten
    anlage,
    strompreis,
    haConnected,
    haVersion,
    discoveryResult,
    selectedDevices,
    createdInvestitionen,

    // Investitions-Bearbeitung
    investitionenToEdit,
    investitionFormData,

    // Actions
    goToStep,
    nextStep,
    prevStep,
    skipStep,

    createAnlage,
    checkHAConnection,
    createStrompreis,
    useDefaultStrompreise,
    runDiscovery,
    toggleDevice,
    selectAllDevices,
    deselectAllDevices,
    updateInvestitionFormData,
    createInvestitionen,
    pvModule: wizardState.pvModule,
    addPVModul,
    updatePVModul,
    removePVModul,
    savePVModule,
    completeWizard,
    resetWizard,

    // Computed
    canProceed,
    progress,
  }
}
