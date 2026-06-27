/**
 * AuswertungenTabelleV4 — Smoke-Test (A.5 Sub 1, Werte-Werkbank): zwei Blöcke
 * (Monatswerte + Energieprofile) mit block-interner Zeitraum-/Vergleich-Leiste.
 * Daten-Hooks gestubbt → isoliert auf die Komposition.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'

vi.mock('../hooks', () => ({
  useSelectedAnlage: () => ({
    anlagen: [{ id: 1, anlagenname: 'Test' }], selectedAnlageId: 1,
    selectedAnlage: { id: 1, anlagenname: 'Test' }, loading: false,
  }),
}))

vi.mock('./useWerteZeitreihe', () => ({
  useWerteZeitreihe: () => ({
    rows: [
      { jahr: 2026, monat: 6, erzeugung: 1960, eigenverbrauch: 634, einspeisung: 1318, netzbezug: 9, gesamtverbrauch: 644, autarkie: 98.5, evQuote: 31.9 },
      { jahr: 2025, monat: 6, erzeugung: 1800, eigenverbrauch: 600, einspeisung: 1200, netzbezug: 20, gesamtverbrauch: 620, autarkie: 96, evQuote: 33 },
    ],
    jahre: [2026, 2025], loading: false, error: null,
  }),
}))
vi.mock('./useTagesWerte', () => ({
  useTagesWerte: () => ({ rows: [], vorjahrRows: null, loading: false, error: null }),
  minusEinJahr: (s: string) => s,
}))

import AuswertungenTabelleV4 from './AuswertungenTabelleV4'

describe('AuswertungenTabelleV4 (Werte-Werkbank)', () => {
  it('rendert beide Blöcke mit block-interner Zeitraum/Vergleich-Leiste', () => {
    render(<AuswertungenTabelleV4 />)
    expect(screen.getByText('Monatswerte')).toBeInTheDocument()
    expect(screen.getByText('Tageswerte')).toBeInTheDocument()
    // Monats-Block ist default offen → seine Zeitraum-Leiste rendert.
    expect(screen.getAllByText('Zeitraum').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Vergleich').length).toBeGreaterThan(0)
  })
})
