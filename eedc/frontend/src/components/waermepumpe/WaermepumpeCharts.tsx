/**
 * Geteilte Wärmepumpen-Charts (IST-`WaermepumpeDashboard` + IA-v4-Hub):
 * - {@link WaermepumpeMonatsverlauf}: Wärmeerzeugung/Monat (Heizung+Warmwasser, Area)
 * - {@link WaermepumpeKostenvergleich}: WP vs. Gas/Öl (Bar) + Ersparnis
 * - {@link WaermepumpeMonatsTabelle}: Strom · Heizung · Warmwasser · JAZ je Monat
 * Eine Code-Wahrheit, kein Drift zwischen Dashboard und Hub.
 */
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, AreaChart, Area,
} from 'recharts'
import ChartTooltip from '../ui/ChartTooltip'
import { MONAT_KURZ, CHART_COLORS, GELD_COLORS } from '../../lib'
import type { InvestitionMonatsdaten, WaermepumpeDashboardResponse } from '../../api/investitionen'

type Zusammenfassung = WaermepumpeDashboardResponse['zusammenfassung']

/** Wärmeerzeugung pro Monat (Heizung + Warmwasser gestapelt). */
export function WaermepumpeMonatsverlauf({ monatsdaten }: { monatsdaten: InvestitionMonatsdaten[] }) {
  const data = monatsdaten.map((md) => ({
    name: `${MONAT_KURZ[md.monat]} ${md.jahr.toString().slice(2)}`,
    heizung: md.verbrauch_daten.heizenergie_kwh || 0,
    warmwasser: md.verbrauch_daten.warmwasser_kwh || 0,
  }))
  return (
    <div className="h-64">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="name" fontSize={10} />
          <YAxis label={{ value: 'kWh', angle: -90, position: 'insideLeft', style: { textAnchor: 'middle' } }} />
          <Tooltip content={<ChartTooltip unit="kWh" />} />
          <Legend />
          <Area type="monotone" dataKey="heizung" stackId="1" fill={CHART_COLORS.wpWaerme} stroke={CHART_COLORS.wpWaerme} name="Heizung" />
          <Area type="monotone" dataKey="warmwasser" stackId="1" fill={CHART_COLORS.wpWarmwasser} stroke={CHART_COLORS.wpWarmwasser} name="Warmwasser" />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}

/** Kostenvergleich WP vs. Gas/Öl (horizontale Balken) + Ersparnis-Zeile. */
export function WaermepumpeKostenvergleich({ zusammenfassung: z }: { zusammenfassung: Zusammenfassung }) {
  const data = [
    { name: 'Wärmepumpe', value: z.wp_kosten_euro, fill: GELD_COLORS.ersparnis },
    { name: 'Gas/Öl', value: z.alte_heizung_kosten_euro, fill: GELD_COLORS.kosten },
  ]
  return (
    <div className="space-y-2">
      <div className="h-64">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} layout="vertical">
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis type="number" tickFormatter={(v) => `${v}€`} />
            <YAxis type="category" dataKey="name" width={110} />
            <Tooltip content={<ChartTooltip unit="€" decimals={2} />} />
            <Bar dataKey="value" />
          </BarChart>
        </ResponsiveContainer>
      </div>
      <div className="text-center">
        <span className="text-lg font-semibold text-green-600 dark:text-green-400">
          Ersparnis: {z.ersparnis_euro.toFixed(2)} €
        </span>
      </div>
    </div>
  )
}

/** Monatsdaten-Tabelle: Strom · Heizung · Warmwasser · JAZ je Monat. */
export function WaermepumpeMonatsTabelle({ monatsdaten }: { monatsdaten: InvestitionMonatsdaten[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-sm">
        <thead>
          <tr className="border-b border-gray-200 dark:border-gray-700">
            <th className="text-left py-2 px-2">Monat</th>
            <th className="text-right py-2 px-2">Strom (kWh)</th>
            <th className="text-right py-2 px-2">Heizung (kWh)</th>
            <th className="text-right py-2 px-2">Warmwasser (kWh)</th>
            <th className="text-right py-2 px-2">JAZ</th>
          </tr>
        </thead>
        <tbody>
          {monatsdaten.map((md) => {
            const strom = md.verbrauch_daten.stromverbrauch_kwh || 0
            const heiz = md.verbrauch_daten.heizenergie_kwh || 0
            const ww = md.verbrauch_daten.warmwasser_kwh || 0
            const cop = strom > 0 ? (heiz + ww) / strom : 0
            return (
              <tr key={md.id ?? `${md.jahr}-${md.monat}`} className="border-b border-gray-100 dark:border-gray-800">
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
  )
}
