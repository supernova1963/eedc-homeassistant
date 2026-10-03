/**
 * Ergebnis-Herleitung — der Client FORMATIERT, was das Backend mit dem Wert liefert (Style-Guide A6, N-600).
 *
 * Netto-Ertrag, Ergebnis vor Betriebskosten und Monats-/Jahresergebnis entstehen seit 03.10.2026 an EINER Stelle,
 * im Backend-Layer `core/berechnungen/ergebnis.py` („Ergebnis-Leiter"). Die Antwort trägt je Stufe den Wert UND
 * die eingesetzten Werte (`ergebnis_herleitung`). Bis dahin bildete der Browser das Monatsergebnis selbst
 * (`gesamtnettoertrag − Betriebskosten + Sonstiges`) und setzte im Tooltip das Sammelfeld „Gesamt-Nettoertrag" ein, in
 * dem die Stromrechnung unsichtbar steckte (Blockmove #398: „Der Nettoertrag wären 303,39 €, die Stromkosten 53,48 €").
 *
 * ⛔ Hier wird NICHT gerechnet — nur Text gesetzt. Der Wächter `check:ergebnis-roh` hält das für die Cockpit- und
 * Finanzen-Dateien fest.
 */
import { fmtCalc } from '../components/ui/FormelTooltip'
import type { ErgebnisStufe } from '../api/aktuellerMonat'

const betrag = (v: number | null | undefined) => `${fmtCalc(Math.abs(v ?? 0), 2)} €`

/**
 * Die eingesetzten Werte einer Stufe als Rechenzeile: `32,00 € Einspeise-Erlös + 180,00 € … − 5,70 € USt …`.
 *
 * `zwischen` setzt einen Zwischenstand VOR den Posten mit diesem Antwortfeld — so steht die Stufe 2 (ohne eigenen
 * Namen im UI, Gegenprüfung G4) als `= 249,91 € vor Betriebskosten` in der Zeile, bevor die Betriebskosten abgehen.
 * `undefined`, wenn die Stufe keinen Wert hat: neben „—" steht keine Rechnung (A6, zweite Regelhälfte).
 */
export function berechnungAus(
  stufe: ErgebnisStufe | null | undefined,
  zwischen?: { vorFeld: string; wert: number | null | undefined; label: string },
): string | undefined {
  if (!stufe || stufe.ergebnis_euro == null || stufe.eingesetzte_werte.length === 0) return undefined
  return stufe.eingesetzte_werte.map((w, i) => {
    const vor = zwischen && w.feld === zwischen.vorFeld && zwischen.wert != null && i > 0
      ? ` = ${fmtCalc(zwischen.wert, 2)} € ${zwischen.label}`
      : ''
    // Das Rechenzeichen folgt dem BETRAG (er trägt sein Vorzeichen): ein Ertragsposten kann negativ sein (Sonstige
    // Positionen mit mehr Ausgaben als Erträgen) und steht dann als „− 530,00 €", nicht als „+ 530,00 €". Nur bei 0,00 €
    // entscheidet die Rolle — ein Aufwand von 0,00 € bleibt ein Aufwand.
    const negativ = (w.betrag_euro ?? 0) < 0 || ((w.betrag_euro ?? 0) === 0 && w.vorzeichen < 0)
    const op = i === 0 ? (negativ ? '− ' : '') : (negativ ? ' − ' : ' + ')
    return `${vor}${op}${betrag(w.betrag_euro)} ${w.name}`
  }).join('')
}

/** `= 206,30 €` — oder `undefined` ohne Wert. */
export function ergebnisZeile(wert: number | null | undefined): string | undefined {
  return wert != null ? `= ${fmtCalc(wert, 2)} €` : undefined
}

/** Warum eine Stufe leer bleibt bzw. was als 0 eingegangen ist — `fehlt: Stromrechnung` (ADR-002/P4). */
export function fehlendHinweis(fehlende: readonly string[] | null | undefined): string | undefined {
  if (!fehlende || fehlende.length === 0) return undefined
  return `fehlt: ${fehlende.join(' · ')}`
}

/** `= 249,91 € · fehlt: WP-Ersparnis` — der Wert mit den als 0 eingegangenen optionalen Posten (P4). */
export function ergebnisMitLuecken(
  wert: number | null | undefined, fehlende: readonly string[] | null | undefined,
): string | undefined {
  const z = ergebnisZeile(wert)
  if (z == null) return undefined
  const f = fehlendHinweis(fehlende)
  return f ? `${z} · ${f}` : z
}
