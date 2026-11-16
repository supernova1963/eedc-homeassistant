/**
 * Beipack N-799 S1 — *Komponenten → Sonstiges*, Kategorie «Speicher»: Verlauf und Vergleich aus `speicher_monatsreihe`.
 *
 * Das Monatsformular schreibt Ladung/Entladung unter `verbrauch_sonstig_kwh`/`erzeugung_kwh` (Feld-Registry). Bis hier
 * las der Hub `ladung_kwh`/`entladung_kwh` aus `verbrauch_daten`: die Kacheln (Backend) zeigten 310/240 kWh, der Verlauf
 * «Ladung ⟷ Entladung» und der Vergleich «Entladung» blieben 0. Jetzt liefert das Backend die Mengen je Monat über die
 * eine Feldwahl (`field_definitions.get_sonstiges_speicher_kwh`), der Adapter liest nur diese Reihe.
 *
 * Schwesterdateien: komponentenAdapter.n785-abgabe.test.tsx, komponentenAdapter.n645-verbraucher.test.tsx.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

const getSonstigesDashboard = vi.fn()
vi.mock('../api/investitionen', () => ({
  investitionenApi: { getSonstigesDashboard: (...a: unknown[]) => getSonstigesDashboard(...a) },
}))

import { KOMPONENTEN_ADAPTER } from './komponentenAdapter'
import type { SonstigesSpeicherMonat } from '../api/investitionen'

const inv = { id: 13, anlage_id: 1, typ: 'sonstiges', bezeichnung: 'Wärmespeicher', aktiv: true }
const sm = (jahr: number, monat: number, ladung_kwh: number, entladung_kwh: number): SonstigesSpeicherMonat =>
  ({ jahr, monat, ladung_kwh, entladung_kwh })

/** Die Rohzeilen tragen die Registry-Felder (wie das Formular) — der Adapter darf sie nicht selbst lesen. */
const antwort = (reihe: SonstigesSpeicherMonat[]) => [{
  investition: inv,
  zusammenfassung: {
    kategorie: 'speicher', gesamt_ladung_kwh: 310, gesamt_entladung_kwh: 240, effizienz_prozent: 77.4,
    ersparnis_euro: 52.32, sonderkosten_euro: 0,
  },
  monatsdaten: reihe.map((m) => ({
    jahr: m.jahr, monat: m.monat,
    verbrauch_daten: { verbrauch_sonstig_kwh: m.ladung_kwh, erzeugung_kwh: m.entladung_kwh },
  })),
  monatsreihe: [],
  speicher_monatsreihe: reihe,
}]

beforeEach(() => { vi.clearAllMocks() })

describe('Sonstiges-Speicher im Komponenten-Hub', () => {
  it('Verlauf «Ladung ⟷ Entladung» je Monat aus der Reihe des Backends', async () => {
    getSonstigesDashboard.mockResolvedValue(antwort([sm(2025, 2, 120, 90), sm(2025, 1, 100, 80), sm(2025, 3, 90, 70)]))
    const [g] = await KOMPONENTEN_ADAPTER.sonstiges.fetch(1)
    expect(g.verlauf?.bars.map((b) => b.key)).toEqual(['ladung', 'entladung'])
    expect(g.verlauf?.rows.map((r) => [r.name, r.ladung, r.entladung])).toEqual([
      ['Jan 25', 100, 80], ['Feb 25', 120, 90], ['Mär 25', 90, 70],
    ])
  })

  it('Vergleich «Entladung»: Jahressummen aus der Reihe', async () => {
    getSonstigesDashboard.mockResolvedValue(antwort([sm(2024, 12, 50, 40), sm(2025, 1, 100, 80), sm(2025, 2, 120, 90)]))
    const [g] = await KOMPONENTEN_ADAPTER.sonstiges.fetch(1)
    expect(g.vergleich?.label).toBe('Entladung')
    expect(g.vergleich?.jahre).toEqual([{ jahr: 2024, summe: 40 }, { jahr: 2025, summe: 170 }])
  })

  it('ältere Backend-Antwort ohne Reihe: Verlauf leer statt Rohfelder zu raten', async () => {
    const [a] = antwort([sm(2025, 1, 100, 80)])
    getSonstigesDashboard.mockResolvedValue([{ ...a, speicher_monatsreihe: undefined }])
    const [g] = await KOMPONENTEN_ADAPTER.sonstiges.fetch(1)
    expect(g.verlauf?.rows).toEqual([])
    expect(g.vergleich?.jahre).toEqual([])
  })
})
