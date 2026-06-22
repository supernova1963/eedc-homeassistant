/**
 * LiveHeuteKacheln — die „Heute"-Tageswerte des Live-Dashboards (Live-KPI-Strip).
 *
 * Aus `pages/LiveDashboard.tsx` extrahiert (IA-V4 A.3): EINE Code-Wahrheit für
 * IST-Live (rechte Sidebar) UND `v4/CockpitLiveV4` (rechte 1/3-Spalte). Bewusst
 * das kompakte 2-Spalten-Micro-Tile-Grid (kein KpiStrip — dessen 248px-Mindest-
 * breite würde die 1/3-Spalte zu hoch machen und die „auf einen Blick"-Balance
 * mit dem Energiefluss-SVG brechen). „Live-KPI-Strip" (KONZEPT Z.76) = Rolle,
 * nicht KPICard-Geometrie.
 *
 * Reihenfolge nach Energiebilanz (#157 detLAN):
 *   Quellen:    PV + Batterie-Entladung      → Σ Eigenverbrauch
 *   Verbrauch:  Eigenverbrauch + Netzbezug   → Σ Hausverbrauch
 *   Einspeisung als PV-Überschuss separat am Ende.
 */
import { Info } from 'lucide-react'
import type { LiveDashboardResponse } from '../../api/liveDashboard'
import { SimpleTooltip } from '../ui/FormelTooltip'

export default function LiveHeuteKacheln({ data }: { data: LiveDashboardResponse }) {
  if (data.heute_pv_kwh === null && data.heute_einspeisung_kwh === null && data.heute_netzbezug_kwh === null) {
    return null
  }
  return (
    <div>
      <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">Heute</h3>
      <div className="grid grid-cols-2 gap-2">
        {data.heute_pv_kwh !== null && (
          <div className="bg-yellow-50 dark:bg-yellow-900/20 rounded-lg px-3 py-2"
               title={data.gestern_pv_kwh !== null ? `Gestern: ${data.gestern_pv_kwh.toFixed(1)} kWh` : undefined}>
            <div className="text-xs text-gray-500 dark:text-gray-400">PV-Erzeugung</div>
            <div className="text-lg font-bold text-yellow-600 dark:text-yellow-400">{data.heute_pv_kwh.toFixed(1)}<span className="text-xs font-normal ml-0.5">kWh</span></div>
          </div>
        )}
        {/* Batterie heute (Ladung/Entladung) */}
        {(() => {
          const komp = data.heute_kwh_pro_komponente
          if (!komp) return null
          let ladung = 0, entladung = 0, found = false
          for (const [k, v] of Object.entries(komp)) {
            if (k.endsWith('_ladung') && k.startsWith('batterie_')) { ladung += v; found = true }
            if (k.endsWith('_entladung') && k.startsWith('batterie_')) { entladung += v; found = true }
          }
          if (!found) return null
          return (
            <div className="bg-teal-50 dark:bg-teal-900/20 rounded-lg px-3 py-2"
                 title={`Batterie heute\nLadung: ${ladung.toFixed(1)} kWh\nEntladung: ${entladung.toFixed(1)} kWh`}>
              <div className="text-xs text-gray-500 dark:text-gray-400">Batterie</div>
              <div className="text-lg font-bold text-teal-600 dark:text-teal-400">
                <span title="Ladung (in den Speicher)">&#9660;{ladung.toFixed(1)}</span>
                <span className="text-gray-400 dark:text-gray-500 mx-0.5">/</span>
                <span title="Entladung (aus dem Speicher)">&#9650;{entladung.toFixed(1)}</span>
                <span className="text-xs font-normal ml-0.5">kWh</span>
              </div>
            </div>
          )
        })()}
        {data.heute_eigenverbrauch_kwh !== null && (
          <div className="bg-blue-50 dark:bg-blue-900/20 rounded-lg px-3 py-2">
            <div className="text-xs text-gray-500 dark:text-gray-400">Eigenverbrauch <SimpleTooltip text={`Selbst genutzter PV-Strom (Direktverbrauch + Batterieentladung)${data.gestern_eigenverbrauch_kwh !== null ? ` | Gestern: ${data.gestern_eigenverbrauch_kwh.toFixed(1)} kWh` : ''}`}><Info className="inline w-3 h-3 opacity-50 cursor-help" /></SimpleTooltip></div>
            <div className="text-lg font-bold text-blue-600 dark:text-blue-400">{data.heute_eigenverbrauch_kwh.toFixed(1)}<span className="text-xs font-normal ml-0.5">kWh</span></div>
          </div>
        )}
        {data.heute_netzbezug_kwh !== null && (
          <div className="bg-red-50 dark:bg-red-900/20 rounded-lg px-3 py-2">
            <div className="text-xs text-gray-500 dark:text-gray-400">Netzbezug <SimpleTooltip text={`Strom der aus dem Netz bezogen wird (nicht durch PV gedeckt)${data.gestern_netzbezug_kwh !== null ? ` | Gestern: ${data.gestern_netzbezug_kwh.toFixed(1)} kWh` : ''}`}><Info className="inline w-3 h-3 opacity-50 cursor-help" /></SimpleTooltip></div>
            <div className="text-lg font-bold text-red-600 dark:text-red-400">{data.heute_netzbezug_kwh.toFixed(1)}<span className="text-xs font-normal ml-0.5">kWh</span></div>
          </div>
        )}
        {/* Hausverbrauch heute (= Eigenverbrauch + Netzbezug) */}
        {data.heute_kwh_pro_komponente?.haushalt != null && (
          <div className="bg-indigo-50 dark:bg-indigo-900/20 rounded-lg px-3 py-2">
            <div className="text-xs text-gray-500 dark:text-gray-400">Hausverbrauch <SimpleTooltip text="Gesamter Stromverbrauch des Haushalts (Eigenverbrauch + Netzbezug)"><Info className="inline w-3 h-3 opacity-50 cursor-help" /></SimpleTooltip></div>
            <div className="text-lg font-bold text-indigo-600 dark:text-indigo-400">{data.heute_kwh_pro_komponente.haushalt.toFixed(1)}<span className="text-xs font-normal ml-0.5">kWh</span></div>
          </div>
        )}
        {/* Einspeisung als PV-Überschuss zum Schluss */}
        {data.heute_einspeisung_kwh !== null && (
          <div className="bg-green-50 dark:bg-green-900/20 rounded-lg px-3 py-2"
               title={`PV-Strom der ins Netz eingespeist wird${data.gestern_einspeisung_kwh !== null ? `\nGestern: ${data.gestern_einspeisung_kwh.toFixed(1)} kWh` : ''}`}>
            <div className="text-xs text-gray-500 dark:text-gray-400">Einspeisung</div>
            <div className="text-lg font-bold text-green-600 dark:text-green-400">{data.heute_einspeisung_kwh.toFixed(1)}<span className="text-xs font-normal ml-0.5">kWh</span></div>
          </div>
        )}
      </div>
      {/* Autarkie + Eigenverbrauchsquote */}
      {(() => {
        const ev = data.heute_eigenverbrauch_kwh
        const nb = data.heute_netzbezug_kwh
        const pv = data.heute_pv_kwh
        const autarkie = ev !== null && nb !== null && (ev + nb) > 0
          ? (ev / (ev + nb)) * 100 : null
        // Cap analog zum Backend-Pattern aus 588a8b07: Bat-Entladung aus Vortagen
        // kann ev > pv erzeugen (Zähler/Nenner gemischter Zeitraum) — visuell auf 100 % begrenzen
        const evQuote = ev !== null && pv !== null && pv > 0
          ? Math.min((ev / pv) * 100, 100) : null
        if (autarkie === null && evQuote === null) return null
        return (
          <div className="grid grid-cols-2 gap-2 mt-2">
            {autarkie !== null && (
              <div className="bg-emerald-50 dark:bg-emerald-900/20 rounded-lg px-3 py-1.5">
                <div className="text-xs text-gray-500 dark:text-gray-400">Autarkie</div>
                <div className="text-base font-bold text-emerald-600 dark:text-emerald-400">{autarkie.toFixed(0)}<span className="text-xs font-normal">%</span></div>
              </div>
            )}
            {evQuote !== null && (
              <div className="bg-sky-50 dark:bg-sky-900/20 rounded-lg px-3 py-1.5">
                <div className="text-xs text-gray-500 dark:text-gray-400">Eigenverbrauch</div>
                <div className="text-base font-bold text-sky-600 dark:text-sky-400">{evQuote.toFixed(0)}<span className="text-xs font-normal">%</span></div>
              </div>
            )}
          </div>
        )
      })()}
    </div>
  )
}
