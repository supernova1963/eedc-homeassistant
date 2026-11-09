import { describe, expect, it } from 'vitest'
import { pvVergleichHerkunft, PV_MODUL_VERTEILT_HERKUNFT } from './pvHerkunft'

describe('Päckchen CC — Herkunftszeile der String-Platzierung je Fall', () => {
  it('ein Modul ohne jeden Wert im Zeitraum ist «offen», nicht «geschätzt (kWp-Anteil)»', () => {
    const h = pvVergleichHerkunft('IST je Modul', 'Nicht alle Module haben in diesem Jahr Werte …', 'nicht_alle_werte')
    expect(h.zustand).toBe('fehlt')
    expect(h.quelleLabel).toBeUndefined()
    expect(h.hinweis).toBe('Nicht alle Module haben in diesem Jahr Werte …')
  })

  it('verteilte Werte behalten das Zeichen «geschätzt (kWp-Anteil)»', () => {
    for (const grund of ['verteilt', 'teilweise_verteilt', null, undefined]) {
      const h = pvVergleichHerkunft('IST je Modul', null, grund)
      expect(h.zustand).toBe('geschaetzt')
      expect(h.quelleLabel).toBe(PV_MODUL_VERTEILT_HERKUNFT.quelleLabel)
    }
  })
})
