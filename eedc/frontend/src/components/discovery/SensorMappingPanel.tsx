/**
 * SensorMappingPanel - Sensor-Zuordnungs-Vorschläge
 */

import { Sun, ArrowUpFromLine, ArrowDownToLine, Battery, BatteryCharging } from 'lucide-react'
import type { SensorMappingSuggestions, DiscoveredSensor } from '../../api/ha'

interface SelectedMappings {
  pv_erzeugung: string | null
  einspeisung: string | null
  netzbezug: string | null
  batterie_ladung: string | null
  batterie_entladung: string | null
}

interface SensorMappingPanelProps {
  suggestions: SensorMappingSuggestions
  selectedMappings: SelectedMappings
  onMappingChange: (field: keyof SelectedMappings, entityId: string | null) => void
  onApplyBest: () => void
}

interface MappingFieldProps {
  label: string
  icon: typeof Sun
  field: keyof SelectedMappings
  suggestions: DiscoveredSensor[]
  value: string | null
  onChange: (entityId: string | null) => void
}

function MappingField({ label, icon: Icon, suggestions, value, onChange }: MappingFieldProps) {
  const hasSuggestions = suggestions.length > 0

  return (
    <div className="flex items-start gap-3 p-3 rounded-lg bg-gray-50 dark:bg-gray-700/50">
      <div className="p-2 rounded-lg bg-white dark:bg-gray-700 shadow-sm">
        <Icon className="w-4 h-4 text-amber-600 dark:text-amber-400" />
      </div>

      <div className="flex-1 min-w-0">
        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
          {label}
        </label>

        <select
          value={value || ''}
          onChange={(e) => onChange(e.target.value || null)}
          className={`
            w-full px-3 py-2 text-sm rounded-lg border
            bg-white dark:bg-gray-800
            border-gray-300 dark:border-gray-600
            text-gray-900 dark:text-white
            focus:ring-2 focus:ring-amber-500 focus:border-amber-500
            ${!hasSuggestions ? 'opacity-50' : ''}
          `}
          disabled={!hasSuggestions}
        >
          <option value="">
            {hasSuggestions ? '-- Nicht zugeordnet --' : '-- Kein Sensor gefunden --'}
          </option>
          {suggestions.map((sensor) => (
            <option key={sensor.entity_id} value={sensor.entity_id}>
              {sensor.friendly_name || sensor.entity_id}
              {sensor.confidence >= 80 && ' ★'}
            </option>
          ))}
        </select>

        {/* Bester Vorschlag Info */}
        {hasSuggestions && suggestions[0].confidence >= 70 && !value && (
          <p className="text-xs text-amber-600 dark:text-amber-400 mt-1">
            Empfehlung: {suggestions[0].friendly_name || suggestions[0].entity_id}
          </p>
        )}

        {/* Aktuell ausgewählt */}
        {value && (
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-1 truncate">
            {value}
          </p>
        )}
      </div>
    </div>
  )
}

export default function SensorMappingPanel({
  suggestions,
  selectedMappings,
  onMappingChange,
  onApplyBest,
}: SensorMappingPanelProps) {
  const totalSuggestions =
    suggestions.pv_erzeugung.length +
    suggestions.einspeisung.length +
    suggestions.netzbezug.length +
    suggestions.batterie_ladung.length +
    suggestions.batterie_entladung.length

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold text-gray-900 dark:text-white">
            Sensor-Zuordnungen
          </h3>
          <p className="text-xs text-gray-500 dark:text-gray-400">
            Für Monatsdaten-Import aus Home Assistant
          </p>
        </div>

        {totalSuggestions > 0 && (
          <button
            onClick={onApplyBest}
            className="text-xs px-3 py-1.5 rounded-lg bg-amber-100 text-amber-700 hover:bg-amber-200 dark:bg-amber-900/30 dark:text-amber-400 dark:hover:bg-amber-900/50 transition-colors"
          >
            Beste übernehmen
          </button>
        )}
      </div>

      {/* Mapping Fields */}
      <div className="space-y-3">
        <MappingField
          label="PV-Erzeugung"
          icon={Sun}
          field="pv_erzeugung"
          suggestions={suggestions.pv_erzeugung}
          value={selectedMappings.pv_erzeugung}
          onChange={(v) => onMappingChange('pv_erzeugung', v)}
        />

        <MappingField
          label="Einspeisung"
          icon={ArrowUpFromLine}
          field="einspeisung"
          suggestions={suggestions.einspeisung}
          value={selectedMappings.einspeisung}
          onChange={(v) => onMappingChange('einspeisung', v)}
        />

        <MappingField
          label="Netzbezug"
          icon={ArrowDownToLine}
          field="netzbezug"
          suggestions={suggestions.netzbezug}
          value={selectedMappings.netzbezug}
          onChange={(v) => onMappingChange('netzbezug', v)}
        />

        <MappingField
          label="Batterie Ladung"
          icon={BatteryCharging}
          field="batterie_ladung"
          suggestions={suggestions.batterie_ladung}
          value={selectedMappings.batterie_ladung}
          onChange={(v) => onMappingChange('batterie_ladung', v)}
        />

        <MappingField
          label="Batterie Entladung"
          icon={Battery}
          field="batterie_entladung"
          suggestions={suggestions.batterie_entladung}
          value={selectedMappings.batterie_entladung}
          onChange={(v) => onMappingChange('batterie_entladung', v)}
        />
      </div>

      {/* Info */}
      <p className="text-xs text-gray-400 dark:text-gray-500 italic">
        Hinweis: Sensor-Zuordnungen werden in der Add-on-Konfiguration gespeichert.
        Änderungen hier dienen nur zur Vorschau.
      </p>
    </div>
  )
}
