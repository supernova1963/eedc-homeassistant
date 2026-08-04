/**
 * JahrSpeicherTabelle — die Aggregations-Regeln von #358 Phase 1.
 *
 * Der eigentliche Prüfgegenstand ist die **Auslastung**: sie darf nicht als
 * Mittelwert der Monats-Prozente entstehen. Genau deshalb liefert das Backend
 * die Basis (Kapazität × Tage) als eigenes, additives Feld.
 */
import { describe, it, expect } from 'vitest'
import {
  baueSpeicherZeilen, summiereSpeicher, auslastungAus, solarAnteil,
} from './JahrSpeicherTabelle'
import type { AktuellerMonatResponse } from '../api/aktuellerMonat'

function monat(m: number, werte: Partial<AktuellerMonatResponse> = {}): AktuellerMonatResponse {
  return {
    jahr: 2026, monat: m,
    speicher_ladung_kwh: null, speicher_entladung_kwh: null,
    speicher_ladung_netz_kwh: null, speicher_vollzyklen: null,
    speicher_auslastungs_basis_kwh: null, speicher_auslastung_prozent: null,
    speicher_ersparnis_euro: null,
    ...werte,
  } as unknown as AktuellerMonatResponse
}

describe('baueSpeicherZeilen', () => {
  it('lässt Monate ohne Speicher-Bewegung weg', () => {
    const zeilen = baueSpeicherZeilen([
      monat(1, { speicher_ladung_kwh: 100, speicher_entladung_kwh: 90 }),
      monat(2),
      monat(3, { speicher_entladung_kwh: 50 }),
    ])
    expect(zeilen.map((z) => z.monat)).toEqual([3, 1])  // absteigend, Regel 0a
  })
})

describe('Auslastung', () => {
  it('entsteht aus den SUMMEN, nicht aus gemittelten Prozenten', () => {
    // Januar: 124 von 310 = 40 %, Februar: 171 von 280 = 61,07 %.
    // Der arithmetische Mittelwert wäre 50,5 % — richtig sind 50,0 %.
    const zeilen = baueSpeicherZeilen([
      monat(1, { speicher_entladung_kwh: 124, speicher_ladung_kwh: 150,
                 speicher_auslastungs_basis_kwh: 310 }),
      monat(2, { speicher_entladung_kwh: 171, speicher_ladung_kwh: 200,
                 speicher_auslastungs_basis_kwh: 280 }),
    ])
    const summe = summiereSpeicher(zeilen)
    expect(summe.auslastungsBasis).toBe(590)
    expect(auslastungAus(summe)).toBeCloseTo(50.0, 1)
    expect(auslastungAus(summe)).not.toBeCloseTo(50.5, 1)
  })

  it('ist ohne Basis unbekannt, nicht 0', () => {
    const zeilen = baueSpeicherZeilen([
      monat(1, { speicher_entladung_kwh: 100, speicher_ladung_kwh: 120 }),
    ])
    expect(auslastungAus(summiereSpeicher(zeilen))).toBeNull()
  })
})

describe('Solar-Anteil', () => {
  it('rechnet den Netz-Rest heraus', () => {
    expect(solarAnteil(1000, 250)).toBeCloseTo(75, 1)
  })

  it('ist ohne erfasste Netzladung unbekannt statt 100 %', () => {
    // Eine Anlage, die die Netzladung gar nicht pflegt, hat nicht „0 % Netz" —
    // sie hat keine Angabe. 100 % wäre eine Behauptung (P4).
    expect(solarAnteil(1000, null)).toBeNull()
  })
})

describe('Summen', () => {
  it('halten null von 0 getrennt', () => {
    const zeilen = baueSpeicherZeilen([
      monat(1, { speicher_entladung_kwh: 100, speicher_ladung_kwh: 120 }),
    ])
    const s = summiereSpeicher(zeilen)
    // Weder Vollzyklen (keine Kapazität) noch Ersparnis (keine Finanz-Zeile)
    // liegen vor — beide bleiben null und erscheinen in der Tabelle als „—".
    expect(s.vollzyklen).toBeNull()
    expect(s.ersparnis).toBeNull()
    expect(s.entladung).toBe(100)
  })

  it('summiert Vollzyklen und Ersparnis, sobald sie vorliegen', () => {
    const zeilen = baueSpeicherZeilen([
      monat(1, { speicher_entladung_kwh: 100, speicher_ladung_kwh: 120,
                 speicher_vollzyklen: 2, speicher_ersparnis_euro: 22 }),
      monat(2, { speicher_entladung_kwh: 150, speicher_ladung_kwh: 180,
                 speicher_vollzyklen: 3, speicher_ersparnis_euro: 33 }),
    ])
    const s = summiereSpeicher(zeilen)
    expect(s.vollzyklen).toBe(5)
    expect(s.ersparnis).toBe(55)
  })
})
