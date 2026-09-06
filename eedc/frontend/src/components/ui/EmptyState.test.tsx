import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { Users } from 'lucide-react'
import EmptyState from './EmptyState'
import FehlerZustand from './FehlerZustand'

// N-318 (2026-08-23): Das DOM-Merkmal `data-leer-erklaert` unterscheidet „hier ist nichts
// zu messen, und die Sicht sagt warum" von „hier wurde nichts gemessen" — an der Sicht
// selbst, nicht an einer gepflegten Sichtenliste.
//
// ⚠ **Sein damaliger Leser, `check:park-leertest`, ist am 2026-09-06 entfallen** (ersetzt
// durch die Quelltext-Wächter `check:park-gate` + `check:park-idliste`). Diese Probe misst
// seither nur noch die SEMANTIK der Komponente: eine erklärte Leere trägt das Merkmal, ein
// FEHLER nicht — ein Fehler erklärt keine legitime Leere. Das bleibt richtig und prüfbar
// ohne den Prüfer, der es einmal gelesen hat.
describe('EmptyState (SoT „Leere Sichten erklären sich", v4.0.4)', () => {
  it('trägt das Merkmal `data-leer-erklaert`', () => {
    const { container } = render(
      <EmptyState icon={Users} title="Teile erst deine Daten" description="Grund steht hier." />,
    )
    expect(container.querySelector('[data-leer-erklaert]')).not.toBeNull()
  })

  it('zeigt Titel und Grund — das Merkmal behauptet eine Erklärung, die auch dasteht', () => {
    render(<EmptyState icon={Users} title="Noch keine Anlage" description="Lege zuerst eine an." />)
    expect(screen.getByText('Noch keine Anlage')).toBeInTheDocument()
    expect(screen.getByText('Lege zuerst eine an.')).toBeInTheDocument()
  })

  it('FehlerZustand trägt es NICHT — ein Fehler erklärt keine legitime Leere', () => {
    // Die Abgrenzung ist der Kern von N-318: Läuft eine Sicht in einen Fehler, hat der Lauf
    // nichts gemessen und muss rot werden. Würde `FehlerZustand` das Merkmal tragen, wäre
    // genau dieser Fall stillgelegt.
    const { container } = render(<FehlerZustand text="Fehler beim Laden" />)
    expect(container.querySelector('[data-leer-erklaert]')).toBeNull()
  })
})
