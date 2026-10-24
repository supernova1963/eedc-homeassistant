/**
 * Layout der Überblick-Kacheln (P-433-2 E1) — die Fälle des Bauplans, die
 * Kreuzungsprobe, die Kapazität je Breite, Reihen-y aus der Geometrie und die
 * Schrift gegen die Energiefluss-Mindestschrift.
 */
import { describe, it, expect } from 'vitest'
import { computeDims, kapazitaet } from '../../live/energieFlussLayout'
import { STAPEL_VERSATZ } from '../../live/EnergieFlussKachel'
import { PANORAMA_BREITE, PANORAMA_HOEHE, type AnkerId } from './waermePanoramaAnker'
import { hatKreuzung, layoutUeberblick, reihenY, schneiden, zeichenbreite, type LayoutKachel, type Platz } from './ueberblickLayout'

const geraet = (id: string, anker: AnkerId): LayoutKachel => ({ id, art: 'geraet', anker })
const wert = (id: string, anker: AnkerId): LayoutKachel => ({ id, art: 'wert', anker })
const innen = (n: number): LayoutKachel[] =>
  Array.from({ length: n }, (_, i) => ({ id: `innen-${i + 1}`, art: 'innengeraet' as const, anker: (['L', 'M', 'N'] as AnkerId[])[Math.min(i, 2)] }))

/** Was in einer Reihe steht: Einzel-ID oder „Gruppe(n)". */
const name = (p: Platz) => (p.gruppe ? `${p.gruppe}(${p.mitglieder.length})` : p.mitglieder[0].id)
const reihe = (ps: Platz[]) => ps.map(name)

const MATHEK = [geraet('wp', 'C'), wert('ww', 'E'), wert('strom', 'I'), wert('aussen', 'HIMMEL')]
const DIETMAR = [wert('strom', 'I'), ...innen(3), geraet('klima', 'O')]

describe('Maßstab wie im Energiefluss (E-P2-6)', () => {
  it('W = 360 · 450 · 600 nach Spaltenbreite, k = 1312 / W', () => {
    expect([360, 374, 375, 499, 500, 1150].map(zeichenbreite)).toEqual([360, 360, 450, 450, 600, 600])
    expect(layoutUeberblick(MATHEK, 900).k).toBeCloseTo(PANORAMA_BREITE / 600, 6)
    expect(layoutUeberblick(MATHEK, 390).k).toBeCloseTo(PANORAMA_BREITE / 450, 6)
    expect(layoutUeberblick(MATHEK, 360).k).toBeCloseTo(PANORAMA_BREITE / 360, 6)
  })

  it.each([600, 900, 1150])('Desktop %i px: Schrift ≥ Energiefluss-Mindestschrift min(12, labF·ctr/600)', (ctr) => {
    for (const fall of [MATHEK, DIETMAR, [...DIETMAR, wert('aussen', 'HIMMEL')]]) {
      const l = layoutUeberblick(fall, ctr)
      expect(l.schriftPx).toBeGreaterThanOrEqual(Math.min(12, l.dims.labelFontSize * ctr / 600) - 1e-9)
    }
  })

  it.each([390, 360])('Handy %i px: Schrift = Energiefluss-Schrift labF·ctr/W (dieselbe Pixelgröße)', (ctr) => {
    const l = layoutUeberblick(DIETMAR, ctr)
    expect(l.schriftPx).toBeCloseTo(l.dims.labelFontSize * ctr / (ctr < 375 ? 360 : 450), 9)
  })
})

describe('Fälle des Bauplans', () => {
  it('Mathek (Sole): C, E, I, Himmel ⇒ 4 oben / 0 unten, dims(4)', () => {
    const l = layoutUeberblick(MATHEK, 900)
    expect(l.oben).toHaveLength(4)
    expect(l.unten).toHaveLength(0)
    expect(l.dims).toEqual(computeDims(4))
    expect(l.oben.every((p) => p.gruppe == null)).toBe(true)
  })

  it('dietmar (Luft/Luft): Desktop 5 in einer Reihe, dims(5)', () => {
    const l = layoutUeberblick(DIETMAR, 900)
    expect(l.oben).toHaveLength(5)
    expect(l.dims).toEqual(computeDims(5))
    expect(l.oben.every((p) => p.gruppe == null)).toBe(true)
  })

  it('dietmar Handy 390 px (4 Plätze): «Innengeräte (3)» + I + O', () => {
    const l = layoutUeberblick(DIETMAR, 390)
    expect(kapazitaet(450, computeDims(5).nodeW)).toBe(4)
    expect(reihe(l.oben).sort()).toEqual(['innengeraete(3)', 'klima', 'strom'])
  })

  it('dietmar Handy 360 px (3 Plätze): ohne Außentemperatur passt es; mit ihr zusätzlich «Weitere (2)»', () => {
    expect(reihe(layoutUeberblick(DIETMAR, 360).oben).sort()).toEqual(['innengeraete(3)', 'klima', 'strom'])
    const mitAussen = layoutUeberblick([...DIETMAR, wert('aussen', 'HIMMEL')], 360)
    expect(kapazitaet(360, computeDims(3).nodeW)).toBe(3)
    expect(reihe(mitAussen.oben).sort()).toEqual(['innengeraete(3)', 'klima', 'weitere(2)'])
    const weitere = mitAussen.oben.find((p) => p.gruppe === 'weitere')!
    expect(weitere.mitglieder.map((m) => m.id).sort()).toEqual(['aussen', 'strom'])
    expect(weitere.linie).toBeNull()   // gemischte Objekte: keine Linie
  })

  it('2× Luft/Wasser: gleicher Anker A ⇒ «Wärmepumpen (2)» unten', () => {
    const l = layoutUeberblick([geraet('wp1', 'A'), geraet('wp2', 'A')], 900)
    expect(reihe(l.oben)).toEqual([])
    expect(reihe(l.unten)).toEqual(['geraete(2)'])
    expect(l.unten[0].linie).not.toBeNull()
  })

  it('Luft/Wasser + Sole: A unten, C oben', () => {
    const l = layoutUeberblick([geraet('lw', 'A'), geraet('sole', 'C')], 900)
    expect(reihe(l.oben)).toEqual(['sole'])
    expect(reihe(l.unten)).toEqual(['lw'])
  })

  it('Innengeräte ≥ 4: L, M, N einzeln + «Innengeräte (n−3)» an N', () => {
    const l = layoutUeberblick(innen(5), 1150)
    expect(reihe(l.oben).sort()).toEqual(['innen-1', 'innen-2', 'innen-3', 'innengeraete(2)'])
    expect(l.oben.find((p) => p.gruppe === 'innengeraete')!.anker).toBe('N')
  })
})

describe('Geometrie', () => {
  const FAELLE: LayoutKachel[][] = [
    MATHEK, DIETMAR, [...DIETMAR, wert('aussen', 'HIMMEL')],
    [geraet('wp1', 'A'), geraet('wp2', 'A')], [geraet('lw', 'A'), geraet('sole', 'C')], innen(5),
    [geraet('bw', 'F'), wert('ww', 'E'), wert('strom', 'I'), ...innen(3), geraet('klima', 'O'), wert('aussen', 'HIMMEL')],
  ]
  const BREITEN = [1150, 900, 600, 390, 360]

  it('Reihen-y aus der Geometrie: Stapel und Fokusrahmen bleiben im Bild', () => {
    for (const ctr of BREITEN) {
      for (const fall of FAELLE) {
        const l = layoutUeberblick(fall, ctr)
        const ueber = (l.dims.nodeH / 2 + STAPEL_VERSATZ + 3) * l.k
        expect(reihenY(l.dims, l.k).oben - ueber).toBeGreaterThanOrEqual(0)
        for (const p of l.oben) expect(p.y - ueber).toBeGreaterThanOrEqual(0)
        for (const p of l.unten) expect(p.y + (l.dims.nodeH / 2) * l.k).toBeLessThanOrEqual(PANORAMA_HOEHE)
      }
    }
  })

  it('Kapazität: keine Reihe hat mehr Plätze als kapazitaet(W, nodeW); Kacheln überlappen nicht und bleiben im Bild', () => {
    for (const ctr of BREITEN) {
      for (const fall of FAELLE) {
        const l = layoutUeberblick(fall, ctr)
        for (const r of [l.oben, l.unten]) {
          expect(r.length).toBeLessThanOrEqual(kapazitaet(l.W, l.dims.nodeW))
          const xs = r.map((p) => p.x).sort((a, b) => a - b)
          for (let i = 1; i < xs.length; i++) expect(xs[i] - xs[i - 1]).toBeGreaterThanOrEqual((l.dims.nodeW + 12) * l.k - 1e-6)
          for (const x of xs) {
            expect(x - (l.dims.nodeW / 2) * l.k).toBeGreaterThanOrEqual(0)
            expect(x + (l.dims.nodeW / 2) * l.k).toBeLessThanOrEqual(PANORAMA_BREITE)
          }
        }
      }
    }
  })

  it('Kreuzungsprobe: in keinem Fall und keiner Breite schneiden sich zwei Linien einer Reihe', () => {
    for (const ctr of BREITEN) {
      for (const fall of FAELLE) {
        const l = layoutUeberblick(fall, ctr)
        expect(hatKreuzung(l.oben), `${ctr}px oben ${reihe(l.oben)}`).toBe(false)
        expect(hatKreuzung(l.unten), `${ctr}px unten ${reihe(l.unten)}`).toBe(false)
      }
    }
  })

  it('Kreuzungsprobe über alle Teilmengen der Pin-Objekte (bis 6 Kacheln, jede Breite)', () => {
    const pins: LayoutKachel[] = [
      geraet('a', 'A'), geraet('c', 'C'), geraet('f', 'F'), wert('e', 'E'), wert('i', 'I'),
      geraet('o', 'O'), wert('h', 'HIMMEL'), ...innen(3),
    ]
    let gezaehlt = 0
    for (let maske = 1; maske < 1 << pins.length; maske++) {
      const fall = pins.filter((_, i) => maske & (1 << i))
      if (fall.length > 6) continue
      for (const ctr of BREITEN) {
        const l = layoutUeberblick(fall, ctr)
        expect(hatKreuzung(l.oben) || hatKreuzung(l.unten), `${ctr}px ${fall.map((f) => f.id)}`).toBe(false)
        gezaehlt++
      }
    }
    expect(gezaehlt).toBeGreaterThan(3000)
  })

  it('schneiden(): echter Schnitt ja, Berührung am Endpunkt und Parallele nein', () => {
    expect(schneiden({ x1: 0, y1: 0, x2: 10, y2: 10 }, { x1: 0, y1: 10, x2: 10, y2: 0 })).toBe(true)
    expect(schneiden({ x1: 0, y1: 0, x2: 10, y2: 10 }, { x1: 10, y1: 10, x2: 20, y2: 0 })).toBe(false)
    expect(schneiden({ x1: 0, y1: 0, x2: 10, y2: 0 }, { x1: 0, y1: 5, x2: 10, y2: 5 })).toBe(false)
  })

  it('Linie: Kachelkante → Anker; liegt der Anker in der Kachel (Himmel), keine Linie', () => {
    const l = layoutUeberblick(MATHEK, 900)
    const himmel = l.oben.find((p) => p.mitglieder[0].id === 'aussen')!
    expect(himmel.linie).toBeNull()
    const wp = l.oben.find((p) => p.mitglieder[0].id === 'wp')!
    expect(wp.linie!.y1).toBeCloseTo(wp.y + (l.dims.nodeH / 2) * l.k, 6)
    expect(wp.linie!.x2).toBeCloseTo(0.204 * PANORAMA_BREITE, 6)
  })
})
