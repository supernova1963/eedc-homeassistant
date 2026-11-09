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
import { Sun, TrendingUp, TrendingDown, GitCompare } from 'lucide-react'
import { Card, ChartLegende, CsvExportButton, Table, TableHead, TableBody, TableFoot } from '../ui'
import { ZELLE, KOPF_ZELLE } from '../ui/tabelleMasse'
import ChartTooltip from '../ui/ChartTooltip'
import { useLegendenToggle } from '../../hooks'
import { HerkunftZeile, type KpiStripItem } from '../blocks'
import { pvVergleichHerkunft } from '../../lib/pvHerkunft'
import { exportToCSV } from '../../utils/export'
import { cockpitApi, PVStringsResponse, type PVStringsGesamtlaufzeitResponse } from '../../api/cockpit'
import {
  SOLL_IST_COLORS, STRING_COLORS, KATEGORIE_FARBEN, HILFSLINIE_DASH,
  formatEnergie, energieAchse, formatProzent, formatSpezErtrag, fmtZahl,
  xAchse, yAchse, achsenEinheit, achsenTick, ACHSEN_MARGIN_TOP,
} from '../../lib'
import { mitAnzahl } from '../../lib/plural'

/** Die Jahres-Antworten für den Mehrjahres-Chart (Block ③) — ein Jahr ohne Antwort wird übersprungen. */
async function ladeJahre(anlageId: number, jahre: number[]): Promise<Map<number, PVStringsResponse>> {
  const dataMap = new Map<number, PVStringsResponse>()
  for (const jahr of jahre) {
    try { dataMap.set(jahr, await cockpitApi.getPVStrings(anlageId, jahr)) } catch { /* Jahr übersprungen */ }
  }
  return dataMap
}

/** Päckchen BB4: Laufzeit-Antwort → `PVStringsResponse`-Form der geteilten Teile — reine Umbenennung, keine Rechnung.
 *  Die Zeilen sind die Träger der ganzen Laufzeit (N-613: ein BKW, das seine Erzeugung später an Modul-Kinder
 *  abgetreten hat, steht mit seinen Jahren drin). */
export function laufzeitAlsJahr(r: PVStringsGesamtlaufzeitResponse): PVStringsResponse {
  return {
    anlage_id: r.anlage_id, jahr: r.letztes_jahr, hat_prognose: r.hat_prognose, prognose_warnung: r.prognose_warnung,
    anlagen_leistung_kwp: r.anlagen_leistung_kwp,
    prognose_gesamt_kwh: r.prognose_gesamt_kwh, ist_gesamt_kwh: r.ist_gesamt_kwh,
    abweichung_gesamt_kwh: r.abweichung_gesamt_kwh, abweichung_gesamt_prozent: r.abweichung_gesamt_prozent,
    spezifischer_ertrag_kwh_kwp: r.spezifischer_ertrag_zeitraum_kwh_kwp ?? null,
    bester_string: r.bester_string, schlechtester_string: r.schlechtester_string,
    ist_quelle: r.ist_quelle, vergleich_hinweis: r.vergleich_hinweis, vergleich_grund: r.vergleich_grund,
    strings: r.strings.map((s) => ({
      investition_id: s.investition_id, bezeichnung: s.bezeichnung, leistung_kwp: s.leistung_kwp,
      ausrichtung: s.ausrichtung, neigung_grad: s.neigung_grad, wechselrichter_id: null,
      wechselrichter_name: s.wechselrichter_name,
      prognose_jahr_kwh: s.prognose_gesamt_kwh, ist_jahr_kwh: s.ist_gesamt_kwh,
      abweichung_jahr_kwh: s.abweichung_gesamt_kwh ?? 0, abweichung_jahr_prozent: s.abweichung_gesamt_prozent,
      performance_ratio_jahr: s.performance_ratio_gesamt, spezifischer_ertrag_kwh_kwp: s.spezifischer_ertrag_kwh_kwp,
      ist_quelle: s.ist_quelle,
      monatswerte: (s.monatswerte_summe ?? []).map((m) => ({
        monat: m.monat, monat_name: m.monat_name, prognose_kwh: m.prognose_summe_kwh, ist_kwh: m.ist_summe_kwh,
        // Je Monat zeigt der Verlauf «Summe aller Jahre» nur SOLL und IST; die Monats-Kennzahlen gibt es nur im Jahr.
        abweichung_kwh: null, abweichung_prozent: null, performance_ratio: null, ist_quelle: s.ist_quelle,
      })),
    })),
  }
}

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
        // Päckchen BB4: «Alle Jahre» liest die Laufzeit-Route — Summen, Abweichung, PR, Ranking-Sperre (A4/b1),
        // spezifischer Ertrag und der Monatsverlauf «Summe aller Jahre» kommen fertig aus dem Backend; der Adapter
        // benennt nur um. Bis dahin faltete der Client die Jahres-Antworten (Σ gerundeter Jahre).
        const [laufzeit, dataMap] = await Promise.all([
          cockpitApi.getPVStringsGesamtlaufzeit(anlageId),
          ladeJahre(anlageId, verfuegbareJahre),
        ])
        // Der Mehrjahres-Chart (Block ③) zeigt je Jahr PR je String und den Anlagen-Kopf des Jahres — die
        // Jahres-Antworten selbst, ohne Faltung.
        setMultiYearData(dataMap)
        setData(laufzeitAlsJahr(laufzeit))
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
  // Päckchen BB4: IST ÷ Anlagen-kWp kommt fertig aus dem Backend (Jahr: `computed_field`, alle Jahre: Laufzeit-Route).
  const spez = data.spezifischer_ertrag_kwh_kwp ?? 0
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
        {' '}&bull;{' '}{mitAnzahl(data.strings.length, 'String', 'Strings')} &bull; {fmtZahl(data.anlagen_leistung_kwp, 1)} kWp
      </p>
      {/* D13-10/D14-18: Icon + Wort IMMER (CsvExportButton-SoT) — Icon-only wirkte
          mobil wie „CSV fehlt". */}
      {onCsv && <CsvExportButton onClick={onCsv} />}
    </div>
  )
}

export function PvStringBestSchlecht({ data }: { data: PVStringsResponse }) {
  if (data.strings.length <= 1) return null
  // A4/b1: Sind die IST-Werte nach kWp verteilt, hat rechnerisch jedes Modul
  // denselben spezifischen Ertrag — dann gibt es keine Platzierung, sondern die
  // Erklärung warum (Backend-Satz, dieselbe Zeile wie im Komponenten-Hub).
  if (data.vergleich_hinweis) {
    return <HerkunftZeile herkunft={pvVergleichHerkunft('IST je Modul', data.vergleich_hinweis, data.vergleich_grund)} />
  }
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
  const legende = useLegendenToggle()
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
            <Legend content={<ChartLegende onItemClick={legende.onItemClick} />} />
            {/* D14-10: kein Dash-Border an Balken (Dash-Kanon nur für Linien-Serien). */}
            <Bar dataKey="SOLL" fill={SOLL_IST_COLORS.soll} name="SOLL (Prognose)" hide={legende.istVersteckt('SOLL')} />
            <Bar dataKey="IST" fill={SOLL_IST_COLORS.ist} name="IST (Erzeugt)" hide={legende.istVersteckt('IST')} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </Card>
  )
}

export function PvStringMonatsverlauf({ data, selectedYear }: { data: PVStringsResponse; selectedYear: number | 'all' }) {
  const legende = useLegendenToggle()
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
            <XAxis dataKey="name" {...xAchse()} /* achsen-allow: Zeit-/Kategorie-Achse (Monat) */ />
            <YAxis width={60} tick={{ fontSize: 10 }} tickFormatter={eAchse.tick} label={achsenEinheit(eAchse.einheit)} />
            <Tooltip content={<ChartTooltip formatter={(v: number) => formatEnergie(v, maxKwh).text} />} />
            <Legend content={<ChartLegende onItemClick={legende.onItemClick} />} />
            {/* D14-10: kein Dash-Border an Balken (Dash-Kanon nur für Linien-Serien). */}
            <Bar dataKey="SOLL" fill={SOLL_IST_COLORS.soll} name="SOLL" hide={legende.istVersteckt('SOLL')} />
            <Bar dataKey="IST" fill={SOLL_IST_COLORS.ist} name="IST" hide={legende.istVersteckt('IST')} />
            <Line type="monotone" dataKey="Abweichung" stroke={SOLL_IST_COLORS.abweichung} strokeWidth={2} dot={{ r: 3 }} name="Abweichung" hide={legende.istVersteckt('Abweichung')} />
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
      <Table mitFuss flaeche="karte">
          <TableHead>
            <tr>
              <th className={`${KOPF_ZELLE} text-left text-gray-500`}>String</th>
              <th className={`${KOPF_ZELLE} text-right text-gray-500`}>kWp</th>
              <th className={`${KOPF_ZELLE} text-left text-gray-500`}>Ausrichtung</th>
              <th className={`${KOPF_ZELLE} text-right text-gray-500`}>SOLL</th>
              <th className={`${KOPF_ZELLE} text-right text-gray-500`}>IST</th>
              <th className={`${KOPF_ZELLE} text-right text-gray-500`}>Abweichung</th>
              <th className={`${KOPF_ZELLE} text-right text-gray-500`}>kWh/kWp</th>
            </tr>
          </TableHead>
          <TableBody>
            {stringsSortedByPerf.map((s) => (
              <tr key={s.investition_id} className="hover:bg-gray-50 dark:hover:bg-gray-800">
                <td className={ZELLE}>
                  <div className="flex items-center gap-2">
                    <div className="w-3 h-3 rounded-full" style={{ backgroundColor: STRING_COLORS[data.strings.findIndex(x => x.investition_id === s.investition_id) % STRING_COLORS.length] }} />
                    <span className="font-medium text-gray-900 dark:text-white">{s.bezeichnung}</span>
                  </div>
                  {s.wechselrichter_name && <p className="text-xs text-gray-500 ml-5">→ {s.wechselrichter_name}</p>}
                </td>
                <td className={`${ZELLE} text-right`}>{fmtZahl(s.leistung_kwp, 1)}</td>
                <td className={ZELLE}>{s.ausrichtung || '-'}{s.neigung_grad ? ` / ${s.neigung_grad}°` : ''}</td>
                <td className={`${ZELLE} text-right text-blue-600`}>{e(s.prognose_jahr_kwh)}</td>
                <td className={`${ZELLE} text-right text-amber-600 font-medium`}>{e(s.ist_jahr_kwh)}</td>
                <td className={`${ZELLE} text-right font-medium ${(s.abweichung_jahr_prozent || 0) >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                  {(s.abweichung_jahr_prozent || 0) >= 0 ? '+' : ''}{s.abweichung_jahr_prozent != null ? formatProzent(s.abweichung_jahr_prozent).text : '0 %'}
                </td>
                <td className={`${ZELLE} text-right text-purple-600`}>{s.spezifischer_ertrag_kwh_kwp != null ? fmtZahl(s.spezifischer_ertrag_kwh_kwp, 0) : '-'}</td>
              </tr>
            ))}
          </TableBody>
          {data.strings.length > 1 && (
            <TableFoot>
              <tr>
                <td className={ZELLE}>Gesamt</td>
                <td className={`${ZELLE} text-right`}>{fmtZahl(data.anlagen_leistung_kwp, 1)}</td>
                <td className={ZELLE}>-</td>
                <td className={`${ZELLE} text-right text-blue-600`}>{e(data.prognose_gesamt_kwh)}</td>
                <td className={`${ZELLE} text-right text-amber-600`}>{e(data.ist_gesamt_kwh)}</td>
                <td className={`${ZELLE} text-right ${(data.abweichung_gesamt_prozent || 0) >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                  {(data.abweichung_gesamt_prozent || 0) >= 0 ? '+' : ''}{data.abweichung_gesamt_prozent != null ? formatProzent(data.abweichung_gesamt_prozent).text : '0 %'}
                </td>
                <td className={`${ZELLE} text-right text-purple-600`}>{fmtZahl(data.spezifischer_ertrag_kwh_kwp ?? 0, 0)}</td>
              </tr>
            </TableFoot>
          )}
        </Table>
    </Card>
  )
}

/** Block ③ — Performance-Ratio über Jahre (Caller gated auf „Alle Jahre"). */
export function PvStringMehrjahr({ data, jahresvergleichData }: {
  data: PVStringsResponse; jahresvergleichData: Array<Record<string, number | string>>
}) {
  const legende = useLegendenToggle()
  return (
    <Card>
      <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">Performance-Entwicklung über Jahre</h3>
      <div className="h-72">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={jahresvergleichData} margin={{ top: ACHSEN_MARGIN_TOP }}>
            <CartesianGrid strokeDasharray="3 3" className="stroke-gray-200 dark:stroke-gray-700" />
            <XAxis dataKey="name" {...xAchse()} /* achsen-allow: Zeit-/Kategorie-Achse (Jahr) */ />
            <YAxis label={achsenEinheit('%')} domain={[80, 120]} ticks={[80, 90, 100, 110, 120]} tickFormatter={achsenTick} {...yAchse(false)} />
            <Tooltip content={<ChartTooltip unit="%" />} />
            <Legend content={<ChartLegende onItemClick={legende.onItemClick} />} />
            {data.strings.map((s, idx) => (
              <Line key={s.investition_id} type="monotone" dataKey={s.bezeichnung}
                stroke={STRING_COLORS[idx % STRING_COLORS.length]} strokeWidth={2} dot={{ r: 4 }} hide={legende.istVersteckt(s.bezeichnung)} />
            ))}
            <Line type="monotone" dataKey="Gesamt" stroke={KATEGORIE_FARBEN.sonstige} strokeWidth={3} strokeDasharray={HILFSLINIE_DASH} dot={{ r: 4 }} hide={legende.istVersteckt('Gesamt')} />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <p className="text-xs text-gray-500 mt-2 text-center">100 % = Prognose erreicht • Werte über 100 % = Überperformance</p>
    </Card>
  )
}
