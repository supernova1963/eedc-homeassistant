/**
 * Layout-Probe der zwei Szenen der E-Mobilität (P-433-2b S1b E4, Bauplan Fassung 2 §3/§9) — mit den Ist-Ankern
 * (gemessen am Bild 1.11.2026, Bild-Brief §10). Das Layout (`ueberblickLayout.ts`) ist unverändert; geprüft wird,
 * dass die Deskriptoren `LADEPUNKT_PANORAMA_DEF` / `FAHRZEUG_PANORAMA_DEF` mit ihm keine Kreuzung erzeugen:
 * alle Teilmengen der Kachel-Arten je Szene × 11 Breiten ⇒ 0 Kreuzungen (in einer Reihe, zwischen den Reihen,
 * Platz × Reihe, keine Reihenlinie durch den Platz), Plätze belegt und Rückfall gezählt, Handy ohne Plätze.
 */
import { describe, it, expect } from 'vitest'
import {
  hatKreuzung, hatKreuzungZwischen, layoutUeberblick, schneiden, type LayoutKachel, type Platz, type UeberblickLayout,
} from './ueberblickLayout'
import { FAHRZEUG_PANORAMA_DEF, LADEPUNKT_PANORAMA_DEF } from './emobPanoramaAnker'
import { ankerReihe, bildReihe, type PanoramaDef } from './panorama'

const BREITEN = [1440, 1150, 1100, 900, 700, 600, 480, 390, 375, 360, 340]
const geraet = (id: string, anker: string): LayoutKachel => ({ id, art: 'geraet', anker })
const wert = (id: string, anker: string): LayoutKachel => ({ id, art: 'wert', anker })

/** Ladepunkt: Wallbox A (Platz links), Ladung Z, Sitzung S, Fahrzeugkachel F (Wert) und zwei weitere Autos an F. */
const LADEPUNKT: LayoutKachel[] = [
  geraet('a', 'A'), wert('z', 'Z'), wert('s', 'S'), wert('f', 'F'), geraet('f2', 'F'), geraet('f3', 'F'),
]
/** Fahrzeug: Laden L (Platz links), Ladestand B, Reichweite C, Gefahren R, Standort H. */
const FAHRZEUG: LayoutKachel[] = [geraet('l', 'L'), wert('b', 'B'), wert('c', 'C'), wert('r', 'R'), wert('h', 'H')]

function* teilmengen(pins: LayoutKachel[]) {
  for (let maske = 1; maske < 1 << pins.length; maske++) yield pins.filter((_, i) => maske & (1 << i))
}

const plaetzeVon = (l: UeberblickLayout) => [l.links, l.rechts].filter((p): p is Platz => p != null)
const mitte = (p: Platz) => ({ x1: p.x, y1: p.y, x2: p.ax, y2: p.ay })
/** Unabhängige Probe (nicht die Layout-Funktion): läuft die Strecke durch das Innere des Rechtecks? 400 Stützpunkte. */
const durchRechteck = (s: { x1: number; y1: number; x2: number; y2: number }, r: { x0: number; y0: number; x1: number; y1: number }) => {
  for (let i = 0; i <= 400; i++) {
    const x = s.x1 + (s.x2 - s.x1) * i / 400
    const y = s.y1 + (s.y2 - s.y1) * i / 400
    if (x > r.x0 + 1e-6 && x < r.x1 - 1e-6 && y > r.y0 + 1e-6 && y < r.y1 - 1e-6) return true
  }
  return false
}
/** Schneidet ein Platz eine Reihenlinie (gezeichnet oder Mitte → Anker) oder läuft eine Reihenlinie durch ihn? */
const konflikte = (l: UeberblickLayout) => {
  const out: string[] = []
  for (const p of plaetzeVon(l)) {
    const bw = (l.dims.nodeW / 2) * l.k
    const bh = (l.dims.nodeH / 2) * l.k
    const r = { x0: p.x - bw, y0: p.y - bh, x1: p.x + bw, y1: p.y + bh }
    for (const q of [...l.oben, ...l.unten]) {
      if (!q.linie) continue
      if (p.linie && (schneiden(p.linie, q.linie) || schneiden(mitte(p), mitte(q)))) out.push(`${p.key}×${q.key}`)
      if (durchRechteck(q.linie, r) || durchRechteck(mitte(q), r)) out.push(`${q.key}→${p.key}`)
    }
  }
  return out
}

interface Zaehlung { layouts: number; platzBelegt: number; rueckfall: number; reihenwechsel: number; weitere: number }

/** Alle Teilmengen × 11 Breiten: die Kreuzungs-Proben, und was gezählt wird. */
function probe(pins: LayoutKachel[], panorama: PanoramaDef): Zaehlung {
  const z: Zaehlung = { layouts: 0, platzBelegt: 0, rueckfall: 0, reihenwechsel: 0, weitere: 0 }
  for (const fall of teilmengen(pins)) {
    for (const ctr of BREITEN) {
      const l = layoutUeberblick(fall, ctr, panorama)
      const was = `${ctr}px ${fall.map((f) => f.id)}`
      expect(hatKreuzung(l.oben) || hatKreuzung(l.unten), was).toBe(false)
      expect(hatKreuzung([...l.oben, ...l.unten]), was).toBe(false)
      expect(hatKreuzungZwischen(l.oben, l.unten), was).toBe(false)
      expect(konflikte(l), was).toEqual([])
      if (ctr < 500) expect([l.links, l.rechts, l.rueckfall.length], was).toEqual([null, null, 0])
      expect(l.rechts, was).toBeNull()   // §9: rechter Platz entfällt in beiden Szenen
      // Jede Kachel steht genau einmal: in einer Reihe oder im Platz.
      const ids = [...l.oben, ...l.unten, ...plaetzeVon(l)].flatMap((p) => p.mitglieder.map((m) => m.id)).sort()
      expect(ids, was).toEqual(fall.map((f) => f.id).sort())
      // Ein Reihenwechsel geht nur in die Bildlage.
      for (const id of l.reihenwechsel) {
        const a = fall.find((f) => f.id === id)!.anker
        expect(ankerReihe(panorama, a), was).not.toBe(bildReihe(panorama, a))
      }
      if (l.links) z.platzBelegt++
      if (l.rueckfall.length) z.rueckfall++
      if (l.reihenwechsel.length) z.reihenwechsel++
      if ([...l.oben, ...l.unten].some((p) => p.gruppe === 'weitere')) z.weitere++
      z.layouts++
    }
  }
  return z
}

describe('Szene «Ladepunkt» — Layout mit den Ist-Ankern (S1b E4)', () => {
  it('alle 63 Teilmengen × 11 Breiten (693 Layouts): 0 Kreuzungen; Platz links belegt/Rückfall gezählt; Handy ohne Plätze', () => {
    const z = probe(LADEPUNKT, LADEPUNKT_PANORAMA_DEF)
    expect(z).toEqual({ layouts: 693, platzBelegt: 192, rueckfall: 0, reihenwechsel: 0, weitere: 0 })
  })

  it('Desktop voll (A, Z, S, F, zwei weitere Autos): A links, oben Z, unten S · F · «E-Autos (2)»', () => {
    for (const ctr of [1440, 900, 600]) {
      const l = layoutUeberblick(LADEPUNKT, ctr, LADEPUNKT_PANORAMA_DEF)
      expect(l.links?.key, `${ctr}`).toBe('a')
      // A waagerecht auf y 33 % über dem Autodach (Bild-Brief §10, Kreuzungsprobe von Hand).
      expect(l.links!.linie!.y1, `${ctr}`).toBeCloseTo(l.links!.linie!.y2, 6)
      expect(l.oben.map((p) => p.key), `${ctr}`).toEqual(['z'])
      expect(l.unten.map((p) => p.key).sort(), `${ctr}`).toEqual(['f', 'grp-geraete-F', 's'])
      expect(LADEPUNKT_PANORAMA_DEF.gruppenName('geraete', 'F')).toBe('E-Autos')
    }
  })

  it('Handy (390 px): zwei Reihen ohne Plätze — oben A · Z, unten S · F', () => {
    const l = layoutUeberblick(LADEPUNKT.slice(0, 4), 390, LADEPUNKT_PANORAMA_DEF)
    expect([l.links, l.rechts]).toEqual([null, null])
    expect(l.oben.map((p) => p.key).sort()).toEqual(['a', 'z'])
    expect(l.unten.map((p) => p.key).sort()).toEqual(['f', 's'])
  })
})

describe('Szene «Fahrzeug» — Layout mit den Ist-Ankern (S1b E4)', () => {
  it('alle 31 Teilmengen × 11 Breiten (341 Layouts): 0 Kreuzungen; Platz links belegt/Rückfall gezählt; Handy ohne Plätze', () => {
    const z = probe(FAHRZEUG, FAHRZEUG_PANORAMA_DEF)
    expect(z).toEqual({ layouts: 341, platzBelegt: 96, rueckfall: 0, reihenwechsel: 0, weitere: 0 })
  })

  it('Desktop voll: L links (kurze Linie von der Seitenkante zur Säule), oben H · C, unten B · R', () => {
    for (const ctr of [1440, 900, 600]) {
      const l = layoutUeberblick(FAHRZEUG, ctr, FAHRZEUG_PANORAMA_DEF)
      expect(l.links?.key, `${ctr}`).toBe('l')
      const li = l.links!.linie!
      expect(li.x1, `${ctr}`).toBeCloseTo(l.links!.x + (l.dims.nodeW / 2) * l.k, 6)   // Seitenkante, nicht Ober-/Unterkante
      expect(Math.hypot(li.x2 - li.x1, li.y2 - li.y1), `${ctr}`).toBeLessThan(100)   // gemessen 92 Bildeinheiten
      expect(l.oben.map((p) => p.key), `${ctr}`).toEqual(['h', 'c'])
      expect(l.unten.map((p) => p.key), `${ctr}`).toEqual(['r', 'b'])
    }
  })

  it('Handy (390 px): oben H · C, unten L · R · B (L ohne Platz in der unteren Reihe, §2)', () => {
    const l = layoutUeberblick(FAHRZEUG, 390, FAHRZEUG_PANORAMA_DEF)
    expect([l.links, l.rechts]).toEqual([null, null])
    expect(l.oben.map((p) => p.key)).toEqual(['h', 'c'])
    expect(l.unten.map((p) => p.key)).toEqual(['l', 'r', 'b'])
  })

  it('Sprengsatz-Probe: nur die Gerätekachel ist Platz-Kandidat — `plaetze.links = [B]` (Wert-Kachel) lässt den Platz leer', () => {
    const def: PanoramaDef = { ...FAHRZEUG_PANORAMA_DEF, plaetze: { links: ['B'], rechts: [] } }
    const l = layoutUeberblick(FAHRZEUG, 1440, def)
    expect(l.links).toBeNull()
    expect(layoutUeberblick(FAHRZEUG, 1440, FAHRZEUG_PANORAMA_DEF).links?.key).toBe('l')
  })
})

describe('Themen-Kacheln am HIMMEL der Szene «Fahrzeug» (4.2.0 TH-E2, P3; Entscheid Master 1.11.2026 zu H3)', () => {
  // Gemessen: die Zeichenbreiten sind 360/450/600; ab fünf Kacheln passen 3/4/6 in eine Reihe — fünf Plätze gibt es
  // nie. Voll + vier Themen: Desktop alle im Bild, ohne «Weitere»; 480–375 px eins im Bild, «Weitere (3)»; 360/340 px
  // «Weitere (4)». Die wörtliche Form «zwei im Bild, Weitere (2)» entsteht mit Reichweite + vier Themen bei 480–375 px.
  // Rang-Aussage überall: Standort (H) und Reichweite (C) bleiben im Bild — Themen wandern zuerst.
  const thema = (id: string): LayoutKachel => ({ id, art: 'thema', anker: 'HIMMEL' })
  const VIER = ['t1', 't2', 't3', 't4'].map(thema)
  const VOLL = [geraet('l', 'L'), wert('b', 'B'), wert('c', 'C'), wert('r', 'R'), wert('h', 'H'), ...VIER]
  const zeile = (ps: Platz[]) => ps.map((p) => (p.gruppe ? `${p.gruppe}(${p.mitglieder.map((m) => m.id).join(',')})` : p.key)).join(' ')

  it.each([
    [1440, 'c h t1 t2 t3 t4'], [1150, 'c h t1 t2 t3 t4'], [1100, 'c h t1 t2 t3 t4'], [900, 'c h t1 t2 t3 t4'],
    [700, 'c h t1 t2 t3 t4'], [600, 'c h t1 t2 t3 t4'],
    [480, 'h c t1 weitere(t2,t3,t4)'], [390, 'h c t1 weitere(t2,t3,t4)'], [375, 'h c t1 weitere(t2,t3,t4)'],
    [360, 'h c weitere(t1,t2,t3,t4)'], [340, 'h c weitere(t1,t2,t3,t4)'],
  ])('voll + vier Themen bei %i px: oben «%s»; Standort und Reichweite im Bild, 0 Kreuzungen', (ctr, oben) => {
    const l = layoutUeberblick(VOLL, ctr, FAHRZEUG_PANORAMA_DEF)
    expect(zeile(l.oben)).toBe(oben)
    for (const id of ['c', 'h']) expect(l.oben.some((p) => p.gruppe == null && p.key === id), id).toBe(true)
    expect(hatKreuzung(l.oben) || hatKreuzung(l.unten) || hatKreuzungZwischen(l.oben, l.unten)).toBe(false)
    expect(l.oben.filter((p) => p.mitglieder.some((m) => m.art === 'thema')).every((p) => p.linie == null)).toBe(true)
  })

  it.each([480, 390, 375])('Reichweite + vier Themen bei %i px: zwei Themen im Bild, «Weitere (2)» mit den letzten zwei', (ctr) => {
    const l = layoutUeberblick([wert('c', 'C'), ...VIER], ctr, FAHRZEUG_PANORAMA_DEF)
    expect(zeile(l.oben)).toBe('c t1 t2 weitere(t3,t4)')
  })
})
