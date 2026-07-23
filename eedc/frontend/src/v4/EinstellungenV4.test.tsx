/**
 * EinstellungenV4 — Shell-Smoke-Test.
 * Sichert: Kategorie-Leiste mit allen 6 Kategorien, aktive Kategorie rendert ihre
 * Blöcke, unbekannte Kategorie → Redirect auf Stammdaten, globale Suche filtert,
 * datengetriebener „Komponenten"-Reiter rendert einen Block pro Investitionstyp.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter, Routes, Route, Navigate } from 'react-router-dom'
import type { Investition } from '../types'

// HA-Verfügbarkeit deterministisch (kein Netzwerk in jsdom); Standalone = false.
vi.mock('../hooks/useHAAvailable', () => ({ useHAAvailable: () => false }))

// Demo-Anlage + Investitionen für den datengetriebenen Komponenten-Zweig (kein
// Netzwerk in jsdom). useInvestitionenByTyp bleibt echt (reine Gruppierung).
const MOCK_INVESTITIONEN = [
  { id: 1, anlage_id: 1, typ: 'speicher', bezeichnung: 'Mein Speicher', parameter: {}, aktiv: true },
  { id: 2, anlage_id: 1, typ: 'e-auto', bezeichnung: 'Mein E-Auto', parameter: {}, aktiv: true },
] as unknown as Investition[]

vi.mock('../hooks', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../hooks')>()
  return {
    ...actual,
    useSelectedAnlage: () => ({
      anlagen: [{ id: 1, anlagenname: 'Demo' }],
      selectedAnlageId: 1,
      selectedAnlage: { id: 1, anlagenname: 'Demo' },
      setSelectedAnlageId: vi.fn(),
      loading: false,
      refresh: vi.fn(),
    }),
    useInvestitionen: () => ({
      investitionen: MOCK_INVESTITIONEN,
      loading: false,
      error: null,
      refresh: vi.fn(),
      createInvestition: vi.fn(),
      updateInvestition: vi.fn(),
      deleteInvestition: vi.fn(),
    }),
  }
})

vi.mock('../api/infothek', () => ({
  infothekApi: {
    getMigrationStatus: vi.fn().mockResolvedValue({ total: 0, investitionen: [] }),
    listFuerInvestition: vi.fn().mockResolvedValue([]),
    create: vi.fn(),
  },
}))

import EinstellungenV4 from './EinstellungenV4'

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/einstellungen" element={<Navigate to="/einstellungen/stammdaten" replace />} />
        <Route path="/einstellungen/:kategorie" element={<EinstellungenV4 />} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('EinstellungenV4 (Einstellungen-Shell)', () => {
  it('zeigt alle 6 Kategorien in der Leiste', () => {
    renderAt('/einstellungen/stammdaten')
    for (const label of ['Stammdaten', 'Komponenten', 'Infothek', 'Daten', 'Integration', 'System']) {
      expect(screen.getAllByText(label).length).toBeGreaterThan(0)
    }
  })

  it('rendert die Blöcke der aktiven Kategorie (Stammdaten → Anlage)', () => {
    renderAt('/einstellungen/stammdaten')
    expect(screen.getByText('Anlage')).toBeInTheDocument()
    expect(screen.getByText('Strompreise')).toBeInTheDocument()
  })

  it('unbekannte Kategorie → Redirect auf Stammdaten', () => {
    renderAt('/einstellungen/quatsch')
    expect(screen.getByText('Anlage')).toBeInTheDocument()
  })

  it('Komponenten-Reiter rendert einen Block pro Investitionstyp (datengetrieben)', () => {
    renderAt('/einstellungen/komponenten')
    // Block-Titel = Typ-Labels (alle 8 Typen, auch ohne Geräte); Inhalt ist per
    // defaultOpen:false eingeklappt → Geräte-Namen erst nach Aufklappen.
    expect(screen.getByText('Speicher')).toBeInTheDocument()
    expect(screen.getByText('E-Auto')).toBeInTheDocument()
    expect(screen.getByText('Wärmepumpe')).toBeInTheDocument()
    // „+"-Neuanlage pro Typ in der Block-Überschrift.
    expect(screen.getByLabelText('Speicher hinzufügen')).toBeInTheDocument()
    expect(screen.getByLabelText('Wallbox hinzufügen')).toBeInTheDocument()
  })

  it('globale Suche filtert über alle Kategorien', () => {
    renderAt('/einstellungen/stammdaten')
    const suchfeld = screen.getByLabelText('Einstellungen durchsuchen')
    fireEvent.change(suchfeld, { target: { value: 'community' } })
    expect(screen.getByText('Community-Share')).toBeInTheDocument()
    expect(screen.queryByText('Anlage')).not.toBeInTheDocument()
  })
})
