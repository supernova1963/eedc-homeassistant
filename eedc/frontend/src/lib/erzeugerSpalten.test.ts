/**
 * Spalten je Erzeuger (#350) — die drei Grenzen der Regel.
 *
 * Sie stehen hier und nicht in der Tabelle, weil dieselbe Regel zwei Sichten
 * bedient (Tageswerte-Tabelle und Cockpit → Tag).
 */
import { describe, it, expect } from 'vitest'
import { baueErzeugerSpalten, pvRestKw } from './erzeugerSpalten'
import { getTagWert, ERZEUGER_METRIK_PREFIX } from './werte'
import type { Investition } from '../types'
import type { TagWerte } from '../api/energie_profil'

const inv = (id: number, typ: string, bezeichnung: string, extra: Partial<Investition> = {}) => ({
  id, anlage_id: 1, typ, bezeichnung, aktiv: true, ...extra,
} as Investition)

const tag = (datum: string, erzeuger?: Record<string, number> | null) => ({
  datum, erzeuger_kwh: erzeuger,
} as TagWerte)

const DACH = inv(7, 'pv-module', 'Dach Süd')
const BKW = inv(9, 'balkonkraftwerk', 'BKW Vorgarten')

describe('baueErzeugerSpalten', () => {
  it('macht je gemessenem Erzeuger eine Spalte', () => {
    const r = baueErzeugerSpalten(
      [tag('2026-05-10', { '7': 5.4, '9': 0.6 })],
      [DACH, BKW], '2026-05-01', '2026-05-31',
    )
    expect(r.metriken.map((m) => m.key)).toEqual([
      `${ERZEUGER_METRIK_PREFIX}7`, `${ERZEUGER_METRIK_PREFIX}9`,
    ])
    expect(r.metriken[0].label).toBe('Dach Süd')
    expect(r.ohneMessung).toEqual([])
  })

  it('schweigt bei nur einem Erzeuger — dort ist die Gerätespalte die Anlagenspalte', () => {
    const r = baueErzeugerSpalten(
      [tag('2026-05-10', { '7': 5.4 })], [DACH], '2026-05-01', '2026-05-31',
    )
    expect(r.metriken).toEqual([])
    expect(r.ohneMessung).toEqual([])
  })

  it('benennt Erzeuger ohne einen einzigen Tageswert', () => {
    const r = baueErzeugerSpalten(
      [tag('2026-05-10', { '7': 5.4 })], [DACH, BKW], '2026-05-01', '2026-05-31',
    )
    expect(r.metriken.map((m) => m.key)).toEqual([`${ERZEUGER_METRIK_PREFIX}7`])
    expect(r.ohneMessung.map((i) => i.bezeichnung)).toEqual(['BKW Vorgarten'])
  })

  it('meldet ein Gerät nicht, das es im Zeitraum noch gar nicht gab', () => {
    const spaeter = inv(9, 'balkonkraftwerk', 'BKW Vorgarten', { anschaffungsdatum: '2026-06-01' })
    const r = baueErzeugerSpalten(
      [tag('2026-05-10', { '7': 5.4 })], [DACH, spaeter], '2026-05-01', '2026-05-31',
    )
    expect(r.imZeitraum.map((i) => i.id)).toEqual([7])
    expect(r.ohneMessung).toEqual([])
  })

  it('lässt stillgelegte Geräte im Zeitraum davor stehen', () => {
    const alt = inv(9, 'balkonkraftwerk', 'BKW alt', { stilllegungsdatum: '2026-05-20' })
    const r = baueErzeugerSpalten(
      [tag('2026-05-10', { '7': 5.4, '9': 0.6 })], [DACH, alt], '2026-05-01', '2026-05-31',
    )
    expect(r.metriken).toHaveLength(2)
  })

  it('zählt Wärmepumpen und andere Verbraucher nicht als Erzeuger', () => {
    const wp = inv(3, 'waermepumpe', 'WP')
    const r = baueErzeugerSpalten(
      [tag('2026-05-10', { '7': 5.4 })], [DACH, wp], '2026-05-01', '2026-05-31',
    )
    expect(r.imZeitraum.map((i) => i.id)).toEqual([7])
  })
})

describe('getTagWert für Erzeuger-Spalten', () => {
  it('liest den Wert aus erzeuger_kwh', () => {
    expect(getTagWert(tag('2026-05-10', { '7': 5.4 }), `${ERZEUGER_METRIK_PREFIX}7`)).toBe(5.4)
  })

  it('gibt null statt 0, wenn für den Tag nichts gemessen wurde', () => {
    // 0 hieße „lief, brachte nichts" — das ist eine andere Aussage.
    expect(getTagWert(tag('2026-05-10', { '7': 5.4 }), `${ERZEUGER_METRIK_PREFIX}9`)).toBeNull()
    expect(getTagWert(tag('2026-05-10', null), `${ERZEUGER_METRIK_PREFIX}7`)).toBeNull()
  })

  it('lässt die regulären Registry-Keys unberührt', () => {
    const zeile = { datum: '2026-05-10', erzeugung: 12.5 } as TagWerte
    expect(getTagWert(zeile, 'erzeugung')).toBe(12.5)
  })
})

describe('pvRestKw — die Stapelhöhe bleibt die Erzeugung', () => {
  it('ist 0, wenn die Geräte die Anlagen-PV voll abdecken', () => {
    expect(pvRestKw(6.0, { pv_7: 5.4, pv_9: 0.6 }, ['pv_7', 'pv_9'])).toBeCloseTo(0)
  })

  it('trägt den Anteil der Geräte ohne Sensor', () => {
    expect(pvRestKw(6.0, { pv_7: 5.4 }, ['pv_7', 'pv_9'])).toBeCloseTo(0.6)
  })

  it('wird nie negativ, wenn die Geräte-Σ über der Anlagen-PV liegt (#356)', () => {
    // Sonst zöge eine negative Fläche den gestapelten Chart unter die Nulllinie.
    expect(pvRestKw(4.0, { pv_7: 5.0 }, ['pv_7'])).toBe(0)
  })

  it('behandelt eine fehlende Stunde als 0 statt NaN', () => {
    expect(pvRestKw(null, null, ['pv_7'])).toBe(0)
  })
})
