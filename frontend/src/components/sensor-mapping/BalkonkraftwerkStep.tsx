/**
 * BalkonkraftwerkStep - Balkonkraftwerk Sensoren zuordnen
 *
 * Felder:
 * - PV-Erzeugung (kWh)
 * - Eigenverbrauch (kWh)
 * - Speicher Ladung (kWh) - optional, wenn BKW-Speicher vorhanden
 * - Speicher Entladung (kWh) - optional
 */

import { Sun } from 'lucide-react'
import type { FeldMapping, HASensorInfo, InvestitionInfo } from '../../api/sensorMapping'
import FeldMappingInput, { type StrategieOption } from './FeldMappingInput'
import Alert from '../ui/Alert'

interface BalkonkraftwerkStepProps {
  investitionen: InvestitionInfo[]
  mappings: Record<string, Record<string, FeldMapping>>
  onChange: (invId: number, field: string, mapping: FeldMapping | null) => void
  availableSensors: HASensorInfo[]
}

export default function BalkonkraftwerkStep({
  investitionen,
  mappings,
  onChange,
  availableSensors,
}: BalkonkraftwerkStepProps) {
  const erzeugungOptionen: StrategieOption[] = [
    {
      value: 'sensor',
      label: 'HA-Sensor',
      description: 'Direkte Messung vom Wechselrichter',
    },
    {
      value: 'manuell',
      label: 'Manuell eingeben',
      description: 'Im Monatsabschluss erfassen',
    },
  ]

  const eigenverbrauchOptionen: StrategieOption[] = [
    {
      value: 'sensor',
      label: 'HA-Sensor',
      description: 'Falls separater Sensor vorhanden',
    },
    {
      value: 'manuell',
      label: 'Manuell eingeben',
      description: 'Im Monatsabschluss erfassen',
    },
    {
      value: 'keine',
      label: 'Nicht erfassen',
      description: 'Wird aus Erzeugung - Einspeisung berechnet',
    },
  ]

  const speicherOptionen: StrategieOption[] = [
    {
      value: 'sensor',
      label: 'HA-Sensor',
      description: 'Z.B. von Speicher-Integration',
    },
    {
      value: 'manuell',
      label: 'Manuell eingeben',
      description: 'Im Monatsabschluss erfassen',
    },
    {
      value: 'keine',
      label: 'Kein Speicher',
      description: 'BKW ohne Speicher',
    },
  ]

  return (
    <div className="space-y-6">
      <Alert type="info">
        Balkonkraftwerke können optional einen integrierten Speicher haben.
        Konfiguriere die Speicher-Felder nur, wenn dein BKW einen Speicher hat.
      </Alert>

      {investitionen.map(inv => (
        <div key={inv.id} className="border border-gray-200 dark:border-gray-700 rounded-xl overflow-hidden">
          {/* Header */}
          <div className="flex items-center gap-3 px-4 py-3 bg-gray-50 dark:bg-gray-700/50">
            <div className="w-8 h-8 bg-green-100 dark:bg-green-900/30 rounded-lg flex items-center justify-center">
              <Sun className="w-4 h-4 text-green-600 dark:text-green-400" />
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
              label="PV-Erzeugung"
              einheit="kWh"
              value={mappings[inv.id.toString()]?.pv_erzeugung_kwh || null}
              onChange={mapping => onChange(inv.id, 'pv_erzeugung_kwh', mapping)}
              availableSensors={availableSensors}
              strategieOptionen={erzeugungOptionen}
            />

            <FeldMappingInput
              label="Eigenverbrauch"
              einheit="kWh"
              value={mappings[inv.id.toString()]?.eigenverbrauch_kwh || null}
              onChange={mapping => onChange(inv.id, 'eigenverbrauch_kwh', mapping)}
              availableSensors={availableSensors}
              strategieOptionen={eigenverbrauchOptionen}
              defaultStrategie="keine"
            />

            <FeldMappingInput
              label="Speicher Ladung"
              einheit="kWh"
              value={mappings[inv.id.toString()]?.speicher_ladung_kwh || null}
              onChange={mapping => onChange(inv.id, 'speicher_ladung_kwh', mapping)}
              availableSensors={availableSensors}
              strategieOptionen={speicherOptionen}
              defaultStrategie="keine"
            />

            <FeldMappingInput
              label="Speicher Entladung"
              einheit="kWh"
              value={mappings[inv.id.toString()]?.speicher_entladung_kwh || null}
              onChange={mapping => onChange(inv.id, 'speicher_entladung_kwh', mapping)}
              availableSensors={availableSensors}
              strategieOptionen={speicherOptionen}
              defaultStrategie="keine"
            />
          </div>
        </div>
      ))}
    </div>
  )
}
