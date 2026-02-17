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

import { Zap, Download, Upload } from 'lucide-react'
import type { FeldMapping, HASensorInfo } from '../../api/sensorMapping'
import FeldMappingInput from './FeldMappingInput'
import Alert from '../ui/Alert'

interface BasisSensorenStepProps {
  value: {
    einspeisung: FeldMapping | null
    netzbezug: FeldMapping | null
    pv_gesamt: FeldMapping | null
  }
  onChange: (field: 'einspeisung' | 'netzbezug' | 'pv_gesamt', mapping: FeldMapping | null) => void
  availableSensors: HASensorInfo[]
}

export default function BasisSensorenStep({
  value,
  onChange,
  availableSensors,
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
    </div>
  )
}
