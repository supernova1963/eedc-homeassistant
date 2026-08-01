/**
 * Nagelt die Zuordnung Stunde → Zeitspanne fest (Backward, #144/#297).
 *
 * Auslöser: Rainer PN 90106 — „Mal wird beim 11:00-Uhr-Punkt von 10:00–11:00
 * angezeigt, mal 11:00–12:00." Zwei Sichten hatten sich ihre Zeitspanne je
 * selbst gebaut; seitdem gibt es genau diese eine Stelle.
 */
import { describe, it, expect } from 'vitest'
import { slotZeitspanne, slotAusIntervallStart, slotAusZeitpunkt } from './stundenSlot'

describe('slotZeitspanne — Slot h trägt [h-1, h)', () => {
  it('beschriftet den 11-Uhr-Punkt mit 10:00–11:00 Uhr', () => {
    expect(slotZeitspanne(11)).toBe('10:00–11:00 Uhr')
  })

  it('führt Slot 0 auf die letzte Stunde des Vortags zurück', () => {
    expect(slotZeitspanne(0)).toBe('23:00–00:00 Uhr')
  })

  it('beschriftet den letzten Slot des Tages als 22:00–23:00 Uhr', () => {
    expect(slotZeitspanne(23)).toBe('22:00–23:00 Uhr')
  })

  it('bleibt bei allen 24 Slots lückenlos und überschneidungsfrei', () => {
    const beginne = Array.from({ length: 24 }, (_, h) => slotZeitspanne(h).slice(0, 5))
    expect(new Set(beginne).size).toBe(24)
    for (let h = 0; h < 24; h++) {
      // Ende des Slots h ist der Beginn von Slot h+1
      expect(slotZeitspanne(h).slice(6, 11)).toBe(slotZeitspanne((h + 1) % 24).slice(0, 5))
    }
  })
})

describe('slotAusIntervallStart — Messreihe mit Slot-Beginn-Stempel', () => {
  it('legt einen um 10:xx beginnenden Punkt in Slot 11', () => {
    expect(slotAusIntervallStart(10)).toBe(11)
  })

  it('meldet für die letzte Tagesstunde Slot 24 (= Folgetag), statt auf 0 zu kippen', () => {
    expect(slotAusIntervallStart(23)).toBe(24)
  })

  it('ist die Umkehrung der Beschriftung: der Slot trägt genau die Stunde davor', () => {
    for (let h = 0; h < 23; h++) {
      expect(slotZeitspanne(slotAusIntervallStart(h)).slice(0, 5)).toBe(`${String(h).padStart(2, '0')}:00`)
    }
  })
})

describe('slotAusZeitpunkt — Zeitpunkt in den Slot, der ihn enthält', () => {
  it('ordnet Sonnenaufgang 05:56 dem Slot 6 zu (nicht 5)', () => {
    expect(slotAusZeitpunkt('05:56')).toBe(6)
  })

  it('behandelt die volle Stunde als Ende ihres Slots', () => {
    expect(slotAusZeitpunkt('06:00')).toBe(6)
  })

  it('schiebt einen Zeitpunkt der letzten Tagesstunde auf 24 (Folgetag)', () => {
    expect(slotAusZeitpunkt('23:30')).toBe(24)
  })

  it('liefert null statt einer erfundenen Stunde, wenn nichts Lesbares kommt', () => {
    expect(slotAusZeitpunkt('')).toBeNull()
    expect(slotAusZeitpunkt('kaputt')).toBeNull()
  })
})
