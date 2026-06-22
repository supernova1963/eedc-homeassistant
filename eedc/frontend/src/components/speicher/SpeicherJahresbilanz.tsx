/**
 * SpeicherJahresbilanz — Block ⑤ „Vergleich" des Speicher-Typs (IA-v4-Hub).
 *
 * Pro Jahr ZWEI gestapelte Säulen nebeneinander als echte Energiebilanz:
 *   Säule 1 „Ladung" = PV-Ladung + Netz-Ladung (Arbitrage, wenn vorhanden)
 *   Säule 2 „Entladung" = Entladung + Verlust
 * Beide Säulen sind gleich hoch (Ladung = Entladung + Verlust) → der Vergleich
 * zeigt Herkunft ⟷ Verwendung + Speicherverlust je Jahr. %-Anteile am
 * Jahres-Ladungsvolumen im Tooltip (und in der aufklappbaren Tabelle).
 */
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from 'recharts'
import { CHART_COLORS, COLORS, SERIE_NEUTRAL } from '../../lib'
import type { InvestitionMonatsdaten } from '../../api/investitionen'

interface JahrBilanz {
  jahr: number
  pvLadung: number
  netzLadung: number
  entladung: number
  verlust: number
  ladungGesamt: number
}

const SERIEN = [
  { key: 'pvLadung', name: 'PV-Ladung', stapel: 'lad', farbe: CHART_COLORS.speicherLadung },
  { key: 'netzLadung', name: 'Netz-Ladung', stapel: 'lad', farbe: COLORS.grid },
  { key: 'entladung', name: 'Entladung', stapel: 'ent', farbe: CHART_COLORS.speicherEntladung },
  { key: 'verlust', name: 'Verlust', stapel: 'ent', farbe: SERIE_NEUTRAL },
] as const

/** Jahresbilanz aus den Monatsdaten (PV/Netz-Ladung, Entladung, Verlust). */
export function prepSpeicherJahresbilanz(monatsdaten: InvestitionMonatsdaten[]): JahrBilanz[] {
  const m = new Map<number, JahrBilanz>()
  for (const md of monatsdaten) {
    const ladung = md.verbrauch_daten.ladung_kwh || 0
    const entladung = md.verbrauch_daten.entladung_kwh || 0
    const netz = md.verbrauch_daten.speicher_ladung_netz_kwh || 0
    const y = m.get(md.jahr) ?? { jahr: md.jahr, pvLadung: 0, netzLadung: 0, entladung: 0, verlust: 0, ladungGesamt: 0 }
    y.pvLadung += Math.max(0, ladung - netz)
    y.netzLadung += netz
    y.entladung += entladung
    y.ladungGesamt += ladung
    m.set(md.jahr, y)
  }
  for (const y of m.values()) y.verlust = Math.max(0, y.ladungGesamt - y.entladung)
  return [...m.values()].sort((a, b) => a.jahr - b.jahr)
}

const fmt = (v: number) => Math.round(v).toLocaleString('de-DE')
const pct = (v: number, ganz: number) => (ganz > 0 ? `${Math.round((v / ganz) * 100)} %` : '—')

interface TooltipPayload { dataKey: string; value: number; name: string; color: string; payload: JahrBilanz }

function BilanzTooltip({ active, payload, label }: { active?: boolean; payload?: TooltipPayload[]; label?: string | number }) {
  if (!active || !payload?.length) return null
  const ganz = payload[0].payload.ladungGesamt
  return (
    <div className="rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 px-3 py-2 shadow-lg text-xs">
      <div className="font-semibold text-gray-900 dark:text-white mb-1">{label}</div>
      {payload.map((p) => (
        <div key={p.dataKey} className="flex items-center justify-between gap-3">
          <span className="flex items-center gap-1.5 text-gray-600 dark:text-gray-300">
            <span className="inline-block w-2 h-2 rounded-sm" style={{ backgroundColor: p.color }} />
            {p.name}
          </span>
          <span className="font-medium text-gray-900 dark:text-white tabular-nums">
            {fmt(p.value)} kWh <span className="text-gray-400 dark:text-gray-500">({pct(p.value, ganz)})</span>
          </span>
        </div>
      ))}
    </div>
  )
}

export function SpeicherJahresbilanz({ monatsdaten, embed = false }: { monatsdaten: InvestitionMonatsdaten[]; embed?: boolean }) {
  const daten = prepSpeicherJahresbilanz(monatsdaten)
  if (daten.length === 0) {
    return <p className="text-sm text-gray-500 dark:text-gray-400">Keine Jahresdaten erfasst.</p>
  }
  const hatNetz = daten.some((d) => d.netzLadung > 0)
  const serien = SERIEN.filter((s) => s.key !== 'netzLadung' || hatNetz)

  return (
    <div className={embed ? 'space-y-4' : 'space-y-6'}>
      <p className="text-sm text-gray-500 dark:text-gray-400">
        Je Jahr links die <span className="font-medium">Ladung</span> nach Herkunft, rechts
        <span className="font-medium"> Entladung + Verlust</span> — beide Säulen gleich hoch (Ladung = Entladung + Verlust).
      </p>
      <div className="h-72">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={daten} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="jahr" fontSize={11} />
            <YAxis fontSize={10} width={56} unit=" kWh" />
            <Tooltip content={<BilanzTooltip />} />
            <Legend wrapperStyle={{ fontSize: 11 }} />
            {serien.map((s) => (
              <Bar key={s.key} dataKey={s.key} name={s.name} stackId={s.stapel} fill={s.farbe} />
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
                <th className="text-right py-2 px-2 font-medium">PV-Ladung</th>
                {hatNetz && <th className="text-right py-2 px-2 font-medium">Netz-Ladung</th>}
                <th className="text-right py-2 px-2 font-medium">Entladung</th>
                <th className="text-right py-2 px-2 font-medium">Verlust</th>
              </tr>
            </thead>
            <tbody>
              {[...daten].reverse().map((d) => (
                <tr key={d.jahr} className="border-b border-gray-100 dark:border-gray-800">
                  <td className="py-1.5 px-2 text-gray-700 dark:text-gray-300">{d.jahr}</td>
                  <td className="text-right py-1.5 px-2 tabular-nums text-gray-900 dark:text-white">{fmt(d.pvLadung)} <span className="text-gray-400 dark:text-gray-500">({pct(d.pvLadung, d.ladungGesamt)})</span></td>
                  {hatNetz && <td className="text-right py-1.5 px-2 tabular-nums text-gray-900 dark:text-white">{fmt(d.netzLadung)} <span className="text-gray-400 dark:text-gray-500">({pct(d.netzLadung, d.ladungGesamt)})</span></td>}
                  <td className="text-right py-1.5 px-2 tabular-nums text-gray-900 dark:text-white">{fmt(d.entladung)} <span className="text-gray-400 dark:text-gray-500">({pct(d.entladung, d.ladungGesamt)})</span></td>
                  <td className="text-right py-1.5 px-2 tabular-nums text-gray-900 dark:text-white">{fmt(d.verlust)} <span className="text-gray-400 dark:text-gray-500">({pct(d.verlust, d.ladungGesamt)})</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </div>
  )
}
