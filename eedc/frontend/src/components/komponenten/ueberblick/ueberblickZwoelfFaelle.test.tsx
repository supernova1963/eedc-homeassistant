/**
 * Überblick Wärme/Klima — Zwölf-Fälle-Snapshot, seit Halt H1 dreizehn Fälle (P-433-2b Sitzung 1a, Bauplan §4 «E0
 * Panorama-Deskriptor, byte-gleich»).
 *
 * **Wozu:** E0 zieht die Wärme-Kopplungen aus `ueberblickLayout.ts` und `UeberblickSchaubild.tsx` in einen
 * Panorama-Deskriptor (`panorama.ts`, `WAERME_PANORAMA_DEF`). Das Wärme/Klima-Schaubild darf sich dabei um kein Byte
 * ändern. Dieser Snapshot wurde **vor** dem Umbau am HEAD `fd9ad9c1` aufgezeichnet und ist seitdem der Wächter:
 * je Fall und Breite das ganze Layout (Reihen, Plätze, Gruppen, Anker-, Kachel- und Linienkoordinaten, Dims, Wechsel,
 * Rückfall) als JSON **und** die gezeichnete SVG des Schaubilds (Bild, aria, Linien, Kacheln, Gruppenname, Farbe
 * «Weitere», «Ohne Sensor»-Zeile) sowie die geöffnete Liste der ersten Gruppe, serialisiert mit sortierten Attributen —
 * diese zwei nur als sha256 (Repo-Größe; eine Abweichung nennt Fall und Breite). Den vollen Text je Zelle schreibt
 * `EEDC_UEBERBLICK_VOLLTEXT=<datei.json>` zum Vergleich zweier Stände. Gleichwertig zur Fassung mit vollem SVG-Text
 * belegt (Bericht S1a).
 *
 * **Fälle (12):** Lab Winterborn · Lab mit zwei «Strom heute» · Mathek ohne Stammdatum (G) · dito mit «Wärme heute» ·
 * Mathek Fußbodenheizung (K) · Mathek Heizkörper (J) · dietmar · dietmar mit fünf Innengeräten, Außen und Warmwasser
 * («Innengeräte (n−3)» an N, «Weitere») · A + C · A + A («Wärmepumpen (2)» links) · F + E + D (Rückfall der
 * Warmwasser-WP) · O + O + I («Wärmepumpen (2)» rechts) · **13 (Halt H1):** zwei Klima-Geräte mit je zwei
 * Innengeräten (L, M, L, M — die Restgruppe «Innengeräte (n−3)» hängt an N, nicht am vierten Innengerät; der
 * Deskriptor trägt dafür `ankerRestgruppe`). **Breiten (5):** 1440 · 900 · 600 · 390 · 360 px.
 *
 * **Wenn dieser Test rot wird:** Überblick absichtlich geändert? Dann den Snapshot neu schreiben und den Diff im
 * Commit mitschicken:
 *
 *     cd eedc/frontend && EEDC_UEBERBLICK_SNAPSHOT=schreiben npx vitest run src/components/komponenten/ueberblick/ueberblickZwoelfFaelle.test.tsx
 *
 * Unabsichtlich? Dann hat sich das Wärme/Klima-Schaubild still geändert — genau der Fall, gegen den er steht.
 */
import { describe, it, expect, beforeAll, afterAll, vi } from 'vitest'
import { render, cleanup, fireEvent } from '@testing-library/react'
import { existsSync, readFileSync, writeFileSync } from 'node:fs'
import { createHash } from 'node:crypto'
import { join } from 'node:path'
import UeberblickSchaubild from './UeberblickSchaubild'
import { layoutUeberblick, type LayoutKachel } from './ueberblickLayout'
import type { UeberblickKachel } from './kachelAnker'
import { WAERME_PANORAMA_DEF } from './waermePanoramaAnker'
import { ThemeProvider } from '../../../context/ThemeContext'
import { stubMatchMedia } from '../../../test/render'
import { CHART_COLORS, KATEGORIE_FARBEN } from '../../../lib'
import type { LiveInnengeraet } from '../../../api/liveDashboard'

const SNAPSHOT = join(process.cwd(), 'src', 'test', 'ueberblick-zwoelf-faelle.snapshot.json')
const SCHREIBEN = process.env.EEDC_UEBERBLICK_SNAPSHOT === 'schreiben'
const VOLLTEXT = process.env.EEDC_UEBERBLICK_VOLLTEXT
const ORIGINAL_RO = globalThis.ResizeObserver

function mitBreite(px: number) {
  vi.stubGlobal('ResizeObserver', class {
    private cb: ResizeObserverCallback
    constructor(cb: ResizeObserverCallback) { this.cb = cb }
    observe(target: Element) {
      this.cb([{ target, contentRect: { width: px, height: 500 } } as unknown as ResizeObserverEntry], this as unknown as ResizeObserver)
    }
    unobserve() {}
    disconnect() {}
  })
}

// ── Fälle ─────────────────────────────────────────────────────────────────────

const geraet = (id: string, anker: string): LayoutKachel => ({ id, art: 'geraet', anker } as LayoutKachel)
const wert = (id: string, anker: string): LayoutKachel => ({ id, art: 'wert', anker } as LayoutKachel)
const innen = (n: number): LayoutKachel[] =>
  Array.from({ length: n }, (_, i) => ({ id: `innen-${i + 1}`, art: 'innengeraet', anker: ['L', 'M', 'N'][Math.min(i, 2)] } as LayoutKachel))

const LAB: LayoutKachel[] = [
  wert('aussen', 'HIMMEL'), geraet('nibe', 'C'), wert('ww', 'E'), wert('vorlauf', 'K'), wert('waerme', 'K'),
  geraet('klima', 'O'), ...innen(2),
]
const MATHEK = (v: string, waerme = false): LayoutKachel[] => [
  wert('aussen', 'HIMMEL'), geraet('wp', 'C'), wert('vorlauf', v), ...(waerme ? [wert('waerme', v)] : []),
  wert('zusatz', 'D'), wert('ww', 'E'), wert('strom', 'I'),
]
const DIETMAR: LayoutKachel[] = [wert('strom', 'I'), ...innen(3), geraet('klima', 'O')]

const FAELLE: Record<string, LayoutKachel[]> = {
  'Lab': LAB,
  'Lab mit zwei Strom heute': [...LAB, wert('s1', 'I'), wert('s2', 'I')],
  'Mathek ohne Stammdatum (G)': MATHEK('G'),
  'Mathek ohne Stammdatum mit Wärme heute (G)': MATHEK('G', true),
  'Mathek Fußbodenheizung (K)': MATHEK('K', true),
  'Mathek Heizkörper (J)': MATHEK('J', true),
  'dietmar': DIETMAR,
  'dietmar mit fünf Innengeräten, Außen und Warmwasser': [wert('strom', 'I'), ...innen(5), geraet('klima', 'O'), wert('aussen', 'HIMMEL'), wert('ww', 'E')],
  'A + C': [geraet('lw', 'A'), geraet('sole', 'C'), wert('ww', 'E')],
  'A + A': [geraet('lw1', 'A'), geraet('lw2', 'A'), wert('ww', 'E')],
  'F + E + D': [geraet('bw', 'F'), wert('ww', 'E'), wert('zusatz', 'D')],
  'O + O + I': [geraet('k1', 'O'), geraet('k2', 'O'), wert('strom', 'I')],
  'zwei Klima-Geräte 2+2 (Halt H1)': [
    geraet('klima1', 'O'), geraet('klima2', 'O'),
    { id: 'innen-1-1', art: 'innengeraet', anker: 'L' }, { id: 'innen-1-2', art: 'innengeraet', anker: 'M' },
    { id: 'innen-2-1', art: 'innengeraet', anker: 'L' }, { id: 'innen-2-2', art: 'innengeraet', anker: 'M' },
  ] as LayoutKachel[],
}
const BREITEN = [1440, 900, 600, 390, 360] as const

/** Eine Zeichen-Kachel aus der Layout-Kachel — feste, art-typische Werte (Gerät mit Modus-Zeile, Innengerät mit
 *  Live-Datensatz für die Gruppenliste, Wert in Rollenfarbe). */
function zuKachel(t: LayoutKachel, i: number): UeberblickKachel {
  const basis = { id: t.id, art: t.art, anker: t.anker, label: `Kachel ${t.id}`, tip: `${t.id}\nQuelle: Probe`, investitionId: 7 }
  if (t.art === 'geraet') {
    const color = KATEGORIE_FARBEN.waermepumpe
    return { ...basis, icon: 'heater', color, isActive: true, wertText: '1,2 kW', zweiteZeile: { text: 'Heizen', fill: color }, leistungKw: 1.2 + i / 10 }
  }
  if (t.art === 'innengeraet') {
    const g: LiveInnengeraet = { investition_id: 7, innengeraet_id: i, bezeichnung: `Innengerät ${t.id}`, leistung_w: 300 + i, soll_temperatur_c: 21, ist_temperatur_c: 20.5 }
    return { ...basis, icon: 'fan', color: KATEGORIE_FARBEN.waermepumpe, isActive: true, wertText: '20,5 °C', zweiteZeile: { text: 'Soll 21,0 °C', fill: KATEGORIE_FARBEN.waermepumpe }, leistungKw: g.leistung_w! / 1000, innengeraet: g }
  }
  return { ...basis, icon: 'thermometer', color: CHART_COLORS.wpStrom, isActive: true, wertText: '6,4 kWh', zweiteZeile: null, wertTextKompakt: '6 kWh' }
}

// ── Serialisierung ────────────────────────────────────────────────────────────

/** Ein Element kanonisch: Tag, Attribute sortiert, Kinder rekursiv; Icon-Innenleben (Lucide-Geometrie) draußen. */
function serialisiere(el: Element, imIcon = false): string {
  const attrs = [...el.attributes].map((a) => `${a.name}=${JSON.stringify(a.value)}`).sort().join(' ')
  const tag = el.tagName.toLowerCase()
  if (imIcon) return `<${tag} ${attrs}/>`
  const kinder = [...el.childNodes].map((n) => {
    if (n.nodeType === 3) return (n.textContent ?? '').trim()
    if (n.nodeType !== 1) return ''
    const kind = n as Element
    const istIcon = tag === 'foreignobject' && kind.tagName.toLowerCase() === 'svg'
    return serialisiere(kind, istIcon)
  }).filter(Boolean)
  return `<${tag} ${attrs}>${kinder.join('')}</${tag}>`
}

/** Das Layout als JSON-Daten — ohne die Kachel-Objekte (nur ihre IDs). */
function layoutDaten(fall: LayoutKachel[], ctr: number) {
  const l = layoutUeberblick(fall, ctr, WAERME_PANORAMA_DEF)
  const platz = (p: (typeof l.oben)[number] | null) => p && ({
    key: p.key, mitglieder: p.mitglieder.map((m) => m.id), gruppe: p.gruppe, anker: p.anker,
    ax: p.ax, ay: p.ay, x: p.x, y: p.y, seite: p.seite, linie: p.linie,
  })
  return {
    W: l.W, k: l.k, dims: l.dims, geraet: l.geraet, schriftPx: l.schriftPx,
    oben: l.oben.map(platz), unten: l.unten.map(platz), links: platz(l.links), rechts: platz(l.rechts),
    reihenwechsel: l.reihenwechsel, rueckfall: l.rueckfall,
  }
}

const sha256 = (s: string) => createHash('sha256').update(s, 'utf8').digest('hex')

/** Das gezeichnete Schaubild; ist eine Gruppe da, zusätzlich die geöffnete Liste der ersten Gruppe (`offen`) — beide
 *  als sha256 des serialisierten Texts. */
const volltext: Record<string, { zu: string; offen: string | null }> = {}
function zeichnung(fall: LayoutKachel[], ctr: number, zelle: string): { zu: string; offen: string | null } {
  mitBreite(ctr)
  const kacheln = fall.map(zuKachel)
  const ohneSensor = ['Leistung Probe', 'Warmwasser-Temperatur']
  const { container } = render(<ThemeProvider><UeberblickSchaubild kacheln={kacheln} ohneSensor={ohneSensor} panorama={WAERME_PANORAMA_DEF} /></ThemeProvider>)
  const wurzel = container.querySelector('[data-ueberblick-schaubild]')!
  const zu = serialisiere(wurzel)
  const knopf = container.querySelector('[data-gruppe]')
  let offen: string | null = null
  if (knopf) {
    fireEvent.click(knopf)
    offen = serialisiere(container.querySelector('[data-gruppen-liste]')!)
  }
  cleanup()
  volltext[zelle] = { zu, offen }
  return { zu: sha256(zu), offen: offen == null ? null : sha256(offen) }
}

type Zelle = { layout: ReturnType<typeof layoutDaten>; schaubild: { zu: string; offen: string | null } }
const ist: Record<string, Zelle> = {}

beforeAll(() => {
  stubMatchMedia()
  for (const [name, fall] of Object.entries(FAELLE)) {
    for (const ctr of BREITEN) {
      const zelle = `${name} @${ctr}`
      ist[zelle] = { layout: layoutDaten(fall, ctr), schaubild: zeichnung(fall, ctr, zelle) }
    }
  }
  if (VOLLTEXT) writeFileSync(VOLLTEXT, JSON.stringify(volltext, null, 1) + '\n')
})
afterAll(() => {
  vi.unstubAllGlobals()
  globalThis.ResizeObserver = ORIGINAL_RO
})

describe('Überblick Wärme/Klima — Zwölf-Fälle-Snapshot (P-433-2b S1a, byte-gleich)', () => {
  it('13 Fälle × 5 Breiten = 65 Zellen; Gruppen kommen vor (Wärmepumpen, Innengeräte, Weitere), Plätze, Rückfall, Wechsel, Restgruppe', () => {
    expect(Object.keys(FAELLE)).toHaveLength(13)
    expect(Object.keys(ist)).toHaveLength(65)
    const gruppen = Object.values(ist).flatMap((z) => [...z.layout.oben, ...z.layout.unten, z.layout.links, z.layout.rechts])
      .map((p) => p?.gruppe).filter((g) => g != null)
    expect(new Set(gruppen)).toEqual(new Set(['geraete', 'innengeraete', 'weitere']))
    expect(Object.values(ist).filter((z) => z.schaubild.offen != null).length).toBeGreaterThan(20)
    expect(Object.values(ist).some((z) => z.layout.links != null)).toBe(true)
    expect(Object.values(ist).some((z) => z.layout.rechts != null)).toBe(true)
    expect(Object.values(ist).some((z) => z.layout.rueckfall.length > 0)).toBe(true)
    expect(Object.values(ist).some((z) => z.layout.reihenwechsel.length > 0)).toBe(true)
    expect(Object.values(ist).some((z) => [...z.layout.oben, ...z.layout.unten].some((p) => p?.key === 'grp-innengeraete-rest'))).toBe(true)
    // Halt H1: zwei Klima-Geräte 2+2 — die Restgruppe hängt an N, ihr einziges Mitglied ist das zweite Innengerät (M).
    const h1 = ist['zwei Klima-Geräte 2+2 (Halt H1) @1440'].layout
    const rest = [...h1.oben, ...h1.unten].find((p) => p?.key === 'grp-innengeraete-rest')!
    expect([rest.anker, rest.mitglieder]).toEqual(['N', ['innen-2-2']])
  })

  it('jede Zelle ist gleich dem eingecheckten Snapshot (aufgezeichnet vor E0)', () => {
    if (SCHREIBEN) {
      writeFileSync(SNAPSHOT, JSON.stringify(ist, null, 1) + '\n')
      return
    }
    expect(existsSync(SNAPSHOT), 'Snapshot fehlt — erzeugen per Befehl im Kopf dieser Datei').toBe(true)
    const soll = JSON.parse(readFileSync(SNAPSHOT, 'utf8')) as Record<string, Zelle>
    expect(Object.keys(ist).sort()).toEqual(Object.keys(soll).sort())
    for (const name of Object.keys(soll)) {
      expect(ist[name].layout, `${name} (Layout)`).toEqual(soll[name].layout)
      expect(ist[name].schaubild.zu, `${name} (Schaubild)`).toBe(soll[name].schaubild.zu)
      expect(ist[name].schaubild.offen, `${name} (Schaubild, Gruppenliste offen)`).toBe(soll[name].schaubild.offen)
    }
  })
})
