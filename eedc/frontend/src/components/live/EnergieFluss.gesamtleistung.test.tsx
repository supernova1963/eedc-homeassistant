/**
 * Energiefluss — „Gesamtleistung"-Rahmen (Bau A §A6, #341 Rainer) und das
 * deutsche kWp-Format im Kachel-Tooltip (Beifang NB-2 aus A4).
 *
 * Die Geometrie (Versatz, Rahmen um die PV-Reihe, „Karte nie höher") prüft
 * `energieFlussLayout.test.ts`. Hier steht, was nur der Render zeigt: dass
 * Rahmen und Chip wirklich gezeichnet werden, wann nicht (#137: ein
 * PV-Knoten; nachts: Summe 0), dass „Solarleistung" über dem Haus weg ist,
 * dass der Chip den Tooltip trägt und wo das Soll steht (seit 5.11.2026 an der
 * PV: im Chip bzw. in der einzigen PV-Kachel, Detail `EnergieFluss.pv-soll.test.tsx`).
 *
 * ⚠ ResizeObserver-Stub wie in `EnergieFluss.gruppen.test.tsx` (jsdom hat keinen).
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render } from '@testing-library/react'
import EnergieFluss, { TIP_GESAMTLEISTUNG } from './EnergieFluss'
import { ThemeProvider } from '../../context/ThemeContext'
import { stubMatchMedia } from '../../test/render'
import type { LiveKomponente } from '../../api/liveDashboard'
import { layoutEnergieFluss } from './energieFlussLayout'

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

/** Neun Strings wie Plan-Tabelle D (Süd 5 · Ost 2 · West 2) — bei 1150 px nach Ausrichtung gruppiert. */
const neunStrings = () => [
  pv(11, 'Süd 1', 'Süd', 1.9), pv(12, 'Süd 2', 'Süd', 1.8), pv(13, 'Süd 3', 'Süd', 1.7),
  pv(14, 'Süd Garage', 'Süd', 1.2), pv(15, 'Süd Gaube', 'Süd', 0.9), pv(16, 'Ost 1', 'Ost', 0.6),
  pv(17, 'Ost 2', 'Ost', 0.5), pv(18, 'West 1', 'West', 1.4), pv(19, 'West 2', 'West', 1.3),
]

function zeichne(komponenten: LiveKomponente[], summePv: number, pvSollKw: number | null = null) {
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

const rahmen = (c: HTMLElement) => c.querySelector('rect[data-gesamtleistung-rahmen]')
const chip = (c: HTMLElement) => c.querySelector('g[data-gesamtleistung]')
const alleTexte = (c: HTMLElement) => [...c.querySelectorAll('svg text')].map(t => t.textContent?.trim() ?? '')
const zahl = (el: Element | null, attr: string) => Number(el?.getAttribute(attr))

describe('EnergieFluss §A6 — „Gesamtleistung" im Rahmen über der PV-Reihe', () => {
  it('mehrere Strings, gruppiert (1150 px): Rahmen um die PV-Reihe, Chip „Gesamtleistung <Wert>", kein „Solarleistung" mehr', () => {
    mitBreite(1150)
    const komp = [...neunStrings(), WP, NETZ, HAUS]
    const { container } = zeichne(komp, 11.3)
    const r = rahmen(container)
    expect(r).not.toBeNull()
    // Geometrie = Layout (eine Quelle): 6 · 31 · 588 × 64 bei k = 1 (s. Layout-Probe)
    const l = layoutEnergieFluss(komp, { breitePx: 1150 })
    expect([zahl(r, 'x'), zahl(r, 'y'), zahl(r, 'width'), zahl(r, 'height')])
      .toEqual([l.gesamtRahmen!.x, l.gesamtRahmen!.y, l.gesamtRahmen!.breite, l.gesamtRahmen!.hoehe])
    expect(r!.getAttribute('fill')).toBe('none')
    expect(chip(container)?.querySelector('text')?.textContent).toBe('Gesamtleistung 11,3 kW')
    expect(alleTexte(container).some(t => t.startsWith('Solarleistung'))).toBe(false)
  })

  it('mehrere Strings einzeln (1150 px, drei Strings): Rahmen und Chip ebenso', () => {
    mitBreite(1150)
    const { container } = zeichne([pv(1, 'Ost', 'Ost', 1.2), pv(2, 'Süd', 'Süd', 3.1), pv(3, 'West', 'West', 1.5), WP, NETZ, HAUS], 5.8)
    expect(rahmen(container)).not.toBeNull()
    expect(chip(container)?.textContent).toContain('Gesamtleistung 5.800 W')
  })

  it('der Chip trägt den bisherigen Tooltip (data-title + <title>, useTouchTitleTooltip-Bauform)', () => {
    mitBreite(1150)
    const { container } = zeichne([...neunStrings(), NETZ, HAUS], 11.3)
    const c = chip(container)!
    expect(TIP_GESAMTLEISTUNG).toBe('Summe aller PV-Erzeuger (ohne Batterie/Netz)')
    expect(c.getAttribute('data-title')).toBe(TIP_GESAMTLEISTUNG)
    expect(c.querySelector(':scope > title')?.textContent).toBe(TIP_GESAMTLEISTUNG)
    // Chip nach den Kacheln (obenauf), Rahmen vor den Linien (dahinter)
    const svg = container.querySelector('svg.flex-1')! // die Zeichenfläche, nicht ein Symbol im Kopf
    const kinder = [...svg.children]
    expect(kinder.indexOf(c)).toBe(kinder.length - 1)
    const haus = kinder.findIndex(e => (e.getAttribute('data-title') ?? '').startsWith('Restverbrauch'))
    expect(haus).toBeGreaterThan(0)
    expect(kinder.indexOf(rahmen(container)!)).toBeLessThan(haus)
  })

  it('#137: genau EIN PV-Knoten ⇒ weder Rahmen noch Chip', () => {
    mitBreite(1150)
    const { container } = zeichne([pv(1, 'Dach Süd', 'Süd', 6.2), WP, NETZ, HAUS], 6.2)
    expect(rahmen(container)).toBeNull()
    expect(chip(container)).toBeNull()
    expect(alleTexte(container).some(t => /Gesamtleistung|Solarleistung/.test(t))).toBe(false)
  })

  it('#137 zählt Komponenten, nicht Kacheln: „PV gesamt" (eine Kachel am Handy) behält Rahmen und Chip — im Bild', () => {
    mitBreite(360)
    const komp = [...[1, 2, 3, 4].map(i => pv(i, `String ${i}`, null, 1)), WP, NETZ, HAUS]
    const { container } = zeichne(komp, 4)
    expect(rahmen(container)).not.toBeNull()
    const c = chip(container)!
    const rect = c.querySelector('rect')!
    // der Rahmen ist hier schmaler als der Chip ⇒ Chip mittig darüber, nie außerhalb der Zeichenfläche
    const r = rahmen(container)!
    const x = zahl(rect, 'x')
    const breite = zahl(rect, 'width')
    expect(breite).toBeGreaterThan(zahl(r, 'width') - 20)
    expect(x + breite / 2).toBeCloseTo(zahl(r, 'x') + zahl(r, 'width') / 2, 9)
    expect(x).toBeGreaterThanOrEqual(0)
    expect(x + breite).toBeLessThanOrEqual(360)
  })

  it('nachts (Summe 0): kein Chip und kein Rahmen — wie die frühere „Solarleistung"-Zeile', () => {
    mitBreite(1150)
    const { container } = zeichne([...neunStrings(), NETZ, HAUS].map(k => k.key.startsWith('pv_') ? { ...k, erzeugung_kw: 0 } : k), 0)
    expect(rahmen(container)).toBeNull()
    expect(chip(container)).toBeNull()
  })

  it('das Soll steht an der PV (5.11.2026): mit Gesamtleistung im Chip, bei einem PV-Knoten in der Kachel — nie über dem Haus', () => {
    // bis 4.2.1: «Solar Soll ~12,4 kW» als nackter Text bei y = CY − hausR − 8, mit und ohne Gesamtleistung
    mitBreite(1150)
    const mit = zeichne([...neunStrings(), NETZ, HAUS], 11.3, 12.4)
    const sollMit = [...mit.container.querySelectorAll('[data-solar-soll]')]
    expect(sollMit.map(e => e === chip(mit.container))).toEqual([true])
    expect(chip(mit.container)?.querySelector('text')?.textContent).toBe('Gesamtleistung 11,3 kW · Soll ~12,4 kW')
    expect(alleTexte(mit.container).some(t => t.startsWith('Solar Soll'))).toBe(false)
    mit.unmount()
    const ohne = zeichne([pv(1, 'Dach Süd', 'Süd', 6.2), NETZ, HAUS], 6.2, 12.4)
    const sollOhne = [...ohne.container.querySelectorAll('[data-solar-soll]')]
    expect(sollOhne.length).toBe(1)
    expect(sollOhne[0].tagName.toLowerCase()).toBe('text')
    expect(sollOhne[0].closest('g[data-title]')?.getAttribute('data-title')).toMatch(/^Dach Süd/)
    expect(sollOhne[0].textContent).toBe('Soll ~12,4 kW')
    expect(alleTexte(ohne.container).some(t => t.startsWith('Solar Soll'))).toBe(false)
  })
})

describe('EnergieFluss — kWp im Kachel-Tooltip deutsch formatiert (NB-2)', () => {
  it('„Auslastung: … % von 13,3 kWp" statt „13.3 kWp"', () => {
    mitBreite(1150)
    const { container } = zeichne([pv(1, 'Dach Süd', 'Süd', 6.2, 13.3), WP, NETZ, HAUS], 6.2)
    const tip = [...container.querySelectorAll('svg g[data-title]')]
      .map(g => g.getAttribute('data-title') ?? '')
      .find(t => t.startsWith('Dach Süd'))!
    expect(tip).toContain('Auslastung: 47 % von 13,3 kWp')
    expect(tip).not.toContain('13.3')
  })
})
