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
import { ChartLegende, Table, TableHead, TableBody } from '../ui'
import { ZELLE, KOPF_ZELLE } from '../ui/tabelleMasse'
import { MONAT_KURZ, CHART_COLORS, GELD_COLORS, GELD_TEXT_CLASS, CHART_HOVER_CURSOR, xAchse, yAchse, achsenEinheit, achsenTick, ACHSEN_MARGIN_TOP, fmtZahl } from '../../lib'
import { useLegendenToggle, useSchmaleAchse } from '../../hooks'
import type { InvestitionMonatsdaten, WaermepumpeDashboardResponse } from '../../api/investitionen'

type Zusammenfassung = WaermepumpeDashboardResponse['zusammenfassung']

/** Wärmeerzeugung pro Monat (Heizung + Warmwasser gestapelt). */
export function WaermepumpeMonatsverlauf({ monatsdaten }: { monatsdaten: InvestitionMonatsdaten[] }) {
  const schmal = useSchmaleAchse()
  const legende = useLegendenToggle()
  const data = monatsdaten.map((md) => ({
    name: `${MONAT_KURZ[md.monat]} ${md.jahr.toString().slice(2)}`,
    heizung: md.verbrauch_daten.heizenergie_kwh || 0,
    warmwasser: md.verbrauch_daten.warmwasser_kwh || 0,
  }))
  return (
    <div className="h-64">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: ACHSEN_MARGIN_TOP }}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="name" {...xAchse(schmal)} /* achsen-allow: Zeit-/Kategorie-Achse (Monat) */ />
          <YAxis label={achsenEinheit('kWh')} tickFormatter={achsenTick} {...yAchse(schmal)} />
          <Tooltip cursor={CHART_HOVER_CURSOR} content={<ChartTooltip unit="kWh" />} />
          <Legend content={<ChartLegende onItemClick={legende.onItemClick} />} />
          <Area type="monotone" dataKey="heizung" stackId="1" fill={CHART_COLORS.wpWaerme} stroke={CHART_COLORS.wpWaerme} name="Heizung" hide={legende.istVersteckt('heizung')} />
          <Area type="monotone" dataKey="warmwasser" stackId="1" fill={CHART_COLORS.wpWarmwasser} stroke={CHART_COLORS.wpWarmwasser} name="Warmwasser" hide={legende.istVersteckt('warmwasser')} />
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
            <XAxis type="number" tickFormatter={(v) => `${fmtZahl(v, 0)} €`} tick={{ fontSize: 10 }} /* achsen-allow: Wert-Achse waagerecht, Einheit/Format pro Tick (de-DE) */ />
            <YAxis type="category" dataKey="name" width={110} tick={{ fontSize: 10 }} /* achsen-allow: Kategorie-Namen (WP vs. Gas/Öl) */ />
            <Tooltip cursor={CHART_HOVER_CURSOR} content={<ChartTooltip unit="€" decimals={2} />} />
            <Bar dataKey="value" />
          </BarChart>
        </ResponsiveContainer>
      </div>
      <div className="text-center">
        <span className={`text-lg font-semibold ${GELD_TEXT_CLASS.ersparnis}`}>
          Ersparnis: {fmtZahl(z.ersparnis_euro, 2)} €
        </span>
      </div>
    </div>
  )
}

/** Monatsdaten-Tabelle: Strom · Heizung · Warmwasser · JAZ je Monat. */
export function WaermepumpeMonatsTabelle({ monatsdaten }: { monatsdaten: InvestitionMonatsdaten[] }) {
  return (
    <Table>
      <TableHead>
        <tr className="border-b border-gray-200 dark:border-gray-700">
          <th className={`${KOPF_ZELLE} text-left`}>Monat</th>
          <th className={`${KOPF_ZELLE} text-right`}>Strom (kWh)</th>
          <th className={`${KOPF_ZELLE} text-right`}>Heizung (kWh)</th>
          <th className={`${KOPF_ZELLE} text-right`}>Warmwasser (kWh)</th>
          <th className={`${KOPF_ZELLE} text-right`}>JAZ</th>
        </tr>
      </TableHead>
      <TableBody>
        {monatsdaten.map((md) => {
          const strom = md.verbrauch_daten.stromverbrauch_kwh || 0
          const heiz = md.verbrauch_daten.heizenergie_kwh || 0
          const ww = md.verbrauch_daten.warmwasser_kwh || 0
          const cop = strom > 0 ? (heiz + ww) / strom : 0
          return (
            <tr key={md.id ?? `${md.jahr}-${md.monat}`} className="border-b border-gray-100 dark:border-gray-800">
              <td className={ZELLE}>{MONAT_KURZ[md.monat]} {md.jahr}</td>
              <td className={`${ZELLE} text-right`}>{fmtZahl(strom, 0)}</td>
              {/* Heizung = WP-Rot, Warmwasser = blau (= CHART_COLORS.wpWaerme/wpWarmwasser; Gernot 2026-06-25 nach detLAN). */}
              <td className={`${ZELLE} text-right text-red-600`}>{fmtZahl(heiz, 0)}</td>
              <td className={`${ZELLE} text-right text-blue-600`}>{fmtZahl(ww, 0)}</td>
              <td className={`${ZELLE} text-right text-orange-600`}>{fmtZahl(cop, 2)}</td>
            </tr>
          )
        })}
      </TableBody>
    </Table>
  )
}
