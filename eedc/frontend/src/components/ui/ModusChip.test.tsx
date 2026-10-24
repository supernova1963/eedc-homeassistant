/**
 * ModusChip (SoT, P-433-2 Nacharbeit): Label aus dem Kanon, Farbpunkt in der
 * Funktionsfarbe (`funktionsFarbe`), Zusatz «(passiv)» nur über die Prop.
 */
import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import ModusChip, { modusMitPassiv } from './ModusChip'
import { CHART_COLORS } from '../../lib'

const farbeVon = (c: HTMLElement) => (c.querySelector('[data-modus-farbe]') as HTMLElement).style.backgroundColor
/** jsdom normalisiert `style` auf rgb(…) — der Vergleichswert läuft durch dieselbe Normalisierung. */
const normiert = (hex: string) => { const d = document.createElement('span'); d.style.backgroundColor = hex; return d.style.backgroundColor }

describe('ModusChip', () => {
  it('zeigt das Kanon-Label und den Punkt in der Funktionsfarbe', () => {
    const heizen = render(<ModusChip modus="heizen" label="Heizen" />)
    expect(heizen.container.textContent).toBe('Heizen')
    expect(farbeVon(heizen.container)).toBe(normiert(CHART_COLORS.wpWaerme))
    const ww = render(<ModusChip modus="warmwasser" label="Warmwasser" />)
    expect(farbeVon(ww.container)).toBe(normiert(CHART_COLORS.wpWarmwasser))
    const kuehlen = render(<ModusChip modus="kuehlen" label="Kühlen" />)
    expect(farbeVon(kuehlen.container)).toBe(normiert(CHART_COLORS.modusKuehlen))
  })

  it('unbekannter Modus (aus, unbestimmt) ⇒ Grau der nicht aufgeteilten Rolle', () => {
    const aus = render(<ModusChip modus="aus" label="Aus" />)
    expect(farbeVon(aus.container)).toBe(normiert(CHART_COLORS.modusNichtAufgeteilt))
  })

  it('«(passiv)» nur mit der Prop — eine Regel für Chip und Kachel', () => {
    expect(render(<ModusChip modus="kuehlen" label="Kühlen" passiv />).container.textContent).toBe('Kühlen (passiv)')
    expect(render(<ModusChip modus="kuehlen" label="Kühlen" />).container.textContent).toBe('Kühlen')
    expect(modusMitPassiv('Kühlen', true)).toBe('Kühlen (passiv)')
    expect(modusMitPassiv('Heizen', false)).toBe('Heizen')
  })

  it('Form nach B17: rounded-full, text-xs, kein ALL-CAPS', () => {
    const chip = render(<ModusChip modus="heizen" label="Heizen" />).container.querySelector('[data-modus-chip]')!
    const klassen = chip.getAttribute('class')!
    expect(klassen).toContain('rounded-full')
    expect(klassen).toContain('text-xs')
    expect(klassen).not.toContain('uppercase')
  })
})
