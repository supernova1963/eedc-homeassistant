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
import { Zap, Download, Upload, Activity, Thermometer, TrendingUp, Sun } from 'lucide-react'
import type { FeldMapping, HASensorInfo } from '../../api/sensorMapping'
import FeldMappingInput, { SensorAutocomplete } from './FeldMappingInput'
import Alert from '../ui/Alert'
import { useHAAvailable } from '../../hooks/useHAAvailable'

interface BasisSensorenStepProps {
  value: {
    einspeisung: FeldMapping | null
    netzbezug: FeldMapping | null
    pv_gesamt: FeldMapping | null
    strompreis: FeldMapping | null
  }
  onChange: (field: 'einspeisung' | 'netzbezug' | 'pv_gesamt' | 'strompreis', mapping: FeldMapping | null) => void
  availableSensors: HASensorInfo[]
  basisLive?: Record<string, string | null>
  onBasisLiveChange?: (key: string, entityId: string | null) => void
  basisLiveInvert?: Record<string, boolean>
  onBasisLiveInvertChange?: (key: string, invert: boolean) => void
  solcastHaAktiv?: boolean
  onSolcastHaChange?: (aktiv: boolean) => void
  solcastApiKey?: string
  onSolcastApiKeyChange?: (key: string) => void
  solcastResourceIds?: { id: string; name: string }[]
  onSolcastResourceIdsChange?: (ids: { id: string; name: string }[]) => void
}

export default function BasisSensorenStep({
  value,
  onChange,
  availableSensors,
  basisLive = {},
  onBasisLiveChange,
  basisLiveInvert = {},
  onBasisLiveInvertChange,
  solcastHaAktiv = false,
  onSolcastHaChange,
  solcastApiKey = '',
  onSolcastApiKeyChange,
  solcastResourceIds = [],
  onSolcastResourceIdsChange,
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

      {/* Strompreis-Sensor (optional, für dynamische Tarife) */}
      <div className="flex items-start gap-4">
        <div className="w-10 h-10 bg-purple-100 dark:bg-purple-900/30 rounded-lg flex items-center justify-center flex-shrink-0">
          <TrendingUp className="w-5 h-5 text-purple-600 dark:text-purple-400" />
        </div>
        <div className="flex-1">
          <FeldMappingInput
            label="Strompreis (dynamischer Tarif)"
            einheit="ct/kWh"
            value={value.strompreis}
            onChange={mapping => onChange('strompreis', mapping)}
            availableSensors={availableSensors}
            strategieOptionen={[
              {
                value: 'sensor' as const,
                label: 'HA-Sensor',
                description: 'Aktueller Strompreis aus Tibber, aWATTar, EPEX o.ä.',
              },
              {
                value: 'keine' as const,
                label: 'Nicht verwenden',
                description: 'Fester Tarif aus den Strompreis-Einstellungen',
              },
            ]}
            defaultStrategie="keine"
          />
          <p className="mt-2 text-xs text-gray-500">
            Optional: Nur für dynamische Stromtarife. Der Sensor sollte den aktuellen
            Arbeitspreis in ct/kWh liefern (z.B. Tibber, aWATTar, EPEX Spot).
            Wird im Tagesverlauf als Overlay angezeigt und für den verbrauchsgewichteten
            Monats-Durchschnittspreis verwendet.
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
              basisLiveInvert={basisLiveInvert}
              onBasisLiveInvertChange={onBasisLiveInvertChange}
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
                requireStatistics={false}
              />
              {basisLive.pv_gesamt_w && onBasisLiveInvertChange && (
                <label className="flex items-center gap-2 mt-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={!!basisLiveInvert.pv_gesamt_w}
                    onChange={e => onBasisLiveInvertChange('pv_gesamt_w', e.target.checked)}
                    className="rounded border-gray-300 dark:border-gray-600 text-primary-600 focus:ring-primary-500"
                  />
                  <span className="text-xs text-gray-600 dark:text-gray-400">
                    Vorzeichen invertieren (&times;&minus;1)
                  </span>
                </label>
              )}
              <p className="mt-2 text-xs text-gray-500">
                Optional: Nur nötig wenn kein Live-Sensor pro PV-String konfiguriert ist.
                Wird als ein &quot;PV Gesamt&quot;-Knoten im Live-Dashboard angezeigt.
              </p>
            </div>

            {/* Außentemperatur (optional) */}
            <div className="border border-sky-200 dark:border-sky-700/50 rounded-lg p-4">
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  <Thermometer className="w-4 h-4 text-sky-600 dark:text-sky-400" />
                  <span className="font-medium text-sm text-gray-900 dark:text-white">Außentemperatur</span>
                </div>
                <span className="text-xs text-sky-500">optional</span>
              </div>
              <p className="text-xs text-gray-500 dark:text-gray-400 mb-3">
                Eigener Temperatursensor (z.B. Wetterstation am Haus).
                Ohne Zuordnung wird die Temperatur automatisch über Open-Meteo ermittelt.
              </p>
              <SensorAutocomplete
                value={basisLive.aussentemperatur_c}
                onChange={entityId => onBasisLiveChange('aussentemperatur_c', entityId)}
                sensors={availableSensors}
                placeholder="sensor.aussentemperatur"
                requireStatistics={false}
              />
            </div>

            {/* SFML + Solcast: Sensoren werden per Auto-Discovery erkannt (prognose_discovery),
                kein manuelles Mapping nötig. Quellenwahl erfolgt in den Anlagen-Einstellungen. */}

            {/* Solcast PV Forecast (optional — Standalone API-Token) */}
            {onSolcastHaChange && (
              <SolcastConfigBlock
                haAvailable={useHAAvailable()}
                solcastHaAktiv={solcastHaAktiv}
                onSolcastHaChange={onSolcastHaChange}
                solcastApiKey={solcastApiKey}
                onSolcastApiKeyChange={onSolcastApiKeyChange}
                solcastResourceIds={solcastResourceIds}
                onSolcastResourceIdsChange={onSolcastResourceIdsChange}
              />
            )}
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
  basisLiveInvert?: Record<string, boolean>
  onBasisLiveInvertChange?: (key: string, invert: boolean) => void
  availableSensors: HASensorInfo[]
}

function NetzLiveSensoren({ basisLive, onBasisLiveChange, basisLiveInvert = {}, onBasisLiveInvertChange, availableSensors }: NetzLiveSensorenProps) {
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
              requireStatistics={false}
            />
            {basisLive.netz_kombi_w && onBasisLiveInvertChange && (
              <label className="flex items-center gap-2 mt-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={!!basisLiveInvert.netz_kombi_w}
                  onChange={e => onBasisLiveInvertChange('netz_kombi_w', e.target.checked)}
                  className="rounded border-gray-300 dark:border-gray-600 text-primary-600 focus:ring-primary-500"
                />
                <span className="text-xs text-gray-600 dark:text-gray-400">
                  Vorzeichen invertieren (&times;&minus;1)
                </span>
              </label>
            )}
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
                requireStatistics={false}
              />
              {basisLive.einspeisung_w && onBasisLiveInvertChange && (
                <label className="flex items-center gap-2 mt-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={!!basisLiveInvert.einspeisung_w}
                    onChange={e => onBasisLiveInvertChange('einspeisung_w', e.target.checked)}
                    className="rounded border-gray-300 dark:border-gray-600 text-primary-600 focus:ring-primary-500"
                  />
                  <span className="text-xs text-gray-600 dark:text-gray-400">
                    Vorzeichen invertieren (&times;&minus;1)
                  </span>
                </label>
              )}
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
                requireStatistics={false}
              />
              {basisLive.netzbezug_w && onBasisLiveInvertChange && (
                <label className="flex items-center gap-2 mt-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={!!basisLiveInvert.netzbezug_w}
                    onChange={e => onBasisLiveInvertChange('netzbezug_w', e.target.checked)}
                    className="rounded border-gray-300 dark:border-gray-600 text-primary-600 focus:ring-primary-500"
                  />
                  <span className="text-xs text-gray-600 dark:text-gray-400">
                    Vorzeichen invertieren (&times;&minus;1)
                  </span>
                </label>
              )}
            </div>
          </div>
        )}
      </div>
    </>
  )
}


// =============================================================================
// SolcastConfigBlock — HA-Toggle oder API-Token je nach Umgebung
// =============================================================================

interface SolcastConfigBlockProps {
  haAvailable: boolean
  solcastHaAktiv: boolean
  onSolcastHaChange: (aktiv: boolean) => void
  solcastApiKey?: string
  onSolcastApiKeyChange?: (key: string) => void
  solcastResourceIds?: { id: string; name: string }[]
  onSolcastResourceIdsChange?: (ids: { id: string; name: string }[]) => void
}

function SolcastConfigBlock({
  haAvailable,
  solcastHaAktiv,
  onSolcastHaChange,
  solcastApiKey = '',
  onSolcastApiKeyChange,
  solcastResourceIds = [],
  onSolcastResourceIdsChange,
}: SolcastConfigBlockProps) {
  const [newResourceId, setNewResourceId] = useState('')

  return (
    <div className="border border-blue-200 dark:border-blue-700/50 rounded-lg p-4">
      <div className="flex items-center gap-3 mb-2">
        <Sun className="w-5 h-5 text-blue-500" />
        <div>
          <span className="font-medium text-sm text-gray-900 dark:text-white">Solcast PV Forecast</span>
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
            Satellitenbasierte PV-Prognose mit Konfidenzband (p10/p90), 7 Tage.
          </p>
        </div>
      </div>

      {haAvailable ? (
        /* HA-Modus: Toggle für automatische Sensor-Erkennung */
        <>
          <div className="flex items-center justify-between">
            <span className="text-sm text-gray-700 dark:text-gray-300">HA-Integration (BJReplay)</span>
            <label className="relative inline-flex items-center cursor-pointer">
              <input
                type="checkbox"
                checked={solcastHaAktiv}
                onChange={e => onSolcastHaChange(e.target.checked)}
                className="sr-only peer"
              />
              <div className="w-9 h-5 bg-gray-200 peer-focus:outline-none rounded-full peer dark:bg-gray-700 peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all dark:border-gray-600 peer-checked:bg-blue-500" />
            </label>
          </div>
          {solcastHaAktiv && (
            <p className="text-xs text-blue-500 mt-2">
              Sensoren werden automatisch erkannt. Ergebnis sichtbar unter Aussichten → Prognosen.
            </p>
          )}
        </>
      ) : (
        /* Standalone-Modus: API-Token + Resource-IDs */
        <div className="space-y-3 mt-2">
          <div>
            <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">
              API-Token (solcast.com → API Keys)
            </label>
            <input
              type="password"
              value={solcastApiKey}
              onChange={e => onSolcastApiKeyChange?.(e.target.value)}
              placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
              className="w-full px-3 py-1.5 text-sm rounded-lg border bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 border-gray-300 dark:border-gray-600 focus:outline-none focus:ring-1 focus:ring-blue-500"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">
              Resource-IDs (solcast.com → My Sites)
            </label>
            {solcastResourceIds.map((r, i) => (
              <div key={r.id} className="flex items-center gap-2 mb-1">
                <span className="text-xs text-gray-600 dark:text-gray-400 flex-1 truncate">{r.id}</span>
                <button
                  type="button"
                  onClick={() => onSolcastResourceIdsChange?.(solcastResourceIds.filter((_, j) => j !== i))}
                  className="text-xs text-red-500 hover:text-red-700"
                >×</button>
              </div>
            ))}
            <div className="flex gap-2">
              <input
                type="text"
                value={newResourceId}
                onChange={e => setNewResourceId(e.target.value)}
                placeholder="xxxx-xxxx-xxxx-xxxx"
                className="flex-1 px-3 py-1.5 text-sm rounded-lg border bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 border-gray-300 dark:border-gray-600 focus:outline-none focus:ring-1 focus:ring-blue-500"
              />
              <button
                type="button"
                disabled={!newResourceId.trim()}
                onClick={() => {
                  if (newResourceId.trim()) {
                    onSolcastResourceIdsChange?.([...solcastResourceIds, { id: newResourceId.trim(), name: `Site ${solcastResourceIds.length + 1}` }])
                    setNewResourceId('')
                  }
                }}
                className="px-3 py-1.5 text-sm bg-blue-500 text-white rounded-lg hover:bg-blue-600 disabled:opacity-50 disabled:cursor-not-allowed"
              >+</button>
            </div>
          </div>
          <p className="text-xs text-gray-500 dark:text-gray-400">
            Kostenloser Solcast-Account: 10 Abrufe/Tag. eedc cached automatisch.
          </p>
        </div>
      )}
    </div>
  )
}
