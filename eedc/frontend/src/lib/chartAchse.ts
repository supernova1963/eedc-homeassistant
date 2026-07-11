import { createElement, type ReactElement } from 'react'

/**
 * Achsen-Standard (D7-5 / detLAN R7 / R9-Nacharbeit) — EINE Wahrheit für Recharts-Achsen.
 *
 *  • `ACHSEN_TICK` — einheitliche Tick-Schriftgröße (10 px) für ALLE Achsen
 *    (X + Y), app-weit. Schluss mit 10/11/12-Drift.
 *  • `ACHSEN_MARGIN_TOP` — reservierter oberer Rand JEDES Charts, damit die
 *    waagerechte Einheits-Beschriftung ({@link achsenEinheit}) ÜBER dem obersten
 *    Tick Platz hat und nicht abschneidet. Pflicht-Margin bei jedem Chart mit
 *    Einheit: `margin={{ top: ACHSEN_MARGIN_TOP, ... }}`.
 *  • `xAchse(schmal)` — Props-Spread NUR für **Zeit-/Text-X-Achsen** (Monat/Tag/
 *    Datum): auf schmalen Views (Mobile, {@link useSchmaleAchse}) **−45°** gedreht
 *    + `interval="preserveStartEnd"` (dünnt Labels aus); sonst horizontal. detLAN
 *    lehnt das frühere 90°-Quer ab (R9). Recharts erkennt `<XAxis>` am
 *    Komponententyp → kein Wrapper möglich, daher Spread:
 *      `<XAxis dataKey="monat" {...xAchse(schmal)} />`
 *    NICHT auf kurze/numerische X-Achsen anwenden (die bleiben horizontal).
 */
export const ACHSEN_TICK = { fontSize: 10 } as const

/** Reservierter oberer Chart-Rand für die waagerechte Einheit über dem obersten Tick. */
export const ACHSEN_MARGIN_TOP = 18

/**
 * achsenTick — de-DE-Standard-`tickFormatter` für JEDE Wert-Achse: Tausenderpunkt
 * + Komma-Dezimalen, variable Nachkommastellen (was der Recharts-Tick natürlich
 * trägt). „2800"→„2.800", „4.5"→„4,5", „100"→„100". Pflicht auf allen Zahl-Achsen,
 * AUSSER die Achse hat einen wert-*transformierenden* Formatter (MWh/t-Skalierung
 * via `energieAchse`/`co2Achse`, €-Format via `fmtZahl`+„ €") — der bleibt.
 */
export const achsenTick = (v: number | string): string =>
  typeof v === 'number' && Number.isFinite(v) ? v.toLocaleString('de-DE') : String(v ?? '')

export interface XAchsenProps {
  tick: typeof ACHSEN_TICK
  angle?: number
  textAnchor?: 'end' | 'middle'
  height?: number
  interval?: 'preserveStartEnd'
}

export function xAchse(_schmal?: boolean, _immer45?: boolean): XAchsenProps {
  // D11-10 (detLAN R11 + Gernot, 2026-06-29): 45° X-Achse EINHEITLICH ÜBERALL
  // (mobil + Desktop). detLAN: „vielleicht einfach einheitlich überall — sieht gut
  // aus, erleichtert die Arbeit, behebt Desktop-Überlapp bei vielen Labels." Kurze
  // Label-Sets drehen bewusst mit. (Params bleiben für Aufruf-Kompatibilität, werden
  // ignoriert.) R9 (detLAN): nie 90°-Quer. `preserveStartEnd` dünnt enge Reihen aus.
  return { tick: ACHSEN_TICK, angle: -45, textAnchor: 'end', height: 48, interval: 'preserveStartEnd' }
}

export interface YAchsenProps {
  tick: typeof ACHSEN_TICK
  width: number
}

/**
 * ACHSEN_Y_BREITE — Default-Breite jeder Wert-Y-Achse (D18-3, detlan #210).
 * Regel: die Y-Achsen-Breite kommt IMMER aus dieser Zentrale — `yAchse(schmal)`
 * = 48 px, betragsabhängig pro Chart übersteuerbar (`yAchse(schmal, 44|52|…)`).
 * NIE der Recharts-Default 60 px (verschwendeter Seitenrand). Wächter:
 * check:charts R3. Kategorie-Y-Achsen (horizontale Balken) setzen ihre
 * Label-Breite weiterhin hart per `width=`.
 */
export const ACHSEN_Y_BREITE = 48

/**
 * yAchse — Y-Achsen-Props. R9-Nacharbeit (detLAN): Y-Tick-**Zahlen bleiben immer
 * waagerecht** (auch mobil — Zahlen sind kurz), kein 90°-Quer mehr. `breite` =
 * feste Achsenbreite (Default {@link ACHSEN_Y_BREITE}, auf allen Views durchgereicht).
 *   `<YAxis yAxisId="kwh" {...yAchse(schmal, 48)} label={achsenEinheit('kWh')} />`
 */
export function yAchse(_schmal: boolean, breite: number = ACHSEN_Y_BREITE): YAchsenProps {
  return { tick: ACHSEN_TICK, width: breite }
}

// ── Achsen-EINHEIT (R9-Nacharbeit / detLAN+Rainer-Kompromiss) ────────────────

export interface AchsenEinheitLabel {
  value: string
  position: 'top'
  content: (props: { viewBox?: { x?: number; y?: number; width?: number; height?: number } }) => ReactElement
}

/**
 * achsenEinheit — die EINE Wahrheit für den Einheiten-Titel einer Achse
 * (R9-Nacharbeit, detLAN + Rainer 👍; Ausrichtungs-Nachzug Gernot 2026-06-30):
 *   • Einheit als **kleine, waagerechte** Beschriftung **über dem obersten Tick**.
 *     **NIE gedreht — auch mobil nicht.** Nie über/auf einem Tick.
 *   • **Horizontal exakt ÜBER den Tick-Werten** (Gernot 2026-06-30): die Einheit
 *     muss dieselbe Ausrichtung/Position wie die Achsen-Zahlen haben. `position:'top'`
 *     allein ankert in der Achsen-Box-MITTE (→ Einheit saß links neben den Zahlen,
 *     D12-14 drehte nur den `textAnchor`, nicht den Ankerpunkt). Fix: eigener
 *     `content`-Renderer, der die x-Position aus der `viewBox` an die Tick-Kante legt —
 *     linke Achse rechtsbündig an der rechten Box-Kante (`x = vb.x + vb.width`,
 *     `textAnchor:'end'`, wie die rechtsbündigen Zahlen), rechte Achse linksbündig an
 *     der linken Box-Kante (`x = vb.x`, `textAnchor:'start'`). `y = vb.y - 6` liegt im
 *     reservierten oberen Rand → Chart braucht weiterhin `margin={{ top: ACHSEN_MARGIN_TOP }}`.
 * `seite` = Orientierung: `'links'` (Default, primär) | `'rechts'` (2. Achse).
 * Jede Achse trägt genau **eine** Einheit; Klammer-Überschriften im Chart-Kopf
 * („… (kWh)") und `unit=`-Tick-Suffixe entfallen — die Einheit gehört an die Achse.
 * Recharts erkennt `<Label>` am `label`-Prop → direkt: `label={achsenEinheit('kWh')}`.
 */
export function achsenEinheit(
  einheit: string,
  seite: 'links' | 'rechts' = 'links',
): AchsenEinheitLabel {
  const rechts = seite === 'rechts'
  return {
    value: einheit,
    position: 'top',
    content: ({ viewBox }) => {
      const x = viewBox?.x ?? 0
      const y = viewBox?.y ?? 0
      const w = viewBox?.width ?? 0
      // Tick-Kante: links = rechte Box-Kante (Zahlen rechtsbündig an der Achslinie),
      // rechts = linke Box-Kante (Zahlen linksbündig an der Achslinie).
      const tx = rechts ? x : x + w
      return createElement(
        'text',
        {
          x: tx,
          y: y - 6,
          textAnchor: rechts ? 'start' : 'end',
          fontSize: 10,
          // Theme-aware via Tailwind fill-Utility (kein Inline-Hex; folgt CHART_THEME
          // gray-500 light / gray-400 dark = Tick-Farbe).
          className: 'fill-gray-500 dark:fill-gray-400',
        },
        einheit,
      )
    },
  }
}
