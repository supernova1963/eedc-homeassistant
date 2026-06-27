/**
 * BkwJahresvergleich — Block ⑤ „Vergleich" des Balkonkraftwerk-Typs (IA-v4-Hub).
 * Pro Jahr EINE gestapelte Säule: Verwendung der Erzeugung (Eigenverbrauch /
 * Einspeisung) → zeigt die Entwicklung der **Eigenverbrauchsquote** über die
 * Jahre. %-Anteile an der Jahres-Erzeugung im Tooltip + Werte-Tabelle.
 * (Das IST-Dashboard hat keinen Jahresvergleich — Hub-Mehrwert ohne IST-Verlust.)
 */
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from 'recharts'
import { CHART_COLORS } from '../../lib'
import { ChartLegende, eedcTooltipProps } from '../ui'
import type { InvestitionMonatsdaten } from '../../api/investitionen'

interface JahrVerwendung { jahr: number; eigenverbrauch: number; einspeisung: number; gesamt: number }

const SERIEN = [
  { key: 'eigenverbrauch', name: 'Eigenverbrauch', farbe: CHART_COLORS.eigenverbrauch },
  { key: 'einspeisung', name: 'Einspeisung', farbe: CHART_COLORS.einspeisung },
] as const

export function prepBkwJahresVerwendung(monatsdaten: InvestitionMonatsdaten[]): JahrVerwendung[] {
  const m = new Map<number, JahrVerwendung>()
  for (const md of monatsdaten) {
    const y = m.get(md.jahr) ?? { jahr: md.jahr, eigenverbrauch: 0, einspeisung: 0, gesamt: 0 }
    const ev = md.verbrauch_daten.eigenverbrauch_kwh || 0
    const einsp = md.verbrauch_daten.einspeisung_kwh || 0
    y.eigenverbrauch += ev; y.einspeisung += einsp; y.gesamt += ev + einsp
    m.set(md.jahr, y)
  }
  return [...m.values()].sort((a, b) => a.jahr - b.jahr)
}

const fmt = (v: number) => Math.round(v).toLocaleString('de-DE')
const pct = (v: number, ganz: number) => (ganz > 0 ? `${Math.round((v / ganz) * 100)} %` : '—')

export function BkwJahresvergleich({ monatsdaten, embed = false }: { monatsdaten: InvestitionMonatsdaten[]; embed?: boolean }) {
  const daten = prepBkwJahresVerwendung(monatsdaten)
  if (daten.length === 0) return <p className="text-sm text-gray-500 dark:text-gray-400">Keine Jahresdaten erfasst.</p>

  return (
    <div className={embed ? 'space-y-4' : 'space-y-6'}>
      <p className="text-sm text-gray-500 dark:text-gray-400">
        Verwendung der Erzeugung je Jahr — zeigt die Entwicklung der <span className="font-medium">Eigenverbrauchsquote</span>.
      </p>
      <div className="h-72">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={daten} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="jahr" tick={{ fontSize: 10 }} />
            <YAxis tick={{ fontSize: 10 }} width={56} unit=" kWh" />
            <Tooltip {...eedcTooltipProps({ unit: ' kWh', decimals: 0, percentOf: 'gesamt' })} />
            <Legend wrapperStyle={{ fontSize: 11 }} content={<ChartLegende />} />
            {SERIEN.map((s) => (
              <Bar key={s.key} dataKey={s.key} name={s.name} stackId="verw" fill={s.farbe} />
            ))}
          </BarChart>
        </ResponsiveContainer>
      </div>

      <details className="border-t border-gray-100 dark:border-gray-800 pt-3">
        <summary className="cursor-pointer text-sm text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white">
          Werte anzeigen ({daten.length} Jahre)
        </summary>
        <div className="mt-3 overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead>
              <tr className="border-b border-gray-200 dark:border-gray-700 text-gray-500 dark:text-gray-400">
                <th className="text-left py-2 px-2 font-medium">Jahr</th>
                <th className="text-right py-2 px-2 font-medium">Eigenverbrauch</th>
                <th className="text-right py-2 px-2 font-medium">Einspeisung</th>
              </tr>
            </thead>
            <tbody>
              {[...daten].reverse().map((d) => (
                <tr key={d.jahr} className="border-b border-gray-100 dark:border-gray-800">
                  <td className="py-1.5 px-2 text-gray-700 dark:text-gray-300">{d.jahr}</td>
                  <td className="text-right py-1.5 px-2 tabular-nums text-gray-900 dark:text-white">{fmt(d.eigenverbrauch)} <span className="text-gray-400 dark:text-gray-500">({pct(d.eigenverbrauch, d.gesamt)})</span></td>
                  <td className="text-right py-1.5 px-2 tabular-nums text-gray-900 dark:text-white">{fmt(d.einspeisung)} <span className="text-gray-400 dark:text-gray-500">({pct(d.einspeisung, d.gesamt)})</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </div>
  )
}
