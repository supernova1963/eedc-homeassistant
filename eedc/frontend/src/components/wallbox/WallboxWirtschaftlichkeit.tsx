/**
 * WallboxWirtschaftlichkeit — Kostenvergleich Heimladung vs. extern + ROI-Erklärung
 * + Amortisation (IST-`WallboxDashboard` UND IA-v4-Hub-Block „Wirtschaftlichkeit";
 * eine Code-Wahrheit). Wallbox-Statistik ist aus E-Auto-Ladedaten abgeleitet.
 */
import { useEffect, useMemo } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from 'recharts'
import ChartTooltip from '../ui/ChartTooltip'
import { ChartLegende } from '../ui'
import { Parkbar } from '../park'
import {
  GELD_COLORS, GELD_TEXT_CLASS, KOMPONENTEN_FARBEN, CHART_HOVER_CURSOR, fmtZahl,
  AMORTISATION_ANNAHME_MODELL_A, amortisationAnnahmeZeile,
} from '../../lib'
import type { WallboxDashboardResponse } from '../../api/investitionen'
import type { Investition } from '../../types'

type Zusammenfassung = WallboxDashboardResponse['zusammenfassung']

export function WallboxWirtschaftlichkeit({ zusammenfassung: z, investition, melde }: {
  zusammenfassung: Zusammenfassung; investition: Investition; melde?: (ids: string[]) => void
}) {
  const kostenVergleichData = [
    { name: 'Heimladung (tatsächlich)', value: z.heim_kosten_euro || 0, fill: GELD_COLORS.ersparnis },
    { name: 'Heimladung (als extern)', value: z.heim_als_extern_kosten_euro || 0, fill: GELD_COLORS.kosten },
  ]
  const anschaffung = investition.anschaffungskosten_gesamt
  const zeigeAmort = anschaffung != null && anschaffung > 0
  const jahresErsparnis = z.anzahl_monate && z.anzahl_monate > 0
    ? ((z.ersparnis_vs_extern_euro || 0) / z.anzahl_monate * 12)
    : 0
  // v4-Hub-Auto-Hide: Kostenvergleich + ROI-Box immer, Amortisation nur mit Anschaffung.
  const ids = useMemo(() => [
    'chart:wallbox-kostenvergleich', 'info:wallbox-roi', ...(zeigeAmort ? ['kpi:wallbox-amortisation'] : []),
  ], [zeigeAmort])
  useEffect(() => { melde?.(ids) }, [melde, ids])

  return (
    <div className="space-y-4">
      {/* Kostenvergleich (Chart + Ersparnis-Zeile, D1 = zusammen). */}
      <Parkbar id="chart:wallbox-kostenvergleich" titel="Heimladung vs. externe Preise">
      <div>
        <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">Heimladung vs. externe Preise</h4>
        <div className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={kostenVergleichData} layout="vertical">
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis type="number" tickFormatter={(v) => `${fmtZahl(v, 0)} €`} tick={{ fontSize: 10 }} /* achsen-allow: Wert-Achse waagerecht, Einheit/Format pro Tick (de-DE) */ />
              <YAxis type="category" dataKey="name" width={150} tick={{ fontSize: 10 }} /* achsen-allow: Kategorie-Namen (Heimladung tatsächlich/extern) */ />
              <Tooltip cursor={CHART_HOVER_CURSOR} content={<ChartTooltip unit="€" decimals={2} />} />
              <Legend content={<ChartLegende />} />
              <Bar dataKey="value" name="Kosten" />
            </BarChart>
          </ResponsiveContainer>
        </div>
        <div className="text-center mt-1">
          <span className={`text-lg font-semibold ${GELD_TEXT_CLASS.ersparnis}`}>
            Ersparnis durch Wallbox: {fmtZahl(z.ersparnis_vs_extern_euro || 0, 2)} €
          </span>
        </div>
      </div>
      </Parkbar>

      {/* ROI-Erklärung — Wallbox-Identität cyan (war violett, Audit-A/E). */}
      <Parkbar id="info:wallbox-roi" titel="Wallbox-ROI erklärt">
      <div className={`${KOMPONENTEN_FARBEN.wallbox.tint} rounded-lg p-4 space-y-2`}>
        <p className="text-sm font-medium text-cyan-700 dark:text-cyan-300">Wallbox-ROI erklärt</p>
        <p className="text-sm text-cyan-600 dark:text-cyan-400">
          Die Ersparnis errechnet sich aus dem Unterschied zwischen Heimladen und externem Laden:
        </p>
        <ul className="text-sm text-cyan-600 dark:text-cyan-400 list-disc list-inside">
          <li>PV-Ladung zuhause: kostenlos ({fmtZahl(z.ladung_pv_kwh || 0, 0)} kWh)</li>
          <li>Netz-Ladung zuhause: Haushaltsstrom ({fmtZahl(z.ladung_netz_kwh || 0, 0)} kWh = {fmtZahl(z.heim_kosten_euro || 0, 2)} €)</li>
          <li>Vergleichspreis extern: {fmtZahl(z.extern_preis_kwh_euro || 0.50, 2)} €/kWh</li>
        </ul>
        {(z.extern_ladung_kwh || 0) > 0 && (
          <p className="text-sm text-cyan-600 dark:text-cyan-400">
            Tatsächliche externe Ladung: {fmtZahl(z.extern_ladung_kwh || 0, 0)} kWh für {fmtZahl(z.extern_kosten_euro || 0, 2)} €
          </p>
        )}
      </div>
      </Parkbar>

      {/* Amortisation (nur mit Anschaffungskosten) */}
      {zeigeAmort && (
        <Parkbar id="kpi:wallbox-amortisation" titel="Amortisation">
        <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
          <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-4">
            <p className="text-sm text-gray-500 dark:text-gray-400">Anschaffungskosten</p>
            <p className="text-2xl font-bold text-gray-900 dark:text-white">{anschaffung!.toLocaleString('de-DE')} €</p>
          </div>
          <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-4">
            <p className="text-sm text-gray-500 dark:text-gray-400">Ersparnis/Jahr (hochgerechnet)</p>
            <p className={`text-2xl font-bold ${GELD_TEXT_CLASS.ersparnis}`}>{fmtZahl(jahresErsparnis, 0)} €</p>
          </div>
          <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-4">
            <p className="text-sm text-gray-500 dark:text-gray-400">Amortisation (ca.)</p>
            <p className="text-2xl font-bold text-blue-600 dark:text-blue-400">
              {jahresErsparnis <= 0 ? '∞' : `${fmtZahl(anschaffung! / jahresErsparnis, 1)} Jahre`}
            </p>
            {/* Konzept §5/§8-6: diese Dauer entsteht im Client aus
                Anschaffung ÷ Ersparnis — ohne Betriebskosten-Abzug, also
                immer Modell A. Deshalb der feste Text aus `lib`, nicht der
                datenabhängige des ROI-Dashboards. */}
            {jahresErsparnis > 0 && (
              <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                {amortisationAnnahmeZeile(AMORTISATION_ANNAHME_MODELL_A)}
              </p>
            )}
          </div>
        </div>
        </Parkbar>
      )}
    </div>
  )
}
