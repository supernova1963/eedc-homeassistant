/**
 * SensorConfigStep - Home Assistant Sensor-Konfiguration
 *
 * v0.8.0 - Neu: Konfiguriert die HA-Sensor-Zuordnung für Monatsdaten-Import.
 * Ersetzt die bisherige config.yaml ha_sensors Konfiguration.
 */

import { useState } from 'react'
import {
  Zap,
  ArrowLeft,
  ArrowRight,
  SkipForward,
  Info,
  AlertCircle,
  List,
  Search,
} from 'lucide-react'
import type { SensorConfig } from '../../../types'
import type { SensorMappingSuggestions, DiscoveredSensor } from '../../../api/ha'

interface SensorConfigStepProps {
  sensorConfig: SensorConfig
  sensorMappings: SensorMappingSuggestions | null
  allEnergySensors: DiscoveredSensor[]
  isLoading: boolean
  error: string | null
  onUpdateConfig: (config: SensorConfig) => void
  onSave: () => Promise<void>
  onSkip: () => void
  onBack: () => void
}

// Sensor-Kategorie Labels
const SENSOR_LABELS: Record<keyof SensorConfig, { label: string; description: string }> = {
  pv_erzeugung: {
    label: 'PV-Erzeugung',
    description: 'Gesamte erzeugte Energie der PV-Anlage (kWh)',
  },
  einspeisung: {
    label: 'Einspeisung',
    description: 'Ins Netz eingespeiste Energie (kWh)',
  },
  netzbezug: {
    label: 'Netzbezug',
    description: 'Aus dem Netz bezogene Energie (kWh)',
  },
  batterie_ladung: {
    label: 'Batterie Ladung',
    description: 'In den Speicher geladene Energie (kWh)',
  },
  batterie_entladung: {
    label: 'Batterie Entladung',
    description: 'Aus dem Speicher entnommene Energie (kWh)',
  },
}

// Einzelner Sensor-Selektor
function SensorSelector({
  field,
  value,
  suggestions,
  allSensors,
  onChange,
}: {
  field: keyof SensorConfig
  value: string | undefined
  suggestions: DiscoveredSensor[]
  allSensors: DiscoveredSensor[]
  onChange: (value: string | undefined) => void
}) {
  const [showAll, setShowAll] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')

  const { label, description } = SENSOR_LABELS[field]

  // Sensoren filtern
  const displaySensors = showAll
    ? searchQuery
      ? allSensors.filter(s =>
          s.entity_id.toLowerCase().includes(searchQuery.toLowerCase()) ||
          s.friendly_name?.toLowerCase().includes(searchQuery.toLowerCase())
        )
      : allSensors
    : suggestions

  // Aktuell ausgewählter Sensor
  const selectedSensor = allSensors.find(s => s.entity_id === value) ||
    suggestions.find(s => s.entity_id === value)

  return (
    <div className="p-4 bg-gray-50 dark:bg-gray-700/50 rounded-xl">
      <div className="flex items-start justify-between mb-3">
        <div>
          <h4 className="font-medium text-gray-900 dark:text-white">{label}</h4>
          <p className="text-sm text-gray-500 dark:text-gray-400">{description}</p>
        </div>
        {suggestions.length > 0 && suggestions[0].confidence && (
          <span className="text-xs px-2 py-1 bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300 rounded-full">
            {Math.round(suggestions[0].confidence * 100)}% Match
          </span>
        )}
      </div>

      {/* Toggle zwischen Vorschlägen und allen Sensoren */}
      <div className="flex items-center gap-2 mb-3">
        <button
          type="button"
          onClick={() => setShowAll(false)}
          className={`
            px-3 py-1.5 text-sm rounded-lg transition-colors
            ${!showAll
              ? 'bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300'
              : 'text-gray-600 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-600'
            }
          `}
        >
          <span className="inline-flex items-center gap-1">
            <Zap className="w-3.5 h-3.5" />
            Vorschläge ({suggestions.length})
          </span>
        </button>
        <button
          type="button"
          onClick={() => setShowAll(true)}
          className={`
            px-3 py-1.5 text-sm rounded-lg transition-colors
            ${showAll
              ? 'bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300'
              : 'text-gray-600 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-600'
            }
          `}
        >
          <span className="inline-flex items-center gap-1">
            <List className="w-3.5 h-3.5" />
            Alle ({allSensors.length})
          </span>
        </button>
      </div>

      {/* Suche (nur bei "Alle") */}
      {showAll && (
        <div className="relative mb-3">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Sensor suchen..."
            className="w-full pl-9 pr-4 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm focus:ring-2 focus:ring-amber-500 focus:border-transparent"
          />
        </div>
      )}

      {/* Sensor-Auswahl */}
      <select
        value={value || ''}
        onChange={(e) => onChange(e.target.value || undefined)}
        className="w-full px-4 py-2.5 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-amber-500 focus:border-transparent"
      >
        <option value="">-- Nicht konfiguriert --</option>
        {displaySensors.map(sensor => (
          <option key={sensor.entity_id} value={sensor.entity_id}>
            {sensor.friendly_name || sensor.entity_id}
            {sensor.current_state ? ` (${sensor.current_state} ${sensor.unit_of_measurement || ''})` : ''}
          </option>
        ))}
      </select>

      {/* Ausgewählter Sensor-Info */}
      {selectedSensor && (
        <div className="mt-2 text-xs text-gray-500 dark:text-gray-400">
          <code className="bg-gray-200 dark:bg-gray-600 px-1.5 py-0.5 rounded">
            {selectedSensor.entity_id}
          </code>
        </div>
      )}
    </div>
  )
}

export default function SensorConfigStep({
  sensorConfig,
  sensorMappings,
  allEnergySensors,
  isLoading,
  error,
  onUpdateConfig,
  onSave,
  onSkip,
  onBack,
}: SensorConfigStepProps) {
  // Anzahl konfigurierter Sensoren
  const configuredCount = Object.values(sensorConfig).filter(v => v).length

  // Update-Handler für einzelnen Sensor
  const handleUpdate = (field: keyof SensorConfig, value: string | undefined) => {
    onUpdateConfig({
      ...sensorConfig,
      [field]: value,
    })
  }

  // Keine Sensoren gefunden
  if (allEnergySensors.length === 0 && !isLoading) {
    return (
      <div>
        <div className="p-6 md:p-8">
          <div className="text-center py-12">
            <div className="inline-flex items-center justify-center w-16 h-16 bg-gray-100 dark:bg-gray-700 rounded-full mb-4">
              <Zap className="w-8 h-8 text-gray-400" />
            </div>
            <h2 className="text-xl font-bold text-gray-900 dark:text-white mb-2">
              Keine Energy-Sensoren gefunden
            </h2>
            <p className="text-gray-500 dark:text-gray-400 max-w-md mx-auto mb-6">
              EEDC konnte keine Energy-Sensoren in Home Assistant finden.
              Die Sensor-Zuordnung kann später unter Einstellungen konfiguriert werden.
            </p>
          </div>
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

          <button
            type="button"
            onClick={onSkip}
            className="inline-flex items-center gap-2 px-6 py-2.5 bg-amber-500 text-white font-medium rounded-lg hover:bg-amber-600 transition-colors"
          >
            Überspringen
            <ArrowRight className="w-4 h-4" />
          </button>
        </div>
      </div>
    )
  }

  return (
    <div>
      <div className="p-6 md:p-8">
        {/* Header */}
        <div className="flex items-center gap-3 mb-6">
          <div className="w-10 h-10 bg-amber-100 dark:bg-amber-900/30 rounded-xl flex items-center justify-center">
            <Zap className="w-5 h-5 text-amber-600 dark:text-amber-400" />
          </div>
          <div>
            <h2 className="text-xl font-bold text-gray-900 dark:text-white">
              Sensor-Zuordnung
            </h2>
            <p className="text-sm text-gray-500 dark:text-gray-400">
              Ordnen Sie die Home Assistant Sensoren den EEDC-Kategorien zu
            </p>
          </div>
        </div>

        {error && (
          <div className="mb-6 p-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg flex items-start gap-3">
            <AlertCircle className="w-5 h-5 text-red-500 flex-shrink-0 mt-0.5" />
            <span className="text-red-700 dark:text-red-300">{error}</span>
          </div>
        )}

        {/* Loading */}
        {isLoading && (
          <div className="text-center py-8">
            <div className="w-8 h-8 border-2 border-amber-500/30 border-t-amber-500 rounded-full animate-spin mx-auto mb-4" />
            <p className="text-gray-500 dark:text-gray-400">Speichere Konfiguration...</p>
          </div>
        )}

        {/* Sensor-Selektoren */}
        {!isLoading && (
          <div className="space-y-4">
            {/* Pflicht-Sensoren */}
            <div>
              <h3 className="text-sm font-semibold text-gray-900 dark:text-white mb-3">
                Wichtige Sensoren
              </h3>
              <div className="space-y-3">
                <SensorSelector
                  field="pv_erzeugung"
                  value={sensorConfig.pv_erzeugung}
                  suggestions={sensorMappings?.pv_erzeugung || []}
                  allSensors={allEnergySensors}
                  onChange={(v) => handleUpdate('pv_erzeugung', v)}
                />
                <SensorSelector
                  field="einspeisung"
                  value={sensorConfig.einspeisung}
                  suggestions={sensorMappings?.einspeisung || []}
                  allSensors={allEnergySensors}
                  onChange={(v) => handleUpdate('einspeisung', v)}
                />
                <SensorSelector
                  field="netzbezug"
                  value={sensorConfig.netzbezug}
                  suggestions={sensorMappings?.netzbezug || []}
                  allSensors={allEnergySensors}
                  onChange={(v) => handleUpdate('netzbezug', v)}
                />
              </div>
            </div>

            {/* Optionale Batterie-Sensoren */}
            <div>
              <h3 className="text-sm font-semibold text-gray-900 dark:text-white mb-3">
                Batterie-Sensoren (optional)
              </h3>
              <div className="space-y-3">
                <SensorSelector
                  field="batterie_ladung"
                  value={sensorConfig.batterie_ladung}
                  suggestions={sensorMappings?.batterie_ladung || []}
                  allSensors={allEnergySensors}
                  onChange={(v) => handleUpdate('batterie_ladung', v)}
                />
                <SensorSelector
                  field="batterie_entladung"
                  value={sensorConfig.batterie_entladung}
                  suggestions={sensorMappings?.batterie_entladung || []}
                  allSensors={allEnergySensors}
                  onChange={(v) => handleUpdate('batterie_entladung', v)}
                />
              </div>
            </div>
          </div>
        )}

        {/* Info-Box */}
        <div className="mt-6 p-4 bg-blue-50 dark:bg-blue-900/20 rounded-lg">
          <p className="text-sm text-blue-700 dark:text-blue-300 flex items-start gap-2">
            <Info className="w-4 h-4 flex-shrink-0 mt-0.5" />
            <span>
              Diese Sensoren werden für den automatischen Import von Monatsdaten aus
              Home Assistant verwendet. Die Konfiguration ersetzt die bisherige
              <code className="mx-1 px-1 py-0.5 bg-blue-100 dark:bg-blue-800 rounded text-xs">
                ha_sensors
              </code>
              Einstellung in der config.yaml.
            </span>
          </p>
        </div>

        {/* Status */}
        <div className="mt-4 text-sm text-gray-500 dark:text-gray-400">
          {configuredCount} von 5 Sensoren zugeordnet
        </div>
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
          <button
            type="button"
            onClick={onSkip}
            className="inline-flex items-center gap-2 px-4 py-2 text-gray-600 dark:text-gray-400 hover:text-gray-800 dark:hover:text-gray-200 transition-colors"
          >
            <SkipForward className="w-4 h-4" />
            Überspringen
          </button>

          <button
            type="button"
            onClick={onSave}
            disabled={isLoading}
            className="inline-flex items-center gap-2 px-6 py-2.5 bg-amber-500 text-white font-medium rounded-lg hover:bg-amber-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isLoading ? (
              <>
                <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                Speichern...
              </>
            ) : (
              <>
                {configuredCount > 0 ? 'Speichern & Weiter' : 'Weiter'}
                <ArrowRight className="w-4 h-4" />
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  )
}
