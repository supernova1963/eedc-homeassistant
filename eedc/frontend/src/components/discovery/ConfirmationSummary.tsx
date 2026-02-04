/**
 * ConfirmationSummary - Zusammenfassung vor dem Erstellen
 */

import { Car, BatteryCharging, Zap, Sun, Server, CheckCircle, AlertCircle } from 'lucide-react'
import type { DiscoveredDevice } from '../../api/ha'

interface ConfirmationSummaryProps {
  devicesToCreate: DiscoveredDevice[]
  onConfirm: () => void
  onBack: () => void
  loading?: boolean
}

const DEVICE_ICONS: Record<string, typeof Car> = {
  ev: Car,
  wallbox: BatteryCharging,
  battery: Zap,
  inverter: Sun,
}

const TYPE_LABELS: Record<string, string> = {
  'e-auto': 'E-Auto',
  'wallbox': 'Wallbox',
  'speicher': 'Speicher',
  'wechselrichter': 'Wechselrichter',
}

export default function ConfirmationSummary({
  devicesToCreate,
  onConfirm,
  onBack,
  loading = false,
}: ConfirmationSummaryProps) {
  if (devicesToCreate.length === 0) {
    return (
      <div className="text-center py-8">
        <AlertCircle className="w-12 h-12 text-amber-500 mx-auto mb-4" />
        <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-2">
          Keine Geräte ausgewählt
        </h3>
        <p className="text-gray-500 dark:text-gray-400 mb-6">
          Bitte wähle mindestens ein Gerät aus, das als Investition angelegt werden soll.
        </p>
        <button
          onClick={onBack}
          className="px-4 py-2 rounded-lg bg-gray-100 text-gray-700 hover:bg-gray-200 dark:bg-gray-700 dark:text-gray-300 dark:hover:bg-gray-600 transition-colors"
        >
          Zurück zur Auswahl
        </button>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="text-center">
        <CheckCircle className="w-12 h-12 text-green-500 mx-auto mb-4" />
        <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-2">
          Zusammenfassung
        </h3>
        <p className="text-gray-500 dark:text-gray-400">
          Folgende {devicesToCreate.length} Investition{devicesToCreate.length !== 1 ? 'en' : ''} werden erstellt:
        </p>
      </div>

      {/* Liste der Geräte */}
      <div className="bg-gray-50 dark:bg-gray-700/50 rounded-lg p-4 space-y-3">
        {devicesToCreate.map((device) => {
          const Icon = DEVICE_ICONS[device.device_type] || Server
          const typLabel = device.suggested_investition_typ
            ? TYPE_LABELS[device.suggested_investition_typ] || device.suggested_investition_typ
            : 'Unbekannt'

          return (
            <div
              key={device.id}
              className="flex items-center gap-3 p-3 bg-white dark:bg-gray-800 rounded-lg"
            >
              <div className="p-2 rounded-lg bg-amber-100 dark:bg-amber-900/30">
                <Icon className="w-5 h-5 text-amber-600 dark:text-amber-400" />
              </div>

              <div className="flex-1 min-w-0">
                <p className="font-medium text-gray-900 dark:text-white">
                  {device.suggested_parameters.bezeichnung as string || device.name}
                </p>
                <div className="flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400">
                  <span>{typLabel}</span>
                  <span className="text-gray-300 dark:text-gray-600">|</span>
                  <span className="text-xs px-1.5 py-0.5 rounded bg-gray-100 dark:bg-gray-700">
                    {device.integration.toUpperCase()}
                  </span>
                </div>
              </div>
            </div>
          )
        })}
      </div>

      {/* Hinweis */}
      <div className="flex items-start gap-2 p-3 bg-blue-50 dark:bg-blue-900/20 rounded-lg">
        <AlertCircle className="w-5 h-5 text-blue-500 flex-shrink-0 mt-0.5" />
        <div className="text-sm text-blue-700 dark:text-blue-300">
          <p>Die Investitionen werden mit Standardwerten erstellt.</p>
          <p className="mt-1">Du kannst die Details später unter "Investitionen" anpassen.</p>
        </div>
      </div>

      {/* Buttons */}
      <div className="flex gap-3">
        <button
          onClick={onBack}
          disabled={loading}
          className="flex-1 px-4 py-2 rounded-lg bg-gray-100 text-gray-700 hover:bg-gray-200 dark:bg-gray-700 dark:text-gray-300 dark:hover:bg-gray-600 transition-colors disabled:opacity-50"
        >
          Zurück
        </button>
        <button
          onClick={onConfirm}
          disabled={loading}
          className="flex-1 px-4 py-2 rounded-lg bg-amber-500 text-white hover:bg-amber-600 transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
        >
          {loading ? (
            <>
              <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
              </svg>
              <span>Erstelle...</span>
            </>
          ) : (
            <span>Investitionen erstellen</span>
          )}
        </button>
      </div>
    </div>
  )
}
