/**
 * AuswertungenPrognoseV4 — Smoke-Test (A.5 Sub 4, Element-Rebuild): die 5 Blöcke
 * rendern (Mehrjahres data-gated auf „Alle Jahre"). Die geteilten Prognose-Teile
 * (Hooks/Elemente) sind gestubbt → isoliert auf die Sicht-Komposition + Park-Hülle.
 * R18-3 (Option B): `basis` kommt als Prop (Jahr-Filter in der Dispatcher-
 * Steuerleiste, KEIN Select in der Sicht); R18-3a: Block ① kennzeichnet bei
 * „Alle Jahre" sichtbar, dass er das neueste Jahr zeigt.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, cleanup } from '@testing-library/react'
import type { AuswertungBasis } from './useAuswertungBasis'

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
  stats: { anzahlMonate: 0 }, statsGesamt: { anzahlMonate: 0 }, strompreis: null, alleTarife: [],
}
const basis = () => basisMock as unknown as AuswertungBasis

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
  it('rendert 5 Blöcke (Mehrjahres data-gated bei „Alle Jahre"); KEIN Jahr-Select in der Sicht (R18-3)', () => {
    render(<AuswertungenPrognoseV4 basis={basis()} />)
    for (const titel of [
      'Jahres-SOLL/IST gegen PVGIS',
      'SOLL/IST pro PV-String',
      'Mehrjahres-Performance',
      'Quellen-Genauigkeit (OM · eedc · Solcast)',
      'Tages-/Stundenprofil',
    ]) {
      expect(screen.getByText(titel)).toBeInTheDocument()
    }
    // R18-3: der EINE Jahr-Select sitzt im Dispatcher — hier keiner.
    expect(screen.queryByLabelText('Jahr filtern')).not.toBeInTheDocument()
  })

  it('R18-3a: Block ① kennzeichnet bei „Alle Jahre" sichtbar das gezeigte Einzeljahr', () => {
    render(<AuswertungenPrognoseV4 basis={basis()} />)
    // Block ① ist defaultOpen → Hinweis sichtbar (neuestes Jahr = 2025).
    expect(screen.getByText(/Einzeljahr-Vergleich und zeigt das Jahr 2025/)).toBeInTheDocument()
  })

  it('zeigt bei Basis-Fetch-Fehler den B8-Fehler-Baustein mit Retry statt stiller Leere (S15)', () => {
    const refresh = vi.fn()
    Object.assign(basisMock, { error: 'Fehler beim Laden der aggregierten Daten', refresh })
    render(<AuswertungenPrognoseV4 basis={basis()} />)
    expect(screen.getByText('Fehler beim Laden der aggregierten Daten')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Erneut versuchen/ }))
    expect(refresh).toHaveBeenCalledTimes(1)
    cleanup()
    Object.assign(basisMock, { error: null, refresh: undefined })
  })
})
