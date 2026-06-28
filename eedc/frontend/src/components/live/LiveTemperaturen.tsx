/**
 * LiveTemperaturen — Außen- + Warmwasser-Temperatur-Kacheln des Live-Dashboards.
 *
 * Aus `pages/LiveDashboard.tsx` extrahiert (IA-V4 A.3) — eine Code-Wahrheit für
 * IST-Live + `v4/CockpitLiveV4`. Gibt `null` zurück, wenn keine Temperatur da ist.
 */
import { fmtZahl } from '../../lib'

export default function LiveTemperaturen({ aussenC, tempMinC, tempMaxC, warmwasserC }: {
  aussenC: number | null | undefined
  tempMinC: number | null | undefined
  tempMaxC: number | null | undefined
  warmwasserC: number | null | undefined
}) {
  if (aussenC == null && warmwasserC == null) return null
  return (
    <div className="flex gap-2">
      {aussenC != null && (
        <div className="flex-1 bg-cyan-50 dark:bg-cyan-900/20 rounded-lg px-3 py-1.5"
             title={tempMinC != null && tempMaxC != null
               ? `Min ${fmtZahl(tempMinC, 0)}° / Max ${fmtZahl(tempMaxC, 0)}°C`
               : undefined}>
          <div className="text-xs text-gray-500 dark:text-gray-400">Außen Temperatur</div>
          <div className="text-base font-bold text-cyan-600 dark:text-cyan-400">
            {fmtZahl(aussenC, 1)}<span className="text-xs font-normal ml-0.5">°C</span>
          </div>
        </div>
      )}
      {warmwasserC != null && (
        <div className="flex-1 bg-orange-50 dark:bg-orange-900/20 rounded-lg px-3 py-1.5">
          <div className="text-xs text-gray-500 dark:text-gray-400">Warmwasser Temperatur</div>
          <div className="text-base font-bold text-orange-600 dark:text-orange-400">
            {fmtZahl(warmwasserC, 1)}<span className="text-xs font-normal ml-0.5">°C</span>
          </div>
        </div>
      )}
    </div>
  )
}
