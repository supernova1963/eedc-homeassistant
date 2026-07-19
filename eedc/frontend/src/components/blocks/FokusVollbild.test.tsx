/**
 * FokusVollbild (Paket CT) — Chart-⇄-Tabelle-Umschalter NUR in der
 * Overlay-Kopfzeile: ohne `tabelle`-Slot kein Umschalter; mit Slot startet
 * jede Fokus-Öffnung beim Chart, „Tabelle" tauscht den Inhalt aus.
 */
import { describe, it, expect } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { FokusVollbild } from './FokusVollbild'

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
