/**
 * BasisSensorenStep - Basis-Sensoren zuordnen
 *
 * Pflichtfelder:
 * - Einspeisung
 * - Netzbezug
 *
 * Optional:
 * - PV Gesamt (für kWp-Verteilung auf Strings)
 */

import { Zap, Download, Upload, Activity } from 'lucide-react'
import type { FeldMapping, HASensorInfo } from '../../api/sensorMapping'
import FeldMappingInput, { SensorAutocomplete } from './FeldMappingInput'
import Alert from '../ui/Alert'

interface BasisSensorenStepProps {
  value: {
    einspeisung: FeldMapping | null
    netzbezug: FeldMapping | null
    pv_gesamt: FeldMapping | null
  }
  onChange: (field: 'einspeisung' | 'netzbezug' | 'pv_gesamt', mapping: FeldMapping | null) => void
  availableSensors: HASensorInfo[]
  basisLive?: Record<string, string | null>
  onBasisLiveChange?: (key: string, entityId: string | null) => void
}

export default function BasisSensorenStep({
  value,
  onChange,
  availableSensors,
  basisLive = {},
  onBasisLiveChange,
}: BasisSensorenStepProps) {
  const basisOptionen = [
    {
      value: 'sensor' as const,
      label: 'HA-Sensor',
      description: 'Wert direkt aus Home Assistant Sensor lesen',
    },
    {
      value: 'manuell' as const,
      label: 'Manuell eingeben',
      description: 'Im Monatsabschluss-Wizard manuell erfassen',
    },
  ]

  const pvGesantOptionen = [
    {
      value: 'sensor' as const,
      label: 'HA-Sensor',
      description: 'PV-Gesamterzeugung aus Wechselrichter-Sensor',
    },
    {
      value: 'keine' as const,
      label: 'Nicht verwenden',
      description: 'Jeder PV-String hat einen eigenen Sensor',
    },
  ]

  return (
    <div className="space-y-6">
      <Alert type="info" title="Basis-Sensoren">
        Diese sind die Grundlage für alle Energie-Berechnungen.
        Die Werte werden typischerweise vom Stromzähler oder Wechselrichter erfasst.
      </Alert>

      {/* Einspeisung */}
      <div className="flex items-start gap-4">
        <div className="w-10 h-10 bg-green-100 dark:bg-green-900/30 rounded-lg flex items-center justify-center flex-shrink-0">
          <Upload className="w-5 h-5 text-green-600 dark:text-green-400" />
        </div>
        <div className="flex-1">
          <FeldMappingInput
            label="Einspeisung"
            einheit="kWh"
            value={value.einspeisung}
            onChange={mapping => onChange('einspeisung', mapping)}
            availableSensors={availableSensors}
            strategieOptionen={basisOptionen}
          />
        </div>
      </div>

      {/* Netzbezug */}
      <div className="flex items-start gap-4">
        <div className="w-10 h-10 bg-red-100 dark:bg-red-900/30 rounded-lg flex items-center justify-center flex-shrink-0">
          <Download className="w-5 h-5 text-red-600 dark:text-red-400" />
        </div>
        <div className="flex-1">
          <FeldMappingInput
            label="Netzbezug"
            einheit="kWh"
            value={value.netzbezug}
            onChange={mapping => onChange('netzbezug', mapping)}
            availableSensors={availableSensors}
            strategieOptionen={basisOptionen}
          />
        </div>
      </div>

      {/* PV Gesamt (optional) */}
      <div className="flex items-start gap-4">
        <div className="w-10 h-10 bg-amber-100 dark:bg-amber-900/30 rounded-lg flex items-center justify-center flex-shrink-0">
          <Zap className="w-5 h-5 text-amber-600 dark:text-amber-400" />
        </div>
        <div className="flex-1">
          <FeldMappingInput
            label="PV Erzeugung Gesamt"
            einheit="kWh"
            value={value.pv_gesamt}
            onChange={mapping => onChange('pv_gesamt', mapping)}
            availableSensors={availableSensors}
            strategieOptionen={pvGesantOptionen}
            defaultStrategie="keine"
          />
          <p className="mt-2 text-xs text-gray-500">
            Optional: Wenn du mehrere PV-Strings hast, aber nur einen Gesamtsensor,
            kann die Erzeugung anteilig nach kWp auf die Strings verteilt werden.
          </p>
        </div>
      </div>

      {/* Live-Sensoren (Leistung in W) */}
      {onBasisLiveChange && (
        <>
          <div className="border-t border-gray-200 dark:border-gray-700 pt-6 mt-6">
            <div className="flex items-center gap-2 mb-4">
              <Activity className="w-5 h-5 text-primary-600 dark:text-primary-400" />
              <h3 className="font-medium text-gray-900 dark:text-white">Live-Sensoren (Leistung)</h3>
            </div>
            <p className="text-xs text-gray-500 dark:text-gray-400 mb-4">
              Optional: Leistungssensoren (W) für das Live-Dashboard.
              Diese sind unabhängig von den Energie-Sensoren (kWh) oben.
            </p>

            <div className="space-y-4">
              <div className="border border-gray-200 dark:border-gray-700 rounded-lg p-4">
                <div className="flex items-center justify-between mb-2">
                  <span className="font-medium text-sm text-gray-900 dark:text-white">Einspeisung</span>
                  <span className="text-xs text-gray-500">(W)</span>
                </div>
                <SensorAutocomplete
                  value={basisLive.einspeisung_w}
                  onChange={entityId => onBasisLiveChange('einspeisung_w', entityId)}
                  sensors={availableSensors}
                  placeholder="Einspeise-Leistungssensor suchen..."
                />
              </div>

              <div className="border border-gray-200 dark:border-gray-700 rounded-lg p-4">
                <div className="flex items-center justify-between mb-2">
                  <span className="font-medium text-sm text-gray-900 dark:text-white">Netzbezug</span>
                  <span className="text-xs text-gray-500">(W)</span>
                </div>
                <SensorAutocomplete
                  value={basisLive.netzbezug_w}
                  onChange={entityId => onBasisLiveChange('netzbezug_w', entityId)}
                  sensors={availableSensors}
                  placeholder="Netzbezug-Leistungssensor suchen..."
                />
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
