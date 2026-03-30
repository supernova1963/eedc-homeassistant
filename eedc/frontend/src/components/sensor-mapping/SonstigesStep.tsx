/**
 * SonstigesStep - Sensoren für sonstige Investitionen zuordnen
 *
 * Felder je nach kategorie:
 * - verbraucher: verbrauch_sonstig_kwh
 * - erzeuger:    erzeugung_kwh
 * - speicher:    verbrauch_sonstig_kwh + erzeugung_kwh
 */

import { Wrench } from 'lucide-react'
import type { FeldMapping, HASensorInfo, InvestitionInfo } from '../../api/sensorMapping'
import FeldMappingInput, { type StrategieOption } from './FeldMappingInput'
import LiveSensorSection, { LIVE_FIELDS } from './LiveSensorSection'

interface SonstigesStepProps {
  investitionen: InvestitionInfo[]
  mappings: Record<string, Record<string, FeldMapping>>
  onChange: (invId: number, field: string, mapping: FeldMapping | null) => void
  availableSensors: HASensorInfo[]
  liveMappings?: Record<string, Record<string, string | null>>
  onLiveChange?: (invId: number, sensorKey: string, entityId: string | null) => void
  liveInvertMappings?: Record<string, Record<string, boolean>>
  onLiveInvertChange?: (invId: number, sensorKey: string, invert: boolean) => void
}

const strategieOptionen: StrategieOption[] = [
  { value: 'sensor', label: 'HA-Sensor', description: 'Direkte Messung' },
  { value: 'manuell', label: 'Manuell eingeben', description: 'Im Monatsabschluss-Wizard erfassen' },
  { value: 'keine', label: 'Nicht erfassen', description: 'Optional' },
]

export default function SonstigesStep({
  investitionen,
  mappings,
  onChange,
  availableSensors,
  liveMappings = {},
  onLiveChange,
  liveInvertMappings = {},
  onLiveInvertChange,
}: SonstigesStepProps) {
  return (
    <div className="space-y-6">
      {investitionen.map(inv => {
        const kat: string = (inv.parameter?.kategorie as string) || 'verbraucher'
        const invMappings = mappings[inv.id.toString()] || {}

        return (
          <div key={inv.id} className="border border-gray-200 dark:border-gray-700 rounded-xl overflow-hidden">
            {/* Header */}
            <div className="flex items-center gap-3 px-4 py-3 bg-gray-50 dark:bg-gray-700/50">
              <div className="w-8 h-8 bg-slate-100 dark:bg-slate-900/30 rounded-lg flex items-center justify-center">
                <Wrench className="w-4 h-4 text-slate-600 dark:text-slate-400" />
              </div>
              <div>
                <div className="font-medium text-gray-900 dark:text-white">{inv.bezeichnung}</div>
                <div className="text-xs text-gray-500 capitalize">{kat}</div>
              </div>
            </div>

            {/* Felder */}
            <div className="p-4 space-y-4">
              {(kat === 'verbraucher' || kat === 'speicher') && (
                <FeldMappingInput
                  label={kat === 'speicher' ? 'Verbrauch / Ladung' : 'Verbrauch'}
                  einheit="kWh"
                  value={invMappings.verbrauch_sonstig_kwh || null}
                  onChange={mapping => onChange(inv.id, 'verbrauch_sonstig_kwh', mapping)}
                  availableSensors={availableSensors}
                  strategieOptionen={strategieOptionen.filter(o => o.value !== 'keine')}
                />
              )}

              {(kat === 'erzeuger' || kat === 'speicher') && (
                <FeldMappingInput
                  label={kat === 'speicher' ? 'Erzeugung / Entladung' : 'Erzeugung'}
                  einheit="kWh"
                  value={invMappings.erzeugung_kwh || null}
                  onChange={mapping => onChange(inv.id, 'erzeugung_kwh', mapping)}
                  availableSensors={availableSensors}
                  strategieOptionen={strategieOptionen.filter(o => o.value !== 'keine')}
                />
              )}

              {/* Live-Sensoren */}
              {onLiveChange && (
                <LiveSensorSection
                  invId={inv.id}
                  liveMappings={liveMappings}
                  onLiveChange={onLiveChange}
                  liveInvertMappings={liveInvertMappings}
                  onLiveInvertChange={onLiveInvertChange}
                  availableSensors={availableSensors}
                  fields={[...LIVE_FIELDS.sonstiges]}
                />
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}
