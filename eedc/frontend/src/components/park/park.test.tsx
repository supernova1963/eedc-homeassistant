import { describe, it, expect, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { ParkProvider, Parkbar, ParkFuss, usePark } from './index'

// IA-V4 SLICE 1 — Element-Park / „Anzeige-Papierkorb".
// Geprüft: No-Op ohne Provider (Release-Sicherheit), Park-Geste (Rechtsklick),
// Ausblenden geparkter Elemente, „Geparkt (n)"-Block + Chip-Restore, localStorage-
// Persistenz pro Sicht, schema-robustes Laden.

const KEY = 'test-park'
const LS = 'eedc-park:' + KEY

function Harness() {
  return (
    <ParkProvider persistKey={KEY}>
      <Parkbar id="kpi:a" titel="Kennzahl A"><div>Inhalt A</div></Parkbar>
      <Parkbar id="kpi:b" titel="Kennzahl B"><div>Inhalt B</div></Parkbar>
      <ParkFuss />
    </ParkProvider>
  )
}

describe('Element-Park (SLICE 1)', () => {
  beforeEach(() => localStorage.clear())

  it('ist ohne ParkProvider inert: Kinder unverändert, kein Fuß', () => {
    function Solo() {
      const park = usePark()
      return (
        <>
          <Parkbar id="x" titel="X"><div>Solo-Inhalt</div></Parkbar>
          <ParkFuss />
          <span>aktiv:{String(park.aktiv)}</span>
        </>
      )
    }
    render(<Solo />)
    expect(screen.getByText('Solo-Inhalt')).toBeInTheDocument()
    expect(screen.getByText('aktiv:false')).toBeInTheDocument()
    // Keine Papierkorb-Fußzeile/Hinweiszeile.
    expect(screen.queryByText(/Papierkorb/)).not.toBeInTheDocument()
  })

  it('parkt ein Element per Rechtsklick → Element weg, „Parkplatz (1)" + Chip', () => {
    render(<Harness />)
    expect(screen.getByText('Inhalt A')).toBeInTheDocument()
    // Rechtsklick auf Element A → Overlay „Parken".
    fireEvent.contextMenu(screen.getByText('Inhalt A'))
    fireEvent.click(screen.getByText('Parken'))

    expect(screen.queryByText('Inhalt A')).not.toBeInTheDocument()
    expect(screen.getByText('Inhalt B')).toBeInTheDocument()
    expect(screen.getByText('Parkplatz (1)')).toBeInTheDocument()
  })

  it('holt ein geparktes Element per Chip-Tap zurück', () => {
    render(<Harness />)
    fireEvent.contextMenu(screen.getByText('Inhalt A'))
    fireEvent.click(screen.getByText('Parken'))
    // „Geparkt"-Block aufklappen → Chip antippen.
    fireEvent.click(screen.getByText('Parkplatz (1)'))
    fireEvent.click(screen.getByText('Kennzahl A'))
    expect(screen.getByText('Inhalt A')).toBeInTheDocument()
    expect(screen.queryByText(/Parkplatz \(/)).not.toBeInTheDocument()
  })

  it('„alles zurückholen" leert den Papierkorb', () => {
    render(<Harness />)
    fireEvent.contextMenu(screen.getByText('Inhalt A'))
    fireEvent.click(screen.getByText('Parken'))
    fireEvent.contextMenu(screen.getByText('Inhalt B'))
    fireEvent.click(screen.getByText('Parken'))
    expect(screen.getByText('Parkplatz (2)')).toBeInTheDocument()
    fireEvent.click(screen.getByText('alles zurückholen'))
    expect(screen.getByText('Inhalt A')).toBeInTheDocument()
    expect(screen.getByText('Inhalt B')).toBeInTheDocument()
    expect(screen.queryByText(/Parkplatz \(/)).not.toBeInTheDocument()
  })

  it('persistiert geparkte Elemente (id + titel) pro Sicht in localStorage', () => {
    const { unmount } = render(<Harness />)
    fireEvent.contextMenu(screen.getByText('Inhalt A'))
    fireEvent.click(screen.getByText('Parken'))

    const gespeichert = JSON.parse(localStorage.getItem(LS)!)
    expect(gespeichert).toEqual([{ id: 'kpi:a', titel: 'Kennzahl A' }])

    // Neu mounten → Zustand rekonstruiert (Element bleibt geparkt).
    unmount()
    render(<Harness />)
    expect(screen.queryByText('Inhalt A')).not.toBeInTheDocument()
    expect(screen.getByText('Parkplatz (1)')).toBeInTheDocument()
  })

  it('lädt schema-robust: kaputter/fremder LS-Inhalt → leer, kein Crash', () => {
    localStorage.setItem(LS, '{"order":["a"]}') // alte BlockState-Form, kein Array
    render(<Harness />)
    expect(screen.getByText('Inhalt A')).toBeInTheDocument()
    expect(screen.getByText('Inhalt B')).toBeInTheDocument()
    expect(screen.queryByText(/Parkplatz \(/)).not.toBeInTheDocument()
  })

  it('verwirft unbekannte/teilweise Einträge beim Laden (Element bleibt sichtbar)', () => {
    localStorage.setItem(LS, JSON.stringify([{ id: 'kpi:a' }, { foo: 1 }])) // titel fehlt / Müll
    render(<Harness />)
    // kpi:a ohne titel = ungültig → nicht geparkt → A sichtbar.
    expect(screen.getByText('Inhalt A')).toBeInTheDocument()
    expect(screen.queryByText(/Parkplatz \(/)).not.toBeInTheDocument()
  })
})
