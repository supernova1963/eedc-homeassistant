/**
 * Energie-Fluss-Diagramm: Visualisiert PV-Verteilung und Haus-Versorgung
 */

import { Zap, Sun, Home } from 'lucide-react'
import { Card } from '../../components/ui'
import type { CockpitUebersicht } from '../../api/cockpit'

export default function EnergyFlowDiagram({ data }: { data: CockpitUebersicht }) {
  const pv = data.pv_erzeugung_kwh
  if (pv <= 0) return null

  const direkt = Math.max(0, data.direktverbrauch_kwh)
  const speicherLad = data.hat_speicher ? Math.max(0, data.speicher_ladung_kwh) : 0
  const einspeis = Math.max(0, data.einspeisung_kwh)
  const pvSum = direkt + speicherLad + einspeis || pv

  const speicherEntl = data.hat_speicher ? Math.max(0, data.speicher_entladung_kwh) : 0
  const netz = Math.max(0, data.netzbezug_kwh)
  const hausSum = direkt + speicherEntl + netz || data.gesamtverbrauch_kwh

  const fmt = (v: number) => v >= 1000 ? `${(v / 1000).toFixed(1)} MWh` : `${v.toFixed(0)} kWh`
  const pct = (v: number, total: number) => total > 0 ? Math.round((v / total) * 100) : 0

  return (
    <Card className="p-4">
      <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3 flex items-center gap-2">
        <Zap className="h-4 w-4 text-yellow-500" />
        Energie-Fluss
      </h3>
      <div className="space-y-4">

        {/* PV-Verteilung */}
        <div>
          <div className="flex justify-between items-center mb-1.5">
            <span className="text-xs text-gray-500 flex items-center gap-1.5">
              <Sun className="h-3.5 w-3.5 text-yellow-500" />
              <span>PV erzeugt: <strong className="text-gray-700 dark:text-gray-300">{fmt(pv)}</strong></span>
            </span>
            <span className="text-xs text-gray-400">Wohin?</span>
          </div>
          <div className="flex h-7 rounded-lg overflow-hidden gap-px bg-gray-100 dark:bg-gray-700">
            {direkt > 0 && (
              <div className="bg-blue-500 flex items-center justify-center transition-all"
                style={{ width: `${pct(direkt, pvSum)}%` }}
                title={`Direktverbrauch: ${fmt(direkt)}`}>
                {pct(direkt, pvSum) >= 12 && (
                  <span className="text-xs text-white font-medium">{pct(direkt, pvSum)}%</span>
                )}
              </div>
            )}
            {speicherLad > 0 && (
              <div className="bg-green-500 flex items-center justify-center"
                style={{ width: `${pct(speicherLad, pvSum)}%` }}
                title={`Speicher: ${fmt(speicherLad)}`}>
                {pct(speicherLad, pvSum) >= 12 && (
                  <span className="text-xs text-white font-medium">{pct(speicherLad, pvSum)}%</span>
                )}
              </div>
            )}
            {einspeis > 0 && (
              <div className="bg-orange-400 flex items-center justify-center"
                style={{ width: `${pct(einspeis, pvSum)}%` }}
                title={`Einspeisung: ${fmt(einspeis)}`}>
                {pct(einspeis, pvSum) >= 12 && (
                  <span className="text-xs text-white font-medium">{pct(einspeis, pvSum)}%</span>
                )}
              </div>
            )}
          </div>
          <div className="flex gap-4 mt-1.5 flex-wrap">
            <span className="text-xs text-gray-500 flex items-center gap-1">
              <span className="w-2.5 h-2.5 rounded-sm bg-blue-500 inline-block flex-shrink-0" />
              Direkt {fmt(direkt)}
            </span>
            {speicherLad > 0 && (
              <span className="text-xs text-gray-500 flex items-center gap-1">
                <span className="w-2.5 h-2.5 rounded-sm bg-green-500 inline-block flex-shrink-0" />
                Speicher {fmt(speicherLad)}
              </span>
            )}
            <span className="text-xs text-gray-500 flex items-center gap-1">
              <span className="w-2.5 h-2.5 rounded-sm bg-orange-400 inline-block flex-shrink-0" />
              Einspeis. {fmt(einspeis)}
            </span>
          </div>
        </div>

        {/* Haus-Versorgung */}
        <div>
          <div className="flex justify-between items-center mb-1.5">
            <span className="text-xs text-gray-500 flex items-center gap-1.5">
              <Home className="h-3.5 w-3.5 text-purple-500" />
              <span>Haus verbraucht: <strong className="text-gray-700 dark:text-gray-300">{fmt(data.gesamtverbrauch_kwh)}</strong></span>
            </span>
            <span className="text-xs text-gray-400">Woher?</span>
          </div>
          <div className="flex h-7 rounded-lg overflow-hidden gap-px bg-gray-100 dark:bg-gray-700">
            {direkt > 0 && (
              <div className="bg-blue-500 flex items-center justify-center"
                style={{ width: `${pct(direkt, hausSum)}%` }}
                title={`PV direkt: ${fmt(direkt)}`}>
                {pct(direkt, hausSum) >= 12 && (
                  <span className="text-xs text-white font-medium">{pct(direkt, hausSum)}%</span>
                )}
              </div>
            )}
            {speicherEntl > 0 && (
              <div className="bg-green-500 flex items-center justify-center"
                style={{ width: `${pct(speicherEntl, hausSum)}%` }}
                title={`Speicher: ${fmt(speicherEntl)}`}>
                {pct(speicherEntl, hausSum) >= 12 && (
                  <span className="text-xs text-white font-medium">{pct(speicherEntl, hausSum)}%</span>
                )}
              </div>
            )}
            {netz > 0 && (
              <div className="bg-red-400 flex items-center justify-center"
                style={{ width: `${pct(netz, hausSum)}%` }}
                title={`Netzbezug: ${fmt(netz)}`}>
                {pct(netz, hausSum) >= 12 && (
                  <span className="text-xs text-white font-medium">{pct(netz, hausSum)}%</span>
                )}
              </div>
            )}
          </div>
          <div className="flex gap-4 mt-1.5 flex-wrap">
            <span className="text-xs text-gray-500 flex items-center gap-1">
              <span className="w-2.5 h-2.5 rounded-sm bg-blue-500 inline-block flex-shrink-0" />
              PV direkt {fmt(direkt)}
            </span>
            {speicherEntl > 0 && (
              <span className="text-xs text-gray-500 flex items-center gap-1">
                <span className="w-2.5 h-2.5 rounded-sm bg-green-500 inline-block flex-shrink-0" />
                Speicher {fmt(speicherEntl)}
              </span>
            )}
            <span className="text-xs text-gray-500 flex items-center gap-1">
              <span className="w-2.5 h-2.5 rounded-sm bg-red-400 inline-block flex-shrink-0" />
              Netzbezug {fmt(netz)}
            </span>
          </div>
        </div>

      </div>
    </Card>
  )
}
