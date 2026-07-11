/**
 * AuswertungenFinanzenV4 — Smoke-Test (A.5 Sub 3): die 3 Blöcke rendern, Geld in €
 * (R1 fmtZahl/formatGeld), T-Konto erbt das Kopf-Jahr (R5: KEIN eigener Jahr-<select>).
 * Daten-Hooks/API gestubbt → isoliert auf die Sicht-Komposition.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, cleanup } from '@testing-library/react'

vi.mock('../hooks', async (importOriginal) => ({
  // R18-2: useApiData (SWR-Sicht-Cache) läuft ECHT — nur Anlage/Achse gemockt.
  ...(await importOriginal<typeof import('../hooks')>()),
  useSelectedAnlage: () => ({
    anlagen: [{ id: 1, anlagenname: 'Test' }], selectedAnlageId: 1,
    selectedAnlage: { id: 1, anlagenname: 'Test' }, loading: false,
  }),
  useSchmaleAchse: () => false,
}))

const basisMock = {
  loading: false, jahr: 2025 as number | 'alle', setJahr: vi.fn(), jahre: [2025],
  zeitraumLabel: '2025',
  strompreis: { netzbezug_arbeitspreis_cent_kwh: 30, einspeiseverguetung_cent_kwh: 8, grundpreis_euro_monat: 10 },
  alleTarife: [], daten: [{ jahr: 2025, monat: 5 }],
  gefiltert: [{
    jahr: 2025, monat: 5, pv_erzeugung_kwh: 12000, eigenverbrauch_kwh: 6000,
    einspeisung_kwh: 6000, netzbezug_kwh: 3000, gesamtverbrauch_kwh: 9000,
    direktverbrauch_kwh: 4000, autarkie_prozent: 70, eigenverbrauchsquote_prozent: 50,
  }],
  stats: { anzahlMonate: 1, gesamtEinspeisung: 6000, gesamtEigenverbrauch: 6000, gesamtNetzbezug: 3000 },
}
vi.mock('./useAuswertungBasis', () => ({ useAuswertungBasis: () => basisMock }))

vi.mock('../api/cockpit', () => ({ cockpitApi: { getKomponentenZeitreihe: vi.fn().mockResolvedValue({ monatswerte: [] }) } }))
vi.mock('../api/aktuellerMonat', () => ({ aktuellerMonatApi: { getData: vi.fn().mockResolvedValue(null) } }))
vi.mock('../api/import', () => ({ importApi: { getPdfZipExportUrl: () => '/api/export.zip' } }))

import AuswertungenFinanzenV4 from './AuswertungenFinanzenV4'

describe('AuswertungenFinanzenV4 (Sub 3)', () => {
  it('rendert die 3 Blöcke; Einspeiseerlös in € (R1); T-Konto ohne eigenen Jahr-Select (R5)', async () => {
    render(<AuswertungenFinanzenV4 />)
    expect(await screen.findByText('Finanz-Übersicht')).toBeInTheDocument()
    expect(screen.getByText('SOLL/HABEN-T-Konto')).toBeInTheDocument()
    expect(screen.getByText('Berichte & Dokumente')).toBeInTheDocument()
    // 6.000 kWh × 8 ct = 480 € Einspeiseerlös → € sichtbar.
    expect(screen.getAllByText('€').length).toBeGreaterThan(0)
    // R5: genau EIN Jahr-Select (im Kopf), KEIN zweiter im T-Konto-Block.
    expect(screen.getAllByLabelText('Jahr filtern').length).toBe(1)
    expect(screen.queryByLabelText('Jahr wählen')).not.toBeInTheDocument()
  })

  it('zeigt bei Basis-Fetch-Fehler den B8-Fehler-Baustein mit Retry statt 0-KPIs (S15)', () => {
    const refresh = vi.fn()
    Object.assign(basisMock, { error: 'Fehler beim Laden der aggregierten Daten', refresh })
    render(<AuswertungenFinanzenV4 />)
    expect(screen.getByText('Fehler beim Laden der aggregierten Daten')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Erneut versuchen/ }))
    expect(refresh).toHaveBeenCalledTimes(1)
    cleanup()
    Object.assign(basisMock, { error: null, refresh: undefined })
  })
})
