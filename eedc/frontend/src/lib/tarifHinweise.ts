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
    // F12 (N-770/N-771 E6): ein Tarif für Wärmepumpe und Wallbox hinter einem gemeinsamen Zähler.
    case 'waermepumpe_wallbox': return 'Wärmepumpe und Wallbox'
    default: return 'Standard'
  }
}

/** F12: Ist ein Anteil der des gemeinsamen Zählers für Wärmepumpe und Wallbox? */
export const istGemeinsamerZaehler = (verwendung: string): boolean => verwendung === 'waermepumpe_wallbox'

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

/** N-770/N-771: ein Anteil des Netzbezugs zum eigenen Komponenten-Tarif — so liefert ihn das Backend
 *  (`monats_fakten.tarif.KomponentenAnteile.als_dict`). */
export interface NetzbezugAnteil {
  verwendung: string
  kwh: number
  cent: number | null
  euro: number
  gemessen_kwh: number
  geklemmt: boolean
}

/**
 * N-770/N-771 (30.10.2026): die Rechnung der Ø-Preis-Kachel mit gemessenem Netzbezug zum WP-/Wallbox-Tarif —
 * «117,9 kWh × 30,0 ct/kWh + 256 kWh × 22,0 ct/kWh (Wärmepumpe)». Ohne Anteile `null` (dann bleibt die alte Zeile).
 * Ein geklemmter Anteil sagt es («gemessen 105,1 kWh, begrenzt»). Gerechnet wird nichts außer dem Rest (Netzbezug −
 * Σ Anteile) für die Anzeige; die Beträge kommen fertig aus dem Backend.
 */
export function netzbezugAnteileBerechnung(
  netzbezugKwh: number,
  haushaltCent: number,
  anteile: NetzbezugAnteil[] | null | undefined,
  fmtKwh: (kwh: number) => string,
  fmtCent: (cent: number) => string,
): string | null {
  if (!anteile || anteile.length === 0) return null
  const rest = netzbezugKwh - anteile.reduce((s, a) => s + a.kwh, 0)
  const teile = anteile.map((a) => {
    const klemme = a.geklemmt ? `, gemessen ${fmtKwh(a.gemessen_kwh)} kWh, begrenzt` : ''
    // F12: der gemeinsame Zähler nennt sich als solcher («Wärmepumpe und Wallbox, gemeinsamer Zähler»).
    const name = verwendungLabel(a.verwendung) + (istGemeinsamerZaehler(a.verwendung) ? ', gemeinsamer Zähler' : '')
    return `${fmtKwh(a.kwh)} kWh × ${a.cent != null ? fmtCent(a.cent) : '—'} ct/kWh (${name}${klemme})`
  })
  return [`${fmtKwh(rest)} kWh × ${fmtCent(haushaltCent)} ct/kWh`, ...teile].join(' + ')
}

/**
 * N-770: der Zusatz an der Eigenverbrauchs-Ersparnis — der PV-Anteil der Wärmepumpe, den eedc zum WP-Tarif statt
 * zum Haushaltspreis bewertet («davon 170,7 kWh PV-Strom der Wärmepumpe zum WP-Tarif 22,0 ct/kWh»). Ohne Messung leer.
 */
export function evWpTarifText(
  kwh: number | null | undefined,
  cent: number | null | undefined,
  fmtKwh: (kwh: number) => string,
  fmtCent: (cent: number) => string,
): string {
  if (kwh == null || kwh <= 0) return ''
  const preis = cent != null ? ` ${fmtCent(cent)} ct/kWh` : ''
  return ` · davon ${fmtKwh(kwh)} kWh PV-Strom der Wärmepumpe zum WP-Tarif${preis}`
}
