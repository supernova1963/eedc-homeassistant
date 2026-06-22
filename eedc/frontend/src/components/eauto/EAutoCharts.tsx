/**
 * Geteilte E-Auto-Charts (IST-`EAutoDashboard` + IA-v4-Hub):
 * - {@link EAutoKmVerlauf}: km pro Monat (Bar)
 * - {@link EAutoLadungVerlauf}: Ladung pro Monat nach Quelle (PV/Netz/Extern, gestapelt)
 * - {@link EAutoMonatsTabelle}: km · kWh · PV · Netz · V2H je Monat
 * - {@link EAutoKostenvergleich}: E-Auto (Strom) vs. Verbrenner (Benzin) + Ersparnis
 * Eine Code-Wahrheit, kein Drift zwischen Dashboard und Hub.
 */
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from 'recharts'
import ChartTooltip from '../ui/ChartTooltip'
import { MONAT_KURZ, LADEQUELLEN_FARBEN, GELD_COLORS, CHART_COLORS } from '../../lib'
import type { InvestitionMonatsdaten, EAutoDashboardResponse } from '../../api/investitionen'

type Zusammenfassung = EAutoDashboardResponse['zusammenfassung']

export function prepEAutoMonate(monatsdaten: InvestitionMonatsdaten[]) {
  return monatsdaten.map((md) => ({
    name: `${MONAT_KURZ[md.monat]} ${md.jahr.toString().slice(2)}`,
    km: md.verbrauch_daten.km_gefahren || 0,
    verbrauch: md.verbrauch_daten.verbrauch_kwh || 0,
    pv: md.verbrauch_daten.ladung_pv_kwh || 0,
    netz: md.verbrauch_daten.ladung_netz_kwh || 0,
    extern: md.verbrauch_daten.ladung_extern_kwh || 0,
    v2h: md.verbrauch_daten.v2h_entladung_kwh || 0,
  }))
}

/** Kilometer pro Monat (Bar). */
export function EAutoKmVerlauf({ monatsdaten }: { monatsdaten: InvestitionMonatsdaten[] }) {
  const data = prepEAutoMonate(monatsdaten)
  return (
    <div className="h-64">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="name" fontSize={10} />
          <YAxis />
          <Tooltip content={<ChartTooltip />} />
          <Bar dataKey="km" fill={CHART_COLORS.emobKm} name="km" />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

/** Ladung pro Monat nach Quelle (PV/Netz/Extern, gestapelt). */
export function EAutoLadungVerlauf({ monatsdaten }: { monatsdaten: InvestitionMonatsdaten[] }) {
  const data = prepEAutoMonate(monatsdaten)
  return (
    <div className="h-64">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="name" fontSize={10} />
          <YAxis />
          <Tooltip content={<ChartTooltip />} />
          <Legend />
          <Bar dataKey="pv" stackId="a" fill={LADEQUELLEN_FARBEN.pv} name="Heim: PV" />
          <Bar dataKey="netz" stackId="a" fill={LADEQUELLEN_FARBEN.netz} name="Heim: Netz" />
          <Bar dataKey="extern" stackId="a" fill={LADEQUELLEN_FARBEN.extern} name="Extern" />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

/** Kostenvergleich E-Auto (Strom) vs. Verbrenner (Benzin) + Ersparnis-Zeile. */
export function EAutoKostenvergleich({ zusammenfassung: z }: { zusammenfassung: Zusammenfassung }) {
  const data = [
    { name: 'E-Auto (Strom)', value: z.strom_kosten_gesamt_euro || 0, fill: GELD_COLORS.ersparnis },
    { name: 'Verbrenner (Benzin)', value: z.benzin_kosten_alternativ_euro || 0, fill: GELD_COLORS.kosten },
  ]
  return (
    <div className="space-y-2">
      <div className="h-64">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} layout="vertical">
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis type="number" tickFormatter={(v) => `${v}€`} />
            <YAxis type="category" dataKey="name" width={120} />
            <Tooltip content={<ChartTooltip unit="€" decimals={2} />} />
            <Bar dataKey="value" />
          </BarChart>
        </ResponsiveContainer>
      </div>
      <div className="text-center">
        <span className="text-lg font-semibold text-green-600 dark:text-green-400">
          Ersparnis: {(z.ersparnis_vs_benzin_euro || 0).toFixed(2)} €
        </span>
      </div>
    </div>
  )
}

/** Monatsdaten-Tabelle: km · kWh · PV · Netz · V2H je Monat. */
export function EAutoMonatsTabelle({ monatsdaten }: { monatsdaten: InvestitionMonatsdaten[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-sm">
        <thead>
          <tr className="border-b border-gray-200 dark:border-gray-700">
            <th className="text-left py-2 px-2">Monat</th>
            <th className="text-right py-2 px-2">km</th>
            <th className="text-right py-2 px-2">kWh</th>
            <th className="text-right py-2 px-2">PV</th>
            <th className="text-right py-2 px-2">Netz</th>
            <th className="text-right py-2 px-2">V2H</th>
          </tr>
        </thead>
        <tbody>
          {monatsdaten.map((md) => (
            <tr key={md.id ?? `${md.jahr}-${md.monat}`} className="border-b border-gray-100 dark:border-gray-800">
              <td className="py-2 px-2">{MONAT_KURZ[md.monat]} {md.jahr}</td>
              <td className="text-right py-2 px-2">{md.verbrauch_daten.km_gefahren || 0}</td>
              <td className="text-right py-2 px-2">{(md.verbrauch_daten.verbrauch_kwh || 0).toFixed(1)}</td>
              <td className="text-right py-2 px-2 text-green-600">{(md.verbrauch_daten.ladung_pv_kwh || 0).toFixed(1)}</td>
              <td className="text-right py-2 px-2 text-red-600">{(md.verbrauch_daten.ladung_netz_kwh || 0).toFixed(1)}</td>
              <td className="text-right py-2 px-2 text-purple-600">{(md.verbrauch_daten.v2h_entladung_kwh || 0).toFixed(1)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
