/**
 * React Hook für Home Assistant Auto-Discovery
 *
 * Verwaltet den Discovery-Prozess und ermöglicht die Auswahl
 * von Geräten und Sensor-Mappings.
 */

import { useState, useCallback } from 'react'
import { haApi } from '../api/ha'
import type {
  DiscoveryResult,
  DiscoveredDevice,
} from '../api/ha'

export type DiscoveryStep = 'idle' | 'scanning' | 'results' | 'confirmation' | 'creating' | 'done' | 'error'

interface SelectedMappings {
  pv_erzeugung: string | null
  einspeisung: string | null
  netzbezug: string | null
  batterie_ladung: string | null
  batterie_entladung: string | null
}

interface UseDiscoveryReturn {
  // State
  step: DiscoveryStep
  discoveryResult: DiscoveryResult | null
  selectedDevices: Set<string>
  selectedMappings: SelectedMappings
  error: string | null

  // Actions
  startDiscovery: (anlageId?: number) => Promise<void>
  toggleDevice: (deviceId: string) => void
  selectAllDevices: () => void
  deselectAllDevices: () => void
  setMapping: (field: keyof SelectedMappings, entityId: string | null) => void
  applyBestMappings: () => void
  goToStep: (step: DiscoveryStep) => void
  reset: () => void

  // Computed
  devicesToCreate: DiscoveredDevice[]
  hasChanges: boolean
}

const EMPTY_MAPPINGS: SelectedMappings = {
  pv_erzeugung: null,
  einspeisung: null,
  netzbezug: null,
  batterie_ladung: null,
  batterie_entladung: null,
}

export function useDiscovery(): UseDiscoveryReturn {
  const [step, setStep] = useState<DiscoveryStep>('idle')
  const [discoveryResult, setDiscoveryResult] = useState<DiscoveryResult | null>(null)
  const [selectedDevices, setSelectedDevices] = useState<Set<string>>(new Set())
  const [selectedMappings, setSelectedMappings] = useState<SelectedMappings>(EMPTY_MAPPINGS)
  const [error, setError] = useState<string | null>(null)

  const startDiscovery = useCallback(async (anlageId?: number) => {
    setStep('scanning')
    setError(null)

    try {
      const result = await haApi.discover(anlageId)
      setDiscoveryResult(result)

      if (!result.ha_connected) {
        setError('Keine Verbindung zu Home Assistant')
        setStep('error')
        return
      }

      // Automatisch nicht-konfigurierte Geräte auswählen
      const autoSelected = new Set<string>()
      for (const device of result.devices) {
        if (!device.already_configured && device.suggested_investition_typ) {
          autoSelected.add(device.id)
        }
      }
      setSelectedDevices(autoSelected)

      // Aktuelle Mappings übernehmen
      setSelectedMappings({
        pv_erzeugung: result.current_mappings.pv_erzeugung,
        einspeisung: result.current_mappings.einspeisung,
        netzbezug: result.current_mappings.netzbezug,
        batterie_ladung: result.current_mappings.batterie_ladung,
        batterie_entladung: result.current_mappings.batterie_entladung,
      })

      setStep('results')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Discovery fehlgeschlagen')
      setStep('error')
    }
  }, [])

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

  const setMapping = useCallback((field: keyof SelectedMappings, entityId: string | null) => {
    setSelectedMappings(prev => ({
      ...prev,
      [field]: entityId,
    }))
  }, [])

  const applyBestMappings = useCallback(() => {
    if (!discoveryResult) return

    const newMappings: SelectedMappings = { ...EMPTY_MAPPINGS }
    const { sensor_mappings } = discoveryResult

    // Beste Vorschläge für jedes Feld auswählen (höchste Confidence)
    if (sensor_mappings.pv_erzeugung.length > 0) {
      newMappings.pv_erzeugung = sensor_mappings.pv_erzeugung[0].entity_id
    }
    if (sensor_mappings.einspeisung.length > 0) {
      newMappings.einspeisung = sensor_mappings.einspeisung[0].entity_id
    }
    if (sensor_mappings.netzbezug.length > 0) {
      newMappings.netzbezug = sensor_mappings.netzbezug[0].entity_id
    }
    if (sensor_mappings.batterie_ladung.length > 0) {
      newMappings.batterie_ladung = sensor_mappings.batterie_ladung[0].entity_id
    }
    if (sensor_mappings.batterie_entladung.length > 0) {
      newMappings.batterie_entladung = sensor_mappings.batterie_entladung[0].entity_id
    }

    setSelectedMappings(newMappings)
  }, [discoveryResult])

  const goToStep = useCallback((newStep: DiscoveryStep) => {
    setStep(newStep)
  }, [])

  const reset = useCallback(() => {
    setStep('idle')
    setDiscoveryResult(null)
    setSelectedDevices(new Set())
    setSelectedMappings(EMPTY_MAPPINGS)
    setError(null)
  }, [])

  // Computed: Geräte die erstellt werden sollen
  const devicesToCreate = discoveryResult?.devices.filter(
    d => selectedDevices.has(d.id) && !d.already_configured && d.suggested_investition_typ
  ) ?? []

  // Computed: Hat der User Änderungen vorgenommen?
  const hasChanges = selectedDevices.size > 0 || Object.values(selectedMappings).some(
    (v, i) => {
      const currentValues = discoveryResult?.current_mappings
        ? [
            discoveryResult.current_mappings.pv_erzeugung,
            discoveryResult.current_mappings.einspeisung,
            discoveryResult.current_mappings.netzbezug,
            discoveryResult.current_mappings.batterie_ladung,
            discoveryResult.current_mappings.batterie_entladung,
          ]
        : [null, null, null, null, null]
      return v !== currentValues[i]
    }
  )

  return {
    // State
    step,
    discoveryResult,
    selectedDevices,
    selectedMappings,
    error,

    // Actions
    startDiscovery,
    toggleDevice,
    selectAllDevices,
    deselectAllDevices,
    setMapping,
    applyBestMappings,
    goToStep,
    reset,

    // Computed
    devicesToCreate,
    hasChanges,
  }
}
