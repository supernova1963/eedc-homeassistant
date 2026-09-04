/**
 * N-390 — die Touch-Park-Geste greift nur in der Kopf-Zone.
 *
 * ⭐ **Der Anlass, und warum ihn kein Gate gefunden hat:** Die Park-Geste und der
 * app-globale Touch-Ersatz für `title=` (`hooks/useTouchTitleTooltip`) hängen am
 * **selben** `touchstart` derselben Fläche. Wer im Energiefluss den Haus-Knoten
 * antippte, um seine sieben Zeilen zu lesen, musste den Finger liegen lassen — und
 * bekam nach 500 ms das Park-Overlay über die ganze Fläche gelegt. Gemeldet von
 * Gernot am 2026-09-04.
 *
 * ⛔ **Die SPEC hatte das vorhergesehen und die falsche Hälfte gebaut**
 * (`SPEC-ELEMENT-LAYOUT-PAPIERKORB.md:65-66`): Sie nennt „Geste an die
 * Titel-/Kopf-Zone binden" UND „Timer + Bewegungs-Schwelle". Gebaut war nur die
 * zweite — und die ist gegen *Chart*-Tooltips gerichtet („Tooltip-Touch ist ein
 * Move/Pan"). Für den title-Tooltip gilt das nicht: dort ist er ein Halten ohne
 * Bewegung, also exakt die Park-Geste.
 *
 * ⚑ **Vor dieser Datei prüfte KEINE Probe die Touch-Geste** — `park.test.tsx` deckt
 * ausschließlich den Rechtsklick ab. Das ist der Grund, warum die Kollision so lange
 * unentdeckt blieb, und die Lehre gehört hierher: eine Geste, die nur auf einem
 * Eingabegerät existiert, wird von einer Suite ohne dieses Gerät nie gemessen.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen, fireEvent, act } from '@testing-library/react'
import { ParkProvider, Parkbar } from './index'

const KEY = 'test-park-kopfzone'

/** Der Parkbar-Wrapper beginnt bei y=100 und ist 300 px hoch. In jsdom liefert
 *  `getBoundingClientRect` sonst lauter Nullen — dann läge JEDER Touch in der
 *  Kopf-Zone und die Probe wäre über beide Zustände grün. */
const WRAPPER_TOP = 100

function rectMock() {
  return vi.spyOn(Element.prototype, 'getBoundingClientRect').mockReturnValue({
    top: WRAPPER_TOP, left: 0, bottom: WRAPPER_TOP + 300, right: 400,
    width: 400, height: 300, x: 0, y: WRAPPER_TOP, toJSON: () => ({}),
  } as DOMRect)
}

function Harness() {
  return (
    <ParkProvider persistKey={KEY}>
      <Parkbar id="kpi:a" titel="Kennzahl A">
        <div>
          <h3>Kennzahl A</h3>
          <button type="button">Vergrößern</button>
          <p>Körper mit Zahlen</p>
        </div>
      </Parkbar>
    </ParkProvider>
  )
}

/** Long-Press an einer absoluten y-Position auslösen und die 500 ms verstreichen lassen. */
function longPress(ziel: Element, clientY: number) {
  fireEvent.touchStart(ziel, { touches: [{ clientX: 50, clientY }] })
  act(() => { vi.advanceTimersByTime(600) })
}

describe('N-390 — Touch-Park-Geste nur in der Kopf-Zone', () => {
  beforeEach(() => { localStorage.clear(); vi.useFakeTimers() })
  afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks() })

  it('Long-Press IN der Kopf-Zone öffnet das Park-Overlay', () => {
    rectMock()
    render(<Harness />)
    longPress(screen.getByText('Kennzahl A'), WRAPPER_TOP + 20)   // 20 px < 44
    expect(screen.getByRole('button', { name: 'Parken' })).toBeInTheDocument()
  })

  it('Long-Press im KÖRPER öffnet es NICHT — das ist der Fund', () => {
    rectMock()
    render(<Harness />)
    longPress(screen.getByText('Körper mit Zahlen'), WRAPPER_TOP + 200) // 200 px > 44
    expect(screen.queryByRole('button', { name: 'Parken' })).not.toBeInTheDocument()
  })

  it('genau an der Grenze: 43 px öffnet, 45 px nicht', () => {
    rectMock()
    const { unmount } = render(<Harness />)
    longPress(screen.getByText('Kennzahl A'), WRAPPER_TOP + 43)
    expect(screen.getByRole('button', { name: 'Parken' })).toBeInTheDocument()
    unmount()

    render(<Harness />)
    longPress(screen.getByText('Kennzahl A'), WRAPPER_TOP + 45)
    expect(screen.queryByRole('button', { name: 'Parken' })).not.toBeInTheDocument()
  })

  it('ein Bedienelement in der Kopf-Zone parkt nicht — es wird bedient', () => {
    rectMock()
    render(<Harness />)
    longPress(screen.getByRole('button', { name: 'Vergrößern' }), WRAPPER_TOP + 10)
    expect(screen.queryByRole('button', { name: 'Parken' })).not.toBeInTheDocument()
  })

  /**
   * ⚑ Die Gegenrichtung, und sie ist keine Formsache: Die Einschränkung gilt
   * NUR für Touch (Entscheid Gernot, 04.09.). Ein Rechtsklick kollidiert mit
   * keinem Hover-Tooltip; ihn mit einzuschränken wäre reiner Komfortverlust.
   * Wer diese Probe rot macht, hat die Regel auf den Desktop ausgeweitet.
   */
  it('Rechtsklick öffnet weiterhin ÜBERALL — auch mitten im Körper', () => {
    rectMock()
    render(<Harness />)
    fireEvent.contextMenu(screen.getByText('Körper mit Zahlen'))
    expect(screen.getByRole('button', { name: 'Parken' })).toBeInTheDocument()
  })
})
