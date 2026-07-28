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
import { useEffect } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
  AreaChart, Area, LineChart, Line,
} from 'recharts'
import ChartTooltip from '../ui/ChartTooltip'
import { ChartLegende, Table, TableHead, TableBody } from '../ui'
import { ZELLE, KOPF_ZELLE } from '../ui/tabelleMasse'
import { Parkbar } from '../park'
import { MONAT_KURZ, CHART_COLORS, COLORS, CHART_HOVER_CURSOR, DATENROLLE, xAchse, yAchse, achsenEinheit, achsenTick, ACHSEN_MARGIN_TOP, fmtZahl } from '../../lib'
import { useLegendenToggle, useSchmaleAchse } from '../../hooks'
import type { InvestitionMonatsdaten, SpeicherDashboardResponse } from '../../api/investitionen'

type Zusammenfassung = SpeicherDashboardResponse['zusammenfassung']
type EffizienzVerlauf = SpeicherDashboardResponse['effizienz_verlauf']

/** Statische Park-IDs des Speicher-Verlaufs (4 feste Anzeigen; Hub-Auto-Hide). */
const VERLAUF_IDS = ['chart:speicher-ladung', 'chart:speicher-zyklen', 'chart:speicher-effizienz', 'tabelle:speicher-monate']

export interface SpeicherVerlaufProps {
  monatsdaten: InvestitionMonatsdaten[]
  zusammenfassung: Zusammenfassung
  effizienzVerlauf: EffizienzVerlauf
  embed?: boolean
  /** v4-Hub: meldet die gerenderten Park-IDs hoch (Block-Auto-Hide). v3/IST: undefined. */
  melde?: (ids: string[]) => void
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
      // N127: ohne gepflegte Kapazität ist `kapazitaet_kwh` null — der
      // Vergleich fällt dann wie bisher auf 0 (kein Balken), nur eben ohne die
      // erfundene 10-kWh-Basis dahinter.
      zyklen: z.kapazitaet_kwh != null && z.kapazitaet_kwh > 0 ? ladung / z.kapazitaet_kwh : 0,
    }
  })
}

function ChartKopf({ children }: { children: string }) {
  return <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-4">{children}</h3>
}

export function SpeicherVerlaufCharts({ monatsdaten, zusammenfassung: z, effizienzVerlauf, embed = false, melde }: SpeicherVerlaufProps) {
  const schmal = useSchmaleAchse()
  const legende = useLegendenToggle()
  // v4-Hub-Auto-Hide: die 4 Anzeigen sind fest → statische ID-Meldung (Gernot 2026-07-09).
  useEffect(() => { melde?.(VERLAUF_IDS) }, [melde])
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
        <Parkbar id="chart:speicher-ladung" titel="Ladung & Entladung pro Monat">
        <div>
          <ChartKopf>Ladung &amp; Entladung pro Monat</ChartKopf>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={monthlyData} margin={{ top: ACHSEN_MARGIN_TOP }}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="name" {...xAchse(schmal)} /* achsen-allow: Zeit-/Kategorie-Achse (Monat) */ />
                <YAxis tickFormatter={achsenTick} {...yAchse(schmal, 70)} label={achsenEinheit('kWh')} />
                <Tooltip cursor={CHART_HOVER_CURSOR} content={<ChartTooltip />} />
                <Legend content={<ChartLegende onItemClick={legende.onItemClick} />} />
                {arbitrageAktiv ? (
                  <>
                    <Bar dataKey="pvLadung" stackId="ladung" fill={CHART_COLORS.speicherLadung} name="PV-Ladung" hide={legende.istVersteckt('pvLadung')} />
                    <Bar dataKey="arbitrage" stackId="ladung" fill={COLORS.grid} name="Netz-Ladung" hide={legende.istVersteckt('arbitrage')} />
                  </>
                ) : (
                  <Bar dataKey="ladung" fill={CHART_COLORS.speicherLadung} name="Ladung" hide={legende.istVersteckt('ladung')} />
                )}
                <Bar dataKey="entladung" fill={CHART_COLORS.speicherEntladung} name="Entladung" hide={legende.istVersteckt('entladung')} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
        </Parkbar>

        {/* Vollzyklen pro Monat */}
        <Parkbar id="chart:speicher-zyklen" titel="Vollzyklen pro Monat">
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
        </Parkbar>
      </div>

      {/* Effizienz — gleitende 12-Monats-Effizienz (carry-over-immun). */}
      <Parkbar id="chart:speicher-effizienz" titel="Effizienz — gleitende 12 Monate">
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
      </Parkbar>

      {/* Monatsdaten-Tabelle (Monat · Ladung · Entladung · Zyklen).
          B6/S9 (R3b E3): auf den details-Disclosure-Kanon gehoben (gray-100/pt-3,
          Zähler in der Summary) — Komponente ist V4-geteilt (SpeicherVerlaufIST),
          Änderung im V3-SpeicherDashboard mit-sichtbar (eine Code-Wahrheit). */}
      <Parkbar id="tabelle:speicher-monate" titel="Monatsdaten-Tabelle">
      <details className="border-t border-gray-100 dark:border-gray-800 pt-3">
        <summary className="cursor-pointer text-sm text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white">
          Monatsdaten anzeigen ({monatsdaten.length})
        </summary>
        <Table aussenClassName="mt-3">
          <TableHead>
            <tr className="border-b border-gray-200 dark:border-gray-700">
              <th className={`${KOPF_ZELLE} text-left`}>Monat</th>
              <th className={`${KOPF_ZELLE} text-right`}>Ladung</th>
              <th className={`${KOPF_ZELLE} text-right`}>Entladung</th>
              <th className={`${KOPF_ZELLE} text-right`}>Zyklen</th>
            </tr>
          </TableHead>
          <TableBody>
            {monthlyData.map((md, idx) => (
              <tr key={idx} className="border-b border-gray-100 dark:border-gray-800">
                <td className={ZELLE}>{md.name}</td>
                <td className={`${ZELLE} text-right ${DATENROLLE.speicherLadung.text}`}>{fmtZahl(md.ladung, 1)}</td>
                <td className={`${ZELLE} text-right ${DATENROLLE.speicherEntladung.text}`}>{fmtZahl(md.entladung, 1)}</td>
                <td className={`${ZELLE} text-right`}>{fmtZahl(md.zyklen, 1)}</td>
              </tr>
            ))}
          </TableBody>
        </Table>
      </details>
      </Parkbar>
    </div>
  )
}
