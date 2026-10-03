/**
 * Die Rechenzeile der Ergebnis-Herleitung — das Rechenzeichen folgt dem Betrag.
 *
 * Gefunden beim Bau des Ergebnisgrößen-Pakets (03.10.2026, HA-Golden-Master): ein Ertragsposten mit negativem Betrag
 * (Sonstige Positionen, netto eine Ausgabe) stand als „+ 530,00 €", weil das Zeichen aus der ROLLE des Postens kam und
 * der Betrag als Absolutwert. Die Zahl daneben war richtig, die Rechnung ging nicht auf.
 *
 * Schwesterdateien: backend/tests/test_ergebnis_symmetrie_monat_jahr.py (dieselbe Regel im HA-Sensortext).
 */
import { describe, it, expect } from 'vitest'
import { berechnungAus } from './ergebnisHerleitung'

const stufe = (werte: Array<[string, number, string, 1 | -1]>, ergebnis: number) => ({
  formel: '',
  eingesetzte_werte: werte.map(([name, betrag_euro, feld, vorzeichen]) => ({ name, betrag_euro, feld, vorzeichen })),
  ergebnis_euro: ergebnis,
})

describe('berechnungAus — Rechenzeichen', () => {
  it('ein negativer Ertragsposten steht mit Minus', () => {
    const z = berechnungAus(stufe([
      ['Einspeise-Erlös', 100, 'einspeise_erloes_euro', 1],
      ['Sonstige Positionen', -530, 'sonstige_netto_euro', 1],
    ], -430))
    expect(z).toContain('− 530,00 € Sonstige Positionen')
    expect(z).not.toContain('+ 530,00')
  })

  it('ein Aufwand von 0,00 € bleibt ein Aufwand', () => {
    const z = berechnungAus(stufe([
      ['Einspeise-Erlös', 100, 'einspeise_erloes_euro', 1],
      ['Betriebskosten', 0, 'betriebskosten_anteilig_euro', -1],
    ], 100))
    expect(z).toContain('− 0,00 € Betriebskosten')
  })

  it('ein Aufwand mit Betrag steht mit Minus, ein Ertrag mit Plus', () => {
    const z = berechnungAus(stufe([
      ['Einspeise-Erlös', 100, 'einspeise_erloes_euro', 1],
      ['Eigenverbrauchs-Ersparnis', 50, 'ev_ersparnis_euro', 1],
      ['Stromrechnung', -40, 'netzbezug_kosten_euro', -1],
    ], 110))
    expect(z).toBe('100,00 € Einspeise-Erlös + 50,00 € Eigenverbrauchs-Ersparnis − 40,00 € Stromrechnung')
  })
})
