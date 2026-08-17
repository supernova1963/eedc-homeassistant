import { describe, it, expect } from 'vitest'
import { baueJahrAlsMonat } from './JahrAggregat'
import type { AktuellerMonatResponse } from '../api/aktuellerMonat'

/**
 * N-252 — *Cockpit → Jahr* darf keinen unmöglichen Wirkungsgrad zeigen.
 *
 * **Warum es diese Datei gibt.** Beim Sprengsatz-Durchgang zu N-252 war dies
 * der einzige STUMME Fall: Der Client-Pfad ließ sich auf den alten Zustand
 * zurückdrehen — roher Quotient plus geratenes Etikett „fenster_lang" — und
 * **kein** Prüfer ging rot. Der Backend-Wächter deckt Python, der
 * Symmetrie-Test deckt den Spiegel; die Stelle, an der beide zusammenkommen,
 * deckte niemand.
 *
 * Der Schaden war nicht die Zahl allein: Unter 104 % stand der bestätigende
 * Satz „über das ganze Fenster gerechnet" — eine Falschmessung mit Gütesiegel.
 */

function monat(jahr: number, m: number, ladung: number, entladung: number): AktuellerMonatResponse {
  return {
    jahr,
    monat: m,
    speicher_ladung_kwh: ladung,
    speicher_entladung_kwh: entladung,
    hat_speicher: true,
  } as unknown as AktuellerMonatResponse
}

describe('Cockpit → Jahr: Speicher-Wirkungsgrad', () => {
  it('zeigt den plausiblen Jahreswert und nennt das lange Fenster', () => {
    const jahr = baueJahrAlsMonat(
      [monat(2026, 1, 100, 88), monat(2026, 2, 100, 90)],
      2026,
    )
    expect(jahr.speicher_wirkungsgrad_prozent).toBeCloseTo(89, 6)
    expect(jahr.speicher_wirkungsgrad_quelle).toBe('fenster_lang')
  })

  it('zeigt KEINEN Wert, wenn übers Jahr mehr entladen als geladen gebucht ist', () => {
    // Der Fall aus #281: „Ladung" nur mit der PV-Ladung gepflegt, die
    // Netzladung steht als zweiter Posten daneben. Über 100 % kann kein
    // Speicher — auch nicht über zwölf Monate.
    const jahr = baueJahrAlsMonat(
      [monat(2026, 1, 100, 110), monat(2026, 2, 100, 104)],
      2026,
    )
    expect(jahr.speicher_wirkungsgrad_prozent).toBeNull()
    expect(jahr.speicher_wirkungsgrad_quelle).toBe('nicht-ermittelbar')
  })

  it('nennt das Etikett NICHT, wenn gar keine Ladung gebucht ist', () => {
    const jahr = baueJahrAlsMonat([monat(2026, 1, 0, 0)], 2026)
    expect(jahr.speicher_wirkungsgrad_prozent).toBeNull()
    expect(jahr.speicher_wirkungsgrad_quelle).toBe('keine-ladung')
  })

  it('behandelt genau 100 % als möglich — die Grenze schließt ein', () => {
    const jahr = baueJahrAlsMonat([monat(2026, 1, 100, 100)], 2026)
    expect(jahr.speicher_wirkungsgrad_prozent).toBeCloseTo(100, 6)
    expect(jahr.speicher_wirkungsgrad_quelle).toBe('fenster_lang')
  })
})
