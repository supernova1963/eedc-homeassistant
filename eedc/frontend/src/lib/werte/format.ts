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

/**
 * Prozentualer Abstand zweier Werte — gebildet aus den **angezeigten** Zahlen.
 *
 * Der geteilte Rechenweg hinter den Vergleichs-Badges (Cockpit Tag/Monat/Jahr,
 * T-Konto). Er löst dieselbe Klasse wie {@link alsAngezeigt} für die Δ-Spalte:
 * Ein Badge, das zwischen zwei gerundeten Zahlen steht, muss deren Verhältnis
 * beschreiben und nicht das der Rohwerte dahinter. Gemessen am 29.08.2026 stand
 * sonst „151 · 151 · ▲ 1 %" (Rohwerte 151,4 / 150,6) und „250,00 · 249,50 ·
 * ▲ 0 %" — beide Richtungen des Widerspruchs, denselben Ursprung.
 *
 * `pfeil` ist genau dann `'='`, wenn beide Zahlen gleich aussehen. Das ist die
 * Regel, die der Baum an zwei Stellen schon trägt: die Δ-Spalte der
 * Werte-Tabelle zeigt `=`, und `PrognoseVergleichTeile::Abweichung` begründet
 * sie wörtlich — „ein ‚▼ 0,0' behauptet eine Unterschreitung, die die
 * angezeigte Zahl gar nicht hergibt".
 *
 * `null` heißt „kein Verhältnis bildbar": Die Bezugsgröße sieht wie eine 0 aus.
 * Der Test auf die **angezeigte** Bezugsgröße ist Absicht — bei 0,4 kWh und
 * `decimals = 0` steht dort „0", und ein Prozentwert relativ zu einer
 * angezeigten Null hat keine Grundlage.
 */
export interface AngezeigtesDelta {
  /** Differenz der angezeigten Zahlen (a − b). */
  diff: number
  /** Prozentualer Abstand, bezogen auf die angezeigte Bezugsgröße. */
  pct: number
  /** '▲' | '▼' | '=' — '=' bei sichtbarer Gleichheit. */
  pfeil: '▲' | '▼' | '='
}

export function angezeigtesDelta(a: number, b: number, decimals: number): AngezeigtesDelta | null {
  const gezeigtA = alsAngezeigt(a, decimals)
  const gezeigtB = alsAngezeigt(b, decimals)
  if (gezeigtB === 0) return null
  const diff = gezeigtA - gezeigtB
  return {
    diff,
    pct: (diff / Math.abs(gezeigtB)) * 100,
    pfeil: diff > 0 ? '▲' : diff < 0 ? '▼' : '=',
  }
}
