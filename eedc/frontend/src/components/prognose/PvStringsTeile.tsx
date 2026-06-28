/**
 * PV-String SOLL/IST — geteilte Element-Bausteine (A.5 Sub 4, Blöcke ②+③).
 *
 * Eine Code-Wahrheit: IST-Tab `pages/auswertung/PVAnlageTab.tsx` UND die v4-Sicht
 * komponieren aus diesen Teilen. Jeder Teil = ein parkbares Element (v4) bzw. direkt
 * gerendert (IST). Energie via `lib/einheiten.ts` (R1/R2: kWh→MWh ab 1.000), Farben
 * aus colors.ts. Block ② = String-Metriken, Block ③ = Mehrjahres-Performance.
 */
import { useState, useEffect, useMemo, useCallback } from 'react'
import {
  BarChart, Bar, LineChart, Line, ComposedChart,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from 'recharts'
import { Sun, TrendingUp, TrendingDown, Download, GitCompare } from 'lucide-react'
import { Card, Button, ChartLegende } from '../ui'
import ChartTooltip from '../ui/ChartTooltip'
import type { KpiStripItem } from '../blocks'
import { exportToCSV } from '../../utils/export'
import { cockpitApi, PVStringsResponse } from '../../api/cockpit'
import {
  SOLL_IST_COLORS, STRING_COLORS, KATEGORIE_FARBEN, PROGNOSE_DASH, HILFSLINIE_DASH,
  formatEnergie, energieAchse, formatProzent, formatSpezErtrag, fmtZahl,
  achsenEinheit, achsenTick, ACHSEN_MARGIN_TOP,
} from '../../lib'

export interface PvStringsVM {
  loading: boolean
  error: string | null
  data: PVStringsResponse | null
  jahresvergleichData: Array<Record<string, number | string>>
}

/** Lädt PV-String-SOLL/IST (Einzeljahr ∨ „alle" aggregiert) + Mehrjahres-Reihe. */
export function usePvStrings(anlageId: number, selectedYear: number | 'all', verfuegbareJahre: number[]): PvStringsVM {
  const [data, setData] = useState<PVStringsResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [multiYearData, setMultiYearData] = useState<Map<number, PVStringsResponse>>(new Map())

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      if (selectedYear === 'all') {
        const dataMap = new Map<number, PVStringsResponse>()
        for (const jahr of verfuegbareJahre) {
          try { dataMap.set(jahr, await cockpitApi.getPVStrings(anlageId, jahr)) } catch { /* Jahr übersprungen */ }
        }
        setMultiYearData(dataMap)
        if (dataMap.size > 0) {
          const firstYearData = dataMap.get(verfuegbareJahre[0])
          if (firstYearData) {
            const aggStrings = firstYearData.strings.map(s => {
              let totalPrognose = 0, totalIst = 0
              dataMap.forEach((yearData) => {
                const sd = yearData.strings.find(ys => ys.investition_id === s.investition_id)
                if (sd) { totalPrognose += sd.prognose_jahr_kwh; totalIst += sd.ist_jahr_kwh }
              })
              const abweichung = totalPrognose > 0 ? ((totalIst - totalPrognose) / totalPrognose) * 100 : null
              return {
                ...s,
                prognose_jahr_kwh: totalPrognose, ist_jahr_kwh: totalIst,
                abweichung_jahr_prozent: abweichung, abweichung_jahr_kwh: totalIst - totalPrognose,
                performance_ratio_jahr: totalPrognose > 0 ? totalIst / totalPrognose : null,
                spezifischer_ertrag_kwh_kwp: s.leistung_kwp > 0 ? totalIst / s.leistung_kwp : null,
                monatswerte: s.monatswerte.map((m, mIdx) => {
                  let mp = 0, mi = 0
                  dataMap.forEach((yearData) => {
                    const sd = yearData.strings.find(ys => ys.investition_id === s.investition_id)
                    if (sd && sd.monatswerte[mIdx]) { mp += sd.monatswerte[mIdx].prognose_kwh; mi += sd.monatswerte[mIdx].ist_kwh }
                  })
                  return { ...m, prognose_kwh: mp, ist_kwh: mi }
                }),
              }
            })
            const totalP = aggStrings.reduce((s, x) => s + x.prognose_jahr_kwh, 0)
            const totalI = aggStrings.reduce((s, x) => s + x.ist_jahr_kwh, 0)
            const sortedByPerf = [...aggStrings].filter(s => s.performance_ratio_jahr !== null)
              .sort((a, b) => (b.performance_ratio_jahr || 0) - (a.performance_ratio_jahr || 0))
            setData({
              ...firstYearData, strings: aggStrings,
              prognose_gesamt_kwh: totalP, ist_gesamt_kwh: totalI, abweichung_gesamt_kwh: totalI - totalP,
              abweichung_gesamt_prozent: totalP > 0 ? ((totalI - totalP) / totalP) * 100 : null,
              bester_string: sortedByPerf[0]?.bezeichnung || null,
              schlechtester_string: sortedByPerf[sortedByPerf.length - 1]?.bezeichnung || null,
            })
          }
        }
      } else {
        setData(await cockpitApi.getPVStrings(anlageId, selectedYear))
      }
    } catch {
      setError('Fehler beim Laden der String-Daten')
    } finally {
      setLoading(false)
    }
  }, [anlageId, selectedYear, verfuegbareJahre])

  useEffect(() => { void load() }, [load])

  const jahresvergleichData = useMemo(() => {
    if (selectedYear !== 'all' || multiYearData.size === 0) return []
    return verfuegbareJahre.map(jahr => {
      const yearData = multiYearData.get(jahr)
      if (!yearData) return null
      const entry: Record<string, number | string> = { name: jahr.toString(), jahr }
      yearData.strings.forEach((s) => {
        entry[s.bezeichnung] = s.performance_ratio_jahr ? Math.round(s.performance_ratio_jahr * 100) : 0
      })
      entry['Gesamt'] = yearData.abweichung_gesamt_prozent ? 100 + yearData.abweichung_gesamt_prozent : 100
      return entry
    }).filter((e): e is Record<string, number | string> => e !== null).reverse()
  }, [selectedYear, multiYearData, verfuegbareJahre])

  return { loading, error, data, jahresvergleichData }
}

export function exportPvStringsCsv(data: PVStringsResponse, selectedYear: number | 'all') {
  const headers = ['String', 'kWp', 'Ausrichtung', 'SOLL (kWh)', 'IST (kWh)', 'Abweichung (%)', 'Performance Ratio', 'kWh/kWp']
  const rows = data.strings.map(s => [
    s.bezeichnung, s.leistung_kwp, s.ausrichtung || '-', s.prognose_jahr_kwh, s.ist_jahr_kwh,
    s.abweichung_jahr_prozent ?? '-',
    s.performance_ratio_jahr ? formatProzent(s.performance_ratio_jahr * 100).text : '-',
    s.spezifischer_ertrag_kwh_kwp ?? '-',
  ])
  exportToCSV(headers, rows, `pv_strings_${selectedYear === 'all' ? 'alle_jahre' : selectedYear}.csv`)
}

/** R2: gemeinsame Energie-Einheit über SOLL/IST-KPIs (größter Wert = Referenz). */
export function pvStringsKpiItems(data: PVStringsResponse, zeitraumLabel?: string): KpiStripItem[] {
  const ref = Math.max(data.prognose_gesamt_kwh, data.ist_gesamt_kwh)
  const e = (v: number) => formatEnergie(v, ref)
  const abwProz = data.abweichung_gesamt_prozent || 0
  const spez = data.anlagen_leistung_kwp > 0 ? data.ist_gesamt_kwh / data.anlagen_leistung_kwp : 0
  return [
    {
      title: 'SOLL (Prognose)', value: e(data.prognose_gesamt_kwh).wert, unit: e(data.prognose_gesamt_kwh).einheit,
      color: 'blue', icon: Sun, subtitle: 'PVGIS Jahresprognose', parkId: 'kpi:soll',
      formel: 'Σ PVGIS-Prognose aller Strings', ergebnis: `= ${e(data.prognose_gesamt_kwh).text}`,
    },
    {
      title: 'IST (Erzeugt)', value: e(data.ist_gesamt_kwh).wert, unit: e(data.ist_gesamt_kwh).einheit,
      color: 'yellow', icon: TrendingUp, subtitle: zeitraumLabel, parkId: 'kpi:ist',
      formel: 'Σ Erzeugung aller Strings', ergebnis: `= ${e(data.ist_gesamt_kwh).text}`,
    },
    {
      title: 'Abweichung', value: `${abwProz >= 0 ? '+' : ''}${formatProzent(abwProz).wert}`, unit: '%',
      color: abwProz >= 0 ? 'green' : 'red', icon: abwProz >= 0 ? TrendingUp : TrendingDown,
      subtitle: `${data.abweichung_gesamt_kwh >= 0 ? '+' : ''}${e(data.abweichung_gesamt_kwh).text}`, parkId: 'kpi:abweichung',
      formel: '(IST − SOLL) ÷ SOLL', ergebnis: `= ${formatProzent(abwProz).text}`,
    },
    {
      title: 'Spez. Ertrag Ø', value: formatSpezErtrag(spez).wert, unit: 'kWh/kWp',
      color: 'purple', icon: GitCompare, subtitle: zeitraumLabel, parkId: 'kpi:spez-ertrag',
      formel: 'IST-Erzeugung ÷ Anlagenleistung', ergebnis: `= ${formatSpezErtrag(spez).text}`,
    },
  ]
}

export function PvStringHeaderZeile({ data, zeitraumLabel, onCsv }: {
  data: PVStringsResponse; zeitraumLabel?: string; onCsv?: () => void
}) {
  return (
    <div className="flex items-center justify-between">
      <p className="text-sm text-gray-500 dark:text-gray-400">
        <span className="font-medium text-gray-700 dark:text-gray-300">{zeitraumLabel}</span>
        {' '}&bull;{' '}{data.strings.length} Strings &bull; {fmtZahl(data.anlagen_leistung_kwp, 1)} kWp
      </p>
      {onCsv && (
        <Button variant="secondary" size="sm" onClick={onCsv}>
          <Download className="h-4 w-4 mr-2" />CSV-Export
        </Button>
      )}
    </div>
  )
}

export function PvStringBestSchlecht({ data }: { data: PVStringsResponse }) {
  if (data.strings.length <= 1) return null
  return (
    <div className="flex flex-wrap gap-3">
      {data.bester_string && (
        <div className="flex items-center gap-2 bg-green-50 dark:bg-green-900/20 px-4 py-2 rounded-lg">
          <TrendingUp className="h-5 w-5 text-green-600" />
          <div>
            <p className="text-xs text-green-600 dark:text-green-400">Beste Performance</p>
            <p className="font-medium text-green-700 dark:text-green-300">{data.bester_string}</p>
          </div>
        </div>
      )}
      {data.schlechtester_string && data.schlechtester_string !== data.bester_string && (
        <div className="flex items-center gap-2 bg-red-50 dark:bg-red-900/20 px-4 py-2 rounded-lg">
          <TrendingDown className="h-5 w-5 text-red-600" />
          <div>
            <p className="text-xs text-red-600 dark:text-red-400">Schwächste Performance</p>
            <p className="font-medium text-red-700 dark:text-red-300">{data.schlechtester_string}</p>
          </div>
        </div>
      )}
    </div>
  )
}

export function PvStringSollIstBar({ data }: { data: PVStringsResponse }) {
  const maxKwh = Math.max(0, ...data.strings.flatMap(s => [s.prognose_jahr_kwh, s.ist_jahr_kwh]))
  const eAchse = energieAchse(maxKwh)
  return (
    <Card>
      <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
        <GitCompare className="h-5 w-5 text-blue-500" />SOLL vs IST pro String
      </h3>
      <div className="h-72">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart
            data={data.strings.map((s) => ({
              name: s.bezeichnung.length > 12 ? s.bezeichnung.slice(0, 12) + '...' : s.bezeichnung,
              SOLL: s.prognose_jahr_kwh, IST: s.ist_jahr_kwh,
            }))}
            layout="vertical"
            margin={{ top: ACHSEN_MARGIN_TOP }}
          >
            <CartesianGrid strokeDasharray="3 3" className="stroke-gray-200 dark:stroke-gray-700" />
            <XAxis type="number" tickFormatter={(v) => `${eAchse.tick(v)} ${eAchse.einheit}`} tick={{ fontSize: 10 }} /* achsen-allow: Wert-Achse waagerecht, Einheit/Format pro Tick (de-DE) */ />
            <YAxis type="category" dataKey="name" width={100} tick={{ fontSize: 10 }} /* achsen-allow: Kategorie-Namen (String) */ />
            <Tooltip content={<ChartTooltip formatter={(v: number) => formatEnergie(v, maxKwh).text} />} />
            <Legend content={<ChartLegende />} />
            <Bar dataKey="SOLL" fill={SOLL_IST_COLORS.soll} stroke={SOLL_IST_COLORS.soll} strokeWidth={1} strokeDasharray={PROGNOSE_DASH} name="SOLL (Prognose)" />
            <Bar dataKey="IST" fill={SOLL_IST_COLORS.ist} name="IST (Erzeugt)" />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </Card>
  )
}

export function PvStringMonatsverlauf({ data, selectedYear }: { data: PVStringsResponse; selectedYear: number | 'all' }) {
  const chartData = (data.strings[0]?.monatswerte.map((m, mIdx) => {
    const soll = data.strings.reduce((sum, s) => sum + (s.monatswerte[mIdx]?.prognose_kwh || 0), 0)
    const ist = data.strings.reduce((sum, s) => sum + (s.monatswerte[mIdx]?.ist_kwh || 0), 0)
    return { name: m.monat_name, SOLL: soll, IST: ist, Abweichung: ist - soll }
  }) || [])
  const maxKwh = Math.max(0, ...chartData.flatMap(d => [d.SOLL, d.IST]))
  const eAchse = energieAchse(maxKwh)
  return (
    <Card>
      <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
        Monatsverlauf SOLL vs IST {selectedYear === 'all' ? '(Summe aller Jahre)' : ''}
      </h3>
      <div className="h-72">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={chartData} margin={{ top: ACHSEN_MARGIN_TOP }}>
            <CartesianGrid strokeDasharray="3 3" className="stroke-gray-200 dark:stroke-gray-700" />
            <XAxis dataKey="name" tick={{ fontSize: 10 }} /* achsen-allow: Zeit-/Kategorie-Achse (Monat) */ />
            <YAxis width={60} tick={{ fontSize: 10 }} tickFormatter={eAchse.tick} label={achsenEinheit(eAchse.einheit)} />
            <Tooltip content={<ChartTooltip formatter={(v: number) => formatEnergie(v, maxKwh).text} />} />
            <Legend content={<ChartLegende />} />
            <Bar dataKey="SOLL" fill={SOLL_IST_COLORS.soll} stroke={SOLL_IST_COLORS.soll} strokeWidth={1} strokeDasharray={PROGNOSE_DASH} name="SOLL" />
            <Bar dataKey="IST" fill={SOLL_IST_COLORS.ist} name="IST" />
            <Line type="monotone" dataKey="Abweichung" stroke={SOLL_IST_COLORS.abweichung} strokeWidth={2} dot={{ r: 3 }} name="Abweichung" />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </Card>
  )
}

export function PvStringTabelle({ data }: { data: PVStringsResponse }) {
  const stringsSortedByPerf = [...data.strings].sort((a, b) => (b.performance_ratio_jahr || 0) - (a.performance_ratio_jahr || 0))
  const eRef = Math.max(0, ...data.strings.flatMap(s => [s.prognose_jahr_kwh, s.ist_jahr_kwh]))
  const e = (v: number) => formatEnergie(v, eRef).text
  return (
    <Card>
      <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">String-Details</h3>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 dark:bg-gray-800">
            <tr>
              <th className="px-3 py-2 text-left font-medium text-gray-500">String</th>
              <th className="px-3 py-2 text-right font-medium text-gray-500">kWp</th>
              <th className="px-3 py-2 text-left font-medium text-gray-500">Ausrichtung</th>
              <th className="px-3 py-2 text-right font-medium text-gray-500">SOLL</th>
              <th className="px-3 py-2 text-right font-medium text-gray-500">IST</th>
              <th className="px-3 py-2 text-right font-medium text-gray-500">Abweichung</th>
              <th className="px-3 py-2 text-right font-medium text-gray-500">kWh/kWp</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
            {stringsSortedByPerf.map((s) => (
              <tr key={s.investition_id} className="hover:bg-gray-50 dark:hover:bg-gray-800">
                <td className="px-3 py-3">
                  <div className="flex items-center gap-2">
                    <div className="w-3 h-3 rounded-full" style={{ backgroundColor: STRING_COLORS[data.strings.findIndex(x => x.investition_id === s.investition_id) % STRING_COLORS.length] }} />
                    <span className="font-medium text-gray-900 dark:text-white">{s.bezeichnung}</span>
                  </div>
                  {s.wechselrichter_name && <p className="text-xs text-gray-500 ml-5">→ {s.wechselrichter_name}</p>}
                </td>
                <td className="px-3 py-3 text-right">{fmtZahl(s.leistung_kwp, 1)}</td>
                <td className="px-3 py-3">{s.ausrichtung || '-'}{s.neigung_grad ? ` / ${s.neigung_grad}°` : ''}</td>
                <td className="px-3 py-3 text-right text-blue-600">{e(s.prognose_jahr_kwh)}</td>
                <td className="px-3 py-3 text-right text-amber-600 font-medium">{e(s.ist_jahr_kwh)}</td>
                <td className={`px-3 py-3 text-right font-medium ${(s.abweichung_jahr_prozent || 0) >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                  {(s.abweichung_jahr_prozent || 0) >= 0 ? '+' : ''}{s.abweichung_jahr_prozent != null ? formatProzent(s.abweichung_jahr_prozent).text : '0 %'}
                </td>
                <td className="px-3 py-3 text-right text-purple-600">{s.spezifischer_ertrag_kwh_kwp != null ? fmtZahl(s.spezifischer_ertrag_kwh_kwp, 0) : '-'}</td>
              </tr>
            ))}
          </tbody>
          {data.strings.length > 1 && (
            <tfoot className="bg-gray-100 dark:bg-gray-800 font-medium">
              <tr>
                <td className="px-3 py-2">Gesamt</td>
                <td className="px-3 py-2 text-right">{fmtZahl(data.anlagen_leistung_kwp, 1)}</td>
                <td className="px-3 py-2">-</td>
                <td className="px-3 py-2 text-right text-blue-600">{e(data.prognose_gesamt_kwh)}</td>
                <td className="px-3 py-2 text-right text-amber-600">{e(data.ist_gesamt_kwh)}</td>
                <td className={`px-3 py-2 text-right ${(data.abweichung_gesamt_prozent || 0) >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                  {(data.abweichung_gesamt_prozent || 0) >= 0 ? '+' : ''}{data.abweichung_gesamt_prozent != null ? formatProzent(data.abweichung_gesamt_prozent).text : '0 %'}
                </td>
                <td className="px-3 py-2 text-right text-purple-600">{fmtZahl(data.anlagen_leistung_kwp > 0 ? data.ist_gesamt_kwh / data.anlagen_leistung_kwp : 0, 0)}</td>
              </tr>
            </tfoot>
          )}
        </table>
      </div>
    </Card>
  )
}

/** Block ③ — Performance-Ratio über Jahre (Caller gated auf „Alle Jahre"). */
export function PvStringMehrjahr({ data, jahresvergleichData }: {
  data: PVStringsResponse; jahresvergleichData: Array<Record<string, number | string>>
}) {
  return (
    <Card>
      <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">Performance-Entwicklung über Jahre</h3>
      <div className="h-72">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={jahresvergleichData} margin={{ top: ACHSEN_MARGIN_TOP }}>
            <CartesianGrid strokeDasharray="3 3" className="stroke-gray-200 dark:stroke-gray-700" />
            <XAxis dataKey="name" tick={{ fontSize: 10 }} /* achsen-allow: Zeit-/Kategorie-Achse (Jahr) */ />
            <YAxis label={achsenEinheit('%')} domain={[80, 120]} ticks={[80, 90, 100, 110, 120]} tickFormatter={achsenTick} tick={{ fontSize: 10 }} />
            <Tooltip content={<ChartTooltip unit="%" />} />
            <Legend content={<ChartLegende />} />
            {data.strings.map((s, idx) => (
              <Line key={s.investition_id} type="monotone" dataKey={s.bezeichnung}
                stroke={STRING_COLORS[idx % STRING_COLORS.length]} strokeWidth={2} dot={{ r: 4 }} />
            ))}
            <Line type="monotone" dataKey="Gesamt" stroke={KATEGORIE_FARBEN.sonstige} strokeWidth={3} strokeDasharray={HILFSLINIE_DASH} dot={{ r: 4 }} />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <p className="text-xs text-gray-500 mt-2 text-center">100 % = Prognose erreicht • Werte über 100 % = Überperformance</p>
    </Card>
  )
}
