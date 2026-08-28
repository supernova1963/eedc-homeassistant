/**
 * DateiLightbox — Tastatur: was verbraucht wird, wird gemeldet (B16-ESC-Nachrang).
 *
 * Die Regel entstand am 28.08.2026 beim Bau von N-343: Zuhörer auf `document`
 * laufen in **Registrierungs**-Reihenfolge, ein später geöffnetes Overlay also
 * NACH einem früheren. Wer die Taste verbraucht, ruft `preventDefault()`; wer
 * darunter liegt (`blocks/FokusVollbild`), entscheidet einen Makrotask später und
 * lässt eine gemeldete Taste liegen. Ohne die Meldung nimmt ein ESC beides.
 *
 * Die Lightbox war der **vierte** ESC-Verbraucher und meldete als einzige nichts.
 * Erreichbar war das nicht — sie lebt allein in `pages/InfothekTeile.tsx`, dort
 * gibt es weder `BlockShell` noch `FokusKachel`, und mit dem Formular-Modal
 * derselben Seite kann sie nicht gleichzeitig offen sein (beide bildschirmfüllend).
 * Angeglichen wurde sie trotzdem: ein Trigger „beim nächsten Anfassen der
 * Infothek" feuert nie, wenn niemand die Infothek anfasst (Gernot, 28.08.).
 *
 * ⚠ Was diese Probe NICHT beweisen kann: die Reihenfolge zweier Zuhörer im
 * echten Browser. Chrome fährt nach JEDEM Zuhörer einen Microtask-Checkpoint,
 * jsdom nicht — genau daran ist am 28.08. eine grüne Vitest-Probe vorbeigelaufen,
 * während die Anwendung zwei Overlays gemeinsam schloss. Hier wird deshalb nur
 * geprüft, dass die Taste als verbraucht GEMELDET wird; dass ein Deferrer die
 * Meldung liest, hält `FokusVollbild.test.tsx` fest.
 */
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, cleanup } from '@testing-library/react'
import DateiLightbox from './DateiLightbox'
import type { InfothekDatei } from '../../types/infothek'

vi.mock('../../api/infothek', () => ({
  infothekApi: { dateiUrl: () => 'blob:bild' },
}))

const DATEIEN = [
  { id: 1, dateiname: 'a.png', mime_type: 'image/png' },
  { id: 2, dateiname: 'b.png', mime_type: 'image/png' },
  { id: 3, dateiname: 'c.png', mime_type: 'image/png' },
] as unknown as InfothekDatei[]

function zeige(index: number, onClose = () => {}, onNavigate = () => {}) {
  render(
    <DateiLightbox
      dateien={DATEIEN}
      eintragId={7}
      currentIndex={index}
      onClose={onClose}
      onNavigate={onNavigate}
    />
  )
}

/** Schickt die Taste an `document` und sagt, ob jemand sie als verbraucht meldet. */
function taste(key: string) {
  const ev = new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true })
  document.dispatchEvent(ev)
  return ev.defaultPrevented
}

afterEach(cleanup)

describe('DateiLightbox — verbrauchte Tasten werden gemeldet', () => {
  it('ESC schließt und meldet die Taste als verbraucht', () => {
    const onClose = vi.fn()
    zeige(1, onClose)

    expect(taste('Escape')).toBe(true)
    expect(onClose).toHaveBeenCalledOnce()
  })

  it('blättert mit den Pfeiltasten und meldet auch sie', () => {
    const onNavigate = vi.fn()
    zeige(1, () => {}, onNavigate)

    expect(taste('ArrowLeft')).toBe(true)
    expect(onNavigate).toHaveBeenLastCalledWith(0)

    expect(taste('ArrowRight')).toBe(true)
    expect(onNavigate).toHaveBeenLastCalledWith(2)
  })

  it('meldet NICHT, was sie gar nicht verbraucht — am Rand der Liste', () => {
    // ⭐ Der Kern der Regel: gemeldet wird, was WIRKT. Am ersten Bild bewirkt
    // ArrowLeft nichts; die Taste dann trotzdem zu sperren, nähme sie einem
    // anderen Overlay, ohne dafür etwas zu tun.
    const onNavigate = vi.fn()
    zeige(0, () => {}, onNavigate)

    expect(taste('ArrowLeft')).toBe(false)
    expect(onNavigate).not.toHaveBeenCalled()

    cleanup()
    zeige(DATEIEN.length - 1, () => {}, onNavigate)
    expect(taste('ArrowRight')).toBe(false)
    expect(onNavigate).not.toHaveBeenCalled()
  })

  it('fasst Tasten nicht an, die ihr nicht gehören', () => {
    const onClose = vi.fn()
    const onNavigate = vi.fn()
    zeige(1, onClose, onNavigate)

    expect(taste('ArrowUp')).toBe(false)
    expect(taste('Enter')).toBe(false)
    expect(onClose).not.toHaveBeenCalled()
    expect(onNavigate).not.toHaveBeenCalled()
  })

  it('hört nach dem Schließen nicht weiter mit', () => {
    // Ein Zuhörer, der den Abbau verpasst, verbraucht Tasten für eine Fläche,
    // die es nicht mehr gibt — und meldet sie als verbraucht.
    const onClose = vi.fn()
    zeige(1, onClose)
    cleanup()

    expect(taste('Escape')).toBe(false)
    expect(onClose).not.toHaveBeenCalled()
  })
})
