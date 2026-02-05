/**
 * DiscoveryStep - Auto-Discovery im Setup-Wizard
 *
 * v0.8.0 - Vereinfacht: Führt Discovery aus und erstellt automatisch
 * rudimentäre Investitionen für alle erkannten Geräte.
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
  Flame,
  Sun,
  Plus,
} from 'lucide-react'
import type { DiscoveryResult, DiscoveredDevice } from '../../../api/ha'

interface DiscoveryStepProps {
  isLoading: boolean
  error: string | null
  haConnected: boolean
  discoveryResult: DiscoveryResult | null
  onRunDiscovery: () => Promise<void>
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
    case 'waermepumpe':
      return <Flame className="w-5 h-5" />
    case 'balkonkraftwerk':
      return <Sun className="w-5 h-5" />
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
    case 'waermepumpe': return 'Wärmepumpe'
    case 'balkonkraftwerk': return 'Balkonkraftwerk'
    default: return 'Unbekannt'
  }
}

export default function DiscoveryStep({
  isLoading,
  error,
  haConnected,
  discoveryResult,
  onRunDiscovery,
  onSkip,
  onBack,
}: DiscoveryStepProps) {
  // Neue erkannte Geräte (noch nicht konfiguriert)
  const newDevices = discoveryResult?.devices.filter(
    d => !d.already_configured && d.suggested_investition_typ
  ) ?? []

  // Bereits konfigurierte Geräte
  const existingDevices = discoveryResult?.devices.filter(
    d => d.already_configured
  ) ?? []

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

        {/* Initial State - Kein Discovery gestartet */}
        {!isLoading && !discoveryResult && !error && haConnected && (
          <div className="text-center py-12">
            <div className="inline-flex items-center justify-center w-20 h-20 bg-amber-100 dark:bg-amber-900/30 rounded-full mb-6">
              <Search className="w-10 h-10 text-amber-500" />
            </div>
            <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-2">
              Geräte automatisch erkennen?
            </h3>
            <p className="text-gray-500 dark:text-gray-400 max-w-md mx-auto mb-6">
              EEDC durchsucht Home Assistant nach Wechselrichtern, Speichern, Wallboxen,
              E-Autos, Wärmepumpen und Balkonkraftwerken.
            </p>
            <p className="text-sm text-gray-400 dark:text-gray-500 mb-8">
              Erkannte Geräte werden als Investitionen angelegt und können im nächsten
              Schritt vervollständigt werden.
            </p>
            <button
              onClick={onRunDiscovery}
              className="inline-flex items-center gap-2 px-6 py-3 bg-amber-500 text-white font-medium rounded-xl hover:bg-amber-600 transition-colors shadow-lg hover:shadow-xl"
            >
              <Search className="w-5 h-5" />
              Discovery starten
            </button>
          </div>
        )}

        {/* Loading State */}
        {isLoading && (
          <div className="text-center py-12">
            <div className="relative mx-auto w-16 h-16 mb-6">
              <Search className="w-16 h-16 text-amber-500 animate-pulse" />
              <div className="absolute inset-0 border-4 border-amber-500/30 rounded-full animate-ping" />
            </div>
            <p className="text-gray-600 dark:text-gray-400 mb-2">
              Durchsuche Home Assistant nach Geräten...
            </p>
            <p className="text-sm text-gray-400 dark:text-gray-500">
              Erkannte Geräte werden automatisch als Investitionen angelegt.
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
            <p className="text-gray-500 dark:text-gray-400 mb-4">
              Die automatische Geräteerkennung ist ohne HA-Verbindung nicht möglich.
            </p>
            <p className="text-sm text-gray-400 dark:text-gray-500 mb-6">
              Sie können Investitionen im nächsten Schritt manuell anlegen.
            </p>
            <div className="inline-flex items-center gap-2 px-4 py-2 bg-blue-50 dark:bg-blue-900/20 text-blue-700 dark:text-blue-300 rounded-lg text-sm">
              <Plus className="w-4 h-4" />
              Manuelles Anlegen möglich im nächsten Schritt
            </div>
          </div>
        )}

        {/* Error State */}
        {!isLoading && error && (
          <div className="text-center py-12">
            <div className="inline-flex items-center justify-center w-16 h-16 bg-red-100 dark:bg-red-900/30 rounded-full mb-4">
              <AlertTriangle className="w-8 h-8 text-red-500" />
            </div>
            <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-2">
              Fehler bei der Erkennung
            </h3>
            <p className="text-red-600 dark:text-red-400 mb-6">{error}</p>
            <button
              onClick={onRunDiscovery}
              className="inline-flex items-center gap-2 px-4 py-2 bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300 rounded-lg hover:bg-amber-200 dark:hover:bg-amber-900/50 transition-colors"
            >
              <RefreshCw className="w-4 h-4" />
              Erneut versuchen
            </button>
          </div>
        )}

        {/* Ergebnisse */}
        {!isLoading && discoveryResult && !error && (
          <div className="space-y-6">
            {/* Erfolg-Header */}
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
                <p className="text-sm text-gray-400 dark:text-gray-500 mb-4">
                  Unterstützt: SMA, evcc, Smart, Wallbox, Wärmepumpen-Integrationen
                </p>
                <div className="flex items-center justify-center gap-4">
                  <button
                    onClick={onRunDiscovery}
                    className="inline-flex items-center gap-2 px-3 py-1.5 text-sm text-amber-600 dark:text-amber-400 hover:text-amber-700 dark:hover:text-amber-300"
                  >
                    <RefreshCw className="w-4 h-4" />
                    Erneut suchen
                  </button>
                  <span className="text-gray-300 dark:text-gray-600">|</span>
                  <span className="text-sm text-gray-500 dark:text-gray-400">
                    Manuelles Anlegen im nächsten Schritt möglich
                  </span>
                </div>
              </div>
            )}

            {/* Neu erkannte Geräte (werden angelegt) */}
            {newDevices.length > 0 && (
              <div>
                <div className="flex items-center gap-2 mb-3">
                  <CheckCircle2 className="w-5 h-5 text-green-500" />
                  <h3 className="text-sm font-semibold text-gray-900 dark:text-white">
                    {newDevices.length} Investition{newDevices.length !== 1 ? 'en' : ''} angelegt
                  </h3>
                </div>

                <div className="grid gap-3 sm:grid-cols-2">
                  {newDevices.map((device) => (
                    <div
                      key={device.id}
                      className="p-4 rounded-xl border-2 border-green-200 dark:border-green-800 bg-green-50 dark:bg-green-900/20"
                    >
                      <div className="flex items-start gap-3">
                        <div className="w-10 h-10 rounded-lg flex items-center justify-center flex-shrink-0 bg-green-100 dark:bg-green-900/30 text-green-600 dark:text-green-400">
                          {getDeviceIcon(device)}
                        </div>
                        <div className="min-w-0 flex-1">
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
                        <CheckCircle2 className="w-5 h-5 text-green-500 flex-shrink-0" />
                      </div>
                    </div>
                  ))}
                </div>

                <p className="mt-4 text-sm text-gray-500 dark:text-gray-400">
                  Diese Investitionen können im nächsten Schritt vervollständigt werden
                  (Kaufdatum, Kaufpreis, etc.).
                </p>
              </div>
            )}

            {/* Bereits konfigurierte Geräte */}
            {existingDevices.length > 0 && (
              <div className="text-sm text-gray-500 dark:text-gray-400 flex items-center gap-2">
                <CheckCircle2 className="w-4 h-4 text-gray-400" />
                {existingDevices.length} Gerät(e) bereits konfiguriert (übersprungen)
              </div>
            )}

            {/* Hinweis für manuelle Ergänzungen */}
            {discoveryResult.devices.length > 0 && (
              <div className="p-4 bg-blue-50 dark:bg-blue-900/20 rounded-lg">
                <p className="text-sm text-blue-700 dark:text-blue-300">
                  <strong>Hinweis:</strong> Im nächsten Schritt können Sie weitere Investitionen
                  manuell hinzufügen (z.B. PV-Module) und alle Details vervollständigen.
                </p>
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
          {/* Überspringen wenn noch kein Discovery */}
          {!discoveryResult && !isLoading && (
            <button
              type="button"
              onClick={onSkip}
              className="inline-flex items-center gap-2 px-4 py-2 text-gray-600 dark:text-gray-400 hover:text-gray-800 dark:hover:text-gray-200 transition-colors"
            >
              <SkipForward className="w-4 h-4" />
              Überspringen
            </button>
          )}

          {/* Weiter nach Discovery */}
          {discoveryResult && !isLoading && (
            <button
              type="button"
              onClick={onSkip}
              className="inline-flex items-center gap-2 px-6 py-2.5 bg-amber-500 text-white font-medium rounded-lg hover:bg-amber-600 transition-colors"
            >
              Weiter
              <ArrowRight className="w-4 h-4" />
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
