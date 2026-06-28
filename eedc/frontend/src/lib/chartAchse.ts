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

export function xAchse(schmal: boolean): XAchsenProps {
  // R9 (detLAN): kein 90°-Quer mehr → −45° + ausgedünnte Labels auf schmalen Views.
  return schmal
    ? { tick: ACHSEN_TICK, angle: -45, textAnchor: 'end', height: 48, interval: 'preserveStartEnd' }
    : { tick: ACHSEN_TICK }
}

export interface YAchsenProps {
  tick: typeof ACHSEN_TICK
  width?: number
}

/**
 * yAchse — Y-Achsen-Props. R9-Nacharbeit (detLAN): Y-Tick-**Zahlen bleiben immer
 * waagerecht** (auch mobil — Zahlen sind kurz), kein 90°-Quer mehr. `breite` =
 * optionale feste Achsenbreite (auf allen Views durchgereicht).
 *   `<YAxis yAxisId="kwh" {...yAchse(schmal, 48)} label={achsenEinheit('kWh')} />`
 */
export function yAchse(_schmal: boolean, breite?: number): YAchsenProps {
  return { tick: ACHSEN_TICK, ...(breite != null ? { width: breite } : {}) }
}

// ── Achsen-EINHEIT (R9-Nacharbeit / detLAN+Rainer-Kompromiss) ────────────────

export interface AchsenEinheitLabel {
  value: string
  position: 'top'
  offset: number
  fontSize: number
  dx?: number
  style: { textAnchor: 'start' | 'end' }
}

/**
 * achsenEinheit — die EINE Wahrheit für den Einheiten-Titel einer Achse
 * (R9-Nacharbeit, detLAN + Rainer 👍):
 *   • Einheit als **kleine, waagerechte** Beschriftung **über dem obersten Tick**,
 *     links an der Achse. **NIE gedreht — auch mobil nicht.** Nie über/auf einem Tick.
 *   • Umgesetzt via `position:'top'` (oberhalb der Plotfläche) im reservierten
 *     oberen Rand → Chart braucht `margin={{ top: ACHSEN_MARGIN_TOP, ... }}`,
 *     sonst clippt es. `textAnchor:'start'` (links) bzw. `'end'` (rechte Achse)
 *     hält die Einheit linksbündig an der Achse statt zentriert.
 *   • **KEIN `angle`, KEIN `schmal`-Sonderfall** mehr (das war der R9-Bug).
 * `seite` = Orientierung: `'links'` (Default, primär) | `'rechts'` (2. Achse).
 * Jede Achse trägt genau **eine** Einheit; Klammer-Überschriften im Chart-Kopf
 * („… (kWh)") und `unit=`-Tick-Suffixe entfallen — die Einheit gehört an die Achse.
 * Recharts erkennt `<Label>` am `label`-Prop → direkt: `label={achsenEinheit('kWh')}`.
 */
export function achsenEinheit(
  einheit: string,
  seite: 'links' | 'rechts' = 'links',
): AchsenEinheitLabel {
  return seite === 'rechts'
    ? { value: einheit, position: 'top', offset: 8, fontSize: 10, dx: 4, style: { textAnchor: 'end' } }
    : { value: einheit, position: 'top', offset: 8, fontSize: 10, dx: -4, style: { textAnchor: 'start' } }
}
