/**
 * Cockpit → Live „Wetter heute": die IST-Kurve muss im selben Stunden-Raster
 * liegen wie die Prognose daneben — Backward (#144/#297), Slot h = [h-1, h).
 *
 * Auslöser: Rainer PN 90106 („Der Prognosewert ist da nicht synchron, ist wohl
 * eine Stunde zu spät"). Gemessen am 01.08.2026 gegen die Live-Box: die
 * 10-Minuten-Punkte der Stunde 10 landeten in Spalte 10 — dort, wo die
 * Prognose bereits 10:00–11:00 zeigte. Auswertungen → Prognose führte
 * denselben Messwert korrekt in Slot 11.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import type { ReactNode } from 'react'
import WetterWidget, { istStundenSlots, prognoseStundenSlots } from './WetterWidget'
import { COLORS } from '../../lib'
import type { LiveWetterResponse, TagesverlaufResponse, VerbrauchsStunde } from '../../api/liveDashboard'
import { renderMitProvidern, stubMatchMedia } from '../../test/render'

// Die Render-Probe liest die Reihe, die das Chart bekommt: `AreaChart` merkt
// sich sein `data`, statt in jsdom (Breite 0) nichts zu zeichnen.
const gezeichnet: { data: Array<Record<string, unknown>> | null } = { data: null }
vi.mock('recharts', async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  ResponsiveContainer: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  AreaChart: ({ data }: { data: Array<Record<string, unknown>> }) => {
    gezeichnet.data = data
    return null
  },
}))

function tagesverlauf(punkte: Array<{ zeit: string; kw: number }>): TagesverlaufResponse {
  return {
    anlage_id: 1,
    datum: '2026-08-01',
    serien: [{ key: 'pv_4', label: 'PV', kategorie: 'pv', farbe: COLORS.solar, seite: 'quelle', bidirektional: false }],
    punkte: punkte.map(p => ({ zeit: p.zeit, werte: { pv_4: p.kw } })),
  }
}

describe('istStundenSlots — IST auf dem Backward-Raster der Prognose', () => {
  it('legt die Punkte der Stunde 10 in Slot 11, nicht in Slot 10', () => {
    const { istDaten } = istStundenSlots(tagesverlauf([
      { zeit: '10:00', kw: 3.0 }, { zeit: '10:30', kw: 3.4 },
    ]))
    expect(istDaten?.[11]?.pv).toBeCloseTo(3.2, 5)
    expect(istDaten?.[10]).toBeUndefined()
  })

  it('mittelt je Slot über alle 10-Minuten-Punkte der zugehörigen Stunde', () => {
    const { istDaten } = istStundenSlots(tagesverlauf([
      { zeit: '09:00', kw: 1.0 }, { zeit: '09:20', kw: 2.0 }, { zeit: '09:40', kw: 3.0 },
      { zeit: '10:00', kw: 5.0 },
    ]))
    expect(istDaten?.[10]?.pv).toBeCloseTo(2.0, 5)
    expect(istDaten?.[11]?.pv).toBeCloseTo(5.0, 5)
  })

  it('verschiebt keine Energie: die Tagessumme der Slot-Mittel bleibt gleich', () => {
    const punkte = Array.from({ length: 6 * 6 }, (_, i) => ({
      zeit: `${String(6 + Math.floor(i / 6)).padStart(2, '0')}:${String((i % 6) * 10).padStart(2, '0')}`,
      kw: 1 + (i % 7) * 0.3,
    }))
    const { istDaten } = istStundenSlots(tagesverlauf(punkte))
    const summeSlots = Object.values(istDaten ?? {}).reduce((s, v) => s + v.pv, 0)
    const summePunkte = punkte.reduce((s, p) => s + p.kw, 0) / 6  // 6 Punkte je Stunde
    expect(summeSlots).toBeCloseTo(summePunkte, 5)
  })

  it('kippt die letzte Tagesstunde nicht an den Tagesanfang', () => {
    const { istDaten } = istStundenSlots(tagesverlauf([{ zeit: '23:10', kw: 0.4 }]))
    // 23:00–24:00 gehört in Slot 0 des FOLGETAGS — nicht in Slot 0 von heute.
    expect(istDaten).toBeNull()
  })

  it('bleibt ohne Daten stumm statt eine leere Stunde zu erfinden', () => {
    expect(istStundenSlots(null).istDaten).toBeNull()
    expect(istStundenSlots(tagesverlauf([])).istDaten).toBeNull()
  })
})

/**
 * N-761 (#434, Burkard): die gestrichelte PV-Prognosekurve trug immer die
 * eedc-Reihe (`pv_ertrag_kw`), auch unter Kopfzahl und Vermerk «Solar Forecast
 * ML» — Σ Kurve 36,1 kWh neben 47,75 kWh. Sie folgt jetzt der gewählten Quelle
 * (SFML oder Solcast), wenn diese ein Stundenprofil meldet (Entscheid #401: ein Block, eine Quelle).
 */
describe('Wetter heute — PV-Prognosekurve aus der gewählten Quelle (N-761)', () => {
  // eedc-Reihe Σ 6,0 kWh, Reihe der Quelle Σ 9,0 kWh (= Kopfzahl der Quelle).
  const EEDC: Record<number, number> = { 10: 1.0, 11: 2.0, 12: 2.0, 13: 1.0 }
  const SFML: Record<number, number> = { 10: 1.5, 11: 3.0, 12: 3.0, 13: 1.5 }
  function profil(mitSfml: boolean): VerbrauchsStunde[] {
    return Array.from({ length: 24 }, (_, h) => ({
      zeit: `${String(h).padStart(2, '0')}:00`,
      pv_ertrag_kw: EEDC[h] ?? 0,
      verbrauch_kw: 0.5,
      pv_ml_prognose_kw: mitSfml ? (SFML[h] ?? 0) : null,
    }))
  }
  function wetter(teil: Partial<LiveWetterResponse>): LiveWetterResponse {
    return {
      anlage_id: 1, verfuegbar: true, grund: null, aktuell: null, stunden: [],
      temperatur_min_c: null, temperatur_max_c: null,
      sonnenstunden: null, sonnenstunden_bisher: null, sonnenstunden_rest: null,
      pv_prognose_kwh: 9.0, pv_prognose_rest_kwh: null, pv_prognose_heute_rollend_kwh: null,
      pv_ist_bisher_kwh: null, grundlast_kw: null, verbrauchsprofil: profil(true),
      prognose_quelle: 'sfml', prognose_quelle_hat_profil: true,
      ...teil,
    }
  }
  const summePv = (m: Record<number, { pv: number }>) => Object.values(m).reduce((s, v) => s + v.pv, 0)

  it('SFML mit Stundenprofil: die Kurve trägt die SFML-Reihe, Σ = Kopfzahl', () => {
    const w = wetter({})
    const m = prognoseStundenSlots(w)
    expect(m[11].pv).toBe(3.0)
    expect(summePv(m)).toBeCloseTo(w.pv_prognose_kwh!, 5)
  })

  it('SFML ohne Stundenprofil (GTI-Schmier): die Kurve bleibt die eedc-Reihe', () => {
    const m = prognoseStundenSlots(wetter({ prognose_quelle_hat_profil: false }))
    expect(m[11].pv).toBe(2.0)
    expect(summePv(m)).toBeCloseTo(6.0, 5)
  })

  it('Solcast mit Stundenprofil: die Kurve trägt die Solcast-Reihe, Σ = Kopfzahl', () => {
    const w = wetter({ prognose_quelle: 'solcast' })
    const m = prognoseStundenSlots(w)
    expect(m[11].pv).toBe(3.0)
    expect(summePv(m)).toBeCloseTo(w.pv_prognose_kwh!, 5)
  })

  it('eedc als Quelle: die eedc-Reihe — auch wenn eine Quellen-Reihe mitkäme (Rückfall mit Hinweis)', () => {
    const m = prognoseStundenSlots(wetter({ prognose_quelle: 'eedc', prognose_quelle_hat_profil: true }))
    expect(summePv(m)).toBeCloseTo(6.0, 5)
  })

  it('ein fehlender SFML-Stundenwert fällt auf den eedc-Wert dieser Stunde, eine SFML-0 bleibt 0', () => {
    const p = profil(true)
    p[12] = { ...p[12], pv_ml_prognose_kw: null }
    p[13] = { ...p[13], pv_ml_prognose_kw: 0 }
    const m = prognoseStundenSlots(wetter({ verbrauchsprofil: p }))
    expect(m[12].pv).toBe(2.0)
    expect(m[13].pv).toBe(0)
  })

  describe('Render-Probe: was das Chart bekommt', () => {
    beforeEach(() => {
      localStorage.clear()
      stubMatchMedia()
      gezeichnet.data = null
    })
    const gestrichelt = () => (gezeichnet.data ?? []).reduce((s, p) => s + ((p.pv_prognose as number | undefined) ?? 0), 0)

    it('SFML mit Profil: die gestrichelte Reihe summiert sich zur Kopfzahl, der Titel nennt die Quelle', () => {
      const { container } = renderMitProvidern(<WetterWidget wetter={wetter({})} />)
      expect(gestrichelt()).toBeCloseTo(9.0, 5)
      expect(container.querySelector('[title="PV-Tagesprognose aus Solar Forecast ML"]')).not.toBeNull()
    })

    it('Solcast mit Profil: die gestrichelte Reihe summiert sich zur Kopfzahl, der Titel nennt Solcast', () => {
      const { container } = renderMitProvidern(<WetterWidget wetter={wetter({ prognose_quelle: 'solcast' })} />)
      expect(gestrichelt()).toBeCloseTo(9.0, 5)
      expect(container.querySelector('[title="PV-Tagesprognose aus Solcast"]')).not.toBeNull()
    })

    it('eedc als Quelle: die gestrichelte Reihe ist die eedc-Reihe', () => {
      renderMitProvidern(<WetterWidget wetter={wetter({ prognose_quelle: 'eedc', prognose_quelle_hat_profil: false, pv_prognose_kwh: 6.0 })} />)
      expect(gestrichelt()).toBeCloseTo(6.0, 5)
    })

    it('SFML ohne Profil: die gestrichelte Reihe ist die eedc-Reihe', () => {
      renderMitProvidern(<WetterWidget wetter={wetter({ prognose_quelle_hat_profil: false })} />)
      expect(gestrichelt()).toBeCloseTo(6.0, 5)
    })
  })
})
