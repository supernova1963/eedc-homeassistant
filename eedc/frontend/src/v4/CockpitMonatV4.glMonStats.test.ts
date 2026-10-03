/**
 * N-604 — „Ø gleicher Monat" in Cockpit → Monat: eine gemessene 0 zählt mit, die Ø-Autarkie ist paarweise.
 *
 * Bis 03.10.2026 warf `v > 0` eine 0-kWh-Einspeisung (Schnee, Volleinspeiser ohne Bezug) aus dem Mittel, und die
 * Ø-Autarkie war das Mittel der Monats-Prozente. Jetzt: `v != null`, und die Autarkie ist Σ EV ÷ Σ Gesamtverbrauch über
 * die Jahre, die BEIDE Werte tragen (R-Q, dieselbe Regel wie das Jahr im Backend). Nachmessung 03.10.: die Regel stand
 * im Code, aber ohne Probe.
 *
 * Schwesterdateien: backend/tests/test_ergebnis_jahr_portiert.py (R-Q im Jahr), test_n584_jahr_grundgesamtheit.py.
 */
import { describe, it, expect } from 'vitest'
import { gleicheMonatStats } from './CockpitMonatV4'
import { monatsZeile } from '../test/factories'

describe('gleicheMonatStats (N-604)', () => {
  const reihe = [
    monatsZeile(2023, 1, { einspeisung_kwh: 0, eigenverbrauch_kwh: 100, gesamtverbrauch_kwh: 400 }),
    monatsZeile(2024, 1, { einspeisung_kwh: 60, eigenverbrauch_kwh: 300, gesamtverbrauch_kwh: 600 }),
    // Ein Jahr ohne Gesamtverbrauch: zählt für EV, NICHT für die Quote.
    monatsZeile(2022, 1, { einspeisung_kwh: 30, eigenverbrauch_kwh: 500, gesamtverbrauch_kwh: undefined }),
    monatsZeile(2025, 1, { einspeisung_kwh: 999 }), // der angezeigte Monat selbst
  ]

  it('eine gemessene 0 kWh zählt im Mittel mit', () => {
    const s = gleicheMonatStats(reihe, { jahr: 2025, monat: 1 })!
    expect(s.einsp).toBeCloseTo((0 + 60 + 30) / 3, 6)  // mit `v > 0` wären es 45
    expect(s.count).toBe(3)
  })

  it('die Ø-Autarkie ist Σ EV ÷ Σ Gesamtverbrauch über die Jahre mit beiden Werten', () => {
    const s = gleicheMonatStats(reihe, { jahr: 2025, monat: 1 })!
    expect(s.autarkie).toBeCloseTo((100 + 300) / (400 + 600) * 100, 6)  // 40 %, nicht Ø(25 %, 50 %) = 37,5 %
  })
})
