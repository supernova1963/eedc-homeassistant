/**
 * Tabellen: Wärmepumpen-Tagesspalten mit Lade-Anzeige (Auftrag 29.10.2026, Entscheid Gernot 28.10.).
 *
 * Gesichert wird:
 *   1. Die Wärmepumpen-Tagesreihe (`mitWaerme`) wird NUR angefragt, wenn eine ihrer Spalten eingeblendet ist — schon
 *      die erste Abfrage richtet sich nach der gespeicherten Spaltenwahl (kein «erst halb, dann ganz»), und das
 *      Einblenden im Spalten-Wähler schaltet sie ein.
 *   2. Solange diese Abfrage läuft, steht die Lade-Anzeige mit Grund — keine Tabelle, kein CSV-Export.
 *   3. Ohne Wärmepumpen-Spalte verhält sich der Block wie bisher (Tabelle + Export).
 *   4. `useTagesWerte` reicht den Parameter an beide Abfragen (Zeitraum und Vergleich) durch.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, renderHook, waitFor } from '@testing-library/react'

const tagesState: { current: { rows: unknown[]; loading: boolean } } = { current: { rows: [], loading: false } }
const useTagesWerteSpy = vi.fn()

vi.mock('../hooks', () => ({
  useSchmaleAchse: () => false,
  useInvestitionen: () => ({ investitionen: [], loading: false, error: null }),
  useSelectedAnlage: () => ({
    anlagen: [{ id: 1, anlagenname: 'Test' }], selectedAnlageId: 1,
    selectedAnlage: { id: 1, anlagenname: 'Test' }, loading: false,
  }),
  useApiData: () => ({ data: [{ jahr: 2026, monat: 9, tage: 30 }], loading: false, error: null }),
}))
vi.mock('./useWerteZeitreihe', () => ({
  useWerteZeitreihe: () => ({
    rows: [{ jahr: 2026, monat: 9, erzeugung: 1960, eigenverbrauch: 634, einspeisung: 1318, netzbezug: 9, gesamtverbrauch: 644, autarkie: 98.5, evQuote: 31.9 }],
    jahre: [2026], loading: false, error: null,
  }),
}))
vi.mock('./useTagesWerte', () => ({
  useTagesWerte: (...args: unknown[]) => {
    useTagesWerteSpy(...args)
    return { rows: tagesState.current.rows, vorjahrRows: null, loading: tagesState.current.loading, error: null }
  },
  minusEinJahr: (s: string) => s,
}))

import AuswertungenTabelleV4, { WAERME_LADE_TEXT } from './AuswertungenTabelleV4'
import type { AuswertungBasis } from './useAuswertungBasis'

const basisMock = {
  daten: [], gefiltert: [], strompreis: null, alleTarife: [], jahr: 'alle',
  setJahr: () => {}, jahre: [2026], zeitraumLabel: '2026',
  loading: false, error: null, refresh: async () => {},
} as unknown as AuswertungBasis

const TAG = { datum: '2026-09-01', erzeugung: 20, eigenverbrauch: 8, einspeisung: 12, netzbezug: 3, wp_kaelte: 4 }
/** Das sechste Argument von `useTagesWerte` — `mitWaerme`. */
const mitWaermeAufrufe = () => useTagesWerteSpy.mock.calls.map((c) => c[5])

function oeffneBeideBloecke() {
  localStorage.setItem('eedc-bloecke:v4-auswertungen-tabelle', JSON.stringify({ zu: [] }))
}
function speichereTagSpalten(keys: string[]) {
  localStorage.setItem('eedc-auswertungen-werkbank:cols:tag', JSON.stringify(keys))
}

describe('Tabellen — Wärmepumpen-Tagesspalten (29.10.2026)', () => {
  beforeEach(() => {
    localStorage.clear()
    useTagesWerteSpy.mockClear()
    tagesState.current = { rows: [TAG], loading: false }
    oeffneBeideBloecke()
  })

  it('ohne eingeblendete WP-Spalte fragt keine Abfrage die Wärmepumpen-Reihe an', () => {
    speichereTagSpalten(['erzeugung', 'netzbezug'])
    render(<AuswertungenTabelleV4 basis={basisMock} />)
    expect(useTagesWerteSpy).toHaveBeenCalled()
    expect(mitWaermeAufrufe().every((v) => v === false)).toBe(true)
  })

  it('mit gespeicherter WP-Spalte fragt schon die ERSTE Abfrage mit (kein «erst halb, dann ganz»)', () => {
    speichereTagSpalten(['erzeugung', 'wp_kaelte'])
    render(<AuswertungenTabelleV4 basis={basisMock} />)
    expect(mitWaermeAufrufe().length).toBeGreaterThan(0)
    expect(mitWaermeAufrufe().every((v) => v === true)).toBe(true)
  })

  it('Einblenden einer WP-Spalte im Spalten-Wähler schaltet die Abfrage ein, Ausblenden wieder aus', () => {
    speichereTagSpalten(['erzeugung'])
    render(<AuswertungenTabelleV4 basis={basisMock} />)
    expect(mitWaermeAufrufe().at(-1)).toBe(false)
    // Die Tageswerte-Tabelle ist die zweite WerteTabelle der Sicht (die erste ist der Monatsblock).
    fireEvent.click(screen.getAllByRole('button', { name: /Spalten \(/ }).at(-1)!)
    fireEvent.click(screen.getByLabelText('Strom Kühlen'))
    expect(mitWaermeAufrufe().at(-1)).toBe(true)
    fireEvent.click(screen.getByLabelText('Strom Kühlen'))
    expect(mitWaermeAufrufe().at(-1)).toBe(false)
  })

  it('auch «WP Zusatzheizung» ist je Tag wählbar und schaltet die Abfrage ein (29.10.2026, Halt H1 Option b)', () => {
    speichereTagSpalten(['erzeugung'])
    render(<AuswertungenTabelleV4 basis={basisMock} />)
    fireEvent.click(screen.getAllByRole('button', { name: /Spalten \(/ }).at(-1)!)
    fireEvent.click(screen.getByLabelText('WP Zusatzheizung'))
    expect(mitWaermeAufrufe().at(-1)).toBe(true)
  })

  it('während die Abfrage mit WP-Spalte läuft: Lade-Anzeige mit Grund, keine Tabelle, kein CSV-Export', () => {
    speichereTagSpalten(['erzeugung', 'wp_waerme'])
    tagesState.current = { rows: [TAG], loading: true }   // auch ein noch stehender Stand wird NICHT gezeigt
    render(<AuswertungenTabelleV4 basis={basisMock} />)
    expect(screen.getByText(WAERME_LADE_TEXT)).toBeInTheDocument()
    expect(WAERME_LADE_TEXT).toMatch(/Stundendatensätze/)
    // Nur der Monatsblock trägt Spaltenwahl und Export — der Tagesblock nicht.
    expect(screen.getAllByRole('button', { name: /Spalten \(/ })).toHaveLength(1)
    expect(screen.getAllByRole('button', { name: /CSV/ })).toHaveLength(1)
  })

  it('fertig geladen: Tabelle und Export stehen, die Lade-Anzeige ist weg', () => {
    speichereTagSpalten(['erzeugung', 'wp_waerme'])
    render(<AuswertungenTabelleV4 basis={basisMock} />)
    expect(screen.queryByText(WAERME_LADE_TEXT)).not.toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: /Spalten \(/ })).toHaveLength(2)
    expect(screen.getAllByRole('button', { name: /CSV/ })).toHaveLength(2)
  })

  it('ohne WP-Spalte wie bisher: ein laufender Zeitraumwechsel lässt die stehende Tabelle stehen', () => {
    speichereTagSpalten(['erzeugung'])
    tagesState.current = { rows: [TAG], loading: true }
    render(<AuswertungenTabelleV4 basis={basisMock} />)
    expect(screen.queryByText(WAERME_LADE_TEXT)).not.toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: /CSV/ })).toHaveLength(2)
  })
})

describe('useTagesWerte — `mitWaerme` an beiden Abfragen', () => {
  it('reicht den Parameter an Zeitraum und Vergleich durch; ohne ihn bleibt der Aufruf wie bisher', async () => {
    vi.resetModules()
    vi.doUnmock('./useTagesWerte')
    vi.doUnmock('../hooks')
    const getTageWerte = vi.fn((..._a: unknown[]) => Promise.resolve([]))
    vi.doMock('../api/energie_profil', () => ({ energieProfilApi: { getTageWerte } }))
    const { useTagesWerte } = await import('./useTagesWerte')

    renderHook(() => useTagesWerte(7, '2026-09-01', '2026-09-30', '2025-09-01', '2025-09-30', true))
    await waitFor(() => expect(getTageWerte).toHaveBeenCalledTimes(2))
    expect(getTageWerte).toHaveBeenCalledWith(7, '2026-09-01', '2026-09-30', true)
    expect(getTageWerte).toHaveBeenCalledWith(7, '2025-09-01', '2025-09-30', true)

    getTageWerte.mockClear()
    renderHook(() => useTagesWerte(7, '2026-08-01', '2026-08-31', null, null))
    await waitFor(() => expect(getTageWerte).toHaveBeenCalledTimes(1))
    expect(getTageWerte).toHaveBeenCalledWith(7, '2026-08-01', '2026-08-31', false)
  })
})
