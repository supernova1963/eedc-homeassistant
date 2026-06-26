/**
 * AuswertungenV4 — Dispatcher-Smoke-Test der Wie-Achse.
 * Sichert: SubTabBar mit den 5 Sub-Tabs in kanonischer Reihenfolge
 * (Finanzen·ROI·Prognose·CO₂·Tabelle), Tabelle rendert die Werkbank, unbekannter
 * Sub → Redirect auf Finanzen (Default).
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Routes, Route, Navigate } from 'react-router-dom'

// Schwere Sub-Sicht-Kinder stubben — Dispatcher-Test isoliert auf Routing.
vi.mock('./AuswertungenTabelleV4', () => ({ default: () => <div>WERKBANK-STUB</div> }))
vi.mock('./AuswertungenCo2V4', () => ({ default: () => <div>CO2-STUB</div> }))
vi.mock('./AuswertungenFinanzenV4', () => ({ default: () => <div>FINANZEN-STUB</div> }))
vi.mock('./AuswertungenPrognoseV4', () => ({ default: () => <div>PROGNOSE-STUB</div> }))
vi.mock('./AuswertungenRoiV4', () => ({ default: () => <div>ROI-STUB</div> }))

import AuswertungenV4 from './AuswertungenV4'

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/v4/auswertungen" element={<Navigate to="/v4/auswertungen/finanzen" replace />} />
        <Route path="/v4/auswertungen/:sub" element={<AuswertungenV4 />} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('AuswertungenV4 (Wie-Achse Dispatcher)', () => {
  it('zeigt alle 5 Sub-Tabs', () => {
    renderAt('/v4/auswertungen/finanzen')
    for (const label of ['Finanzen', 'ROI', 'Prognose', 'CO₂', 'Tabelle']) {
      expect(screen.getAllByText(label).length).toBeGreaterThan(0)
    }
  })

  it('rendert die Werkbank im Tabelle-Sub', () => {
    renderAt('/v4/auswertungen/tabelle')
    expect(screen.getByText('WERKBANK-STUB')).toBeInTheDocument()
  })

  it('rendert Finanzen im Finanzen-Sub', () => {
    renderAt('/v4/auswertungen/finanzen')
    expect(screen.getByText('FINANZEN-STUB')).toBeInTheDocument()
  })

  it('rendert ROI im ROI-Sub', () => {
    renderAt('/v4/auswertungen/roi')
    expect(screen.getByText('ROI-STUB')).toBeInTheDocument()
  })

  it('unbekannter Sub → Redirect auf Finanzen', () => {
    renderAt('/v4/auswertungen/quatsch')
    expect(screen.getByText('FINANZEN-STUB')).toBeInTheDocument()
  })
})
