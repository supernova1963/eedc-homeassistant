/**
 * Die Ø-Preis-Kachel nennt die Herkunft ihrer Zahl (#412, 11.09.2026).
 *
 * Schwesterdatei: `MonatBilanz.test.tsx` (dieselbe Kachel-Fabrik).
 *
 * ⛔ **Warum das nötig wurde.** Bis 11.09.2026 kannte die Formel-Zeile zwei
 * Texte: „dynamischer Tarif" (wenn ein Ø gepflegt war) und sonst „Arbeitspreis
 * aus dem Strompreis-Tarif". Ein über HT/NT-Fenster gewichteter Preis lief
 * schon damals unter dem zweiten — falsch, aber folgenlos. Mit der neuen
 * **gemessenen** Stufe wären es drei Fälle unter zwei Namen geworden: Ein aus
 * Stundenpreisen gemittelter Wert hätte „Arbeitspreis aus dem Strompreis-Tarif"
 * über sich gehabt. Das ist eine Falschaussage, die der Bau selbst eingebaut
 * hätte (ADR-002/P4: die Antwort sagt, was sie ist).
 */
import { describe, it, expect } from 'vitest'
import { baueNetzKostenKpis } from './MonatBilanz'
import type { AktuellerMonatResponse } from '../api/aktuellerMonat'

const basis = (over: Partial<AktuellerMonatResponse> = {}): AktuellerMonatResponse =>
  ({
    netzbezug_kwh: 500,
    netzbezug_preis_cent: 34,
    netzbezug_arbeitspreis_kosten_euro: 170,
    netzbezug_durchschnittspreis_cent: null,
    ...over,
  } as unknown as AktuellerMonatResponse)

const preisKachel = (d: AktuellerMonatResponse) =>
  baueNetzKostenKpis(d).find((k) => k.title === 'Ø-Preis Netz')

describe('Ø-Preis Netz — die Formel nennt die Herkunft', () => {
  it('gemessen: sagt, dass die Stundenpreise gemittelt wurden', () => {
    const k = preisKachel(basis({
      netzbezug_preis_herkunft: 'gemessen',
      netzbezug_preis_abdeckung: 0.36,
      netzbezug_preis_cent: 22.4,
    }))

    expect(k?.formel).toContain('gemessenen Stundenpreise')
    expect(k?.formel).not.toContain('aus dem Strompreis-Tarif')
  })

  it('gemessen: nennt die Abdeckung, weil sie im laufenden Monat klein ist', () => {
    const k = preisKachel(basis({
      netzbezug_preis_herkunft: 'gemessen', netzbezug_preis_abdeckung: 0.36,
    }))

    expect(k?.formel).toContain('36 %')
  })

  it('gepflegt: nennt den Monatsabschluss als Quelle', () => {
    const k = preisKachel(basis({
      netzbezug_preis_herkunft: 'gepflegt',
      netzbezug_durchschnittspreis_cent: 26.5,
    }))

    expect(k?.formel).toContain('abgerechneter')
  })

  it('zeitfenster: wird nicht mehr als Tarif-Arbeitspreis ausgegeben', () => {
    // Der Fall, der schon vor #412 falsch beschriftet war.
    const k = preisKachel(basis({ netzbezug_preis_herkunft: 'zeitfenster' }))

    expect(k?.formel).toContain('HT/NT')
  })

  it('stamm: bleibt beim eingeführten Wortlaut', () => {
    const k = preisKachel(basis({ netzbezug_preis_herkunft: 'stamm' }))

    expect(k?.formel).toContain('Arbeitspreis aus dem Strompreis-Tarif')
  })

  it('N-655 Jahr: die gefaltete Herkunft „zeitfenster" ergibt dieselbe Formel wie der Monat', () => {
    // Bis 10.10.2026 trug die Jahresantwort kein Herkunftsfeld — die Kachel fiel auf den Tarif-Text zurück.
    const jahr = preisKachel(basis({ netzbezug_preis_herkunft: 'zeitfenster' }))
    const monat = preisKachel(basis({ netzbezug_preis_herkunft: 'zeitfenster', netzbezug_preis_effektiv_cent: 30 }))
    expect(jahr?.formel).toBe(monat?.formel)
    expect(jahr?.formel).not.toBe(preisKachel(basis({ netzbezug_preis_herkunft: 'stamm' }))?.formel)
  })

  it('N-655 Jahr: „gemischt" behauptet keine einzelne Stufe', () => {
    const k = preisKachel(basis({ netzbezug_preis_herkunft: 'gemischt' }))
    for (const einzel of ['gepflegt', 'zeitfenster', 'stamm'] as const) {
      expect(k?.formel).not.toBe(preisKachel(basis({ netzbezug_preis_herkunft: einzel }))?.formel)
    }
  })

  it('ohne Herkunft (alte Antwort) behauptet die Kachel keine', () => {
    // ⚠ Eine Antwort ohne das Feld darf nicht plötzlich „gemessen" behaupten —
    // der Client kann es nicht wissen.
    const k = preisKachel(basis())

    expect(k?.formel).toContain('Arbeitspreis aus dem Strompreis-Tarif')
  })
})

/**
 * ⭐ **Die Gegenrichtung, und sie fehlte** (17.09.2026, SOLL Flex-Tarife H-2).
 *
 * Die Prüfungen oben lesen ausschließlich `formel` — den **Satz**. Dass die
 * **Zahl** daneben dieselbe Herkunft hat, hat nie jemand geprüft, und genau
 * dort saß der Fehler: Die Kachel las `netzbezug_durchschnittspreis_cent ??
 * netzbezug_preis_cent`, also den gepflegten Ø, sonst den Tarif. Im laufenden
 * Monat ohne Abschluss stand deshalb der **Stammpreis** unter dem Satz „Ø
 * deiner gemessenen Stundenpreise" — und die Kosten daneben waren mit dem
 * gemessenen Ø gerechnet. Drei Zahlen, eine Kachel (OB73-gif zu #412).
 *
 * *Ein Prüfer, der nur die Beschriftung liest, bestätigt die Beschriftung.*
 */
describe('Ø-Preis Netz — die Kachel zeigt die Zahl, die die Formel beschreibt', () => {
  it('gemessen: zeigt den gemessenen Ø, nicht den Tarif-Arbeitspreis', () => {
    // Genau OB73-gifs Lage: September läuft, kein Abschluss, Stammpreis 31,5,
    // gemessener Ø 35,6.
    const k = preisKachel(basis({
      netzbezug_preis_herkunft: 'gemessen',
      netzbezug_preis_abdeckung: 0.55,
      netzbezug_preis_effektiv_cent: 35.6,
      netzbezug_preis_cent: 31.5,
      netzbezug_durchschnittspreis_cent: null,
    }))

    expect(k?.value).toContain('35,6')
    expect(k?.value).not.toContain('31,5')
  })

  it('gepflegt: der abgerechnete Ø steht in der Kachel', () => {
    const k = preisKachel(basis({
      netzbezug_preis_herkunft: 'gepflegt',
      netzbezug_preis_effektiv_cent: 26.5,
      netzbezug_durchschnittspreis_cent: 26.5,
      netzbezug_preis_cent: 31.5,
    }))

    expect(k?.value).toContain('26,5')
  })

  it('stamm: Tarifpreis und angezeigter Preis sind dieselbe Zahl', () => {
    // Die Regression (SOLL §10, Prüfstein 2): Wo nichts gemessen wird, bewegt
    // sich nichts.
    const k = preisKachel(basis({
      netzbezug_preis_herkunft: 'stamm',
      netzbezug_preis_effektiv_cent: 31.5,
      netzbezug_preis_cent: 31.5,
    }))

    expect(k?.value).toContain('31,5')
  })

  it('alte Antwort ohne das Feld: verhält sich wie vorher', () => {
    // ⚠ Rückfall-Kette, damit ein Client gegen eine ältere Antwort nicht leer
    // läuft — gepflegter Ø, sonst Tarif.
    const k = preisKachel(basis({
      netzbezug_durchschnittspreis_cent: 26.5,
      netzbezug_preis_cent: 31.5,
    }))

    expect(k?.value).toContain('26,5')
  })
})
