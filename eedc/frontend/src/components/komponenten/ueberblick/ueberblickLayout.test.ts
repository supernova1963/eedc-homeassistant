/**
 * Layout der Überblick-Kacheln (P-433-2 E1) — die Fälle des Bauplans, die
 * Kreuzungsprobe, die Kapazität je Breite, Reihen-y aus der Geometrie und die
 * Schrift gegen die Energiefluss-Mindestschrift. Seit P-433-2d (Gernot 26.10.2026)
 * gilt die Reihenregel «Technik oben, Räume unten» (`ankerReihe`): die Fälle des
 * Bauplans tragen die neuen Reihen (Erwartung angepasst, nicht die Aussage). Seit P-433-2e (Gernot 26.10.2026)
 * stehen am Desktop die Wärmepumpe (A/C/F) links und die Klima-Außeneinheit (O) rechts neben dem Haus statt in
 * einer Reihe — die Fälle tragen die Plätze (Erwartung angepasst), die Proben der Plätze stehen am Ende (S1–S7).
 */
import { describe, it, expect } from 'vitest'
import { computeDims, kapazitaet } from '../../live/energieFlussLayout'
import { STAPEL_VERSATZ } from '../../live/EnergieFlussKachel'
import { ANKER_REIHE, PANORAMA_BREITE, PANORAMA_HOEHE, WAERME_ANKER, ankerReihe, bildReihe, type AnkerId } from './waermePanoramaAnker'
import { hatKreuzung, hatKreuzungZwischen, layoutReihen, layoutUeberblick, platzGeometrie, reihenY, schneiden, trifftRechteck, zeichenbreite, type LayoutKachel, type Platz } from './ueberblickLayout'

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
  it('Mathek (Sole): Desktop WP links, E, I, Himmel oben ⇒ 3 oben / 0 unten, dims(3); Handy 4 oben, dims(4)', () => {
    const l = layoutUeberblick(MATHEK, 900)
    expect(l.links && name(l.links)).toBe('wp')
    expect(l.oben).toHaveLength(3)
    expect(l.unten).toHaveLength(0)
    expect(l.dims).toEqual(computeDims(3))
    expect(l.oben.every((p) => p.gruppe == null)).toBe(true)
    const h = layoutUeberblick(MATHEK, 390)
    expect([h.oben.length, h.unten.length, h.links]).toEqual([4, 0, null])
    expect(h.dims).toEqual(computeDims(4))
  })

  it('dietmar (Luft/Luft): Desktop Strom oben, Klima-Außeneinheit rechts, drei Innengeräte unten, dims(3)', () => {
    const l = layoutUeberblick(DIETMAR, 900)
    expect(reihe(l.oben)).toEqual(['strom'])
    expect(l.rechts && name(l.rechts)).toBe('klima')
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

  it('2× Luft/Wasser: gleicher Anker A ⇒ «Wärmepumpen (2)» im linken Platz (Desktop), oben am Handy', () => {
    const l = layoutUeberblick([geraet('wp1', 'A'), geraet('wp2', 'A')], 900)
    expect(l.links && name(l.links)).toBe('geraete(2)')
    expect(reihe(l.oben)).toEqual([])
    expect(reihe(l.unten)).toEqual([])
    expect(l.links!.linie).not.toBeNull()
    expect(reihe(layoutUeberblick([geraet('wp1', 'A'), geraet('wp2', 'A')], 390).oben)).toEqual(['geraete(2)'])
  })

  it('Luft/Wasser + Sole: Desktop A links, C oben; Handy beide oben in Anker-x-Folge (A vor C)', () => {
    const l = layoutUeberblick([geraet('lw', 'A'), geraet('sole', 'C')], 900)
    expect(l.links && name(l.links)).toBe('lw')
    expect(reihe(l.oben)).toEqual(['sole'])
    expect(reihe(l.unten)).toEqual([])
    const h = layoutUeberblick([geraet('lw', 'A'), geraet('sole', 'C')], 390)
    expect(reihe(h.oben)).toEqual(['lw', 'sole'])
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
    // Gerät in der Reihe: Handy (am Desktop steht es im linken Platz, Probe S6).
    const h = layoutUeberblick(MATHEK, 390)
    const wp = h.oben.find((p) => p.mitglieder[0].id === 'wp')!
    expect(wp.linie!.y1).toBeCloseTo(wp.y + (h.dims.nodeH / 2) * h.k, 6)
    expect(wp.linie!.x2).toBeCloseTo(0.204 * PANORAMA_BREITE, 6)
  })
})

describe('Reihenregel «Technik oben, Räume unten» (P-433-2d, Gernot 26.10.2026)', () => {
  const reiheVon = (l: Pick<ReturnType<typeof layoutUeberblick>, 'oben' | 'unten'> & Partial<ReturnType<typeof layoutUeberblick>>, id: string) =>
    l.oben.some((p) => p.mitglieder.some((m) => m.id === id)) ? 'oben'
      : l.unten.some((p) => p.mitglieder.some((m) => m.id === id)) ? 'unten'
        : l.links?.mitglieder.some((m) => m.id === id) ? 'links'
          : l.rechts?.mitglieder.some((m) => m.id === id) ? 'rechts' : null

  // Die Reihe gilt am Handy und für jede Kachel ohne Einzelplatz; am Desktop stehen die Geräte an A/C/F links und an O
  // rechts (P-433-2e) — dort prüft die Zeile 1150 px den Platz.
  const DESKTOP_PLATZ: Record<string, 'links' | 'rechts'> = { A: 'links', C: 'links', F: 'links', O: 'rechts' }
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
    for (const ctr of [390, 360]) expect(reiheVon(layoutUeberblick([kachel], ctr), 'x'), `${ctr}`).toBe(soll)
    const desktop = kachel.art === 'geraet' ? DESKTOP_PLATZ[kachel.anker] ?? soll : soll
    expect(reiheVon(layoutUeberblick([kachel], 1150), 'x'), '1150').toBe(desktop)
    expect(reiheVon(layoutReihen([kachel], 1150), 'x'), '1150 ohne Plätze').toBe(soll)
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

  it('Lab-Fall: Desktop Nibe links, Klima rechts, oben Außen · Warmwasser, unten Vorlauf · Wärme · zwei Innengeräte; Handy wie 2d', () => {
    const l = layoutUeberblick(LAB, 1440)
    expect([l.links && name(l.links), l.rechts && name(l.rechts)]).toEqual(['nibe', 'klima'])
    expect(reihe(l.oben)).toEqual(['aussen', 'ww'])
    expect(reihe(l.unten).sort()).toEqual(['innen-1', 'innen-2', 'vorlauf', 'waerme'])
    const h = layoutUeberblick(LAB, 390)
    expect(reihe(h.oben)).toEqual(['aussen', 'nibe', 'ww', 'klima'])
    expect(reihe(h.unten).sort()).toEqual(['innen-1', 'innen-2', 'vorlauf', 'waerme'])
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

  it('Lab mit zwei «Strom heute» (Desktop): das erste Innengerät wechselt nach oben, die Kapazität greift neu', () => {
    // Ohne Plätze (P-433-2d) greift danach «Weitere»; mit Nibe links und Klima rechts (P-433-2e) passt die obere Reihe.
    const r = layoutReihen([...LAB, wert('s1', 'I'), wert('s2', 'I')], 1440)
    expect(r.reihenwechsel).toEqual(['innen-1'])
    expect(inReihe(r.oben, 'innen-1')).toBe(true)
    expect(reihe(r.unten)).toEqual(['vorlauf', 'waerme', 'innen-2'])
    expect(r.oben.some((p) => p.gruppe === 'weitere')).toBe(true)
    const l = layoutUeberblick([...LAB, wert('s1', 'I'), wert('s2', 'I')], 1440)
    expect(l.reihenwechsel).toEqual(['innen-1'])
    expect([l.links && name(l.links), l.rechts && name(l.rechts)]).toEqual(['nibe', 'klima'])
    expect(reihe(l.oben)).toEqual(['aussen', 'ww', 's1', 'innen-1', 's2'])
    expect(reihe(l.unten)).toEqual(['vorlauf', 'waerme', 'innen-2'])
  })
})

describe('Zwei Plätze wie Netz und Speicher (P-433-2e, Gernot 26.10.2026)', () => {
  const PINS: LayoutKachel[] = [
    geraet('a', 'A'), geraet('c', 'C'), geraet('f', 'F'), geraet('o', 'O'), wert('e', 'E'), wert('i', 'I'), wert('d', 'D'),
    wert('h', 'HIMMEL'), wert('k', 'K'), wert('j', 'J'), wert('gv', 'G'), ...innen(3),
  ]
  const DESKTOP = [1440, 1150, 900, 700, 600]
  const HANDY = [480, 390, 375, 360, 340]
  const LAB: LayoutKachel[] = [
    wert('aussen', 'HIMMEL'), geraet('nibe', 'C'), wert('ww', 'E'), wert('vorlauf', 'K'), wert('waerme', 'K'),
    geraet('klima', 'O'), ...innen(2),
  ]
  const teilmengen = function* (bis: number) {
    for (let maske = 1; maske < 1 << PINS.length; maske++) {
      const fall = PINS.filter((_, i) => maske & (1 << i))
      if (fall.length <= bis) yield fall
    }
  }
  const plaetzeVon = (l: ReturnType<typeof layoutUeberblick>) => [l.links, l.rechts].filter((p): p is Platz => p != null)
  const rechteck = (p: Platz, l: ReturnType<typeof layoutUeberblick>) => {
    const bw = (l.dims.nodeW / 2) * l.k
    const bh = (l.dims.nodeH / 2) * l.k
    return { x0: p.x - bw, y0: p.y - bh, x1: p.x + bw, y1: p.y + bh }
  }
  /** Unabhängige Probe (nicht die Layout-Funktion): läuft die Strecke durch das Innere des Rechtecks? 400 Stützpunkte. */
  const durchRechteck = (s: { x1: number; y1: number; x2: number; y2: number }, r: { x0: number; y0: number; x1: number; y1: number }) => {
    for (let i = 0; i <= 400; i++) {
      const x = s.x1 + (s.x2 - s.x1) * i / 400
      const y = s.y1 + (s.y2 - s.y1) * i / 400
      if (x > r.x0 + 1e-6 && x < r.x1 - 1e-6 && y > r.y0 + 1e-6 && y < r.y1 - 1e-6) return true
    }
    return false
  }
  const mitte = (p: Platz) => ({ x1: p.x, y1: p.y, x2: p.ax, y2: p.ay })
  /** Schneidet ein Platz eine Reihenlinie (gezeichnet oder Mitte → Anker) oder läuft eine Reihenlinie durch ihn? */
  const konflikte = (l: ReturnType<typeof layoutUeberblick>) => {
    const out: string[] = []
    for (const p of plaetzeVon(l)) {
      const r = rechteck(p, l)
      for (const q of [...l.oben, ...l.unten]) {
        if (!q.linie) continue
        if (p.linie && (schneiden(p.linie, q.linie) || schneiden(mitte(p), mitte(q)))) out.push(`${p.key}×${q.key}`)
        if (durchRechteck(q.linie, r) || durchRechteck(mitte(q), r)) out.push(`${q.key}→${p.key}`)
      }
    }
    return out
  }

  it.each([1440, 960, 600])('S1 Lab bei %i px: Nibe links, Klima rechts, oben 2, unten 4, dims(4), keine Kreuzung, keine Linie durch einen Platz', (ctr) => {
    const l = layoutUeberblick(LAB, ctr)
    expect(l.links && name(l.links)).toBe('nibe')
    expect(l.rechts && name(l.rechts)).toBe('klima')
    expect(reihe(l.oben)).toEqual(['aussen', 'ww'])
    expect(reihe(l.unten).sort()).toEqual(['innen-1', 'innen-2', 'vorlauf', 'waerme'])
    expect(l.dims).toEqual(computeDims(4))
    expect(l.rueckfall).toEqual([])
    expect(konflikte(l)).toEqual([])
    // Lage (gemessen am Bild v4): links (10 %|38 %), rechts (90 %|65 %).
    expect(Math.round(100 * l.links!.x / PANORAMA_BREITE)).toBe(10)
    expect(Math.round(100 * l.links!.y / PANORAMA_HOEHE)).toBe(38)
    expect(Math.round(100 * l.rechts!.x / PANORAMA_BREITE)).toBe(90)
    expect(Math.round(100 * l.rechts!.y / PANORAMA_HOEHE)).toBe(65)
  })

  it.each([
    ['Warmwasser-WP F + Zusatzheizung D', [geraet('geraet-F', 'F'), wert('zusatz', 'D')]],
    ['Warmwasser-WP F + Warmwasser E + Zusatzheizung D', [geraet('geraet-F', 'F'), wert('ww', 'E'), wert('zusatz', 'D')]],
  ] as const)('S2 %s: die Linie aus dem linken Platz kreuzte die Linie zum Pufferspeicher ⇒ F bleibt oben (Rückfall)', (_, fall) => {
    for (const ctr of DESKTOP) {
      const l = layoutUeberblick([...fall], ctr)
      expect(l.rueckfall, `${ctr}`).toEqual(['geraet-F'])
      expect(l.links, `${ctr}`).toBeNull()
      expect(reihe(l.oben), `${ctr}`).toContain('geraet-F')
      expect(hatKreuzung(l.oben), `${ctr}`).toBe(false)
      // Ohne Rückfall: F im linken Platz neben den Reihen der übrigen Kacheln ⇒ Kreuzung mit der Linie nach D.
      const rest = layoutReihen(fall.filter((t) => t.id !== 'geraet-F'), ctr)
      const f = platzGeometrie([fall[0]], 'links', rest.dims, rest.k)
      const d = rest.oben.find((p) => p.key === 'zusatz')!
      expect(schneiden(f.linie!, d.linie!), `${ctr}`).toBe(true)
    }
  })

  it('S3 Teilmengen ≤ 6 aus 14 × 5 Desktop-Breiten (32 375): keine Kreuzung Platz × Reihe, keine Reihenlinie durch einen Platz, Dims nie kleiner, «Weitere» nie häufiger als 2d, Rückfall nur mit der Warmwasser-WP', () => {
    let gezaehlt = 0
    let belegt = 0
    let rueckfall = 0
    for (const fall of teilmengen(6)) {
      for (const ctr of DESKTOP) {
        const l = layoutUeberblick(fall, ctr)
        const zwei = layoutReihen(fall, ctr)   // P-433-2d ohne Plätze
        const was = `${ctr}px ${fall.map((f) => f.id)}`
        expect(konflikte(l), was).toEqual([])
        expect(hatKreuzung(l.oben) || hatKreuzung(l.unten), was).toBe(false)
        expect(hatKreuzungZwischen(l.oben, l.unten), was).toBe(false)
        if (l.links?.linie && l.rechts?.linie) expect(schneiden(l.links.linie, l.rechts.linie), was).toBe(false)
        expect(l.dims.nodeW, was).toBeGreaterThanOrEqual(zwei.dims.nodeW)
        const weitere = (ps: Platz[]) => ps.filter((p) => p.gruppe === 'weitere').length
        expect(weitere([...l.oben, ...l.unten]), was).toBeLessThanOrEqual(weitere([...zwei.oben, ...zwei.unten]))
        for (const id of l.rueckfall) expect(id, was).toBe('f')
        // Jede Kachel steht genau einmal: in einer Reihe oder in einem Platz.
        const ids = [...l.oben, ...l.unten, ...plaetzeVon(l)].flatMap((p) => p.mitglieder.map((m) => m.id)).sort()
        expect(ids, was).toEqual(fall.map((f) => f.id).sort())
        if (l.links || l.rechts) belegt++
        if (l.rueckfall.length) rueckfall++
        gezaehlt++
      }
    }
    expect(gezaehlt).toBe(32375)
    expect(belegt).toBe(26940)
    expect(rueckfall).toBe(1820)
  })

  it('S3b Rangfolge A → C → F: die Listenreihenfolge der Geräte ändert nichts — a, c, f und c, f, a liefern je Layout dieselben Plätze und Rückfälle (1 820, nur F)', () => {
    const umstellen = (fall: LayoutKachel[]) => [
      ...['c', 'f', 'a'].map((id) => fall.find((t) => t.id === id)).filter((t): t is LayoutKachel => t != null),
      ...fall.filter((t) => !['a', 'c', 'f'].includes(t.id)),
    ]
    const signatur = (l: ReturnType<typeof layoutUeberblick>) => JSON.stringify([
      l.links?.key ?? null, l.links?.mitglieder.map((m) => m.id) ?? null, l.rechts?.key ?? null, [...l.rueckfall].sort(),
    ])
    let gezaehlt = 0
    let belegt = 0
    let rueckfall = 0
    for (const fall of teilmengen(6)) {
      for (const ctr of DESKTOP) {
        const l = layoutUeberblick(fall, ctr)
        const u = layoutUeberblick(umstellen(fall), ctr)
        const was = `${ctr}px ${fall.map((f) => f.id)}`
        expect(signatur(u), was).toBe(signatur(l))
        expect(konflikte(u), was).toEqual([])
        for (const id of u.rueckfall) expect(id, was).toBe('f')
        if (u.links || u.rechts) belegt++
        if (u.rueckfall.length) rueckfall++
        gezaehlt++
      }
    }
    expect(gezaehlt).toBe(32375)
    expect(belegt).toBe(26940)
    expect(rueckfall).toBe(1820)
  })

  it('S2b fällt der erste Rang zurück, wird der nächste versucht, bevor der Platz leer bleibt (Mechanik; am Bild v4 nicht erreichbar)', () => {
    // Am Bild v4 fallen A und C nie zurück (gemessen: 0 von 32 375 Layouts in allen sechs Reihenfolgen). Für die Probe
    // liegt A für die Dauer des Tests auf (40 %|40 %): die Linie aus dem Platz läuft dann seitlich und kreuzt die
    // Warmwasser-Linie nach E ⇒ A fällt zurück, C (Rang 2) nimmt den Platz.
    const vorher = { ...WAERME_ANKER.A }
    try {
      WAERME_ANKER.A = { ...vorher, x: 40, y: 40 }
      const l = layoutUeberblick([geraet('lw', 'A'), geraet('sole', 'C'), wert('ww', 'E')], 900)
      expect(l.rueckfall).toEqual(['lw'])
      expect(l.links && name(l.links)).toBe('sole')
      expect(reihe(l.oben).sort()).toEqual(['lw', 'ww'])
      expect(konflikte(l)).toEqual([])
    } finally {
      WAERME_ANKER.A = vorher
    }
    expect(WAERME_ANKER.A.x).toBe(14.1)
  })

  it('S4 Handy (480 … 340 px): keine Plätze, Reihen und Dims gleich dem 2d-Layout (alle Teilmengen ≤ 6)', () => {
    let gezaehlt = 0
    for (const fall of teilmengen(6)) {
      for (const ctr of HANDY) {
        const l = layoutUeberblick(fall, ctr)
        expect(l.links === null && l.rechts === null && l.rueckfall.length === 0).toBe(true)
        expect(l).toEqual({ ...layoutReihen(fall, ctr), links: null, rechts: null, rueckfall: [] })
        gezaehlt++
      }
    }
    expect(gezaehlt).toBe(32375)
  })

  it('S5 Gruppe: 2× A ⇒ «Wärmepumpen (2)» links; A + C ⇒ A links, C in der Reihe; Luft/Luft + Luft/Wasser ⇒ beide Plätze; 2× O ⇒ «Wärmepumpen (2)» rechts', () => {
    const aa = layoutUeberblick([geraet('lw1', 'A'), geraet('lw2', 'A'), wert('ww', 'E')], 900)
    expect(aa.links && name(aa.links)).toBe('geraete(2)')
    expect(aa.links!.mitglieder.map((m) => m.id)).toEqual(['lw1', 'lw2'])
    expect(aa.links!.key).toBe('grp-geraete-A')
    const ac = layoutUeberblick([geraet('lw', 'A'), geraet('sole', 'C')], 900)
    expect(ac.links && name(ac.links)).toBe('lw')
    expect(reihe(ac.oben)).toEqual(['sole'])
    // Die Anker-Rangfolge A → C → F entscheidet, nicht die Listenreihenfolge (Entscheid Master 26.10.2026).
    const ca = layoutUeberblick([geraet('sole', 'C'), geraet('lw', 'A')], 900)
    expect(ca.links && name(ca.links)).toBe('lw')
    expect(reihe(ca.oben)).toEqual(['sole'])
    expect(ca.rueckfall).toEqual([])
    const beide = layoutUeberblick([geraet('klima', 'O'), geraet('lw', 'A')], 900)
    expect([beide.links && name(beide.links), beide.rechts && name(beide.rechts)]).toEqual(['lw', 'klima'])
    expect([beide.oben, beide.unten]).toEqual([[], []])
    const oo = layoutUeberblick([geraet('k1', 'O'), geraet('k2', 'O'), wert('strom', 'I')], 900)
    expect(oo.rechts && name(oo.rechts)).toBe('geraete(2)')
    expect(reihe(oo.oben)).toEqual(['strom'])
  })

  it('S6 Geometrie (alle Teilmengen ≤ 6 × Desktop): Plätze im Bild, am Rand wie die äußerste Reihenkachel, ≥ 12k von den Reihen, links über 45 %, rechts ab 58 % und nie über der Klima-Außeneinheit', () => {
    const oY = (WAERME_ANKER.O.y / 100) * PANORAMA_HOEHE
    for (const fall of teilmengen(6)) {
      for (const ctr of DESKTOP) {
        const l = layoutUeberblick(fall, ctr)
        if (!l.links && !l.rechts) continue
        const was = `${ctr}px ${fall.map((f) => f.id)}`
        const bh = (l.dims.nodeH / 2) * l.k
        const ry = reihenY(l.dims, l.k)
        const obenUnterkante = l.oben.length ? Math.max(...l.oben.map((p) => p.y)) + bh : ry.oben + bh
        const untenOberkante = l.unten.length ? Math.min(...l.unten.map((p) => p.y)) - bh : ry.unten - bh
        for (const p of plaetzeVon(l)) {
          const r = rechteck(p, l)
          expect(r.x0 >= 0 && r.x1 <= PANORAMA_BREITE && r.y0 >= 0 && r.y1 <= PANORAMA_HOEHE, was).toBe(true)
          const rand = (l.dims.nodeW / 2 + 15) * l.k
          expect(p.x, was).toBeCloseTo(p.seite === 'links' ? rand : PANORAMA_BREITE - rand, 6)
          // Kein Platz überdeckt eine Reihenkachel.
          for (const q of [...l.oben, ...l.unten]) {
            const s = rechteck(q, l)
            expect(r.x1 <= s.x0 || s.x1 <= r.x0 || r.y1 <= s.y0 || s.y1 <= r.y0, `${was} ${p.key}/${q.key}`).toBe(true)
          }
        }
        if (l.links) {
          const r = rechteck(l.links, l)
          expect(r.y0 - (ry.oben + bh), was).toBeGreaterThanOrEqual(12 * l.k - 1e-6)
          expect(r.y0 - obenUnterkante, was).toBeGreaterThanOrEqual(12 * l.k - 1e-6)
          expect(r.y1, was).toBeLessThanOrEqual(0.45 * PANORAMA_HOEHE + 1e-6)
        }
        if (l.rechts) {
          const r = rechteck(l.rechts, l)
          expect(ry.unten - bh - r.y1, was).toBeGreaterThanOrEqual(12 * l.k - 1e-6)
          expect(untenOberkante - r.y1, was).toBeGreaterThanOrEqual(12 * l.k - 1e-6)
          expect(r.y0, was).toBeGreaterThanOrEqual(0.58 * PANORAMA_HOEHE - 1e-6)
          expect(r.y0, was).toBeGreaterThan(oY)
        }
      }
    }
  })

  it('S6 Linie von der nächsten Kante: Anker unter der Kachel ⇒ Unterkante, über ihr ⇒ Oberkante, daneben ⇒ Seitenkante', () => {
    const l = layoutUeberblick(LAB, 900)
    const bh = (l.dims.nodeH / 2) * l.k
    const bw = (l.dims.nodeW / 2) * l.k
    expect(l.links!.linie).toEqual({ x1: l.links!.x, y1: l.links!.y + bh, x2: l.links!.ax, y2: l.links!.ay })   // C unter der Kachel
    expect(l.rechts!.linie).toEqual({ x1: l.rechts!.x, y1: l.rechts!.y - bh, x2: l.rechts!.ax, y2: l.rechts!.ay })   // O über ihr
    const f = layoutUeberblick([geraet('bw', 'F')], 900).links!   // F auf Höhe der Kachel, rechts von ihr
    expect(f.ay).toBeGreaterThan(f.y - (computeDims(1).nodeH / 2) * l.k)
    expect(f.linie).toEqual({ x1: f.x + (computeDims(1).nodeW / 2) * l.k, y1: f.y, x2: f.ax, y2: f.ay })
    void bw
  })

  it('S7 dietmar: Klima rechts, Strom oben, drei Innengeräte unten einzeln, dims(3) — an jeder Desktop-Breite', () => {
    for (const ctr of DESKTOP) {
      const l = layoutUeberblick(DIETMAR, ctr)
      expect(l.rechts && name(l.rechts), `${ctr}`).toBe('klima')
      expect(l.links, `${ctr}`).toBeNull()
      expect(reihe(l.oben), `${ctr}`).toEqual(['strom'])
      expect(reihe(l.unten).sort(), `${ctr}`).toEqual(['innen-1', 'innen-2', 'innen-3'])
      expect(l.dims, `${ctr}`).toEqual(computeDims(3))
      expect(konflikte(l), `${ctr}`).toEqual([])
    }
  })

  // Nachmessung 26.10.2026: `trifftRechteck` ist am Bild v4 mit gekürzter unterer Reihe unerreichbar (0 Treffer in
  // 32 375 Layouten) — Verteidigung für ein neues Bild. Damit die exportierte Funktion nicht ungetestet bleibt: Durchlauf
  // und Ende im Rechteck zählen, Berührung an Kante oder Ecke und Verlauf außerhalb nicht.
  it('trifftRechteck: Durchlauf ja, Berührung nein', () => {
    const r = { x0: 100, y0: 100, x1: 200, y1: 160 }
    expect(trifftRechteck({ x1: 50, y1: 130, x2: 250, y2: 130 }, r)).toBe(true)
    expect(trifftRechteck({ x1: 50, y1: 50, x2: 150, y2: 130 }, r)).toBe(true)
    expect(trifftRechteck({ x1: 50, y1: 100, x2: 250, y2: 100 }, r)).toBe(false)
    expect(trifftRechteck({ x1: 0, y1: 0, x2: 100, y2: 100 }, r)).toBe(false)
    expect(trifftRechteck({ x1: 50, y1: 200, x2: 250, y2: 220 }, r)).toBe(false)
  })
})
