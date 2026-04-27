/**
 * WaermepumpeStep - Wärmepumpe-Sensoren zuordnen
 *
 * Felder:
 * - Stromverbrauch (kWh) - Pflicht
 * - Heizenergie (kWh) - Sensor oder COP-Berechnung
 * - Warmwasser (kWh) - Sensor, COP-Berechnung, oder nicht separat
 */

import { Thermometer } from 'lucide-react'
import type { FeldMapping, HASensorInfo, InvestitionInfo } from '../../api/sensorMapping'
import FeldMappingInput, { type StrategieOption } from './FeldMappingInput'
import Alert from '../ui/Alert'
import LiveSensorSection, { LIVE_FIELDS } from './LiveSensorSection'

interface WaermepumpeStepProps {
  investitionen: InvestitionInfo[]
  mappings: Record<string, Record<string, FeldMapping>>
  onChange: (invId: number, field: string, mapping: FeldMapping | null) => void
  availableSensors: HASensorInfo[]
  liveMappings?: Record<string, Record<string, string | null>>
  onLiveChange?: (invId: number, sensorKey: string, entityId: string | null) => void
  liveInvertMappings?: Record<string, Record<string, boolean>>
  onLiveInvertChange?: (invId: number, sensorKey: string, invert: boolean) => void
}

export default function WaermepumpeStep({
  investitionen,
  mappings,
  onChange,
  availableSensors,
  liveMappings = {},
  onLiveChange,
  liveInvertMappings = {},
  onLiveInvertChange,
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
    {
      value: 'keine',
      label: 'Nicht erfassen',
      description: 'Wird so übernommen / kein Sensor vorhanden',
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
      label: 'JAZ-Berechnung',
      description: 'Stromverbrauch × JAZ',
    },
    {
      value: 'keine',
      label: 'Nicht erfassen',
      description: 'Wird so übernommen / kein Wärmemengenzähler vorhanden',
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
      label: 'JAZ-Berechnung',
      description: 'Anteil Strom × JAZ',
    },
    {
      value: 'keine',
      label: 'Nicht separat erfassen',
      description: 'Warmwasser ist in Heizenergie enthalten',
    },
  ]

  return (
    <div className="space-y-6">
      <Alert type="info" title="JAZ-basierte Berechnung">
        Wenn kein Wärmemengenzähler vorhanden ist, wird die Heizenergie aus dem
        Stromverbrauch und der JAZ (Jahresarbeitszahl) berechnet:
        Heizenergie = Stromverbrauch × JAZ. Die JAZ stammt aus den
        Investitions-Parametern.
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
                  JAZ: {inv.cop.toFixed(1)}
                </div>
              )}
            </div>
          </div>

          {/* Felder */}
          <div className="p-4 space-y-4">
            {/* Stromverbrauch - getrennt oder gesamt */}
            {inv.parameter?.getrennte_strommessung ? (
              <>
                <FeldMappingInput
                  label="Strom Heizen"
                  einheit="kWh"
                  value={mappings[inv.id.toString()]?.strom_heizen_kwh || null}
                  onChange={mapping => onChange(inv.id, 'strom_heizen_kwh', mapping)}
                  availableSensors={availableSensors}
                  strategieOptionen={stromOptionen}
                />
                <FeldMappingInput
                  label="Strom Warmwasser"
                  einheit="kWh"
                  value={mappings[inv.id.toString()]?.strom_warmwasser_kwh || null}
                  onChange={mapping => onChange(inv.id, 'strom_warmwasser_kwh', mapping)}
                  availableSensors={availableSensors}
                  strategieOptionen={stromOptionen}
                />
              </>
            ) : (
              <FeldMappingInput
                label="Stromverbrauch"
                einheit="kWh"
                value={mappings[inv.id.toString()]?.stromverbrauch_kwh || null}
                onChange={mapping => onChange(inv.id, 'stromverbrauch_kwh', mapping)}
                availableSensors={availableSensors}
                strategieOptionen={stromOptionen}
              />
            )}

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

            {/* Live-Sensoren */}
            {onLiveChange && (
              <LiveSensorSection
                invId={inv.id}
                liveMappings={liveMappings}
                onLiveChange={onLiveChange}
                liveInvertMappings={liveInvertMappings}
                onLiveInvertChange={onLiveInvertChange}
                availableSensors={availableSensors}
                fields={[
                  ...LIVE_FIELDS.waermepumpe,
                  { key: 'leistung_heizen_w', label: 'Leistung Heizen (optional)', einheit: 'W', placeholder: 'WP-Heizleistung suchen...' },
                  { key: 'leistung_warmwasser_w', label: 'Leistung Warmwasser (optional)', einheit: 'W', placeholder: 'WP-Warmwasserleistung suchen...' },
                ]}
              />
            )}
          </div>
        </div>
      ))}
    </div>
  )
}
