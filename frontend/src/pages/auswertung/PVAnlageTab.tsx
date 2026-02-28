/**
 * PV-Anlage Tab - String-Performance Analyse über Zeit
 *
 * Zeigt:
 * - SOLL-IST Vergleich pro String für ausgewähltes Jahr
 * - Performance-Entwicklung über mehrere Jahre
 * - Spezifischer Ertrag pro String
 */

import { useState, useEffect, useMemo } from 'react'
import {
  BarChart, Bar, LineChart, Line, ComposedChart,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer
} from 'recharts'
import { Sun, TrendingUp, TrendingDown, Download, AlertTriangle, GitCompare } from 'lucide-react'
import { Card, Button, LoadingSpinner, Alert, fmtCalc } from '../../components/ui'
import { exportToCSV } from '../../utils/export'
import { KPICard } from './KPICard'
import { cockpitApi, PVStringsResponse } from '../../api/cockpit'

const STRING_COLORS = ['#f59e0b', '#3b82f6', '#10b981', '#8b5cf6', '#06b6d4', '#ec4899']

interface PVAnlageTabProps {
  anlageId: number
  selectedYear: number | 'all'
  verfuegbareJahre: number[]
  zeitraumLabel?: string
}

export function PVAnlageTab({ anlageId, selectedYear, verfuegbareJahre, zeitraumLabel }: PVAnlageTabProps) {
  const [data, setData] = useState<PVStringsResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Für Jahresvergleich: Daten für alle Jahre laden
  const [multiYearData, setMultiYearData] = useState<Map<number, PVStringsResponse>>(new Map())


  // Daten für ein spezifisches Jahr oder alle Jahre laden
  useEffect(() => {
    const loadData = async () => {
      setLoading(true)
      setError(null)

      try {
        if (selectedYear === 'all') {
          // Alle Jahre laden und aggregieren
          const dataMap = new Map<number, PVStringsResponse>()
          for (const jahr of verfuegbareJahre) {
            try {
              const result = await cockpitApi.getPVStrings(anlageId, jahr)
              dataMap.set(jahr, result)
            } catch (err) {
              console.error(`Fehler beim Laden Jahr ${jahr}:`, err)
            }
          }
          setMultiYearData(dataMap)

          // Aggregieren: SOLL und IST über alle Jahre summieren
          if (dataMap.size > 0) {
            const firstYearData = dataMap.get(verfuegbareJahre[0])
            if (firstYearData) {
              // Aggregierte Daten erstellen
              const aggStrings = firstYearData.strings.map(s => {
                let totalPrognose = 0
                let totalIst = 0

                // Über alle Jahre summieren
                dataMap.forEach((yearData) => {
                  const stringData = yearData.strings.find(ys => ys.investition_id === s.investition_id)
                  if (stringData) {
                    totalPrognose += stringData.prognose_jahr_kwh
                    totalIst += stringData.ist_jahr_kwh
                  }
                })

                const abweichung = totalPrognose > 0 ? ((totalIst - totalPrognose) / totalPrognose) * 100 : null
                const perfRatio = totalPrognose > 0 ? totalIst / totalPrognose : null

                return {
                  ...s,
                  prognose_jahr_kwh: totalPrognose,
                  ist_jahr_kwh: totalIst,
                  abweichung_jahr_prozent: abweichung,
                  abweichung_jahr_kwh: totalIst - totalPrognose,
                  performance_ratio_jahr: perfRatio,
                  spezifischer_ertrag_kwh_kwp: s.leistung_kwp > 0 ? totalIst / s.leistung_kwp : null,
                  // Monatswerte aggregieren
                  monatswerte: s.monatswerte.map((m, mIdx) => {
                    let monthPrognose = 0
                    let monthIst = 0
                    dataMap.forEach((yearData) => {
                      const stringData = yearData.strings.find(ys => ys.investition_id === s.investition_id)
                      if (stringData && stringData.monatswerte[mIdx]) {
                        monthPrognose += stringData.monatswerte[mIdx].prognose_kwh
                        monthIst += stringData.monatswerte[mIdx].ist_kwh
                      }
                    })
                    return {
                      ...m,
                      prognose_kwh: monthPrognose,
                      ist_kwh: monthIst,
                    }
                  })
                }
              })

              // Gesamt aggregieren
              const totalPrognoseGesamt = aggStrings.reduce((sum, s) => sum + s.prognose_jahr_kwh, 0)
              const totalIstGesamt = aggStrings.reduce((sum, s) => sum + s.ist_jahr_kwh, 0)

              // Bester/Schlechtester String bestimmen
              const sortedByPerf = [...aggStrings].filter(s => s.performance_ratio_jahr !== null)
                .sort((a, b) => (b.performance_ratio_jahr || 0) - (a.performance_ratio_jahr || 0))

              const aggregated: PVStringsResponse = {
                ...firstYearData,
                strings: aggStrings,
                prognose_gesamt_kwh: totalPrognoseGesamt,
                ist_gesamt_kwh: totalIstGesamt,
                abweichung_gesamt_kwh: totalIstGesamt - totalPrognoseGesamt,
                abweichung_gesamt_prozent: totalPrognoseGesamt > 0
                  ? ((totalIstGesamt - totalPrognoseGesamt) / totalPrognoseGesamt) * 100
                  : null,
                bester_string: sortedByPerf[0]?.bezeichnung || null,
                schlechtester_string: sortedByPerf[sortedByPerf.length - 1]?.bezeichnung || null,
              }
              setData(aggregated)
            }
          }
        } else {
          // Einzelnes Jahr laden
          const result = await cockpitApi.getPVStrings(anlageId, selectedYear)
          setData(result)
        }
      } catch (err) {
        setError('Fehler beim Laden der String-Daten')
        console.error(err)
      } finally {
        setLoading(false)
      }
    }
    loadData()
  }, [anlageId, selectedYear, verfuegbareJahre])

  // Jahresvergleich Chart-Daten
  const jahresvergleichData = useMemo(() => {
    if (selectedYear !== 'all' || multiYearData.size === 0) return []

    return verfuegbareJahre.map(jahr => {
      const yearData = multiYearData.get(jahr)
      if (!yearData) return null

      const entry: Record<string, number | string> = {
        name: jahr.toString(),
        jahr
      }

      // Performance Ratio pro String
      yearData.strings.forEach((s) => {
        entry[s.bezeichnung] = s.performance_ratio_jahr
          ? Math.round(s.performance_ratio_jahr * 100)
          : 0
      })

      // Gesamt
      entry['Gesamt'] = yearData.abweichung_gesamt_prozent
        ? 100 + yearData.abweichung_gesamt_prozent
        : 100

      return entry
    }).filter(Boolean).reverse() // Ältestes Jahr zuerst
  }, [selectedYear, multiYearData, verfuegbareJahre])

  // CSV Export
  const handleExportCSV = () => {
    if (!data) return
    const headers = [
      'String', 'kWp', 'Ausrichtung', 'SOLL (kWh)', 'IST (kWh)',
      'Abweichung (%)', 'Performance Ratio', 'kWh/kWp'
    ]
    const rows = data.strings.map(s => [
      s.bezeichnung,
      s.leistung_kwp,
      s.ausrichtung || '-',
      s.prognose_jahr_kwh,
      s.ist_jahr_kwh,
      s.abweichung_jahr_prozent ?? '-',
      s.performance_ratio_jahr ? (s.performance_ratio_jahr * 100).toFixed(1) + '%' : '-',
      s.spezifischer_ertrag_kwh_kwp ?? '-'
    ])
    const exportName = selectedYear === 'all' ? 'alle_jahre' : selectedYear.toString()
    exportToCSV(headers, rows, `pv_strings_${exportName}.csv`)
  }

  if (loading) return <LoadingSpinner text="Lade PV-String Daten..." />

  if (error) {
    return <Alert type="error">{error}</Alert>
  }

  if (!data || data.strings.length === 0) {
    return (
      <Card className="text-center py-8">
        <Sun className="h-12 w-12 mx-auto text-gray-400 mb-4" />
        <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-2">
          Keine PV-Module gefunden
        </h3>
        <p className="text-gray-500 dark:text-gray-400">
          Bitte PV-Module unter Einstellungen → Investitionen anlegen.
        </p>
      </Card>
    )
  }

  if (!data.hat_prognose) {
    return (
      <Alert type="warning">
        <div className="flex items-center gap-2">
          <AlertTriangle className="h-4 w-4" />
          <span>
            Keine PVGIS-Prognose vorhanden. Bitte unter Einstellungen → PVGIS eine Prognose abrufen,
            um den SOLL-IST Vergleich zu nutzen.
          </span>
        </div>
      </Alert>
    )
  }

  // String-Daten sortiert nach Performance
  const stringsSortedByPerf = [...data.strings].sort((a, b) =>
    (b.performance_ratio_jahr || 0) - (a.performance_ratio_jahr || 0)
  )

  return (
    <div className="space-y-6">
      {/* Header mit Zeitraum und Export */}
      <div className="flex items-center justify-between">
        <p className="text-sm text-gray-500 dark:text-gray-400">
          <span className="font-medium text-gray-700 dark:text-gray-300">{zeitraumLabel}</span>
          {' '}&bull;{' '}{data.strings.length} Strings &bull; {data.anlagen_leistung_kwp.toFixed(1)} kWp
        </p>
        <Button variant="secondary" size="sm" onClick={handleExportCSV}>
          <Download className="h-4 w-4 mr-2" />
          CSV Export
        </Button>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <KPICard
          title="SOLL (Prognose)"
          value={(data.prognose_gesamt_kwh / 1000).toFixed(1)}
          unit="MWh"
          subtitle="PVGIS Jahresprognose"
          icon={Sun}
          color="text-blue-500"
          bgColor="bg-blue-50 dark:bg-blue-900/20"
          formel="Σ PVGIS-Prognose aller Strings"
          berechnung={data.strings.map(s => `${s.bezeichnung}: ${s.prognose_jahr_kwh.toFixed(0)} kWh`).join(' + ')}
          ergebnis={`= ${fmtCalc(data.prognose_gesamt_kwh, 0)} kWh`}
        />
        <KPICard
          title="IST (Erzeugt)"
          value={(data.ist_gesamt_kwh / 1000).toFixed(1)}
          unit="MWh"
          subtitle={zeitraumLabel}
          icon={TrendingUp}
          color="text-amber-500"
          bgColor="bg-amber-50 dark:bg-amber-900/20"
          formel="Σ Erzeugung aller Strings"
          berechnung={data.strings.map(s => `${s.bezeichnung}: ${s.ist_jahr_kwh.toFixed(0)} kWh`).join(' + ')}
          ergebnis={`= ${fmtCalc(data.ist_gesamt_kwh, 0)} kWh`}
        />
        <KPICard
          title="Abweichung"
          value={`${(data.abweichung_gesamt_prozent || 0) >= 0 ? '+' : ''}${(data.abweichung_gesamt_prozent || 0).toFixed(1)}`}
          unit="%"
          subtitle={`${data.abweichung_gesamt_kwh >= 0 ? '+' : ''}${data.abweichung_gesamt_kwh.toFixed(0)} kWh`}
          icon={(data.abweichung_gesamt_prozent || 0) >= 0 ? TrendingUp : TrendingDown}
          color={(data.abweichung_gesamt_prozent || 0) >= 0 ? 'text-green-500' : 'text-red-500'}
          bgColor={(data.abweichung_gesamt_prozent || 0) >= 0 ? 'bg-green-50 dark:bg-green-900/20' : 'bg-red-50 dark:bg-red-900/20'}
          formel="(IST - SOLL) ÷ SOLL × 100"
          berechnung={`(${fmtCalc(data.ist_gesamt_kwh, 0)} - ${fmtCalc(data.prognose_gesamt_kwh, 0)}) ÷ ${fmtCalc(data.prognose_gesamt_kwh, 0)} × 100`}
          ergebnis={`= ${fmtCalc(data.abweichung_gesamt_prozent || 0, 1)} %`}
        />
        <KPICard
          title="Spez. Ertrag Ø"
          value={(data.ist_gesamt_kwh / data.anlagen_leistung_kwp).toFixed(0)}
          unit="kWh/kWp"
          subtitle={zeitraumLabel}
          icon={GitCompare}
          color="text-purple-500"
          bgColor="bg-purple-50 dark:bg-purple-900/20"
          formel="IST-Erzeugung ÷ Anlagenleistung"
          berechnung={`${fmtCalc(data.ist_gesamt_kwh, 0)} kWh ÷ ${fmtCalc(data.anlagen_leistung_kwp, 1)} kWp`}
          ergebnis={`= ${fmtCalc(data.ist_gesamt_kwh / data.anlagen_leistung_kwp, 0)} kWh/kWp`}
        />
      </div>

      {/* Beste/Schlechteste Performance Badges */}
      {data.strings.length > 1 && (
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
      )}

      {/* Chart: SOLL vs IST pro String */}
      <Card>
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
          <GitCompare className="h-5 w-5 text-blue-500" />
          SOLL vs IST pro String
        </h3>
        <div className="h-72">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart
              data={data.strings.map((s, idx) => ({
                name: s.bezeichnung.length > 12 ? s.bezeichnung.slice(0, 12) + '...' : s.bezeichnung,
                SOLL: s.prognose_jahr_kwh,
                IST: s.ist_jahr_kwh,
                color: STRING_COLORS[idx % STRING_COLORS.length],
              }))}
              layout="vertical"
            >
              <CartesianGrid strokeDasharray="3 3" className="stroke-gray-200 dark:stroke-gray-700" />
              <XAxis type="number" unit=" kWh" />
              <YAxis type="category" dataKey="name" width={100} tick={{ fontSize: 11 }} />
              <Tooltip formatter={(value: number) => [`${value.toFixed(0)} kWh`, '']} />
              <Legend />
              <Bar dataKey="SOLL" fill="#3b82f6" name="SOLL (Prognose)" />
              <Bar dataKey="IST" fill="#f59e0b" name="IST (Erzeugt)" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </Card>

      {/* Chart: Monatsverlauf (aggregiert) */}
      <Card>
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
          Monatsverlauf SOLL vs IST {selectedYear === 'all' ? '(Summe aller Jahre)' : ''}
        </h3>
        <div className="h-72">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart
              data={data.strings[0]?.monatswerte.map((m, mIdx) => {
                const entry: Record<string, number | string> = {
                  name: m.monat_name,
                  SOLL: data.strings.reduce((sum, s) => sum + (s.monatswerte[mIdx]?.prognose_kwh || 0), 0),
                  IST: data.strings.reduce((sum, s) => sum + (s.monatswerte[mIdx]?.ist_kwh || 0), 0),
                }
                entry['Abweichung'] = (entry['IST'] as number) - (entry['SOLL'] as number)
                return entry
              }) || []}
            >
              <CartesianGrid strokeDasharray="3 3" className="stroke-gray-200 dark:stroke-gray-700" />
              <XAxis dataKey="name" tick={{ fontSize: 10 }} />
              <YAxis unit=" kWh" tick={{ fontSize: 11 }} />
              <Tooltip formatter={(value: number) => [`${value.toFixed(0)} kWh`, '']} />
              <Legend />
              <Bar dataKey="SOLL" fill="#3b82f6" name="SOLL" opacity={0.6} />
              <Bar dataKey="IST" fill="#f59e0b" name="IST" />
              <Line
                type="monotone"
                dataKey="Abweichung"
                stroke="#10b981"
                strokeWidth={2}
                dot={{ r: 3 }}
                name="Abweichung"
              />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      </Card>

      {/* Jahresvergleich (wenn "Alle Jahre" ausgewählt) */}
      {selectedYear === 'all' && jahresvergleichData.length > 1 && (
        <Card>
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
            Performance-Entwicklung über Jahre
          </h3>
          <div className="h-72">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={jahresvergleichData}>
                <CartesianGrid strokeDasharray="3 3" className="stroke-gray-200 dark:stroke-gray-700" />
                <XAxis dataKey="name" />
                <YAxis
                  unit="%"
                  domain={[80, 120]}
                  ticks={[80, 90, 100, 110, 120]}
                />
                <Tooltip formatter={(value: number) => [`${value}%`, '']} />
                <Legend />
                {data.strings.map((s, idx) => (
                  <Line
                    key={s.investition_id}
                    type="monotone"
                    dataKey={s.bezeichnung}
                    stroke={STRING_COLORS[idx % STRING_COLORS.length]}
                    strokeWidth={2}
                    dot={{ r: 4 }}
                  />
                ))}
                <Line
                  type="monotone"
                  dataKey="Gesamt"
                  stroke="#6b7280"
                  strokeWidth={3}
                  strokeDasharray="5 5"
                  dot={{ r: 4 }}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
          <p className="text-xs text-gray-500 mt-2 text-center">
            100% = Prognose erreicht • Werte über 100% = Überperformance
          </p>
        </Card>
      )}

      {/* Detail-Tabelle */}
      <Card>
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
          String-Details
        </h3>
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
                      <div
                        className="w-3 h-3 rounded-full"
                        style={{ backgroundColor: STRING_COLORS[data.strings.findIndex(x => x.investition_id === s.investition_id) % STRING_COLORS.length] }}
                      />
                      <span className="font-medium text-gray-900 dark:text-white">{s.bezeichnung}</span>
                    </div>
                    {s.wechselrichter_name && (
                      <p className="text-xs text-gray-500 ml-5">→ {s.wechselrichter_name}</p>
                    )}
                  </td>
                  <td className="px-3 py-3 text-right">{s.leistung_kwp.toFixed(1)}</td>
                  <td className="px-3 py-3">
                    {s.ausrichtung || '-'}
                    {s.neigung_grad && ` / ${s.neigung_grad}°`}
                  </td>
                  <td className="px-3 py-3 text-right text-blue-600">{s.prognose_jahr_kwh.toFixed(0)} kWh</td>
                  <td className="px-3 py-3 text-right text-amber-600 font-medium">{s.ist_jahr_kwh.toFixed(0)} kWh</td>
                  <td className={`px-3 py-3 text-right font-medium ${
                    (s.abweichung_jahr_prozent || 0) >= 0 ? 'text-green-600' : 'text-red-600'
                  }`}>
                    {(s.abweichung_jahr_prozent || 0) >= 0 ? '+' : ''}{s.abweichung_jahr_prozent?.toFixed(1) || 0}%
                  </td>
                  <td className="px-3 py-3 text-right text-purple-600">
                    {s.spezifischer_ertrag_kwh_kwp?.toFixed(0) || '-'}
                  </td>
                </tr>
              ))}
            </tbody>
            <tfoot className="bg-gray-100 dark:bg-gray-800 font-medium">
              <tr>
                <td className="px-3 py-2">Gesamt</td>
                <td className="px-3 py-2 text-right">{data.anlagen_leistung_kwp.toFixed(1)}</td>
                <td className="px-3 py-2">-</td>
                <td className="px-3 py-2 text-right text-blue-600">{data.prognose_gesamt_kwh.toFixed(0)} kWh</td>
                <td className="px-3 py-2 text-right text-amber-600">{data.ist_gesamt_kwh.toFixed(0)} kWh</td>
                <td className={`px-3 py-2 text-right ${
                  (data.abweichung_gesamt_prozent || 0) >= 0 ? 'text-green-600' : 'text-red-600'
                }`}>
                  {(data.abweichung_gesamt_prozent || 0) >= 0 ? '+' : ''}{data.abweichung_gesamt_prozent?.toFixed(1) || 0}%
                </td>
                <td className="px-3 py-2 text-right text-purple-600">
                  {(data.ist_gesamt_kwh / data.anlagen_leistung_kwp).toFixed(0)}
                </td>
              </tr>
            </tfoot>
          </table>
        </div>
      </Card>
    </div>
  )
}
