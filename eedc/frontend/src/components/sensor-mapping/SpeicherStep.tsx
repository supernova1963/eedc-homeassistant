/**
 * SpeicherStep - Speicher-Sensoren zuordnen
 *
 * Felder:
 * - Ladung (kWh)
 * - Entladung (kWh)
 * - Netzladung (kWh, optional für Arbitrage)
 */

import { Battery } from 'lucide-react'
import type { FeldMapping, HASensorInfo, InvestitionInfo } from '../../api/sensorMapping'
import FeldMappingInput, { type StrategieOption } from './FeldMappingInput'

interface SpeicherStepProps {
  investitionen: InvestitionInfo[]
  mappings: Record<string, Record<string, FeldMapping>>
  onChange: (invId: number, field: string, mapping: FeldMapping | null) => void
  availableSensors: HASensorInfo[]
}

export default function SpeicherStep({
  investitionen,
  mappings,
  onChange,
  availableSensors,
}: SpeicherStepProps) {
  const basisOptionen: StrategieOption[] = [
    {
      value: 'sensor',
      label: 'HA-Sensor',
      description: 'Wert direkt aus Home Assistant lesen',
    },
    {
      value: 'manuell',
      label: 'Manuell eingeben',
      description: 'Im Monatsabschluss-Wizard erfassen',
    },
  ]

  const netzladungOptionen: StrategieOption[] = [
    {
      value: 'sensor',
      label: 'HA-Sensor',
      description: 'Separater Sensor für Netzladung',
    },
    {
      value: 'keine',
      label: 'Nicht erfassen',
      description: 'Speicher wird nicht aus dem Netz geladen',
    },
    {
      value: 'manuell',
      label: 'Manuell eingeben',
      description: 'Im Monatsabschluss-Wizard erfassen',
    },
  ]

  return (
    <div className="space-y-6">
      {investitionen.map(inv => (
        <div key={inv.id} className="border border-gray-200 dark:border-gray-700 rounded-xl overflow-hidden">
          {/* Header */}
          <div className="flex items-center gap-3 px-4 py-3 bg-gray-50 dark:bg-gray-700/50">
            <div className="w-8 h-8 bg-green-100 dark:bg-green-900/30 rounded-lg flex items-center justify-center">
              <Battery className="w-4 h-4 text-green-600 dark:text-green-400" />
            </div>
            <div>
              <div className="font-medium text-gray-900 dark:text-white">
                {inv.bezeichnung}
              </div>
            </div>
          </div>

          {/* Felder */}
          <div className="p-4 space-y-4">
            <FeldMappingInput
              label="Ladung"
              einheit="kWh"
              value={mappings[inv.id.toString()]?.ladung_kwh || null}
              onChange={mapping => onChange(inv.id, 'ladung_kwh', mapping)}
              availableSensors={availableSensors}
              strategieOptionen={basisOptionen}
            />

            <FeldMappingInput
              label="Entladung"
              einheit="kWh"
              value={mappings[inv.id.toString()]?.entladung_kwh || null}
              onChange={mapping => onChange(inv.id, 'entladung_kwh', mapping)}
              availableSensors={availableSensors}
              strategieOptionen={basisOptionen}
            />

            <FeldMappingInput
              label="Netzladung"
              einheit="kWh"
              value={mappings[inv.id.toString()]?.ladung_netz_kwh || null}
              onChange={mapping => onChange(inv.id, 'ladung_netz_kwh', mapping)}
              availableSensors={availableSensors}
              strategieOptionen={netzladungOptionen}
              defaultStrategie="keine"
            />
            <p className="text-xs text-gray-500 -mt-2 ml-1">
              Netzladung wird für Arbitrage-Auswertung (Speicher aus Netz laden) benötigt.
            </p>
          </div>
        </div>
      ))}
    </div>
  )
}
