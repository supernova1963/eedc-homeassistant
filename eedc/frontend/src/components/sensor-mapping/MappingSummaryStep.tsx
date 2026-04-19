/**
 * MappingSummaryStep - Zusammenfassung des Sensor-Mappings
 */

import { useState } from 'react'
import {
  CheckCircle,
  Wifi,
  Calculator,
  Percent,
  Edit3,
  MinusCircle,
  Zap,
  Sun,
  Battery,
  Thermometer,
  Car,
  Activity,
  AlertTriangle,
  History,
  Loader2,
} from 'lucide-react'
import type { FeldMapping, InvestitionInfo, StrategieTyp } from '../../api/sensorMapping'
import { energieProfilApi, type VollbackfillResult } from '../../api/energie_profil'

interface MappingSummaryStepProps {
  state: {
    basis: {
      einspeisung: FeldMapping | null
      netzbezug: FeldMapping | null
      pv_gesamt: FeldMapping | null
    }
    investitionen: Record<string, Record<string, FeldMapping>>
    basisLive: Record<string, string | null>
    investitionenLive: Record<string, Record<string, string | null>>
    basisLiveInvert: Record<string, boolean>
    investitionenLiveInvert: Record<string, Record<string, boolean>>
    solcastHaAktiv: boolean
  }
  investitionen: InvestitionInfo[]
  anlageId?: number | null
}

const STRATEGIE_ICONS: Record<StrategieTyp, React.ReactNode> = {
  sensor: <Wifi className="w-4 h-4 text-green-500" />,
  kwp_verteilung: <Percent className="w-4 h-4 text-blue-500" />,
  cop_berechnung: <Calculator className="w-4 h-4 text-purple-500" />,
  ev_quote: <Percent className="w-4 h-4 text-amber-500" />,
  manuell: <Edit3 className="w-4 h-4 text-gray-500" />,
  keine: <MinusCircle className="w-4 h-4 text-gray-400" />,
}

const STRATEGIE_LABELS: Record<StrategieTyp, string> = {
  sensor: 'HA-Sensor',
  kwp_verteilung: 'kWp-Verteilung',
  cop_berechnung: 'COP-Berechnung',
  ev_quote: 'EV-Quote',
  manuell: 'Manuell',
  keine: 'Nicht erfassen',
}

const TYP_ICONS: Record<string, React.ReactNode> = {
  'pv-module': <Sun className="w-4 h-4" />,
  speicher: <Battery className="w-4 h-4" />,
  waermepumpe: <Thermometer className="w-4 h-4" />,
  'e-auto': <Car className="w-4 h-4" />,
  wallbox: <Zap className="w-4 h-4" />,
}

const LIVE_KEY_LABELS: Record<string, string> = {
  einspeisung_w: 'Einspeisung',
  netzbezug_w: 'Netzbezug',
  netz_kombi_w: 'Netz (Kombi)',
  aussentemperatur_c: 'Außentemperatur',
  leistung_w: 'Leistung',
  soc: 'SoC',
  warmwasser_temperatur_c: 'Warmwasser',
}

function MappingRow({ label, mapping }: { label: string; mapping: FeldMapping | null }) {
  if (!mapping) {
    return (
      <div className="flex items-center justify-between py-2 border-b border-gray-100 dark:border-gray-700 last:border-0">
        <span className="text-sm text-gray-600 dark:text-gray-400">{label}</span>
        <span className="text-sm text-gray-400 italic">Nicht konfiguriert</span>
      </div>
    )
  }

  return (
    <div className="flex items-center justify-between py-2 border-b border-gray-100 dark:border-gray-700 last:border-0">
      <span className="text-sm text-gray-600 dark:text-gray-400">{label}</span>
      <div className="flex items-center gap-2">
        {STRATEGIE_ICONS[mapping.strategie]}
        <span className="text-sm font-medium text-gray-900 dark:text-white">
          {STRATEGIE_LABELS[mapping.strategie]}
        </span>
        {mapping.strategie === 'sensor' && mapping.sensor_id && (
          <span className="text-xs text-gray-500 max-w-[200px] truncate">
            ({mapping.sensor_id})
          </span>
        )}
        {mapping.strategie === 'cop_berechnung' && mapping.parameter?.cop && (
          <span className="text-xs text-gray-500">
            (COP: {mapping.parameter.cop})
          </span>
        )}
        {mapping.strategie === 'kwp_verteilung' && mapping.parameter?.anteil && (
          <span className="text-xs text-gray-500">
            ({((mapping.parameter.anteil as number) * 100).toFixed(1)}%)
          </span>
        )}
      </div>
    </div>
  )
}

function LiveSensorRow({ label, entityId, inverted }: { label: string; entityId: string | null; inverted?: boolean }) {
  return (
    <div className="flex items-center justify-between py-2 border-b border-gray-100 dark:border-gray-700 last:border-0">
      <span className="text-sm text-gray-600 dark:text-gray-400">{label}</span>
      {entityId ? (
        <div className="flex items-center gap-2">
          <span className="text-xs text-green-700 dark:text-green-400 font-mono max-w-[250px] truncate">
            {entityId}
          </span>
          {inverted && (
            <span className="text-xs text-amber-600 dark:text-amber-400 font-medium">×−1</span>
          )}
        </div>
      ) : (
        <span className="text-sm text-gray-400 italic">Nicht zugeordnet</span>
      )}
    </div>
  )
}

export default function MappingSummaryStep({
  state,
  investitionen,
  anlageId,
}: MappingSummaryStepProps) {
  const [isBackfilling, setIsBackfilling] = useState(false)
  const [backfillResult, setBackfillResult] = useState<VollbackfillResult | null>(null)
  const [backfillError, setBackfillError] = useState<string | null>(null)

  const handleVollbackfill = async () => {
    if (!anlageId) return
    setIsBackfilling(true)
    setBackfillError(null)
    setBackfillResult(null)
    try {
      const result = await energieProfilApi.vollbackfill(anlageId)
      setBackfillResult(result)
    } catch (e) {
      setBackfillError(e instanceof Error ? e.message : 'Fehler beim Backfill')
    } finally {
      setIsBackfilling(false)
    }
  }
  // Statistiken berechnen
  const stats = {
    sensor: 0,
    kwp_verteilung: 0,
    cop_berechnung: 0,
    ev_quote: 0,
    manuell: 0,
    keine: 0,
  }

  const countStrategy = (mapping: FeldMapping | null) => {
    if (mapping?.strategie) {
      stats[mapping.strategie]++
    }
  }

  // Basis zählen
  countStrategy(state.basis.einspeisung)
  countStrategy(state.basis.netzbezug)
  countStrategy(state.basis.pv_gesamt)

  // Investitionen zählen
  Object.values(state.investitionen).forEach(felder => {
    Object.values(felder).forEach(mapping => {
      countStrategy(mapping)
    })
  })

  const totalConfigured = stats.sensor + stats.kwp_verteilung + stats.cop_berechnung + stats.ev_quote + stats.manuell

  // Live-Sensoren zählen
  const basisLive = state.basisLive || {}
  const invLive = state.investitionenLive || {}
  const basisLiveEntries = Object.entries(basisLive).filter(([, v]) => v)
  const invLiveEntries = Object.entries(invLive).flatMap(([, sensors]) =>
    Object.entries(sensors).filter(([, v]) => v)
  )
  const totalLive = basisLiveEntries.length + invLiveEntries.length

  return (
    <div className="space-y-6">
      {/* Statistik-Übersicht */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-4">
        <StatCard
          icon={<Wifi className="w-5 h-5 text-green-500" />}
          label="HA-Sensor"
          count={stats.sensor}
        />
        <StatCard
          icon={<Percent className="w-5 h-5 text-blue-500" />}
          label="kWp-Verteilung"
          count={stats.kwp_verteilung}
        />
        <StatCard
          icon={<Calculator className="w-5 h-5 text-purple-500" />}
          label="COP-Berechnung"
          count={stats.cop_berechnung}
        />
        <StatCard
          icon={<Percent className="w-5 h-5 text-amber-500" />}
          label="EV-Quote"
          count={stats.ev_quote}
        />
        <StatCard
          icon={<Edit3 className="w-5 h-5 text-gray-500" />}
          label="Manuell"
          count={stats.manuell}
        />
        <StatCard
          icon={<Activity className="w-5 h-5 text-primary-500" />}
          label="Live-Sensoren"
          count={totalLive}
        />
      </div>

      {/* Gesamt-Info */}
      <div className="bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg p-4">
        <div className="flex items-center gap-2">
          <CheckCircle className="w-5 h-5 text-green-600 dark:text-green-400" />
          <span className="font-medium text-green-800 dark:text-green-200">
            {totalConfigured} Felder konfiguriert, {totalLive} Live-Sensoren
          </span>
        </div>
      </div>

      {/* Warnung wenn keine Live-Sensoren */}
      {totalLive === 0 && (
        <div className="bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-lg p-4">
          <div className="flex items-center gap-2">
            <AlertTriangle className="w-5 h-5 text-amber-600 dark:text-amber-400" />
            <span className="font-medium text-amber-800 dark:text-amber-200">
              Keine Live-Sensoren zugeordnet — das Live-Dashboard bleibt leer
            </span>
          </div>
        </div>
      )}

      {/* Basis-Sensoren (Energie) */}
      <div className="border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden">
        <div className="px-4 py-3 bg-gray-50 dark:bg-gray-700/50 flex items-center gap-2">
          <Zap className="w-5 h-5 text-amber-500" />
          <h3 className="font-medium text-gray-900 dark:text-white">Basis-Sensoren (Energie)</h3>
        </div>
        <div className="px-4 py-2">
          <MappingRow label="Einspeisung" mapping={state.basis.einspeisung} />
          <MappingRow label="Netzbezug" mapping={state.basis.netzbezug} />
          <MappingRow label="PV Gesamt" mapping={state.basis.pv_gesamt} />
        </div>
      </div>

      {/* Basis Live-Sensoren */}
      {Object.keys(basisLive).length > 0 && (
        <div className="border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden">
          <div className="px-4 py-3 bg-gray-50 dark:bg-gray-700/50 flex items-center gap-2">
            <Activity className="w-5 h-5 text-primary-500" />
            <h3 className="font-medium text-gray-900 dark:text-white">Basis Live-Sensoren (W)</h3>
          </div>
          <div className="px-4 py-2">
            {Object.entries(basisLive).map(([key, entityId]) => (
              <LiveSensorRow
                key={key}
                label={LIVE_KEY_LABELS[key] || key}
                entityId={entityId}
                inverted={state.basisLiveInvert?.[key]}
              />
            ))}
          </div>
        </div>
      )}

      {/* Solcast PV Forecast */}
      {state.solcastHaAktiv && (
        <div className="border border-blue-200 dark:border-blue-700/50 rounded-lg overflow-hidden">
          <div className="px-4 py-3 bg-blue-50 dark:bg-blue-900/20 flex items-center gap-2">
            <Sun className="w-5 h-5 text-blue-500" />
            <h3 className="font-medium text-gray-900 dark:text-white">Solcast PV Forecast</h3>
            <span className="text-xs text-blue-500 ml-auto">HA-Integration</span>
          </div>
          <div className="px-4 py-2 text-sm text-gray-600 dark:text-gray-400">
            Automatische Erkennung der Solcast-Sensoren (unabhängig von der HA-Spracheinstellung).
            Prognosen für 7 Tage mit Konfidenzband (p10/p90), sichtbar unter Aussichten → Prognosen.
          </div>
        </div>
      )}

      {/* Investitionen */}
      {/* Energieprofil-Verlauf nachberechnen */}
      {anlageId != null && (
        <div className="border border-blue-200 dark:border-blue-800 rounded-lg p-4 bg-blue-50 dark:bg-blue-900/20">
          <div className="flex items-start justify-between gap-4">
            <div>
              <h3 className="font-medium text-blue-900 dark:text-blue-100">Energieprofil-Verlauf nachberechnen</h3>
              <p className="text-sm text-blue-700 dark:text-blue-300 mt-1">
                Füllt stündliche Energieprofile aus der HA Long-Term Statistics — unabhängig von der ~10-Tage-Grenze der Sensor-History.
              </p>
              {backfillResult && (
                <p className="text-sm text-blue-800 dark:text-blue-200 mt-2 font-medium">
                  ✓ {backfillResult.geschrieben} Tage geschrieben ({backfillResult.von} – {backfillResult.bis})
                </p>
              )}
              {backfillError && (
                <p className="text-sm text-red-700 dark:text-red-300 mt-2">{backfillError}</p>
              )}
            </div>
            <button
              type="button"
              onClick={handleVollbackfill}
              disabled={isBackfilling}
              className="shrink-0 flex items-center gap-2 px-3 py-2 text-sm font-medium rounded-lg bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {isBackfilling
                ? <><Loader2 className="w-4 h-4 animate-spin" /> Wird berechnet…</>
                : <><History className="w-4 h-4" /> Verlauf nachberechnen</>
              }
            </button>
          </div>
        </div>
      )}

      {investitionen.map(inv => {
        const felder = state.investitionen[inv.id.toString()] || {}
        const live = invLive[inv.id.toString()] || {}
        const hasFelder = Object.keys(felder).length > 0
        const hasLive = Object.values(live).some(v => v)
        if (!hasFelder && !hasLive) return null

        return (
          <div key={inv.id} className="border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden">
            <div className="px-4 py-3 bg-gray-50 dark:bg-gray-700/50 flex items-center gap-2">
              <span className="text-gray-600 dark:text-gray-400">
                {TYP_ICONS[inv.typ] || <Zap className="w-4 h-4" />}
              </span>
              <h3 className="font-medium text-gray-900 dark:text-white">{inv.bezeichnung}</h3>
              <span className="text-xs text-gray-500">({inv.typ})</span>
            </div>
            <div className="px-4 py-2">
              {Object.entries(felder).map(([field, mapping]) => (
                <MappingRow
                  key={field}
                  label={field.replace(/_/g, ' ').replace('kwh', '(kWh)')}
                  mapping={mapping}
                />
              ))}
              {Object.entries(live).filter(([, v]) => v).length > 0 && (
                <>
                  <div className="flex items-center gap-1 pt-2 pb-1">
                    <Activity className="w-3 h-3 text-primary-500" />
                    <span className="text-xs font-medium text-primary-600 dark:text-primary-400">Live</span>
                  </div>
                  {Object.entries(live).map(([key, entityId]) =>
                    entityId ? (
                      <LiveSensorRow
                        key={key}
                        label={LIVE_KEY_LABELS[key] || key}
                        entityId={entityId}
                        inverted={state.investitionenLiveInvert?.[inv.id.toString()]?.[key]}
                      />
                    ) : null
                  )}
                </>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}

function StatCard({
  icon,
  label,
  count,
}: {
  icon: React.ReactNode
  label: string
  count: number
}) {
  return (
    <div className="bg-gray-50 dark:bg-gray-700/50 rounded-lg p-3 text-center">
      <div className="flex justify-center mb-1">{icon}</div>
      <div className="text-lg font-bold text-gray-900 dark:text-white">{count}</div>
      <div className="text-xs text-gray-500">{label}</div>
    </div>
  )
}
