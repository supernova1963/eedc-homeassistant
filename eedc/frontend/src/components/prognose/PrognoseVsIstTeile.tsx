/**
 * PrognoseVsIst — geteilte Element-Bausteine (A.5 Sub 4, Block ①).
 *
 * Eine Code-Wahrheit: die IST-Seite `pages/PrognoseVsIst.tsx` UND die v4-Sicht
 * `v4/AuswertungenPrognoseV4.tsx` komponieren aus diesen Teilen. Jeder Teil ist ein
 * eigenständiges Anzeige-Element (v4 umhüllt es mit `Parkbar`; IST rendert es direkt).
 * Zahlen/Einheiten via `lib/einheiten.ts` (R1/R2: kWh→MWh ab 1.000, Tausenderpunkt,
 * pro KPI-Strip eine gemeinsame Einheit über den Referenzwert); Farben aus colors.ts.
 */
import { useState, useEffect, useCallback } from 'react'
import { TrendingUp, TrendingDown, Download } from 'lucide-react'
import {
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
  ComposedChart, Line, ReferenceLine, Bar,
} from 'recharts'
import { Card, Button, ChartLegende } from '../ui'
import ChartTooltip from '../ui/ChartTooltip'
import type { KpiStripItem } from '../blocks'
import { pvgisApi, monatsdatenApi } from '../../api'
import type { PVModulPrognose } from '../../api/pvgis'
import type { AggregierteMonatsdaten } from '../../api/monatsdaten'
import { SOLL_IST_COLORS, PROGNOSE_DASH, formatEnergie, energieAchse, formatProzent, xAchse, yAchse } from '../../lib'
import { useSchmaleAchse } from '../../hooks'
import { useChartTheme } from '../../context/ThemeContext'

const monatNamen = ['', 'Jan', 'Feb', 'Mär', 'Apr', 'Mai', 'Jun', 'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Dez']

interface PrognoseData {
  jahresertrag_kwh: number
  monatswerte: Array<{ monat: number; e_m: number }>
  isLive?: boolean
  module?: PVModulPrognose[]
}

export interface VergleichsDaten {
  monat: number
  monatName: string
  prognose: number
  ist: number
  abweichung: number
  abweichungProzent: number
}

export interface PrognoseVsIstVM {
  loading: boolean
  error: string | null
  prognose: PrognoseData | null
  monatsdaten: AggregierteMonatsdaten[]
  verfuegbareJahre: number[]
  vergleichsDaten: VergleichsDaten[]
  jahresPrognose: number
  jahresIst: number
  jahresAbweichung: number
  jahresAbweichungProzent: number
  monateMitDaten: number
  hochgerechneterJahresIst: number
  saving: boolean
  reload: () => void
  save: () => Promise<void>
}

/** Lädt PVGIS-Prognose (gespeichert ∨ live) + Monatsdaten und berechnet den
 *  Jahres-SOLL/IST-Vergleich für ein konkretes Jahr. Geteilt von IST + v4. */
export function usePrognoseVsIst(anlageId: number | null | undefined, jahr: number | undefined): PrognoseVsIstVM {
  const [prognose, setPrognose] = useState<PrognoseData | null>(null)
  const [monatsdaten, setMonatsdaten] = useState<AggregierteMonatsdaten[]>([])
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    if (!anlageId) return
    setLoading(true)
    setError(null)
    try {
      const md = await monatsdatenApi.listAggregiert(anlageId)
      setMonatsdaten(md)
      const gespeichert = await pvgisApi.getAktivePrognose(anlageId)
      if (gespeichert) {
        setPrognose({ jahresertrag_kwh: gespeichert.jahresertrag_kwh, monatswerte: gespeichert.monatswerte, isLive: false })
      } else {
        try {
          const live = await pvgisApi.getPrognose(anlageId)
          setPrognose({
            jahresertrag_kwh: live.jahresertrag_kwh,
            monatswerte: live.monatsdaten.map(m => ({ monat: m.monat, e_m: m.e_m })),
            isLive: true, module: live.module,
          })
        } catch (pvgisError) {
          setPrognose(null)
          if (pvgisError instanceof Error && pvgisError.message.includes('PV-Module')) {
            setError('Keine PV-Module für diese Anlage definiert. Bitte unter Einstellungen → Investitionen anlegen.')
          }
        }
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Fehler beim Laden')
    } finally {
      setLoading(false)
    }
  }, [anlageId])

  useEffect(() => { void load() }, [load, jahr])

  const save = useCallback(async () => {
    if (!anlageId) return
    setSaving(true)
    try {
      await pvgisApi.speicherePrognose(anlageId)
      const currentModule = prognose?.module
      await load()
      if (currentModule && currentModule.length > 0) {
        setPrognose(prev => prev ? { ...prev, module: currentModule } : null)
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Fehler beim Speichern')
    } finally {
      setSaving(false)
    }
  }, [anlageId, prognose, load])

  const verfuegbareJahre = [...new Set(monatsdaten.map(m => m.jahr))].sort((a, b) => b - a)

  const vergleichsDaten: VergleichsDaten[] = []
  if (prognose?.monatswerte && jahr != null) {
    for (let monat = 1; monat <= 12; monat++) {
      const prognoseWert = prognose.monatswerte.find(m => m.monat === monat)?.e_m || 0
      const istWert = monatsdaten
        .filter(m => m.jahr === jahr && m.monat === monat)
        .reduce((sum, m) => sum + (m.pv_erzeugung_kwh || 0), 0)
      const abweichung = istWert - prognoseWert
      vergleichsDaten.push({
        monat, monatName: monatNamen[monat], prognose: prognoseWert, ist: istWert,
        abweichung, abweichungProzent: prognoseWert > 0 ? (abweichung / prognoseWert) * 100 : 0,
      })
    }
  }

  const jahresPrognose = vergleichsDaten.reduce((s, d) => s + d.prognose, 0)
  const jahresIst = vergleichsDaten.reduce((s, d) => s + d.ist, 0)
  const jahresAbweichung = jahresIst - jahresPrognose
  const jahresAbweichungProzent = jahresPrognose > 0 ? (jahresAbweichung / jahresPrognose) * 100 : 0
  const monateMitDaten = 12 - vergleichsDaten.filter(d => d.ist === 0).length
  const hochgerechneterJahresIst = monateMitDaten > 0 ? (jahresIst / monateMitDaten) * 12 : 0

  return {
    loading, error, prognose, monatsdaten, verfuegbareJahre, vergleichsDaten,
    jahresPrognose, jahresIst, jahresAbweichung, jahresAbweichungProzent,
    monateMitDaten, hochgerechneterJahresIst, saving, reload: () => void load(), save,
  }
}

/** R2: gemeinsame Energie-Einheit über alle KPIs des Strips (größter Wert = Referenz). */
export function pvgisKpiItems(vm: PrognoseVsIstVM, jahr: number | undefined): KpiStripItem[] {
  const ref = Math.max(vm.jahresPrognose, vm.jahresIst, Math.abs(vm.jahresAbweichung), vm.hochgerechneterJahresIst)
  const e = (v: number) => formatEnergie(v, ref)
  const vzP = vm.jahresAbweichung >= 0 ? '+' : ''
  const items: KpiStripItem[] = [
    {
      title: 'PVGIS Prognose', value: e(vm.jahresPrognose).wert, unit: e(vm.jahresPrognose).einheit,
      color: 'yellow', subtitle: jahr != null ? `Jahr ${jahr}` : 'Jahr', parkId: 'kpi:pvgis-prognose',
      formel: 'Σ PVGIS-Monatsprognose', ergebnis: `= ${e(vm.jahresPrognose).text}`,
    },
    {
      title: 'IST-Erzeugung', value: e(vm.jahresIst).wert, unit: e(vm.jahresIst).einheit,
      color: 'green', subtitle: `${vm.monateMitDaten} von 12 Monaten`, parkId: 'kpi:ist-erzeugung',
      formel: 'Σ IST-PV-Erzeugung', ergebnis: `= ${e(vm.jahresIst).text}`,
    },
    {
      title: 'Abweichung', value: `${vzP}${e(vm.jahresAbweichung).wert}`, unit: e(vm.jahresAbweichung).einheit,
      color: vm.jahresAbweichung >= 0 ? 'green' : 'red', icon: vm.jahresAbweichung >= 0 ? TrendingUp : TrendingDown,
      subtitle: `${vzP}${formatProzent(vm.jahresAbweichungProzent).text}`, parkId: 'kpi:abweichung',
      formel: '(IST − SOLL) ÷ SOLL', ergebnis: `= ${vzP}${formatProzent(vm.jahresAbweichungProzent).text}`,
    },
  ]
  if (vm.monateMitDaten < 12 && vm.monateMitDaten > 0) {
    const proz = vm.jahresPrognose > 0 ? (vm.hochgerechneterJahresIst / vm.jahresPrognose - 1) * 100 : 0
    items.push({
      title: 'Hochrechnung Jahr', value: e(vm.hochgerechneterJahresIst).wert, unit: e(vm.hochgerechneterJahresIst).einheit,
      color: 'blue', subtitle: `${proz >= 0 ? '+' : ''}${formatProzent(proz).text} vs. Prognose`, parkId: 'kpi:hochrechnung',
      formel: 'IST ÷ Monate mit Daten × 12', ergebnis: `= ${e(vm.hochgerechneterJahresIst).text}`,
    })
  }
  return items
}

/** Live-Prognose-Hinweis + „Prognose speichern" (nur bei Live-Abruf). */
export function PvgisSpeichern({ vm }: { vm: PrognoseVsIstVM }) {
  if (!vm.prognose?.isLive) return null
  return (
    <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-4 flex items-center justify-between gap-4">
      <div className="text-blue-700 dark:text-blue-300">
        <strong>Live-Prognose:</strong> Diese Prognose wurde gerade von PVGIS abgerufen und ist noch nicht gespeichert.
      </div>
      <Button size="sm" onClick={vm.save} disabled={vm.saving}>
        <Download className="h-4 w-4 mr-1" />
        {vm.saving ? 'Speichern…' : 'Speichern'}
      </Button>
    </div>
  )
}

/** Monatlicher SOLL/IST-Vergleich (Balken) + Abweichungs-Linie. */
export function PvgisMonatsChart({ vm, jahr }: { vm: PrognoseVsIstVM; jahr: number | undefined }) {
  const achsen = useChartTheme()
  const schmal = useSchmaleAchse()
  const maxKwh = Math.max(0, ...vm.vergleichsDaten.flatMap(d => [d.prognose, d.ist]))
  const eAchse = energieAchse(maxKwh)
  return (
    <Card className="space-y-4">
      <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
        Monatlicher Vergleich{jahr != null ? ` ${jahr}` : ''}
      </h2>
      <div className="h-80">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={vm.vergleichsDaten}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="monatName" {...xAchse(schmal)} />
            <YAxis yAxisId="left" tickFormatter={eAchse.tick} unit={` ${eAchse.einheit}`} {...yAchse(schmal)} />
            <YAxis yAxisId="right" orientation="right" tickFormatter={(v) => `${v}%`} />
            <Tooltip content={<ChartTooltip formatter={(value: number, name: string) =>
              name.includes('%') ? formatProzent(value).text : formatEnergie(value, maxKwh).text} />} />
            <Legend content={<ChartLegende />} />
            <ReferenceLine yAxisId="right" y={0} stroke={achsen.referenz} strokeDasharray="3 3" />
            <Bar yAxisId="left" dataKey="prognose" fill={SOLL_IST_COLORS.soll} stroke={SOLL_IST_COLORS.soll} strokeWidth={1} strokeDasharray={PROGNOSE_DASH} name="PVGIS Prognose" />
            <Bar yAxisId="left" dataKey="ist" fill={SOLL_IST_COLORS.ist} name="IST-Erzeugung" />
            <Line yAxisId="right" type="monotone" dataKey="abweichungProzent" stroke={SOLL_IST_COLORS.abweichung} strokeWidth={2} name="Abweichung %" dot={{ fill: SOLL_IST_COLORS.abweichung }} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </Card>
  )
}

/** Monats-Detailtabelle inkl. Gesamt-Fuß + Bewertungsspalte. */
export function PvgisDetailTabelle({ vm }: { vm: PrognoseVsIstVM }) {
  const eRef = Math.max(0, ...vm.vergleichsDaten.flatMap(d => [d.prognose, d.ist]))
  const e = (v: number) => formatEnergie(v, eRef).text
  return (
    <Card className="space-y-4">
      <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Monatliche Details</h2>
      <div className="overflow-x-auto">
        <table className="min-w-full text-sm">
          <thead>
            <tr className="border-b border-gray-200 dark:border-gray-700">
              <th className="text-left py-2 px-2">Monat</th>
              <th className="text-right py-2 px-2">PVGIS Prognose</th>
              <th className="text-right py-2 px-2">IST-Erzeugung</th>
              <th className="text-right py-2 px-2">Abweichung</th>
              <th className="text-right py-2 px-2">%</th>
              <th className="text-center py-2 px-2">Bewertung</th>
            </tr>
          </thead>
          <tbody>
            {vm.vergleichsDaten.map((d) => (
              <tr key={d.monat} className="border-b border-gray-100 dark:border-gray-800">
                <td className="py-2 px-2 font-medium">{d.monatName}</td>
                <td className="text-right py-2 px-2 text-yellow-600">{e(d.prognose)}</td>
                <td className="text-right py-2 px-2">
                  {d.ist > 0 ? <span className="text-green-600">{e(d.ist)}</span> : <span className="text-gray-400 dark:text-gray-500">-</span>}
                </td>
                <td className={`text-right py-2 px-2 ${d.abweichung >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                  {d.ist > 0 ? `${d.abweichung >= 0 ? '+' : ''}${e(d.abweichung)}` : '-'}
                </td>
                <td className={`text-right py-2 px-2 ${d.abweichungProzent >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                  {d.ist > 0 ? `${d.abweichungProzent >= 0 ? '+' : ''}${formatProzent(d.abweichungProzent).text}` : '-'}
                </td>
                <td className="text-center py-2 px-2">
                  {d.ist === 0 ? <span className="text-gray-400 dark:text-gray-500">Keine Daten</span>
                    : d.abweichungProzent >= 5 ? <span className="inline-flex items-center gap-1 text-green-600"><TrendingUp className="h-4 w-4" />Übertroffen</span>
                    : d.abweichungProzent >= -5 ? <span className="text-blue-600">Im Plan</span>
                    : d.abweichungProzent >= -15 ? <span className="text-yellow-600">Leicht unter Plan</span>
                    : <span className="inline-flex items-center gap-1 text-red-600"><TrendingDown className="h-4 w-4" />Unter Plan</span>}
                </td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr className="border-t-2 border-gray-300 dark:border-gray-600 font-bold">
              <td className="py-2 px-2">Gesamt</td>
              <td className="text-right py-2 px-2 text-yellow-600">{e(vm.jahresPrognose)}</td>
              <td className="text-right py-2 px-2 text-green-600">{e(vm.jahresIst)}</td>
              <td className={`text-right py-2 px-2 ${vm.jahresAbweichung >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                {vm.jahresAbweichung >= 0 ? '+' : ''}{e(vm.jahresAbweichung)}
              </td>
              <td className={`text-right py-2 px-2 ${vm.jahresAbweichungProzent >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                {vm.jahresAbweichungProzent >= 0 ? '+' : ''}{formatProzent(vm.jahresAbweichungProzent).text}
              </td>
              <td></td>
            </tr>
          </tfoot>
        </table>
      </div>
    </Card>
  )
}

/** Interpretations-Hilfe (Bewertungs-Schwellen erklärt). */
export function PvgisErklaerung() {
  return (
    <div className="bg-purple-50 dark:bg-purple-900/20 rounded-lg p-4">
      <h3 className="font-medium text-purple-700 dark:text-purple-300 mb-2">Interpretation der Abweichungen</h3>
      <ul className="text-sm text-purple-600 dark:text-purple-400 space-y-1 list-disc list-inside">
        <li><strong>Übertroffen (&gt;5 %):</strong> Die Anlage produziert mehr als erwartet — sehr gut!</li>
        <li><strong>Im Plan (±5 %):</strong> Die Anlage entspricht den Erwartungen von PVGIS.</li>
        <li><strong>Leicht unter Plan (−5 % bis −15 %):</strong> Kleinere Abweichungen, z. B. durch lokale Wetterbedingungen.</li>
        <li><strong>Unter Plan (&lt;−15 %):</strong> Deutliche Minderleistung — Verschattung, Verschmutzung oder technische Probleme prüfen.</li>
      </ul>
      <p className="text-xs text-purple-500 dark:text-purple-400 mt-3">
        Hinweis: PVGIS basiert auf langjährigen Mittelwerten. Einzelne Monate können stark abweichen.
      </p>
    </div>
  )
}
