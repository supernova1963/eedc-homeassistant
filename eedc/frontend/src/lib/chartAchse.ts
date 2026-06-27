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
