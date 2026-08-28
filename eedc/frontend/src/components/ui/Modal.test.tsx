/**
 * Modal — der Dialog-SoT der App (Style-Guide B16). 28 Dialog-Instanzen in 14 Dateien
 * hängen an dieser Datei, direkt oder über die Hüllen `ConfirmDialog` und
 * `DestructiveActionDialog`; bis zu diesem Paket hatte sie keine eigene Probe.
 *
 * Geprüft wird die Semantik (Rolle + Name) und die Fokus-Führung beim Öffnen und
 * Schließen — nicht der Fokusfang: jsdom bewegt den Fokus bei Tab nicht, eine Probe
 * dafür wäre keine.
 */
import { useState } from 'react'
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import Modal from './Modal'

describe('Modal — Dialog-Semantik (B16)', () => {
  it('geschlossen: rendert nichts', () => {
    const { container } = render(
      <Modal isOpen={false} onClose={() => {}} title="Egal"><p>Inhalt</p></Modal>,
    )
    expect(container).toBeEmptyDOMElement()
  })

  it('offen: ist ein Dialog, ist modal und trägt seinen Titel als Namen', () => {
    render(<Modal isOpen onClose={() => {}} title="Monatsdaten löschen"><p>Inhalt</p></Modal>)
    const dialog = screen.getByRole('dialog', { name: 'Monatsdaten löschen' })
    expect(dialog).toHaveAttribute('aria-modal', 'true')
  })

  it('zwei gleichzeitig offene Dialoge tragen verschiedene Titel-ids', () => {
    render(
      <>
        <Modal isOpen onClose={() => {}} title="Assistent"><p>A</p></Modal>
        <Modal isOpen onClose={() => {}} title="Assistent schließen?"><p>B</p></Modal>
      </>,
    )
    const [a, b] = screen.getAllByRole('dialog')
    expect(a.getAttribute('aria-labelledby')).not.toBe(b.getAttribute('aria-labelledby'))
    expect(screen.getByRole('dialog', { name: 'Assistent schließen?' })).toBeInTheDocument()
  })

  it('setzt den Anfangsfokus auf den Dialog selbst, nicht auf sein erstes Bedienelement', () => {
    render(
      <Modal isOpen onClose={() => {}} title="Löschen">
        <button>Endgültig löschen</button>
      </Modal>,
    )
    expect(screen.getByRole('dialog')).toHaveFocus()
    expect(screen.getByRole('button', { name: 'Endgültig löschen' })).not.toHaveFocus()
  })

  it('gibt den Fokus beim Schließen an das auslösende Element zurück', () => {
    function Harness() {
      const [offen, setOffen] = useState(false)
      return (
        <>
          <button onClick={() => setOffen(true)}>Öffnen</button>
          <Modal isOpen={offen} onClose={() => setOffen(false)} title="Test"><p>Inhalt</p></Modal>
        </>
      )
    }
    render(<Harness />)
    const ausloeser = screen.getByRole('button', { name: 'Öffnen' })
    ausloeser.focus()
    fireEvent.click(ausloeser)

    expect(screen.getByRole('dialog')).toHaveFocus()

    fireEvent.click(screen.getByRole('button', { name: 'Schließen' }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(ausloeser).toHaveFocus()
  })

  it('ESC schließt und meldet die Taste als verbraucht', () => {
    const onClose = vi.fn()
    render(<Modal isOpen onClose={onClose} title="Test"><p>Inhalt</p></Modal>)

    const ereignis = new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true })
    document.dispatchEvent(ereignis)

    expect(onClose).toHaveBeenCalledTimes(1)
    // Damit ein darunterliegendes `FokusVollbild` die Taste liegen lässt.
    expect(ereignis.defaultPrevented).toBe(true)
  })

  it('Backdrop-Klick schließt, ein Klick im Dialog nicht', () => {
    const onClose = vi.fn()
    render(<Modal isOpen onClose={onClose} title="Test"><p>Inhalt</p></Modal>)

    fireEvent.click(screen.getByText('Inhalt'))
    expect(onClose).not.toHaveBeenCalled()

    fireEvent.click(document.querySelector('.bg-black\\/50') as Element)
    expect(onClose).toHaveBeenCalledTimes(1)
  })
})
