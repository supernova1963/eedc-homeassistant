/**
 * AuswertungenCo2V4 — Smoke-Test (A.5 Sub 2): die 3 Blöcke rendern, CO₂ trägt die
 * R2-Einheit (formatCo2: kg→t ab ≥1.000), Amortisations-Block ist data-gated.
 * Daten-Hooks/API gestubbt → isoliert auf die Sicht-Komposition.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'

vi.mock('../hooks', () => ({
  useSelectedAnlage: () => ({
    anlagen: [{ id: 1, anlagenname: 'Test' }], selectedAnlageId: 1,
    selectedAnlage: { id: 1, anlagenname: 'Test' }, loading: false,
  }),
  useSchmaleAchse: () => false,
}))

vi.mock('./useAuswertungBasis', () => ({
  useAuswertungBasis: () => ({
    daten: [], loading: false, strompreis: null, alleTarife: [],
    jahr: 'alle' as const, setJahr: vi.fn(), jahre: [2025], zeitraumLabel: '2025',
    gefiltert: [{
      jahr: 2025, monat: 5, pv_erzeugung_kwh: 12000, eigenverbrauch_kwh: 6000,
      einspeisung_kwh: 6000, netzbezug_kwh: 3000, gesamtverbrauch_kwh: 9000,
      direktverbrauch_kwh: 4000, autarkie_prozent: 70, eigenverbrauchsquote_prozent: 50,
    }],
    stats: { gesamtErzeugung: 12000, anzahlMonate: 12 },
  }),
}))

vi.mock('../api/investitionen', () => ({
  investitionenApi: {
    getCO2Amortisation: vi.fn().mockResolvedValue({
      graue_last_gesamt_kg: 8000,
      posten: [{ investition_id: 1, bezeichnung: 'PV-Anlage', typ: 'pv', quelle: 'default', graue_last_kg: 8000 }],
    }),
  },
}))

import AuswertungenCo2V4 from './AuswertungenCo2V4'

describe('AuswertungenCo2V4 (Sub 2)', () => {
  it('rendert die 3 Blöcke; CO₂ in t (R2 ≥1.000 kg→t); Amortisation data-gated', async () => {
    render(<AuswertungenCo2V4 />)
    // Block ① + ③ sofort; ② erscheint nach getCO2Amortisation (graue Last > 0).
    expect(await screen.findByText('CO₂-Bilanz & Wirkung')).toBeInTheDocument()
    expect(screen.getByText('Berechnungsgrundlage')).toBeInTheDocument()
    expect(await screen.findByText('CO₂-Amortisation')).toBeInTheDocument()
    // 12.000 kWh × 0,38 = 4.560 kg → R2 schaltet auf t (≥1.000) → Einheit „t" im Strip.
    expect(screen.getAllByText('t').length).toBeGreaterThan(0)
  })
})
