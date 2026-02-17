/**
 * EAutoStep - E-Auto und Wallbox Sensoren zuordnen
 *
 * E-Auto Felder:
 * - Ladung PV (kWh)
 * - Ladung Netz (kWh) - oder EV-Quote
 * - km gefahren - typischerweise manuell
 * - V2H Entladung (kWh) - optional
 *
 * Wallbox Felder:
 * - Ladung gesamt (kWh)
 */

import { Car, PlugZap } from 'lucide-react'
import type { FeldMapping, HASensorInfo, InvestitionInfo } from '../../api/sensorMapping'
import FeldMappingInput, { type StrategieOption } from './FeldMappingInput'
import Alert from '../ui/Alert'

interface EAutoStepProps {
  investitionen: InvestitionInfo[]
  mappings: Record<string, Record<string, FeldMapping>>
  onChange: (invId: number, field: string, mapping: FeldMapping | null) => void
  availableSensors: HASensorInfo[]
}

export default function EAutoStep({
  investitionen,
  mappings,
  onChange,
  availableSensors,
}: EAutoStepProps) {
  const eAutos = investitionen.filter(i => i.typ === 'e-auto')
  const wallboxen = investitionen.filter(i => i.typ === 'wallbox')

  const ladungOptionen: StrategieOption[] = [
    {
      value: 'sensor',
      label: 'HA-Sensor',
      description: 'Direkte Messung',
    },
    {
      value: 'manuell',
      label: 'Manuell eingeben',
      description: 'Im Monatsabschluss-Wizard erfassen',
    },
  ]

  const netzLadungOptionen: StrategieOption[] = [
    {
      value: 'sensor',
      label: 'HA-Sensor',
      description: 'Separater Sensor für Netzladung',
    },
    {
      value: 'ev_quote',
      label: 'EV-Quote berechnen',
      description: 'Basierend auf Anlagen-Eigenverbrauchsquote',
    },
    {
      value: 'manuell',
      label: 'Manuell eingeben',
      description: 'Im Monatsabschluss-Wizard erfassen',
    },
  ]

  const kmOptionen: StrategieOption[] = [
    {
      value: 'sensor',
      label: 'HA-Sensor',
      description: 'Z.B. aus Auto-Integration',
    },
    {
      value: 'manuell',
      label: 'Manuell eingeben',
      description: 'Kilometerstand monatlich erfassen',
    },
  ]

  const v2hOptionen: StrategieOption[] = [
    {
      value: 'sensor',
      label: 'HA-Sensor',
      description: 'V2H/V2G Entladung',
    },
    {
      value: 'keine',
      label: 'Nicht vorhanden',
      description: 'Kein Vehicle-to-Home',
    },
  ]

  return (
    <div className="space-y-6">
      {/* E-Autos */}
      {eAutos.length > 0 && (
        <>
          <h3 className="font-medium text-gray-900 dark:text-white flex items-center gap-2">
            <Car className="w-5 h-5" />
            E-Autos
          </h3>

          {eAutos.map(inv => (
            <div key={inv.id} className="border border-gray-200 dark:border-gray-700 rounded-xl overflow-hidden">
              {/* Header */}
              <div className="flex items-center gap-3 px-4 py-3 bg-gray-50 dark:bg-gray-700/50">
                <div className="w-8 h-8 bg-blue-100 dark:bg-blue-900/30 rounded-lg flex items-center justify-center">
                  <Car className="w-4 h-4 text-blue-600 dark:text-blue-400" />
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
                  label="Ladung PV"
                  einheit="kWh"
                  value={mappings[inv.id.toString()]?.ladung_pv_kwh || null}
                  onChange={mapping => onChange(inv.id, 'ladung_pv_kwh', mapping)}
                  availableSensors={availableSensors}
                  strategieOptionen={ladungOptionen}
                />

                <FeldMappingInput
                  label="Ladung Netz"
                  einheit="kWh"
                  value={mappings[inv.id.toString()]?.ladung_netz_kwh || null}
                  onChange={mapping => onChange(inv.id, 'ladung_netz_kwh', mapping)}
                  availableSensors={availableSensors}
                  strategieOptionen={netzLadungOptionen}
                />

                <FeldMappingInput
                  label="Gefahrene Kilometer"
                  einheit="km"
                  value={mappings[inv.id.toString()]?.km_gefahren || null}
                  onChange={mapping => onChange(inv.id, 'km_gefahren', mapping)}
                  availableSensors={availableSensors}
                  strategieOptionen={kmOptionen}
                  defaultStrategie="manuell"
                />

                <FeldMappingInput
                  label="V2H Entladung"
                  einheit="kWh"
                  value={mappings[inv.id.toString()]?.v2h_entladung_kwh || null}
                  onChange={mapping => onChange(inv.id, 'v2h_entladung_kwh', mapping)}
                  availableSensors={availableSensors}
                  strategieOptionen={v2hOptionen}
                  defaultStrategie="keine"
                />
              </div>
            </div>
          ))}
        </>
      )}

      {/* Wallboxen */}
      {wallboxen.length > 0 && (
        <>
          <h3 className="font-medium text-gray-900 dark:text-white flex items-center gap-2 mt-8">
            <PlugZap className="w-5 h-5" />
            Wallboxen
          </h3>

          <Alert type="info">
            Wallbox-Ladung wird für die Gesamtübersicht verwendet.
            Die Zuordnung PV/Netz erfolgt über die E-Auto-Konfiguration.
          </Alert>

          {wallboxen.map(inv => (
            <div key={inv.id} className="border border-gray-200 dark:border-gray-700 rounded-xl overflow-hidden">
              {/* Header */}
              <div className="flex items-center gap-3 px-4 py-3 bg-gray-50 dark:bg-gray-700/50">
                <div className="w-8 h-8 bg-purple-100 dark:bg-purple-900/30 rounded-lg flex items-center justify-center">
                  <PlugZap className="w-4 h-4 text-purple-600 dark:text-purple-400" />
                </div>
                <div>
                  <div className="font-medium text-gray-900 dark:text-white">
                    {inv.bezeichnung}
                  </div>
                </div>
              </div>

              {/* Felder */}
              <div className="p-4">
                <FeldMappingInput
                  label="Ladung Gesamt"
                  einheit="kWh"
                  value={mappings[inv.id.toString()]?.ladung_kwh || null}
                  onChange={mapping => onChange(inv.id, 'ladung_kwh', mapping)}
                  availableSensors={availableSensors}
                  strategieOptionen={ladungOptionen}
                />
              </div>
            </div>
          ))}
        </>
      )}
    </div>
  )
}
