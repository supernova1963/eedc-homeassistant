/**
 * LiveSocBalken — Ladezustand-Balken (SoC) je Batterie/E-Auto aus den Live-Gauges.
 *
 * Aus `pages/LiveDashboard.tsx` extrahiert (IA-V4 A.3) — eine Code-Wahrheit für
 * IST-Live + `v4/CockpitLiveV4`. Rendert nur die `soc_*`-Gauges; gibt `null`
 * zurück, wenn keine vorhanden sind.
 */
import type { LiveGauge } from '../../api/liveDashboard'
import { AMPEL_BG_CLASS } from '../../lib'

export default function LiveSocBalken({ gauges }: { gauges: LiveGauge[] }) {
  const socGauges = gauges.filter((g) => g.key.startsWith('soc_'))
  if (socGauges.length === 0) return null
  return (
    <div>
      <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">Ladezustand</h3>
      <div className="space-y-2">
        {socGauges.map((gauge) => {
          const pct = gauge.max_wert > gauge.min_wert
            ? ((gauge.wert - gauge.min_wert) / (gauge.max_wert - gauge.min_wert)) * 100 : 0
          // SoC-Ampel über die Ampel-SoT (Regel G): leer = kritisch, voll = gut.
          const color = AMPEL_BG_CLASS[pct < 20 ? 'kritisch' : pct < 50 ? 'maessig' : 'gut']
          return (
            <div key={gauge.key} title={`${gauge.label}: ${gauge.wert} ${gauge.einheit}`}>
              <div className="flex items-center justify-between text-xs mb-0.5">
                <span className="text-gray-600 dark:text-gray-400 truncate mr-2">{gauge.label}</span>
                <span className="font-bold text-gray-900 dark:text-white shrink-0">{Math.round(gauge.wert)}{gauge.einheit}</span>
              </div>
              <div className="h-2 bg-gray-200 dark:bg-gray-700 rounded-sm overflow-hidden">
                <div className={`h-full rounded-sm transition-all ${color}`} style={{ width: `${Math.min(100, Math.max(0, pct))}%` }} />
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
