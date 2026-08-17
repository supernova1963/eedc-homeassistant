/**
 * N-244 — die Feldauswahl eines *Sonstiges*-Geräts rät keine Kategorie.
 *
 * Client-Hälfte des Backend-Wächters `test_n244_sonstiges_kategorie_sot.py`.
 * Beide Seiten beantworten dieselbe Frage, und genau deshalb müssen sie
 * dieselbe Antwort geben: Die Zuordnungs- und Erfassungsflächen rendern aus
 * diesem Spiegel, während der Snapshot-Pfad im Backend entscheidet, welches
 * Feld überhaupt gesucht wird. Läuft der Spiegel weg, bietet die Oberfläche
 * wieder Felder an, die für dieses Gerät nirgends gelesen werden (N-259-Klasse).
 */
import { describe, it, expect } from 'vitest'
import { getFelderFuerSonstiges, getFelderFuerInvestition } from './fieldDefinitions'

const namen = (fs: { feld: string }[]) => fs.map(f => f.feld)

const ERZEUGER = ['erzeugung_kwh', 'eigenverbrauch_kwh', 'einspeisung_kwh', 'einspeise_erloes_euro']
const VERBRAUCHER = ['verbrauch_sonstig_kwh', 'bezug_pv_kwh', 'bezug_netz_kwh']

describe('N-244 — Sonstiges ohne gepflegte Kategorie', () => {
  it('bietet beide Richtungen an, statt eine zu raten', () => {
    const felder = namen(getFelderFuerSonstiges(undefined))
    for (const f of [...VERBRAUCHER, ...ERZEUGER]) expect(felder).toContain(f)
  })

  it('nennt die Verbrauchsseite zuerst — die Lesart aller wertführenden Pfade', () => {
    expect(namen(getFelderFuerSonstiges(null))[0]).toBe('verbrauch_sonstig_kwh')
  })

  it.each([undefined, null, '', 'erzueger', 'Verbraucher', 'unsinn'])(
    'behandelt %p wie „nicht gepflegt" (auch den Tippfehler)',
    (kat) => {
      expect(namen(getFelderFuerSonstiges(kat as string))).toEqual(
        namen(getFelderFuerSonstiges(undefined)),
      )
    },
  )

  it('dupliziert kein Feld, obwohl `speicher` beide Seiten mitbringt', () => {
    const felder = namen(getFelderFuerSonstiges(undefined))
    expect(new Set(felder).size).toBe(felder.length)
  })

  it('erreicht die Route, die die Erfassungsfläche wirklich aufruft', () => {
    // Der Befund saß NICHT in `getFelderFuerSonstiges`, sondern im Aufrufer,
    // der ihm `'erzeuger'` schon vorgekaut übergab.
    const felder = namen(getFelderFuerInvestition('sonstiges', {}))
    for (const f of [...VERBRAUCHER, ...ERZEUGER]) expect(felder).toContain(f)
  })
})

describe('N-244 — ein gepflegtes Gerät ist ein beweisbarer No-op', () => {
  it.each([
    ['erzeuger', ERZEUGER],
    ['verbraucher', VERBRAUCHER],
    ['speicher', ['erzeugung_kwh', 'verbrauch_sonstig_kwh']],
  ])('%s bleibt exakt bei seinen Feldern', (kat, erwartet) => {
    expect(namen(getFelderFuerSonstiges(kat as string))).toEqual(erwartet)
    expect(namen(getFelderFuerInvestition('sonstiges', { kategorie: kat }))).toEqual(erwartet)
  })

  it('hält die Prämisse des Fundes: die zwei Richtungen sind disjunkt', () => {
    const e = new Set(namen(getFelderFuerSonstiges('erzeuger')))
    const v = namen(getFelderFuerSonstiges('verbraucher'))
    expect(v.filter(f => e.has(f))).toEqual([])
  })
})
