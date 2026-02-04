/**
 * DeviceCard - Zeigt ein entdecktes HA-Gerät an
 */

import { Car, BatteryCharging, Zap, Sun, Server, CheckCircle } from 'lucide-react'
import type { DiscoveredDevice } from '../../api/ha'

interface DeviceCardProps {
  device: DiscoveredDevice
  selected: boolean
  onToggle: () => void
}

const DEVICE_ICONS: Record<string, typeof Car> = {
  ev: Car,
  wallbox: BatteryCharging,
  battery: Zap,
  inverter: Sun,
}

const INTEGRATION_COLORS: Record<string, string> = {
  evcc: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400',
  sma: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400',
  smart: 'bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-400',
  wallbox: 'bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-400',
}

export default function DeviceCard({ device, selected, onToggle }: DeviceCardProps) {
  const Icon = DEVICE_ICONS[device.device_type] || Server
  const integrationColor = INTEGRATION_COLORS[device.integration] || 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300'

  const canSelect = !device.already_configured && device.suggested_investition_typ

  return (
    <div
      className={`
        relative p-4 rounded-lg border-2 transition-all cursor-pointer
        ${selected
          ? 'border-amber-500 bg-amber-50 dark:bg-amber-900/20'
          : 'border-gray-200 dark:border-gray-700 hover:border-gray-300 dark:hover:border-gray-600'
        }
        ${device.already_configured ? 'opacity-60' : ''}
        ${!canSelect ? 'cursor-not-allowed' : ''}
      `}
      onClick={() => canSelect && onToggle()}
    >
      {/* Checkbox */}
      {canSelect && (
        <div className="absolute top-3 right-3">
          <div
            className={`
              w-5 h-5 rounded border-2 flex items-center justify-center
              ${selected
                ? 'bg-amber-500 border-amber-500'
                : 'border-gray-300 dark:border-gray-600'
              }
            `}
          >
            {selected && (
              <svg className="w-3 h-3 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
              </svg>
            )}
          </div>
        </div>
      )}

      {/* Bereits konfiguriert Badge */}
      {device.already_configured && (
        <div className="absolute top-3 right-3 flex items-center gap-1 text-xs text-green-600 dark:text-green-400">
          <CheckCircle className="w-4 h-4" />
          <span>Konfiguriert</span>
        </div>
      )}

      {/* Icon und Name */}
      <div className="flex items-start gap-3">
        <div className={`
          p-2 rounded-lg
          ${selected ? 'bg-amber-100 dark:bg-amber-800/30' : 'bg-gray-100 dark:bg-gray-700'}
        `}>
          <Icon className={`w-6 h-6 ${selected ? 'text-amber-600' : 'text-gray-600 dark:text-gray-400'}`} />
        </div>

        <div className="flex-1 min-w-0">
          <h4 className="font-medium text-gray-900 dark:text-white truncate">
            {device.name}
          </h4>

          <div className="flex flex-wrap gap-2 mt-1">
            {/* Integration Badge */}
            <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${integrationColor}`}>
              {device.integration.toUpperCase()}
            </span>

            {/* Gerätetyp */}
            <span className="text-xs text-gray-500 dark:text-gray-400">
              {device.device_type === 'ev' ? 'E-Auto' :
               device.device_type === 'wallbox' ? 'Wallbox' :
               device.device_type === 'battery' ? 'Speicher' :
               device.device_type === 'inverter' ? 'Wechselrichter' :
               device.device_type}
            </span>

            {/* Confidence */}
            {device.confidence >= 80 && (
              <span className="text-xs text-green-600 dark:text-green-400">
                {device.confidence}% Konfidenz
              </span>
            )}
          </div>

          {/* Hersteller/Model */}
          {(device.manufacturer || device.model) && (
            <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
              {[device.manufacturer, device.model].filter(Boolean).join(' ')}
            </p>
          )}

          {/* Sensoren-Anzahl */}
          {device.sensors.length > 0 && (
            <p className="text-xs text-gray-400 dark:text-gray-500 mt-2">
              {device.sensors.length} Sensor{device.sensors.length !== 1 ? 'en' : ''} gefunden
            </p>
          )}
        </div>
      </div>

      {/* Vorgeschlagene Parameter */}
      {canSelect && Object.keys(device.suggested_parameters).length > 0 && (
        <div className="mt-3 pt-3 border-t border-gray-200 dark:border-gray-700">
          <p className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">
            Wird erstellt als:
          </p>
          <p className="text-sm text-gray-700 dark:text-gray-300">
            {device.suggested_parameters.bezeichnung as string || device.name}
          </p>
        </div>
      )}
    </div>
  )
}
