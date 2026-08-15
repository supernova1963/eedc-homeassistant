/**
 * SOLL-Erfüllung — die Anzeige sagt, über welches Fenster sie spricht (N-69).
 *
 * Das Backend kürzt den SOLL-Nenner im laufenden Monat auf die abgelaufenen
 * Tage (Entscheid Gernot 2026-08-04). Damit stimmt die Prozentzahl — die
 * kWh-Zahl daneben ist dann aber kein Monats-SOLL mehr, und genau das muss die
 * Oberfläche sagen. Zahlen aus der Messung an Gernots Anlage (2026-08-04).
 */
import { describe, it, expect } from 'vitest'
import {
  istSollAnteilig, sollErfuellungMonatProzent, sollErfuellungProzent,
  sollFensterText, sollMonatGesamtKwh, zeigeMonatsprognose,
} from './sollErfuellung'
import type { SollQuelle } from './sollErfuellung'

const q = (p: Partial<SollQuelle>): SollQuelle => ({
  soll_pv_kwh: null, pv_erzeugung_kwh: null, soll_pv_tage: null, soll_pv_tage_gesamt: null,
  soll_pv_kwh_monat: null,
  ...p,
} as SollQuelle)

describe('sollErfuellungProzent', () => {
  it('rechnet die gekürzte Augustzahl (148 %, nicht 19 %)', () => {
    const pct = sollErfuellungProzent(q({
      soll_pv_kwh: 179.1, pv_erzeugung_kwh: 264.75, soll_pv_tage: 4, soll_pv_tage_gesamt: 31,
    }))
    expect(Math.round(pct!)).toBe(148)
  })

  it('gibt null ohne SOLL', () => {
    expect(sollErfuellungProzent(q({ pv_erzeugung_kwh: 264.75 }))).toBeNull()
  })

  it('gibt null bei SOLL 0 — ein Monat in der Zukunft hat keine Erfüllung', () => {
    expect(sollErfuellungProzent(q({
      soll_pv_kwh: 0, pv_erzeugung_kwh: 0, soll_pv_tage: 0, soll_pv_tage_gesamt: 30,
    }))).toBeNull()
  })
})

describe('sollFensterText', () => {
  it('benennt das Fenster im laufenden Monat', () => {
    const d = q({ soll_pv_kwh: 179.1, pv_erzeugung_kwh: 264.75, soll_pv_tage: 4, soll_pv_tage_gesamt: 31 })
    expect(istSollAnteilig(d)).toBe(true)
    expect(sollFensterText(d)).toBe('anteilig · 4 von 31 Tagen')
  })

  it('schweigt im abgeschlossenen Monat', () => {
    const d = q({ soll_pv_kwh: 1509, pv_erzeugung_kwh: 1843.25, soll_pv_tage: 31, soll_pv_tage_gesamt: 31 })
    expect(istSollAnteilig(d)).toBe(false)
    expect(sollFensterText(d)).toBeNull()
  })

  it('schweigt, solange das Backend die Felder nicht liefert', () => {
    // Ältere Antwort ohne die beiden Felder: keine Behauptung über ein Fenster.
    expect(sollFensterText(q({ soll_pv_kwh: 1509, pv_erzeugung_kwh: 1843.25 }))).toBeNull()
  })

  it('summiert im Jahr über die Monate', () => {
    // Jan–Jul voll (212 Tage) + 4 Augusttage von 31.
    const d = q({ soll_pv_kwh: 8107.8, pv_erzeugung_kwh: 9715.02, soll_pv_tage: 216, soll_pv_tage_gesamt: 243 })
    expect(sollFensterText(d)).toBe('anteilig · 216 von 243 Tagen')
    expect(Math.round(sollErfuellungProzent(d)!)).toBe(120)
  })
})

describe('Volle Monatsprognose (Melder dietmar1968, T89667 #155)', () => {
  // Dieselbe Augustzahl wie oben: das Backend hat 1.387,9 kWh auf 4 von 31
  // Tagen gekürzt (179,1 kWh). Die Rückrechnung muss den Ausgangswert exakt
  // treffen — sie ist die Umkehrung einer linearen Kürzung, keine Schätzung.
  const august = q({
    soll_pv_kwh: 179.1, pv_erzeugung_kwh: 264.75, soll_pv_tage: 4, soll_pv_tage_gesamt: 31,
    soll_pv_kwh_monat: 1387.9,
  })

  it('nimmt die volle Prognose aus der Antwort statt sie zurückzurechnen', () => {
    expect(sollMonatGesamtKwh(august)).toBe(1387.9)
    // Die Rückrechnung aus der gerundeten Zahl daneben träfe 1388,0 — der
    // Grund, warum das Feld überhaupt geliefert wird.
    expect((179.1 * 31) / 4).toBeCloseTo(1388.0, 1)
  })

  it('nennt den Monatsfortschritt (19 %) neben der Erfüllung (148 %)', () => {
    // Beide Zahlen sind richtig und beantworten verschiedene Fragen — genau
    // deshalb steht die Prognose als ZWEITE Angabe daneben, statt die erste zu
    // ersetzen.
    expect(Math.round(sollErfuellungMonatProzent(august)!)).toBe(19)
    expect(Math.round(sollErfuellungProzent(august)!)).toBe(148)
  })

  it('zeigt sich nur im angefangenen Monat', () => {
    expect(zeigeMonatsprognose(august)).toBe(true)
    // Abgeschlossen: „bis heute" und „ganzer Monat" sind dieselbe Zahl.
    const fertig = q({
      soll_pv_kwh: 1509, pv_erzeugung_kwh: 1843.25, soll_pv_tage: 31, soll_pv_tage_gesamt: 31,
      soll_pv_kwh_monat: 1509,
    })
    expect(zeigeMonatsprognose(fertig)).toBe(false)
    // Zukunft: null abgelaufene Tage, nichts zurückzurechnen (keine Division).
    // Zukunft bzw. Jahres-Aggregat: das Feld ist nicht belegt.
    const zukunft = q({
      soll_pv_kwh: 0, pv_erzeugung_kwh: 0, soll_pv_tage: 0, soll_pv_tage_gesamt: 30,
    })
    expect(sollMonatGesamtKwh(zukunft)).toBeNull()
    expect(zeigeMonatsprognose(zukunft)).toBe(false)
    // Ältere Antwort ohne die Fenster-Felder: keine Behauptung.
    expect(zeigeMonatsprognose(q({ soll_pv_kwh: 1509, pv_erzeugung_kwh: 1843.25 }))).toBe(false)
  })
})
