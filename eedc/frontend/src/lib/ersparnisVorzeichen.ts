/**
 * Ersparnis oder Mehrkosten — **die eine Stelle, die das Vorzeichen liest**.
 *
 * ⛔ **Der Anlass (Befund W-10, zwei Melder-Screenshots von dietmar1968,
 * 25.08.2026):** Unter der Überschrift „Ersparnis vs. Gas" stand
 * `+-49,53 €`. Der Code stellte das Plus **unbesehen** voran:
 *
 * ```ts
 * value: hat(d.wp_ersparnis_euro) ? `+${fmtCalc(d.wp_ersparnis_euro, 2)}` : '—'
 * ```
 *
 * Die **Rechnung stimmte** — eine Wärmepumpe mit einer Arbeitszahl unter 1 ist
 * teurer als Gas, und der Kühlstrom ist seit 19.08. korrekt aus dem Vergleich
 * heraus (E-B). Falsch waren nur Vorzeichen und Wort.
 *
 * ⭐ **Das Plus selbst war nie der Fehler.** Ein positiver Betrag *soll* sein
 * Vorzeichen tragen — sonst sähe eine Ersparnis wie eine nackte Zahl aus. Der
 * Fehler war, es ohne Blick auf das Vorzeichen zu setzen. Deshalb steht hier
 * eine Fallunterscheidung und keine Streichung.
 *
 * ⚠ **Warum als SoT und nicht als drei Einzelfixes** (Regel 0a): Die Klasse saß
 * an **drei** Stellen derselben Datei — WP-Kachel, WP-Summary und
 * E-Mob-Summary („+… € vs. Verbrenner"). Zwei davon hatte kein Melder gesehen.
 * Ein Fix nur an der gemeldeten Stelle hätte die anderen beiden stehen lassen.
 */

import { fmtCalc } from '../components/ui'

export interface ErsparnisAnzeige {
  /** Der formatierte Betrag samt Vorzeichen — `+312,40` bzw. `-49,53`. */
  betrag: string
  /** `true`, wenn der Betrag negativ ist: dann ist es keine Ersparnis. */
  istMehrkosten: boolean
  /**
   * Das passende Wort zum Vorzeichen — `Ersparnis` oder `Mehrkosten`.
   * Ohne Bezug (`vs. Gas`), damit der Aufrufer ihn anhängen kann.
   */
  wort: string
}

/**
 * Formatiert einen Ersparnis-Betrag **mit dem Wort, das zu seinem Vorzeichen
 * passt**.
 *
 * @param euro     Betrag; positiv = Ersparnis, negativ = Mehrkosten.
 * @param decimals Nachkommastellen (Kachel 2, Summary 0).
 */
export function ersparnisAnzeige(
  euro: number | null | undefined,
  decimals = 2,
): ErsparnisAnzeige | null {
  if (euro === null || euro === undefined || isNaN(euro)) return null
  const istMehrkosten = euro < 0
  return {
    // `fmtCalc` trägt das Minus selbst — ein zweites voranzustellen ergäbe
    // genau die Doppelung, um die es hier geht.
    betrag: istMehrkosten ? fmtCalc(euro, decimals) : `+${fmtCalc(euro, decimals)}`,
    istMehrkosten,
    wort: istMehrkosten ? 'Mehrkosten' : 'Ersparnis',
  }
}
