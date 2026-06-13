/**
 * FeldMappingInput - Wiederverwendbare Komponente für Feld-Zuordnung
 *
 * Strategien (Achse A1, v3.39.0 — auf zwei reduziert):
 * - sensor: Direkter HA-Sensor
 * - keine: Kein Sensor (manuell im Wizard erfassen / bewusst leer)
 */

import { useState, useCallback, useRef, useEffect, useId } from 'react'
import { Search, X, AlertTriangle } from 'lucide-react'
import type { FeldMapping, StrategieTyp, HASensorInfo } from '../../api/sensorMapping'

// Energie-Einheiten für kWh-Slots (#200 — Power-Sensor in kWh-Slot ist Bug-Quelle)
const ENERGIE_EINHEITEN = new Set(['kWh', 'Wh', 'MWh', 'GWh'])

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
  /** Optionaler Hinweistext unter dem Label: erklärt, welchen Wert/Sensortyp das Feld erwartet.
   *  Quelle: Backend-SoT field_definitions (via /monatsdaten/feld-hinweise). */
  hint?: string
  value: FeldMapping | null
  onChange: (mapping: FeldMapping | null) => void
  availableSensors: HASensorInfo[]
  strategieOptionen: StrategieOption[]
  defaultStrategie?: StrategieTyp
}

// =============================================================================
// SensorAutocomplete Component
// =============================================================================

interface SensorAutocompleteProps {
  value: string | null | undefined
  onChange: (sensorId: string | null) => void
  sensors: HASensorInfo[]
  placeholder?: string
  /**
   * Wenn `true` (Default), wird bei Sensoren ohne `state_class` der Badge
   * „keine HA-Statistik" angezeigt — relevant für kumulative kWh-Zähler, weil
   * Vollbackfill/Reaggregate ohne Long-Term-Statistics nicht funktionieren.
   *
   * Bei reinen Live-Leistungs-Sensoren (Watt) ist `state_class` irrelevant —
   * wir lesen den Live-State direkt aus der HA-API. Hier `false` setzen,
   * damit der Badge nicht irreführend für W-Sensoren erscheint
   * (Joachim-PN 2026-05-04, Wattpilot Charging Power).
   */
  requireStatistics?: boolean
}

function SensorAutocomplete({ value, onChange, sensors, placeholder, requireStatistics = true }: SensorAutocompleteProps) {
  const [search, setSearch] = useState('')
  const [isOpen, setIsOpen] = useState(false)
  const [openUp, setOpenUp] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (isOpen && containerRef.current) {
      const rect = containerRef.current.getBoundingClientRect()
      const spaceBelow = window.innerHeight - rect.bottom
      setOpenUp(spaceBelow < 260)
    }
  }, [isOpen])

  useEffect(() => {
    if (!isOpen) return
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { setIsOpen(false); setSearch('') }
    }
    const handleClickOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false); setSearch('')
      }
    }
    document.addEventListener('keydown', handleKeyDown)
    document.addEventListener('mousedown', handleClickOutside)
    return () => {
      document.removeEventListener('keydown', handleKeyDown)
      document.removeEventListener('mousedown', handleClickOutside)
    }
  }, [isOpen])

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

  // Zeige ausgewählten Sensor auch wenn er nicht in der Liste ist (z.B. nach Import)
  const hasValue = value && value.length > 0

  return (
    <div className="relative" ref={containerRef}>
      {hasValue ? (
        <div className={`flex items-center gap-2 px-3 py-2 rounded-lg ${
          selectedSensor
            ? 'bg-gray-100 dark:bg-gray-700'
            : 'bg-amber-50 dark:bg-amber-900/30 border border-amber-300 dark:border-amber-700'
        }`}>
          <span className="flex-1 text-sm truncate flex items-center gap-2">
            <span className="truncate">{selectedSensor?.friendly_name || value}</span>
            {!selectedSensor && (
              <span className="text-xs text-amber-600 dark:text-amber-400 flex-shrink-0">(nicht verfügbar)</span>
            )}
            {requireStatistics && selectedSensor?.has_statistics === false && (
              <span
                className="flex-shrink-0 text-[10px] px-1.5 py-0.5 rounded bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300"
                title="Sensor ohne state_class — fehlt in HA-Long-Term-Statistics. Folge: die Korrektur-Werkzeuge in der Datenverwaltung (Vollbackfill, Verlauf nachrechnen, Per-Tag-Reaggregation) wirken auf diesen Sensor nicht — jeder Aussetzer ist permanent verloren. Empfohlen: state_class via customize.yaml ergänzen."
              >
                keine HA-Statistik
              </span>
            )}
          </span>
          <button
            onClick={handleClear}
            aria-label="Auswahl löschen"
            className="p-1 hover:bg-gray-200 dark:hover:bg-gray-600 rounded"
          >
            <X className="w-4 h-4 text-gray-500" />
          </button>
        </div>
      ) : (
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 dark:text-gray-500" />
          <input
            type="text"
            value={search}
            onChange={e => {
              setSearch(e.target.value)
              setIsOpen(true)
            }}
            onFocus={() => setIsOpen(true)}
            placeholder={placeholder || 'Sensor suchen...'}
            aria-label="Sensor suchen"
            className="w-full pl-10 pr-4 py-2 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-amber-500"
          />
        </div>
      )}

      {isOpen && !value && (
        <div className={`absolute z-10 w-full max-h-60 overflow-auto bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg shadow-lg ${openUp ? 'bottom-full mb-1' : 'mt-1'}`}>
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
                <div className="text-sm font-medium text-gray-900 dark:text-white truncate flex items-center gap-1">
                  <span className="truncate">{sensor.friendly_name || sensor.entity_id}</span>
                  {sensor.has_statistics === false && (
                    <span
                      className="flex-shrink-0 text-[10px] px-1.5 py-0.5 rounded bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300"
                      title="Sensor ohne state_class — fehlt in HA-Long-Term-Statistics. Korrektur-Werkzeuge in der Datenverwaltung wirken auf diesen Sensor nicht."
                    >
                      ohne Statistik
                    </span>
                  )}
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
// UnitMismatchHint — Warnung bei Power-Sensor in kWh-Slot (#200 rcmcronny)
// =============================================================================

interface UnitMismatchHintProps {
  einheit: string
  sensorId: string | null | undefined
  sensors: HASensorInfo[]
}

function UnitMismatchHint({ einheit, sensorId, sensors }: UnitMismatchHintProps) {
  if (einheit !== 'kWh' || !sensorId) return null
  const selected = sensors.find(s => s.entity_id === sensorId)
  // Nicht in Liste (Import / nicht verfügbar) → Einheit unbekannt, keine Warnung
  if (!selected || !selected.unit) return null
  if (ENERGIE_EINHEITEN.has(selected.unit)) return null

  return (
    <div className="mt-2 flex items-start gap-2 rounded-lg border border-amber-300 bg-amber-50 p-3 text-xs text-amber-800 dark:border-amber-700/50 dark:bg-amber-900/20 dark:text-amber-200">
      <AlertTriangle className="mt-0.5 h-4 w-4 flex-shrink-0" />
      <div>
        <span className="font-medium">Einheit „{selected.unit}" passt nicht in einen kWh-Slot.</span>{' '}
        Dieser Slot erwartet einen Energie-Zähler (kWh, Wh, MWh) — der ausgewählte
        Sensor liefert {selected.device_class === 'power' ? 'momentane Leistung' : 'einen anderen Wert'}.
        Wähle einen Energie-Sensor, oder trag den Sensor unten unter „Live-Sensoren (Leistung)"
        ein — daraus wird der Tageswert dann automatisch berechnet.
      </div>
    </div>
  )
}

// =============================================================================
// FeldMappingInput Component
// =============================================================================

export default function FeldMappingInput({
  label,
  einheit,
  hint,
  value,
  onChange,
  availableSensors,
  strategieOptionen,
  defaultStrategie = 'sensor',
}: FeldMappingInputProps) {
  const groupId = useId()
  const currentStrategie = value?.strategie || defaultStrategie

  const handleStrategieChange = (strategie: StrategieTyp) => {
    if (strategie === 'keine') {
      onChange({ strategie: 'keine' })
    } else {
      onChange({ strategie: 'sensor', sensor_id: value?.sensor_id || null })
    }
  }

  const handleSensorChange = (sensorId: string | null) => {
    onChange({
      strategie: 'sensor',
      sensor_id: sensorId,
    })
  }

  return (
    <div className="border border-gray-200 dark:border-gray-700 rounded-lg p-4">
      <div className="flex items-start justify-between mb-3">
        <div>
          <span className="font-medium text-gray-900 dark:text-white">{label}</span>
          <span className="ml-2 text-sm text-gray-500">({einheit})</span>
          {hint && (
            <p className="mt-1 text-xs text-gray-500 dark:text-gray-400 max-w-prose">{hint}</p>
          )}
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
              name={`strategie-${groupId}`}
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
                  <UnitMismatchHint
                    einheit={einheit}
                    sensorId={value?.sensor_id}
                    sensors={availableSensors}
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
