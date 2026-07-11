/**
 * AuswertungenV4 — Dispatcher-Smoke-Test der Wie-Achse.
 * Sichert: SubTabBar mit den 5 Sub-Tabs in kanonischer Reihenfolge
 * (Finanzen·ROI·Prognose·CO₂·Tabelle), Tabelle rendert die Werkbank, unbekannter
 * Sub → Redirect auf Finanzen (Default).
 * R18-3 (Option B): der Jahr-Filter sitzt als EINE Steuerleiste im Dispatcher —
 * sichtbar für Finanzen/Prognose/CO₂, ausgeblendet für ROI/Tabelle, und die
 * Auswahl überlebt den Sub-Tab-Wechsel (Basis lebt im Dispatcher).
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter, Routes, Route, Navigate } from 'react-router-dom'

// Schwere Sub-Sicht-Kinder stubben — Dispatcher-Test isoliert auf Routing/Leiste.
vi.mock('./AuswertungenTabelleV4', () => ({ default: () => <div>WERKBANK-STUB</div> }))
vi.mock('./AuswertungenCo2V4', () => ({ default: () => <div>CO2-STUB</div> }))
vi.mock('./AuswertungenFinanzenV4', () => ({ default: () => <div>FINANZEN-STUB</div> }))
vi.mock('./AuswertungenPrognoseV4', () => ({ default: () => <div>PROGNOSE-STUB</div> }))
vi.mock('./AuswertungenRoiV4', () => ({ default: () => <div>ROI-STUB</div> }))

// Basis-Datenpfad gestubbt (useAuswertungBasis läuft ECHT — Jahr-State im Dispatcher).
vi.mock('../hooks', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../hooks')>()),
  useSelectedAnlage: () => ({
    anlagen: [{ id: 1, anlagenname: 'Test' }], selectedAnlageId: 1,
    selectedAnlage: { id: 1, anlagenname: 'Test' }, loading: false,
  }),
  useAggregierteDaten: () => ({
    daten: [{ jahr: 2025, monat: 1 }, { jahr: 2024, monat: 12 }],
    loading: false, error: null, refresh: vi.fn(),
  }),
  useAktuellerStrompreis: () => ({ strompreis: null }),
  useStrompreise: () => ({ strompreise: [] }),
}))

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

  it('R18-3: Jahr-Filter-Leiste in Finanzen/Prognose/CO₂, NICHT in ROI/Tabelle', () => {
    renderAt('/v4/auswertungen/finanzen')
    expect(screen.getByLabelText('Jahr filtern')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('link', { name: 'ROI' }))
    expect(screen.queryByLabelText('Jahr filtern')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('link', { name: 'Prognose' }))
    expect(screen.getByLabelText('Jahr filtern')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('link', { name: 'Tabelle' }))
    expect(screen.queryByLabelText('Jahr filtern')).not.toBeInTheDocument()
  })

  it('R18-3: die Jahr-Auswahl überlebt den Sub-Tab-Wechsel (Basis im Dispatcher)', () => {
    renderAt('/v4/auswertungen/finanzen')
    const select = screen.getByLabelText('Jahr filtern') as HTMLSelectElement
    fireEvent.change(select, { target: { value: '2024' } })
    expect(select.value).toBe('2024')
    fireEvent.click(screen.getByRole('link', { name: 'CO₂' }))
    expect((screen.getByLabelText('Jahr filtern') as HTMLSelectElement).value).toBe('2024')
  })
})
