/**
 * React Hook für den Setup-Wizard State Management
 *
 * v1.0.0 - Standalone-Version (ohne HA-Abhängigkeit)
 *
 * Ablauf:
 * 1. Welcome
 * 2. Anlage (+ Auto-Geocoding)
 * 3. Strompreise
 * 4. Investitionen (PV-System mit Wechselrichter + Module, optional weitere)
 * 5. Summary
 * 6. Complete
 */

import { useState, useCallback, useEffect, useRef } from 'react'
import { anlagenApi } from '../api/anlagen'
import { strompreiseApi } from '../api/strompreise'
import { investitionenApi, type InvestitionCreate } from '../api/investitionen'
import { pvgisApi, type GespeichertePrognose } from '../api/pvgis'
import type { Anlage, Strompreis, Investition, InvestitionTyp } from '../types'

// Wizard-Schritte (v1.0: ohne HA)
export type WizardStep =
  | 'welcome'
  | 'anlage'
  | 'strompreise'
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

// Schritt-Reihenfolge (v1.0: ohne HA)
const STEP_ORDER: WizardStep[] = [
  'welcome',
  'anlage',
  'strompreise',
  'investitionen',
  'summary',
  'complete',
]

// Investition-Typ Reihenfolge für Anzeige
export const INVESTITION_TYP_ORDER: InvestitionTyp[] = [
  'wechselrichter',
  'pv-module',
  'speicher',
  'balkonkraftwerk',
  'waermepumpe',
  'e-auto',
  'wallbox',
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
  pvgisPrognose: GespeichertePrognose | null
  pvgisError: string | null

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

  // Strompreise
  createStrompreis: (data: StrompreisCreateData) => Promise<void>
  useDefaultStrompreise: () => Promise<void>

  // Investitionen bearbeiten
  updateInvestition: (id: number, data: Partial<Investition>) => Promise<void>
  deleteInvestition: (id: number) => Promise<void>
  addInvestition: (typ: InvestitionTyp) => Promise<Investition>
  createDefaultPVSystem: () => Promise<void>

  // PVGIS
  fetchPvgisPrognose: () => Promise<void>

  // Abschluss
  completeWizard: () => void
  resetWizard: () => void

  // Computed
  canProceed: boolean
  progress: number
  canFetchPvgis: boolean
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

  // Alle Investitionen der Anlage
  const [investitionen, setInvestitionen] = useState<Investition[]>([])

  // PVGIS Prognose
  const [pvgisPrognose, setPvgisPrognose] = useState<GespeichertePrognose | null>(null)
  const [pvgisError, setPvgisError] = useState<string | null>(null)

  // Pending updates für Debouncing (verhindert Race Conditions)
  const pendingUpdatesRef = useRef<Map<number, { data: Partial<Investition>; timer: ReturnType<typeof setTimeout> }>>(new Map())

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

  // Alle pending updates sofort ausführen (flush)
  const flushPendingUpdates = useCallback(async () => {
    const pending = pendingUpdatesRef.current
    if (pending.size === 0) return

    const promises: Promise<unknown>[] = []
    pending.forEach(({ data, timer }, id) => {
      clearTimeout(timer)
      promises.push(
        investitionenApi.update(id, data).catch(e => {
          console.error(`Fehler beim Update von Investition ${id}:`, e)
        })
      )
    })
    pending.clear()

    await Promise.all(promises)
    await refreshInvestitionen()
  }, [refreshInvestitionen])

  const nextStep = useCallback(async () => {
    // Vor dem Wechsel: Alle pending updates ausführen
    await flushPendingUpdates()

    const currentIndex = STEP_ORDER.indexOf(step)
    if (currentIndex < STEP_ORDER.length - 1) {
      goToStep(STEP_ORDER[currentIndex + 1])
    }
  }, [step, goToStep, flushPendingUpdates])

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

  // Geocoding
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

  // Investition aktualisieren mit Debouncing
  const updateInvestition = useCallback(async (id: number, data: Partial<Investition>) => {
    // 1. Sofort lokalen State optimistisch aktualisieren (für UI-Reaktivität)
    setInvestitionen(prev => prev.map(inv => {
      if (inv.id !== id) return inv
      return {
        ...inv,
        ...data,
        // Parameter speziell mergen
        parameter: data.parameter
          ? { ...(inv.parameter || {}), ...data.parameter }
          : inv.parameter,
      }
    }))

    // 2. Bestehenden Timer für diese Investition löschen
    const existing = pendingUpdatesRef.current.get(id)
    if (existing?.timer) {
      clearTimeout(existing.timer)
    }

    // 3. Daten akkumulieren (merge mit vorherigen pending updates)
    const mergedData = existing?.data
      ? {
          ...existing.data,
          ...data,
          // Parameter speziell mergen wenn beide vorhanden
          parameter: data.parameter
            ? { ...(existing.data.parameter || {}), ...data.parameter }
            : existing.data.parameter,
        }
      : data

    // 4. Neuen Timer setzen (500ms Debounce für API-Call)
    const timer = setTimeout(async () => {
      pendingUpdatesRef.current.delete(id)
      try {
        await investitionenApi.update(id, mergedData)
        // Nicht sofort refreshen - nur bei Fehlern
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Fehler beim Aktualisieren')
        // Bei Fehler: Daten vom Server neu laden
        await refreshInvestitionen()
      }
    }, 500)

    pendingUpdatesRef.current.set(id, { data: mergedData, timer })
  }, [refreshInvestitionen])

  // Investition löschen
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

  // Standard-PV-System erstellen (Wechselrichter + PV-Module)
  const createDefaultPVSystem = useCallback(async () => {
    if (!wizardState.anlageId || !anlage) {
      setError('Keine Anlage vorhanden')
      return
    }

    setIsLoading(true)
    setError(null)

    try {
      // 1. Wechselrichter erstellen
      const wechselrichter = await investitionenApi.create({
        anlage_id: wizardState.anlageId,
        typ: 'wechselrichter',
        bezeichnung: 'Wechselrichter',
        aktiv: true,
        anschaffungsdatum: anlage.installationsdatum,
      } as InvestitionCreate)

      // 2. PV-Module erstellen und dem Wechselrichter zuordnen
      await investitionenApi.create({
        anlage_id: wizardState.anlageId,
        typ: 'pv-module',
        bezeichnung: 'PV-Module',
        leistung_kwp: anlage.leistung_kwp,
        ausrichtung: anlage.ausrichtung,
        neigung_grad: anlage.neigung_grad,
        parent_investition_id: wechselrichter.id,
        aktiv: true,
        anschaffungsdatum: anlage.installationsdatum,
      } as InvestitionCreate)

      // State aktualisieren
      setWizardState(prev => ({
        ...prev,
        createdInvestitionen: [...prev.createdInvestitionen, wechselrichter.id],
      }))

      await refreshInvestitionen()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Fehler beim Erstellen des PV-Systems')
    } finally {
      setIsLoading(false)
    }
  }, [wizardState.anlageId, anlage, refreshInvestitionen])

  // PVGIS Prognose abrufen und speichern
  const fetchPvgisPrognose = useCallback(async () => {
    if (!wizardState.anlageId || !anlage) return

    // Prüfen ob Koordinaten vorhanden
    if (!anlage.latitude || !anlage.longitude) {
      setPvgisError('Keine Koordinaten vorhanden')
      return
    }

    // Prüfen ob PV-Module vorhanden
    const hasPVModules = investitionen.some(i => i.typ === 'pv-module')
    if (!hasPVModules) {
      setPvgisError('Keine PV-Module vorhanden')
      return
    }

    setIsLoading(true)
    setPvgisError(null)

    try {
      const prognose = await pvgisApi.speicherePrognose(wizardState.anlageId)
      setPvgisPrognose(prognose)
    } catch (e) {
      const message = e instanceof Error ? e.message : 'Fehler beim Abrufen der PVGIS-Prognose'
      setPvgisError(message)
    } finally {
      setIsLoading(false)
    }
  }, [wizardState.anlageId, anlage, investitionen])

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
      case 'strompreise':
        return !!wizardState.strompreisId
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

  // Computed: Kann PVGIS abgerufen werden?
  const canFetchPvgis = !!(
    anlage?.latitude &&
    anlage?.longitude &&
    investitionen.some(i => i.typ === 'pv-module')
  )

  return {
    // State
    step,
    wizardState,
    isLoading,
    error,

    // Daten
    anlage,
    strompreis,
    pvgisPrognose,
    pvgisError,

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
    createStrompreis,
    useDefaultStrompreise,
    updateInvestition,
    deleteInvestition,
    addInvestition,
    createDefaultPVSystem,
    fetchPvgisPrognose,
    completeWizard,
    resetWizard,

    // Computed
    canProceed,
    progress,
    canFetchPvgis,
  }
}
