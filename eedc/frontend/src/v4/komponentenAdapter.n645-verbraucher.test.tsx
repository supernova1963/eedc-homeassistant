/**
 * N-645 — *Komponenten → Sonstiges* ④ Verlauf / ⑤ Vergleich eines Verbrauchers lesen die bewertete Monatsreihe.
 *
 * Bis 4.1.3 summierte der Vergleich den Legacy-Zwilling `verbrauch_kwh` (Kachel und Lesetür nehmen den Kanon
 * `verbrauch_sonstig_kwh` zuerst): M07 Pool (beide Namen) 108 statt 72, M10 Sauna (nur Kanon) 0 statt 24. Der
 * Verlauf stapelte nur PV- und Netzbezug — ohne diese Messung kein Balken, obwohl die Kachel den Verbrauch
 * nannte. Fachentscheid Master 09.10.: was keine Messung aufteilt, steht als EIN Segment „nicht aufgeteilt".
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

const getSonstigesDashboard = vi.fn()
vi.mock('../api/investitionen', () => ({
  investitionenApi: { getSonstigesDashboard: (...a: unknown[]) => getSonstigesDashboard(...a) },
}))

import { KOMPONENTEN_ADAPTER } from './komponentenAdapter'
import type { SonstigesMonatsWert } from '../api/investitionen'

const inv = { id: 1, anlage_id: 1, typ: 'sonstiges', bezeichnung: 'Pool', aktiv: true }
const mw = (jahr: number, monat: number, w: Partial<SonstigesMonatsWert>): SonstigesMonatsWert => {
  const v = w.verbrauch_kwh ?? 0
  const pv = w.bezug_pv_kwh ?? 0
  const netz = w.bezug_netz_kwh ?? 0
  return { jahr, monat, verbrauch_kwh: v, bezug_pv_kwh: pv, bezug_netz_kwh: netz,
    nicht_aufgeteilt_kwh: Math.max(0, v - pv - netz), ...w }
}
/** Die Rohzeile steht absichtlich daneben — mit dem Legacy-Zwilling, den der Vergleich früher las. */
const antwort = (monatsreihe: SonstigesMonatsWert[], verbrauch_daten: Record<string, number> = {}) => [{
  investition: inv,
  zusammenfassung: { kategorie: 'verbraucher', gesamt_verbrauch_kwh: 72, sonderkosten_euro: 0 },
  monatsdaten: monatsreihe.map((m) => ({ jahr: m.jahr, monat: m.monat, verbrauch_daten })),
  monatsreihe,
}]

beforeEach(() => { vi.clearAllMocks() })

describe('N-645 — Sonstiges-Verbraucher aus der Monatsreihe', () => {
  it('Vergleich summiert den Verbrauch der Reihe, nicht den Legacy-Zwilling der Rohzeile', async () => {
    getSonstigesDashboard.mockResolvedValue(antwort([mw(2026, 6, { verbrauch_kwh: 72 })], { verbrauch_kwh: 108 }))
    const [g] = await KOMPONENTEN_ADAPTER.sonstiges.fetch(1)
    expect(g.vergleich?.jahre).toEqual([{ jahr: 2026, summe: 72 }])
  })

  it('ohne PV-/Netz-Messung EIN Segment „nicht aufgeteilt" mit dem ganzen Verbrauch', async () => {
    getSonstigesDashboard.mockResolvedValue(antwort([mw(2026, 6, { verbrauch_kwh: 24 }), mw(2026, 7, { verbrauch_kwh: 30 })]))
    const [g] = await KOMPONENTEN_ADAPTER.sonstiges.fetch(1)
    expect(g.verlauf?.bars.map((b) => [b.key, b.label])).toEqual([['rest', 'nicht aufgeteilt']])
    expect(g.verlauf?.rows.map((r) => [r.name, r.rest])).toEqual([['Jun 26', 24], ['Jul 26', 30]])
  })

  it('mit Teilmessung: PV · Netz · nicht aufgeteilt; Σ Segmente = Verbrauch des Monats', async () => {
    getSonstigesDashboard.mockResolvedValue(antwort([
      mw(2026, 6, { verbrauch_kwh: 100, bezug_pv_kwh: 30, bezug_netz_kwh: 50 }),
    ]))
    const [g] = await KOMPONENTEN_ADAPTER.sonstiges.fetch(1)
    expect(g.verlauf?.bars.map((b) => b.key)).toEqual(['pv', 'netz', 'rest'])
    const [r] = g.verlauf!.rows
    expect([r.pv, r.netz, r.rest]).toEqual([30, 50, 20])
    expect(Number(r.pv) + Number(r.netz) + Number(r.rest)).toBe(100)
  })

  it('voll gemessen: kein Segment „nicht aufgeteilt" (vertraute Anzeige PV ⟷ Netz)', async () => {
    getSonstigesDashboard.mockResolvedValue(antwort([
      mw(2026, 6, { verbrauch_kwh: 80, bezug_pv_kwh: 30, bezug_netz_kwh: 50 }),
    ]))
    const [g] = await KOMPONENTEN_ADAPTER.sonstiges.fetch(1)
    expect(g.verlauf?.bars.map((b) => b.key)).toEqual(['pv', 'netz'])
  })

  it('ohne Monatsreihe weder Verlauf noch Vergleich', async () => {
    getSonstigesDashboard.mockResolvedValue(antwort([]))
    const [g] = await KOMPONENTEN_ADAPTER.sonstiges.fetch(1)
    expect(g.verlauf).toBeUndefined()
    expect(g.vergleich).toBeUndefined()
  })
})
