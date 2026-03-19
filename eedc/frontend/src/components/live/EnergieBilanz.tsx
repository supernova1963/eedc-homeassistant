/**
 * EnergieBilanz — Gespiegelte Balken für Erzeugung/Verbrauch.
 *
 * Logarithmische Balkenlänge: log(1 + kW) — damit 0.3 kW Haushalt
 * neben 22 kW E-Auto-Ladung noch sichtbar bleibt.
 * kW-Werte stehen als Text neben den Balken.
 */

import { Sun, Zap, Battery, Car, Flame, Wrench, Home, Plug } from 'lucide-react'
import type { LiveKomponente } from '../../api/liveDashboard'

const ICON_MAP: Record<string, React.ElementType> = {
  sun: Sun,
  zap: Zap,
  battery: Battery,
  car: Car,
  plug: Plug,
  flame: Flame,
  wrench: Wrench,
  home: Home,
}

const COLOR_MAP: Record<string, string> = {
  pv: '#eab308',       // gelb
  netz: '#ef4444',      // rot
  batterie: '#3b82f6',  // blau
  eauto: '#a855f7',     // lila
  waermepumpe: '#f97316', // orange
  sonstige: '#6b7280',  // grau
  haushalt: '#10b981',  // grün
}

/** Farbe für einen Komponenten-Key ermitteln (z.B. "pv_1" → pv-Farbe) */
function getColor(key: string): string {
  if (COLOR_MAP[key]) return COLOR_MAP[key]
  // Prefix vor der Investition-ID extrahieren (z.B. "batterie_3" → "batterie")
  const prefix = key.replace(/_\d+$/, '')
  if (COLOR_MAP[prefix]) return COLOR_MAP[prefix]
  // Basis-Kategorie aus erstem Segment (z.B. "waermepumpe_5_heizen" → "waermepumpe")
  const basis = key.split('_')[0]
  return COLOR_MAP[basis] || '#6b7280'
}

interface EnergieBilanzProps {
  komponenten: LiveKomponente[]
  summeErzeugung: number
  summeVerbrauch: number
  tagesWerte?: Record<string, number | null>
}

/** Logarithmische Skalierung: log(1 + kW) normiert auf maxLog → 0–100% */
function logScale(kw: number, maxLog: number): number {
  if (kw <= 0 || maxLog <= 0) return 0
  return (Math.log(1 + kw) / maxLog) * 100
}

export default function EnergieBilanz({ komponenten, summeErzeugung, summeVerbrauch, tagesWerte }: EnergieBilanzProps) {
  if (komponenten.length === 0) return null

  const rows = komponenten.map((k) => ({
    key: k.key,
    label: k.label,
    icon: k.icon,
    erzeugung: k.erzeugung_kw ?? 0,
    verbrauch: k.verbrauch_kw ?? 0,
  }))

  // Max für log-Normierung
  const allValues = rows.flatMap((r) => [r.erzeugung, r.verbrauch])
  const maxLog = Math.log(1 + Math.max(...allValues, 0.1))

  return (
    <div className="flex flex-col h-full">
      <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3 shrink-0">Energiebilanz</h3>
      <div className="flex-1 flex flex-col justify-evenly min-h-0">
        {rows.map((row) => {
          const Icon = ICON_MAP[row.icon]
          const erzPct = logScale(row.erzeugung, maxLog)
          const vrbPct = logScale(row.verbrauch, maxLog)
          const color = getColor(row.key)

          // Tooltip: aktuell + Tageswert
          const tagesKwh = tagesWerte?.[row.key]
          const tipParts = [row.label]
          if (row.erzeugung > 0) tipParts.push(`Quelle: ${row.erzeugung.toFixed(2)} kW`)
          if (row.verbrauch > 0) tipParts.push(`Verbrauch: ${row.verbrauch.toFixed(2)} kW`)
          if (tagesKwh !== null && tagesKwh !== undefined) tipParts.push(`Heute: ${tagesKwh.toFixed(1)} kWh`)

          return (
            <div key={row.key} className="flex items-center gap-2 min-h-9 py-1 cursor-default" title={tipParts.join('\n')}>
              {/* Label + Icon links */}
              <div className="flex items-center gap-1.5 w-36 shrink-0">
                {Icon && <Icon className="h-4 w-4 text-gray-500 dark:text-gray-400 shrink-0" />}
                <span className="text-xs text-gray-700 dark:text-gray-300 truncate">{row.label}</span>
              </div>

              {/* Erzeugung (links, wächst nach links) */}
              <div className="flex-1 flex justify-end items-center gap-1">
                {row.erzeugung > 0 && (
                  <span className="text-xs text-green-600 dark:text-green-400 tabular-nums shrink-0">
                    {row.erzeugung.toFixed(2)}
                  </span>
                )}
                <div className="w-full relative h-6">
                  {row.erzeugung > 0 && (
                    <div
                      className="absolute right-0 top-0.5 h-5 rounded-l transition-all duration-500"
                      style={{
                        width: `${erzPct}%`,
                        backgroundColor: '#22c55e',
                        opacity: 0.8,
                      }}
                    />
                  )}
                </div>
              </div>

              {/* Trennlinie */}
              <div className="w-px h-6 bg-gray-300 dark:bg-gray-600 shrink-0" />

              {/* Verbrauch (rechts, wächst nach rechts) */}
              <div className="flex-1 flex items-center gap-1">
                <div className="w-full relative h-6">
                  {row.verbrauch > 0 && (
                    <div
                      className="absolute left-0 top-0.5 h-5 rounded-r transition-all duration-500"
                      style={{
                        width: `${vrbPct}%`,
                        backgroundColor: color,
                        opacity: 0.8,
                      }}
                    />
                  )}
                </div>
                {row.verbrauch > 0 && (
                  <span className="text-xs text-gray-600 dark:text-gray-400 tabular-nums shrink-0">
                    {row.verbrauch.toFixed(2)}
                  </span>
                )}
              </div>
            </div>
          )
        })}
      </div>

      {/* Achsen-Beschriftung */}
      <div className="flex items-center mt-1 pl-36 text-[10px] text-gray-400 dark:text-gray-500 shrink-0">
        <div className="flex-1 text-right">Quellen (kW)</div>
        <div className="w-px mx-1" />
        <div className="flex-1 text-left">Verbrauch (kW)</div>
      </div>

      {/* Summenzeile */}
      <div className="flex justify-between text-sm text-gray-600 dark:text-gray-400 mt-2 px-2 shrink-0">
        <span className="text-green-600 dark:text-green-400">
          Quellen: {summeErzeugung.toFixed(2)} kW
        </span>
        <span className="text-red-600 dark:text-red-400">
          Verbrauch: {summeVerbrauch.toFixed(2)} kW
        </span>
      </div>
    </div>
  )
}
