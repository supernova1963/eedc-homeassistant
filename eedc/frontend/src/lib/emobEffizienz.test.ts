import { describe, it, expect } from 'vitest'
import { emobEffizienzZeitraum, type EmobVerbrauchQuelle } from './emobEffizienz'

/**
 * Fixtures WORTGLEICH zu `backend/tests/test_n557_emob_effizienz_symmetrie.py`.
 * Wer hier eine Zeile ändert, ändert sie dort mit — der Backend-Test liest
 * diesen Block und vergleicht ihn Feld für Feld.
 *
 * [[[basis_kwh, km, quelle], …], erwartetWert, erwarteteQuelle]
 */
type Monat = [number | null, number, EmobVerbrauchQuelle]
const FIXTURES: [Monat[], number | null, EmobVerbrauchQuelle][] = [
  // Verbrauchssensor erst ab Monat 7: Näherung + Messung, Σ ÷ Σ, „ladung".
  [[[300.0, 1500.0, 'ladung'], [270.0, 1500.0, 'gemessen']], 19.0, 'ladung'],
  // Alle Monate gemessen ⇒ „gemessen".
  [[[270.0, 1500.0, 'gemessen'], [180.0, 1000.0, 'gemessen']], 18.0, 'gemessen'],
  // Ein Monat mit km, aber ohne jede Energiemenge, verdünnt die Quote nicht —
  // und macht aus „gemessen" eine Näherung.
  [[[270.0, 1500.0, 'gemessen'], [null, 500.0, 'keine']], 18.0, 'ladung'],
  // Ein Monat ohne km zählt weder im Zähler noch im Nenner.
  [[[270.0, 1500.0, 'gemessen'], [null, 0.0, 'keine']], 18.0, 'gemessen'],
  // Keine Basis ⇒ keine Zahl.
  [[[null, 0.0, 'keine']], null, 'keine'],
  [[], null, 'keine'],
]

describe('emobEffizienzZeitraum — Spiegel des Layer-SoT (N-557)', () => {
  it.each(FIXTURES)('%j ⇒ %s (%s)', (monate, wert, quelle) => {
    const e = emobEffizienzZeitraum(
      monate.map(([basis_kwh, km, q]) => ({ basis_kwh, km, quelle: q })),
    )
    expect(e.quelle).toBe(quelle)
    if (wert === null) expect(e.wert).toBeNull()
    else expect(e.wert).toBeCloseTo(wert, 6)
  })
})
