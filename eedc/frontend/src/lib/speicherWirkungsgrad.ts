/**
 * Speicher-Wirkungsgrad — Client-Spiegel von
 * `backend/core/berechnungen/speicher_wirkungsgrad.py` (ADR-001).
 *
 * **Warum es diesen Spiegel gibt.** Zwei Sichten bilden den η aus Summen, die
 * erst im Client entstehen: *Cockpit → Jahr* (`v4/JahrAggregat.tsx` addiert N
 * Monats-Antworten) und *Auswertungen → Tabelle* (`pages/auswertung/types.ts`).
 * Für sie gibt es keine Backend-Zahl, die sie lesen könnten — also braucht die
 * Regel eine zweite Heimat, keine zweite Definition. Gleiches Muster wie
 * `lib/monatsLuecken.ts` ↔ `core/monats_luecken.py`, gewächtert durch
 * `backend/tests/test_speicher_wirkungsgrad_symmetrie.py`.
 *
 * **Die Regel in einem Satz:** Über 100 % kann kein Speicher — ohne
 * Ladestandsmessung ist ein solcher Quotient deshalb *kein* Wert, sondern eine
 * fehlende Aussage (P4: sagen, was man weiß, und wie sicher).
 *
 * Bis zum 17.08.2026 rechneten beide Sichten den Quotienten roh und
 * ungekappt; *Cockpit → Jahr* schrieb zusätzlich „über das ganze Fenster
 * gerechnet" darunter — ein Etikett, das die Falschmessung bestätigte, statt
 * sie zu benennen (N-252).
 */

/** Unterhalb dieser Lademenge ist der Quotient Messrauschen, kein Wirkungsgrad.
 *  Spiegel von `MINDEST_LADUNG_KWH`. */
export const MINDEST_LADUNG_KWH = 0.1

/** Herkunft der Aussage — dasselbe Vokabular, das
 *  `v4/KomponentenSektionen.tsx::wirkungsgradHinweis` in Sätze übersetzt. */
export type WirkungsgradQuelle =
  | 'soc_korrigiert'
  | 'roh-unkorrigiert'
  | 'fenster_lang'
  | 'nicht-ermittelbar'
  | 'keine-ladung'

export interface SpeicherWirkungsgrad {
  /** η in Prozent — `null` heißt „nicht ermittelbar", nicht „0". */
  prozent: number | null
  quelle: WirkungsgradQuelle
}

/**
 * η für einen Zeitraum, plus die Herkunft der Aussage.
 *
 * @param langesFensterQuelle Etikett für Aufrufer, deren Zeitraum den
 *   SoC-Übertrag von sich aus ausmittelt (Jahr, gleitendes Fenster). Ersetzt
 *   nur den Namen des unkorrigierten Falls — **nicht** die Obergrenze: auch
 *   über ein Jahr beweist ein Wert über 100 %, dass eine der beiden Mengen
 *   falsch gepflegt ist (häufigste Ursache: „Ladung" nur mit der PV-Ladung
 *   befüllt, Netzladung separat daneben — #281).
 */
export function speicherWirkungsgrad(
  ladungKwh: number | null | undefined,
  entladungKwh: number | null | undefined,
  langesFensterQuelle?: 'fenster_lang',
): SpeicherWirkungsgrad {
  const lad = ladungKwh ?? 0
  const entl = entladungKwh ?? 0
  if (lad <= MINDEST_LADUNG_KWH) return { prozent: null, quelle: 'keine-ladung' }

  const roh = (entl / lad) * 100
  if (roh <= 100) return { prozent: roh, quelle: langesFensterQuelle ?? 'roh-unkorrigiert' }
  return { prozent: null, quelle: 'nicht-ermittelbar' }
}
