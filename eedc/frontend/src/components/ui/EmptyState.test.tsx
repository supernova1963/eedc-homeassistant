import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { Users } from 'lucide-react'
import EmptyState from './EmptyState'
import FehlerZustand from './FehlerZustand'

// N-318 (2026-08-23): `check:park-leertest` unterscheidet „hier ist nichts zu messen, und
// die Sicht sagt warum" von „hier wurde nichts gemessen" — und zwar am DOM-Merkmal
// `data-leer-erklaert`, nicht an einer gepflegten Sichtenliste. Damit ist das Attribut ein
// VERTRAG zwischen Produkt und Laufzeit-Gate: Fällt es weg, meldet das Gate eine legitim
// leere Sicht als Befund (oder — schlimmer — es fehlt bei einer neuen SoT-Erklärung und der
// Lauf wird grundlos rot). Ein Laufzeit-Gate kann das nicht schützen: Es bemerkt den Verlust
// nur, wenn zufällig gerade eine Sicht legitim leer ist. Deshalb hier.
describe('EmptyState (SoT „Leere Sichten erklären sich", v4.0.4)', () => {
  it('trägt das Merkmal `data-leer-erklaert` (Vertrag mit check:park-leertest)', () => {
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
