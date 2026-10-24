/**
 * P-433-1 «Kompakt» (Konzept #433 Stufe 1, E5) — Netzrichtung als Text und Pfeilspitze in Lite.
 *
 * - **S1-3:** die Netz-Kachel trägt ihre Richtung als zweite Zeile: «Bezug» / «Einspeisung» /
 *   «Balance» (innerhalb `netz_puffer_w`). Text und Farbe folgen EINER Regel (`netzRichtung`) —
 *   dieselbe, die schon die Netz-Farbe bestimmt.
 * - **S1-5:** im Lite-Modus hat jede aktive Linie eine Pfeilspitze am Hausende in der Linienfarbe
 *   (Quellen ins Haus, Senken hinaus); der Effekt-Modus bleibt bei den Partikeln.
 *
 * Schwester: `EnergieFluss.haus.test.tsx` («Rest»/«gesamt» im Haus-Kreis),
 * `EnergieFluss.betriebsmodus.test.tsx` (Modus-Chip).
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { render } from '@testing-library/react'
import EnergieFluss, { NETZ_RICHTUNG_TEXT, getNodeColor, netzRichtung } from './EnergieFluss'
import { pfeilspitze } from './energieFlussLayout'
import { ThemeProvider } from '../../context/ThemeContext'
import { stubMatchMedia } from '../../test/render'
import { COLORS, STATUS_COLORS } from '../../lib'
import type { LiveKomponente } from '../../api/liveDashboard'

beforeEach(() => {
  stubMatchMedia()
  localStorage.clear()
})

const knoten = (key: string, extra: Partial<LiveKomponente>): LiveKomponente =>
  ({ key, label: key, icon: 'wrench', erzeugung_kw: null, verbrauch_kw: null, ...extra })
const PV = knoten('pv_1', { label: 'Dach', icon: 'sun', erzeugung_kw: 3.0, typ: 'pv-module' })
const WP = knoten('waermepumpe_7', { label: 'WP', icon: 'flame', typ: 'waermepumpe', verbrauch_kw: 1.2 })
const SAUNA_AUS = knoten('sonstige_9', { label: 'Sauna', typ: 'sonstiges', kategorie: 'verbraucher', verbrauch_kw: 0 })

function zeichne(komp: LiveKomponente[], { lite = false, puffer = 100 }: { lite?: boolean; puffer?: number } = {}) {
  localStorage.setItem('eedc-energiefluss-lite', lite ? '1' : '0')
  return render(
    <ThemeProvider>
      <EnergieFluss komponenten={komp} summeErzeugung={3} summeVerbrauch={3} summePv={3} gauges={[]} netzPufferW={puffer} />
    </ThemeProvider>,
  )
}

const netzKachel = (c: HTMLElement) =>
  [...c.querySelectorAll('g[data-title]')].find(g => g.getAttribute('data-title')!.startsWith('Stromnetz'))!

describe('Netz-Kachel — Richtung als Text (S1-3)', () => {
  it.each([
    ['Bezug', { erzeugung_kw: 2.0 }, COLORS.grid],
    ['Einspeisung', { verbrauch_kw: 1.5 }, COLORS.solar],
    ['Balance', { erzeugung_kw: 0.05 }, STATUS_COLORS.ok],
  ] as const)('%s', (text, fluss, farbe) => {
    const netz = knoten('netz', { label: 'Stromnetz', icon: 'zap', ...fluss })
    const { container } = zeichne([PV, WP, netz])
    const zeile = [...netzKachel(container).querySelectorAll('text')].find(t => t.textContent === text)
    expect(zeile, `keine Zeile «${text}»`).toBeTruthy()
    // Farbe = Netz-Farbe (dynamisch nach Richtung), keine neue Farbe.
    expect(zeile!.getAttribute('fill')).toBe(farbe)
    expect(getNodeColor(netz)).toBe(farbe)
  })

  it('die Schwelle ist `netz_puffer_w` — dieselbe Regel für Text und Farbe', () => {
    const netz = knoten('netz', { erzeugung_kw: 0.3 })
    expect(netzRichtung(netz, 100)).toBe('bezug')
    expect(netzRichtung(netz, 500)).toBe('balance')
    expect(getNodeColor(netz, 500)).toBe(STATUS_COLORS.ok)
    expect(NETZ_RICHTUNG_TEXT[netzRichtung(netz, 500)]).toBe('Balance')
  })

  it('ohne Fluss grau «Balance» — wie jede inaktive zweite Zeile', () => {
    const netz = knoten('netz', { label: 'Stromnetz', icon: 'zap' })
    const { container } = zeichne([PV, WP, netz])
    const zeile = [...netzKachel(container).querySelectorAll('text')].find(t => t.textContent === 'Balance')!
    expect(zeile.getAttribute('fill')).not.toBe(STATUS_COLORS.ok)
  })
})

describe('Pfeilspitze am Hausende (S1-5)', () => {
  const netz = knoten('netz', { label: 'Stromnetz', icon: 'zap', erzeugung_kw: 0.5 })

  it('Lite: je aktive Linie genau eine Pfeilspitze in der Linienfarbe; inaktive ohne', () => {
    const { container } = zeichne([PV, WP, SAUNA_AUS, netz], { lite: true })
    const pfeile = [...container.querySelectorAll('polygon[data-pfeil]')]
    expect(pfeile).toHaveLength(3)
    const richtung = pfeile.map(p => p.getAttribute('data-pfeil')).sort()
    expect(richtung).toEqual(['vom-haus', 'zum-haus', 'zum-haus'])
    expect(pfeile.map(p => p.getAttribute('fill'))).toContain(getNodeColor(WP))
  })

  it('Effekt: keine Pfeilspitze (die Partikel zeigen die Richtung)', () => {
    const { container } = zeichne([PV, WP, netz], { lite: false })
    expect(container.querySelectorAll('polygon[data-pfeil]')).toHaveLength(0)
    expect(container.querySelectorAll('animateMotion').length).toBeGreaterThan(0)
  })

  it('die Spitze liegt außerhalb des Kreises und zeigt bei Quellen ins Haus, bei Senken hinaus', () => {
    const [cx, cy, r] = [300, 180, 38]
    const pkt = (s: string) => s.split(' ').map(p => p.split(',').map(Number))
    const abstand = ([x, y]: number[]) => Math.hypot(x - cx, y - cy)
    const quelle = pkt(pfeilspitze(300, 50, cx, cy, r + 2, 7, 4, true))
    const senke = pkt(pfeilspitze(300, 50, cx, cy, r + 2, 7, 4, false))
    for (const ecken of [quelle, senke]) for (const e of ecken) expect(abstand(e)).toBeGreaterThan(r)
    // Spitze = erste Ecke: bei der Quelle näher am Haus als die Basis, bei der Senke weiter weg.
    expect(abstand(quelle[0])).toBeLessThan(abstand(quelle[1]))
    expect(abstand(senke[0])).toBeGreaterThan(abstand(senke[1]))
  })
})
