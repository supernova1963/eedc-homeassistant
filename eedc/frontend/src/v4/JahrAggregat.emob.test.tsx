import { describe, it, expect } from 'vitest'
import { baueJahrAlsMonat } from './JahrAggregat'
import { aktuellerMonat } from '../test/factories'

/**
 * N-557 — *Cockpit → Jahr*: kWh/100 km ist Σ Monatswerte ÷ Σ km, „Ladung gesamt"
 * ist Σ (Heim + Extern). Konzept Heimladung/Fahrverbrauch, Regel 10.
 *
 * Bis zum 25.09.2026 bildete das Jahr `Σ Heimladung ÷ Σ km` und nannte das
 * „gemessen", sobald ein einziger Monat gemessen war — mit Verbrauchssensor ab
 * Juli also eine Ladungs-Quote unter dem Etikett einer Messung (Johnny_1993 #375).
 */

const monat = (m: number, heim: number, extern: number, km: number, fahrverbrauch: number | null) => {
  const gesamt = heim + extern
  return aktuellerMonat(2025, m, {
    emob_ladung_kwh: heim,
    emob_ladung_extern_kwh: extern,
    emob_ladung_gesamt_kwh: gesamt,
    emob_km: km,
    emob_verbrauch_quelle: fahrverbrauch != null ? 'gemessen' : 'ladung',
    emob_verbrauch_basis_kwh: fahrverbrauch ?? gesamt,
    emob_verbrauch_100km: ((fahrverbrauch ?? gesamt) / km) * 100,
    hat_emobilitaet: true,
  })
}

describe('Cockpit → Jahr: E-Mobilität (N-557)', () => {
  const jahr = baueJahrAlsMonat(
    [
      ...[1, 2, 3, 4, 5, 6].map((m) => monat(m, 250, 50, 1500, null)),
      ...[7, 8, 9, 10, 11, 12].map((m) => monat(m, 250, 50, 1500, 270)),
    ],
    2025,
  )

  it('rechnet die Jahresquote aus den Monatswerten, nicht aus der Ladung', () => {
    // (6 × 300 + 6 × 270) ÷ (12 × 1500) × 100 = 19,0 — die alte Formel ergab
    // Σ Heim ÷ Σ km = 3000 ÷ 18000 × 100 = 16,7.
    expect(jahr.emob_verbrauch_100km).toBeCloseTo(19.0, 6)
  })

  it('nennt „gemessen" nur, wenn jeder Monat mit km gemessen ist', () => {
    expect(jahr.emob_verbrauch_quelle).toBe('ladung')
    const alleGemessen = baueJahrAlsMonat(
      [monat(7, 250, 0, 1500, 270), monat(8, 250, 0, 1000, 180)],
      2025,
    )
    expect(alleGemessen.emob_verbrauch_quelle).toBe('gemessen')
    expect(alleGemessen.emob_verbrauch_100km).toBeCloseTo(18.0, 6)
  })

  it('führt „Ladung gesamt" als Summe von Heim + Extern, die Heimladung bleibt Heim', () => {
    expect(jahr.emob_ladung_gesamt_kwh).toBe(3600)
    expect(jahr.emob_ladung_kwh).toBe(3000)
  })
})
