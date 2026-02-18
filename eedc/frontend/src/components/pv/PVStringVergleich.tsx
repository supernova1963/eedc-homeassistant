/**
 * PV-String-Vergleich Komponente (Gesamtlaufzeit)
 *
 * Zeigt SOLL vs IST Vergleich pro PV-Modul/String über die gesamte Laufzeit:
 * 1. Jahresübersicht: SOLL vs IST pro Jahr für jeden String
 * 2. Saisonaler Vergleich: Jan-Dez Durchschnitt vs PVGIS-Prognose
 * 3. Tabelle mit Gesamtlaufzeit-Statistik pro String
 */

import { useState, useEffect, useMemo } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
  ComposedChart, Line, Area
} from 'recharts'
import { Sun, TrendingUp, TrendingDown, AlertTriangle, Calendar, BarChart3 } from 'lucide-react'
import { Card, LoadingSpinner, Alert } from '../ui'
import { cockpitApi, type PVStringsGesamtlaufzeitResponse } from '../../api/cockpit'

const STRING_COLORS = ['#f59e0b', '#3b82f6', '#10b981', '#8b5cf6', '#06b6d4', '#ec4899']

interface Props {
  anlageId: number
}

export function PVStringVergleich({ anlageId }: Props) {
  const [data, setData] = useState<PVStringsGesamtlaufzeitResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false

    const loadData = async () => {
      setLoading(true)
      setError(null)

      try {
        const result = await cockpitApi.getPVStringsGesamtlaufzeit(anlageId)
        if (!cancelled) {
          setData(result)
        }
      } catch (err: unknown) {
        if (!cancelled) {
          const errorMsg = err && typeof err === 'object' && 'detail' in err
            ? String((err as { detail: string }).detail)
            : 'Fehler beim Laden der String-Daten'
          setError(errorMsg)
          console.error('PVStringVergleich Fehler:', err)
        }
      } finally {
        if (!cancelled) {
          setLoading(false)
        }
      }
    }

    loadData()
    return () => { cancelled = true }
  }, [anlageId])

  // Chart-Daten: Jahresübersicht pro String
  const jahresChartData = useMemo(() => {
    if (!data?.strings || data.strings.length === 0) return []

    // Gruppiere nach Jahr
    const byYear: Record<number, Record<string, { soll: number; ist: number }>> = {}

    for (const s of data.strings) {
      for (const jw of s.jahreswerte) {
        if (!byYear[jw.jahr]) byYear[jw.jahr] = {}
        byYear[jw.jahr][s.bezeichnung] = {
          soll: jw.prognose_kwh,
          ist: jw.ist_kwh,
        }
      }
    }

    return Object.entries(byYear)
      .sort(([a], [b]) => Number(a) - Number(b))
      .map(([jahr, strings]) => {
        const row: Record<string, number | string> = { name: jahr }
        for (const s of data.strings) {
          const vals = strings[s.bezeichnung]
          if (vals) {
            row[`${s.bezeichnung} SOLL`] = Math.round(vals.soll)
            row[`${s.bezeichnung} IST`] = Math.round(vals.ist)
          }
        }
        return row
      })
  }, [data])

  // Chart-Daten: Saisonaler Vergleich (Jan-Dez)
  const saisonalChartData = useMemo(() => {
    if (!data?.saisonal_aggregiert) return []

    return data.saisonal_aggregiert.map(s => ({
      name: s.monat_name.slice(0, 3),
      SOLL: Math.round(s.prognose_kwh),
      'IST Ø': Math.round(s.ist_durchschnitt_kwh),
      'IST Summe': Math.round(s.ist_summe_kwh),
    }))
  }, [data])

  // Loading State
  if (loading) {
    return <LoadingSpinner text="Lade String-Vergleich..." />
  }

  // Error State
  if (error) {
    return <Alert type="error">{error}</Alert>
  }

  // No Data State
  if (!data || !data.strings || data.strings.length === 0) {
    return (
      <div className="text-center py-8">
        <Sun className="h-12 w-12 mx-auto text-gray-400 mb-4" />
        <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-2">
          Keine PV-Module gefunden
        </h3>
        <p className="text-gray-500 dark:text-gray-400">
          Bitte PV-Module unter Einstellungen → Investitionen anlegen.
        </p>
      </div>
    )
  }

  // No Prognosis State
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

  // Performance Badge
  const PerformanceBadge = ({ ratio }: { ratio: number | null | undefined }) => {
    if (ratio == null) return <span className="text-gray-400">-</span>
    const pct = ratio * 100
    const colorClass = pct >= 95 ? 'text-green-600' : pct < 85 ? 'text-red-600' : 'text-amber-600'
    const Icon = pct >= 95 ? TrendingUp : pct < 85 ? TrendingDown : null
    return (
      <span className={`flex items-center gap-1 ${colorClass}`}>
        {Icon && <Icon className="h-3 w-3" />}
        {pct.toFixed(0)}%
      </span>
    )
  }

  return (
    <div className="space-y-6">
      {/* KPI Übersicht */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="bg-blue-50 dark:bg-blue-900/20 rounded-lg p-4">
          <p className="text-sm text-blue-600 dark:text-blue-400">SOLL (Prognose)</p>
          <p className="text-xl font-bold text-blue-700 dark:text-blue-300">
            {(data.prognose_gesamt_kwh / 1000).toFixed(1)} MWh
          </p>
          <p className="text-xs text-blue-500">{data.anzahl_jahre} Jahre × PVGIS</p>
        </div>
        <div className="bg-amber-50 dark:bg-amber-900/20 rounded-lg p-4">
          <p className="text-sm text-amber-600 dark:text-amber-400">IST (Erzeugt)</p>
          <p className="text-xl font-bold text-amber-700 dark:text-amber-300">
            {(data.ist_gesamt_kwh / 1000).toFixed(1)} MWh
          </p>
          <p className="text-xs text-amber-500">{data.anzahl_monate} Monate erfasst</p>
        </div>
        <div className={`rounded-lg p-4 ${
          (data.abweichung_gesamt_prozent ?? 0) >= 0
            ? 'bg-green-50 dark:bg-green-900/20'
            : 'bg-red-50 dark:bg-red-900/20'
        }`}>
          <p className="text-sm text-gray-600 dark:text-gray-400">Abweichung</p>
          <p className={`text-xl font-bold ${
            (data.abweichung_gesamt_prozent ?? 0) >= 0
              ? 'text-green-600 dark:text-green-400'
              : 'text-red-600 dark:text-red-400'
          }`}>
            {(data.abweichung_gesamt_prozent ?? 0) >= 0 ? '+' : ''}
            {data.abweichung_gesamt_prozent?.toFixed(1) ?? '0'}%
          </p>
        </div>
        <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-4">
          <p className="text-sm text-gray-600 dark:text-gray-400">Zeitraum</p>
          <p className="text-xl font-bold text-gray-700 dark:text-gray-300">
            {data.erstes_jahr} - {data.letztes_jahr}
          </p>
          <p className="text-xs text-gray-500">{data.anlagen_leistung_kwp.toFixed(1)} kWp</p>
        </div>
      </div>

      {/* Beste/Schlechteste Performance */}
      {data.strings.length > 1 && (data.bester_string || data.schlechtester_string) && (
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

      {/* Jahresübersicht pro String */}
      {jahresChartData.length > 0 && (
        <Card>
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
            <Calendar className="h-5 w-5 text-blue-500" />
            SOLL vs IST pro Jahr
          </h3>
          <div className="h-72">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={jahresChartData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="name" />
                <YAxis unit=" kWh" />
                <Tooltip formatter={(value: number) => [`${value.toLocaleString()} kWh`]} />
                <Legend />
                {data.strings.map((s, idx) => (
                  <Bar
                    key={`${s.investition_id}-soll`}
                    dataKey={`${s.bezeichnung} SOLL`}
                    fill={STRING_COLORS[idx % STRING_COLORS.length]}
                    opacity={0.4}
                    name={`${s.bezeichnung} SOLL`}
                  />
                ))}
                {data.strings.map((s, idx) => (
                  <Bar
                    key={`${s.investition_id}-ist`}
                    dataKey={`${s.bezeichnung} IST`}
                    fill={STRING_COLORS[idx % STRING_COLORS.length]}
                    name={`${s.bezeichnung} IST`}
                  />
                ))}
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>
      )}

      {/* Saisonaler Vergleich */}
      {saisonalChartData.length > 0 && (
        <Card>
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
            <BarChart3 className="h-5 w-5 text-green-500" />
            Saisonaler Vergleich (Jan - Dez)
          </h3>
          <p className="text-sm text-gray-500 mb-4">
            Vergleicht die monatliche PVGIS-Prognose mit dem Durchschnitt der tatsächlichen Erzeugung über alle Jahre.
          </p>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={saisonalChartData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="name" />
                <YAxis unit=" kWh" />
                <Tooltip formatter={(value: number) => [`${value.toLocaleString()} kWh`]} />
                <Legend />
                <Area
                  type="monotone"
                  dataKey="SOLL"
                  fill="#3b82f6"
                  stroke="#3b82f6"
                  fillOpacity={0.2}
                  name="PVGIS Prognose"
                />
                <Line
                  type="monotone"
                  dataKey="IST Ø"
                  stroke="#f59e0b"
                  strokeWidth={3}
                  dot={{ r: 4 }}
                  name="IST Durchschnitt"
                />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </Card>
      )}

      {/* String-Detail-Tabelle */}
      <Card>
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
          Einzelne Strings / Module (Gesamtlaufzeit)
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
                <tr key={s.investition_id} className="hover:bg-gray-50 dark:hover:bg-gray-800">
                  <td className="px-3 py-3">
                    <div className="flex items-center gap-2">
                      <div
                        className="w-3 h-3 rounded-full flex-shrink-0"
                        style={{ backgroundColor: STRING_COLORS[idx % STRING_COLORS.length] }}
                      />
                      <span className="font-medium text-gray-900 dark:text-white">
                        {s.bezeichnung}
                      </span>
                    </div>
                    {s.wechselrichter_name && (
                      <p className="text-xs text-gray-500 ml-5">→ {s.wechselrichter_name}</p>
                    )}
                  </td>
                  <td className="px-3 py-3 text-right text-gray-600 dark:text-gray-400">
                    {s.leistung_kwp.toFixed(1)}
                  </td>
                  <td className="px-3 py-3 text-gray-600 dark:text-gray-400">
                    {s.ausrichtung || '-'}
                    {s.neigung_grad != null && ` / ${s.neigung_grad}°`}
                  </td>
                  <td className="px-3 py-3 text-right text-blue-600 dark:text-blue-400">
                    {(s.prognose_gesamt_kwh / 1000).toFixed(1)} MWh
                  </td>
                  <td className="px-3 py-3 text-right font-medium" style={{ color: STRING_COLORS[idx % STRING_COLORS.length] }}>
                    {(s.ist_gesamt_kwh / 1000).toFixed(1)} MWh
                  </td>
                  <td className={`px-3 py-3 text-right ${
                    (s.abweichung_gesamt_prozent ?? 0) >= 0 ? 'text-green-600' : 'text-red-600'
                  }`}>
                    {(s.abweichung_gesamt_prozent ?? 0) >= 0 ? '+' : ''}
                    {s.abweichung_gesamt_prozent?.toFixed(1) ?? '0'}%
                  </td>
                  <td className="px-3 py-3 text-right">
                    <PerformanceBadge ratio={s.performance_ratio_gesamt} />
                  </td>
                  <td className="px-3 py-3 text-right text-gray-600 dark:text-gray-400">
                    {s.spezifischer_ertrag_kwh_kwp?.toFixed(0) ?? '-'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  )
}
