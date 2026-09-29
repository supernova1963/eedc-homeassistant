/**
 * Sonnenangebot über die Jahre — Globalstrahlung und Sonnenstunden je Monat.
 *
 * **Warum dieser Block hier steht** (#395 Punkt 1, Melder OB73-gif). Die Frage
 * „war mein Jahr schwach — oder meine Anlage?" wird auf dieser Fläche schon
 * beantwortet: Block ③ zeigt die Performance-Ratio je String über die Jahre.
 * Das ist die Antwort für den, der PR lesen kann. **Die Sonnenstunden sind die
 * laienlesbare Bezugsgröße daneben**, und sie fehlten bisher in jeder Sicht —
 * beide Größen stehen zwar als Monatsspalten in *Auswertungen → Tabelle*, aber
 * ein Diagramm gab es nirgends.
 *
 * ⭐ **Zwei Serien, und das ist kein Zierrat.** Die **Globalstrahlung** ist die
 * für PV physikalisch tragende Größe und über die Anbieter hinweg vergleichbar
 * (12–16 % Unterschied). Die **Sonnenstunden** sind die verständliche, aber die
 * schwächere: Open-Meteo und Bright Sky liegen bei ihnen um Faktor 1,6–2,0
 * auseinander. Nur die Stunden zu zeigen hieße, die schwächere Größe allein zu
 * lassen; nur die Strahlung zu zeigen hieße, die Frage nicht zu beantworten.
 *
 * Zwei Einheiten ⇒ zwei Y-Achsen, und die rechte ist ausdrücklich beschriftet.
 * Kein neuer Ladepfad: die Monatszeilen der Auswertungs-Basis tragen beide
 * Größen bereits (`pages/auswertung/types.ts`).
 */
import { useMemo } from 'react'
import {
  Bar, CartesianGrid, ComposedChart, Legend, Line, ResponsiveContainer,
  Tooltip, XAxis, YAxis,
} from 'recharts'
import { Card, ChartLegende } from '../ui'
import ChartTooltip from '../ui/ChartTooltip'
import type { ChartTabelleSpalte } from '../ui'
import { useLegendenToggle } from '../../hooks'
import { CHART_COLORS } from '../../lib/colors'
import { ACHSEN_MARGIN_TOP, achsenEinheit, achsenTick, xAchse, yAchse } from '../../lib/chartAchse'
import type { AggregierteMonatsdaten } from '../../api/monatsdaten'

/** Ein Punkt der Kurve — ein Monat, beschriftet als `MM/JJJJ`. */
export interface SonnenangebotPunkt {
  monat: string
  globalstrahlung: number | null
  sonnenstunden: number | null
}

const MM = (jahr: number, monat: number): string => `${String(monat).padStart(2, '0')}/${jahr}`

/**
 * Die Punkte der Kurve aus den Monatszeilen der Auswertungs-Basis.
 *
 * ⚠ **Monate ohne Wetterwert fallen NICHT weg, sie bleiben `null`.** Eine
 * herausgelassene Lücke sähe aus wie ein durchgehender Verlauf und wäre genau
 * die Aussage, die dieser Block widerlegen soll. Recharts zeichnet `null` als
 * Unterbrechung; der Daten-Checker nennt den Monat beim Namen.
 */
export function baueSonnenangebot(
  zeilen: readonly AggregierteMonatsdaten[],
): SonnenangebotPunkt[] {
  return [...zeilen]
    .sort((a, b) => (a.jahr - b.jahr) || (a.monat - b.monat))
    .map((z) => ({
      monat: MM(z.jahr, z.monat),
      globalstrahlung: z.globalstrahlung_kwh_m2 ?? null,
      sonnenstunden: z.sonnenstunden ?? null,
    }))
}

/** Trägt die Reihe überhaupt einen Wert? Ohne das wäre der Block eine leere Fläche. */
export function hatSonnenangebot(punkte: readonly SonnenangebotPunkt[]): boolean {
  return punkte.some((p) => p.globalstrahlung != null || p.sonnenstunden != null)
}

export const SONNENANGEBOT_SPALTEN: ChartTabelleSpalte[] = [
  { key: 'globalstrahlung', label: 'Globalstrahlung', einheit: 'kWh/m²', summierbar: false },
  { key: 'sonnenstunden', label: 'Sonnenstunden', einheit: 'h', summierbar: false },
]

export function SonnenangebotChart({ punkte }: { punkte: readonly SonnenangebotPunkt[] }) {
  const legende = useLegendenToggle()
  const daten = useMemo(() => [...punkte], [punkte])

  return (
    <Card>
      <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
        Sonnenangebot je Monat
      </h3>
      <div className="h-72">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={daten} margin={{ top: ACHSEN_MARGIN_TOP }}>
            <CartesianGrid strokeDasharray="3 3" className="stroke-gray-200 dark:stroke-gray-700" />
            <XAxis dataKey="monat" {...xAchse()} /* achsen-allow: Zeit-Achse (Monat) */ />
            <YAxis yAxisId="ghi" label={achsenEinheit('kWh/m²')} tickFormatter={achsenTick} {...yAchse(false)} />
            <YAxis yAxisId="sonne" orientation="right" label={achsenEinheit('h')} tickFormatter={achsenTick} {...yAchse(false)} />
            <Tooltip content={<ChartTooltip />} />
            <Legend content={<ChartLegende onItemClick={legende.onItemClick} />} />
            <Bar
              yAxisId="ghi" dataKey="globalstrahlung" name="Globalstrahlung"
              fill={CHART_COLORS.strahlung} radius={[2, 2, 0, 0]}
              hide={legende.istVersteckt('Globalstrahlung')}
            />
            <Line
              yAxisId="sonne" type="monotone" dataKey="sonnenstunden" name="Sonnenstunden"
              stroke={CHART_COLORS.sonnenstunden} strokeWidth={2} dot={{ r: 3 }}
              connectNulls={false}
              hide={legende.istVersteckt('Sonnenstunden')}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <p className="text-xs text-gray-500 mt-2 text-center">
        Die Globalstrahlung (Balken, linke Achse) ist die für PV tragende Größe · die Sonnenstunden
        (Linie, rechte Achse) sind die anschauliche. Lücken heißt: für den Monat liegt kein Wetterwert vor.
      </p>
    </Card>
  )
}
