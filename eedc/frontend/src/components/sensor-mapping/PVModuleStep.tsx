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
import { useFeldHinweise } from '../../hooks/useFeldHinweise'
import { fmtZahl } from '../../lib'

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
  const hinweise = useFeldHinweise()
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

        // Achse A1: kWp-Verteilung ist kein Sensor-Mapping-Strategiewert mehr,
        // sondern ein read-time-Helper ([[project_kwp_verteilung_aggregator]]).
        // Bei mehreren PV-Strings ohne eigenen Sensor liest die Aggregation den
        // PV-Gesamtsensor und verteilt ihn anteilig nach kWp — ohne dass hier
        // eine Strategie gewählt werden muss. Auswahl daher nur sensor/keine.
        const strategieOptionen: StrategieOption[] = [
          {
            value: 'sensor',
            label: 'Eigener Sensor',
            description: 'Separater Sensor für diesen PV-String',
          },
          {
            value: 'keine',
            label: 'Kein Sensor',
            description: hasPvGesamtSensor && kwpAnteil > 0
              ? `Anteilig (${fmtZahl(kwpAnteil * 100, 1)} %) aus PV-Gesamt verteilt oder manuell erfassen`
              : 'Manuell im Monatsabschluss erfassen',
          },
        ]

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
                    {fmtZahl(inv.kwp, 1)} kWp
                    {kwpAnteil > 0 && ` (${fmtZahl(kwpAnteil * 100, 1)} %)`}
                  </div>
                )}
              </div>
            </div>

            {/* Felder */}
            <div className="p-4 space-y-4">
              <FeldMappingInput
                label="PV-Erzeugung"
                einheit="kWh"
                hint={hinweise['pv-module']?.pv_erzeugung_kwh}
                value={mappings[inv.id.toString()]?.pv_erzeugung_kwh || null}
                onChange={mapping => onChange(inv.id, 'pv_erzeugung_kwh', mapping)}
                availableSensors={availableSensors}
                strategieOptionen={strategieOptionen}
                defaultStrategie={hasPvGesamtSensor && kwpAnteil > 0 ? 'keine' : 'sensor'}
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
                    requireStatistics={false}
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
