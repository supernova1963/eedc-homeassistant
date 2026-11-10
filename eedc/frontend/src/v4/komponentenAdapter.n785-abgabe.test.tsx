/**
 * #443 / N-785 — *Komponenten → Sonstiges* kennt die Kategorie «Abgabe an Dritte».
 *
 * Bis 4.2.2 fiel ein Abgabe-Gerät im Adapter in die Erzeuger-Sicht (Erzeugung «—», Verlauf und Vergleich aus
 * `erzeugung_kwh`), im Backend in den Speicher-Zweig (Ladung/Entladung 0). Jetzt: Abgabe · Erlös · Monate, Verlauf und
 * Vergleich aus `abgabe_monatsreihe` (Monats-Fakten des Backends), keine Ersparnis- und keine CO₂-Kachel.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

const getSonstigesDashboard = vi.fn()
vi.mock('../api/investitionen', () => ({
  investitionenApi: { getSonstigesDashboard: (...a: unknown[]) => getSonstigesDashboard(...a) },
}))

import { KOMPONENTEN_ADAPTER } from './komponentenAdapter'
import type { SonstigesAbgabeMonat } from '../api/investitionen'

const inv = { id: 12, anlage_id: 1, typ: 'sonstiges', bezeichnung: 'Mieterstrom', aktiv: true }
const GRUND = 'Abgabe an Dritte ist kein Eigenverbrauch; ein Erlös steht nur, wenn er am Gerät gepflegt ist.'
const am = (jahr: number, monat: number, abgabe_kwh: number, erloes_euro: number | null = null): SonstigesAbgabeMonat =>
  ({ jahr, monat, abgabe_kwh, erloes_euro })

/** Die Rohzeile trägt absichtlich `erzeugung_kwh` (Alt-Monat vor der Umstellung) — sie darf nirgends erscheinen. */
const antwort = (reihe: SonstigesAbgabeMonat[], z: Record<string, unknown>) => [{
  investition: inv,
  zusammenfassung: { kategorie: 'abgabe', sonderkosten_euro: 0, ...z },
  monatsdaten: reihe.map((m) => ({ jahr: m.jahr, monat: m.monat, verbrauch_daten: { erzeugung_kwh: 999 } })),
  monatsreihe: [],
  abgabe_monatsreihe: reihe,
}]

beforeEach(() => { vi.clearAllMocks() })

describe('#443 — Abgabe an Dritte im Komponenten-Hub', () => {
  it('Kennzahlen: Abgabe · Erlös · Monate — keine Ersparnis-, keine CO₂-Kachel', async () => {
    getSonstigesDashboard.mockResolvedValue(antwort([am(2025, 12, 205, 12.5), am(2026, 1, 210, 12.5)], {
      gesamt_abgabe_kwh: 415, erloes_abgabe_euro: 25, monate_mit_erloes: 2, monate_mit_abgabe: 2, bewertet: true,
    }))
    const [g] = await KOMPONENTEN_ADAPTER.sonstiges.fetch(1)
    expect(g.status.map((k) => [k.title, k.value, k.unit])).toEqual([
      ['Abgabe', '415', 'kWh'], ['Erlös', '25,00', '€'], ['Monate', '2', ''],
    ])
    expect(g.status.some((k) => /Ersparnis|CO₂/.test(String(k.title)))).toBe(false)
    expect(g.selektorBadge).toBe('Abgabe an Dritte')
  })

  it('Verlauf: eine Balkenreihe «Abgabe» je Monat aus der Reihe, nicht aus `erzeugung_kwh`', async () => {
    getSonstigesDashboard.mockResolvedValue(antwort([am(2026, 2, 190), am(2026, 1, 210)], {
      gesamt_abgabe_kwh: 400, monate_mit_abgabe: 2, bewertet: false, nicht_bewertet_grund: GRUND,
    }))
    const [g] = await KOMPONENTEN_ADAPTER.sonstiges.fetch(1)
    expect(g.verlauf?.bars.map((b) => [b.key, b.label])).toEqual([['abgabe', 'Abgabe']])
    expect(g.verlauf?.rows.map((r) => [r.name, r.abgabe])).toEqual([['Jan 26', 210], ['Feb 26', 190]])
  })

  it('Vergleich: Jahressummen der Abgabe aus der Reihe des Backends', async () => {
    getSonstigesDashboard.mockResolvedValue(antwort([am(2025, 11, 185), am(2025, 12, 205), am(2026, 1, 210)], {
      gesamt_abgabe_kwh: 600, monate_mit_abgabe: 3, bewertet: false, nicht_bewertet_grund: GRUND,
    }))
    const [g] = await KOMPONENTEN_ADAPTER.sonstiges.fetch(1)
    expect(g.vergleich?.label).toBe('Abgabe')
    expect(g.vergleich?.jahre).toEqual([{ jahr: 2025, summe: 390 }, { jahr: 2026, summe: 210 }])
  })

  it('Wirtschaftlichkeit mit Erlös: EIN Posten «Erlös aus der Abgabe»', async () => {
    getSonstigesDashboard.mockResolvedValue(antwort([am(2026, 1, 210, 12.5)], {
      gesamt_abgabe_kwh: 210, erloes_abgabe_euro: 12.5, monate_mit_erloes: 1, monate_mit_abgabe: 1, bewertet: true,
    }))
    const [g] = await KOMPONENTEN_ADAPTER.sonstiges.fetch(1)
    expect(g.wirtschaftlichkeit?.posten.map((p) => [p.label, p.euro])).toEqual([['Erlös aus der Abgabe', 12.5]])
    expect(g.wirtschaftlichkeit?.nichtBewertet).toBeUndefined()
  })

  it('ohne Erlös: Kachel «nicht bewertet», Wirtschaftlichkeit mit dem Grund des Backends', async () => {
    getSonstigesDashboard.mockResolvedValue(antwort([am(2026, 1, 210)], {
      gesamt_abgabe_kwh: 210, erloes_abgabe_euro: null, monate_mit_erloes: 0, monate_mit_abgabe: 1,
      bewertet: false, nicht_bewertet_grund: GRUND,
    }))
    const [g] = await KOMPONENTEN_ADAPTER.sonstiges.fetch(1)
    const erloes = g.status.find((k) => k.title === 'Erlös')
    expect([erloes?.value, erloes?.color]).toEqual(['—', 'gray'])
    expect(g.wirtschaftlichkeit).toEqual({ posten: [], nichtBewertet: GRUND })
  })

  it('ohne Monatsreihe weder Verlauf noch Vergleich', async () => {
    getSonstigesDashboard.mockResolvedValue(antwort([], { gesamt_abgabe_kwh: 0, monate_mit_abgabe: 0, bewertet: false, nicht_bewertet_grund: GRUND }))
    const [g] = await KOMPONENTEN_ADAPTER.sonstiges.fetch(1)
    expect(g.verlauf).toBeUndefined()
    expect(g.vergleich).toBeUndefined()
  })
})
