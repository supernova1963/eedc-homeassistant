/**
 * Die vier Kennzahl-Formeln des Clients — bis E6 ohne Test (M9).
 *
 * `lib/calculations.ts` liefert Autarkie, Eigenverbrauchsquote, spezifischen
 * Ertrag und COP. Gemessen am 2026-08-24: **keine** der 159 Testdateien
 * importierte das Modul.
 *
 * Der Kern ist jeweils der **Nenner-Null-Fall**. Zwei der vier Funktionen
 * antworten darauf verschieden — die Quoten mit `0`, der COP mit `null` —,
 * und das ist Absicht: „0 % Autarkie" ist eine Aussage, „COP 0" wäre eine
 * Behauptung über eine Wärmepumpe, die gar nicht gelaufen ist.
 */
import { describe, it, expect } from 'vitest'
import {
  calcAutarkie,
  calcEigenverbrauchsquote,
  calcSpezifischerErtrag,
} from './calculations'

describe('calcAutarkie', () => {
  it('ist der Anteil des Eigenverbrauchs am Gesamtverbrauch, in Prozent', () => {
    expect(calcAutarkie(300, 1000)).toBe(30)
  })

  it('liefert 100 bei vollständiger Deckung', () => {
    expect(calcAutarkie(1000, 1000)).toBe(100)
  })

  it('liefert 0 ohne Verbrauch — nicht NaN, nicht Infinity', () => {
    expect(calcAutarkie(500, 0)).toBe(0)
  })

  it('liefert 0 bei negativem Verbrauch (Zähler-Glitch)', () => {
    expect(calcAutarkie(500, -10)).toBe(0)
  })
})

describe('calcEigenverbrauchsquote', () => {
  it('ist der Anteil des Eigenverbrauchs an der Erzeugung', () => {
    expect(calcEigenverbrauchsquote(250, 1000)).toBe(25)
  })

  it('rechnet gegen die ERZEUGUNG, nicht gegen den Verbrauch', () => {
    // Dieselben Zahlen, andere Bedeutung — die Verwechslung ist die Klasse,
    // gegen die #326 und DI-2 gebaut wurden.
    expect(calcEigenverbrauchsquote(300, 1000)).toBe(calcAutarkie(300, 1000))
    expect(calcEigenverbrauchsquote(300, 500)).not.toBe(calcAutarkie(300, 1000))
  })

  it('liefert 0 ohne Erzeugung', () => {
    expect(calcEigenverbrauchsquote(100, 0)).toBe(0)
  })
})

describe('calcSpezifischerErtrag', () => {
  it('ist kWh je kWp', () => {
    expect(calcSpezifischerErtrag(9500, 10)).toBe(950)
  })

  it('liefert 0 ohne Nennleistung — auch bei null und undefined', () => {
    expect(calcSpezifischerErtrag(9500, 0)).toBe(0)
    expect(calcSpezifischerErtrag(9500, null)).toBe(0)
    expect(calcSpezifischerErtrag(9500, undefined)).toBe(0)
  })
})

