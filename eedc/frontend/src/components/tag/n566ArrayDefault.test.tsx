/**
 * N-566 — ein optionaler Array-Prop darf keinen `= []`-Default im Parameter tragen, wenn er in
 * eine Effekt- oder Memo-Abhängigkeit läuft.
 *
 * `TagWerteTabelle` rendete endlos, sobald ein Aufrufer `erzeugerSerien` wegließ: der Default
 * `= []` war je Render ein neues Array, `erzeugerSpalten` damit auch, und der Spalten-Effekt
 * setzte State (Lücken-Bau, Minimal-Probe hing bis `timeout 60`). Produktiv unerreicht, weil
 * `CockpitTagV4` die Prop immer übergibt — eine Falle für den zweiten Aufrufer.
 *
 * Dieselbe Bauform stand in `TagVerlaufChart` (`erzeugerSerien`, `wpSerien`) und in
 * `WaermeVerlaufChart` (`linien`) — dort ohne Effekt, aber in Memo-Abhängigkeiten: jeder Render
 * rechnete den Chart neu. Die Proben unten zählen das an einem Aufruf, den nur die Memos machen.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ThemeProvider } from '../../context/ThemeContext'
import { stubMatchMedia } from '../../test/render'
import { TagWerteTabelle } from './TagWerteTabelle'
import { TagVerlaufChart } from './TagVerlaufChart'
import { WaermeVerlaufChart, type VerlaufStapel } from '../../v4/WaermeVerlaufChart'
import type { StundenWert, SerieInfo } from '../../api/energie_profil'

const stunde = (h: number, over: Partial<StundenWert> = {}): StundenWert => ({
  stunde: h,
  pv_kw: null, verbrauch_kw: null, einspeisung_kw: null, netzbezug_kw: null,
  batterie_kw: null, waermepumpe_kw: null, wallbox_kw: null,
  ueberschuss_kw: null, defizit_kw: null,
  temperatur_c: null, globalstrahlung_wm2: null, soc_prozent: null,
  komponenten: null, wp_starts_anzahl: null, wp_betriebsstunden: null,
  ...over,
})

const KEINE_EXTRA: SerieInfo[] = []
const DATEN: StundenWert[] = [
  stunde(9, { pv_kw: 1.0, netzbezug_kw: 0.2, einspeisung_kw: 0.1, verbrauch_kw: 1.1 }),
  stunde(10, { pv_kw: 1.5, netzbezug_kw: 0.1, einspeisung_kw: 0.2, verbrauch_kw: 1.4 }),
]

beforeEach(() => {
  // Der ThemeProvider (Achsenfarben des Tages-Charts) fragt die Systemeinstellung ab.
  stubMatchMedia()
})

describe('N-566 — Array-Default als Abhängigkeit', () => {
  it('TagWerteTabelle rendert ohne `erzeugerSerien` und endet', () => {
    // Vor N-566 kehrte `render` hier nie zurück (Effekt → State → neues `[]` → Effekt …).
    render(<TagWerteTabelle daten={DATEN} extraSerien={KEINE_EXTRA} datum="2026-05-24" gesamtverbrauchTag={2.5} verworfen={{}} />)
    expect(screen.getAllByText('2,50').length).toBeGreaterThan(0)
  })

  it('TagVerlaufChart rechnet bei gleichem Input nicht neu, wenn `erzeugerSerien`/`wpSerien` fehlen', () => {
    const daten = [...DATEN]
    const find = vi.spyOn(daten, 'find')              // nur `baueChartDaten` (Memo) ruft `daten.find`
    const chart = <ThemeProvider><TagVerlaufChart daten={daten} extraSerien={KEINE_EXTRA} /></ThemeProvider>
    const { rerender } = render(chart)
    const nachErstem = find.mock.calls.length
    expect(nachErstem).toBeGreaterThan(0)
    rerender(<ThemeProvider><TagVerlaufChart daten={daten} extraSerien={KEINE_EXTRA} /></ThemeProvider>)
    rerender(<ThemeProvider><TagVerlaufChart daten={daten} extraSerien={KEINE_EXTRA} /></ThemeProvider>)
    expect(find.mock.calls.length).toBe(nachErstem)
  })

  it('WaermeVerlaufChart rechnet die Einheiten nicht neu, wenn `linien` fehlt', () => {
    const stapel: VerlaufStapel[] = [{ key: 'heizen', label: 'Heizen', farbe: 'x' } as unknown as VerlaufStapel]
    const forEach = vi.spyOn(stapel, 'forEach')      // nur das Memo `einheitJeLabel` ruft `stapel.forEach`
    const { rerender } = render(<WaermeVerlaufChart rows={[]} stapel={stapel} />)
    const nachErstem = forEach.mock.calls.length
    expect(nachErstem).toBeGreaterThan(0)
    rerender(<WaermeVerlaufChart rows={[]} stapel={stapel} />)
    rerender(<WaermeVerlaufChart rows={[]} stapel={stapel} />)
    expect(forEach.mock.calls.length).toBe(nachErstem)
  })
})
