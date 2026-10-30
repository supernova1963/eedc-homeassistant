import type { StrompreisVerwendung } from '../types'

/**
 * Hinweistexte an den Tarif-Eingaben.
 *
 * Anlass: Forum T89667 #120 (Phir0n) — „ob flat mit der eingegebenen Zahl
 * gerechnet wird oder der Misch-Vergütungssatz im Hintergrund anhand der
 * Anlagengröße berechnet wird". eedc rechnet **flat**
 * (`docs/BERECHNUNGEN.md` §3.2: `Einspeise-Erlös = Σ(Einspeisung) ×
 * Einspeisevergütung / 100`); eine EEG-Leistungsstaffel kennt es an keiner
 * Stelle, und es soll sie auch nicht selbst ermitteln (Entscheid 2026-08-08:
 * die Rahmenbedingungen kennt nur der Betreiber). Zugesagt in T89667 #122.
 *
 * Der Text steht hier statt zweimal im Formular, weil ihn zwei Eingaben
 * tragen: die Pflege-Route (`pages/StrompreiseTeile.tsx`) und der Setup-Wizard
 * (`components/setup-wizard/steps/StrompreiseStep.tsx`). Ein Hinweis, der an
 * einer der beiden Stellen anders lautet, ist derselbe Befund noch einmal.
 */

/**
 * Was mit der eingetragenen Einspeisevergütung geschieht — und was der
 * Eingebende deshalb eintragen darf.
 *
 * Bewusst **kein** Rechenhilfe-Angebot: der Satz erklärt, dass eedc nicht
 * rechnet, er rechnet nicht selbst vor (Entscheid 2026-08-08).
 */
export const EINSPEISEVERGUETUNG_FLAT_HINWEIS =
  'eedc rechnet flat mit diesem Satz — bei gestaffelter EEG-Vergütung den nach kWp gewichteten Mischsatz eintragen'

/**
 * Anwenderwort je Tarif-Verwendung — die Tarifliste (`pages/StrompreiseTeile.tsx`) und der Ausweis der Grundgebühr
 * (N-769) sprechen denselben Namen. Spiegel im Backend: `monats_fakten/tarif.py::VERWENDUNG_LABEL` (PDF-Monatsbericht).
 */
export function verwendungLabel(v: StrompreisVerwendung | string): string {
  switch (v) {
    case 'waermepumpe': return 'Wärmepumpe'
    case 'wallbox': return 'Wallbox'
    default: return 'Standard'
  }
}

/**
 * N-769 (30.10.2026): die Grundgebühr je Tarif, wenn ein eigener Wärmepumpen- oder Wallbox-Tarif beiträgt — als
 * Klammerzusatz zur Summe („ (Standard 14,00 € · Wärmepumpe 10,00 €)"); ohne Aufteilung leer. Die Beträge kommen
 * fertig aus dem Backend (`grundgebuehr_aufteilung`), hier wird nur formatiert.
 */
export function grundgebuehrAufteilungText(
  aufteilung: Record<string, number> | null | undefined,
  fmt: (euro: number) => string,
): string {
  if (!aufteilung) return ''
  const teile = Object.entries(aufteilung).map(([v, euro]) => `${verwendungLabel(v)} ${fmt(euro)} €`)
  return teile.length > 0 ? ` (${teile.join(' · ')})` : ''
}
