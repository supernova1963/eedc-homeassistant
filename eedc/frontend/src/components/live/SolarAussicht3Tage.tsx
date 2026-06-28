/**
 * SolarAussicht3Tage — 3-Tage-Solar-Vorschau (Heute/Morgen/Übermorgen) mit
 * VM/NM-Split + Verbrauchsprognose-Zeile unter „Heute".
 *
 * Aus `pages/LiveDashboard.tsx` extrahiert (IA-V4 A.3) — EINE Code-Wahrheit für
 * IST-Live + `v4/CockpitLiveV4`. Reine Darstellung; `heutePvKwh` (IST-PV heute)
 * fließt in den „verbleibend/übertroffen"-Vergleich der Heute-Zeile ein.
 */
import { Info } from 'lucide-react'
import type { LiveWetterResponse } from '../../api/liveDashboard'
import type { SolarPrognoseTag } from '../../api/wetter'
import { SimpleTooltip } from '../ui/FormelTooltip'
import { fmtZahl } from '../../lib'

export default function SolarAussicht3Tage({ prognose3Tage, wetter, heutePvKwh }: {
  prognose3Tage: SolarPrognoseTag[]
  wetter: LiveWetterResponse | null
  heutePvKwh: number | null
}) {
  if (!prognose3Tage || prognose3Tage.length === 0) return null
  return (
    <div>
      <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">
        Solar-Aussicht{wetter?.prognose_quelle && wetter.prognose_quelle !== 'eedc' && ` (${wetter.prognose_quelle === 'solcast' ? 'Solcast' : 'SFML'})`} <SimpleTooltip text={`${wetter?.prognose_quelle === 'solcast' ? 'Solcast-Prognose (pur)' : wetter?.prognose_quelle === 'sfml' ? 'Solar Forecast ML (pur)' : 'GTI-basierte Prognose (Open-Meteo) mit Lernfaktor'}. VM/NM = Split an Solar Noon.`}><Info className="inline w-3 h-3 text-gray-400 dark:text-gray-500 opacity-50 cursor-help" /></SimpleTooltip>
      </h3>
      {prognose3Tage.some(t => t.pv_ertrag_morgens_kwh != null) && (
        <div className="grid grid-cols-[auto_1fr_7rem] px-3 mb-0.5">
          <span />
          <span />
          <span className="text-[10px] text-right">
            <span className="text-amber-500">VM</span>
            <span className="text-gray-400 dark:text-gray-500 mx-0.5">/</span>
            <span className="text-yellow-500">NM</span>
          </span>
        </div>
      )}
      <div className="space-y-1.5">
        {prognose3Tage.map((tag, i) => {
          const label = i === 0 ? 'Heute' : i === 1 ? 'Morgen' : 'Übermorgen'
          const hasVmNm = tag.pv_ertrag_morgens_kwh != null
          const isProminent = i < 3
          const verbrPrognKwh = i === 0 && wetter?.verbrauchsprofil?.length
            ? wetter.verbrauchsprofil.reduce((s, v) => s + v.verbrauch_kw, 0)
            : null
          const verbrTooltip = wetter?.profil_typ?.startsWith('individuell')
            ? `Individuelles Profil (${wetter.profil_typ === 'individuell_wochenende' ? 'Wochenende' : 'Werktag'}, ${wetter.profil_tage ?? '?'} Tage) — Haus + Batterie + WP + Wallbox + Sonstige`
            : 'BDEW H0 Standardlastprofil — Haus + Batterie + WP + Wallbox + Sonstige'
          const verbleibenKwh = i === 0 && wetter?.pv_prognose_kwh != null ? (() => {
            const diff = wetter.pv_prognose_kwh - (heutePvKwh ?? 0)
            const nachSU = wetter.sunset ? (() => {
              const now = new Date()
              const [h, m] = wetter.sunset!.split(':').map(Number)
              return now.getHours() * 60 + now.getMinutes() >= h * 60 + m
            })() : false
            if (nachSU) return null
            return diff
          })() : null
          const prozentUeber = verbleibenKwh != null && verbleibenKwh < 0 && wetter?.pv_prognose_kwh
            ? Math.round(Math.abs(verbleibenKwh) / wetter.pv_prognose_kwh * 100)
            : null
          return (
            <div key={tag.datum}>
            <div className={`grid grid-cols-[auto_1fr_7rem] items-center gap-x-2 rounded-lg px-3 py-2 ${
              i === 0 ? 'bg-yellow-50 dark:bg-yellow-900/20' :
              'bg-amber-50/60 dark:bg-amber-900/10'
            }`}>
              <span className={`shrink-0 ${isProminent ? 'text-sm font-medium text-gray-600 dark:text-gray-300' : 'text-xs text-gray-400 dark:text-gray-500'}`}>{label}</span>
              <div className="flex flex-col items-end">
                <span className={`font-bold text-yellow-600 dark:text-yellow-400 ${isProminent ? 'text-base' : 'text-xs'}`}>
                  {fmtZahl(i === 0 && wetter?.pv_prognose_kwh != null ? wetter.pv_prognose_kwh : tag.pv_ertrag_kwh, 1)}
                  <span className="text-xs font-normal ml-0.5">kWh</span>
                </span>
                {verbleibenKwh != null && (
                  <span className={`text-[10px] ${verbleibenKwh > 0 ? 'text-lime-600 dark:text-lime-400' : 'text-emerald-600 dark:text-emerald-400'}`}
                        title={verbleibenKwh > 0
                          ? `Noch ~${fmtZahl(verbleibenKwh, 1)} kWh ausstehend`
                          : `Prognose um ${fmtZahl(Math.abs(verbleibenKwh), 1)} kWh übertroffen`}>
                    {verbleibenKwh > 0 ? `~${fmtZahl(verbleibenKwh, 1)} verbl.` : `+${fmtZahl(Math.abs(verbleibenKwh), 1)} kWh über Progn.${prozentUeber != null ? ` (+${prozentUeber} %)` : ''}`}
                  </span>
                )}
              </div>
              <span className="text-right text-xs w-28">
                {hasVmNm ? (
                  <>
                    <span className="font-semibold text-amber-500">{fmtZahl(tag.pv_ertrag_morgens_kwh!, 1)}</span>
                    <span className="text-gray-400 dark:text-gray-500 mx-0.5">/</span>
                    <span className="font-semibold text-yellow-500">{fmtZahl(tag.pv_ertrag_nachmittags_kwh ?? 0, 1)}</span>
                  </>
                ) : null}
              </span>
            </div>
            {/* Verbrauchsprognose im Stil der Prognose-Zeilen — nur unter Heute */}
            {verbrPrognKwh != null && (
              <div className="grid grid-cols-[auto_1fr_7rem] items-center gap-x-2 rounded-lg px-3 py-1 bg-gray-50 dark:bg-gray-700/50">
                <span className="text-xs text-gray-400 dark:text-gray-300 flex items-center gap-1">
                  Verbrauchsprognose
                  {wetter?.profil_typ?.startsWith('individuell') && (
                    <span className="text-[9px] text-emerald-500">(ind.)</span>
                  )}
                  <SimpleTooltip text={verbrTooltip}><Info className="w-3 h-3 opacity-40 cursor-help" /></SimpleTooltip>
                </span>
                <div className="flex flex-col items-end">
                  <span className="text-xs font-bold text-orange-500 dark:text-orange-400">
                    ~{fmtZahl(verbrPrognKwh, 1)}<span className="text-xs font-normal ml-0.5">kWh</span>
                  </span>
                </div>
                <span className="w-28" />
              </div>
            )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
