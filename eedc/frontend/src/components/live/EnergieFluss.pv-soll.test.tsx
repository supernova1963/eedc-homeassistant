/**
 * Energiefluss — wo das «Soll» der laufenden Stunde steht (Entscheid Gernot 5.11.2026).
 *
 * Bis 4.2.1 stand «Solar Soll ~x kW» als nackter Text über dem Haus, genau auf der
 * Flusslinie PV → Haus — schwer lesbar, und die Größe gehört zur PV, nicht zum Haus.
 * Seitdem trägt sie die PV selbst, mit EINER Zählung wie der «Gesamtleistung»-Chip
 * (`pvCount` über die Komponenten, #137):
 *
 * - **genau ein PV-Erzeuger:** zweite Zeile der PV-Kachel `Soll ~3,9 kW` (Form wie die
 *   SoC-Zeile: Wert · Soll · Name), auch bei 0 W; Tooltip-Zeile
 *   `Soll (Prognose der laufenden Stunde): ~3,9 kW`.
 * - **mehr als ein PV-Erzeuger:** am Chip `Gesamtleistung … · Soll ~3,9 kW`, der Satz im
 *   Chip-Tooltip angehängt. Ohne Chip (Summe 0) kein Soll — kein eigener Träger.
 *   Eine Gruppenkachel («PV gesamt», Ausrichtungsgruppen) trägt keine zweite Zeile.
 * - Ohne Soll (`null` oder 0) ist die PV-Kachel bitgleich zum Stand vor dem Umbau
 *   (Snapshot `src/test/energiefluss-pv-soll.snapshot.json`, am HEAD `c28461eca`
 *   aufgezeichnet). Neu schreiben nur bei absichtlicher Kachel-Änderung:
 *
 *       cd eedc/frontend && EEDC_PV_SOLL_SNAPSHOT=schreiben npx vitest run src/components/live/EnergieFluss.pv-soll.test.tsx
 *
 * - **kein PV-Knoten** (Nachtrag Gernot 5.11.2026 nach dem Lab-Test rc24, Winterborn: nur eine
 *   Wärmepumpe als Live-Knoten): Rückfall «Solar Soll ~6,5 kW» als Pille über dem Haus, Form wie
 *   der «gesamt …»-Chip darunter, Tooltip derselbe Soll-Satz. Mit PV-Knoten nie die Pille.
 *
 * Die Markierung `data-solar-soll` sitzt am tragenden Element (Kachel-Textzeile bzw.
 * Chip-Gruppe) — Proben und Playwright-Pläne finden das Soll darüber.
 *
 * ⚠ ResizeObserver-Stub wie in `EnergieFluss.gesamtleistung.test.tsx` (jsdom hat keinen).
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render } from '@testing-library/react'
import { existsSync, readFileSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import EnergieFluss, { TIP_GESAMTLEISTUNG } from './EnergieFluss'
import { ThemeProvider } from '../../context/ThemeContext'
import { stubMatchMedia } from '../../test/render'
import type { LiveKomponente } from '../../api/liveDashboard'
import { layoutEnergieFluss } from './energieFlussLayout'

const SNAPSHOT = join(process.cwd(), 'src', 'test', 'energiefluss-pv-soll.snapshot.json')
const SCHREIBEN = process.env.EEDC_PV_SOLL_SNAPSHOT === 'schreiben'
const ORIGINAL_RO = globalThis.ResizeObserver
const SOLL_TIP = 'Soll (Prognose der laufenden Stunde): ~3,9 kW'

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

beforeEach(() => {
  stubMatchMedia()
  localStorage.clear()
})
afterEach(() => {
  vi.unstubAllGlobals()
  globalThis.ResizeObserver = ORIGINAL_RO
})

const knoten = (key: string, extra: Partial<LiveKomponente>): LiveKomponente =>
  ({ key, label: key, icon: 'wrench', erzeugung_kw: null, verbrauch_kw: null, ...extra })
const pv = (id: number, label: string, ausr: string | null, kw: number, kwp: number | null = 3) =>
  knoten(`pv_${id}`, { label, icon: 'sun', erzeugung_kw: kw, typ: 'pv-module', ausrichtung_label: ausr, leistung_kwp: kwp })
const NETZ = knoten('netz', { label: 'Stromnetz', icon: 'zap', erzeugung_kw: 1 })
const HAUS = knoten('haushalt', { label: 'Restverbrauch', icon: 'home', verbrauch_kw: 0.6 })
const WP = knoten('waermepumpe_31', { label: 'Wärmepumpe', icon: 'flame', typ: 'waermepumpe', verbrauch_kw: 1.4 })

const EIN_PV = () => [pv(1, 'Dach Süd', 'Süd', 6.2, 13.3), WP, NETZ, HAUS]
const ZWEI_PV = (kw = 3) => [pv(1, 'Dach Süd', 'Süd', kw), pv(2, 'Garage', 'West', kw), WP, NETZ, HAUS]

function zeichne(komponenten: LiveKomponente[], pvSollKw: number | null, { breite = 1150, lite = false } = {}) {
  localStorage.setItem('eedc-energiefluss-lite', lite ? '1' : '0')
  mitBreite(breite)
  const summePv = komponenten.filter(k => k.key.startsWith('pv_')).reduce((s, k) => s + (k.erzeugung_kw ?? 0), 0)
  return render(
    <ThemeProvider>
      <EnergieFluss
        komponenten={komponenten}
        summeErzeugung={summePv + 1}
        summeVerbrauch={summePv + 1}
        summePv={summePv}
        gauges={[]}
        pvSollKw={pvSollKw}
      />
    </ThemeProvider>,
  )
}

const kachel = (c: HTMLElement, name: string) =>
  [...c.querySelectorAll('svg g[data-title]')].find(g => (g.getAttribute('data-title') ?? '').startsWith(name))!
const pvKacheln = (c: HTMLElement) =>
  [...c.querySelectorAll('svg g[data-title]')].filter(g => g.querySelector('foreignObject')
    && /^(Dach Süd|Garage|PV gesamt|String|Süd|Ost|West)/.test(g.getAttribute('data-title') ?? ''))
const texte = (el: Element) => [...el.querySelectorAll('text')].map(t => t.textContent?.trim() ?? '')
const chip = (c: HTMLElement) => c.querySelector('g[data-gesamtleistung]')
const sollTraeger = (c: HTMLElement) => [...c.querySelectorAll('[data-solar-soll]')]
/** Die Rückfall-Pille über dem Haus (kein PV-Knoten): die Soll-Gruppe, die nicht der Chip ist. */
const hausPille = (c: HTMLElement) => c.querySelector('g[data-solar-soll]:not([data-gesamtleistung])')
const alleTexte = (c: HTMLElement) => [...c.querySelectorAll('svg text')].map(t => t.textContent?.trim() ?? '')

/** Ein Element kanonisch: Tag, Attribute sortiert, Kinder rekursiv; Icon-Innenleben draußen (Muster `kachel-sot`). */
function serialisiere(el: Element, imIcon = false): string {
  const attrs = [...el.attributes].map(a => `${a.name}=${JSON.stringify(a.value)}`).sort().join(' ')
  const tag = el.tagName.toLowerCase()
  if (imIcon) return `<${tag} ${attrs}/>`
  const kinder = [...el.childNodes].map(n => {
    if (n.nodeType === 3) return (n.textContent ?? '').trim()
    if (n.nodeType !== 1) return ''
    const kind = n as Element
    return serialisiere(kind, tag === 'foreignobject' && kind.tagName.toLowerCase() === 'svg')
  }).filter(Boolean)
  return `<${tag} ${attrs}>${kinder.join('')}</${tag}>`
}

describe('Soll bei genau einem PV-Erzeuger — zweite Zeile der PV-Kachel', () => {
  it('Soll 3,9 ⇒ «Soll ~3,9 kW» zwischen Wert und Name, Name verschoben, nichts über dem Haus', () => {
    const komp = EIN_PV()
    const { container } = zeichne(komp, 3.9)
    const k = kachel(container, 'Dach Süd')
    expect(texte(k)).toEqual(['6.200 W', 'Soll ~3,9 kW', 'Dach Süd'])
    const zeile = k.querySelector('text[data-solar-soll]')
    expect(zeile?.textContent).toBe('Soll ~3,9 kW')
    // Regel `zweiteZeile`: der Name rückt nach unten wie bei der SoC-Zeile
    const l = layoutEnergieFluss(komp, { breitePx: 1150 })
    const knotenPv = l.nodes.find(n => n.komp.key === 'pv_1')!
    const name = [...k.querySelectorAll('text')].at(-1)!
    expect(Number(name.getAttribute('y'))).toBe(knotenPv.y + l.dims.nodeH / 2 - 4)
    expect(Number(zeile!.getAttribute('y'))).toBe(knotenPv.y + l.dims.kwFontSize + 2)
    // genau ein Träger, kein Text «Solar Soll», kein Chip
    expect(sollTraeger(container).length).toBe(1)
    expect(alleTexte(container).some(t => t.includes('Solar Soll'))).toBe(false)
    expect(chip(container)).toBeNull()
  })

  it('der Kachel-Tooltip trägt die Soll-Zeile (data-title und <title>)', () => {
    const { container } = zeichne(EIN_PV(), 3.9)
    const k = kachel(container, 'Dach Süd')
    expect(k.getAttribute('data-title')!.split('\n')).toContain(SOLL_TIP)
    expect(k.querySelector(':scope > title')?.textContent?.split('\n')).toContain(SOLL_TIP)
  })

  it('mit Auslastungs-Pegel steht die Zeile neutral (Kommentar am Typ `ZweiteZeile`)', () => {
    const { container } = zeichne(EIN_PV(), 3.9)
    const zeile = kachel(container, 'Dach Süd').querySelector('text[data-solar-soll]')!
    expect(zeile.getAttribute('class')).toBe('font-semibold fill-gray-900 dark:fill-white')
    expect(zeile.getAttribute('fill')).toBeNull()
  })

  it('auch bei 0 W PV (Kachel inaktiv), sobald das Soll > 0 ist — dann grau', () => {
    const { container } = zeichne([pv(1, 'Dach Süd', 'Süd', 0, 13.3), WP, NETZ, HAUS], 3.9)
    const k = kachel(container, 'Dach Süd')
    expect(texte(k)).toEqual(['0 W', 'Soll ~3,9 kW', 'Dach Süd'])
    expect(k.querySelector('text[data-solar-soll]')!.getAttribute('class')).toBe('font-semibold fill-gray-500 dark:fill-gray-400')
  })

  it('kleines Handy (360 px) und Lite: dieselbe Regel', () => {
    for (const [breite, lite] of [[360, false], [360, true], [1150, true]] as const) {
      const { container, unmount } = zeichne(EIN_PV(), 3.9, { breite, lite })
      expect(kachel(container, 'Dach Süd').querySelector('text[data-solar-soll]')?.textContent, `${breite} lite=${lite}`)
        .toBe('Soll ~3,9 kW')
      expect(sollTraeger(container).length, `${breite} lite=${lite}`).toBe(1)
      unmount()
    }
  })

  it('Soll null oder 0 ⇒ keine zweite Zeile, PV-Kachel bitgleich zum Stand vor dem Umbau', () => {
    const ist: Record<string, string> = {}
    for (const lite of [false, true]) for (const soll of [null, 0]) {
      const { container, unmount } = zeichne(EIN_PV(), soll, { lite })
      const k = kachel(container, 'Dach Süd')
      expect(texte(k), `soll=${soll} lite=${lite}`).toEqual(['6.200 W', 'Dach Süd'])
      expect(sollTraeger(container).length, `soll=${soll} lite=${lite}`).toBe(0)
      expect(k.getAttribute('data-title'), `soll=${soll} lite=${lite}`).not.toContain('Soll')
      ist[`lite=${lite} soll=${soll}`] = serialisiere(k)
      unmount()
    }
    if (SCHREIBEN) {
      writeFileSync(SNAPSHOT, JSON.stringify(ist, null, 1) + '\n')
      return
    }
    expect(existsSync(SNAPSHOT), 'Snapshot fehlt — erzeugen per Befehl im Kopf dieser Datei').toBe(true)
    expect(ist).toEqual(JSON.parse(readFileSync(SNAPSHOT, 'utf8')))
  })
})

describe('Soll bei mehreren PV-Erzeugern — am «Gesamtleistung»-Chip', () => {
  it('zwei PV-Knoten, Summe > 0, Soll 3,9 ⇒ Chip «Gesamtleistung … · Soll ~3,9 kW», keine Kachel trägt das Soll', () => {
    const { container } = zeichne(ZWEI_PV(), 3.9)
    const c = chip(container)!
    expect(c.querySelector('text')?.textContent).toBe('Gesamtleistung 6.000 W · Soll ~3,9 kW')
    expect(sollTraeger(container).map(e => e === c)).toEqual([true])
    for (const k of pvKacheln(container)) {
      expect(texte(k).some(t => t.includes('Soll'))).toBe(false)
      expect(k.getAttribute('data-title')).not.toContain('Soll')
    }
    expect(alleTexte(container).some(t => t.includes('Solar Soll'))).toBe(false)
  })

  it('der Chip-Tooltip hängt den Soll-Satz an; ohne Soll bleibt er wortgleich', () => {
    const mit = zeichne(ZWEI_PV(), 3.9)
    const c = chip(mit.container)!
    expect(c.getAttribute('data-title')).toBe(`${TIP_GESAMTLEISTUNG}\n${SOLL_TIP}`)
    expect(c.querySelector(':scope > title')?.textContent).toBe(`${TIP_GESAMTLEISTUNG}\n${SOLL_TIP}`)
    mit.unmount()
    const ohne = zeichne(ZWEI_PV(), null)
    expect(chip(ohne.container)!.getAttribute('data-title')).toBe(TIP_GESAMTLEISTUNG)
    expect(chip(ohne.container)!.querySelector('text')?.textContent).toBe('Gesamtleistung 6.000 W')
    expect(sollTraeger(ohne.container).length).toBe(0)
  })

  it('Soll 0 bei zwei PV-Knoten ⇒ Chip ohne Soll', () => {
    const { container } = zeichne(ZWEI_PV(), 0)
    expect(chip(container)!.querySelector('text')?.textContent).toBe('Gesamtleistung 6.000 W')
    expect(sollTraeger(container).length).toBe(0)
  })

  it('zwei PV-Knoten mit Summe 0, Soll 0,1 ⇒ kein Chip, kein Soll im Bild', () => {
    const { container } = zeichne(ZWEI_PV(0), 0.1)
    expect(chip(container)).toBeNull()
    expect(sollTraeger(container).length).toBe(0)
    expect(alleTexte(container).some(t => t.includes('Soll'))).toBe(false)
  })

  it('gruppierte PV («PV gesamt» am Handy, eine gezeichnete Kachel) ⇒ Soll im Chip, Gruppenkachel ohne zweite Zeile', () => {
    const komp = [...[1, 2, 3, 4].map(i => pv(i, `String ${i}`, null, 1)), WP, NETZ, HAUS]
    const { container } = zeichne(komp, 3.9, { breite: 360 })
    const l = layoutEnergieFluss(komp, { breitePx: 360 })
    const gruppe = l.nodes.find(n => n.komp.key.startsWith('pv_') && n.mitglieder)!
    expect(gruppe).toBeDefined()
    expect(l.nodes.filter(n => n.komp.key.startsWith('pv_'))).toHaveLength(1)
    const c = chip(container)!
    expect(c.querySelector('text')?.textContent).toBe('Gesamtleistung 4.000 W · Soll ~3,9 kW')
    // der längere Chip bleibt in der Zeichenfläche (Breite aus der Textlänge, mittig über dem schmalen Rahmen)
    const rect = c.querySelector('rect')!
    expect(Number(rect.getAttribute('x'))).toBeGreaterThanOrEqual(0)
    expect(Number(rect.getAttribute('x')) + Number(rect.getAttribute('width'))).toBeLessThanOrEqual(l.W)
    expect(sollTraeger(container).map(e => e === c)).toEqual([true])
    const k = kachel(container, gruppe.komp.label)
    expect(k.querySelector('[data-stapel]')).not.toBeNull()
    expect(texte(k)).toHaveLength(2)
    expect(texte(k).some(t => t.includes('Soll'))).toBe(false)
  })

  it('Ausrichtungsgruppen (neun Strings, 1150 px) ⇒ Soll im Chip, keine Gruppenkachel trägt es', () => {
    const neun = [
      pv(11, 'Süd 1', 'Süd', 1.9), pv(12, 'Süd 2', 'Süd', 1.8), pv(13, 'Süd 3', 'Süd', 1.7),
      pv(14, 'Süd Garage', 'Süd', 1.2), pv(15, 'Süd Gaube', 'Süd', 0.9), pv(16, 'Ost 1', 'Ost', 0.6),
      pv(17, 'Ost 2', 'Ost', 0.5), pv(18, 'West 1', 'West', 1.4), pv(19, 'West 2', 'West', 1.3),
    ]
    const { container } = zeichne([...neun, NETZ, HAUS], 12.4)
    const c = chip(container)!
    expect(c.querySelector('text')?.textContent).toBe('Gesamtleistung 11,3 kW · Soll ~12,4 kW')
    expect(sollTraeger(container).map(e => e === c)).toEqual([true])
    const gruppen = [...container.querySelectorAll('svg g[data-title]')].filter(g => g.querySelector('[data-stapel]'))
    expect(gruppen.length).toBeGreaterThan(0)
    for (const g of gruppen) expect(texte(g)).toHaveLength(2)
  })
})

describe('Rückfall ohne PV-Knoten — «Solar Soll» als Pille über dem Haus (Nachtrag 5.11.2026)', () => {
  const OHNE_PV = () => [WP, NETZ, HAUS]

  it('kein PV-Knoten, Soll 6,5 ⇒ Pille «Solar Soll ~6,5 kW» mit data-solar-soll und Tooltip, über dem Haus', () => {
    const komp = OHNE_PV()
    const { container } = zeichne(komp, 6.5)
    const p = hausPille(container)!
    expect(p).not.toBeNull()
    expect(p.querySelector('text')?.textContent).toBe('Solar Soll ~6,5 kW')
    expect(sollTraeger(container).map(e => e === p)).toEqual([true])
    const tip = 'Soll (Prognose der laufenden Stunde): ~6,5 kW'
    expect(p.getAttribute('data-title')).toBe(tip)
    expect(p.querySelector(':scope > title')?.textContent).toBe(tip)
    // Form wie der «gesamt …»-Chip: weiße Pille, Unterkante 4 Einheiten über dem Haus-Kreis
    const rect = p.querySelector('rect')!
    expect(rect.getAttribute('class')).toMatch(/^fill-white dark:fill-gray-800 /)
    const l = layoutEnergieFluss(komp, { breitePx: 1150 })
    const hoehe = Number(rect.getAttribute('height'))
    expect(Number(rect.getAttribute('y')) + hoehe).toBeCloseTo(l.CY - l.dims.hausR - 4, 9)
    expect(Number(rect.getAttribute('rx'))).toBeCloseTo(hoehe / 2, 9)
    expect(Number(rect.getAttribute('x')) + Number(rect.getAttribute('width')) / 2).toBeCloseTo(l.CX, 9)
    expect(chip(container)).toBeNull()
  })

  it('Farben je Hintergrund wie der frühere Soll-Text (Text und Rand lila)', () => {
    const erwartet: Record<string, [string, string]> = {
      default: ['fill-purple-500 dark:fill-purple-400', 'stroke-purple-500 dark:stroke-purple-400'],
      milchstrasse: ['fill-purple-500 dark:fill-purple-400', 'stroke-purple-500 dark:stroke-purple-400'],
      sunset: ['fill-purple-800 dark:fill-purple-400', 'stroke-purple-800 dark:stroke-purple-400'],
      alps: ['fill-indigo-800 dark:fill-indigo-300', 'stroke-indigo-800 dark:stroke-indigo-300'],
      haus: ['fill-indigo-800 dark:fill-purple-400', 'stroke-indigo-800 dark:stroke-purple-400'],
    }
    for (const [hg, [text, rand]] of Object.entries(erwartet)) {
      localStorage.setItem('eedc-energiefluss-bg', hg)
      const { container, unmount } = zeichne(OHNE_PV(), 6.5)
      const p = hausPille(container)!
      expect(p.querySelector('text')?.getAttribute('class'), hg).toBe(`font-semibold ${text}`)
      expect(p.querySelector('rect')?.getAttribute('class'), hg).toBe(`fill-white dark:fill-gray-800 ${rand}`)
      expect(p.querySelector('rect')?.getAttribute('stroke'), hg).toBeNull()
      unmount()
    }
  })

  it('kein PV-Knoten, Soll null oder 0 ⇒ nichts', () => {
    for (const soll of [null, 0]) {
      const { container, unmount } = zeichne(OHNE_PV(), soll)
      expect(sollTraeger(container).length, `soll=${soll}`).toBe(0)
      expect(alleTexte(container).some(t => t.includes('Soll')), `soll=${soll}`).toBe(false)
      unmount()
    }
  })

  it('mit PV-Knoten nie die Pille: ein PV, zwei PV, zwei PV mit Summe 0, Gruppe', () => {
    const faelle: [string, LiveKomponente[], number][] = [
      ['1 PV', EIN_PV(), 1150],
      ['1 PV bei 0 W', [pv(1, 'Dach Süd', 'Süd', 0, 13.3), WP, NETZ, HAUS], 1150],
      ['2 PV', ZWEI_PV(), 1150],
      ['2 PV Summe 0', ZWEI_PV(0), 1150],
      ['Gruppe', [...[1, 2, 3, 4].map(i => pv(i, `String ${i}`, null, 1)), WP, NETZ, HAUS], 360],
    ]
    for (const [name, komp, breite] of faelle) {
      const { container, unmount } = zeichne(komp, 3.9, { breite })
      expect(hausPille(container), name).toBeNull()
      expect(alleTexte(container).some(t => t.includes('Solar Soll')), name).toBe(false)
      unmount()
    }
  })
})
