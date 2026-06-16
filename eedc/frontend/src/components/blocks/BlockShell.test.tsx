import { describe, it, expect, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { BlockShell } from './BlockShell'
import type { Block } from './types'

// IA-V4 E3 Slice 1: das aus dem Skelett promovierte universelle Block-Modell.
// Geprüft werden die strukturkritischen Invarianten: Einklappen, Fokus/Vollbild,
// ↑↓-Reihenfolge und die localStorage-Persistenz pro Sicht.

function bloecke(): Block[] {
  return [
    { id: 'a', title: 'Block A', defaultOpen: true, render: () => <p>Inhalt A</p> },
    { id: 'b', title: 'Block B', defaultOpen: true, render: () => <p>Inhalt B</p> },
    { id: 'c', title: 'Block C', defaultOpen: true, render: () => <p>Inhalt C</p> },
  ]
}

const KEY = 'test-sicht'

describe('BlockShell', () => {
  beforeEach(() => localStorage.clear())

  it('rendert alle Blöcke und ihren Inhalt (offen)', () => {
    render(<BlockShell bloecke={bloecke()} persistKey={KEY} />)
    expect(screen.getByText('Block A')).toBeInTheDocument()
    expect(screen.getByText('Inhalt A')).toBeInTheDocument()
    expect(screen.getByText('Inhalt C')).toBeInTheDocument()
  })

  it('klappt einen Block ein (Inhalt verschwindet)', () => {
    render(<BlockShell bloecke={bloecke()} persistKey={KEY} />)
    expect(screen.getByText('Inhalt A')).toBeInTheDocument()
    fireEvent.click(screen.getAllByLabelText('einklappen')[0])
    // Erstes Toggle betrifft Block A (erster „einklappen"-Button).
    expect(screen.queryByText('Inhalt A')).not.toBeInTheDocument()
    // Andere Blöcke bleiben offen.
    expect(screen.getByText('Inhalt B')).toBeInTheDocument()
  })

  it('zeigt im Fokus nur den gewählten Block + Zurück', () => {
    render(<BlockShell bloecke={bloecke()} persistKey={KEY} />)
    const fokusButtons = screen.getAllByLabelText('Fokus / Vollbild')
    fireEvent.click(fokusButtons[1]) // Block B
    expect(screen.getByText('Inhalt B')).toBeInTheDocument()
    expect(screen.queryByText('Inhalt A')).not.toBeInTheDocument()
    expect(screen.getByText('Zurück')).toBeInTheDocument()
    fireEvent.click(screen.getByText('Zurück'))
    expect(screen.getByText('Inhalt A')).toBeInTheDocument()
  })

  it('verschiebt einen Block per ↑↓ (nur wenn sortierbar)', () => {
    render(<BlockShell bloecke={bloecke()} persistKey={KEY} sortierbar />)
    const titelVorher = screen.getAllByText(/^Block [ABC]$/).map((e) => e.textContent)
    expect(titelVorher).toEqual(['Block A', 'Block B', 'Block C'])
    // Block B nach oben.
    const hoch = screen.getAllByLabelText('nach oben')
    fireEvent.click(hoch[1])
    const titelNachher = screen.getAllByText(/^Block [ABC]$/).map((e) => e.textContent)
    expect(titelNachher).toEqual(['Block B', 'Block A', 'Block C'])
  })

  it('ohne sortierbar gibt es keine ↑↓-Buttons', () => {
    render(<BlockShell bloecke={bloecke()} persistKey={KEY} />)
    expect(screen.queryByLabelText('nach oben')).not.toBeInTheDocument()
  })

  it('persistiert Klappzustand + Reihenfolge pro Sicht in localStorage', () => {
    const { unmount } = render(<BlockShell bloecke={bloecke()} persistKey={KEY} sortierbar />)
    // Block A einklappen + Block C nach oben.
    fireEvent.click(screen.getAllByLabelText('einklappen')[0])
    fireEvent.click(screen.getAllByLabelText('nach oben')[2]) // C über B

    const gespeichert = JSON.parse(localStorage.getItem('eedc-bloecke:' + KEY)!)
    expect(gespeichert.zu).toContain('a')
    expect(gespeichert.order).toEqual(['a', 'c', 'b'])

    // Neu mounten: Zustand wird aus localStorage rekonstruiert.
    unmount()
    render(<BlockShell bloecke={bloecke()} persistKey={KEY} sortierbar />)
    expect(screen.queryByText('Inhalt A')).not.toBeInTheDocument() // A bleibt zu
    const titel = screen.getAllByText(/^Block [ABC]$/).map((e) => e.textContent)
    expect(titel).toEqual(['Block A', 'Block C', 'Block B'])
  })
})
