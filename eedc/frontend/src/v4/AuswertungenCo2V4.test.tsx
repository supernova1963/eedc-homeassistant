/**
 * AuswertungenCo2V4 — Smoke-Test (A.5 Sub 2): die 3 Blöcke rendern, CO₂ trägt die
 * R2-Einheit (formatCo2: kg→t ab ≥1.000), Amortisations-Block ist data-gated.
 * Daten-Hooks/API gestubbt → isoliert auf die Sicht-Komposition.
 * R18-3 (Option B): `basis` kommt als Prop (Dispatcher hält den Jahr-Filter);
 * R18-3c: Amortisation rechnet IMMER auf der Gesamt-Historie und kennzeichnet
 * das bei gesetztem Einzeljahr-Filter sichtbar.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, cleanup } from '@testing-library/react'
import type { AuswertungBasis } from './useAuswertungBasis'

vi.mock('../hooks', async (importOriginal) => ({
  // R18-2: useApiData (SWR-Sicht-Cache) läuft ECHT — nur Anlage/Achse gemockt.
  ...(await importOriginal<typeof import('../hooks')>()),
  useSelectedAnlage: () => ({
    anlagen: [{ id: 1, anlagenname: 'Test' }], selectedAnlageId: 1,
    selectedAnlage: { id: 1, anlagenname: 'Test' }, loading: false,
  }),
  useSchmaleAchse: () => false,
}))

const monat2024 = {
  jahr: 2024, monat: 11, pv_erzeugung_kwh: 4000, eigenverbrauch_kwh: 2000,
  einspeisung_kwh: 2000, netzbezug_kwh: 1500, gesamtverbrauch_kwh: 3500,
  direktverbrauch_kwh: 1500, autarkie_prozent: 60, eigenverbrauchsquote_prozent: 50,
}
const monat2025 = {
  jahr: 2025, monat: 5, pv_erzeugung_kwh: 12000, eigenverbrauch_kwh: 6000,
  einspeisung_kwh: 6000, netzbezug_kwh: 3000, gesamtverbrauch_kwh: 9000,
  direktverbrauch_kwh: 4000, autarkie_prozent: 70, eigenverbrauchsquote_prozent: 50,
}
const basisMock = {
  daten: [monat2024, monat2025], loading: false, strompreis: null, alleTarife: [],
  jahr: 'alle' as number | 'alle', setJahr: vi.fn(), jahre: [2025, 2024], zeitraumLabel: '2024–2025',
  gefiltert: [monat2024, monat2025],
  stats: { gesamtErzeugung: 16000, anzahlMonate: 2 },
  statsGesamt: { gesamtErzeugung: 16000, anzahlMonate: 2 },
}
const basis = () => basisMock as unknown as AuswertungBasis

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
    render(<AuswertungenCo2V4 basis={basis()} />)
    // Block ① + ③ sofort; ② erscheint nach getCO2Amortisation (graue Last > 0).
    expect(await screen.findByText('CO₂-Bilanz & Wirkung')).toBeInTheDocument()
    expect(screen.getByText('Berechnungsgrundlage')).toBeInTheDocument()
    expect(await screen.findByText('CO₂-Amortisation')).toBeInTheDocument()
    // 16.000 kWh × 0,38 = 6.080 kg → R2 schaltet auf t (≥1.000) → Einheit „t" im Strip.
    expect(screen.getAllByText('t').length).toBeGreaterThan(0)
  })

  it('R18-3c: Amortisation bleibt bei Einzeljahr-Filter Gesamt-bezogen + sichtbar gekennzeichnet', async () => {
    Object.assign(basisMock, {
      jahr: 2025, gefiltert: [monat2025],
      stats: { gesamtErzeugung: 12000, anzahlMonate: 1 },
    })
    render(<AuswertungenCo2V4 basis={basis()} />)
    const amortTitel = await screen.findByText('CO₂-Amortisation')
    fireEvent.click(amortTitel) // Block ② aufklappen (defaultOpen: false)
    // Kennzeichen sichtbar: Jahr-Filter wirkt im Amortisations-Block nicht.
    expect(await screen.findByText(/Jahr-Filter wirkt hier nicht/)).toBeInTheDocument()
    // „Bereits ausgeglichen" rechnet mit der GESAMT-Historie (16.000 kWh × 0,38 =
    // 6.080 kg von 8.000 kg = 76 %), nicht mit dem gefilterten Jahr (4.560 → 57 %).
    expect(screen.getByText(/6,08.*von.*8,00/)).toBeInTheDocument()
    cleanup()
    Object.assign(basisMock, {
      jahr: 'alle', gefiltert: [monat2024, monat2025],
      stats: { gesamtErzeugung: 16000, anzahlMonate: 2 },
    })
  })

  it('zeigt bei Basis-Fetch-Fehler den B8-Fehler-Baustein mit Retry statt 0-KPIs (S15)', () => {
    const refresh = vi.fn()
    Object.assign(basisMock, { error: 'Fehler beim Laden der aggregierten Daten', refresh })
    render(<AuswertungenCo2V4 basis={basis()} />)
    expect(screen.getByText('Fehler beim Laden der aggregierten Daten')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Erneut versuchen/ }))
    expect(refresh).toHaveBeenCalledTimes(1)
    cleanup()
    Object.assign(basisMock, { error: null, refresh: undefined })
  })
})
