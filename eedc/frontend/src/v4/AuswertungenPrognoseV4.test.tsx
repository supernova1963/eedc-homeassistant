/**
 * AuswertungenPrognoseV4 — Smoke-Test (A.5 Sub 4, Element-Rebuild): die 5 Blöcke
 * rendern (Mehrjahres data-gated auf „Alle Jahre"), R5 = EINE Jahr-Steuerung im
 * Kopf. Die geteilten Prognose-Teile (Hooks/Elemente) sind gestubbt → isoliert auf
 * die Sicht-Komposition + Park-Hülle.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'

vi.mock('../hooks', () => ({
  useSchmaleAchse: () => false,
  useSelectedAnlage: () => ({
    anlagen: [{ id: 1, anlagenname: 'Test' }], selectedAnlageId: 1,
    selectedAnlage: { id: 1, anlagenname: 'Test' }, loading: false,
  }),
}))

const basisMock = {
  loading: false, jahr: 'alle' as number | 'alle', setJahr: vi.fn(), jahre: [2025, 2024],
  zeitraumLabel: '2024–2025', daten: [], gefiltert: [],
  stats: { anzahlMonate: 0 }, strompreis: null, alleTarife: [],
}
vi.mock('./useAuswertungBasis', () => ({ useAuswertungBasis: () => basisMock }))

// Geteilte Prognose-Teile neutralisiert (Hooks → loading, Elemente → null/[]),
// damit keine echten API-Calls laufen und die Komposition isoliert prüfbar ist.
vi.mock('../components/prognose/PrognoseVsIstTeile', () => ({
  usePrognoseVsIst: () => ({ loading: true }),
  pvgisKpiItems: () => [],
  PvgisSpeichern: () => null, PvgisMonatsChart: () => null, PvgisDetailTabelle: () => null, PvgisErklaerung: () => null,
}))
vi.mock('../components/prognose/PvStringsTeile', () => ({
  usePvStrings: () => ({ loading: true, data: null, jahresvergleichData: [] }),
  pvStringsKpiItems: () => [], exportPvStringsCsv: vi.fn(),
  PvStringHeaderZeile: () => null, PvStringBestSchlecht: () => null, PvStringSollIstBar: () => null,
  PvStringMonatsverlauf: () => null, PvStringTabelle: () => null, PvStringMehrjahr: () => null,
}))
vi.mock('../components/prognose/PrognoseVergleichTeile', () => ({
  usePrognoseVergleich: () => ({ loading: true }),
  hatLernfaktorO12: () => false, hatStratifizierung: () => false, hatTracking: () => false,
  PvgKpiMatrix: () => null, PvgStatusHinweise: () => null, PvgLernfaktorO12: () => null,
  PvgStratifizierung: () => null, PvgHeatmap: () => null, PvgStundenprofil: () => null,
  Pvg24hTabelle: () => null, Pvg7TageTabelle: () => null, PvgGenauigkeitsTracking: () => null,
}))

import AuswertungenPrognoseV4 from './AuswertungenPrognoseV4'

describe('AuswertungenPrognoseV4 (Sub 4)', () => {
  it('rendert 5 Blöcke (Mehrjahres data-gated bei „Alle Jahre"); R5 ein Jahr-Select', () => {
    render(<AuswertungenPrognoseV4 />)
    for (const titel of [
      'Jahres-SOLL/IST gegen PVGIS',
      'SOLL/IST pro PV-String',
      'Mehrjahres-Performance',
      'Quellen-Genauigkeit (OM · eedc · Solcast)',
      'Tages-/Stundenprofil',
    ]) {
      expect(screen.getByText(titel)).toBeInTheDocument()
    }
    expect(screen.getAllByLabelText('Jahr filtern').length).toBe(1)
  })
})
