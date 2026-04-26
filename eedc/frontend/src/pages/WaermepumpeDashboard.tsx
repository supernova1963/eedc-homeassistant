/**
 * Wärmepumpe
 * Zeigt Statistiken: COP, Stromverbrauch, Heizenergie, Ersparnis vs. Gas/Öl
 */

import { Fragment, useState, useEffect } from 'react'
import { Flame, Zap, Leaf, TrendingUp, Thermometer } from 'lucide-react'
import { Card, LoadingSpinner, Alert, Select, KPICard } from '../components/ui'
import ChartTooltip from '../components/ui/ChartTooltip'
import { useSelectedAnlage } from '../hooks'
import type { Anlage } from '../types'
import { MONAT_KURZ } from '../lib'
import { investitionenApi } from '../api'
import type { WaermepumpeDashboardResponse } from '../api/investitionen'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
  PieChart, Pie, Cell, AreaChart, Area
} from 'recharts'

export default function WaermepumpeDashboard() {
  const { anlagen, selectedAnlageId, setSelectedAnlageId, loading: anlagenLoading } = useSelectedAnlage()
  const [dashboards, setDashboards] = useState<WaermepumpeDashboardResponse[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!selectedAnlageId) return

    const loadDashboard = async () => {
      setLoading(true)
      setError(null)
      try {
        const data = await investitionenApi.getWaermepumpeDashboard(selectedAnlageId)
        setDashboards(data)
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Fehler beim Laden')
      } finally {
        setLoading(false)
      }
    }

    loadDashboard()
  }, [selectedAnlageId])

  if (anlagenLoading) return <LoadingSpinner text="Lade..." />

  if (anlagen.length === 0) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Wärmepumpe</h1>
        <Alert type="warning">Bitte zuerst eine Anlage anlegen.</Alert>
      </div>
    )
  }

  const showSelector = anlagen.length > 1
  const selectorProps = {
    anlagen,
    selectedAnlageId,
    setSelectedAnlageId,
  }

  return (
    <div className="space-y-6">
      {error && <Alert type="error">{error}</Alert>}

      {loading ? (
        <LoadingSpinner text="Lade Wärmepumpe Daten..." />
      ) : dashboards.length === 0 ? (
        <>
          <PlaceholderHeader showSelector={showSelector} {...selectorProps} />
          <Card>
            <div className="text-center py-8 text-gray-500 dark:text-gray-400">
              <Flame className="h-12 w-12 mx-auto mb-4 opacity-50" />
              <p>Keine Wärmepumpe für diese Anlage erfasst.</p>
              <p className="text-sm mt-2">Füge eine Wärmepumpe unter "Investitionen" hinzu.</p>
            </div>
          </Card>
        </>
      ) : (
        dashboards.map((dashboard, idx) => (
          <Fragment key={dashboard.investition.id}>
            {idx > 0 && <hr className="border-t border-gray-200 dark:border-gray-700" />}
            <WaermepumpeBlock
              dashboard={dashboard}
              showSelector={idx === 0 && showSelector}
              {...selectorProps}
            />
          </Fragment>
        ))
      )}
    </div>
  )
}

interface SelectorProps {
  anlagen: Anlage[]
  selectedAnlageId: number | undefined
  setSelectedAnlageId: (id: number) => void
  showSelector: boolean
}

function AnlageSelector({ anlagen, selectedAnlageId, setSelectedAnlageId, showSelector }: SelectorProps) {
  if (!showSelector) return null
  return (
    <Select
      compact
      value={selectedAnlageId?.toString() || ''}
      onChange={(e) => setSelectedAnlageId(parseInt(e.target.value))}
      options={anlagen.map(a => ({ value: a.id.toString(), label: a.anlagenname }))}
    />
  )
}

function PlaceholderHeader(props: SelectorProps) {
  return (
    <div className="flex items-center justify-between flex-wrap gap-4">
      <div className="flex items-center gap-3 min-w-0">
        <Flame className="h-8 w-8 text-orange-500 flex-shrink-0" />
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white truncate">Wärmepumpe</h1>
      </div>
      <AnlageSelector {...props} />
    </div>
  )
}

function WaermepumpeBlock({ dashboard, ...selectorProps }: { dashboard: WaermepumpeDashboardResponse } & SelectorProps) {
  const { investition, monatsdaten, zusammenfassung } = dashboard
  const z = zusammenfassung

  const hatGetrennteStrom = z.cop_heizen !== undefined

  const monthlyData = monatsdaten.map(md => {
    const d = md.verbrauch_daten
    const strom = d.stromverbrauch_kwh || 0
    const heizung = d.heizenergie_kwh || 0
    const warmwasser = d.warmwasser_kwh || 0
    const stromHeizen = d.strom_heizen_kwh || 0
    const stromWarmwasser = d.strom_warmwasser_kwh || 0
    return {
      name: `${MONAT_KURZ[md.monat]} ${md.jahr.toString().slice(2)}`,
      strom,
      strom_heizen: stromHeizen,
      strom_warmwasser: stromWarmwasser,
      heizung,
      warmwasser,
      cop: (heizung + warmwasser) / (strom || 1),
      cop_heizen: stromHeizen > 0 ? heizung / stromHeizen : null,
      cop_warmwasser: stromWarmwasser > 0 ? warmwasser / stromWarmwasser : null,
    }
  })

  // Monatsvergleich über Jahre: Jan/Feb/...Dez als Gruppen, je ein Balken pro Jahr
  const [vergleichModus, setVergleichModus] = useState<'cop' | 'strom'>('strom')
  const vergleichJahre = [...new Set(monatsdaten.map(md => md.jahr))].sort()
  const vergleichJahreColors = ['#f59e0b', '#22c55e', '#3b82f6', '#ef4444', '#8b5cf6']
  const vergleichData = Array.from({ length: 12 }, (_, i) => {
    const monat = i + 1
    const entry: Record<string, string | number | null> = { name: MONAT_KURZ[monat] }
    for (const jahr of vergleichJahre) {
      const md = monatsdaten.find(m => m.monat === monat && m.jahr === jahr)
      if (md) {
        const waerme = (md.verbrauch_daten.heizenergie_kwh || 0) + (md.verbrauch_daten.warmwasser_kwh || 0)
        const strom = md.verbrauch_daten.stromverbrauch_kwh || 0
        if (vergleichModus === 'cop') {
          entry[`val_${jahr}`] = strom > 0 ? Math.round(waerme / strom * 100) / 100 : null
        } else {
          entry[`val_${jahr}`] = strom > 0 ? Math.round(strom) : null
        }
      } else {
        entry[`val_${jahr}`] = null
      }
    }
    return entry
  })

  const waermePieData = [
    { name: 'Heizung', value: z.gesamt_heizenergie_kwh },
    { name: 'Warmwasser', value: z.gesamt_warmwasser_kwh },
  ]

  const kostenVergleichData = [
    { name: 'Wärmepumpe', value: z.wp_kosten_euro, fill: '#22c55e' },
    { name: 'Gas/Öl', value: z.alte_heizung_kosten_euro, fill: '#ef4444' },
  ]

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div className="flex items-center gap-3 min-w-0">
          <Flame className="h-8 w-8 text-orange-500 flex-shrink-0" />
          <div className="min-w-0">
            <h1 className="text-2xl font-bold text-gray-900 dark:text-white truncate">
              {investition.bezeichnung}
            </h1>
            <p className="text-sm text-gray-500 dark:text-gray-400">
              {z.anzahl_monate} Monate Daten
            </p>
          </div>
        </div>
        <AnlageSelector {...selectorProps} />
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3 sm:gap-4">
        <KPICard
          title="JAZ (gesamt)"
          value={z.durchschnitt_cop.toFixed(2)}
          icon={Thermometer}
          color="orange"
          formel="JAZ = Wärme ÷ Strom (Gesamtlaufzeit)"
          berechnung={`${z.gesamt_waerme_kwh.toFixed(0)} kWh ÷ ${z.gesamt_stromverbrauch_kwh.toFixed(0)} kWh`}
          ergebnis={`= ${z.durchschnitt_cop.toFixed(2)}`}
        />
        <KPICard
          title="Wärme erzeugt"
          value={(z.gesamt_waerme_kwh / 1000).toFixed(1)}
          unit="MWh"
          icon={Flame}
          color="red"
          formel="Wärme = Heizung + Warmwasser"
          berechnung={`${z.gesamt_heizenergie_kwh.toFixed(0)} + ${z.gesamt_warmwasser_kwh.toFixed(0)} kWh`}
          ergebnis={`= ${z.gesamt_waerme_kwh.toFixed(0)} kWh`}
        />
        <KPICard
          title="Strom verbraucht"
          value={(z.gesamt_stromverbrauch_kwh / 1000).toFixed(1)}
          unit="MWh"
          icon={Zap}
          color="yellow"
          formel="Σ Stromverbrauch WP"
          berechnung={`${z.gesamt_stromverbrauch_kwh.toFixed(0)} kWh`}
          ergebnis={`= ${(z.gesamt_stromverbrauch_kwh / 1000).toFixed(2)} MWh`}
        />
        <KPICard
          title="Ersparnis"
          value={z.ersparnis_euro.toFixed(0)}
          unit="€"
          icon={TrendingUp}
          color="green"
          trend={z.ersparnis_euro > 0 ? 'up' : undefined}
          formel="Ersparnis = Gas/Öl-Kosten − WP-Kosten"
          berechnung={`${z.alte_heizung_kosten_euro.toFixed(0)} € − ${z.wp_kosten_euro.toFixed(0)} €`}
          ergebnis={`= ${z.ersparnis_euro.toFixed(2)} €`}
        />
      </div>
      {/* Getrennte JAZ-Anzeige (wenn separate Strommessung) */}
      {hatGetrennteStrom && (
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3 sm:gap-4">
          <KPICard
            title="JAZ Heizen"
            value={z.cop_heizen?.toFixed(2) || '–'}
            icon={Thermometer}
            color="blue"
            formel="JAZ Heizen = Heizenergie ÷ Strom Heizen"
            berechnung={`${z.gesamt_heizung_getrennt_kwh?.toFixed(0)} kWh ÷ ${z.gesamt_strom_heizen_kwh?.toFixed(0)} kWh`}
            ergebnis={`= ${z.cop_heizen?.toFixed(2) || '–'}`}
          />
          <KPICard
            title="JAZ Warmwasser"
            value={(z.cop_warmwasser && z.cop_warmwasser > 0) ? z.cop_warmwasser.toFixed(2) : '–'}
            icon={Thermometer}
            color="purple"
            formel="JAZ WW = Warmwasser ÷ Strom WW"
            berechnung={`${z.gesamt_warmwasser_getrennt_kwh?.toFixed(0)} kWh ÷ ${z.gesamt_strom_warmwasser_kwh?.toFixed(0)} kWh`}
            ergebnis={(z.cop_warmwasser && z.cop_warmwasser > 0) ? `= ${z.cop_warmwasser.toFixed(2)}` : '– (keine Daten)'}
          />
          <KPICard
            title="Strom Heizen"
            value={(z.gesamt_strom_heizen_kwh! / 1000).toFixed(1)}
            unit="MWh"
            icon={Zap}
            color="yellow"
          />
          <KPICard
            title="Strom Warmwasser"
            value={z.gesamt_strom_warmwasser_kwh ? (z.gesamt_strom_warmwasser_kwh / 1000).toFixed(1) : '–'}
            unit={z.gesamt_strom_warmwasser_kwh ? 'MWh' : ''}
            icon={Zap}
            color="yellow"
          />
        </div>
      )}
      <p className="text-xs text-gray-400 dark:text-gray-500 italic -mt-2">
        JAZ = Jahresarbeitszahl über die gesamte Laufzeit ({z.anzahl_monate} Monate). Jahresweise Auswertung unter Auswertungen → Komponenten.
      </p>

      {/* Charts Row 1 */}
      <div className="grid md:grid-cols-2 gap-6">
        {/* Wärme-Verteilung */}
        <div>
          <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-4">
            Wärme-Verteilung
          </h3>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={waermePieData}
                  cx="50%"
                  cy="50%"
                  innerRadius={60}
                  outerRadius={80}
                  paddingAngle={5}
                  dataKey="value"
                  label={({ name, percent }) => `${name}: ${(percent * 100).toFixed(0)}%`}
                >
                  <Cell fill="#ef4444" />
                  <Cell fill="#3b82f6" />
                </Pie>
                <Tooltip content={<ChartTooltip unit="kWh" />} />
              </PieChart>
            </ResponsiveContainer>
          </div>
          <div className="flex justify-center gap-6 text-sm">
            <span className="flex items-center gap-2">
              <span className="w-3 h-3 rounded-full bg-red-500"></span>
              Heizung: {z.gesamt_heizenergie_kwh.toFixed(0)} kWh
            </span>
            <span className="flex items-center gap-2">
              <span className="w-3 h-3 rounded-full bg-blue-500"></span>
              Warmwasser: {z.gesamt_warmwasser_kwh.toFixed(0)} kWh
            </span>
          </div>
        </div>

        {/* Kostenvergleich */}
        <div>
          <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-4">
            Kostenvergleich WP vs. Gas/Öl
          </h3>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={kostenVergleichData} layout="vertical">
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis type="number" tickFormatter={(v) => `${v}€`} />
                <YAxis type="category" dataKey="name" width={110} />
                <Tooltip content={<ChartTooltip unit="€" decimals={2} />} />
                <Bar dataKey="value" />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <div className="text-center mt-2">
            <span className="text-lg font-semibold text-green-600 dark:text-green-400">
              Ersparnis: {z.ersparnis_euro.toFixed(2)} €
            </span>
          </div>
        </div>
      </div>

      {/* Charts Row 2 */}
      <div className="grid md:grid-cols-2 gap-6">
        {/* Wärme pro Monat */}
        <div>
          <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-4">
            Wärmeerzeugung pro Monat (kWh)
          </h3>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={monthlyData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="name" fontSize={10} />
                <YAxis />
                <Tooltip content={<ChartTooltip />} />
                <Legend />
                <Area type="monotone" dataKey="heizung" stackId="1" fill="#ef4444" stroke="#dc2626" name="Heizung" />
                <Area type="monotone" dataKey="warmwasser" stackId="1" fill="#3b82f6" stroke="#2563eb" name="Warmwasser" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

      </div>

      {/* Monatsvergleich über Jahre – volle Breite mit Toggle */}
      <div>
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300">
            {vergleichModus === 'cop' ? 'COP' : 'Stromverbrauch'} Monatsvergleich {vergleichJahre.length > 1 ? `(${vergleichJahre[0]}–${vergleichJahre[vergleichJahre.length - 1]})` : vergleichJahre[0]}
          </h3>
          <div className="flex rounded-lg border border-gray-300 dark:border-gray-600 text-sm overflow-hidden">
            <button
              onClick={() => setVergleichModus('strom')}
              className={`px-3 py-1 transition-colors ${vergleichModus === 'strom' ? 'bg-yellow-500 text-white' : 'text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700'}`}
            >
              Strom (kWh)
            </button>
            <button
              onClick={() => setVergleichModus('cop')}
              className={`px-3 py-1 transition-colors ${vergleichModus === 'cop' ? 'bg-orange-500 text-white' : 'text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700'}`}
            >
              COP
            </button>
          </div>
        </div>
        <div className="h-72">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={vergleichData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="name" fontSize={12} />
              <YAxis domain={vergleichModus === 'cop' ? [0, 6] : undefined} />
              <Tooltip content={<ChartTooltip formatter={(v) => vergleichModus === 'cop' ? v?.toFixed(2) : `${v} kWh`} />} />
              <Legend />
              {vergleichJahre.map((jahr, i) => (
                <Bar
                  key={jahr}
                  dataKey={`val_${jahr}`}
                  name={`${jahr}`}
                  fill={vergleichJahreColors[i % vergleichJahreColors.length]}
                />
              ))}
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* CO2 Info */}
      <div className="bg-green-50 dark:bg-green-900/20 rounded-lg p-4 flex items-center gap-4">
        <Leaf className="h-8 w-8 text-green-500" />
        <div>
          <p className="text-sm text-green-600 dark:text-green-400">CO₂ Ersparnis gegenüber fossiler Heizung</p>
          <p className="text-2xl font-bold text-green-700 dark:text-green-300">
            {z.co2_ersparnis_kg.toFixed(0)} kg
          </p>
        </div>
      </div>

      {/* Detail-Tabelle */}
      <details className="border-t border-gray-200 dark:border-gray-700 pt-4">
        <summary className="cursor-pointer text-sm text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white">
          Monatsdaten anzeigen
        </summary>
        <div className="mt-4 overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead>
              <tr className="border-b border-gray-200 dark:border-gray-700">
                <th className="text-left py-2 px-2">Monat</th>
                <th className="text-right py-2 px-2">Strom</th>
                <th className="text-right py-2 px-2">Heizung</th>
                <th className="text-right py-2 px-2">Warmwasser</th>
                <th className="text-right py-2 px-2">COP</th>
              </tr>
            </thead>
            <tbody>
              {monatsdaten.map((md) => {
                const strom = md.verbrauch_daten.stromverbrauch_kwh || 0
                const heiz = md.verbrauch_daten.heizenergie_kwh || 0
                const ww = md.verbrauch_daten.warmwasser_kwh || 0
                const cop = strom > 0 ? (heiz + ww) / strom : 0
                return (
                  <tr key={md.id} className="border-b border-gray-100 dark:border-gray-800">
                    <td className="py-2 px-2">{MONAT_KURZ[md.monat]} {md.jahr}</td>
                    <td className="text-right py-2 px-2">{strom.toFixed(0)}</td>
                    <td className="text-right py-2 px-2 text-red-600">{heiz.toFixed(0)}</td>
                    <td className="text-right py-2 px-2 text-blue-600">{ww.toFixed(0)}</td>
                    <td className="text-right py-2 px-2 text-orange-600">{cop.toFixed(2)}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </details>
    </div>
  )
}
