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
import { describe, it, expect } from 'vitest'
import { istStundenSlots } from './WetterWidget'
import { COLORS } from '../../lib'
import type { TagesverlaufResponse } from '../../api/liveDashboard'

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
