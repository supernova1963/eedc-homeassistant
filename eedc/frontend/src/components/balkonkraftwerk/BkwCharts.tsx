/**
 * Geteilte Balkonkraftwerk-Charts (IST-`BalkonkraftwerkDashboard` + IA-v4-Hub):
 * - {@link BkwErzeugungVerlauf}: Erzeugung/Monat (Eigenverbrauch + Einspeisung, Area)
 * - {@link BkwSpeicherVerlauf}: integrierter Speicher Ladung/Entladung pro Monat (Bar)
 * - {@link BkwMonatsTabelle}: Erzeugung · Eigenverbrauch · Einspeisung [· Speicher]
 * Eine Code-Wahrheit, kein Drift zwischen Dashboard und Hub.
 */
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, AreaChart, Area,
} from 'recharts'
import ChartTooltip from '../ui/ChartTooltip'
import { MONAT_KURZ, CHART_COLORS } from '../../lib'
import type { InvestitionMonatsdaten } from '../../api/investitionen'

export function prepBkwMonate(monatsdaten: InvestitionMonatsdaten[]) {
  return monatsdaten.map((md) => ({
    name: `${MONAT_KURZ[md.monat]} ${md.jahr.toString().slice(2)}`,
    erzeugung: md.verbrauch_daten.erzeugung_kwh || 0,
    eigenverbrauch: md.verbrauch_daten.eigenverbrauch_kwh || 0,
    einspeisung: md.verbrauch_daten.einspeisung_kwh || 0,
    speicher_ladung: md.verbrauch_daten.speicher_ladung_kwh || 0,
    speicher_entladung: md.verbrauch_daten.speicher_entladung_kwh || 0,
  }))
}

/** Erzeugung pro Monat (Eigenverbrauch + Einspeisung gestapelt). */
export function BkwErzeugungVerlauf({ monatsdaten }: { monatsdaten: InvestitionMonatsdaten[] }) {
  const data = prepBkwMonate(monatsdaten)
  return (
    <div className="h-64">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="name" fontSize={10} />
          <YAxis />
          <Tooltip content={<ChartTooltip />} />
          <Legend />
          <Area type="monotone" dataKey="eigenverbrauch" stackId="1" fill={CHART_COLORS.eigenverbrauch} stroke={CHART_COLORS.eigenverbrauch} name="Eigenverbrauch" />
          <Area type="monotone" dataKey="einspeisung" stackId="1" fill={CHART_COLORS.einspeisung} stroke={CHART_COLORS.einspeisung} name="Einspeisung" />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}

/** Integrierter Speicher: Ladung/Entladung pro Monat (Bar). */
export function BkwSpeicherVerlauf({ monatsdaten }: { monatsdaten: InvestitionMonatsdaten[] }) {
  const data = prepBkwMonate(monatsdaten)
  return (
    <div className="h-48">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="name" fontSize={10} />
          <YAxis />
          <Tooltip content={<ChartTooltip />} />
          <Legend />
          <Bar dataKey="speicher_ladung" fill={CHART_COLORS.speicherLadung} name="Ladung" />
          <Bar dataKey="speicher_entladung" fill={CHART_COLORS.speicherEntladung} name="Entladung" />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

/** Monatsdaten-Tabelle: Erzeugung · Eigenverbrauch · Einspeisung [· Speicher]. */
export function BkwMonatsTabelle({ monatsdaten, hatSpeicher }: { monatsdaten: InvestitionMonatsdaten[]; hatSpeicher?: boolean }) {
  const data = prepBkwMonate(monatsdaten)
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-sm">
        <thead>
          <tr className="border-b border-gray-200 dark:border-gray-700">
            <th className="text-left py-2 px-2">Monat</th>
            <th className="text-right py-2 px-2">Erzeugung</th>
            <th className="text-right py-2 px-2">Eigenverbrauch</th>
            <th className="text-right py-2 px-2">Einspeisung</th>
            {hatSpeicher && <>
              <th className="text-right py-2 px-2">Sp. Ladung</th>
              <th className="text-right py-2 px-2">Sp. Entl.</th>
            </>}
          </tr>
        </thead>
        <tbody>
          {data.map((md, idx) => (
            <tr key={idx} className="border-b border-gray-100 dark:border-gray-800">
              <td className="py-2 px-2">{md.name}</td>
              <td className="text-right py-2 px-2 text-yellow-600">{md.erzeugung.toFixed(1)}</td>
              <td className="text-right py-2 px-2 text-green-600">{md.eigenverbrauch.toFixed(1)}</td>
              <td className="text-right py-2 px-2 text-orange-600">{md.einspeisung.toFixed(1)}</td>
              {hatSpeicher && <>
                <td className="text-right py-2 px-2 text-purple-600">{md.speicher_ladung.toFixed(1)}</td>
                <td className="text-right py-2 px-2 text-purple-600">{md.speicher_entladung.toFixed(1)}</td>
              </>}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
