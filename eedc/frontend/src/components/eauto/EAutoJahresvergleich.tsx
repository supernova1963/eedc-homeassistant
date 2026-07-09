/**
 * EAutoJahresvergleich — Block ⑤ „Vergleich" des E-Auto-Typs (IA-v4-Hub).
 *
 * Pro Jahr EINE gestapelte Säule: Ladung nach Quelle (PV / Netz / Extern) →
 * zeigt, wie sich der **PV-Anteil der Ladung über die Jahre** entwickelt.
 * %-Anteile am Jahres-Ladungsvolumen im Tooltip + aufklappbare Werte-Tabelle.
 * (Das IST-Dashboard hat keinen Jahresvergleich — Hub-Mehrwert ohne IST-Verlust.)
 */
import { useEffect } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from 'recharts'
import { LADEQUELLEN_FARBEN, xAchse, achsenEinheit, achsenTick, ACHSEN_MARGIN_TOP, fmtZahl } from '../../lib'
import { ChartLegende, eedcTooltipProps } from '../ui'
import ScrollSchatten from '../ui/ScrollSchatten'
import { Parkbar } from '../park'
import type { InvestitionMonatsdaten } from '../../api/investitionen'

const KEINE_IDS: string[] = []
const JAHRES_IDS = ['info:eauto-jahres', 'chart:eauto-jahresvergleich', 'tabelle:eauto-jahre']

interface JahrLadung { jahr: number; pv: number; netz: number; extern: number; gesamt: number }

const SERIEN = [
  { key: 'pv', name: 'Heim: PV', farbe: LADEQUELLEN_FARBEN.pv },
  { key: 'netz', name: 'Heim: Netz', farbe: LADEQUELLEN_FARBEN.netz },
  { key: 'extern', name: 'Extern', farbe: LADEQUELLEN_FARBEN.extern },
] as const

export function prepEAutoJahresLadung(monatsdaten: InvestitionMonatsdaten[]): JahrLadung[] {
  const m = new Map<number, JahrLadung>()
  for (const md of monatsdaten) {
    const y = m.get(md.jahr) ?? { jahr: md.jahr, pv: 0, netz: 0, extern: 0, gesamt: 0 }
    const pv = md.verbrauch_daten.ladung_pv_kwh || 0
    const netz = md.verbrauch_daten.ladung_netz_kwh || 0
    const extern = md.verbrauch_daten.ladung_extern_kwh || 0
    y.pv += pv; y.netz += netz; y.extern += extern; y.gesamt += pv + netz + extern
    m.set(md.jahr, y)
  }
  return [...m.values()].sort((a, b) => a.jahr - b.jahr)
}

const fmt = (v: number) => Math.round(v).toLocaleString('de-DE')
const pct = (v: number, ganz: number) => (ganz > 0 ? `${fmtZahl((v / ganz) * 100, 0)} %` : '—')

export function EAutoJahresvergleich({ monatsdaten, embed = false, melde }: { monatsdaten: InvestitionMonatsdaten[]; embed?: boolean; melde?: (ids: string[]) => void }) {
  const daten = prepEAutoJahresLadung(monatsdaten)
  const leer = daten.length === 0
  useEffect(() => { melde?.(leer ? KEINE_IDS : JAHRES_IDS) }, [melde, leer])
  if (leer) return <p className="text-sm text-gray-500 dark:text-gray-400">Keine Jahresdaten erfasst.</p>
  const hatExtern = daten.some((d) => d.extern > 0)
  const serien = SERIEN.filter((s) => s.key !== 'extern' || hatExtern)

  return (
    <div className={embed ? 'space-y-4' : 'space-y-6'}>
      <Parkbar id="info:eauto-jahres" titel="Jahresvergleich-Erklärung">
      <p className="text-sm text-gray-500 dark:text-gray-400">
        Ladung je Jahr nach Quelle — zeigt die Entwicklung des <span className="font-medium">PV-Anteils</span>.
      </p>
      </Parkbar>
      <Parkbar id="chart:eauto-jahresvergleich" titel="Ladung nach Quelle pro Jahr">
      <div className="h-72">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={daten} margin={{ top: ACHSEN_MARGIN_TOP, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="jahr" {...xAchse()} /* achsen-allow: Zeit-/Kategorie-Achse (Jahr) */ />
            <YAxis tick={{ fontSize: 10 }} width={56} tickFormatter={achsenTick} label={achsenEinheit('kWh')} />
            <Tooltip {...eedcTooltipProps({ unit: ' kWh', decimals: 0, percentOf: 'gesamt' })} />
            <Legend wrapperStyle={{ fontSize: 11 }} content={<ChartLegende />} />
            {serien.map((s) => (
              <Bar key={s.key} dataKey={s.key} name={s.name} stackId="lad" fill={s.farbe} />
            ))}
          </BarChart>
        </ResponsiveContainer>
      </div>
      </Parkbar>

      <Parkbar id="tabelle:eauto-jahre" titel="Jahres-Tabelle">
      <details className="border-t border-gray-100 dark:border-gray-800 pt-3">
        <summary className="cursor-pointer text-sm text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white">
          Werte anzeigen ({daten.length} Jahre)
        </summary>
        <ScrollSchatten achse="horizontal" aussenClassName="mt-3" fadeFrom="from-white dark:from-gray-800">
          <table className="min-w-full text-sm">
            <thead>
              <tr className="border-b border-gray-200 dark:border-gray-700 text-gray-500 dark:text-gray-400">
                {/* B2/C3 (#237): Einheit im Header — Zellen tragen nur Zahl + %-Anteil. */}
                <th className="text-left py-2 px-2 font-medium">Jahr</th>
                <th className="text-right py-2 px-2 font-medium">PV (kWh)</th>
                <th className="text-right py-2 px-2 font-medium">Netz (kWh)</th>
                {hatExtern && <th className="text-right py-2 px-2 font-medium">Extern (kWh)</th>}
              </tr>
            </thead>
            <tbody>
              {[...daten].reverse().map((d) => (
                <tr key={d.jahr} className="border-b border-gray-100 dark:border-gray-800">
                  <td className="py-1.5 px-2 text-gray-700 dark:text-gray-300">{d.jahr}</td>
                  <td className="text-right py-1.5 px-2 tabular-nums text-gray-900 dark:text-white">{fmt(d.pv)} <span className="text-gray-400 dark:text-gray-500">({pct(d.pv, d.gesamt)})</span></td>
                  <td className="text-right py-1.5 px-2 tabular-nums text-gray-900 dark:text-white">{fmt(d.netz)} <span className="text-gray-400 dark:text-gray-500">({pct(d.netz, d.gesamt)})</span></td>
                  {hatExtern && <td className="text-right py-1.5 px-2 tabular-nums text-gray-900 dark:text-white">{fmt(d.extern)} <span className="text-gray-400 dark:text-gray-500">({pct(d.extern, d.gesamt)})</span></td>}
                </tr>
              ))}
            </tbody>
          </table>
        </ScrollSchatten>
      </details>
      </Parkbar>
    </div>
  )
}
