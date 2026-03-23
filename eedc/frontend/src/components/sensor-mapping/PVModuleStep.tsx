/**
 * PVModuleStep - PV-Module Sensoren zuordnen
 *
 * Unterstützt:
 * - Direkter Sensor pro String
 * - kWp-Verteilung basierend auf PV Gesamt
 * - Live-Leistungssensor pro String (für Live-Dashboard)
 */

import { Sun, Activity } from 'lucide-react'
import type { FeldMapping, HASensorInfo, InvestitionInfo } from '../../api/sensorMapping'
import FeldMappingInput, { SensorAutocomplete, type StrategieOption } from './FeldMappingInput'
import Alert from '../ui/Alert'

interface PVModuleStepProps {
  investitionen: InvestitionInfo[]
  mappings: Record<string, Record<string, FeldMapping>>
  onChange: (invId: number, field: string, mapping: FeldMapping | null) => void
  availableSensors: HASensorInfo[]
  gesamtKwp: number
  basisPvGesamt: FeldMapping | null
  liveMappings?: Record<string, Record<string, string | null>>
  onLiveChange?: (invId: number, sensorKey: string, entityId: string | null) => void
  liveInvertMappings?: Record<string, Record<string, boolean>>
  onLiveInvertChange?: (invId: number, sensorKey: string, invert: boolean) => void
}

export default function PVModuleStep({
  investitionen,
  mappings,
  onChange,
  availableSensors,
  gesamtKwp,
  basisPvGesamt,
  liveMappings = {},
  onLiveChange,
  liveInvertMappings = {},
  onLiveInvertChange,
}: PVModuleStepProps) {
  const hasPvGesamtSensor = basisPvGesamt?.strategie === 'sensor' && basisPvGesamt?.sensor_id

  return (
    <div className="space-y-6">
      {/* Info zu kWp-Verteilung */}
      {investitionen.length > 1 && (
        <Alert type="info" title={hasPvGesamtSensor ? 'kWp-Verteilung verfügbar' : 'Tipp'}>
          {hasPvGesamtSensor ? (
            <>Du hast einen PV-Gesamt-Sensor konfiguriert. Die Erzeugung kann anteilig auf die einzelnen Strings verteilt werden.</>
          ) : (
            <>Wenn du keinen separaten Sensor pro String hast, konfiguriere zuerst unter "Basis-Sensoren" einen PV-Gesamt-Sensor.</>
          )}
        </Alert>
      )}

      {investitionen.map(inv => {
        const kwpAnteil = gesamtKwp > 0 && inv.kwp ? inv.kwp / gesamtKwp : 0

        const strategieOptionen: StrategieOption[] = [
          {
            value: 'sensor',
            label: 'Eigener Sensor',
            description: 'Separater Sensor für diesen PV-String',
          },
        ]

        if (hasPvGesamtSensor && kwpAnteil > 0) {
          strategieOptionen.push({
            value: 'kwp_verteilung',
            label: `kWp-Verteilung (${(kwpAnteil * 100).toFixed(1)}%)`,
            description: `${inv.kwp?.toFixed(1)} kWp von ${gesamtKwp.toFixed(1)} kWp gesamt`,
          })
        }

        strategieOptionen.push({
          value: 'manuell',
          label: 'Manuell eingeben',
          description: 'Im Monatsabschluss-Wizard erfassen',
        })

        return (
          <div key={inv.id} className="border border-gray-200 dark:border-gray-700 rounded-xl overflow-hidden">
            {/* Header */}
            <div className="flex items-center gap-3 px-4 py-3 bg-gray-50 dark:bg-gray-700/50">
              <div className="w-8 h-8 bg-amber-100 dark:bg-amber-900/30 rounded-lg flex items-center justify-center">
                <Sun className="w-4 h-4 text-amber-600 dark:text-amber-400" />
              </div>
              <div>
                <div className="font-medium text-gray-900 dark:text-white">
                  {inv.bezeichnung}
                </div>
                {inv.kwp && (
                  <div className="text-xs text-gray-500">
                    {inv.kwp.toFixed(1)} kWp
                    {kwpAnteil > 0 && ` (${(kwpAnteil * 100).toFixed(1)}%)`}
                  </div>
                )}
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
                strategieOptionen={strategieOptionen}
                kwpAnteil={kwpAnteil}
                defaultStrategie={hasPvGesamtSensor && kwpAnteil > 0 ? 'kwp_verteilung' : 'sensor'}
              />

              {/* Live-Sensor */}
              {onLiveChange && (
                <div className="border border-gray-200 dark:border-gray-700 rounded-lg p-4">
                  <div className="flex items-center gap-2 mb-2">
                    <Activity className="w-4 h-4 text-primary-500" />
                    <span className="font-medium text-sm text-gray-900 dark:text-white">Live-Leistung</span>
                    <span className="text-xs text-gray-500">(W) — für Live-Dashboard</span>
                  </div>
                  <SensorAutocomplete
                    value={liveMappings[inv.id.toString()]?.leistung_w}
                    onChange={entityId => onLiveChange(inv.id, 'leistung_w', entityId)}
                    sensors={availableSensors}
                    placeholder="PV-Leistungssensor suchen..."
                  />
                  {liveMappings[inv.id.toString()]?.leistung_w && onLiveInvertChange && (
                    <label className="flex items-center gap-2 mt-2 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={!!liveInvertMappings[inv.id.toString()]?.leistung_w}
                        onChange={e => onLiveInvertChange(inv.id, 'leistung_w', e.target.checked)}
                        className="rounded border-gray-300 dark:border-gray-600 text-primary-600 focus:ring-primary-500"
                      />
                      <span className="text-xs text-gray-600 dark:text-gray-400">
                        Vorzeichen invertieren (&times;&minus;1)
                      </span>
                    </label>
                  )}
                </div>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}
