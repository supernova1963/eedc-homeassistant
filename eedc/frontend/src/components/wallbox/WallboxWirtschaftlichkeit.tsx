/**
 * WallboxWirtschaftlichkeit — Kostenvergleich Heimladung vs. extern + ROI-Erklärung
 * + Amortisation (IST-`WallboxDashboard` UND IA-v4-Hub-Block „Wirtschaftlichkeit";
 * eine Code-Wahrheit). Wallbox-Statistik ist aus E-Auto-Ladedaten abgeleitet.
 */
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from 'recharts'
import ChartTooltip from '../ui/ChartTooltip'
import { GELD_COLORS } from '../../lib'
import type { WallboxDashboardResponse } from '../../api/investitionen'
import type { Investition } from '../../types'

type Zusammenfassung = WallboxDashboardResponse['zusammenfassung']

export function WallboxWirtschaftlichkeit({ zusammenfassung: z, investition }: {
  zusammenfassung: Zusammenfassung; investition: Investition
}) {
  const kostenVergleichData = [
    { name: 'Heimladung (tatsächlich)', value: z.heim_kosten_euro || 0, fill: GELD_COLORS.ersparnis },
    { name: 'Heimladung (als extern)', value: z.heim_als_extern_kosten_euro || 0, fill: GELD_COLORS.kosten },
  ]
  const anschaffung = investition.anschaffungskosten_gesamt
  const jahresErsparnis = z.anzahl_monate && z.anzahl_monate > 0
    ? ((z.ersparnis_vs_extern_euro || 0) / z.anzahl_monate * 12)
    : 0

  return (
    <div className="space-y-4">
      {/* Kostenvergleich */}
      <div>
        <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">Heimladung vs. externe Preise</h4>
        <div className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={kostenVergleichData} layout="vertical">
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis type="number" tickFormatter={(v) => `${v}€`} />
              <YAxis type="category" dataKey="name" width={150} />
              <Tooltip content={<ChartTooltip unit="€" decimals={2} />} />
              <Legend />
              <Bar dataKey="value" name="Kosten" />
            </BarChart>
          </ResponsiveContainer>
        </div>
        <div className="text-center mt-1">
          <span className="text-lg font-semibold text-green-600 dark:text-green-400">
            Ersparnis durch Wallbox: {(z.ersparnis_vs_extern_euro || 0).toFixed(2)} €
          </span>
        </div>
      </div>

      {/* ROI-Erklärung */}
      <div className="bg-purple-50 dark:bg-purple-900/20 rounded-lg p-4 space-y-2">
        <p className="text-sm font-medium text-purple-700 dark:text-purple-300">Wallbox-ROI erklärt</p>
        <p className="text-sm text-purple-600 dark:text-purple-400">
          Die Ersparnis errechnet sich aus dem Unterschied zwischen Heimladen und externem Laden:
        </p>
        <ul className="text-sm text-purple-600 dark:text-purple-400 list-disc list-inside">
          <li>PV-Ladung zuhause: kostenlos ({(z.ladung_pv_kwh || 0).toFixed(0)} kWh)</li>
          <li>Netz-Ladung zuhause: Haushaltsstrom ({(z.ladung_netz_kwh || 0).toFixed(0)} kWh = {(z.heim_kosten_euro || 0).toFixed(2)} €)</li>
          <li>Vergleichspreis extern: {(z.extern_preis_kwh_euro || 0.50).toFixed(2)} €/kWh</li>
        </ul>
        {(z.extern_ladung_kwh || 0) > 0 && (
          <p className="text-sm text-purple-600 dark:text-purple-400">
            Tatsächliche externe Ladung: {(z.extern_ladung_kwh || 0).toFixed(0)} kWh für {(z.extern_kosten_euro || 0).toFixed(2)} €
          </p>
        )}
      </div>

      {/* Amortisation (nur mit Anschaffungskosten) */}
      {anschaffung != null && anschaffung > 0 && (
        <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
          <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-4">
            <p className="text-sm text-gray-500 dark:text-gray-400">Anschaffungskosten</p>
            <p className="text-2xl font-bold text-gray-900 dark:text-white">{anschaffung.toLocaleString('de-DE')} €</p>
          </div>
          <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-4">
            <p className="text-sm text-gray-500 dark:text-gray-400">Ersparnis/Jahr (hochgerechnet)</p>
            <p className="text-2xl font-bold text-green-600 dark:text-green-400">{jahresErsparnis.toFixed(0)} €</p>
          </div>
          <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-4">
            <p className="text-sm text-gray-500 dark:text-gray-400">Amortisation (ca.)</p>
            <p className="text-2xl font-bold text-blue-600 dark:text-blue-400">
              {jahresErsparnis <= 0 ? '∞' : `${(anschaffung / jahresErsparnis).toFixed(1)} Jahre`}
            </p>
          </div>
        </div>
      )}
    </div>
  )
}
