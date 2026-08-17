import { describe, it, expect } from 'vitest'
import { speicherWirkungsgrad, MINDEST_LADUNG_KWH } from './speicherWirkungsgrad'

/**
 * Fixtures WORTGLEICH zu `backend/tests/test_speicher_wirkungsgrad_symmetrie.py`.
 * Wer hier eine Zeile ändert, ändert sie dort mit — der Backend-Test liest
 * diesen Block und vergleicht ihn Feld für Feld.
 *
 * [ladung, entladung, langesFensterQuelle, erwartetProzent, erwarteteQuelle]
 */
const FIXTURES = [
  [100.0, 88.0, null, 88.0, 'roh-unkorrigiert'],
  [100.0, 88.0, 'fenster_lang', 88.0, 'fenster_lang'],
  // Der Kern des Befundes: über 100 % gibt es KEINEN Wert — auch nicht im
  // langen Fenster, und schon gar nicht mit bestätigendem Etikett.
  [100.0, 104.0, null, null, 'nicht-ermittelbar'],
  [100.0, 104.0, 'fenster_lang', null, 'nicht-ermittelbar'],
  // Genau 100 % ist möglich (Grenzfall, kein Ausschluss).
  [100.0, 100.0, null, 100.0, 'roh-unkorrigiert'],
  // 0 % ist eine Messung, keine Leerstelle.
  [50.0, 0.0, null, 0.0, 'roh-unkorrigiert'],
  // Unterhalb der Mindest-Ladung ist der Quotient Rauschen.
  [0.0, 0.0, null, null, 'keine-ladung'],
  [0.05, 4.0, null, null, 'keine-ladung'],
  [0.1, 0.09, null, null, 'keine-ladung'],
]

describe('speicherWirkungsgrad — Spiegel des Layer-SoT', () => {
  it.each(FIXTURES)(
    'ladung=%s entladung=%s fenster=%s ⇒ %s (%s)',
    (ladung, entladung, fenster, prozent, quelle) => {
      const eta = speicherWirkungsgrad(
        ladung as number,
        entladung as number,
        (fenster ?? undefined) as 'fenster_lang' | undefined,
      )
      expect(eta.quelle).toBe(quelle)
      if (prozent === null) expect(eta.prozent).toBeNull()
      else expect(eta.prozent).toBeCloseTo(prozent as number, 6)
    },
  )

  it('behandelt null/undefined wie 0 — ohne zu werfen', () => {
    expect(speicherWirkungsgrad(null, null).quelle).toBe('keine-ladung')
    expect(speicherWirkungsgrad(undefined, undefined).prozent).toBeNull()
    expect(speicherWirkungsgrad(100, null).prozent).toBe(0)
  })

  it('trägt dieselbe Mindest-Ladung wie das Backend', () => {
    expect(MINDEST_LADUNG_KWH).toBe(0.1)
  })
})
