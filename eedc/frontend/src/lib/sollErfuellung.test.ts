/**
 * SOLL-Erfüllung — die Anzeige liest Quote und Fenster aus der Antwort (N-69, N-356).
 *
 * Bis 03.10.2026 rechnete `lib/sollErfuellung.ts` die Quote selbst; die Proben dafür (gekürzte Augustzahl 148 %
 * statt 19 %, Monatsfortschritt 19 %, SOLL 0 ⇒ keine Quote, Jahr 216 von 243 Tagen ⇒ 120 %) stehen seit dem Umzug
 * in den Backend-Layer mit denselben Zahlen in `backend/tests/test_ergebnis_leiter.py::test_soll_erfuellung_*`
 * bzw. `test_ergebnis_jahr_portiert.py::test_soll_*`. Hier bleibt, was der Client tut: lesen, und das Gate für die
 * Monatsprognose-Kachel.
 */
import { describe, it, expect } from 'vitest'
import {
  istSollAnteilig, sollErfuellungMonatProzent, sollErfuellungProzent,
  sollFensterText, sollMonatGesamtKwh, zeigeMonatsprognose,
} from './sollErfuellung'
import type { SollQuelle } from './sollErfuellung'

const q = (p: Partial<SollQuelle>): SollQuelle => ({
  soll_pv_kwh: null, pv_erzeugung_kwh: null, soll_pv_tage: null, soll_pv_tage_gesamt: null,
  soll_pv_kwh_monat: null, soll_erfuellung_prozent: null, soll_erfuellung_monat_prozent: null,
  soll_fenster_text: null,
  ...p,
} as SollQuelle)

// Winterborn, 4. August 2026: 179,1 kWh SOLL auf 4 von 31 Tagen, 264,75 kWh IST, 1.387,9 kWh SOLL ganzer Monat.
const AUGUST = q({
  soll_pv_kwh: 179.1, pv_erzeugung_kwh: 264.75, soll_pv_tage: 4, soll_pv_tage_gesamt: 31, soll_pv_kwh_monat: 1387.9,
  soll_erfuellung_prozent: 147.82, soll_erfuellung_monat_prozent: 19.08, soll_fenster_text: 'anteilig · 4 von 31 Tagen',
})

describe('Leser der SOLL-Felder', () => {
  it('liest die Quote und das Fenster aus der Antwort — kein eigener Quotient', () => {
    expect(sollErfuellungProzent(AUGUST)).toBe(147.82)
    expect(sollFensterText(AUGUST)).toBe('anteilig · 4 von 31 Tagen')
    expect(istSollAnteilig(AUGUST)).toBe(true)
    // Gegenprobe: stünde hier noch die eigene Rechnung, käme aus 264,75 ÷ 179,1 eine andere Zahl (147,82…≠ 99).
    expect(sollErfuellungProzent({ ...AUGUST, soll_erfuellung_prozent: 99 })).toBe(99)
  })

  it('ohne Feld keine Behauptung — weder Quote noch Fenster', () => {
    const alt = q({ soll_pv_kwh: 1509, pv_erzeugung_kwh: 1843.25 })
    expect(sollErfuellungProzent(alt)).toBeNull()
    expect(sollFensterText(alt)).toBeNull()
    expect(istSollAnteilig(alt)).toBe(false)
  })

  it('volle Monatsprognose: Feld aus der Antwort, nicht zurückgerechnet (dietmar1968, T89667 #155)', () => {
    expect(sollMonatGesamtKwh(AUGUST)).toBe(1387.9)
    expect(sollErfuellungMonatProzent(AUGUST)).toBe(19.08)
    // Die Rückrechnung aus der gerundeten Zahl träfe 1.388,0 — der Grund, warum das Feld geliefert wird.
    expect((179.1 * 31) / 4).toBeCloseTo(1388.0, 1)
  })

  it('die Monatsprognose zeigt sich nur im angefangenen Monat', () => {
    expect(zeigeMonatsprognose(AUGUST)).toBe(true)
    const fertig = q({ soll_pv_kwh: 1509, soll_pv_kwh_monat: 1509, soll_erfuellung_prozent: 122, soll_erfuellung_monat_prozent: 122 })
    expect(zeigeMonatsprognose(fertig)).toBe(false)
    expect(zeigeMonatsprognose(q({ soll_pv_kwh: 0, soll_pv_tage: 0, soll_pv_tage_gesamt: 30 }))).toBe(false)
  })
})
