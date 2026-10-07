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
import { ChartLegende, Table, TableHead, TableBody } from '../ui'
import { ZELLE, KOPF_ZELLE } from '../ui/tabelleMasse'
import { MONAT_KURZ, CHART_COLORS, CHART_HOVER_CURSOR, DATENROLLE, xAchse, yAchse, achsenEinheit, achsenTick, ACHSEN_MARGIN_TOP, fmtZahl } from '../../lib'
import { useLegendenToggle, useSchmaleAchse } from '../../hooks'
import type { BkwMonatsWert } from '../../api/investitionen'

/**
 * N-638: liest die bewertete Monatsreihe des Backends (`monatsreihe`), nicht mehr die
 * rohen `verbrauch_daten`. Dort stand die Erzeugung unter `pv_erzeugung_kwh` (gelesen
 * wurde `erzeugung_kwh` — immer 0), Eigenverbrauch und Einspeisung nur aus Handpflege;
 * die Kopfzahlen rechneten daneben anteilig an der Hausbilanz. Jetzt zeigen Verlauf und
 * Kopf dieselbe Rechnung. `null` bleibt `null` (nicht bewertbar, ADR-002/P4) — die
 * Tabelle zeigt dafür „—", das Diagramm eine Lücke, keine 0.
 */
export function prepBkwMonate(monatsreihe: BkwMonatsWert[]) {
  return monatsreihe.map((m) => ({
    name: `${MONAT_KURZ[m.monat]} ${m.jahr.toString().slice(2)}`,
    erzeugung: m.erzeugung_kwh,
    eigenverbrauch: m.eigenverbrauch_kwh,
    einspeisung: m.einspeisung_kwh,
    speicher_ladung: m.speicher_ladung_kwh,
    speicher_entladung: m.speicher_entladung_kwh,
  }))
}

/** Erzeugung pro Monat (Eigenverbrauch + Einspeisung gestapelt). */
export function BkwErzeugungVerlauf({ monatsreihe }: { monatsreihe: BkwMonatsWert[] }) {
  const schmal = useSchmaleAchse()
  const legende = useLegendenToggle()
  const data = prepBkwMonate(monatsreihe)
  return (
    <div className="h-64">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: ACHSEN_MARGIN_TOP }}>
          <CartesianGrid strokeDasharray="3 3" className="stroke-gray-200 dark:stroke-gray-700" />
          <XAxis dataKey="name" {...xAchse(schmal)} /* achsen-allow: Zeit-/Kategorie-Achse */ />
          <YAxis {...yAchse(schmal)} tickFormatter={achsenTick} label={achsenEinheit('kWh')} />
          <Tooltip cursor={CHART_HOVER_CURSOR} content={<ChartTooltip />} />
          <Legend content={<ChartLegende onItemClick={legende.onItemClick} />} />
          <Area type="monotone" dataKey="eigenverbrauch" stackId="1" fill={CHART_COLORS.eigenverbrauch} stroke={CHART_COLORS.eigenverbrauch} name="Eigenverbrauch" hide={legende.istVersteckt('eigenverbrauch')} />
          <Area type="monotone" dataKey="einspeisung" stackId="1" fill={CHART_COLORS.einspeisung} stroke={CHART_COLORS.einspeisung} name="Einspeisung" hide={legende.istVersteckt('einspeisung')} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}

/** Integrierter Speicher: Ladung/Entladung pro Monat (Bar). */
export function BkwSpeicherVerlauf({ monatsreihe }: { monatsreihe: BkwMonatsWert[] }) {
  const schmal = useSchmaleAchse()
  const legende = useLegendenToggle()
  const data = prepBkwMonate(monatsreihe)
  return (
    <div className="h-48">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: ACHSEN_MARGIN_TOP }}>
          <CartesianGrid strokeDasharray="3 3" className="stroke-gray-200 dark:stroke-gray-700" />
          <XAxis dataKey="name" {...xAchse(schmal)} /* achsen-allow: Zeit-/Kategorie-Achse */ />
          <YAxis {...yAchse(schmal)} tickFormatter={achsenTick} label={achsenEinheit('kWh')} />
          <Tooltip cursor={CHART_HOVER_CURSOR} content={<ChartTooltip />} />
          <Legend content={<ChartLegende onItemClick={legende.onItemClick} />} />
          <Bar dataKey="speicher_ladung" fill={CHART_COLORS.speicherLadung} name="Ladung" hide={legende.istVersteckt('speicher_ladung')} />
          <Bar dataKey="speicher_entladung" fill={CHART_COLORS.speicherEntladung} name="Entladung" hide={legende.istVersteckt('speicher_entladung')} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

/** Monatsdaten-Tabelle: Erzeugung · Eigenverbrauch · Einspeisung [· Speicher]. */
export function BkwMonatsTabelle({ monatsreihe, hatSpeicher }: { monatsreihe: BkwMonatsWert[]; hatSpeicher?: boolean }) {
  const data = prepBkwMonate(monatsreihe)
  return (
    <Table>
      <TableHead>
        <tr className="border-b border-gray-200 dark:border-gray-700">
          {/* B2/C3 (#237): Einheit im Header „Name (Einheit)", nicht pro Zelle. */}
          <th className={`${KOPF_ZELLE} text-left`}>Monat</th>
          <th className={`${KOPF_ZELLE} text-right`}>Erzeugung (kWh)</th>
          <th className={`${KOPF_ZELLE} text-right`}>Eigenverbrauch (kWh)</th>
          <th className={`${KOPF_ZELLE} text-right`}>Einspeisung (kWh)</th>
          {hatSpeicher && <>
            <th className={`${KOPF_ZELLE} text-right`}>Sp. Ladung (kWh)</th>
            <th className={`${KOPF_ZELLE} text-right`}>Sp. Entl. (kWh)</th>
          </>}
        </tr>
      </TableHead>
      <TableBody>
        {data.map((md, idx) => (
          <tr key={idx} className="border-b border-gray-100 dark:border-gray-800">
            <td className={ZELLE}>{md.name}</td>
            <td className={`${ZELLE} text-right ${DATENROLLE.pv.text}`}>{fmtZahl(md.erzeugung, 1)}</td>
            <td className={`${ZELLE} text-right ${DATENROLLE.eigenverbrauch.text}`}>{fmtZahl(md.eigenverbrauch, 1)}</td>
            <td className={`${ZELLE} text-right ${DATENROLLE.einspeisung.text}`}>{fmtZahl(md.einspeisung, 1)}</td>
            {hatSpeicher && <>
              <td className={`${ZELLE} text-right ${DATENROLLE.speicherLadung.text}`}>{fmtZahl(md.speicher_ladung, 1)}</td>
              <td className={`${ZELLE} text-right ${DATENROLLE.speicherEntladung.text}`}>{fmtZahl(md.speicher_entladung, 1)}</td>
            </>}
          </tr>
        ))}
      </TableBody>
    </Table>
  )
}
