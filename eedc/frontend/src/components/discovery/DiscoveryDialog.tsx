/**
 * DiscoveryDialog - Hauptdialog für Home Assistant Auto-Discovery
 */

import { useEffect } from 'react'
import { Search, Wifi, WifiOff, AlertTriangle, CheckCircle2 } from 'lucide-react'
import Modal from '../ui/Modal'
import DeviceCard from './DeviceCard'
import SensorMappingPanel from './SensorMappingPanel'
import ConfirmationSummary from './ConfirmationSummary'
import { useDiscovery } from '../../hooks/useDiscovery'
import { investitionenApi } from '../../api/investitionen'
import type { InvestitionCreate } from '../../types'

interface DiscoveryDialogProps {
  isOpen: boolean
  onClose: () => void
  anlageId: number
  onInvestitionenCreated?: () => void
}

export default function DiscoveryDialog({
  isOpen,
  onClose,
  anlageId,
  onInvestitionenCreated,
}: DiscoveryDialogProps) {
  const {
    step,
    discoveryResult,
    selectedDevices,
    selectedMappings,
    error,
    startDiscovery,
    toggleDevice,
    selectAllDevices,
    deselectAllDevices,
    setMapping,
    applyBestMappings,
    goToStep,
    reset,
    devicesToCreate,
  } = useDiscovery()

  // Discovery starten wenn Dialog öffnet
  useEffect(() => {
    if (isOpen && step === 'idle') {
      startDiscovery(anlageId)
    }
  }, [isOpen, step, anlageId, startDiscovery])

  // Reset beim Schließen
  const handleClose = () => {
    reset()
    onClose()
  }

  // Investitionen erstellen
  const handleCreateInvestitionen = async () => {
    goToStep('creating')

    try {
      for (const device of devicesToCreate) {
        const investitionData: InvestitionCreate = {
          anlage_id: anlageId,
          typ: device.suggested_investition_typ as InvestitionCreate['typ'],
          bezeichnung: (device.suggested_parameters.bezeichnung as string) || device.name,
          hersteller: (device.suggested_parameters.hersteller as string) || device.manufacturer || undefined,
          kaufdatum: new Date().toISOString().split('T')[0],
          kaufpreis: 0, // Muss später ausgefüllt werden
          aktiv: true,
        }

        // Typ-spezifische Parameter
        if (device.suggested_investition_typ === 'e-auto') {
          investitionData.batterie_kwh = (device.suggested_parameters.batterie_kwh as number) || undefined
        }

        await investitionenApi.create(investitionData)
      }

      goToStep('done')
      onInvestitionenCreated?.()
    } catch (e) {
      goToStep('error')
    }
  }

  // Title basierend auf Step
  const getTitle = (): string => {
    switch (step) {
      case 'scanning':
        return 'Home Assistant durchsuchen...'
      case 'results':
        return 'Gefundene Geräte'
      case 'confirmation':
        return 'Bestätigung'
      case 'creating':
        return 'Erstelle Investitionen...'
      case 'done':
        return 'Fertig!'
      case 'error':
        return 'Fehler'
      default:
        return 'Auto-Discovery'
    }
  }

  return (
    <Modal isOpen={isOpen} onClose={handleClose} title={getTitle()} size="lg">
      {/* Scanning State */}
      {step === 'scanning' && (
        <div className="py-12 text-center">
          <div className="relative mx-auto w-16 h-16 mb-6">
            <Search className="w-16 h-16 text-amber-500 animate-pulse" />
            <div className="absolute inset-0 border-4 border-amber-500/30 rounded-full animate-ping" />
          </div>
          <p className="text-gray-600 dark:text-gray-400">
            Durchsuche Home Assistant nach Geräten...
          </p>
        </div>
      )}

      {/* Error State */}
      {step === 'error' && (
        <div className="py-12 text-center">
          <WifiOff className="w-16 h-16 text-red-500 mx-auto mb-4" />
          <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-2">
            Verbindung fehlgeschlagen
          </h3>
          <p className="text-gray-500 dark:text-gray-400 mb-6">
            {error || 'Keine Verbindung zu Home Assistant möglich.'}
          </p>
          <div className="flex gap-3 justify-center">
            <button
              onClick={handleClose}
              className="px-4 py-2 rounded-lg bg-gray-100 text-gray-700 hover:bg-gray-200 dark:bg-gray-700 dark:text-gray-300 dark:hover:bg-gray-600 transition-colors"
            >
              Schließen
            </button>
            <button
              onClick={() => startDiscovery(anlageId)}
              className="px-4 py-2 rounded-lg bg-amber-500 text-white hover:bg-amber-600 transition-colors"
            >
              Erneut versuchen
            </button>
          </div>
        </div>
      )}

      {/* Results State */}
      {step === 'results' && discoveryResult && (
        <div className="space-y-6">
          {/* HA Status */}
          <div className="flex items-center gap-2 text-sm">
            {discoveryResult.ha_connected ? (
              <>
                <Wifi className="w-4 h-4 text-green-500" />
                <span className="text-green-600 dark:text-green-400">Home Assistant verbunden</span>
              </>
            ) : (
              <>
                <WifiOff className="w-4 h-4 text-red-500" />
                <span className="text-red-600 dark:text-red-400">Nicht verbunden</span>
              </>
            )}
          </div>

          {/* Warnings */}
          {discoveryResult.warnings.length > 0 && (
            <div className="p-3 bg-amber-50 dark:bg-amber-900/20 rounded-lg">
              <div className="flex items-start gap-2">
                <AlertTriangle className="w-5 h-5 text-amber-500 flex-shrink-0 mt-0.5" />
                <div className="text-sm text-amber-700 dark:text-amber-300">
                  {discoveryResult.warnings.map((w, i) => (
                    <p key={i}>{w}</p>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* Geräte */}
          <div>
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-semibold text-gray-900 dark:text-white">
                Gefundene Geräte ({discoveryResult.devices.length})
              </h3>
              {discoveryResult.devices.filter(d => !d.already_configured && d.suggested_investition_typ).length > 0 && (
                <div className="flex gap-2">
                  <button
                    onClick={deselectAllDevices}
                    className="text-xs text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-300"
                  >
                    Keine
                  </button>
                  <span className="text-gray-300 dark:text-gray-600">|</span>
                  <button
                    onClick={selectAllDevices}
                    className="text-xs text-amber-600 hover:text-amber-700 dark:text-amber-400 dark:hover:text-amber-300"
                  >
                    Alle
                  </button>
                </div>
              )}
            </div>

            {discoveryResult.devices.length === 0 ? (
              <div className="text-center py-8 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
                <p className="text-gray-500 dark:text-gray-400">
                  Keine Geräte gefunden.
                </p>
                <p className="text-sm text-gray-400 dark:text-gray-500 mt-1">
                  Unterstützt: SMA, evcc, Smart, Wallbox
                </p>
              </div>
            ) : (
              <div className="grid gap-3 sm:grid-cols-2">
                {discoveryResult.devices.map((device) => (
                  <DeviceCard
                    key={device.id}
                    device={device}
                    selected={selectedDevices.has(device.id)}
                    onToggle={() => toggleDevice(device.id)}
                  />
                ))}
              </div>
            )}
          </div>

          {/* Sensor Mappings */}
          <div className="border-t border-gray-200 dark:border-gray-700 pt-6">
            <SensorMappingPanel
              suggestions={discoveryResult.sensor_mappings}
              allEnergySensors={discoveryResult.all_energy_sensors}
              selectedMappings={selectedMappings}
              onMappingChange={setMapping}
              onApplyBest={applyBestMappings}
            />
          </div>

          {/* Buttons */}
          <div className="flex gap-3 pt-4 border-t border-gray-200 dark:border-gray-700">
            <button
              onClick={handleClose}
              className="flex-1 px-4 py-2 rounded-lg bg-gray-100 text-gray-700 hover:bg-gray-200 dark:bg-gray-700 dark:text-gray-300 dark:hover:bg-gray-600 transition-colors"
            >
              Abbrechen
            </button>
            <button
              onClick={() => goToStep('confirmation')}
              disabled={selectedDevices.size === 0}
              className="flex-1 px-4 py-2 rounded-lg bg-amber-500 text-white hover:bg-amber-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Weiter ({selectedDevices.size} ausgewählt)
            </button>
          </div>
        </div>
      )}

      {/* Confirmation State */}
      {step === 'confirmation' && (
        <ConfirmationSummary
          devicesToCreate={devicesToCreate}
          onConfirm={handleCreateInvestitionen}
          onBack={() => goToStep('results')}
        />
      )}

      {/* Creating State */}
      {step === 'creating' && (
        <div className="py-12 text-center">
          <div className="mx-auto w-16 h-16 mb-6">
            <svg className="animate-spin w-16 h-16 text-amber-500" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
            </svg>
          </div>
          <p className="text-gray-600 dark:text-gray-400">
            Erstelle {devicesToCreate.length} Investition{devicesToCreate.length !== 1 ? 'en' : ''}...
          </p>
        </div>
      )}

      {/* Done State */}
      {step === 'done' && (
        <div className="py-12 text-center">
          <CheckCircle2 className="w-16 h-16 text-green-500 mx-auto mb-4" />
          <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-2">
            Erfolgreich erstellt!
          </h3>
          <p className="text-gray-500 dark:text-gray-400 mb-6">
            {devicesToCreate.length} Investition{devicesToCreate.length !== 1 ? 'en wurden' : ' wurde'} angelegt.
          </p>
          <button
            onClick={handleClose}
            className="px-6 py-2 rounded-lg bg-amber-500 text-white hover:bg-amber-600 transition-colors"
          >
            Fertig
          </button>
        </div>
      )}
    </Modal>
  )
}
