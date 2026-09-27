/**
 * WaermeVerlaufChart — der Verlauf im Wärme/Klima-Block (Konzept Wärme/Klima §8).
 *
 * Generisch über die x-Achse: `rows` tragen einen `name` (Monatskürzel, Tag,
 * Stunde), `bars` stapeln sich auf der kWh-Achse, `linien` liegen darüber —
 * wahlweise auf derselben Achse oder auf einer zweiten rechts. Damit ist es
 * **dieselbe** Komponente für Jahr (x = Monate), Monat (x = Tage) und Tag
 * (x = Stunden); die Sichten liefern nur andere Zeilen.
 *
 * ⭐ **Warum eine eigene Komponente und nicht die des Hubs.**
 * `KomponentenVerlaufChart` ist ein `BarChart` und kennt keine Linien. Ihn auf
 * `ComposedChart` zu heben wäre für den Hub **nicht** folgenlos: recharts
 * wählt die Cursor-Form am `chartName` (`component/Cursor.js:46-48`) —
 * `BarChart` bekommt ein `Rectangle` über die Bandbreite, alles andere eine
 * `Curve`. Das graue Hover-Band des Hubs (`CHART_HOVER_CURSOR`, nur `fill`)
 * würde dabei zur dünnen Linie. Gemessen 10.09.2026, kein Gate misst es.
 *
 * ⚑ Die Komposition ist bewusst je Chart, der **SoT sind die Primitive**:
 * `xAchse`/`yAchse`/`achsenEinheit`/`achsenTick`, `useLegendenToggle`,
 * `ChartLegende`, `eedcTooltipProps`, `CHART_COLORS`. Vorbild ist
 * {@link JahrCo2Chart} — gestapelte Balken links, Linie auf zweiter Achse
 * rechts, Formatter je Serie.
 */
import { useMemo } from 'react'
import {
  ComposedChart, Bar, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer,
} from 'recharts'
import { ChartLegende, eedcTooltipProps } from '../components/ui'
import { WetterIcon } from '../components/aussicht'
import { xAchse, yAchse, achsenEinheit, achsenTick, ACHSEN_MARGIN_TOP, fmtZahl } from '../lib'
import { useLegendenToggle, useSchmaleAchse } from '../hooks'

/** Eine gestapelte Mengen-Serie (kWh) — Farbe aus `lib/colors`. */
export interface VerlaufStapel {
  key: string
  label: string
  farbe: string
}

/** Eine Linien-Serie über dem Stapel. `achse: 'rechts'` legt sie auf die
 *  zweite Achse (andere Einheit); ohne Angabe teilt sie die kWh-Achse. */
export interface VerlaufLinie {
  key: string
  label: string
  farbe: string
  achse?: 'links' | 'rechts'
  /** Nachkommastellen im Tooltip (Default 1). */
  dezimalen?: number
}

export interface WaermeVerlaufRow {
  name: string
  [serie: string]: number | string | null
}

/**
 * Das Wettersymbol einer Periode, als Tick einer **zweiten** x-Achse (WK-16c).
 *
 * ⭐ **Warum eine zweite Achse und kein Streifen daneben:** Beide Achsen teilen
 * dieselbe Kategorien-Skala, also fluchten die Symbole mit den Balken — ohne
 * dass irgendwo eine Pixelbreite nachgerechnet wird. Genau daran ist der Versuch
 * „Chart + Streifen" in der Aussicht-Fläche gescheitert (dort steht heute ein
 * CSS-Grid statt eines Charts).
 *
 * ⚑ Gezeichnet wird in einem ``foreignObject``: Der Symbolsatz ist die
 * eingeführte SoT-Komponente {@link WetterIcon} (Lucide + Tailwind-Tonwerte),
 * und die gilt für HTML. Sie in SVG nachzubauen wäre eine zweite Bauform für
 * dieselben zehn Symbole.
 */
function WetterTick({ x, y, payload, symbole }: {
  x?: number; y?: number
  payload?: { value?: string | number }
  symbole: Record<string, string>
}) {
  const symbol = symbole[String(payload?.value ?? '')]
  if (!symbol || x == null || y == null) return null
  return (
    <foreignObject x={x - 8} y={y - 16} width={16} height={16}>
      <div className="flex items-center justify-center">
        <WetterIcon symbol={symbol} className="h-4 w-4" />
      </div>
    </foreignObject>
  )
}

/** N-566 (Klassen-Dreifrage c): Default der optionalen Prop `linien` — EINE Referenz. Ein
 *  `= []` im Parameter wäre je Render neu und liefe in die Memo-Abhängigkeit von
 *  `einheitJeLabel` (dieselbe Bauform wie `TagWerteTabelle`/`TagVerlaufChart`). */
const KEINE_LINIEN: VerlaufLinie[] = []

export function WaermeVerlaufChart({
  rows, stapel, linien = KEINE_LINIEN, einheit = 'kWh', rechteEinheit, tall, wetterSymbole,
}: {
  rows: WaermeVerlaufRow[]
  stapel: VerlaufStapel[]
  linien?: VerlaufLinie[]
  einheit?: string
  /** Einheit der zweiten Achse — nur nötig, wenn eine Linie `achse: 'rechts'` trägt. */
  rechteEinheit?: string
  tall?: boolean
  /** `{Zeilen-Name: Symbol}` — Wettersymbole über der Zeitachse (WK-16c). */
  wetterSymbole?: Record<string, string>
}) {
  const schmal = useSchmaleAchse()
  // B7-Standard: Serien per Legenden-Klick aus-/einblenden. Reset, wenn sich
  // der Serien-Satz ändert (andere Periode, andere Betriebsarten).
  const legende = useLegendenToggle([...stapel, ...linien].map((s) => s.key).join('|'))
  // Einheit je Serie für den Tooltip — die zweite Achse trägt eine andere
  // (°C, %), und ein gemeinsamer `unit` würde sie mit kWh beschriften.
  const einheitJeLabel = useMemo(() => {
    const m = new Map<string, { einheit: string; dezimalen: number }>()
    stapel.forEach((b) => m.set(b.label, { einheit, dezimalen: 0 }))
    linien.forEach((l) => m.set(l.label, {
      einheit: l.achse === 'rechts' ? (rechteEinheit ?? '') : einheit,
      dezimalen: l.dezimalen ?? 1,
    }))
    return m
  }, [stapel, linien, einheit, rechteEinheit])

  if (rows.length === 0) {
    return <p className="text-sm text-gray-500 dark:text-gray-400">Keine Verlaufsdaten erfasst.</p>
  }

  const hatRechte = linien.some((l) => l.achse === 'rechts')
  // ⚠ **Symbole nur, wo sie nebeneinander passen.** Ein 16-px-Icon je Periode
  // braucht Platz; auf einem schmalen Gerät reicht er für zwölf Monate, nicht
  // für 31 Tage. Wo er fehlt, erscheint die Reihe gar nicht — überlappende
  // Symbole wären eine Auskunft, die niemand lesen kann.
  const zeigtWetter = !!wetterSymbole && Object.keys(wetterSymbole).length > 0
    && rows.length <= (schmal ? 12 : 31)

  return (
    <div className={tall ? 'h-[420px]' : 'h-72'}>
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={rows} margin={{ top: ACHSEN_MARGIN_TOP, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" className="stroke-gray-200 dark:stroke-gray-700" />
          <XAxis dataKey="name" {...xAchse(schmal)} interval="preserveStartEnd" /* achsen-allow: Zeit-/Kategorie-Achse */ />
          {zeigtWetter && (
            <XAxis
              xAxisId="wetter" dataKey="name" orientation="top" type="category"
              axisLine={false} tickLine={false} height={20} interval={0}
              // Custom-Renderer: Er zeichnet je Periode ein **Icon** statt eines
              // Textes und bestimmt Größe wie Ausrichtung selbst — deshalb weder
              // 10-px-Tick noch −45° (s. `check-achsen.mjs`, X_HORIZONTAL_OK).
              tick={(props) => <WetterTick {...props} symbole={wetterSymbole!} />}
              /* achsen-allow: Zeit-/Kategorie-Achse */
            />
          )}
          <YAxis yAxisId="menge" {...yAchse(schmal, 48)} tickFormatter={achsenTick} label={achsenEinheit(einheit)} />
          {hatRechte && (
            <YAxis
              yAxisId="rechts" orientation="right" {...yAchse(schmal, 40)}
              tickFormatter={achsenTick} label={achsenEinheit(rechteEinheit ?? '', 'rechts')}
            />
          )}
          <Tooltip {...eedcTooltipProps({
            formatter: (value: number, name: string) => {
              const e = einheitJeLabel.get(name)
              return `${fmtZahl(value, e?.dezimalen ?? 0)}${e?.einheit ? ` ${e.einheit}` : ''}`
            },
          })} />
          <Legend wrapperStyle={{ fontSize: 11 }} content={<ChartLegende onItemClick={legende.onItemClick} />} />
          {stapel.map((b) => (
            <Bar
              key={b.key} yAxisId="menge" dataKey={b.key} name={b.label}
              stackId="menge" fill={b.farbe} hide={legende.istVersteckt(b.key)}
            />
          ))}
          {linien.map((l) => (
            // `connectNulls` bewusst NICHT: eine Lücke in der gemessenen Wärme
            // ist eine Aussage (E7 — es gibt dort keinen gemessenen Wert), und
            // eine durchgezogene Linie darüber wäre eine Behauptung.
            <Line
              key={l.key} yAxisId={l.achse === 'rechts' ? 'rechts' : 'menge'} type="monotone"
              dataKey={l.key} name={l.label} stroke={l.farbe} strokeWidth={2} dot={false}
              hide={legende.istVersteckt(l.key)}
            />
          ))}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  )
}
