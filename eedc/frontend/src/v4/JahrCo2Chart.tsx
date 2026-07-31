/**
 * JahrCo2Chart — „CO₂-Bilanz"-Block der Cockpit/Jahr-Sicht.
 *
 * Zeigt die vermiedene CO₂-Menge der MONATE des gewählten Jahres, gestapelt nach
 * den drei Quellen, die der Backend-Kanon getrennt ausweist:
 *   • PV/Eigenverbrauch — vermiedener Netzstrom
 *   • Wärmepumpe        — vermiedene fossile Wärme
 *   • E-Mobilität       — vermiedener Kraftstoff
 * dazu die Autarkie desselben Monats als Linie auf der zweiten (%)-Achse.
 *
 * Quelle: `cockpitApi.getNachhaltigkeit` (`/cockpit/nachhaltigkeit/{anlage}`).
 * Der Endpoint rechnet seit 2026-07-31 auf den Monats-Fakten (ADR-002/**P10**) und
 * liefert die Anteile bereits **geklemmt**, passend zum Stapel — `co2_gesamt_kg`
 * IST die Summe der drei geklemmten Anteile, also die Höhe des gestapelten Balkens.
 * Hier wird nichts nachgerechnet.
 *
 * ─── Jahres-Scope: welche Größe ist jahresgebunden? ──────────────────────────
 * Der Endpoint kennt **kein** `?jahr=` und liefert die GANZE Historie; gefiltert
 * wird ausschließlich hier ({@link baueJahrCo2ChartDaten}).
 *   • JAHRESGEBUNDEN  — alles in diesem Chart: `co2_pv_kg`, `co2_wp_kg`,
 *     `co2_emob_kg`, `co2_gesamt_kg`, `autarkie_prozent`. Es sind Monatswerte, die
 *     Filterung trifft sie ALLE (der halb greifende Jahres-Filter war N-10/S4).
 *   • NICHT JAHRESGEBUNDEN — `co2_kumuliert_kg`. Das ist eine Lebensdauer-Zahl
 *     über die gesamte Historie und taucht deshalb hier bewusst NICHT auf: eine
 *     kumulierte Linie, die im Januar auf halber Höhe beginnt, erklärt sich nicht
 *     selbst. Sie wird in {@link CockpitJahrV4} als eigener Kennwert gezeigt —
 *     ausdrücklich beschriftet, damit die beiden Zeitbezüge nicht verschwimmen.
 */
import { useMemo } from 'react'
import {
  ComposedChart, Bar, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer,
} from 'recharts'
import { ChartLegende, eedcTooltipProps } from '../components/ui'
import {
  CHART_COLORS, MONAT_KURZ, co2Achse, xAchse, yAchse, achsenEinheit, achsenTick,
  ACHSEN_MARGIN_TOP, fmtZahl,
} from '../lib'
import { useLegendenToggle, useSchmaleAchse } from '../hooks'
import type { NachhaltigkeitMonat } from '../api/cockpit'
import type { ChartTabelleSpalte } from '../components/ui'

export interface Co2ChartPunkt {
  monat: string
  monatNr: number
  co2Pv: number
  co2Wp: number
  co2Emob: number
  /** Stapel-Höhe = Σ der drei geklemmten Anteile (Backend-Kanon, nicht nachgerechnet). */
  co2Gesamt: number
  autarkie: number | null
}

/**
 * Die Monate EINES Jahres aus der Gesamt-Historie (aufsteigend).
 *
 * Das ist die eine Stelle, an der der Jahres-Filter greift — und er greift auf
 * die ganze Zeile, nicht auf einzelne Serien.
 */
export function baueJahrCo2ChartDaten(
  monatswerte: readonly NachhaltigkeitMonat[],
  jahr: number,
): Co2ChartPunkt[] {
  return monatswerte
    .filter((m) => m.jahr === jahr)
    .slice()
    .sort((a, b) => a.monat - b.monat)
    .map((m) => ({
      monat: MONAT_KURZ[m.monat],
      monatNr: m.monat,
      co2Pv: m.co2_pv_kg,
      co2Wp: m.co2_wp_kg,
      co2Emob: m.co2_emob_kg,
      co2Gesamt: m.co2_gesamt_kg,
      autarkie: m.autarkie_prozent,
    }))
}

/** Σ der Monats-CO₂ des gewählten Jahres (kg) — der jahresgebundene Kennwert. */
export function co2JahresSumme(punkte: readonly Co2ChartPunkt[]): number {
  return punkte.reduce((s, p) => s + p.co2Gesamt, 0)
}

/**
 * Spalten der Chart-Daten-Tabelle (Paket CT): Union der Chart-Serien plus die
 * Stapel-Höhe, die der Chart als Balken-Gesamthöhe ohnehin zeigt. `kg` steht
 * nicht in der Summierbar-Default-Menge (kWh/km/€) — für Mengen ist die
 * Jahres-Summe aber genau die richtige Fußzeile, also explizit gesetzt.
 */
export const CO2_TABELLEN_SPALTEN: ChartTabelleSpalte[] = [
  { key: 'co2Pv', label: 'PV/Eigenverbrauch', einheit: 'kg', summierbar: true },
  { key: 'co2Wp', label: 'Wärmepumpe', einheit: 'kg', summierbar: true },
  { key: 'co2Emob', label: 'E-Mobilität', einheit: 'kg', summierbar: true },
  { key: 'co2Gesamt', label: 'CO₂ gesamt', einheit: 'kg', summierbar: true },
  { key: 'autarkie', label: 'Autarkie', einheit: '%' },
]

export function JahrCo2Chart({ daten }: { daten: Co2ChartPunkt[] }) {
  const schmal = useSchmaleAchse()
  const legende = useLegendenToggle()
  // Achsen-Einheit vom Stapel-Maximum (nicht vom größten Einzelanteil) — sonst
  // stünde die Achse in kg, während der Balken längst im t-Bereich liegt.
  const achse = useMemo(() => co2Achse(Math.max(0, ...daten.map((p) => p.co2Gesamt))), [daten])

  if (daten.length === 0) {
    return <p className="text-sm text-gray-500 dark:text-gray-400">Keine CO₂-Daten im Jahr.</p>
  }

  return (
    <div className="space-y-3">
      <p className="text-xs text-gray-400 dark:text-gray-500">
        Gestapelt: PV/Eigenverbrauch + Wärmepumpe + E-Mobilität = vermiedenes CO₂ des Monats
      </p>

      <div className="h-72">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={daten} margin={{ top: ACHSEN_MARGIN_TOP, right: 8, bottom: 0, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" className="stroke-gray-200 dark:stroke-gray-700" />
            <XAxis dataKey="monat" {...xAchse(schmal)} /* achsen-allow: Zeit-/Kategorie-Achse (Monat) */ />
            <YAxis yAxisId="co2" {...yAchse(schmal, 48)} tickFormatter={achse.tick} label={achsenEinheit(achse.einheit)} />
            <YAxis yAxisId="pct" orientation="right" domain={[0, 100]} {...yAchse(schmal, 40)} tickFormatter={achsenTick} label={achsenEinheit('%', 'rechts')} />
            <Tooltip {...eedcTooltipProps({ formatter: (value: number, name: string) =>
              name === 'Autarkie' ? `${fmtZahl(value, 1)} %` : `${fmtZahl(value, 1)} kg` })} />
            <Legend wrapperStyle={{ fontSize: 12 }} content={
              <ChartLegende onItemClick={legende.onItemClick} />
            } />

            <Bar yAxisId="co2" dataKey="co2Pv" name="PV/Eigenverbrauch" stackId="co2" fill={CHART_COLORS.co2Pv} hide={legende.istVersteckt('co2Pv')} />
            <Bar yAxisId="co2" dataKey="co2Wp" name="Wärmepumpe" stackId="co2" fill={CHART_COLORS.co2Wp} hide={legende.istVersteckt('co2Wp')} />
            <Bar yAxisId="co2" dataKey="co2Emob" name="E-Mobilität" stackId="co2" fill={CHART_COLORS.co2Emob} hide={legende.istVersteckt('co2Emob')} />
            <Line yAxisId="pct" type="monotone" dataKey="autarkie" name="Autarkie" stroke={CHART_COLORS.autarkie} strokeWidth={2} dot={false} connectNulls hide={legende.istVersteckt('autarkie')} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}
