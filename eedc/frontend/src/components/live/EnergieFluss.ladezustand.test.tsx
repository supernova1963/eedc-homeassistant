/**
 * Energiefluss — Zustands-Chip an der Wallbox-Kachel (P-433-2b K1, K-12, S1-4 aus P-433-1).
 *
 * Gemessener Ladezustand ≠ «lädt» ⇒ die zweite Zeile ist ein Chip in der Funktionsfarbe («Wartet · PV» gelb, «Fehler»
 * rot, Ruhezustände gedämpft); «lädt» ⇒ weiter die Auto-Zeile. Ohne Ladezustand bleibt die Kachel, wie sie war — der
 * Kachel-Snapshot (`EnergieFluss.kachel-sot.test.tsx`) bleibt dafür unverändert. Der Tooltip nennt den Zustand.
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { render } from '@testing-library/react'
import EnergieFluss from './EnergieFluss'
import { ThemeProvider } from '../../context/ThemeContext'
import { stubMatchMedia } from '../../test/render'
import { KOMPONENTEN_FARBEN, STATUS_COLORS } from '../../lib'
import type { LiveKomponente } from '../../api/liveDashboard'

beforeEach(() => stubMatchMedia())

const wallbox = (over: Partial<LiveKomponente> = {}): LiveKomponente => ({
  key: 'wallbox_6', label: 'go-eCharger', icon: 'plug', erzeugung_kw: null, verbrauch_kw: 7.4, typ: 'wallbox',
  fahrzeuge: [{ investition_id: 4, label: 'ID.4', soc: 45, kw: 7.0, v2h: false }], fahrzeuge_zuordnung: 'eindeutig',
  ...over,
})

function zeichne(k: LiveKomponente) {
  return render(
    <ThemeProvider>
      <EnergieFluss komponenten={[k]} summeErzeugung={8} summeVerbrauch={8} summePv={8} gauges={[]} />
    </ThemeProvider>,
  ).container
}
const texte = (c: HTMLElement) => [...c.querySelectorAll('text')].map((t) => t.textContent?.trim())
const tip = (c: HTMLElement) => [...c.querySelectorAll('g[data-title]')].map((g) => g.getAttribute('data-title') ?? '').find((t) => t.startsWith('go-eCharger')) ?? ''

describe('Wallbox-Kachel — Zustands-Chip', () => {
  it('«Wartet · PV»: Chip im Gelb der Status-Achse statt der Auto-Zeile', () => {
    const c = zeichne(wallbox({ verbrauch_kw: 0, ladezustand: 'wartet', ladezustand_label: 'Wartet', lademodus: 'pv', lademodus_label: 'PV' }))
    const chip = c.querySelector('rect[data-modus-chip]')!
    expect(chip.getAttribute('fill')).toBe(STATUS_COLORS.warnung)
    expect(chip.getAttribute('data-modus-chip')).toBe('aktiv')
    expect(texte(c)).toContain('Wartet · PV')
    expect(texte(c).some((t) => t?.startsWith('ID.4'))).toBe(false)
    expect(tip(c)).toContain('Zustand: Wartet · PV')
  })

  it('«Kein Fahrzeug» gedämpft, «Fehler» rot', () => {
    const kf = zeichne(wallbox({ verbrauch_kw: 0, fahrzeuge: [], ladezustand: 'kein_fahrzeug', ladezustand_label: 'Kein Fahrzeug' }))
    expect(kf.querySelector('rect[data-modus-chip]')!.getAttribute('data-modus-chip')).toBe('gedaempft')
    const fe = zeichne(wallbox({ verbrauch_kw: 0, ladezustand: 'fehler', ladezustand_label: 'Fehler' }))
    expect(fe.querySelector('rect[data-modus-chip]')!.getAttribute('fill')).toBe(STATUS_COLORS.kritisch)
  })

  it('«lädt»: weiter die Auto-Zeile, kein Chip; der Tooltip nennt «Lädt · PV»', () => {
    const c = zeichne(wallbox({ ladezustand: 'laedt', ladezustand_label: 'Lädt', lademodus: 'pv', lademodus_label: 'PV' }))
    expect(c.querySelector('rect[data-modus-chip]')).toBeNull()
    expect(texte(c).some((t) => t?.startsWith('ID.4'))).toBe(true)
    expect(tip(c)).toContain('Zustand: Lädt · PV')
  })

  it('ohne Ladezustand: keine Änderung — Auto-Zeile, kein Chip, kein Zustand im Tooltip', () => {
    const c = zeichne(wallbox())
    expect(c.querySelector('rect[data-modus-chip]')).toBeNull()
    expect(tip(c)).not.toContain('Zustand:')
  })

  it('«lädt» trägt die Rolle der Wallbox (keine neue Farbe) — über die Funktionsfarbe', async () => {
    const { funktionsFarbe } = await import('../../lib/funktionsFarben')
    expect(funktionsFarbe('laedt')).toBe(KOMPONENTEN_FARBEN.wallbox.hex)
    expect(funktionsFarbe('verbunden')).toBe(funktionsFarbe('aus'))
  })
})
