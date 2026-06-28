/**
 * SpeicherVerlaufCharts — die drei IST-Speicher-Zeitreihen + Monats-Detailtabelle,
 * als EINE wiederverwendbare Komponente (IST-Dashboard `SpeicherDashboard` UND
 * IA-v4-Komponenten-Hub via `komponentenAnalyse`-Registry; keine zweite Kopie).
 *
 * - Ladung & Entladung pro Monat (Arbitrage-Stapel bei Netzladung)
 * - Vollzyklen pro Monat (Area)
 * - Effizienz gleitende 12 Monate (Line, carry-over-immun — vom Backend)
 * - Monatsdaten-Tabelle (Monat · Ladung · Entladung · Zyklen)
 *
 * `embed` rendert ohne eigene Überschrift/Abstände-Rahmen für den Hub-Block;
 * die Datenaufbereitung ist hier zentral, damit beide Seiten identisch rechnen.
 */
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
  AreaChart, Area, LineChart, Line,
} from 'recharts'
import ChartTooltip from '../ui/ChartTooltip'
import { ChartLegende } from '../ui'
import { MONAT_KURZ, CHART_COLORS, COLORS, CHART_HOVER_CURSOR, DATENROLLE, xAchse, yAchse, achsenEinheit, achsenTick, ACHSEN_MARGIN_TOP, fmtZahl } from '../../lib'
import { useSchmaleAchse } from '../../hooks'
import type { InvestitionMonatsdaten, SpeicherDashboardResponse } from '../../api/investitionen'

type Zusammenfassung = SpeicherDashboardResponse['zusammenfassung']
type EffizienzVerlauf = SpeicherDashboardResponse['effizienz_verlauf']

export interface SpeicherVerlaufProps {
  monatsdaten: InvestitionMonatsdaten[]
  zusammenfassung: Zusammenfassung
  effizienzVerlauf: EffizienzVerlauf
  embed?: boolean
}

/** Monatszeilen für die drei Charts + Tabelle (chronologisch, wie IST). */
export function prepSpeicherMonate(monatsdaten: InvestitionMonatsdaten[], z: Zusammenfassung) {
  return monatsdaten.map((md) => {
    const ladung = md.verbrauch_daten.ladung_kwh || 0
    const entladung = md.verbrauch_daten.entladung_kwh || 0
    const arbitrage = md.verbrauch_daten.speicher_ladung_netz_kwh || 0
    return {
      name: `${MONAT_KURZ[md.monat]} ${md.jahr.toString().slice(2)}`,
      ladung, entladung, arbitrage,
      pvLadung: ladung - arbitrage,
      zyklen: z.kapazitaet_kwh > 0 ? ladung / z.kapazitaet_kwh : 0,
    }
  })
}

function ChartKopf({ children }: { children: string }) {
  return <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-4">{children}</h3>
}

export function SpeicherVerlaufCharts({ monatsdaten, zusammenfassung: z, effizienzVerlauf, embed = false }: SpeicherVerlaufProps) {
  const schmal = useSchmaleAchse()
  const monthlyData = prepSpeicherMonate(monatsdaten, z)
  const effizienzData = effizienzVerlauf.map((e) => ({
    name: `${MONAT_KURZ[e.monat]} ${e.jahr.toString().slice(2)}`,
    effizienz: e.effizienz_prozent,
  }))
  const arbitrageAktiv = z.arbitrage_faehig && z.arbitrage_kwh > 0

  return (
    <div className={embed ? 'space-y-4' : 'space-y-6'}>
      <div className="grid md:grid-cols-2 gap-6">
        {/* Ladung/Entladung pro Monat (Arbitrage-Stapel bei Netzladung) */}
        <div>
          <ChartKopf>Ladung &amp; Entladung pro Monat</ChartKopf>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={monthlyData} margin={{ top: ACHSEN_MARGIN_TOP }}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="name" {...xAchse(schmal)} /* achsen-allow: Zeit-/Kategorie-Achse (Monat) */ />
                <YAxis tickFormatter={achsenTick} {...yAchse(schmal, 70)} label={achsenEinheit('kWh')} />
                <Tooltip cursor={CHART_HOVER_CURSOR} content={<ChartTooltip />} />
                <Legend content={<ChartLegende />} />
                {arbitrageAktiv ? (
                  <>
                    <Bar dataKey="pvLadung" stackId="ladung" fill={CHART_COLORS.speicherLadung} name="PV-Ladung" />
                    <Bar dataKey="arbitrage" stackId="ladung" fill={COLORS.grid} name="Netz-Ladung" />
                  </>
                ) : (
                  <Bar dataKey="ladung" fill={CHART_COLORS.speicherLadung} name="Ladung" />
                )}
                <Bar dataKey="entladung" fill={CHART_COLORS.speicherEntladung} name="Entladung" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Vollzyklen pro Monat */}
        <div>
          <ChartKopf>Vollzyklen pro Monat</ChartKopf>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={monthlyData} margin={{ top: ACHSEN_MARGIN_TOP }}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="name" {...xAchse(schmal)} /* achsen-allow: Zeit-/Kategorie-Achse (Monat) */ />
                <YAxis tickFormatter={achsenTick} {...yAchse(schmal, 40)} label={achsenEinheit('Zyklen')} />
                <Tooltip cursor={CHART_HOVER_CURSOR} content={<ChartTooltip decimals={1} />} />
                <Area type="monotone" dataKey="zyklen" fill={CHART_COLORS.speicherZyklen} stroke={CHART_COLORS.speicherZyklen} name="Zyklen" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      {/* Effizienz — gleitende 12-Monats-Effizienz (carry-over-immun). */}
      <div>
        <ChartKopf>Effizienz — gleitende 12 Monate</ChartKopf>
        <div className="h-48">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={effizienzData} margin={{ top: ACHSEN_MARGIN_TOP }}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="name" {...xAchse(schmal)} /* achsen-allow: Zeit-/Kategorie-Achse (Monat) */ />
              <YAxis domain={[0, 100]} tickFormatter={achsenTick} {...yAchse(schmal, 55)} label={achsenEinheit('%')} />
              <Tooltip cursor={CHART_HOVER_CURSOR} content={<ChartTooltip unit="%" decimals={1} />} />
              <Line type="monotone" dataKey="effizienz" stroke={CHART_COLORS.speicherEffizienz} strokeWidth={2} dot={{ r: 4 }} name="Effizienz" connectNulls />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Monatsdaten-Tabelle (Monat · Ladung · Entladung · Zyklen). */}
      <details className="border-t border-gray-200 dark:border-gray-700 pt-4">
        <summary className="cursor-pointer text-sm text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white">
          Monatsdaten anzeigen
        </summary>
        <div className="mt-4 overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead>
              <tr className="border-b border-gray-200 dark:border-gray-700">
                <th className="text-left py-2 px-2">Monat</th>
                <th className="text-right py-2 px-2">Ladung</th>
                <th className="text-right py-2 px-2">Entladung</th>
                <th className="text-right py-2 px-2">Zyklen</th>
              </tr>
            </thead>
            <tbody>
              {monthlyData.map((md, idx) => (
                <tr key={idx} className="border-b border-gray-100 dark:border-gray-800">
                  <td className="py-2 px-2">{md.name}</td>
                  <td className={`text-right py-2 px-2 ${DATENROLLE.speicherLadung.text}`}>{fmtZahl(md.ladung, 1)}</td>
                  <td className={`text-right py-2 px-2 ${DATENROLLE.speicherEntladung.text}`}>{fmtZahl(md.entladung, 1)}</td>
                  <td className="text-right py-2 px-2">{fmtZahl(md.zyklen, 1)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </div>
  )
}
