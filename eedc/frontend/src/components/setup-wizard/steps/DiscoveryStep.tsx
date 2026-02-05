/**
 * DiscoveryStep - Auto-Discovery im Setup-Wizard
 */

import {
  Search,
  Wifi,
  WifiOff,
  RefreshCw,
  ArrowLeft,
  ArrowRight,
  SkipForward,
  CheckCircle2,
  AlertTriangle,
  Car,
  Battery,
  Plug,
  Cpu,
} from 'lucide-react'
import type { DiscoveryResult, DiscoveredDevice } from '../../../api/ha'

interface DiscoveryStepProps {
  isLoading: boolean
  error: string | null
  haConnected: boolean
  discoveryResult: DiscoveryResult | null
  selectedDevices: Set<string>
  onToggleDevice: (deviceId: string) => void
  onSelectAll: () => void
  onDeselectAll: () => void
  onRetry: () => void
  onNext: () => void
  onSkip: () => void
  onBack: () => void
}

// Icon basierend auf Gerätetyp
function getDeviceIcon(device: DiscoveredDevice) {
  switch (device.suggested_investition_typ) {
    case 'e-auto':
      return <Car className="w-5 h-5" />
    case 'speicher':
      return <Battery className="w-5 h-5" />
    case 'wallbox':
      return <Plug className="w-5 h-5" />
    case 'wechselrichter':
      return <Cpu className="w-5 h-5" />
    default:
      return <Cpu className="w-5 h-5" />
  }
}

// Typ-Label
function getTypeLabel(typ: string | null): string {
  switch (typ) {
    case 'e-auto': return 'E-Auto'
    case 'speicher': return 'Speicher'
    case 'wallbox': return 'Wallbox'
    case 'wechselrichter': return 'Wechselrichter'
    case 'pv-module': return 'PV-Module'
    default: return 'Unbekannt'
  }
}

export default function DiscoveryStep({
  isLoading,
  error,
  haConnected,
  discoveryResult,
  selectedDevices,
  onToggleDevice,
  onSelectAll,
  onDeselectAll,
  onRetry,
  onNext,
  onSkip,
  onBack,
}: DiscoveryStepProps) {
  const selectableDevices = discoveryResult?.devices.filter(
    d => !d.already_configured && d.suggested_investition_typ
  ) ?? []

  const selectedCount = selectedDevices.size

  return (
    <div>
      <div className="p-6 md:p-8">
        {/* Header */}
        <div className="flex items-center gap-3 mb-6">
          <div className="w-10 h-10 bg-amber-100 dark:bg-amber-900/30 rounded-xl flex items-center justify-center">
            <Search className="w-5 h-5 text-amber-600 dark:text-amber-400" />
          </div>
          <div>
            <h2 className="text-xl font-bold text-gray-900 dark:text-white">
              Geräte erkennen
            </h2>
            <p className="text-sm text-gray-500 dark:text-gray-400">
              Automatische Erkennung aus Home Assistant
            </p>
          </div>
        </div>

        {/* Loading State */}
        {isLoading && (
          <div className="text-center py-12">
            <div className="relative mx-auto w-16 h-16 mb-6">
              <Search className="w-16 h-16 text-amber-500 animate-pulse" />
              <div className="absolute inset-0 border-4 border-amber-500/30 rounded-full animate-ping" />
            </div>
            <p className="text-gray-600 dark:text-gray-400">
              Durchsuche Home Assistant nach Geräten...
            </p>
          </div>
        )}

        {/* Nicht verbunden */}
        {!isLoading && !haConnected && (
          <div className="text-center py-12">
            <div className="inline-flex items-center justify-center w-16 h-16 bg-gray-100 dark:bg-gray-700 rounded-full mb-4">
              <WifiOff className="w-8 h-8 text-gray-400" />
            </div>
            <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-2">
              Keine Home Assistant Verbindung
            </h3>
            <p className="text-gray-500 dark:text-gray-400 mb-6">
              Die automatische Geräteerkennung ist ohne HA-Verbindung nicht möglich.
            </p>
            <p className="text-sm text-gray-400 dark:text-gray-500">
              Sie können Investitionen später manuell anlegen.
            </p>
          </div>
        )}

        {/* Error State */}
        {!isLoading && haConnected && error && (
          <div className="text-center py-12">
            <div className="inline-flex items-center justify-center w-16 h-16 bg-red-100 dark:bg-red-900/30 rounded-full mb-4">
              <AlertTriangle className="w-8 h-8 text-red-500" />
            </div>
            <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-2">
              Fehler bei der Erkennung
            </h3>
            <p className="text-red-600 dark:text-red-400 mb-6">{error}</p>
            <button
              onClick={onRetry}
              className="inline-flex items-center gap-2 px-4 py-2 bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300 rounded-lg hover:bg-amber-200 dark:hover:bg-amber-900/50 transition-colors"
            >
              <RefreshCw className="w-4 h-4" />
              Erneut versuchen
            </button>
          </div>
        )}

        {/* Ergebnisse */}
        {!isLoading && haConnected && discoveryResult && !error && (
          <div className="space-y-6">
            {/* HA Status */}
            <div className="flex items-center gap-2 text-sm">
              <Wifi className="w-4 h-4 text-green-500" />
              <span className="text-green-600 dark:text-green-400">
                Home Assistant verbunden
              </span>
              {discoveryResult.devices.length > 0 && (
                <span className="text-gray-400 dark:text-gray-500">
                  • {discoveryResult.devices.length} Gerät(e) gefunden
                </span>
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

            {/* Keine Geräte gefunden */}
            {discoveryResult.devices.length === 0 && (
              <div className="text-center py-8 bg-gray-50 dark:bg-gray-700/50 rounded-xl">
                <p className="text-gray-600 dark:text-gray-400 mb-2">
                  Keine unterstützten Geräte gefunden.
                </p>
                <p className="text-sm text-gray-400 dark:text-gray-500">
                  Unterstützt: SMA, evcc, Smart, Wallbox Integrationen
                </p>
                <button
                  onClick={onRetry}
                  className="mt-4 inline-flex items-center gap-2 px-3 py-1.5 text-sm text-amber-600 dark:text-amber-400 hover:text-amber-700 dark:hover:text-amber-300"
                >
                  <RefreshCw className="w-4 h-4" />
                  Erneut suchen
                </button>
              </div>
            )}

            {/* Geräte-Liste */}
            {selectableDevices.length > 0 && (
              <div>
                <div className="flex items-center justify-between mb-3">
                  <h3 className="text-sm font-semibold text-gray-900 dark:text-white">
                    Verfügbare Geräte ({selectableDevices.length})
                  </h3>
                  <div className="flex gap-2 text-xs">
                    <button
                      onClick={onDeselectAll}
                      className="text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-300"
                    >
                      Keine
                    </button>
                    <span className="text-gray-300 dark:text-gray-600">|</span>
                    <button
                      onClick={onSelectAll}
                      className="text-amber-600 hover:text-amber-700 dark:text-amber-400 dark:hover:text-amber-300"
                    >
                      Alle
                    </button>
                  </div>
                </div>

                <div className="grid gap-3 sm:grid-cols-2">
                  {discoveryResult.devices.map((device) => {
                    const isSelectable = !device.already_configured && device.suggested_investition_typ
                    const isSelected = selectedDevices.has(device.id)

                    return (
                      <button
                        key={device.id}
                        type="button"
                        onClick={() => isSelectable && onToggleDevice(device.id)}
                        disabled={!isSelectable}
                        className={`
                          relative p-4 rounded-xl border-2 text-left transition-all
                          ${device.already_configured
                            ? 'border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800/50 opacity-60 cursor-not-allowed'
                            : isSelected
                              ? 'border-amber-500 bg-amber-50 dark:bg-amber-900/20'
                              : 'border-gray-200 dark:border-gray-700 hover:border-amber-300 dark:hover:border-amber-700'
                          }
                        `}
                      >
                        {/* Checkbox */}
                        {isSelectable && (
                          <div className={`
                            absolute top-3 right-3 w-5 h-5 rounded-full border-2 flex items-center justify-center
                            ${isSelected
                              ? 'border-amber-500 bg-amber-500'
                              : 'border-gray-300 dark:border-gray-600'
                            }
                          `}>
                            {isSelected && (
                              <CheckCircle2 className="w-4 h-4 text-white" />
                            )}
                          </div>
                        )}

                        {/* Bereits konfiguriert Badge */}
                        {device.already_configured && (
                          <div className="absolute top-3 right-3 px-2 py-0.5 bg-gray-200 dark:bg-gray-700 text-gray-500 dark:text-gray-400 text-xs rounded-full">
                            Bereits vorhanden
                          </div>
                        )}

                        {/* Content */}
                        <div className="flex items-start gap-3 pr-8">
                          <div className={`
                            w-10 h-10 rounded-lg flex items-center justify-center flex-shrink-0
                            ${isSelected
                              ? 'bg-amber-100 dark:bg-amber-900/30 text-amber-600 dark:text-amber-400'
                              : 'bg-gray-100 dark:bg-gray-700 text-gray-500 dark:text-gray-400'
                            }
                          `}>
                            {getDeviceIcon(device)}
                          </div>
                          <div className="min-w-0">
                            <div className="font-medium text-gray-900 dark:text-white truncate">
                              {device.name}
                            </div>
                            <div className="text-sm text-gray-500 dark:text-gray-400">
                              {device.manufacturer && `${device.manufacturer} • `}
                              {getTypeLabel(device.suggested_investition_typ)}
                            </div>
                            <div className="text-xs text-gray-400 dark:text-gray-500 mt-1">
                              {device.integration}
                            </div>
                          </div>
                        </div>
                      </button>
                    )
                  })}
                </div>
              </div>
            )}

            {/* Bereits konfigurierte Geräte */}
            {discoveryResult.devices.some(d => d.already_configured) && (
              <div className="text-sm text-gray-500 dark:text-gray-400">
                <CheckCircle2 className="w-4 h-4 inline mr-1 text-green-500" />
                {discoveryResult.devices.filter(d => d.already_configured).length} Gerät(e) bereits konfiguriert
              </div>
            )}
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="px-6 md:px-8 py-4 bg-gray-50 dark:bg-gray-700/50 border-t border-gray-200 dark:border-gray-700 flex justify-between">
        <button
          type="button"
          onClick={onBack}
          className="inline-flex items-center gap-2 px-4 py-2 text-gray-700 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          Zurück
        </button>

        <div className="flex gap-3">
          {selectedCount === 0 && (
            <button
              type="button"
              onClick={onSkip}
              disabled={isLoading}
              className="inline-flex items-center gap-2 px-4 py-2 text-gray-600 dark:text-gray-400 hover:text-gray-800 dark:hover:text-gray-200 transition-colors"
            >
              <SkipForward className="w-4 h-4" />
              Überspringen
            </button>
          )}

          <button
            type="button"
            onClick={onNext}
            disabled={isLoading}
            className="inline-flex items-center gap-2 px-6 py-2.5 bg-amber-500 text-white font-medium rounded-lg hover:bg-amber-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {selectedCount > 0 ? (
              <>
                Weiter ({selectedCount} ausgewählt)
                <ArrowRight className="w-4 h-4" />
              </>
            ) : (
              <>
                Weiter
                <ArrowRight className="w-4 h-4" />
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  )
}
