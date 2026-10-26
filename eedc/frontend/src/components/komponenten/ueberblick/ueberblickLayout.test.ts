/**
 * Layout der Überblick-Kacheln (P-433-2 E1) — die Fälle des Bauplans, die
 * Kreuzungsprobe, die Kapazität je Breite, Reihen-y aus der Geometrie und die
 * Schrift gegen die Energiefluss-Mindestschrift. Seit P-433-2d (Gernot 26.10.2026)
 * gilt die Reihenregel «Technik oben, Räume unten» (`ankerReihe`): die Fälle des
 * Bauplans tragen die neuen Reihen (Erwartung angepasst, nicht die Aussage).
 */
import { describe, it, expect } from 'vitest'
import { computeDims, kapazitaet } from '../../live/energieFlussLayout'
import { STAPEL_VERSATZ } from '../../live/EnergieFlussKachel'
import { ANKER_REIHE, PANORAMA_BREITE, PANORAMA_HOEHE, WAERME_ANKER, ankerReihe, bildReihe, type AnkerId } from './waermePanoramaAnker'
import { hatKreuzung, hatKreuzungZwischen, layoutUeberblick, reihenY, schneiden, zeichenbreite, type LayoutKachel, type Platz } from './ueberblickLayout'

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

  it('dietmar (Luft/Luft): Desktop Strom + Klima-Außeneinheit oben, drei Innengeräte unten, dims(3)', () => {
    const l = layoutUeberblick(DIETMAR, 900)
    expect(reihe(l.oben)).toEqual(['strom', 'klima'])
    expect(reihe(l.unten).sort()).toEqual(['innen-1', 'innen-2', 'innen-3'])
    expect(l.dims).toEqual(computeDims(3))
    expect([...l.oben, ...l.unten].every((p) => p.gruppe == null)).toBe(true)
  })

  it('dietmar Handy 390 px (4 Plätze je Reihe): die drei Innengeräte passen einzeln in die untere Reihe', () => {
    const l = layoutUeberblick(DIETMAR, 390)
    expect(kapazitaet(450, computeDims(3).nodeW)).toBeGreaterThanOrEqual(3)
    expect(reihe(l.oben).sort()).toEqual(['klima', 'strom'])
    expect(reihe(l.unten).sort()).toEqual(['innen-1', 'innen-2', 'innen-3'])
  })

  it('dietmar Handy 360 px (3 Plätze je Reihe): mit Außen 3 oben / 3 unten, kein Reihenwechsel', () => {
    expect(kapazitaet(360, computeDims(3).nodeW)).toBe(3)
    const mitAussen = layoutUeberblick([...DIETMAR, wert('aussen', 'HIMMEL')], 360)
    expect(reihe(mitAussen.oben).sort()).toEqual(['aussen', 'klima', 'strom'])
    expect(reihe(mitAussen.unten).sort()).toEqual(['innen-1', 'innen-2', 'innen-3'])
    expect(mitAussen.reihenwechsel).toEqual([])
  })

  it('dietmar Handy 360/340 px ohne Außen: Strom → Zählerreihe kreuzte Innengerät → L ⇒ das erste Innengerät wechselt nach oben', () => {
    for (const ctr of [360, 340]) {
      const l = layoutUeberblick(DIETMAR, ctr)
      expect(l.reihenwechsel, `${ctr}`).toEqual(['innen-1'])
      expect(reihe(l.oben)).toEqual(['strom', 'innen-1', 'klima'])
      expect(reihe(l.unten)).toEqual(['innen-2', 'innen-3'])
      expect(hatKreuzung([...l.oben, ...l.unten]), `${ctr}`).toBe(false)
    }
  })

  it('«Weitere (n)» ohne Linie: dietmar mit Außen und Warmwasser bei 360 px', () => {
    const voll = layoutUeberblick([...DIETMAR, wert('aussen', 'HIMMEL'), wert('ww', 'E')], 360)
    const weitere = voll.oben.find((p) => p.gruppe === 'weitere')!
    expect(weitere.mitglieder.map((m) => m.id).sort()).toEqual(['aussen', 'strom', 'ww'])
    expect(weitere.linie).toBeNull()   // gemischte Objekte: keine Linie
  })

  it('2× Luft/Wasser: gleicher Anker A ⇒ «Wärmepumpen (2)» oben (Technik)', () => {
    const l = layoutUeberblick([geraet('wp1', 'A'), geraet('wp2', 'A')], 900)
    expect(reihe(l.oben)).toEqual(['geraete(2)'])
    expect(reihe(l.unten)).toEqual([])
    expect(l.oben[0].linie).not.toBeNull()
  })

  it('Luft/Wasser + Sole: beide Geräte oben in Anker-x-Folge (A vor C)', () => {
    const l = layoutUeberblick([geraet('lw', 'A'), geraet('sole', 'C')], 900)
    expect(reihe(l.oben)).toEqual(['lw', 'sole'])
    expect(reihe(l.unten)).toEqual([])
  })

  it('Innengeräte ≥ 4: L, M, N einzeln + «Innengeräte (n−3)» an N, alle unten', () => {
    const l = layoutUeberblick(innen(5), 1150)
    expect(reihe(l.oben)).toEqual([])
    expect(reihe(l.unten).sort()).toEqual(['innen-1', 'innen-2', 'innen-3', 'innengeraete(2)'])
    expect(l.unten.find((p) => p.gruppe === 'innengeraete')!.anker).toBe('N')
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
    // P-433-2d: um die Objekte von Zusatzheizung (D) und «Vorlauf · Rücklauf»/«Wärme heute» (G · K · J) erweitert.
    const pins: LayoutKachel[] = [
      geraet('a', 'A'), geraet('c', 'C'), geraet('f', 'F'), wert('e', 'E'), wert('i', 'I'),
      geraet('o', 'O'), wert('h', 'HIMMEL'), ...innen(3),
      wert('d', 'D'), wert('vg', 'G'), wert('vk', 'K'), wert('vj', 'J'),
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
    expect(gezaehlt).toBeGreaterThan(30000)
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

describe('Reihenregel «Technik oben, Räume unten» (P-433-2d, Gernot 26.10.2026)', () => {
  const reiheVon = (l: ReturnType<typeof layoutUeberblick>, id: string) =>
    l.oben.some((p) => p.mitglieder.some((m) => m.id === id)) ? 'oben'
      : l.unten.some((p) => p.mitglieder.some((m) => m.id === id)) ? 'unten' : null

  it.each([
    ['Außen (Himmel)', 'oben', wert('x', 'HIMMEL')],
    ['Luft/Wasser-Außeneinheit A (Bild 57,6 %)', 'oben', geraet('x', 'A')],
    ['WP-Schrank C', 'oben', geraet('x', 'C')],
    ['Warmwasser-WP F', 'oben', geraet('x', 'F')],
    ['Klima-Außeneinheit O', 'oben', geraet('x', 'O')],
    ['Warmwasser E', 'oben', wert('x', 'E')],
    ['Zusatzheizung D', 'oben', wert('x', 'D')],
    ['Strom heute I', 'oben', wert('x', 'I')],
    ['Vorlauf/Wärme am Hydraulikmodul G, ohne Stammdatum (Entscheid H1)', 'oben', wert('x', 'G')],
    ['Vorlauf/Wärme an der Fußbodenheizung K', 'unten', wert('x', 'K')],
    ['Vorlauf/Wärme am Heizkörper J (Bild 42,3 %)', 'unten', wert('x', 'J')],
    ['Innengerät L (Bild 17,2 %)', 'unten', { id: 'x', art: 'innengeraet', anker: 'L' } as LayoutKachel],
    ['Innengerät M', 'unten', { id: 'x', art: 'innengeraet', anker: 'M' } as LayoutKachel],
    ['Innengerät N', 'unten', { id: 'x', art: 'innengeraet', anker: 'N' } as LayoutKachel],
  ] as const)('%s ⇒ %s', (_, soll, kachel) => {
    for (const ctr of [1150, 390, 360]) expect(reiheVon(layoutUeberblick([kachel], ctr), 'x'), `${ctr}`).toBe(soll)
  })

  it('Gruppe «Innengeräte (n)» steht unten — auch wenn die Reihe sie erst wegen der Kapazität bildet', () => {
    const l = layoutUeberblick([...innen(4), wert('vk', 'K'), wert('wk', 'K')], 360)
    expect(reihe(l.unten).sort()).toEqual(['innengeraete(4)', 'vk', 'wk'])
    expect(l.oben).toEqual([])
  })

  it('jedes Objekt, an dem eine Kachel stehen kann, hat einen Eintrag — die Bildlage ist nur Rückfall', () => {
    const mitKachel: AnkerId[] = ['HIMMEL', 'A', 'C', 'F', 'O', 'E', 'D', 'I', 'G', 'K', 'J', 'L', 'M', 'N']
    for (const a of mitKachel) expect(ANKER_REIHE[a], a).toBeDefined()
    // Raumkontext ohne Kachel: kein Eintrag.
    for (const a of ['H', 'P', 'Q', 'R'] as AnkerId[]) expect(ANKER_REIHE[a], a).toBeUndefined()
  })

  it('Rückfall für Anker ohne Eintrag: Bildlage (y < 50 % ⇒ oben, sonst unten)', () => {
    expect(WAERME_ANKER.P.y).toBeLessThan(50)
    expect(WAERME_ANKER.Q.y).toBeGreaterThanOrEqual(50)
    expect(ankerReihe('P')).toBe('oben')
    expect(ankerReihe('Q')).toBe('unten')
    const l = layoutUeberblick([wert('p', 'P'), wert('q', 'Q')], 900)
    expect(reihe(l.oben)).toEqual(['p'])
    expect(reihe(l.unten)).toEqual(['q'])
  })

  /** Lab-Fall Winterborn (26.10.): Nibe Sole (C) mit Vorlauf an der Fußbodenheizung (K) und Wärme heute (K),
   *  Warmwasser (E), Außen; Multisplit (O) mit zwei Innengeräten (L, M). */
  const LAB: LayoutKachel[] = [
    wert('aussen', 'HIMMEL'), geraet('nibe', 'C'), wert('ww', 'E'), wert('vorlauf', 'K'), wert('waerme', 'K'),
    geraet('klima', 'O'), ...innen(2),
  ]
  const BREITEN_LAB = [1440, 1150, 1100, 900, 700, 600, 480, 390, 375, 360, 340]

  it('Lab-Fall: oben Außen · Nibe · Warmwasser · Klima, unten Vorlauf · Wärme · zwei Innengeräte (Desktop)', () => {
    const l = layoutUeberblick(LAB, 1440)
    expect(reihe(l.oben)).toEqual(['aussen', 'nibe', 'ww', 'klima'])
    expect(reihe(l.unten).sort()).toEqual(['innen-1', 'innen-2', 'vorlauf', 'waerme'])
  })

  it('Lab-Fall: an keiner Breite schneiden sich zwei Linien — weder in einer Reihe noch zwischen den Reihen', () => {
    for (const fall of [LAB, LAB.filter((k) => k.id !== 'waerme')]) {
      for (const ctr of BREITEN_LAB) {
        const l = layoutUeberblick(fall, ctr)
        expect(hatKreuzung(l.oben), `oben @${ctr}`).toBe(false)
        expect(hatKreuzung(l.unten), `unten @${ctr}`).toBe(false)
        expect(hatKreuzung([...l.oben, ...l.unten]), `zwischen den Reihen @${ctr}: ${reihe(l.oben)} | ${reihe(l.unten)}`).toBe(false)
      }
    }
  })
})

describe('Reihenwechsel bei Kreuzung (Entscheid Gernot 26.10.2026 zu H1)', () => {
  const PINS: LayoutKachel[] = [
    geraet('a', 'A'), geraet('c', 'C'), geraet('f', 'F'), geraet('o', 'O'), wert('e', 'E'), wert('i', 'I'), wert('d', 'D'),
    wert('h', 'HIMMEL'), wert('k', 'K'), wert('j', 'J'), wert('gv', 'G'), ...innen(3),
  ]
  const BREITEN_ALLE = [1440, 1150, 1100, 900, 700, 600, 480, 390, 375, 360, 340]
  const inReihe = (ps: Platz[], id: string) => ps.some((p) => p.mitglieder.some((m) => m.id === id))

  it('Fixpunkt über alle Teilmengen ≤ 6 aus 14 Objekten × 11 Breiten: keine Schnitte, weder zwischen noch in den Reihen; höchstens n Wechsel, jeder in die Bildlage', () => {
    let gezaehlt = 0
    for (let maske = 1; maske < 1 << PINS.length; maske++) {
      const fall = PINS.filter((_, i) => maske & (1 << i))
      if (fall.length > 6) continue
      for (const ctr of BREITEN_ALLE) {
        const l = layoutUeberblick(fall, ctr)
        const was = `${ctr}px ${fall.map((f) => f.id)}`
        expect(hatKreuzung(l.oben) || hatKreuzung(l.unten), was).toBe(false)
        expect(hatKreuzung([...l.oben, ...l.unten]), was).toBe(false)
        expect(hatKreuzungZwischen(l.oben, l.unten), was).toBe(false)   // auch Kachelmitte → Anker
        expect(l.reihenwechsel.length, was).toBeLessThanOrEqual(fall.length)
        for (const id of l.reihenwechsel) {
          const t = fall.find((f) => f.id === id)!
          expect(ankerReihe(t.anker), was).not.toBe(bildReihe(t.anker))   // nur wer nicht in seiner Bildlage stand
          expect(inReihe(bildReihe(t.anker) === 'oben' ? l.oben : l.unten, id), was).toBe(true)
        }
        gezaehlt++
      }
    }
    expect(gezaehlt).toBe(71225)
  })

  it('Garantie: stehen alle Kacheln in ihrer Bildlage, kreuzt keine Linie die andere Reihe (dieselben 71 225 Layouts)', () => {
    // Obere Linien enden über, untere unter der Bildmitte. Probe: ANKER_REIHE für die Dauer des Tests = Bildlage.
    const vorher = { ...ANKER_REIHE }
    try {
      for (const id of Object.keys(ANKER_REIHE) as AnkerId[]) ANKER_REIHE[id] = bildReihe(id)
      let gezaehlt = 0
      for (let maske = 1; maske < 1 << PINS.length; maske++) {
        const fall = PINS.filter((_, i) => maske & (1 << i))
        if (fall.length > 6) continue
        for (const ctr of BREITEN_ALLE) {
          const l = layoutUeberblick(fall, ctr)
          expect(hatKreuzung([...l.oben, ...l.unten]), `${ctr}px ${fall.map((f) => f.id)}`).toBe(false)
          expect(hatKreuzungZwischen(l.oben, l.unten), `${ctr}px ${fall.map((f) => f.id)}`).toBe(false)
          expect(l.reihenwechsel).toEqual([])
          gezaehlt++
        }
      }
      expect(gezaehlt).toBe(71225)
    } finally {
      for (const id of Object.keys(ANKER_REIHE) as AnkerId[]) delete ANKER_REIHE[id]
      Object.assign(ANKER_REIHE, vorher)
    }
    for (const id of Object.keys(WAERME_ANKER) as AnkerId[]) {
      expect(bildReihe(id), id).toBe(WAERME_ANKER[id].y < 50 ? 'oben' : 'unten')
    }
  })

  it('«Vorlauf · Rücklauf» und «Wärme heute» am selben Objekt bleiben in derselben Reihe (K · J · G, mit bis zu 4 weiteren Kacheln)', () => {
    const rest = PINS.filter((p) => !['k', 'j', 'gv'].includes(p.id))
    for (const anker of ['K', 'J', 'G'] as AnkerId[]) {
      for (let maske = 0; maske < 1 << rest.length; maske++) {
        const andere = rest.filter((_, i) => maske & (1 << i))
        if (andere.length > 4) continue
        for (const ctr of [1440, 600, 390, 360]) {
          const l = layoutUeberblick([...andere, wert('vorlauf', anker), wert('waerme', anker)], ctr)
          expect(inReihe(l.oben, 'vorlauf'), `${anker} ${ctr} ${andere.map((f) => f.id)}`).toBe(inReihe(l.oben, 'waerme'))
        }
      }
    }
  })

  const LAB: LayoutKachel[] = [
    wert('aussen', 'HIMMEL'), geraet('nibe', 'C'), wert('ww', 'E'), wert('vorlauf', 'K'), wert('waerme', 'K'),
    geraet('klima', 'O'), ...innen(2),
  ]
  const MATHEK_REIHE = (v: AnkerId, waerme = false): LayoutKachel[] => [
    wert('aussen', 'HIMMEL'), geraet('wp', 'C'), wert('vorlauf', v), ...(waerme ? [wert('waerme', v)] : []),
    wert('zusatz', 'D'), wert('ww', 'E'), wert('strom', 'I'),
  ]
  const wechselJeBreite = (fall: LayoutKachel[]) => BREITEN_ALLE.map((ctr) => layoutUeberblick(fall, ctr).reihenwechsel.length)

  it.each([
    ['Lab-Fall', LAB, [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]],
    ['Lab mit zwei «Strom heute»', [...LAB, wert('s1', 'I'), wert('s2', 'I')], [1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0]],
    ['Mathek ohne Stammdatum (G)', MATHEK_REIHE('G'), [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]],
    ['Mathek ohne Stammdatum mit Wärme heute (G)', MATHEK_REIHE('G', true), [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]],
    ['Mathek Fußbodenheizung (K)', MATHEK_REIHE('K'), [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]],
    ['Mathek Heizkörper (J)', MATHEK_REIHE('J'), [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]],
    ['dietmar', DIETMAR, [0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1]],
  ] as const)('%s: Wechsel je Breite (1440 … 340 px) wie gemessen, keine Schnitte', (_, fall, soll) => {
    expect(wechselJeBreite([...fall])).toEqual(soll)
    for (const ctr of BREITEN_ALLE) {
      const l = layoutUeberblick([...fall], ctr)
      expect(hatKreuzung([...l.oben, ...l.unten]), `${ctr}`).toBe(false)
      expect(hatKreuzungZwischen(l.oben, l.unten), `${ctr}`).toBe(false)
    }
  })

  it('Lab mit zwei «Strom heute» (Desktop): das erste Innengerät wechselt nach oben, die Kapazität greift neu («Weitere»)', () => {
    const l = layoutUeberblick([...LAB, wert('s1', 'I'), wert('s2', 'I')], 1440)
    expect(l.reihenwechsel).toEqual(['innen-1'])
    expect(inReihe(l.oben, 'innen-1')).toBe(true)
    expect(reihe(l.unten)).toEqual(['vorlauf', 'waerme', 'innen-2'])
    expect(l.oben.some((p) => p.gruppe === 'weitere')).toBe(true)
  })
})
