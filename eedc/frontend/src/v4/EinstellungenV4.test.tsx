/**
 * EinstellungenV4 — Shell-Smoke-Test.
 * Sichert: Kategorie-Leiste mit allen 6 Kategorien, aktive Kategorie rendert ihre
 * Blöcke, unbekannte Kategorie → Redirect auf Stammdaten, globale Suche filtert.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter, Routes, Route, Navigate } from 'react-router-dom'

// HA-Verfügbarkeit deterministisch (kein Netzwerk in jsdom); Standalone = false.
vi.mock('../hooks/useHAAvailable', () => ({ useHAAvailable: () => false }))

import EinstellungenV4 from './EinstellungenV4'

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/v4/einstellungen" element={<Navigate to="/v4/einstellungen/stammdaten" replace />} />
        <Route path="/v4/einstellungen/:kategorie" element={<EinstellungenV4 />} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('EinstellungenV4 (Einstellungen-Shell)', () => {
  it('zeigt alle 6 Kategorien in der Leiste', () => {
    renderAt('/v4/einstellungen/stammdaten')
    for (const label of ['Stammdaten', 'Infothek', 'Daten', 'Integration', 'System', 'Daten teilen']) {
      expect(screen.getAllByText(label).length).toBeGreaterThan(0)
    }
  })

  it('rendert die Blöcke der aktiven Kategorie (Stammdaten → Anlage)', () => {
    renderAt('/v4/einstellungen/stammdaten')
    expect(screen.getByText('Anlage')).toBeInTheDocument()
    expect(screen.getByText('Strompreise')).toBeInTheDocument()
  })

  it('unbekannte Kategorie → Redirect auf Stammdaten', () => {
    renderAt('/v4/einstellungen/quatsch')
    expect(screen.getByText('Anlage')).toBeInTheDocument()
  })

  it('globale Suche filtert über alle Kategorien', () => {
    renderAt('/v4/einstellungen/stammdaten')
    const suchfeld = screen.getByLabelText('Einstellungen durchsuchen')
    fireEvent.change(suchfeld, { target: { value: 'community' } })
    expect(screen.getByText('Community-Share')).toBeInTheDocument()
    expect(screen.queryByText('Anlage')).not.toBeInTheDocument()
  })
})
