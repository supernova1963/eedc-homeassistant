/**
 * FokusVollbild (Paket CT) — Chart-⇄-Tabelle-Umschalter NUR in der
 * Overlay-Kopfzeile: ohne `tabelle`-Slot kein Umschalter; mit Slot startet
 * jede Fokus-Öffnung beim Chart, „Tabelle" tauscht den Inhalt aus.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { FokusVollbild } from './FokusVollbild'
import { DatumPicker } from '../ui/DatumPicker'

// Die Entscheidung des Vollbilds fällt in einem Makrotask (s. Komponente) — erst danach messen.
const tick = () => new Promise((r) => setTimeout(r, 0))

describe('FokusVollbild — Chart ⇄ Tabelle (Paket CT)', () => {
  it('ohne tabelle-Slot: kein Umschalter in der Kopfzeile', () => {
    render(
      <FokusVollbild titel="Verlauf" onClose={() => {}}>
        <p>Chart-Inhalt</p>
      </FokusVollbild>,
    )
    expect(screen.getByText('Chart-Inhalt')).toBeInTheDocument()
    expect(screen.queryByRole('group', { name: 'Darstellung' })).not.toBeInTheDocument()
  })

  it('mit tabelle-Slot: startet beim Chart, Umschalter tauscht auf die Tabelle und zurück', () => {
    render(
      <FokusVollbild titel="Verlauf" onClose={() => {}} tabelle={<p>Tabellen-Inhalt</p>}>
        <p>Chart-Inhalt</p>
      </FokusVollbild>,
    )
    expect(screen.getByText('Chart-Inhalt')).toBeInTheDocument()
    expect(screen.queryByText('Tabellen-Inhalt')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Tabelle' }))
    expect(screen.getByText('Tabellen-Inhalt')).toBeInTheDocument()
    expect(screen.queryByText('Chart-Inhalt')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Chart' }))
    expect(screen.getByText('Chart-Inhalt')).toBeInTheDocument()
    expect(screen.queryByText('Tabellen-Inhalt')).not.toBeInTheDocument()
  })
})

describe('FokusVollbild — ESC schließt (Style-Guide B16)', () => {
  // ⚠ Grenze dieser Proben: jsdom bildet die Reihenfolge der document-Zuhörer nach,
  // aber NICHT Chromes Microtask-Checkpoint zwischen zwei Zuhörern. Dass der Nachrang
  // in der Anwendung wirkt, ist am 2026-08-28 an der Dev-Box gemessen worden, nicht
  // hier. Was diese Proben halten, ist der Riegel selbst (`defaultPrevented`).

  // Ein Backdrop-Klick ist hier nicht prüfbar und auch nicht gebaut: das Overlay ist
  // deckend, es gibt kein Daneben. ESC ist der einzige Ausweg neben „Zurück".
  const escSenden = () => {
    const ereignis = new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true })
    document.dispatchEvent(ereignis)
    return ereignis
  }

  it('ESC ruft onClose', async () => {
    const onClose = vi.fn()
    render(<FokusVollbild titel="Verlauf" onClose={onClose}><p>Inhalt</p></FokusVollbild>)

    escSenden()
    await tick()
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('ESC, das ein Overlay DARIN verbraucht hat, lässt das Vollbild offen', async () => {
    // Der reale Fall: der `DatumPicker` im kopf-Slot von Cockpit/Tag und /Monat. Sein
    // Zuhörer wird SPÄTER registriert und läuft daher nach unserem; er meldet die Taste
    // per preventDefault als verbraucht. Ohne das nähme ESC beides auf einmal.
    const onClose = vi.fn()
    render(<FokusVollbild titel="Verlauf" onClose={onClose}><p>Inhalt</p></FokusVollbild>)

    const inneres = (e: KeyboardEvent) => { if (e.key === 'Escape') e.preventDefault() }
    document.addEventListener('keydown', inneres)
    try {
      escSenden()
      await tick()
      expect(onClose).not.toHaveBeenCalled()
    } finally {
      document.removeEventListener('keydown', inneres)
    }
  })

  it('nach dem Abbau hört niemand mehr mit', async () => {
    const onClose = vi.fn()
    const { unmount } = render(<FokusVollbild titel="Verlauf" onClose={onClose}><p>Inhalt</p></FokusVollbild>)
    unmount()

    escSenden()
    await tick()
    expect(onClose).not.toHaveBeenCalled()
  })
})

describe('FokusVollbild — ESC mit echtem DatumPicker im kopf-Slot', () => {
  it('schließt den Picker, nicht das Vollbild (der Fall aus Cockpit/Tag und /Monat)', async () => {
    const onClose = vi.fn()
    render(
      <FokusVollbild
        titel="Verlauf"
        onClose={onClose}
        kopf={<DatumPicker modus="monat" value="2026-06" onChange={() => {}} ariaLabel="Monat" />}
      >
        <p>Inhalt</p>
      </FokusVollbild>,
    )
    // Picker öffnen — sein Zuhörer wird JETZT registriert, also nach dem des Vollbilds.
    fireEvent.click(screen.getByRole('button', { name: 'Monat' }))
    expect(screen.getByRole('button', { name: 'Aug' })).toBeInTheDocument()

    fireEvent.keyDown(document, { key: 'Escape' })
    await tick()

    expect(screen.queryByRole('button', { name: 'Aug' })).not.toBeInTheDocument()
    expect(onClose).not.toHaveBeenCalled()
    expect(screen.getByText('Inhalt')).toBeInTheDocument()
  })
})
