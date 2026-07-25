/**
 * Pure Berechnungs-Helper.
 *
 * Schwerpunkt `calcEinspeiseErloes`: Der Helper ist der Frontend-Spiegel von
 * `backend/core/berechnungen/einspeise_erloes.py`. Die Fälle hier entsprechen
 * 1:1 denen in `backend/tests/test_einspeise_erloes.py` (gleiche Zahlen) —
 * driften die beiden Seiten auseinander, zeigt die Finanz-Übersicht einen
 * anderen Einspeiseerlös als das T-Konto auf derselben Seite.
 */
import { describe, it, expect } from 'vitest'
import { calcEinspeiseErloes } from './calculations'

describe('calcEinspeiseErloes (§51 EEG)', () => {
  it('ohne §51-Daten (null) bleibt der volle Erlös', () => {
    const r = calcEinspeiseErloes(1000, null, 8.2)
    expect(r.erloes_euro).toBeCloseTo(82.0, 6)
    expect(r.nicht_verguetet_euro).toBe(0)
    expect(r.nicht_verguetete_kwh).toBe(0)
  })

  it('undefined verhält sich wie null (Feld fehlt in der Response)', () => {
    expect(calcEinspeiseErloes(1000, undefined, 8.2).erloes_euro).toBeCloseTo(82.0, 6)
  })

  it('0 kWh Negativpreis-Volumen ist identisch zum null-Pfad', () => {
    const r = calcEinspeiseErloes(1000, 0, 8.2)
    expect(r.erloes_euro).toBeCloseTo(82.0, 6)
    expect(r.nicht_verguetete_kwh).toBe(0)
  })

  it('zieht das §51-Volumen anteilig ab — voller Erlös bleibt rekonstruierbar', () => {
    const r = calcEinspeiseErloes(1000, 120, 8.2)
    expect(r.erloes_euro).toBeCloseTo((1000 - 120) * 8.2 / 100, 6)
    expect(r.nicht_verguetet_euro).toBeCloseTo(120 * 8.2 / 100, 6)
    expect(r.nicht_verguetete_kwh).toBe(120)
    expect(r.erloes_euro + r.nicht_verguetet_euro).toBeCloseTo(1000 * 8.2 / 100, 6)
  })

  it('klemmt Drift ab: mehr §51-kWh als Einspeisung ergibt nie einen negativen Erlös', () => {
    const r = calcEinspeiseErloes(100, 150, 8.0)
    expect(r.erloes_euro).toBe(0)
    expect(r.nicht_verguetete_kwh).toBe(100)
    expect(r.nicht_verguetet_euro).toBeCloseTo(8.0, 6)
  })

  it('ohne Einspeisung gibt es weder Erlös noch Abzug', () => {
    expect(calcEinspeiseErloes(0, 50, 8.2)).toEqual({
      erloes_euro: 0, nicht_verguetet_euro: 0, nicht_verguetete_kwh: 0,
    })
  })

  it('negative Einspeisung (Datenfehler) liefert 0 statt eines Negativwerts', () => {
    expect(calcEinspeiseErloes(-10, 5, 8.2).erloes_euro).toBe(0)
  })
})
