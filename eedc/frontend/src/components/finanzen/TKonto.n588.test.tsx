/**
 * N-588 im Client — die Herleitung der Eigenverbrauchs-Ersparnis nennt die BEWERTETE Menge aus der Antwort.
 *
 * Seit N-588 bewertet das Backend den Eigenverbrauch ohne die Wandlungsverluste, wenn der Messpunkt-Vertrag hält
 * (`eigenverbrauch_ohne_verluste_kwh`). Stünde in der Rechenzeile weiter der Bilanz-Eigenverbrauch, ginge
 * „450 kWh × 30 ct = 124,20 €" nicht auf (Differenz Verluste × Preis). Der Client rechnet die Verluste nicht nach —
 * er setzt die Felder der Antwort ein (F13a: EV 450, Verluste 36 ⇒ 414 kWh).
 *
 * Schwesterdateien: backend/tests/test_pv_achse_matrix.py (F13a), TKonto.evpreis.test.tsx.
 */
import { describe, it, expect } from 'vitest'
import { baueTKonto } from './TKonto'
import { aktuellerMonat } from '../../test/factories'

const F13A = {
  eigenverbrauch_kwh: 450, eigenverbrauch_ohne_verluste_kwh: 414, wandlungsverluste_kwh: 36,
  ev_ersparnis_euro: 124.2, einspeise_erloes_euro: 14.4, einspeisung_kwh: 180,
  netzbezug_kwh: 72, netzbezug_kosten_euro: 21.6, netzbezug_preis_cent: 30, netzbezug_preis_effektiv_cent: 30,
  netto_ertrag_euro: 138.6,
}

const zeile = (over = {}) =>
  baueTKonto(aktuellerMonat(2026, 6, { ...F13A, ...over })).habenPosten.find((p) => p.label === 'Eigenverbrauch-Ersparnis')!

describe('N-588 — T-Konto: Herleitung mit dem Eigenverbrauch ohne Wandlungsverluste', () => {
  it('Verluste bewertet: „414 kWh (450 − 36 Verluste) × 30 ct"', () => {
    expect(zeile().berechnung).toBe('414,0 kWh (450,0 − 36,0 Verluste) × 30,00 ct/kWh')
  })

  it('Verluste NICHT bewertet (Grund gesetzt): die Menge ist der Eigenverbrauch, ohne Klammer', () => {
    expect(zeile({ eigenverbrauch_ohne_verluste_kwh: 450, verluste_grund: 'dc_speicher', ev_ersparnis_euro: 135 })
      .berechnung).toBe('450,0 kWh × 30,00 ct/kWh')
  })

  it('GEGENPROBE — ohne Verluste (ältere Antwort ohne das Feld) bleibt die Zeile wie bisher', () => {
    expect(zeile({ eigenverbrauch_ohne_verluste_kwh: undefined, wandlungsverluste_kwh: undefined, ev_ersparnis_euro: 135 })
      .berechnung).toBe('450,0 kWh × 30,00 ct/kWh')
  })
})
