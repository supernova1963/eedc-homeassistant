/**
 * AuswertungenFinanzenV4 — Smoke-Test (A.5 Sub 3): die 3 Blöcke rendern, Geld in €
 * (R1 fmtZahl/formatGeld), T-Konto erbt das Kopf-Jahr (R5: KEIN eigener Jahr-<select>).
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
  }),
}))

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
})
