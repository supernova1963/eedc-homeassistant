/**
 * Hero-Leiste: Top-3 KPIs mit Vorjahresvergleich
 */

import { TrendingUp, TrendingDown, Minus } from 'lucide-react'
import { FormelTooltip, fmtCalc } from '../../components/ui'
import type { CockpitUebersicht } from '../../api/cockpit'

export default function HeroLeiste({ data, prevData, year }: {
  data: CockpitUebersicht
  prevData: CockpitUebersicht | null
  year?: number
}) {
  const trend = (curr: number, prev?: number) => {
    if (!prev || prev === 0) return null
    return ((curr - prev) / prev) * 100
  }

  const items = [
    {
      label: 'Autarkie',
      value: `${data.autarkie_prozent.toFixed(1)} %`,
      delta: trend(data.autarkie_prozent, prevData?.autarkie_prozent),
      color: 'text-blue-600 dark:text-blue-400',
      bg: 'bg-blue-50 dark:bg-blue-900/20',
      formel: '1 − Netzbezug ÷ Gesamtverbrauch',
      berechnung: data.gesamtverbrauch_kwh
        ? `1 − ${fmtCalc(data.netzbezug_kwh, 0)} ÷ ${fmtCalc(data.gesamtverbrauch_kwh, 0)} kWh`
        : undefined,
    },
    {
      label: 'Spez. Ertrag',
      value: data.spezifischer_ertrag_kwh_kwp
        ? `${data.spezifischer_ertrag_kwh_kwp.toFixed(0)} kWh/kWp`
        : '---',
      delta: trend(data.spezifischer_ertrag_kwh_kwp || 0, prevData?.spezifischer_ertrag_kwh_kwp ?? undefined),
      color: 'text-yellow-600 dark:text-yellow-400',
      bg: 'bg-yellow-50 dark:bg-yellow-900/20',
      formel: 'PV-Erzeugung ÷ Anlagenleistung',
      berechnung: data.pv_erzeugung_kwh && data.anlagenleistung_kwp
        ? `${fmtCalc(data.pv_erzeugung_kwh, 0)} kWh ÷ ${fmtCalc(data.anlagenleistung_kwp, 1)} kWp`
        : undefined,
    },
    {
      label: 'Netto-Ertrag',
      value: `${data.netto_ertrag_euro.toFixed(0)} €`,
      delta: trend(data.netto_ertrag_euro, prevData?.netto_ertrag_euro),
      color: 'text-emerald-600 dark:text-emerald-400',
      bg: 'bg-emerald-50 dark:bg-emerald-900/20',
      formel: 'Einsparung + Einspeisevergütung − Fixkosten',
    },
  ]

  return (
    <div className="grid grid-cols-3 gap-3">
      {items.map(item => (
        <div key={item.label} className={`rounded-xl p-4 ${item.bg}`}>
          <p className="text-xs text-gray-500 dark:text-gray-400 mb-1">{item.label}</p>
          <p className={`text-2xl font-bold ${item.color}`}>
            <FormelTooltip formel={item.formel} berechnung={item.berechnung}>
              {item.value}
            </FormelTooltip>
          </p>
          {item.delta !== null && year && (
            <div className={`flex items-center gap-1 mt-1 text-xs font-medium ${
              item.delta >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-500 dark:text-red-400'
            }`}>
              {item.delta > 0.5
                ? <TrendingUp className="h-3 w-3" />
                : item.delta < -0.5
                  ? <TrendingDown className="h-3 w-3" />
                  : <Minus className="h-3 w-3" />
              }
              {item.delta > 0 ? '+' : ''}{item.delta.toFixed(1)} % vs. {year - 1}
            </div>
          )}
        </div>
      ))}
    </div>
  )
}
