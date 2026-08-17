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
import { ApiError } from '../api/client'
import { anlagenApi } from '../api/anlagen'
import { strompreiseApi } from '../api/strompreise'
import { investitionenApi, type InvestitionCreate } from '../api/investitionen'
import { pvgisApi, type GespeichertePrognose } from '../api/pvgis'
import { TYP_LABELS } from '../lib/constants'
import { monatsersterVon } from '../lib/datum'
import type { Anlage, Strompreis, Investition, InvestitionTyp } from '../types'

// Wizard-Schritte (v1.0: ohne HA)
export type WizardStep =
  | 'welcome'
  | 'anlage'
  | 'strompreise'
  | 'investitionen'
  | 'integration'
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
  // **0 ist Absicht, kein fehlender Wert.** Bis 08.08.2026 leitete der Wizard
  // hier eine EEG-Stufe aus `leistung_kwp` ab (8,2 / 7,1 / 5,8) und schlug
  // damit für jede Anlage über 10 kWp einen zu NIEDRIGEN Satz vor: gestaffelt
  // wird nach installierter Leistung, für die Gesamtanlage gilt der gewichtete
  // Mischsatz. Entfernt statt korrigiert (Gernot, 08.08.2026) — die Sätze
  // ändern sich laufend (für 2027 laufen bereits neue Planungen), eine Tabelle
  // im Code veraltet garantiert, und den geltenden Satz kennt nur der
  // Betreiber. Eine geschätzte Zahl sähe wie eine gepflegte aus; die 0 ist
  // sichtbar unfertig und wird vom Daten-Checker gemeldet, sobald tatsächlich
  // eingespeist wird (`daten_checker/stammdaten.py`).
  einspeiseverguetung_cent_kwh: 0,
  grundpreis_euro_monat: 12.0,
}

// Anlage-Daten für Wizard
interface AnlageCreateData {
  anlagenname: string
  leistung_kwp: number
  installationsdatum?: string
  standort_plz?: string
  standort_ort?: string
  standort_strasse?: string
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
// D2 (2026-07-18): 'integration' nach den Investitionen — die Energy-Dashboard-
// Vorschläge mappen auf Investitionen und brauchen sie daher zuerst.
// SoT für Umfang UND Reihenfolge — SetupWizard leitet seine Anzeige hieraus ab.
export const STEP_ORDER: WizardStep[] = [
  'welcome',
  'anlage',
  'strompreise',
  'investitionen',
  'integration',
  'summary',
  'complete',
]


// Die Parent-Kind-Regel steht NICHT mehr hier. Sie lebte bis 2026-07-31 als
// eigene, unvollständige Kopie in dieser Datei ('speicher' → nur
// 'wechselrichter') — der Setup-Wizard bot damit den Balkonkraftwerk-Parent
// nie an, obwohl Formular und Backend ihn kennen. Ein Kanon, den der
// Einstiegspfad nicht anbietet, ist keiner.
// SoT: components/forms/sections/investitionFormHelpers.ts (`parentTypenFuer`).

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
  //
  // ⚠ N-265: Der Fehler wurde hier bis 17.08.2026 mit `.catch(() => {})`
  // verschluckt. Genau an dieser Stelle ERFÄHRT eedc, dass die gespeicherte
  // Anlage nicht mehr existiert — und warf die Auskunft weg. Die tote ID blieb
  // im Wizard-State, ist als Zahl `truthy` und kam damit durch jeden
  // `if (!wizardState.anlageId)`-Wächter darunter; sichtbar wurde sie erst beim
  // Speichern, als roher Backend-404 „Anlage nicht gefunden".
  useEffect(() => {
    if (!wizardState.anlageId || anlage) return

    let abgebrochen = false
    anlagenApi.get(wizardState.anlageId)
      .then(geladen => { if (!abgebrochen) setAnlage(geladen) })
      .catch((e: unknown) => {
        if (abgebrochen) return
        // NUR der 404 ist eine Aussage über die Anlage. Ein Netz- oder
        // Neustart-Fehler darf den Wizard-Fortschritt nicht wegwerfen.
        if (!(e instanceof ApiError) || e.status !== 404) return
        // Mit der Anlage sind Tarif und Investitionen kaskadiert mitgelöscht
        // (`models/anlage.py:150-155`) — die gemerkten IDs zeigen ebenfalls ins
        // Leere. Zurück auf den Schritt, der eine Anlage anlegt: jeder spätere
        // kann ohne sie nur scheitern.
        setWizardState(prev => ({
          ...prev,
          anlageId: null,
          strompreisId: null,
          createdInvestitionen: [],
        }))
        setStep('anlage')
      })

    return () => { abgebrochen = true }
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
        investitionenApi.update(id, data).catch(() => {})
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
  const geocodeAddress = useCallback(async (plz: string, ort?: string, strasse?: string) => {
    try {
      const result = await anlagenApi.geocode(plz, ort, strasse)
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

    await createStrompreis({
      netzbezug_arbeitspreis_cent_kwh: DEFAULT_STROMPREISE.netzbezug_arbeitspreis_cent_kwh,
      einspeiseverguetung_cent_kwh: DEFAULT_STROMPREISE.einspeiseverguetung_cent_kwh,
      grundpreis_euro_monat: DEFAULT_STROMPREISE.grundpreis_euro_monat,
      // N-257: siehe `monatsersterVon` — der Inbetriebnahme-Tag ist selten der
      // Monatserste, und der Stichtag der Monatsrechnung ist es immer.
      gueltig_ab: monatsersterVon(anlage.installationsdatum) || new Date().toISOString().split('T')[0],
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
      // Pflichtfeld bezeichnung: leeres Feld NICHT speichern. Sonst lehnt das
      // Backend mit min_length-422 ab und refreshInvestitionen() holt den alten
      // Wert zurück (wirkt wie "füllt sich von selbst"). Lokaler State bleibt leer,
      // bis der Nutzer wieder etwas eintippt; finale Validierung beim Wizard-Submit.
      if ('bezeichnung' in mergedData && !(mergedData.bezeichnung ?? '').trim()) {
        return
      }
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
      // PV-Module und DC-Speicher brauchen einen Wechselrichter als Parent
      let parentId: number | undefined
      if (typ === 'pv-module' || typ === 'speicher') {
        const wechselrichter = investitionen.find(i => i.typ === 'wechselrichter')
        if (wechselrichter) {
          parentId = wechselrichter.id
        }
      }

      const newInvestition = await investitionenApi.create({
        anlage_id: wizardState.anlageId,
        typ,
        bezeichnung: `Neue ${TYP_LABELS[typ] ?? typ}`,
        aktiv: true,
        ...(parentId ? { parent_investition_id: parentId } : {}),
      })

      await refreshInvestitionen()
      return newInvestition
    } catch (e) {
      const message = e instanceof Error ? e.message : 'Fehler beim Hinzufügen'
      setError(message)
      throw e
    }
  }, [wizardState.anlageId, investitionen, refreshInvestitionen])

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
      // Ausrichtung/Neigung trägt der User in der PV-Modul-Investition selbst nach.
      await investitionenApi.create({
        anlage_id: wizardState.anlageId,
        typ: 'pv-module',
        bezeichnung: 'PV-Module',
        leistung_kwp: anlage.leistung_kwp,
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
