/**
 * N-390 — der Touch-Tooltip bleibt lesbar, statt beim Loslassen zu verschwinden.
 *
 * ⛔ **Was hier gemessen wird, und warum die HÖHE der Aussage zählt:** Bis zum
 * 2026-09-04 hing an `touchend` ein `hide`. Der Tooltip war damit formal
 * „vorhanden" — eine Probe, die nur seine Existenz nach `touchstart` prüft, wäre
 * über den alten UND den neuen Zustand grün gewesen. Der Defekt lag im
 * **Zeitfenster**: Der Text erschien und verschwand mit dem Finger, ein
 * mehrzeiliger Inhalt (der Haus-Knoten des Energieflusses trägt sieben Zeilen) war
 * so nicht zu lesen. Wer trotzdem las, ließ den Finger liegen — und löste damit die
 * Park-Geste aus. Deshalb prüft die Kernprobe ausdrücklich den Zustand **nach**
 * `touchend`.
 *
 * ⚑ Die andere Hälfte des Fundes sitzt in `components/park/parkbar-kopfzone.test.tsx`.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, fireEvent, act } from '@testing-library/react'
import { useTouchTitleTooltip } from './useTouchTitleTooltip'

function Harness() {
  useTouchTitleTooltip()
  return (
    <div>
      <div data-testid="mit-title" title={'Haushalt\nAktuell: 1,20 kW'}>Haus</div>
      <div data-testid="mit-data-title" data-title="Summe aller PV-Erzeuger">SVG-Ersatz</div>
      <div data-testid="ohne">Nichts dahinter</div>
    </div>
  )
}

/** Der Hook rendert in `document.body`, nicht in den React-Baum. */
const tooltipText = () =>
  Array.from(document.body.children)
    .filter((el) => el.tagName === 'DIV' && (el as HTMLElement).style.position === 'fixed')
    .map((el) => el.textContent)

const tap = (el: Element) =>
  fireEvent.touchStart(el, { touches: [{ clientX: 50, clientY: 200 }] })

describe('N-390 — Touch-Tooltip', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks() })

  it('erscheint bei touchstart auf einem title-Element', () => {
    const { getByTestId } = render(<Harness />)
    tap(getByTestId('mit-title'))
    expect(tooltipText().join()).toContain('Haushalt')
  })

  it('BLEIBT nach touchend stehen — das ist der Fund', () => {
    const { getByTestId } = render(<Harness />)
    const ziel = getByTestId('mit-title')
    tap(ziel)
    fireEvent.touchEnd(ziel)
    expect(tooltipText().join()).toContain('Haushalt')
  })

  it('greift auch auf data-title (der Weg des Energiefluss-SVG)', () => {
    const { getByTestId } = render(<Harness />)
    const ziel = getByTestId('mit-data-title')
    tap(ziel)
    fireEvent.touchEnd(ziel)
    expect(tooltipText().join()).toContain('Summe aller PV-Erzeuger')
  })

  it('schließt beim nächsten Tap auf etwas ohne Auskunft', () => {
    const { getByTestId } = render(<Harness />)
    tap(getByTestId('mit-title'))
    fireEvent.touchEnd(getByTestId('mit-title'))
    tap(getByTestId('ohne'))
    expect(tooltipText()).toHaveLength(0)
  })

  it('schließt beim Scrollen — ein Pan ist keine Leseabsicht', () => {
    const { getByTestId } = render(<Harness />)
    tap(getByTestId('mit-title'))
    fireEvent.touchMove(getByTestId('mit-title'))
    expect(tooltipText()).toHaveLength(0)
  })

  it('räumt sich nach dem Auto-Timeout selbst weg', () => {
    const { getByTestId } = render(<Harness />)
    tap(getByTestId('mit-title'))
    fireEvent.touchEnd(getByTestId('mit-title'))
    expect(tooltipText().join()).toContain('Haushalt')
    act(() => { vi.advanceTimersByTime(6100) })
    expect(tooltipText()).toHaveLength(0)
  })

  it('hinterlässt beim Unmount nichts im DOM', () => {
    const { getByTestId, unmount } = render(<Harness />)
    tap(getByTestId('mit-title'))
    unmount()
    expect(tooltipText()).toHaveLength(0)
  })
})
