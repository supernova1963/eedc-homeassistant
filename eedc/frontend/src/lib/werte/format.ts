/**
 * Zahl-Formatierung für die Werte-Tabelle — delegiert an die zentrale Zahl-SoT
 * `fmtZahl` (R1: de-DE mit Tausenderpunkt). Eigener Name bleibt für die Werte-
 * Modul-Aufrufer; EINE Format-Wahrheit (kein zweiter toLocaleString-Wrapper).
 */
import { fmtZahl } from '../einheiten'

export function fmtWert(v: number | null, decimals: number): string {
  return fmtZahl(v, decimals)
}

/**
 * Denselben Wert als Zahl, den {@link fmtWert} als Text zeigt.
 *
 * Wer eine Zelle aus zwei anderen Zellen erklärt (die Δ-Spalte), muss mit den
 * **angezeigten** Zahlen rechnen — sonst widerspricht die Erklärung dem, was
 * daneben steht. Gemeldet von Striker (T89667 #162) an einer Tageszeile:
 * „Aktuell 0 · Vorperiode 12 · Δ ▼ 11 (−97,6 %)" — 12 − 0 ist nicht 11, und
 * zwei Zeilen tiefer stand zweimal 0 nebeneinander mit „▼ 0 (−73,3 %)".
 * Ursache war die gemischte Genauigkeit: die Spalten rundeten, die Δ-Spalte
 * rechnete mit den Rohwerten weiter. Dieselbe Klasse wie der Cent-Widerspruch
 * zwischen Kachel und Tabelle (T89667 #163).
 *
 * Rundung über den **Betrag**, weil `toLocaleString` „halfExpand" nutzt
 * (−0,5 → „−1"), `Math.round` dagegen zur +∞ hin rundet (−0,5 → −0). Ohne das
 * wichen Text und Zahl bei negativen Werten um eine Einheit voneinander ab —
 * die Finanz-Metriken kennen negative Werte.
 */
export function alsAngezeigt(v: number, decimals: number): number {
  const faktor = 10 ** decimals
  return Math.sign(v) * Math.round(Math.abs(v) * faktor) / faktor
}
