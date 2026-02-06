/**
 * React Hook für den Setup-Wizard State Management
 *
 * v0.8.0 - Refactored Wizard mit vollständiger Investitions-Erfassung
 *
 * Neuer Ablauf:
 * 1. Welcome
 * 2. Anlage (+ Auto-Geocoding)
 * 3. HA-Verbindung prüfen
 * 4. Strompreise
 * 5. Discovery → Alle Geräte rudimentär anlegen
 * 6. Investitionen vervollständigen (eine Seite, alle Typen)
 * 7. Sensor-Konfiguration
 * 8. Summary
 * 9. Complete
 */

import { useState, useCallback, useEffect } from 'react'
import { anlagenApi } from '../api/anlagen'
import { strompreiseApi } from '../api/strompreise'
import { haApi } from '../api/ha'
import { investitionenApi, type InvestitionCreate } from '../api/investitionen'
import type { Anlage, Strompreis, Investition, InvestitionTyp } from '../types'
import type { DiscoveryResult } from '../api/ha'

// Wizard-Schritte (v0.9: sensor-config entfernt - kein HA-Import mehr)
export type WizardStep =
  | 'welcome'
  | 'anlage'
  | 'ha-connection'
  | 'strompreise'
  | 'discovery'
  | 'investitionen'
  | 'summary'
  | 'complete'

// Wizard-State der in LocalStorage gespeichert wird
export interface WizardState {
  completed: boolean
  currentStep: WizardStep
  anlageId: number | null
  strompreisId: number | null
  createdInvestitionen: number[]
  skippedSteps: WizardStep[]
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

// Anlage-Daten für Wizard
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
  wechselrichter_hersteller?: string
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
}

// Schritt-Reihenfolge (v0.9: sensor-config entfernt)
const STEP_ORDER: WizardStep[] = [
  'welcome',
  'anlage',
  'ha-connection',
  'strompreise',
  'discovery',
  'investitionen',
  'summary',
  'complete',
]

// Investition-Typ Reihenfolge für Anzeige
export const INVESTITION_TYP_ORDER: InvestitionTyp[] = [
  'wechselrichter',
  'pv-module',
  'speicher',
  'wallbox',
  'e-auto',
  'waermepumpe',
  'balkonkraftwerk',
  'sonstiges',
]

// Labels für Investitions-Typen
export const INVESTITION_TYP_LABELS: Record<InvestitionTyp, string> = {
  'wechselrichter': 'Wechselrichter',
  'pv-module': 'PV-Module',
  'speicher': 'Speicher',
  'wallbox': 'Wallbox',
  'e-auto': 'E-Auto',
  'waermepumpe': 'Wärmepumpe',
  'balkonkraftwerk': 'Balkonkraftwerk',
  'sonstiges': 'Sonstiges',
}

// Welche Typen können einem Parent zugeordnet werden?
// v0.9: E-Auto ist eigenständig (keine Wallbox-Zuordnung)
export const PARENT_MAPPING: Partial<Record<InvestitionTyp, InvestitionTyp>> = {
  'pv-module': 'wechselrichter',  // Pflicht: PV-Module müssen einem Wechselrichter zugeordnet sein
  'speicher': 'wechselrichter',    // Optional: Für Hybrid-Wechselrichter
}

// Welche Parent-Zuordnungen sind Pflicht?
export const PARENT_REQUIRED: InvestitionTyp[] = ['pv-module']

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

  // Investitionen (alle Investitionen der Anlage)
  investitionen: Investition[]
  refreshInvestitionen: () => Promise<void>

  // Actions
  goToStep: (step: WizardStep) => void
  nextStep: () => void
  prevStep: () => void
  skipStep: () => void

  // Anlage
  createAnlage: (data: AnlageCreateData) => Promise<void>
  geocodeAddress: (plz: string, ort?: string) => Promise<{ latitude: number; longitude: number } | null>

  // HA-Verbindung
  checkHAConnection: () => Promise<void>

  // Strompreise
  createStrompreis: (data: StrompreisCreateData) => Promise<void>
  useDefaultStrompreise: () => Promise<void>

  // Discovery (NEU: erstellt rudimentäre Investitionen)
  runDiscoveryAndCreateInvestitionen: () => Promise<void>

  // Investitionen bearbeiten
  updateInvestition: (id: number, data: Partial<Investition>) => Promise<void>
  deleteInvestition: (id: number) => Promise<void>
  addInvestition: (typ: InvestitionTyp) => Promise<Investition>

  // Abschluss
  completeWizard: () => void
  resetWizard: () => void

  // Computed
  canProceed: boolean
  progress: number
}

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

  // Alle Investitionen der Anlage
  const [investitionen, setInvestitionen] = useState<Investition[]>([])

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

  // Investitionen laden
  const refreshInvestitionen = useCallback(async () => {
    if (!wizardState.anlageId) return
    try {
      const all = await investitionenApi.list(wizardState.anlageId)
      setInvestitionen(all)
    } catch {
      // Ignore
    }
  }, [wizardState.anlageId])

  // Investitionen laden wenn Anlage vorhanden
  useEffect(() => {
    refreshInvestitionen()
  }, [refreshInvestitionen])

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

  // Geocoding (NEU)
  const geocodeAddress = useCallback(async (plz: string, ort?: string) => {
    try {
      const result = await anlagenApi.geocode(plz, ort)
      return { latitude: result.latitude, longitude: result.longitude }
    } catch {
      return null
    }
  }, [])

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
    } catch {
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

  // NEU: Discovery ausführen UND rudimentäre Investitionen erstellen
  const runDiscoveryAndCreateInvestitionen = useCallback(async () => {
    if (!wizardState.anlageId) {
      setError('Keine Anlage vorhanden')
      return
    }

    setIsLoading(true)
    setError(null)

    try {
      // Discovery ausführen
      const manufacturer = anlage?.wechselrichter_hersteller || undefined
      const result = await haApi.discover(wizardState.anlageId, manufacturer)
      setDiscoveryResult(result)

      if (!result.ha_connected) {
        // Kein HA, aber trotzdem weitermachen
        nextStep()
        return
      }

      // Rudimentäre Investitionen für alle erkannten Geräte erstellen
      const createdIds: number[] = []

      for (const device of result.devices) {
        if (device.already_configured || !device.suggested_investition_typ) continue

        try {
          const investitionData: InvestitionCreate = {
            anlage_id: wizardState.anlageId,
            typ: device.suggested_investition_typ as InvestitionCreate['typ'],
            bezeichnung: device.name,
            // Nur rudimentäre Daten, Rest wird in Schritt 6 vervollständigt
            parameter: device.suggested_parameters || {},
            aktiv: true,
          }

          const newInvestition = await investitionenApi.create(investitionData)
          createdIds.push(newInvestition.id)
        } catch {
          // Einzelne Fehler ignorieren, weitermachen
        }
      }

      // State aktualisieren
      setWizardState(prev => ({
        ...prev,
        createdInvestitionen: [...prev.createdInvestitionen, ...createdIds],
      }))

      // Investitionen neu laden
      await refreshInvestitionen()

      nextStep()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Discovery fehlgeschlagen')
    } finally {
      setIsLoading(false)
    }
  }, [wizardState.anlageId, anlage, nextStep, refreshInvestitionen])

  // NEU: Investition aktualisieren
  const updateInvestition = useCallback(async (id: number, data: Partial<Investition>) => {
    try {
      await investitionenApi.update(id, data)
      await refreshInvestitionen()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Fehler beim Aktualisieren')
    }
  }, [refreshInvestitionen])

  // NEU: Investition löschen
  const deleteInvestition = useCallback(async (id: number) => {
    try {
      await investitionenApi.delete(id)
      await refreshInvestitionen()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Fehler beim Löschen')
    }
  }, [refreshInvestitionen])

  // Investition manuell hinzufügen
  const addInvestition = useCallback(async (typ: InvestitionTyp): Promise<Investition> => {
    if (!wizardState.anlageId) {
      throw new Error('Keine Anlage vorhanden')
    }

    setError(null)

    try {
      const newInvestition = await investitionenApi.create({
        anlage_id: wizardState.anlageId,
        typ,
        bezeichnung: `Neue ${INVESTITION_TYP_LABELS[typ]}`,
        aktiv: true,
      })

      await refreshInvestitionen()
      return newInvestition
    } catch (e) {
      const message = e instanceof Error ? e.message : 'Fehler beim Hinzufügen'
      setError(message)
      throw e
    }
  }, [wizardState.anlageId, refreshInvestitionen])

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
    setInvestitionen([])
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
      case 'discovery':
        return true
      case 'investitionen':
        return true // Kann mit 0 Investitionen fortfahren
      case 'summary':
        return true
      default:
        return false
    }
  })()

  // Computed: Fortschritt in Prozent
  const progress = Math.round((STEP_ORDER.indexOf(step) / (STEP_ORDER.length - 1)) * 100)

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

    // Investitionen
    investitionen,
    refreshInvestitionen,

    // Actions
    goToStep,
    nextStep,
    prevStep,
    skipStep,

    createAnlage,
    geocodeAddress,
    checkHAConnection,
    createStrompreis,
    useDefaultStrompreise,
    runDiscoveryAndCreateInvestitionen,
    updateInvestition,
    deleteInvestition,
    addInvestition,
    completeWizard,
    resetWizard,

    // Computed
    canProceed,
    progress,
  }
}
