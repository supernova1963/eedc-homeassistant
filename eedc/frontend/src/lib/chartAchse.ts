/**
 * Achsen-Standard (D7-5 / detLAN R7) — EINE Wahrheit für Recharts-Achsen.
 *
 *  • `ACHSEN_TICK` — einheitliche Tick-Schriftgröße (10 px) für ALLE Achsen
 *    (X + Y), app-weit. Schluss mit 10/11/12-Drift.
 *  • `xAchse(schmal)` — Props-Spread NUR für **Zeit-/Text-X-Achsen** (Monat/Tag/
 *    Datum): auf schmalen Views (Mobile, {@link useSchmaleAchse}) 90° gedreht +
 *    mehr Höhe, damit nichts überlappt; sonst horizontal. Recharts erkennt `<XAxis>`
 *    am Komponententyp → kein Wrapper möglich, daher Spread:
 *      `<XAxis dataKey="monat" {...xAchse(schmal)} />`
 *    NICHT auf kurze/numerische X-Achsen anwenden (die bleiben horizontal).
 */
export const ACHSEN_TICK = { fontSize: 10 } as const

export interface XAchsenProps {
  tick: typeof ACHSEN_TICK
  angle?: number
  textAnchor?: 'end' | 'middle'
  height?: number
}

export function xAchse(schmal: boolean): XAchsenProps {
  return schmal
    ? { tick: ACHSEN_TICK, angle: -90, textAnchor: 'end', height: 56 }
    : { tick: ACHSEN_TICK }
}

export interface YAchsenProps {
  tick: typeof ACHSEN_TICK
  angle?: number
  textAnchor?: 'middle'
  width?: number
}

/**
 * yAchse — Y-Achsen-Props (detLAN R7): auf schmalen Views die Y-Tick-Labels 90°
 * drehen + Achsen-Breite verschmälern (gedrehte Zahlen brauchen kaum Breite) →
 * mehr horizontaler Platz fürs Diagramm auf Mobile. `breite` = Normalbreite des
 * Charts (wird auf Desktop durchgereicht; ersetzt das bisherige `width`-Prop).
 *   `<YAxis yAxisId="kwh" {...yAchse(schmal, 48)} unit=" kWh" />`
 */
export function yAchse(schmal: boolean, breite?: number): YAchsenProps {
  return schmal
    ? { tick: ACHSEN_TICK, angle: -90, textAnchor: 'middle', width: 28 }
    : { tick: ACHSEN_TICK, ...(breite != null ? { width: breite } : {}) }
}

// ── Achsen-EINHEIT (D9-A / detLAN R9, Plan B) ────────────────────────────────

export interface AchsenEinheitLabel {
  value: string
  angle?: number
  position: 'insideTopLeft' | 'insideTopRight' | 'insideLeft' | 'insideRight'
  offset?: number
  fontSize: number
  style?: { textAnchor?: 'start' | 'middle' | 'end' }
}

/**
 * achsenEinheit — die EINE Wahrheit für den Einheiten-Titel einer Achse (Plan B,
 * detLAN R9 / Gernot 2026-06-28):
 *   • **breit (≥640):** Einheit **einmal waagerecht oben** an der Achse
 *     (`insideTopLeft`/`insideTopRight`, kein `angle`) — kein gedrehter Längs-Titel
 *     mehr. Innen an der oberen Achsenecke statt `position:'top'`, damit die Einheit
 *     bei knappem `margin.top` nicht oben abschneidet (D9-D Cut-off, Gate für R10-3).
 *   • **schmal (<640, {@link useSchmaleAchse}):** quer längs der Achse (90°),
 *     gerechtfertigt auf Mobile.
 * `seite` = Orientierung der Achse: `'links'` (Default, primär) | `'rechts'`
 * (2. Achse). Jede Achse trägt genau **eine** Einheit; Klammer-Überschriften im
 * Chart-Kopf entfallen (Einheit gehört an die Achse). Recharts erkennt `<Label>`
 * am `label`-Prop → Spread nicht nötig, direkt: `label={achsenEinheit('kWh', schmal)}`.
 *
 * Hinweis Legenden-Kollision (D9-D3): die Einheit sitzt innen an der oberen
 * Achsenecke → hat der Chart eine **Top**-Legende (`verticalAlign="top"`), diese
 * nach unten setzen, damit Titel ≠ Legende (Recharts-Default ist ohnehin unten).
 */
export function achsenEinheit(
  einheit: string,
  schmal: boolean,
  seite: 'links' | 'rechts' = 'links',
): AchsenEinheitLabel {
  if (schmal) {
    return seite === 'rechts'
      ? { value: einheit, angle: 90, position: 'insideRight', fontSize: 10, style: { textAnchor: 'middle' } }
      : { value: einheit, angle: -90, position: 'insideLeft', fontSize: 10, style: { textAnchor: 'middle' } }
  }
  // breit: Einheit waagerecht innen an der oberen Achsenecke
  return seite === 'rechts'
    ? { value: einheit, position: 'insideTopRight', offset: 6, fontSize: 10, style: { textAnchor: 'end' } }
    : { value: einheit, position: 'insideTopLeft', offset: 6, fontSize: 10, style: { textAnchor: 'start' } }
}
