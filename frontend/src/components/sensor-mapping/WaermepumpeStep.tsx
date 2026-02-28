/**
 * WaermepumpeStep - Wärmepumpe-Sensoren zuordnen
 *
 * Felder:
 * - Stromverbrauch (kWh) - Pflicht
 * - Heizenergie (kWh) - Sensor oder COP-Berechnung
 * - Warmwasser (kWh) - Sensor, COP-Berechnung, oder nicht separat
 */

import { Thermometer, Zap } from 'lucide-react'
import type { FeldMapping, HASensorInfo, InvestitionInfo } from '../../api/sensorMapping'
import FeldMappingInput, { type StrategieOption } from './FeldMappingInput'
import Alert from '../ui/Alert'

interface WaermepumpeStepProps {
  investitionen: InvestitionInfo[]
  mappings: Record<string, Record<string, FeldMapping>>
  onChange: (invId: number, field: string, mapping: FeldMapping | null) => void
  availableSensors: HASensorInfo[]
}

export default function WaermepumpeStep({
  investitionen,
  mappings,
  onChange,
  availableSensors,
}: WaermepumpeStepProps) {
  const stromOptionen: StrategieOption[] = [
    {
      value: 'sensor',
      label: 'HA-Sensor',
      description: 'Stromverbrauch aus Energiemessung',
    },
    {
      value: 'manuell',
      label: 'Manuell eingeben',
      description: 'Im Monatsabschluss-Wizard erfassen',
    },
  ]

  const heizOptionen: StrategieOption[] = [
    {
      value: 'sensor',
      label: 'Wärmemengenzähler',
      description: 'Direkte Messung der Heizenergie',
    },
    {
      value: 'cop_berechnung',
      label: 'COP-Berechnung',
      description: 'Stromverbrauch × COP (JAZ)',
    },
  ]

  const warmwasserOptionen: StrategieOption[] = [
    {
      value: 'sensor',
      label: 'Wärmemengenzähler',
      description: 'Separater Sensor für Warmwasser',
    },
    {
      value: 'cop_berechnung',
      label: 'COP-Berechnung',
      description: 'Anteil Strom × COP',
    },
    {
      value: 'keine',
      label: 'Nicht separat erfassen',
      description: 'Warmwasser ist in Heizenergie enthalten',
    },
  ]

  return (
    <div className="space-y-6">
      <Alert type="info" title="COP-Berechnung">
        Wenn kein Wärmemengenzähler vorhanden ist, kann die Heizenergie über den COP
        (Coefficient of Performance) berechnet werden. Der COP sollte aus den
        Investitions-Parametern übernommen werden.
      </Alert>

      {investitionen.map(inv => (
        <div key={inv.id} className="border border-gray-200 dark:border-gray-700 rounded-xl overflow-hidden">
          {/* Header */}
          <div className="flex items-center gap-3 px-4 py-3 bg-gray-50 dark:bg-gray-700/50">
            <div className="w-8 h-8 bg-blue-100 dark:bg-blue-900/30 rounded-lg flex items-center justify-center">
              <Thermometer className="w-4 h-4 text-blue-600 dark:text-blue-400" />
            </div>
            <div>
              <div className="font-medium text-gray-900 dark:text-white">
                {inv.bezeichnung}
              </div>
              {inv.cop && (
                <div className="text-xs text-gray-500">
                  JAZ/COP: {inv.cop.toFixed(1)}
                </div>
              )}
            </div>
          </div>

          {/* Felder */}
          <div className="p-4 space-y-4">
            {/* Stromverbrauch - Pflicht */}
            <div className="flex items-start gap-3">
              <div className="w-6 h-6 bg-amber-100 dark:bg-amber-900/30 rounded flex items-center justify-center flex-shrink-0 mt-1">
                <Zap className="w-3 h-3 text-amber-600" />
              </div>
              <div className="flex-1">
                <FeldMappingInput
                  label="Stromverbrauch"
                  einheit="kWh"
                  value={mappings[inv.id.toString()]?.stromverbrauch_kwh || null}
                  onChange={mapping => onChange(inv.id, 'stromverbrauch_kwh', mapping)}
                  availableSensors={availableSensors}
                  strategieOptionen={stromOptionen}
                />
              </div>
            </div>

            {/* Heizenergie */}
            <FeldMappingInput
              label="Heizenergie"
              einheit="kWh"
              value={mappings[inv.id.toString()]?.heizenergie_kwh || null}
              onChange={mapping => onChange(inv.id, 'heizenergie_kwh', mapping)}
              availableSensors={availableSensors}
              strategieOptionen={heizOptionen}
              copDefault={inv.cop || 3.5}
            />

            {/* Warmwasser */}
            <FeldMappingInput
              label="Warmwasser"
              einheit="kWh"
              value={mappings[inv.id.toString()]?.warmwasser_kwh || null}
              onChange={mapping => onChange(inv.id, 'warmwasser_kwh', mapping)}
              availableSensors={availableSensors}
              strategieOptionen={warmwasserOptionen}
              copDefault={inv.cop ? inv.cop - 0.5 : 3.0}
              defaultStrategie="keine"
            />
          </div>
        </div>
      ))}
    </div>
  )
}
