/**
 * LiveSensorSection — Wiederverwendbare Live-Sensor-Zuordnung pro Investition.
 *
 * Zeigt SensorAutocomplete-Felder für leistung_w und optional soc.
 */

import { Activity } from 'lucide-react'
import type { HASensorInfo } from '../../api/sensorMapping'
import { SensorAutocomplete } from './FeldMappingInput'

interface LiveSensorField {
  key: string
  label: string
  einheit: string
  placeholder: string
}

interface LiveSensorSectionProps {
  invId: number
  liveMappings: Record<string, Record<string, string | null>>
  onLiveChange: (invId: number, sensorKey: string, entityId: string | null) => void
  availableSensors: HASensorInfo[]
  fields: LiveSensorField[]
}

export default function LiveSensorSection({
  invId,
  liveMappings,
  onLiveChange,
  availableSensors,
  fields,
}: LiveSensorSectionProps) {
  return (
    <div className="border-t border-gray-200 dark:border-gray-700 pt-4 mt-4 space-y-3">
      <div className="flex items-center gap-2 mb-1">
        <Activity className="w-4 h-4 text-primary-500" />
        <span className="font-medium text-sm text-gray-900 dark:text-white">Live-Sensoren</span>
        <span className="text-xs text-gray-500">— für Live-Dashboard</span>
      </div>

      {fields.map(field => (
        <div key={field.key} className="border border-gray-200 dark:border-gray-700 rounded-lg p-4">
          <div className="flex items-center justify-between mb-2">
            <span className="font-medium text-sm text-gray-900 dark:text-white">{field.label}</span>
            <span className="text-xs text-gray-500">({field.einheit})</span>
          </div>
          <SensorAutocomplete
            value={liveMappings[invId.toString()]?.[field.key]}
            onChange={entityId => onLiveChange(invId, field.key, entityId)}
            sensors={availableSensors}
            placeholder={field.placeholder}
          />
        </div>
      ))}
    </div>
  )
}

// Vordefinierte Feld-Sets pro Investitionstyp
export const LIVE_FIELDS = {
  pv: [
    { key: 'leistung_w', label: 'Leistung', einheit: 'W', placeholder: 'PV-Leistungssensor suchen...' },
  ],
  speicher: [
    { key: 'leistung_w', label: 'Leistung', einheit: 'W, +Ladung/−Entladung', placeholder: 'Batterie-Leistungssensor suchen...' },
    { key: 'soc', label: 'Ladezustand (SoC)', einheit: '%', placeholder: 'SoC-Sensor suchen...' },
  ],
  eauto: [
    { key: 'leistung_w', label: 'Ladeleistung', einheit: 'W', placeholder: 'Lade-Leistungssensor suchen...' },
    { key: 'soc', label: 'Ladezustand (SoC)', einheit: '%', placeholder: 'SoC-Sensor suchen...' },
  ],
  waermepumpe: [
    { key: 'leistung_w', label: 'Leistung', einheit: 'W', placeholder: 'WP-Leistungssensor suchen...' },
  ],
  wallbox: [
    { key: 'leistung_w', label: 'Ladeleistung', einheit: 'W', placeholder: 'Wallbox-Leistungssensor suchen...' },
  ],
  balkonkraftwerk: [
    { key: 'leistung_w', label: 'Leistung', einheit: 'W', placeholder: 'BKW-Leistungssensor suchen...' },
  ],
} as const
