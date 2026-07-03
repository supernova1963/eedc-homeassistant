import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import ScrollSchatten from './ScrollSchatten'

// jsdom hat keine Layout-Engine → Overflow-Geometrie pro Test explizit setzen.
function scroller(achse?: 'horizontal' | 'vertikal' | 'beide', geo?: Partial<Record<'scrollWidth' | 'clientWidth' | 'scrollHeight' | 'clientHeight', number>>) {
  const { container } = render(
    <ScrollSchatten achse={achse}>
      <div>Inhalt</div>
    </ScrollSchatten>,
  )
  const el = container.querySelector('.scrollbar-none') as HTMLElement
  const g = { scrollWidth: 600, clientWidth: 200, scrollHeight: 40, clientHeight: 40, ...geo }
  for (const [k, v] of Object.entries(g)) Object.defineProperty(el, k, { value: v, configurable: true })
  return el
}

function rad(el: HTMLElement, init: WheelEventInit) {
  const e = new WheelEvent('wheel', { bubbles: true, cancelable: true, ...init })
  el.dispatchEvent(e)
  return e
}

describe('ScrollSchatten Rad-Umleitung (A9)', () => {
  it('leitet vertikales Rad auf horizontalen Scroll um (nur-horizontal-Container)', () => {
    const el = scroller('horizontal')
    const e = rad(el, { deltaY: 50 })
    expect(e.defaultPrevented).toBe(true)
    expect(el.scrollLeft).toBe(50)
  })

  it('normiert Zeilen-Delta (deltaMode 1, Firefox) auf Pixel', () => {
    const el = scroller('horizontal')
    rad(el, { deltaY: 3, deltaMode: 1 })
    expect(el.scrollLeft).toBe(48)
  })

  it('reicht das Event am rechten Ende durch (Seiten-Scroll läuft weiter)', () => {
    const el = scroller('horizontal')
    el.scrollLeft = 400 // 400 + 200 = scrollWidth → am Ende
    const e = rad(el, { deltaY: 50 })
    expect(e.defaultPrevented).toBe(false)
    expect(el.scrollLeft).toBe(400)
  })

  it('lässt Modifier-Gesten nativ (Shift=horizontal, Strg=Zoom)', () => {
    const el = scroller('horizontal')
    expect(rad(el, { deltaY: 50, shiftKey: true }).defaultPrevented).toBe(false)
    expect(rad(el, { deltaY: 50, ctrlKey: true }).defaultPrevented).toBe(false)
    expect(el.scrollLeft).toBe(0)
  })

  it('lässt echte Horizontal-Gesten (Trackpad-deltaX) nativ', () => {
    const el = scroller('horizontal')
    expect(rad(el, { deltaX: 60, deltaY: 10 }).defaultPrevented).toBe(false)
  })

  it('greift NICHT bei vertikalem Überlauf oder anderer Achse', () => {
    const beide = scroller('beide')
    expect(rad(beide, { deltaY: 50 }).defaultPrevented).toBe(false)
    const misch = scroller('horizontal', { scrollHeight: 400, clientHeight: 100 })
    expect(rad(misch, { deltaY: 50 }).defaultPrevented).toBe(false)
  })
})
