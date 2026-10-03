/**
 * Cockpit/Jahr — welche Monate zählen zum Jahr? (Fund N-65, Paket P-12)
 *
 * Bis v4.0.6 galt „ein Monat zählt, wenn er eine aggregierte Zeile hat" (+ der
 * heutige). Eine `Monatsdaten`-Zeile entsteht aber erst beim **Monatsabschluss** —
 * ein längst gelaufener Monat ohne Abschluss fiel damit komplett aus der Jahreszahl.
 *
 * An der Box gemessen (Winterborn, 10.100.1.13, 2026-08-02):
 * `/monatsdaten/aggregiert/1` meldet für 2026 Jan–Jun, `/aktueller-monat` liefert für
 * Juli aber 1.843,25 kWh PV. Angezeigt waren 7.703 kWh statt 9.547 — knapp ein
 * Viertel der Jahresernte fehlte, und zwar ausgerechnet der stärkste Monat.
 *
 * Die Gegenrichtung ist genauso gemessen und wird hier mitgesichert: `/aktueller-monat`
 * beantwortet AUCH Monate vor der Inbetriebnahme (Januar 2023 → `soll_pv_kwh: 396,1`).
 * Ein blindes 1–12-Fanout hätte das SOLL aufgebläht und die SOLL-Erfüllung gedrückt.
 */
import { describe, it, expect } from 'vitest'
import { kennzahlenFensterAus, monatsFensterAus } from '../lib/monatsFenster'

const bis = (n: number) => Array.from({ length: n }, (_, i) => i + 1)

// Die Monatsmenge (`zuLadendeMonate`), „Messung oder nur Stammdaten?" (`monatHatDaten`) und die Grundgesamtheit
// des Vergleichs (`abgeschlosseneMonate`) entscheidet seit 03.10.2026 die Jahresroute
// (`backend/services/jahres_aggregat.py`). Ihre Proben stehen mit denselben Zahlen (Winterborn, 2. August 2026) in
// `backend/tests/test_ergebnis_jahr_portiert.py::test_menge_*`, `test_monat_hat_daten_*`,
// `test_abgeschlossene_monate`. Hier bleibt die Beschriftung.

describe('kennzahlenFensterAus — der Unterschied wird benannt', () => {
  it('Kopfzahl umfasst mehr Monate als der Vergleich ⇒ Fenster steht dran', () => {
    expect(kennzahlenFensterAus(bis(8), bis(7))).toBe('Jan–Aug')
  })

  it('Dezember: ein VOLLES Fenster ist hier gerade erklärungsbedürftig', () => {
    // Die 12-Monats-Ausnahme von `monatsFensterAus` darf hier NICHT greifen —
    // Jan–Dez enthält den angefangenen Dezember, der Vergleich nur Jan–Nov.
    expect(kennzahlenFensterAus(bis(12), bis(11))).toBe('Jan–Dez')
    expect(monatsFensterAus(bis(12))).toBeNull()
  })

  it('REGRESSION — deckungsgleich ⇒ nichts zu sagen', () => {
    expect(kennzahlenFensterAus(bis(12), bis(12))).toBeNull()
    expect(kennzahlenFensterAus([1, 2, 4], [1, 2, 4])).toBeNull()
    expect(kennzahlenFensterAus([], [])).toBeNull()
  })

  it('Lücke im Jahr wird als unterbrochenes Fenster geschrieben', () => {
    expect(kennzahlenFensterAus([1, 2, 4, 5, 6, 7, 8], [1, 2, 4, 5, 6, 7])).toBe('Jan–Feb, Apr–Aug')
  })
})
