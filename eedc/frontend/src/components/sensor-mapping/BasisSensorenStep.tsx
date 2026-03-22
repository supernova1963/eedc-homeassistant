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

import { useState } from 'react'
import { Zap, Download, Upload, Activity } from 'lucide-react'
import type { FeldMapping, HASensorInfo } from '../../api/sensorMapping'
import FeldMappingInput, { SensorAutocomplete } from './FeldMappingInput'
import Alert from '../ui/Alert'

interface BasisSensorenStepProps {
  value: {
    einspeisung: FeldMapping | null
    netzbezug: FeldMapping | null
    pv_gesamt: FeldMapping | null
  }
  onChange: (field: 'einspeisung' | 'netzbezug' | 'pv_gesamt', mapping: FeldMapping | null) => void
  availableSensors: HASensorInfo[]
  basisLive?: Record<string, string | null>
  onBasisLiveChange?: (key: string, entityId: string | null) => void
}

export default function BasisSensorenStep({
  value,
  onChange,
  availableSensors,
  basisLive = {},
  onBasisLiveChange,
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

      {/* Live-Sensoren (Leistung in W) */}
      {onBasisLiveChange && (
        <div className="border-t border-gray-200 dark:border-gray-700 pt-6 mt-6">
          <div className="flex items-center gap-2 mb-4">
            <Activity className="w-5 h-5 text-primary-600 dark:text-primary-400" />
            <h3 className="font-medium text-gray-900 dark:text-white">Live-Sensoren (Leistung)</h3>
          </div>
          <p className="text-xs text-gray-500 dark:text-gray-400 mb-4">
            Optional: Leistungssensoren (W) für das Live-Dashboard.
            Diese sind unabhängig von den Energie-Sensoren (kWh) oben.
          </p>

          <div className="space-y-4">
            <NetzLiveSensoren
              basisLive={basisLive}
              onBasisLiveChange={onBasisLiveChange}
              availableSensors={availableSensors}
            />

            <div className="border border-gray-200 dark:border-gray-700 rounded-lg p-4">
              <div className="flex items-center justify-between mb-2">
                <span className="font-medium text-sm text-gray-900 dark:text-white">PV Gesamt</span>
                <span className="text-xs text-gray-500">(W)</span>
              </div>
              <SensorAutocomplete
                value={basisLive.pv_gesamt_w}
                onChange={entityId => onBasisLiveChange('pv_gesamt_w', entityId)}
                sensors={availableSensors}
                placeholder="PV-Gesamt-Leistungssensor suchen..."
              />
              <p className="mt-2 text-xs text-gray-500">
                Optional: Nur nötig wenn kein Live-Sensor pro PV-String konfiguriert ist.
                Wird als ein &quot;PV Gesamt&quot;-Knoten im Live-Dashboard angezeigt.
              </p>
            </div>

            {/* Solar Forecast ML (optional) */}
            <div className="border border-purple-200 dark:border-purple-700/50 rounded-lg p-4">
              <div className="flex items-center justify-between mb-2">
                <span className="font-medium text-sm text-gray-900 dark:text-white">Solar Forecast ML</span>
                <span className="text-xs text-purple-500">optional</span>
              </div>
              <p className="text-xs text-gray-500 dark:text-gray-400 mb-3">
                ML-basierte PV-Prognose aus dem Solar Forecast ML Add-on.
                Wird als zusätzliche Linie im Wetter-Chart angezeigt.
              </p>
              <div className="space-y-3">
                <div>
                  <span className="text-xs text-gray-600 dark:text-gray-400 mb-1 block">Tages-Forecast (kWh)</span>
                  <SensorAutocomplete
                    value={basisLive.sfml_today_kwh}
                    onChange={entityId => onBasisLiveChange('sfml_today_kwh', entityId)}
                    sensors={availableSensors}
                    placeholder="sensor.solar_forecast_ml_today"
                  />
                </div>
                <div>
                  <span className="text-xs text-gray-600 dark:text-gray-400 mb-1 block">Genauigkeit (%)</span>
                  <SensorAutocomplete
                    value={basisLive.sfml_accuracy_pct}
                    onChange={entityId => onBasisLiveChange('sfml_accuracy_pct', entityId)}
                    sensors={availableSensors}
                    placeholder="sensor.solar_forecast_ml_model_accuracy"
                  />
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}


// =============================================================================
// NetzLiveSensoren — Getrennt oder Kombiniert
// =============================================================================

interface NetzLiveSensorenProps {
  basisLive: Record<string, string | null>
  onBasisLiveChange: (key: string, entityId: string | null) => void
  availableSensors: HASensorInfo[]
}

function NetzLiveSensoren({ basisLive, onBasisLiveChange, availableSensors }: NetzLiveSensorenProps) {
  const hasKombi = !!basisLive.netz_kombi_w
  const hasGetrennt = !!basisLive.einspeisung_w || !!basisLive.netzbezug_w
  const [kombiModus, setKombiModus] = useState(hasKombi && !hasGetrennt)

  const handleModusChange = (useKombi: boolean) => {
    setKombiModus(useKombi)
    // Alte Werte zurücksetzen
    if (useKombi) {
      onBasisLiveChange('einspeisung_w', null)
      onBasisLiveChange('netzbezug_w', null)
    } else {
      onBasisLiveChange('netz_kombi_w', null)
    }
  }

  return (
    <>
      {/* Modus-Umschalter */}
      <div className="border border-gray-200 dark:border-gray-700 rounded-lg p-4">
        <div className="flex items-center justify-between mb-3">
          <span className="font-medium text-sm text-gray-900 dark:text-white">Netz-Sensoren</span>
          <span className="text-xs text-gray-500">(W)</span>
        </div>

        <div className="flex gap-2 mb-4">
          <button
            type="button"
            onClick={() => handleModusChange(false)}
            className={`flex-1 px-3 py-2 text-sm rounded-lg transition-colors ${
              !kombiModus
                ? 'bg-amber-100 dark:bg-amber-900/30 text-amber-800 dark:text-amber-200 ring-1 ring-amber-500'
                : 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-600'
            }`}
          >
            Getrennte Sensoren
          </button>
          <button
            type="button"
            onClick={() => handleModusChange(true)}
            className={`flex-1 px-3 py-2 text-sm rounded-lg transition-colors ${
              kombiModus
                ? 'bg-amber-100 dark:bg-amber-900/30 text-amber-800 dark:text-amber-200 ring-1 ring-amber-500'
                : 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-600'
            }`}
          >
            Kombinierter Sensor
          </button>
        </div>

        {kombiModus ? (
          <div>
            <p className="text-xs text-gray-500 dark:text-gray-400 mb-3">
              Ein Sensor für Netz-Leistung: positiv = Bezug, negativ = Einspeisung.
            </p>
            <SensorAutocomplete
              value={basisLive.netz_kombi_w}
              onChange={entityId => onBasisLiveChange('netz_kombi_w', entityId)}
              sensors={availableSensors}
              placeholder="Kombinierten Netz-Sensor suchen..."
            />
          </div>
        ) : (
          <div className="space-y-3">
            <div>
              <div className="flex items-center justify-between mb-1">
                <span className="text-sm text-gray-700 dark:text-gray-300">Einspeisung</span>
              </div>
              <SensorAutocomplete
                value={basisLive.einspeisung_w}
                onChange={entityId => onBasisLiveChange('einspeisung_w', entityId)}
                sensors={availableSensors}
                placeholder="Einspeise-Leistungssensor suchen..."
              />
            </div>
            <div>
              <div className="flex items-center justify-between mb-1">
                <span className="text-sm text-gray-700 dark:text-gray-300">Netzbezug</span>
              </div>
              <SensorAutocomplete
                value={basisLive.netzbezug_w}
                onChange={entityId => onBasisLiveChange('netzbezug_w', entityId)}
                sensors={availableSensors}
                placeholder="Netzbezug-Leistungssensor suchen..."
              />
            </div>
          </div>
        )}
      </div>
    </>
  )
}
