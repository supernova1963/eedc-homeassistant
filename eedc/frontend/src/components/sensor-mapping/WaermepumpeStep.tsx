/**
 * WaermepumpeStep - Wärmepumpe-Sensoren zuordnen
 *
 * Felder:
 * - Stromverbrauch (kWh) - Pflicht
 * - Heizenergie (kWh) - Sensor oder COP-Berechnung
 * - Warmwasser (kWh) - Sensor, COP-Berechnung, oder nicht separat
 * - Kompressor-Starts (kumulativer Zähler) - optional, Issue #136
 */

import { Thermometer } from 'lucide-react'
import type { FeldMapping, HASensorInfo, InvestitionInfo } from '../../api/sensorMapping'
import FeldMappingInput, { type StrategieOption } from './FeldMappingInput'
import Alert from '../ui/Alert'
import LiveSensorSection, { LIVE_FIELDS } from './LiveSensorSection'
import { useFeldHinweise } from '../../hooks/useFeldHinweise'
import { fmtZahl } from '../../lib'

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
  const hinweise = useFeldHinweise()
  const stromOptionen: StrategieOption[] = [
    {
      value: 'sensor',
      label: 'HA-Sensor',
      description: 'Stromverbrauch aus Energiemessung',
    },
    {
      value: 'keine',
      label: 'Kein Sensor',
      description: 'Manuell im Monatsabschluss erfassen / kein Sensor vorhanden',
    },
  ]

  const heizOptionen: StrategieOption[] = [
    {
      value: 'sensor',
      label: 'Wärmemengenzähler',
      description: 'Direkte Messung der abgegebenen Heizwärme (thermisch)',
    },
    {
      value: 'keine',
      label: 'Kein Sensor',
      description: 'Wird aus Stromverbrauch × JAZ berechnet / manuell erfassen',
    },
  ]

  const warmwasserOptionen: StrategieOption[] = [
    {
      value: 'sensor',
      label: 'Wärmemengenzähler',
      description: 'Separater Sensor für Warmwasser-Wärme (thermisch)',
    },
    {
      value: 'keine',
      label: 'Kein Sensor',
      description: 'In Heizwärme enthalten / wird aus Strom × JAZ berechnet',
    },
  ]

  const startsOptionen: StrategieOption[] = [
    {
      value: 'sensor',
      label: 'HA-Sensor',
      description: 'Kumulativer Zähler (Total-Increasing) der Kompressor-Starts',
    },
    {
      value: 'keine',
      label: 'Nicht erfassen',
      description: 'Kein Starts-Zähler verfügbar',
    },
  ]

  const betriebsstundenOptionen: StrategieOption[] = [
    {
      value: 'sensor',
      label: 'HA-Sensor',
      description: 'Kumulativer Zähler (Total-Increasing) der Betriebsstunden',
    },
    {
      value: 'keine',
      label: 'Nicht erfassen',
      description: 'Kein Betriebsstunden-Zähler verfügbar',
    },
  ]

  return (
    <div className="space-y-6">
      <Alert type="info" title="JAZ-basierte Berechnung">
        Wenn kein Wärmemengenzähler vorhanden ist, wird die abgegebene
        Heizwärme (thermisch) aus dem Stromverbrauch (elektrisch) und der JAZ
        (Jahresarbeitszahl) berechnet: Heizwärme = Stromverbrauch × JAZ. Die
        JAZ stammt aus den Investitions-Parametern.
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
                  JAZ: {fmtZahl(inv.cop, 1)}
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
                  hint={hinweise.waermepumpe?.strom_heizen_kwh}
                  value={mappings[inv.id.toString()]?.strom_heizen_kwh || null}
                  onChange={mapping => onChange(inv.id, 'strom_heizen_kwh', mapping)}
                  availableSensors={availableSensors}
                  strategieOptionen={stromOptionen}
                />
                <FeldMappingInput
                  label="Strom Warmwasser"
                  einheit="kWh"
                  hint={hinweise.waermepumpe?.strom_warmwasser_kwh}
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
                hint={hinweise.waermepumpe?.stromverbrauch_kwh}
                value={mappings[inv.id.toString()]?.stromverbrauch_kwh || null}
                onChange={mapping => onChange(inv.id, 'stromverbrauch_kwh', mapping)}
                availableSensors={availableSensors}
                strategieOptionen={stromOptionen}
              />
            )}

            {/* Heizwärme (#120: Wording-Schaerfung — abgegebene thermische Energie,
                nicht Strom; rcmcronny verwechselte „Heizenergie" mit Strom) */}
            <FeldMappingInput
              label="Heizwärme"
              einheit="kWh"
              hint={hinweise.waermepumpe?.heizenergie_kwh}
              value={mappings[inv.id.toString()]?.heizenergie_kwh || null}
              onChange={mapping => onChange(inv.id, 'heizenergie_kwh', mapping)}
              availableSensors={availableSensors}
              strategieOptionen={heizOptionen}
            />

            {/* Warmwasser */}
            <FeldMappingInput
              label="Warmwasser"
              einheit="kWh"
              hint={hinweise.waermepumpe?.warmwasser_kwh}
              value={mappings[inv.id.toString()]?.warmwasser_kwh || null}
              onChange={mapping => onChange(inv.id, 'warmwasser_kwh', mapping)}
              availableSensors={availableSensors}
              strategieOptionen={warmwasserOptionen}
              defaultStrategie="keine"
            />

            {/* Kompressor-Starts (optional, kumulativer Counter) */}
            <div>
              <FeldMappingInput
                label="Kompressor-Starts (Anzahl, kumulativ)"
                einheit="Starts"
                value={mappings[inv.id.toString()]?.wp_starts_anzahl || null}
                onChange={mapping => onChange(inv.id, 'wp_starts_anzahl', mapping)}
                availableSensors={availableSensors}
                strategieOptionen={startsOptionen}
                defaultStrategie="keine"
              />
              <div className="text-xs text-gray-500 dark:text-gray-400 mt-1 pl-1">
                Optional. Kumulativer Anzahl-Zähler der Kompressor-Starts für Tages-/Monats-KPI (Verschleiß / Auslegung).
                Sollte der Sensor das „ohne Statistik"-Badge aufweisen, beachte bitte die Anleitung zum Nachrüsten — siehe Hilfe → Sensor-Referenz → „ohne Statistik"-Badge.
              </div>
            </div>

            {/* Betriebsstunden (optional, kumulativer Counter, #238 detLAN) */}
            <div>
              <FeldMappingInput
                label="Betriebsstunden (kumulativ)"
                einheit="h"
                value={mappings[inv.id.toString()]?.wp_betriebsstunden || null}
                onChange={mapping => onChange(inv.id, 'wp_betriebsstunden', mapping)}
                availableSensors={availableSensors}
                strategieOptionen={betriebsstundenOptionen}
                defaultStrategie="keine"
              />
              <div className="text-xs text-gray-500 dark:text-gray-400 mt-1 pl-1">
                Optional. Kumulativer Zähler der Gesamt-Betriebsstunden. Kombiniert mit den Kompressor-Starts ergibt sich „Ø Laufzeit pro Start" — typisches Diagnose-Maß für die WP-Auslegung (10 Starts/Tag bei 23 h Betrieb ist deutlich schlechter als bei 4 h Betrieb).
              </div>
            </div>

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
