/**
 * Community-PV-Ertrag — geteilte Teile (Daten-Hook + Präsentations-Sektionen).
 * EINE Code-Wahrheit für IST (`PVErtragTab`) und IA-V4 (`CommunityPVErtragV4`).
 * Sektionen rendern Inhalt OHNE äußere Card/Block-Hülle (Aufrufer wickelt).
 * Zahlen de-DE (`fmtZahl`), Farben/Achsen aus der Zentrale.
 */
import { useEffect, useMemo, useState } from 'react'
import { Sun, TrendingUp, TrendingDown, Calendar, Target, Award } from 'lucide-react'
import { KPICard } from '../../components/ui'
import { Parkbar } from '../../components/park'
import ChartTooltip from '../../components/ui/ChartTooltip'
import { useChartTheme } from '../../context/ThemeContext'
import { communityApi } from '../../api'
import type { CommunityBenchmarkResponse, Verteilung, MonatlicheDurchschnitte } from '../../api/community'
import {
  Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell, ComposedChart, Line,
} from 'recharts'
import {
  MONAT_KURZ, STATUS_COLORS, EIGENE_SERIE_FARBEN, SERIE_NEUTRAL, ACHSEN_TICK,
  ACHSEN_MARGIN_TOP, achsenEinheit, achsenTick, fmtZahl,
} from '../../lib'

// Element-Park (IA-V4, Element-Park-Doktrin Gernot 2026-06-27): JEDE Anzeige
// (KPI, Chart, Beschriftung/Legende, Tabelle, Hinweis) ist einzeln parkbar.
// `Parkbar` ist OHNE ParkProvider inert → der IST-`PVErtragTab` (v3, kein Provider)
// bleibt optisch identisch; nur die V4-Sicht aktiviert die Geste. IDs view-eindeutig
// (persistKey 'v4-community-pv-ertrag'); der V4-Builder blendet einen Block aus, wenn
// ALLE seine Element-IDs geparkt sind (alleGeparkt).
export const PV_PARK_IDS = {
  kennzahlen: ['pv-kennzahlen-position', 'pv-kennzahlen-vs-community', 'pv-kennzahlen-vs-region'],
  monatsertrag: ['pv-monatsertrag-chart', 'pv-monatsertrag-legende'],
  jahresuebersicht: ['pv-jahresuebersicht-tabelle'],
  verteilung: ['pv-verteilung-chart', 'pv-verteilung-statistik', 'pv-verteilung-legende'],
  hinweis: ['pv-hinweis'],
} as const

export interface PVErtragDaten {
  distribution: Verteilung | null
  chartData: { name: string; ertrag: number; durchschnitt: number; isPositive: boolean }[]
  jahresStats: { jahr: number; spezErtrag: number; anzahlMonate: number; vollstaendig: boolean }[] | null
  perzentil: number | null
  performanceStats: { abweichungGesamt: number; abweichungRegion: number; differenzAbsolut: number } | null
  extraLoading: boolean
}

// ─── Daten-Hook (lädt Verteilung + Monats-Ø; leitet Chart/Jahres-Aggregate ab) ──

export function usePVErtragDaten(benchmark: CommunityBenchmarkResponse | null): PVErtragDaten {
  const [distribution, setDistribution] = useState<Verteilung | null>(null)
  const [monthlyAverages, setMonthlyAverages] = useState<MonatlicheDurchschnitte | null>(null)
  const [extraLoading, setExtraLoading] = useState(false)

  useEffect(() => {
    let ab = false
    setExtraLoading(true)
    Promise.all([
      communityApi.getDistribution('spez_ertrag', 15).catch(() => null),
      communityApi.getMonthlyAverages(24).catch(() => null),
    ])
      .then(([dist, monthly]) => { if (!ab) { setDistribution(dist); setMonthlyAverages(monthly) } })
      .finally(() => { if (!ab) setExtraLoading(false) })
    return () => { ab = true }
  }, [])

  const chartData = useMemo(() => {
    if (!benchmark?.anlage.monatswerte) return []
    const monatsnamen = MONAT_KURZ.slice(1)
    const avgMap = new Map<string, number>()
    monthlyAverages?.monate?.forEach((m) => avgMap.set(`${m.jahr}-${m.monat}`, m.spez_ertrag_avg))
    return [...benchmark.anlage.monatswerte]
      .sort((a, b) => a.jahr - b.jahr || a.monat - b.monat)
      .slice(-12)
      .map((m) => {
        const spezErtrag = m.spez_ertrag_kwh_kwp || 0
        let durchschnitt = avgMap.get(`${m.jahr}-${m.monat}`) ?? avgMap.get(`${m.jahr - 1}-${m.monat}`)
        if (durchschnitt === undefined) durchschnitt = benchmark.benchmark.spez_ertrag_durchschnitt / 12
        const abweichung = durchschnitt > 0 ? ((spezErtrag - durchschnitt) / durchschnitt) * 100 : 0
        return { name: `${monatsnamen[m.monat - 1]} ${String(m.jahr).slice(2)}`, ertrag: spezErtrag, durchschnitt, isPositive: abweichung >= 0 }
      })
  }, [benchmark, monthlyAverages])

  const jahresStats = useMemo(() => {
    if (!benchmark?.anlage.monatswerte) return null
    const mw = benchmark.anlage.monatswerte
    return [...new Set(mw.map((m) => m.jahr))].sort((a, b) => b - a).map((jahr) => {
      const jd = mw.filter((m) => m.jahr === jahr)
      const summe = jd.reduce((s, m) => s + (m.spez_ertrag_kwh_kwp || 0), 0)
      return { jahr, spezErtrag: summe, anzahlMonate: jd.length, vollstaendig: jd.length === 12 }
    })
  }, [benchmark])

  const perzentil = useMemo(() => {
    if (!benchmark) return null
    const { rang_gesamt, anzahl_anlagen_gesamt } = benchmark.benchmark
    return Math.round((1 - rang_gesamt / anzahl_anlagen_gesamt) * 100)
  }, [benchmark])

  const performanceStats = useMemo(() => {
    if (!benchmark) return null
    const { spez_ertrag_anlage, spez_ertrag_durchschnitt, spez_ertrag_region } = benchmark.benchmark
    return {
      abweichungGesamt: ((spez_ertrag_anlage - spez_ertrag_durchschnitt) / spez_ertrag_durchschnitt) * 100,
      abweichungRegion: ((spez_ertrag_anlage - spez_ertrag_region) / spez_ertrag_region) * 100,
      differenzAbsolut: spez_ertrag_anlage - spez_ertrag_durchschnitt,
    }
  }, [benchmark])

  return { distribution, chartData, jahresStats, perzentil, performanceStats, extraLoading }
}

// ─── Sektion: KPI-Strip (Position · vs. Community · vs. Region) ────────────────

export function PvKpiStrip({ perzentil, performanceStats }: Pick<PVErtragDaten, 'perzentil' | 'performanceStats'>) {
  const ag = performanceStats?.abweichungGesamt ?? 0
  const ar = performanceStats?.abweichungRegion ?? 0
  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
      <Parkbar id="pv-kennzahlen-position" titel="Deine Position">
        <KPICard title="Deine Position" value={`Top ${fmtZahl(100 - (perzentil || 0), 0)} %`} subtitle={`Besser als ${fmtZahl(perzentil, 0)} % der Community`} color="blue" icon={Award} />
      </Parkbar>
      <Parkbar id="pv-kennzahlen-vs-community" titel="vs. Community">
        <KPICard title="vs. Community" value={`${ag >= 0 ? '+' : ''}${fmtZahl(ag, 1)}`} unit="%" subtitle={`${fmtZahl(performanceStats?.differenzAbsolut, 0)} kWh/kWp Differenz`} color={ag >= 0 ? 'green' : 'red'} icon={ag >= 0 ? TrendingUp : TrendingDown} />
      </Parkbar>
      <Parkbar id="pv-kennzahlen-vs-region" titel="vs. Region">
        <KPICard title="vs. Region" value={`${ar >= 0 ? '+' : ''}${fmtZahl(ar, 1)}`} unit="%" subtitle="Vergleich mit deinem Bundesland" color={ar >= 0 ? 'green' : 'red'} icon={Target} />
      </Parkbar>
    </div>
  )
}

// ─── Sektion: Monatlicher Ertrag vs. Community ────────────────────────────────

export function MonatsErtragChart({ benchmark, chartData }: { benchmark: CommunityBenchmarkResponse; chartData: PVErtragDaten['chartData'] }) {
  const achsen = useChartTheme()
  return (
    <div>
      <Parkbar id="pv-monatsertrag-chart" titel="Monatlicher Ertrag (Diagramm)">
        <div className="flex items-center justify-end mb-2">
          <span className="text-sm text-gray-500 dark:text-gray-400">{benchmark.zeitraum_label}</span>
        </div>
        <div className="h-72">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={chartData} margin={{ top: ACHSEN_MARGIN_TOP }}>
              <CartesianGrid strokeDasharray="3 3" stroke={achsen.grid} />
              <XAxis dataKey="name" tick={ACHSEN_TICK} interval={0} angle={-45} textAnchor="end" height={60} /* achsen-allow: Zeit-/Kategorie-Achse (Monat) */ />
              <YAxis tick={ACHSEN_TICK} tickFormatter={achsenTick} label={achsenEinheit('kWh/kWp')} />
              <Tooltip content={<ChartTooltip formatter={(value: number, name: string) => (name === 'ertrag' || name === 'durchschnitt' ? `${fmtZahl(value, 1)} kWh/kWp` : String(value))} />} />
              <Line type="monotone" dataKey="durchschnitt" stroke={achsen.referenz} strokeWidth={2} strokeDasharray="5 5" dot={false} name="durchschnitt" />
              <Bar dataKey="ertrag" radius={[2, 2, 0, 0]} name="ertrag">
                {chartData.map((entry, index) => <Cell key={`cell-${index}`} fill={entry.isPositive ? STATUS_COLORS.ok : STATUS_COLORS.kritisch} fillOpacity={0.8} />)}
              </Bar>
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      </Parkbar>
      <Parkbar id="pv-monatsertrag-legende" titel="Monatlicher Ertrag (Legende)">
      <div className="flex flex-wrap items-center justify-center gap-x-6 gap-y-2 mt-4 text-sm">
        <span className="flex items-center gap-2"><span className="w-4 h-3 rounded" style={{ backgroundColor: STATUS_COLORS.ok }} /><span className="text-gray-600 dark:text-gray-400">Über Monats-Ø</span></span>
        <span className="flex items-center gap-2"><span className="w-4 h-3 rounded" style={{ backgroundColor: STATUS_COLORS.kritisch }} /><span className="text-gray-600 dark:text-gray-400">Unter Monats-Ø</span></span>
        <span className="flex items-center gap-2"><span className="w-6 h-0 border-t-2 border-dashed border-gray-400" /><span className="text-gray-600 dark:text-gray-400">Community Monats-Ø</span></span>
      </div>
      </Parkbar>
    </div>
  )
}

// ─── Sektion: Jahresübersicht (Tabelle) ──────────────────────────────────────

export function JahresUebersicht({ benchmark, jahresStats }: { benchmark: CommunityBenchmarkResponse; jahresStats: NonNullable<PVErtragDaten['jahresStats']> }) {
  return (
    <Parkbar id="pv-jahresuebersicht-tabelle" titel="Jahresübersicht">
    <div className="overflow-x-auto">
      <table className="w-full">
        <thead>
          <tr className="border-b border-gray-200 dark:border-gray-700">
            <th className="text-left py-3 px-4 text-sm font-medium text-gray-500 dark:text-gray-400">Jahr</th>
            <th className="text-right py-3 px-4 text-sm font-medium text-gray-500 dark:text-gray-400">Spez. Ertrag</th>
            <th className="text-right py-3 px-4 text-sm font-medium text-gray-500 dark:text-gray-400">vs. Community</th>
            <th className="text-right py-3 px-4 text-sm font-medium text-gray-500 dark:text-gray-400">Monate</th>
          </tr>
        </thead>
        <tbody>
          {jahresStats.map((js) => {
            const abweichung = ((js.spezErtrag - benchmark.benchmark.spez_ertrag_durchschnitt) / benchmark.benchmark.spez_ertrag_durchschnitt) * 100
            const isPositive = abweichung >= 0
            return (
              <tr key={js.jahr} className="border-b border-gray-100 dark:border-gray-800 last:border-0">
                <td className="py-3 px-4">
                  <span className="font-medium text-gray-900 dark:text-white">{js.jahr}</span>
                  {!js.vollstaendig && <span className="ml-2 text-xs text-gray-400 dark:text-gray-500">(unvollständig)</span>}
                </td>
                <td className="text-right py-3 px-4"><span className="font-semibold text-gray-900 dark:text-white">{fmtZahl(js.spezErtrag, 0)} kWh/kWp</span></td>
                <td className="text-right py-3 px-4"><span className={`font-medium ${isPositive ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}`}>{isPositive ? '+' : ''}{fmtZahl(abweichung, 1)} %</span></td>
                <td className="text-right py-3 px-4 text-gray-500 dark:text-gray-400">{fmtZahl(js.anzahlMonate, 0)}/12</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
    </Parkbar>
  )
}

// ─── Sektion: Verteilungs-Histogramm ─────────────────────────────────────────

export function VerteilungHistogramm({ benchmark, distribution }: { benchmark: CommunityBenchmarkResponse; distribution: Verteilung }) {
  const achsen = useChartTheme()
  const eigen = benchmark.benchmark.spez_ertrag_anlage
  return (
    <div>
      <Parkbar id="pv-verteilung-chart" titel="Verteilung (Diagramm)">
      <div className="h-64">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={distribution.bins.map((bin) => ({ range: `${fmtZahl(bin.von, 0)}–${fmtZahl(bin.bis, 0)}`, anzahl: bin.anzahl }))} margin={{ top: ACHSEN_MARGIN_TOP }}>
            <CartesianGrid strokeDasharray="3 3" stroke={achsen.grid} />
            <XAxis dataKey="range" tick={ACHSEN_TICK} angle={-45} textAnchor="end" height={60} /* achsen-allow: Kategorie-Achse (Ertragsklassen kWh/kWp) */ />
            <YAxis tick={ACHSEN_TICK} tickFormatter={achsenTick} label={achsenEinheit('Anlagen')} />
            <Tooltip content={<ChartTooltip formatter={(value: number) => `${fmtZahl(value, 0)} Anlagen`} labelFormatter={(label) => `${label} kWh/kWp`} />} />
            <Bar dataKey="anzahl" radius={[2, 2, 0, 0]}>
              {distribution.bins.map((bin, index) => {
                const isOwn = eigen >= bin.von && eigen < bin.bis
                return <Cell key={`cell-${index}`} fill={isOwn ? EIGENE_SERIE_FARBEN.du : SERIE_NEUTRAL} fillOpacity={isOwn ? 1 : 0.7} />
              })}
            </Bar>
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      </Parkbar>
      <Parkbar id="pv-verteilung-statistik" titel="Verteilung (Kennzahlen)">
      <div className="mt-4 grid grid-cols-2 md:grid-cols-4 gap-3 sm:gap-4 text-sm">
        {([['Minimum', distribution.statistik.min], ['Durchschnitt', distribution.statistik.durchschnitt], ['Median', distribution.statistik.median], ['Maximum', distribution.statistik.max]] as const).map(([label, wert]) => (
          <div key={label} className="text-center">
            <p className="text-gray-500 dark:text-gray-400">{label}</p>
            <p className="font-semibold text-gray-900 dark:text-white">{fmtZahl(wert, 0)} kWh/kWp</p>
          </div>
        ))}
      </div>
      </Parkbar>
      <Parkbar id="pv-verteilung-legende" titel="Verteilung (Legende)">
      <div className="flex items-center justify-center gap-4 mt-3 text-sm">
        <span className="flex items-center gap-2"><span className="w-4 h-3 rounded" style={{ backgroundColor: EIGENE_SERIE_FARBEN.du }} /><span className="text-gray-600 dark:text-gray-400">Deine Position</span></span>
      </div>
      </Parkbar>
    </div>
  )
}

// ─── Sektion: Vergleich-Hinweis ──────────────────────────────────────────────

export function VergleichHinweis({ benchmark, performanceStats }: { benchmark: CommunityBenchmarkResponse; performanceStats: PVErtragDaten['performanceStats'] }) {
  return (
    <Parkbar id="pv-hinweis" titel="Über den Vergleich">
    <div className="flex items-start gap-3">
      <Sun className="h-5 w-5 text-primary-500 mt-0.5 flex-shrink-0" />
      <p className="text-sm text-gray-600 dark:text-gray-400">
        Der Community-Durchschnitt basiert auf {fmtZahl(benchmark.benchmark.anzahl_anlagen_gesamt, 0)} Anlagen.
        Dein spezifischer Ertrag von <strong>{fmtZahl(benchmark.benchmark.spez_ertrag_anlage, 0)} kWh/kWp</strong> liegt
        {' '}{(performanceStats?.abweichungGesamt || 0) >= 0 ? 'über' : 'unter'} dem Durchschnitt von
        {' '}<strong>{fmtZahl(benchmark.benchmark.spez_ertrag_durchschnitt, 0)} kWh/kWp</strong>.
        Faktoren wie Ausrichtung ({benchmark.anlage.ausrichtung}), Neigung ({fmtZahl(benchmark.anlage.neigung_grad, 0)}°)
        und regionale Sonneneinstrahlung beeinflussen die Ergebnisse.
      </p>
    </div>
    </Parkbar>
  )
}

// Re-Export der Icons für den Komposer (Card-Köpfe).
export { Sun, Calendar, Target }
