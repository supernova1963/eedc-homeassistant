/**
 * FeldMappingInput - Wiederverwendbare Komponente für Feld-Zuordnung
 *
 * Unterstützt verschiedene Strategien:
 * - sensor: Direkter HA-Sensor
 * - kwp_verteilung: Anteilig nach kWp
 * - cop_berechnung: COP × Stromverbrauch
 * - ev_quote: Nach Eigenverbrauchsquote
 * - manuell: Manuelle Eingabe
 * - keine: Nicht erfassen
 */

import { useState, useCallback } from 'react'
import { Search, X } from 'lucide-react'
import type { FeldMapping, StrategieTyp, HASensorInfo } from '../../api/sensorMapping'

// =============================================================================
// Types
// =============================================================================

interface StrategieOption {
  value: StrategieTyp
  label: string
  description?: string
}

interface FeldMappingInputProps {
  label: string
  einheit: string
  value: FeldMapping | null
  onChange: (mapping: FeldMapping | null) => void
  availableSensors: HASensorInfo[]
  strategieOptionen: StrategieOption[]
  defaultStrategie?: StrategieTyp
  // Für spezielle Strategien
  kwpAnteil?: number       // Für kwp_verteilung
  copDefault?: number      // Für cop_berechnung
}

// =============================================================================
// SensorAutocomplete Component
// =============================================================================

interface SensorAutocompleteProps {
  value: string | null | undefined
  onChange: (sensorId: string | null) => void
  sensors: HASensorInfo[]
  placeholder?: string
}

function SensorAutocomplete({ value, onChange, sensors, placeholder }: SensorAutocompleteProps) {
  const [search, setSearch] = useState('')
  const [isOpen, setIsOpen] = useState(false)

  const filteredSensors = sensors.filter(
    s =>
      s.entity_id.toLowerCase().includes(search.toLowerCase()) ||
      s.friendly_name?.toLowerCase().includes(search.toLowerCase())
  )

  const selectedSensor = sensors.find(s => s.entity_id === value)

  const handleSelect = useCallback((sensorId: string) => {
    onChange(sensorId)
    setSearch('')
    setIsOpen(false)
  }, [onChange])

  const handleClear = useCallback(() => {
    onChange(null)
    setSearch('')
  }, [onChange])

  return (
    <div className="relative">
      {value && selectedSensor ? (
        <div className="flex items-center gap-2 px-3 py-2 bg-gray-100 dark:bg-gray-700 rounded-lg">
          <span className="flex-1 text-sm truncate">
            {selectedSensor.friendly_name || selectedSensor.entity_id}
          </span>
          <button
            onClick={handleClear}
            className="p-1 hover:bg-gray-200 dark:hover:bg-gray-600 rounded"
          >
            <X className="w-4 h-4 text-gray-500" />
          </button>
        </div>
      ) : (
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
          <input
            type="text"
            value={search}
            onChange={e => {
              setSearch(e.target.value)
              setIsOpen(true)
            }}
            onFocus={() => setIsOpen(true)}
            placeholder={placeholder || 'Sensor suchen...'}
            className="w-full pl-10 pr-4 py-2 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-amber-500"
          />
        </div>
      )}

      {isOpen && !value && (
        <div className="absolute z-10 w-full mt-1 max-h-60 overflow-auto bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg shadow-lg">
          {filteredSensors.length === 0 ? (
            <div className="px-4 py-3 text-sm text-gray-500">
              {search ? 'Keine Sensoren gefunden' : 'Sensor eingeben...'}
            </div>
          ) : (
            filteredSensors.slice(0, 50).map(sensor => (
              <button
                key={sensor.entity_id}
                onClick={() => handleSelect(sensor.entity_id)}
                className="w-full px-4 py-2 text-left hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
              >
                <div className="text-sm font-medium text-gray-900 dark:text-white truncate">
                  {sensor.friendly_name || sensor.entity_id}
                </div>
                <div className="text-xs text-gray-500 truncate">
                  {sensor.entity_id}
                  {sensor.unit && ` (${sensor.unit})`}
                  {sensor.state && ` - ${sensor.state}`}
                </div>
              </button>
            ))
          )}
        </div>
      )}
    </div>
  )
}

// =============================================================================
// FeldMappingInput Component
// =============================================================================

export default function FeldMappingInput({
  label,
  einheit,
  value,
  onChange,
  availableSensors,
  strategieOptionen,
  defaultStrategie = 'sensor',
  kwpAnteil,
  copDefault,
}: FeldMappingInputProps) {
  const currentStrategie = value?.strategie || defaultStrategie

  const handleStrategieChange = (strategie: StrategieTyp) => {
    if (strategie === 'keine') {
      onChange({ strategie: 'keine' })
    } else if (strategie === 'manuell') {
      onChange({ strategie: 'manuell' })
    } else if (strategie === 'sensor') {
      onChange({ strategie: 'sensor', sensor_id: value?.sensor_id || null })
    } else if (strategie === 'kwp_verteilung') {
      onChange({
        strategie: 'kwp_verteilung',
        parameter: { anteil: kwpAnteil || 0, basis_sensor: 'pv_gesamt' },
      })
    } else if (strategie === 'cop_berechnung') {
      onChange({
        strategie: 'cop_berechnung',
        parameter: { cop: copDefault || 3.5, basis_feld: 'stromverbrauch_kwh' },
      })
    } else if (strategie === 'ev_quote') {
      onChange({
        strategie: 'ev_quote',
        parameter: {},
      })
    }
  }

  const handleSensorChange = (sensorId: string | null) => {
    onChange({
      strategie: 'sensor',
      sensor_id: sensorId,
    })
  }

  const handleCopChange = (cop: number) => {
    onChange({
      strategie: 'cop_berechnung',
      parameter: { ...value?.parameter, cop },
    })
  }

  return (
    <div className="border border-gray-200 dark:border-gray-700 rounded-lg p-4">
      <div className="flex items-center justify-between mb-3">
        <div>
          <span className="font-medium text-gray-900 dark:text-white">{label}</span>
          <span className="ml-2 text-sm text-gray-500">({einheit})</span>
        </div>
      </div>

      <div className="space-y-3">
        {strategieOptionen.map(option => (
          <label
            key={option.value}
            className={`
              flex items-start gap-3 p-3 rounded-lg cursor-pointer transition-colors
              ${currentStrategie === option.value
                ? 'bg-amber-50 dark:bg-amber-900/20 ring-1 ring-amber-500'
                : 'hover:bg-gray-50 dark:hover:bg-gray-700/50'
              }
            `}
          >
            <input
              type="radio"
              name={`strategie-${label}`}
              checked={currentStrategie === option.value}
              onChange={() => handleStrategieChange(option.value)}
              className="mt-1 w-4 h-4 text-amber-500 focus:ring-amber-500"
            />
            <div className="flex-1 min-w-0">
              <div className="font-medium text-sm text-gray-900 dark:text-white">
                {option.label}
              </div>
              {option.description && (
                <div className="text-xs text-gray-500 mt-0.5">
                  {option.description}
                </div>
              )}

              {/* Sensor Autocomplete */}
              {currentStrategie === 'sensor' && option.value === 'sensor' && (
                <div className="mt-3">
                  <SensorAutocomplete
                    value={value?.sensor_id}
                    onChange={handleSensorChange}
                    sensors={availableSensors}
                  />
                </div>
              )}

              {/* kWp-Verteilung Info */}
              {currentStrategie === 'kwp_verteilung' && option.value === 'kwp_verteilung' && kwpAnteil !== undefined && (
                <div className="mt-2 text-xs text-amber-600 dark:text-amber-400">
                  {(kwpAnteil * 100).toFixed(1)}% von PV Gesamt
                </div>
              )}

              {/* COP Input */}
              {currentStrategie === 'cop_berechnung' && option.value === 'cop_berechnung' && (
                <div className="mt-3 flex items-center gap-2">
                  <span className="text-sm text-gray-500">COP:</span>
                  <input
                    type="number"
                    step="0.1"
                    min="1"
                    max="10"
                    value={value?.parameter?.cop || copDefault || 3.5}
                    onChange={e => handleCopChange(parseFloat(e.target.value) || 3.5)}
                    className="w-20 px-2 py-1 text-sm bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded focus:outline-none focus:ring-1 focus:ring-amber-500"
                  />
                </div>
              )}
            </div>
          </label>
        ))}
      </div>
    </div>
  )
}

// =============================================================================
// Exports
// =============================================================================

export { SensorAutocomplete }
export type { StrategieOption }
