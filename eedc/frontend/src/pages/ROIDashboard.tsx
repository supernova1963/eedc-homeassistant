/**
 * ROI-Dashboard - Wirtschaftlichkeitsanalyse aller Investitionen
 */

import { useState, useEffect, useMemo } from 'react'
import {
  TrendingUp,
  Clock,
  Leaf,
  PiggyBank,
  Car,
  Flame,
  Battery,
  Plug,
  Settings2,
  Sun,
  LayoutGrid,
} from 'lucide-react'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  LineChart,
  Line,
} from 'recharts'
import { Card, Alert, LoadingSpinner, EmptyState, FormelTooltip, fmtCalc } from '../components/ui'
import { useAnlagen, useAktuellerStrompreis } from '../hooks'
import { investitionenApi, type ROIDashboardResponse } from '../api'

const typIcons: Record<string, React.ElementType> = {
  'e-auto': Car,
  'waermepumpe': Flame,
  'speicher': Battery,
  'wallbox': Plug,
  'wechselrichter': Settings2,
  'pv-module': Sun,
  'balkonkraftwerk': LayoutGrid,
  'sonstiges': Settings2,
}

const typColors: Record<string, string> = {
  'e-auto': '#3b82f6',
  'waermepumpe': '#f97316',
  'speicher': '#22c55e',
  'wallbox': '#a855f7',
  'wechselrichter': '#06b6d4',
  'pv-module': '#eab308',
  'balkonkraftwerk': '#14b8a6',
  'sonstiges': '#6b7280',
}

const typLabels: Record<string, string> = {
  'e-auto': 'E-Auto',
  'waermepumpe': 'Wärmepumpe',
  'speicher': 'Speicher',
  'wallbox': 'Wallbox',
  'wechselrichter': 'Wechselrichter',
  'pv-module': 'PV-Module',
  'balkonkraftwerk': 'Balkonkraftwerk',
  'sonstiges': 'Sonstiges',
}

export default function ROIDashboard() {
  const { anlagen, loading: anlagenLoading } = useAnlagen()
  const [selectedAnlageId, setSelectedAnlageId] = useState<number | null>(null)
  const [roiData, setRoiData] = useState<ROIDashboardResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Anpassbare Parameter
  const [strompreis, setStrompreis] = useState<number>(30)
  const [einspeiseverguetung, setEinspeiseverguetung] = useState<number>(8.2)
  const [benzinpreis, setBenzinpreis] = useState<number>(1.85)

  const anlageId = selectedAnlageId ?? anlagen[0]?.id
  const { strompreis: aktuellerStrompreis } = useAktuellerStrompreis(anlageId ?? null)

  // Strompreis aus DB übernehmen wenn verfügbar
  useEffect(() => {
    if (aktuellerStrompreis) {
      setStrompreis(aktuellerStrompreis.netzbezug_arbeitspreis_cent_kwh)
      setEinspeiseverguetung(aktuellerStrompreis.einspeiseverguetung_cent_kwh)
    }
  }, [aktuellerStrompreis])

  // ROI-Daten laden
  useEffect(() => {
    if (!anlageId) return

    const loadROI = async () => {
      try {
        setLoading(true)
        setError(null)
        const data = await investitionenApi.getROIDashboard(
          anlageId,
          strompreis,
          einspeiseverguetung,
          benzinpreis
        )
        setRoiData(data)
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Fehler beim Laden der ROI-Daten')
      } finally {
        setLoading(false)
      }
    }

    loadROI()
  }, [anlageId, strompreis, einspeiseverguetung, benzinpreis])

  // Amortisations-Zeitreihe berechnen
  const amortisationData = useMemo(() => {
    if (!roiData || roiData.gesamt_relevante_kosten <= 0) return []

    const data = []
    let kumulierteEinsparung = 0
    const maxJahre = Math.min(
      Math.ceil((roiData.gesamt_amortisation_jahre ?? 20) * 1.5),
      30
    )

    for (let jahr = 0; jahr <= maxJahre; jahr++) {
      data.push({
        jahr,
        kumulierte_einsparung: Math.round(kumulierteEinsparung),
        investition: roiData.gesamt_relevante_kosten,
      })
      kumulierteEinsparung += roiData.gesamt_jahres_einsparung
    }

    return data
  }, [roiData])

  // Einsparungen nach Typ
  const einsparungenByTyp = useMemo(() => {
    if (!roiData) return []

    const grouped: Record<string, number> = {}
    roiData.berechnungen.forEach(b => {
      const typ = b.investition_typ
      grouped[typ] = (grouped[typ] || 0) + b.jahres_einsparung
    })

    return Object.entries(grouped)
      .map(([typ, value]) => ({
        name: typLabels[typ] || typ,
        value: Math.round(value),
        color: typColors[typ] || '#6b7280',
      }))
      .filter(d => d.value > 0)
  }, [roiData])

  // Einzelne Investitionen für Balkendiagramm
  const investitionenChart = useMemo(() => {
    if (!roiData) return []

    return roiData.berechnungen.map(b => ({
      name: b.investition_bezeichnung.length > 15
        ? b.investition_bezeichnung.substring(0, 15) + '...'
        : b.investition_bezeichnung,
      fullName: b.investition_bezeichnung,
      kosten: b.relevante_kosten,
      einsparung: b.jahres_einsparung,
      amortisation: b.amortisation_jahre ?? 0,
      typ: b.investition_typ,
      color: typColors[b.investition_typ] || '#6b7280',
    }))
  }, [roiData])

  if (anlagenLoading) {
    return <LoadingSpinner text="Lade Daten..." />
  }

  if (anlagen.length === 0) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
          ROI-Dashboard
        </h1>
        <Alert type="warning">
          Bitte lege zuerst eine PV-Anlage an.
        </Alert>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
            ROI-Dashboard
          </h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            Wirtschaftlichkeitsanalyse deiner Investitionen
          </p>
        </div>
        <div className="flex items-center gap-3">
          {anlagen.length > 1 && (
            <select
              value={anlageId ?? ''}
              onChange={(e) => setSelectedAnlageId(Number(e.target.value))}
              className="input w-auto"
            >
              {anlagen.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.anlagenname}
                </option>
              ))}
            </select>
          )}
        </div>
      </div>

      {error && (
        <Alert type="error" onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      {/* Parameter-Eingabe */}
      <Card>
        <div className="flex items-center gap-2 mb-4">
          <Settings2 className="h-5 w-5 text-gray-500" />
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
            Berechnungsparameter
          </h2>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              Strompreis (Cent/kWh)
            </label>
            <input
              type="number"
              step="0.1"
              value={strompreis}
              onChange={(e) => setStrompreis(Number(e.target.value))}
              className="input"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              Einspeisevergütung (Cent/kWh)
            </label>
            <input
              type="number"
              step="0.1"
              value={einspeiseverguetung}
              onChange={(e) => setEinspeiseverguetung(Number(e.target.value))}
              className="input"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              Benzinpreis (Euro/Liter)
            </label>
            <input
              type="number"
              step="0.01"
              value={benzinpreis}
              onChange={(e) => setBenzinpreis(Number(e.target.value))}
              className="input"
            />
          </div>
        </div>
      </Card>

      {loading && <LoadingSpinner text="Berechne ROI..." />}

      {!loading && roiData && roiData.berechnungen.length === 0 && (
        <EmptyState
          icon={PiggyBank}
          title="Keine aktiven Investitionen"
          description="Erfasse Investitionen auf der Investitionen-Seite, um deren Wirtschaftlichkeit zu analysieren."
        />
      )}

      {!loading && roiData && roiData.berechnungen.length > 0 && (
        <>
          {/* KPI Cards */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            <KPICard
              icon={PiggyBank}
              title="Gesamtinvestition"
              value={`${roiData.gesamt_investition.toLocaleString('de-DE')} €`}
              subtitle={`Relevant: ${roiData.gesamt_relevante_kosten.toLocaleString('de-DE')} €`}
              color="text-blue-500"
              bgColor="bg-blue-50 dark:bg-blue-900/20"
              formel="Σ Anschaffungskosten aller Investitionen"
              berechnung={`Relevant = Gesamt − Alternativkosten`}
              ergebnis={`= ${fmtCalc(roiData.gesamt_relevante_kosten, 0)} €`}
            />
            <KPICard
              icon={TrendingUp}
              title="Jährliche Einsparung"
              value={`${roiData.gesamt_jahres_einsparung.toLocaleString('de-DE')} €`}
              subtitle={roiData.gesamt_roi_prozent ? `ROI: ${roiData.gesamt_roi_prozent}%` : 'ROI: -'}
              color="text-green-500"
              bgColor="bg-green-50 dark:bg-green-900/20"
              formel="Σ Einsparungen aller Investitionen"
              berechnung={roiData.gesamt_relevante_kosten > 0 ? `ROI = Einsparung ÷ Kosten × 100` : undefined}
              ergebnis={roiData.gesamt_roi_prozent ? `= ${roiData.gesamt_roi_prozent}% ROI` : undefined}
            />
            <KPICard
              icon={Clock}
              title="Amortisation"
              value={roiData.gesamt_amortisation_jahre ? `${roiData.gesamt_amortisation_jahre} Jahre` : '-'}
              subtitle="Bis zur Kostendeckung"
              color="text-orange-500"
              bgColor="bg-orange-50 dark:bg-orange-900/20"
              formel="Relevante Kosten ÷ Jährliche Einsparung"
              berechnung={roiData.gesamt_jahres_einsparung > 0 ? `${fmtCalc(roiData.gesamt_relevante_kosten, 0)} € ÷ ${fmtCalc(roiData.gesamt_jahres_einsparung, 0)} €/Jahr` : undefined}
              ergebnis={roiData.gesamt_amortisation_jahre ? `= ${roiData.gesamt_amortisation_jahre} Jahre` : undefined}
            />
            <KPICard
              icon={Leaf}
              title="CO2-Einsparung"
              value={`${roiData.gesamt_co2_einsparung_kg.toLocaleString('de-DE')} kg`}
              subtitle="pro Jahr"
              color="text-emerald-500"
              bgColor="bg-emerald-50 dark:bg-emerald-900/20"
              formel="Σ CO2-Einsparungen aller Investitionen"
              berechnung="Je nach Investitionstyp unterschiedlich"
              ergebnis={`= ${fmtCalc(roiData.gesamt_co2_einsparung_kg / 1000, 2)} t CO2/Jahr`}
            />
          </div>

          {/* Charts */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Amortisations-Chart */}
            <Card>
              <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
                Amortisationsverlauf
              </h3>
              <div className="h-80">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={amortisationData}>
                    <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
                    <XAxis
                      dataKey="jahr"
                      label={{ value: 'Jahre', position: 'bottom' }}
                      tick={{ fontSize: 12 }}
                    />
                    <YAxis
                      tickFormatter={(v) => `${(v / 1000).toFixed(0)}k`}
                      tick={{ fontSize: 12 }}
                    />
                    <Tooltip
                      formatter={(value: number, name: string) => [
                        `${value.toLocaleString('de-DE')} €`,
                        name === 'kumulierte_einsparung' ? 'Kumulierte Einsparung' : 'Investition'
                      ]}
                      labelFormatter={(label) => `Jahr ${label}`}
                    />
                    <Legend
                      formatter={(value) =>
                        value === 'kumulierte_einsparung' ? 'Kumulierte Einsparung' : 'Investition'
                      }
                    />
                    <Line
                      type="monotone"
                      dataKey="kumulierte_einsparung"
                      stroke="#22c55e"
                      strokeWidth={2}
                      dot={false}
                    />
                    <Line
                      type="monotone"
                      dataKey="investition"
                      stroke="#ef4444"
                      strokeWidth={2}
                      strokeDasharray="5 5"
                      dot={false}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
              {roiData.gesamt_amortisation_jahre && (
                <p className="text-sm text-gray-500 dark:text-gray-400 mt-2 text-center">
                  Break-Even nach ca. {roiData.gesamt_amortisation_jahre} Jahren
                </p>
              )}
            </Card>

            {/* Einsparungen nach Typ */}
            <Card>
              <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
                Einsparungen nach Typ
              </h3>
              <div className="h-80">
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie
                      data={einsparungenByTyp}
                      dataKey="value"
                      nameKey="name"
                      cx="50%"
                      cy="50%"
                      outerRadius={100}
                      label={({ name, percent }) =>
                        `${name}: ${(percent * 100).toFixed(0)}%`
                      }
                      labelLine={true}
                    >
                      {einsparungenByTyp.map((entry, index) => (
                        <Cell key={`cell-${index}`} fill={entry.color} />
                      ))}
                    </Pie>
                    <Tooltip
                      formatter={(value: number) => [`${value.toLocaleString('de-DE')} €/Jahr`, 'Einsparung']}
                    />
                  </PieChart>
                </ResponsiveContainer>
              </div>
            </Card>
          </div>

          {/* Investitionen im Vergleich */}
          <Card>
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
              Investitionen im Vergleich
            </h3>
            <div className="h-80">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={investitionenChart} layout="vertical">
                  <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
                  <XAxis type="number" tickFormatter={(v) => `${v.toLocaleString('de-DE')}`} />
                  <YAxis dataKey="name" type="category" width={120} tick={{ fontSize: 11 }} />
                  <Tooltip
                    formatter={(value: number, name: string) => [
                      name === 'kosten'
                        ? `${value.toLocaleString('de-DE')} €`
                        : `${value.toLocaleString('de-DE')} €/Jahr`,
                      name === 'kosten' ? 'Relevante Kosten' : 'Jährliche Einsparung'
                    ]}
                  />
                  <Legend
                    formatter={(value) =>
                      value === 'kosten' ? 'Relevante Kosten (€)' : 'Jährliche Einsparung (€)'
                    }
                  />
                  <Bar dataKey="kosten" fill="#94a3b8" name="kosten" />
                  <Bar dataKey="einsparung" fill="#22c55e" name="einsparung" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </Card>

          {/* Detail-Tabelle */}
          <Card>
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
              Detailübersicht
            </h3>
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
                <thead>
                  <tr>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                      Investition
                    </th>
                    <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                      Kosten
                    </th>
                    <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                      Einsparung/Jahr
                    </th>
                    <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                      ROI
                    </th>
                    <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                      Amortisation
                    </th>
                    <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                      CO2
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
                  {roiData.berechnungen.map((b) => {
                    const Icon = typIcons[b.investition_typ] || Settings2
                    return (
                      <tr key={b.investition_id} className="hover:bg-gray-50 dark:hover:bg-gray-800">
                        <td className="px-4 py-3 whitespace-nowrap">
                          <div className="flex items-center gap-2">
                            <Icon
                              className="h-4 w-4"
                              style={{ color: typColors[b.investition_typ] }}
                            />
                            <div>
                              <p className="text-sm font-medium text-gray-900 dark:text-white">
                                {b.investition_bezeichnung}
                              </p>
                              <p className="text-xs text-gray-500 dark:text-gray-400">
                                {typLabels[b.investition_typ]}
                              </p>
                            </div>
                          </div>
                        </td>
                        <td className="px-4 py-3 whitespace-nowrap text-right">
                          <p className="text-sm text-gray-900 dark:text-white">
                            {b.relevante_kosten.toLocaleString('de-DE')} €
                          </p>
                          {b.anschaffungskosten_alternativ > 0 && (
                            <p className="text-xs text-gray-500 dark:text-gray-400">
                              ({b.anschaffungskosten.toLocaleString('de-DE')} € gesamt)
                            </p>
                          )}
                        </td>
                        <td className="px-4 py-3 whitespace-nowrap text-right text-sm text-green-600 dark:text-green-400 font-medium">
                          {b.jahres_einsparung.toLocaleString('de-DE')} €
                        </td>
                        <td className="px-4 py-3 whitespace-nowrap text-right text-sm">
                          {b.roi_prozent ? (
                            <span className={b.roi_prozent >= 10 ? 'text-green-600 dark:text-green-400' : 'text-gray-900 dark:text-white'}>
                              {b.roi_prozent}%
                            </span>
                          ) : (
                            <span className="text-gray-400">-</span>
                          )}
                        </td>
                        <td className="px-4 py-3 whitespace-nowrap text-right text-sm">
                          {b.amortisation_jahre ? (
                            <span className={b.amortisation_jahre <= 10 ? 'text-green-600 dark:text-green-400' : 'text-orange-500'}>
                              {b.amortisation_jahre} J.
                            </span>
                          ) : (
                            <span className="text-gray-400">-</span>
                          )}
                        </td>
                        <td className="px-4 py-3 whitespace-nowrap text-right text-sm text-emerald-600 dark:text-emerald-400">
                          {b.co2_einsparung_kg ? `${b.co2_einsparung_kg.toLocaleString('de-DE')} kg` : '-'}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
                <tfoot>
                  <tr className="bg-gray-50 dark:bg-gray-800 font-semibold">
                    <td className="px-4 py-3 text-sm text-gray-900 dark:text-white">
                      Gesamt
                    </td>
                    <td className="px-4 py-3 text-right text-sm text-gray-900 dark:text-white">
                      {roiData.gesamt_relevante_kosten.toLocaleString('de-DE')} €
                    </td>
                    <td className="px-4 py-3 text-right text-sm text-green-600 dark:text-green-400">
                      {roiData.gesamt_jahres_einsparung.toLocaleString('de-DE')} €
                    </td>
                    <td className="px-4 py-3 text-right text-sm text-gray-900 dark:text-white">
                      {roiData.gesamt_roi_prozent ? `${roiData.gesamt_roi_prozent}%` : '-'}
                    </td>
                    <td className="px-4 py-3 text-right text-sm text-gray-900 dark:text-white">
                      {roiData.gesamt_amortisation_jahre ? `${roiData.gesamt_amortisation_jahre} J.` : '-'}
                    </td>
                    <td className="px-4 py-3 text-right text-sm text-emerald-600 dark:text-emerald-400">
                      {roiData.gesamt_co2_einsparung_kg.toLocaleString('de-DE')} kg
                    </td>
                  </tr>
                </tfoot>
              </table>
            </div>
          </Card>

          {/* Hinweis */}
          <Alert type="info">
            <strong>Hinweis:</strong> Die Berechnungen sind Prognosen basierend auf den eingegebenen Parametern.
            Die tatsächlichen Einsparungen können je nach Nutzungsverhalten und Energiepreisen abweichen.
          </Alert>
        </>
      )}
    </div>
  )
}

interface KPICardProps {
  icon: React.ElementType
  title: string
  value: string
  subtitle?: string
  color: string
  bgColor: string
  // Tooltip-Props
  formel?: string
  berechnung?: string
  ergebnis?: string
}

function KPICard({ icon: Icon, title, value, subtitle, color, bgColor, formel, berechnung, ergebnis }: KPICardProps) {
  const valueContent = (
    <span className="text-2xl font-bold text-gray-900 dark:text-white">{value}</span>
  )

  return (
    <Card>
      <div className="flex items-start gap-4">
        <div className={`p-3 rounded-lg ${bgColor}`}>
          <Icon className={`h-6 w-6 ${color}`} />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-sm text-gray-500 dark:text-gray-400">{title}</p>
          {formel ? (
            <FormelTooltip formel={formel} berechnung={berechnung} ergebnis={ergebnis}>
              {valueContent}
            </FormelTooltip>
          ) : (
            valueContent
          )}
          {subtitle && (
            <p className="text-sm text-gray-500 dark:text-gray-400">{subtitle}</p>
          )}
        </div>
      </div>
    </Card>
  )
}
