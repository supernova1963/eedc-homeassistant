/**
 * JahrAggregat — Jahres-Preise sind verbrauchsgewichtet, nicht Monats-Mittel.
 *
 * Auslöser Forum simon42 #89667/67 (Algie): die Jahres-Kachel „Ø-Preis Netz" nannte
 * oben einen Preis, der zur eigenen Unterzeile („Σ kWh · Σ €") nicht passte. Ursache
 * war das ungewichtete Mittel der Monatspreise — ein teurer Winter mit viel Bezug
 * wog dort so viel wie ein billiger Sommer mit fast keinem.
 *
 * Geprüft wird die reine Aufbereitung (`baueJahrAlsMonat`), nicht die Darstellung.
 */
import { describe, it, expect } from 'vitest'
import type { AktuellerMonatResponse } from '../api/aktuellerMonat'
import { baueJahrAlsMonat } from './JahrAggregat'

const monat = (m: number, felder: Partial<AktuellerMonatResponse>): AktuellerMonatResponse => ({
  anlage_id: 1, anlage_name: 'Demo', jahr: 2025, monat: m, monat_name: String(m),
  aktualisiert_um: '', quellen: {},
  ...felder,
} as unknown as AktuellerMonatResponse)

describe('baueJahrAlsMonat — Tarif-Zeile', () => {
  it('gewichtet den Netzbezugspreis mit der bezogenen Menge', () => {
    const jahr = baueJahrAlsMonat([
      monat(1, { netzbezug_kwh: 400, netzbezug_preis_cent: 40 }),
      monat(7, { netzbezug_kwh: 100, netzbezug_preis_cent: 20 }),
    ], 2025)

    // (400 × 40 + 100 × 20) / 500 = 36 — das ungewichtete Mittel wäre 30 gewesen.
    expect(jahr.netzbezug_preis_cent).toBeCloseTo(36, 6)
    expect(jahr.netzbezug_kwh).toBe(500)
  })

  it('gewichtet die Einspeisevergütung mit der eingespeisten Menge', () => {
    const jahr = baueJahrAlsMonat([
      monat(1, { einspeisung_kwh: 50, einspeise_preis_cent: 8 }),
      monat(7, { einspeisung_kwh: 450, einspeise_preis_cent: 12 }),
    ], 2025)

    // (50 × 8 + 450 × 12) / 500 = 11,6 — ungewichtet wären es 10 gewesen.
    expect(jahr.einspeise_preis_cent).toBeCloseTo(11.6, 6)
  })

  it('lässt Monate ohne Menge aus beiden Summen — ein leerer Monat verdünnt nicht', () => {
    const jahr = baueJahrAlsMonat([
      monat(1, { netzbezug_kwh: 300, netzbezug_preis_cent: 30 }),
      monat(2, { netzbezug_kwh: null, netzbezug_preis_cent: 99 }),
    ], 2025)

    expect(jahr.netzbezug_preis_cent).toBeCloseTo(30, 6)
  })

  it('fällt ohne jede Menge auf das Monats-Mittel zurück statt die Kachel zu leeren', () => {
    const jahr = baueJahrAlsMonat([
      monat(1, { netzbezug_kwh: 0, netzbezug_preis_cent: 30 }),
      monat(2, { netzbezug_kwh: 0, netzbezug_preis_cent: 40 }),
    ], 2025)

    expect(jahr.netzbezug_preis_cent).toBeCloseTo(35, 6)
  })

  it('bevorzugt den mitgeschriebenen Ø-Bezugspreis vor dem Tarif-Arbeitspreis', () => {
    const jahr = baueJahrAlsMonat([
      monat(1, { netzbezug_kwh: 100, netzbezug_preis_cent: 30, netzbezug_durchschnittspreis_cent: 22 }),
      monat(2, { netzbezug_kwh: 100, netzbezug_preis_cent: 30, netzbezug_durchschnittspreis_cent: 26 }),
    ], 2025)

    expect(jahr.netzbezug_preis_cent).toBeCloseTo(24, 6)
    // Gesetzt ⇒ die Kachel beschriftet als dynamischen Tarif.
    expect(jahr.netzbezug_durchschnittspreis_cent).toBeCloseTo(24, 6)
  })

  it('lässt den Ø-Bezugspreis leer, wenn kein Monat einen trug', () => {
    const jahr = baueJahrAlsMonat([
      monat(1, { netzbezug_kwh: 100, netzbezug_preis_cent: 30 }),
    ], 2025)

    expect(jahr.netzbezug_durchschnittspreis_cent).toBeNull()
    expect(jahr.netzbezug_preis_cent).toBeCloseTo(30, 6)
  })
})
