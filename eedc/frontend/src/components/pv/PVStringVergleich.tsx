/**
 * PV-String-Vergleich Komponente
 * Zeigt SOLL vs IST Vergleich pro PV-Modul/String
 */

import { useState, useEffect, useMemo } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
  ComposedChart, Line, Cell
} from 'recharts'
import { Sun, TrendingUp, TrendingDown, AlertTriangle, ChevronDown, ChevronRight } from 'lucide-react'
import { Card, LoadingSpinner, Alert } from '../ui'
import { cockpitApi, PVStringsResponse } from '../../api/cockpit'

const STRING_COLORS = ['#f59e0b', '#3b82f6', '#10b981', '#8b5cf6', '#06b6d4', '#ec4899']

interface Props {
  anlageId: number
  jahr?: number
}

export function PVStringVergleich({ anlageId, jahr }: Props) {
  const [data, setData] = useState<PVStringsResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [expandedString, setExpandedString] = useState<number | null>(null)

  useEffect(() => {
    const loadData = async () => {
      setLoading(true)
      setError(null)
      try {
        const result = await cockpitApi.getPVStrings(anlageId, jahr)
        setData(result)
      } catch (err: unknown) {
        const errorDetail = err && typeof err === 'object' && 'detail' in err
          ? (err as { detail: string }).detail
          : 'Fehler beim Laden der String-Daten'
        setError(errorDetail)
        console.error('PVStringVergleich Fehler:', err)
      } finally {
        setLoading(false)
      }
    }
    loadData()
  }, [anlageId, jahr])

  // Chart-Daten für String-Vergleich
  const stringChartData = useMemo(() => {
    if (!data?.strings) return []
    return data.strings.map((s, idx) => ({
      name: s.bezeichnung.length > 15 ? s.bezeichnung.slice(0, 15) + '...' : s.bezeichnung,
      fullName: s.bezeichnung,
      Prognose: s.prognose_jahr_kwh,
      IST: s.ist_jahr_kwh,
      Performance: s.performance_ratio_jahr ? s.performance_ratio_jahr * 100 : null,
      color: STRING_COLORS[idx % STRING_COLORS.length],
    }))
  }, [data])

  // Monats-Chart für ausgewählten String
  const monatsChartData = useMemo(() => {
    if (!data?.strings || expandedString === null) return []
    const stringData = data.strings.find(s => s.investition_id === expandedString)
    if (!stringData) return []
    return stringData.monatswerte.map(m => ({
      name: m.monat_name,
      Prognose: m.prognose_kwh,
      IST: m.ist_kwh,
      Abweichung: m.abweichung_kwh,
    }))
  }, [data, expandedString])

  if (loading) return <LoadingSpinner text="Lade String-Vergleich..." />

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
            Keine PVGIS-Prognose vorhanden. Bitte unter Einstellungen → PVGIS eine Prognose abrufen.
          </span>
        </div>
      </Alert>
    )
  }

  const PerformanceIndicator = ({ ratio }: { ratio: number | null }) => {
    if (ratio === null) return <span className="text-gray-400">-</span>
    const pct = ratio * 100
    const isGood = pct >= 95
    const isBad = pct < 85
    return (
      <span className={`flex items-center gap-1 ${isGood ? 'text-green-600' : isBad ? 'text-red-600' : 'text-amber-600'}`}>
        {isGood ? <TrendingUp className="h-4 w-4" /> : isBad ? <TrendingDown className="h-4 w-4" /> : null}
        {pct.toFixed(0)}%
      </span>
    )
  }

  return (
    <div className="space-y-6">
      {/* Übersicht */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="bg-blue-50 dark:bg-blue-900/20 rounded-lg p-4">
          <p className="text-sm text-blue-600 dark:text-blue-400">SOLL (Prognose)</p>
          <p className="text-xl font-bold text-blue-700 dark:text-blue-300">
            {(data.prognose_gesamt_kwh / 1000).toFixed(1)} MWh
          </p>
        </div>
        <div className="bg-amber-50 dark:bg-amber-900/20 rounded-lg p-4">
          <p className="text-sm text-amber-600 dark:text-amber-400">IST (Erzeugt)</p>
          <p className="text-xl font-bold text-amber-700 dark:text-amber-300">
            {(data.ist_gesamt_kwh / 1000).toFixed(1)} MWh
          </p>
        </div>
        <div className={`rounded-lg p-4 ${
          (data.abweichung_gesamt_prozent || 0) >= 0
            ? 'bg-green-50 dark:bg-green-900/20'
            : 'bg-red-50 dark:bg-red-900/20'
        }`}>
          <p className="text-sm text-gray-600 dark:text-gray-400">Abweichung</p>
          <p className={`text-xl font-bold ${
            (data.abweichung_gesamt_prozent || 0) >= 0
              ? 'text-green-600 dark:text-green-400'
              : 'text-red-600 dark:text-red-400'
          }`}>
            {(data.abweichung_gesamt_prozent || 0) >= 0 ? '+' : ''}{data.abweichung_gesamt_prozent?.toFixed(1) || 0}%
          </p>
        </div>
        <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-4">
          <p className="text-sm text-gray-600 dark:text-gray-400">Anlagenleistung</p>
          <p className="text-xl font-bold text-gray-700 dark:text-gray-300">
            {data.anlagen_leistung_kwp.toFixed(1)} kWp
          </p>
        </div>
      </div>

      {/* Beste/Schlechteste Performance */}
      {(data.bester_string || data.schlechtester_string) && data.strings.length > 1 && (
        <div className="flex flex-wrap gap-4 text-sm">
          {data.bester_string && (
            <div className="flex items-center gap-2 bg-green-50 dark:bg-green-900/20 px-3 py-1 rounded-full">
              <TrendingUp className="h-4 w-4 text-green-600" />
              <span className="text-green-700 dark:text-green-300">
                Beste Performance: <strong>{data.bester_string}</strong>
              </span>
            </div>
          )}
          {data.schlechtester_string && data.schlechtester_string !== data.bester_string && (
            <div className="flex items-center gap-2 bg-red-50 dark:bg-red-900/20 px-3 py-1 rounded-full">
              <TrendingDown className="h-4 w-4 text-red-600" />
              <span className="text-red-700 dark:text-red-300">
                Schwächster: <strong>{data.schlechtester_string}</strong>
              </span>
            </div>
          )}
        </div>
      )}

      {/* String-Vergleich Chart */}
      <Card>
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
          String-Vergleich: SOLL vs IST
        </h3>
        <div className="h-72">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={stringChartData} layout="vertical">
              <CartesianGrid strokeDasharray="3 3" className="stroke-gray-200 dark:stroke-gray-700" />
              <XAxis type="number" unit=" kWh" />
              <YAxis type="category" dataKey="name" width={120} tick={{ fontSize: 11 }} />
              <Tooltip
                formatter={(value: number, name: string) => [`${value.toFixed(0)} kWh`, name]}
                labelFormatter={(label) => {
                  const item = stringChartData.find(d => d.name === label)
                  return item?.fullName || label
                }}
              />
              <Legend />
              <Bar dataKey="Prognose" fill="#3b82f6" name="SOLL (Prognose)" />
              <Bar dataKey="IST" name="IST (Erzeugt)">
                {stringChartData.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={entry.color} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </Card>

      {/* String-Detail-Tabelle */}
      <Card>
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
          Einzelne Strings / Module
        </h3>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 dark:bg-gray-800">
              <tr>
                <th className="px-3 py-2 text-left font-medium text-gray-500">String / Modul</th>
                <th className="px-3 py-2 text-right font-medium text-gray-500">kWp</th>
                <th className="px-3 py-2 text-left font-medium text-gray-500">Ausrichtung</th>
                <th className="px-3 py-2 text-right font-medium text-gray-500">SOLL</th>
                <th className="px-3 py-2 text-right font-medium text-gray-500">IST</th>
                <th className="px-3 py-2 text-right font-medium text-gray-500">Abw.</th>
                <th className="px-3 py-2 text-right font-medium text-gray-500">Performance</th>
                <th className="px-3 py-2 text-right font-medium text-gray-500">kWh/kWp</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
              {data.strings.map((s, idx) => (
                <>
                  <tr
                    key={s.investition_id}
                    className="hover:bg-gray-50 dark:hover:bg-gray-800 cursor-pointer"
                    onClick={() => setExpandedString(expandedString === s.investition_id ? null : s.investition_id)}
                  >
                    <td className="px-3 py-3">
                      <div className="flex items-center gap-2">
                        {expandedString === s.investition_id
                          ? <ChevronDown className="h-4 w-4 text-gray-400" />
                          : <ChevronRight className="h-4 w-4 text-gray-400" />
                        }
                        <div
                          className="w-3 h-3 rounded-full"
                          style={{ backgroundColor: STRING_COLORS[idx % STRING_COLORS.length] }}
                        />
                        <span className="font-medium text-gray-900 dark:text-white">{s.bezeichnung}</span>
                      </div>
                      {s.wechselrichter_name && (
                        <p className="text-xs text-gray-500 ml-9">→ {s.wechselrichter_name}</p>
                      )}
                    </td>
                    <td className="px-3 py-3 text-right text-gray-600 dark:text-gray-400">
                      {s.leistung_kwp.toFixed(1)}
                    </td>
                    <td className="px-3 py-3 text-gray-600 dark:text-gray-400">
                      {s.ausrichtung || '-'}
                      {s.neigung_grad && ` / ${s.neigung_grad}°`}
                    </td>
                    <td className="px-3 py-3 text-right text-blue-600 dark:text-blue-400">
                      {s.prognose_jahr_kwh.toFixed(0)} kWh
                    </td>
                    <td className="px-3 py-3 text-right font-medium" style={{ color: STRING_COLORS[idx % STRING_COLORS.length] }}>
                      {s.ist_jahr_kwh.toFixed(0)} kWh
                    </td>
                    <td className={`px-3 py-3 text-right ${
                      (s.abweichung_jahr_prozent || 0) >= 0 ? 'text-green-600' : 'text-red-600'
                    }`}>
                      {(s.abweichung_jahr_prozent || 0) >= 0 ? '+' : ''}{s.abweichung_jahr_prozent?.toFixed(1) || 0}%
                    </td>
                    <td className="px-3 py-3 text-right">
                      <PerformanceIndicator ratio={s.performance_ratio_jahr} />
                    </td>
                    <td className="px-3 py-3 text-right text-gray-600 dark:text-gray-400">
                      {s.spezifischer_ertrag_kwh_kwp?.toFixed(0) || '-'}
                    </td>
                  </tr>
                  {/* Expanded: Monats-Chart */}
                  {expandedString === s.investition_id && (
                    <tr key={`${s.investition_id}-detail`}>
                      <td colSpan={8} className="px-3 py-4 bg-gray-50 dark:bg-gray-800/50">
                        <h4 className="font-medium text-gray-900 dark:text-white mb-3">
                          Monatsverlauf: {s.bezeichnung}
                        </h4>
                        <div className="h-48">
                          <ResponsiveContainer width="100%" height="100%">
                            <ComposedChart data={monatsChartData}>
                              <CartesianGrid strokeDasharray="3 3" className="stroke-gray-200 dark:stroke-gray-700" />
                              <XAxis dataKey="name" tick={{ fontSize: 10 }} />
                              <YAxis unit=" kWh" tick={{ fontSize: 10 }} />
                              <Tooltip formatter={(value: number) => [`${value.toFixed(0)} kWh`, '']} />
                              <Legend />
                              <Bar dataKey="Prognose" fill="#3b82f6" name="SOLL" opacity={0.6} />
                              <Bar dataKey="IST" fill={STRING_COLORS[idx % STRING_COLORS.length]} name="IST" />
                              <Line
                                type="monotone"
                                dataKey="Abweichung"
                                stroke="#ef4444"
                                strokeWidth={2}
                                dot={{ r: 3 }}
                                name="Abweichung"
                              />
                            </ComposedChart>
                          </ResponsiveContainer>
                        </div>
                      </td>
                    </tr>
                  )}
                </>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  )
}
