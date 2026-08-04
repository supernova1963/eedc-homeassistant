/**
 * SOLL-Erfüllung — die Anzeige sagt, über welches Fenster sie spricht (N-69).
 *
 * Das Backend kürzt den SOLL-Nenner im laufenden Monat auf die abgelaufenen
 * Tage (Entscheid Gernot 2026-08-04). Damit stimmt die Prozentzahl — die
 * kWh-Zahl daneben ist dann aber kein Monats-SOLL mehr, und genau das muss die
 * Oberfläche sagen. Zahlen aus der Messung an Gernots Anlage (2026-08-04).
 */
import { describe, it, expect } from 'vitest'
import { istSollAnteilig, sollErfuellungProzent, sollFensterText } from './sollErfuellung'
import type { SollQuelle } from './sollErfuellung'

const q = (p: Partial<SollQuelle>): SollQuelle => ({
  soll_pv_kwh: null, pv_erzeugung_kwh: null, soll_pv_tage: null, soll_pv_tage_gesamt: null,
  ...p,
} as SollQuelle)

describe('sollErfuellungProzent', () => {
  it('rechnet die gekürzte Augustzahl (148 %, nicht 19 %)', () => {
    const pct = sollErfuellungProzent(q({
      soll_pv_kwh: 179.1, pv_erzeugung_kwh: 264.75, soll_pv_tage: 4, soll_pv_tage_gesamt: 31,
    }))
    expect(Math.round(pct!)).toBe(148)
  })

  it('gibt null ohne SOLL', () => {
    expect(sollErfuellungProzent(q({ pv_erzeugung_kwh: 264.75 }))).toBeNull()
  })

  it('gibt null bei SOLL 0 — ein Monat in der Zukunft hat keine Erfüllung', () => {
    expect(sollErfuellungProzent(q({
      soll_pv_kwh: 0, pv_erzeugung_kwh: 0, soll_pv_tage: 0, soll_pv_tage_gesamt: 30,
    }))).toBeNull()
  })
})

describe('sollFensterText', () => {
  it('benennt das Fenster im laufenden Monat', () => {
    const d = q({ soll_pv_kwh: 179.1, pv_erzeugung_kwh: 264.75, soll_pv_tage: 4, soll_pv_tage_gesamt: 31 })
    expect(istSollAnteilig(d)).toBe(true)
    expect(sollFensterText(d)).toBe('anteilig · 4 von 31 Tagen')
  })

  it('schweigt im abgeschlossenen Monat', () => {
    const d = q({ soll_pv_kwh: 1509, pv_erzeugung_kwh: 1843.25, soll_pv_tage: 31, soll_pv_tage_gesamt: 31 })
    expect(istSollAnteilig(d)).toBe(false)
    expect(sollFensterText(d)).toBeNull()
  })

  it('schweigt, solange das Backend die Felder nicht liefert', () => {
    // Ältere Antwort ohne die beiden Felder: keine Behauptung über ein Fenster.
    expect(sollFensterText(q({ soll_pv_kwh: 1509, pv_erzeugung_kwh: 1843.25 }))).toBeNull()
  })

  it('summiert im Jahr über die Monate', () => {
    // Jan–Jul voll (212 Tage) + 4 Augusttage von 31.
    const d = q({ soll_pv_kwh: 8107.8, pv_erzeugung_kwh: 9715.02, soll_pv_tage: 216, soll_pv_tage_gesamt: 243 })
    expect(sollFensterText(d)).toBe('anteilig · 216 von 243 Tagen')
    expect(Math.round(sollErfuellungProzent(d)!)).toBe(120)
  })
})
