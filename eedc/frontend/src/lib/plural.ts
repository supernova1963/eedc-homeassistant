/**
 * Zahl + Substantiv — die eine Stelle, an der die Einzahl entschieden wird.
 *
 * **Warum es diese Zentrale gibt (Regel 0a, N-580).** Die Bauform „Zahl direkt
 * gefolgt von einem fest verdrahteten Plural" stand am 29.09.2026 an **65
 * Stellen in 30 Dateien** — jede davon zeigt bei genau einem Element eine
 * falsche Form („1 Felder noch ohne Quelle", im Galerie-Bild
 * `einstellungen_datenquellen.png` an der Wärmepumpe sichtbar). Vierzehn
 * weitere Stellen hatten dieselbe Frage schon gelöst, jede mit einem eigenen
 * Ternär und in vier verschiedenen Schreibweisen (`=== 1 ?`, `!== 1 ?`,
 * `> 1 ?`, Suffix-Ternär mitten im Wort). Eine Regel, die an 79 Stellen
 * einzeln beantwortet wird, ist keine Regel — deshalb hier.
 *
 * **Warum beide Formen übergeben werden und es keine Wörterbuch-Magie gibt.**
 * Der deutsche Plural ist nicht ableitbar (Feld→Felder, Monat→Monate,
 * Anlage→Anlagen, Sensor→Sensoren, Eintrag→Einträge, String→Strings), und der
 * **Fall** hängt am Satz: „in 1 Monat" ⇄ „in 3 Monaten" braucht den Dativ,
 * „1 Monat" ⇄ „3 Monate" den Nominativ. Eine Zentrale, die das raten will,
 * wäre an der ersten Dativ-Stelle falsch. Beide Formen stehen deshalb am
 * Aufrufer — die Zentrale entscheidet nur **welche**, und das an einem Ort.
 *
 * ⛔ **Nicht für Substantive mit gleicher Ein- und Mehrzahl** (Fehler, Zähler,
 * Speicher, Monitor …). Dort ist der feste Plural bereits richtig; ein Aufruf
 * mit zwei gleichen Zeichenketten wäre Lärm. `DatenCheckerTeile.tsx` hält das
 * seit jeher mit dem Kommentar „// Singular = Plural" fest.
 */

/** Die passende Form zur Anzahl — ohne die Zahl selbst. */
export function plural(anzahl: number, einzahl: string, mehrzahl: string): string {
  return anzahl === 1 ? einzahl : mehrzahl
}

/**
 * Anzahl + passende Form, mit einem Leerzeichen dazwischen: `3 Felder`, `1 Feld`.
 *
 * Der Normalfall. Die Zahl wird **nicht** formatiert — wer Tausenderpunkte
 * braucht, nimmt {@link plural} und setzt `fmtZahl` davor (so bleibt die
 * Zahlformatierung dort, wo sie hingehört: `lib/einheiten.ts`).
 */
export function mitAnzahl(anzahl: number, einzahl: string, mehrzahl: string): string {
  return `${anzahl} ${plural(anzahl, einzahl, mehrzahl)}`
}
