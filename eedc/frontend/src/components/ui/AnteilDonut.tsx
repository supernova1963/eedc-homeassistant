/**
 * AnteilDonut — SoT-Darstellung für Anteils-/Verteilungs-Charts (B7 „Anteil → Donut",
 * D17-6 „drei Torten, dreimal anders" → EINE Bildsprache).
 *
 * EINE Chart-Klasse = EINE Komponente (Regel 0a): ersetzt die früheren Hand-Pies in
 * `RoiTypPie` + den Community-Deep-Dives. Kanonische Eigenschaften, überall gleich:
 *  - **Form:** Donut (`innerRadius`), Radien in %-→ füllt die Container-Breite (D17-5b).
 *  - **Keine Slice-Labels** (ragten über schmale Container, detLAN 2026-06-28). Name + %
 *    stehen in EINER umbruchfähigen Swatch-Legende darunter — auf jeder Breite vollständig.
 *  - **Legende = `ChartLegende`-Bildsprache** (Farb-Viereck + monochromer Text, nie roher
 *    Recharts-`<Legend>`); der %-Wert steht gedämpft dahinter.
 *  - **Hervorhebung** der „eigenen" Scheibe über `SERIE_HERVORHEBUNG` (kein Inline-`#000`).
 *  - **Tooltip** über die `eedcTooltipProps`-Factory (Regel D: Cursor+Content aus einer Hand).
 *
 * Höhe/Breite stellt der Aufrufer (Card/Parkbar); `chartHoehe` steuert nur den Chart-Bereich.
 */
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer } from 'recharts'
import { eedcTooltipProps } from './eedcTooltip'
import { SERIE_HERVORHEBUNG, fmtZahl } from '../../lib'

export interface AnteilDonutDatum {
  /** Bereits label-gemappter Anzeigename (TYP_LABELS/REGION_NAMEN …) — nie Roh-Enum. */
  name: string
  value: number
  /** Datenrollen-Farbe aus `lib/colors.ts`. */
  color: string
}

export interface AnteilDonutProps {
  data: AnteilDonutDatum[]
  /** Tooltip-Einheit (z. B. `'€/Jahr'`, `'Anlagen'`). */
  unit?: string
  /** Tooltip-Nachkommastellen (Default 0 — Anteile sind i. d. R. Zählwerte). */
  decimals?: number
  /** Name der „eigenen" Scheibe → kräftiger Ring + Legenden-Betonung. */
  hervorhebung?: string
  /** Zusatz hinter dem hervorgehobenen Legenden-Eintrag (z. B. `'(Du)'`). */
  hervorhebungLabel?: string
  /** Tailwind-Höhe des Chart-Bereichs (Legende fließt darunter). Default `h-64`. */
  chartHoehe?: string
}

export default function AnteilDonut({
  data, unit, decimals = 0, hervorhebung, hervorhebungLabel, chartHoehe = 'h-64',
}: AnteilDonutProps) {
  const summe = data.reduce((s, d) => s + d.value, 0)

  return (
    <div>
      <div className={chartHoehe}>
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie data={data} dataKey="value" nameKey="name" cx="50%" cy="50%" innerRadius="55%" outerRadius="80%">
              {data.map((entry) => {
                const eigen = hervorhebung != null && entry.name === hervorhebung
                return (
                  <Cell
                    key={entry.name}
                    fill={entry.color}
                    stroke={eigen ? SERIE_HERVORHEBUNG.ring : undefined}
                    strokeWidth={eigen ? SERIE_HERVORHEBUNG.breite : undefined}
                  />
                )
              })}
            </Pie>
            <Tooltip {...eedcTooltipProps({ unit, decimals, cursor: false })} />
          </PieChart>
        </ResponsiveContainer>
      </div>
      {/* Swatch-Legende (ChartLegende-Bildsprache: Viereck + monochromer Text, % gedämpft). */}
      <ul className="mt-2 flex flex-wrap justify-center gap-x-4 gap-y-1 m-0 p-0 list-none">
        {data.map((d) => {
          const eigen = hervorhebung != null && d.name === hervorhebung
          return (
            <li key={d.name} className="flex items-center gap-1.5 text-sm">
              <span className="inline-block w-2.5 h-2.5 rounded-sm shrink-0" style={{ backgroundColor: d.color }} />
              <span className={`text-gray-600 dark:text-gray-300 ${eigen ? 'font-medium' : ''}`}>
                {d.name}{eigen && hervorhebungLabel ? ` ${hervorhebungLabel}` : ''}
              </span>
              <span className="text-gray-400 dark:text-gray-500 tabular-nums">
                {fmtZahl(summe > 0 ? (d.value / summe) * 100 : 0, 0)} %
              </span>
            </li>
          )
        })}
      </ul>
    </div>
  )
}
