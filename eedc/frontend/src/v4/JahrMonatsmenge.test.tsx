/**
 * Cockpit/Jahr — welche Monate zählen zum Jahr? (Fund N-65, Paket P-12)
 *
 * Bis v4.0.6 galt „ein Monat zählt, wenn er eine aggregierte Zeile hat" (+ der
 * heutige). Eine `Monatsdaten`-Zeile entsteht aber erst beim **Monatsabschluss** —
 * ein längst gelaufener Monat ohne Abschluss fiel damit komplett aus der Jahreszahl.
 *
 * An der Box gemessen (Winterborn, 10.100.1.13, 2026-08-02):
 * `/monatsdaten/aggregiert/1` meldet für 2026 Jan–Jun, `/aktueller-monat` liefert für
 * Juli aber 1.843,25 kWh PV. Angezeigt waren 7.703 kWh statt 9.547 — knapp ein
 * Viertel der Jahresernte fehlte, und zwar ausgerechnet der stärkste Monat.
 *
 * Die Gegenrichtung ist genauso gemessen und wird hier mitgesichert: `/aktueller-monat`
 * beantwortet AUCH Monate vor der Inbetriebnahme (Januar 2023 → `soll_pv_kwh: 396,1`).
 * Ein blindes 1–12-Fanout hätte das SOLL aufgebläht und die SOLL-Erfüllung gedrückt.
 */
import { describe, it, expect } from 'vitest'
import {
  zuLadendeMonate, monatHatDaten, abgeschlosseneMonate, kennzahlenFensterAus, monatsFensterAus,
} from './JahrAggregat'
import type { AktuellerMonatResponse } from '../api/aktuellerMonat'
import { aktuellerMonat, monatsZeile } from '../test/factories'

const zeile = (jahr: number, monat: number) => monatsZeile(jahr, monat)
const jahresZeilen = (jahr: number, monate: number[]) => monate.map((m) => zeile(jahr, m))
const bis = (n: number) => Array.from({ length: n }, (_, i) => i + 1)

/** Winterborn wie an der Box: 2023 ab Juni, 2024/2025 voll, 2026 mit Zeilen bis Juni. */
const WINTERBORN = [
  ...jahresZeilen(2026, bis(6)),
  ...jahresZeilen(2025, bis(12)),
  ...jahresZeilen(2024, bis(12)),
  ...jahresZeilen(2023, [6, 7, 8, 9, 10, 11, 12]),
]
const AM_2_AUGUST = new Date(2026, 7, 2)

describe('zuLadendeMonate — die Monatsmenge eines Jahres', () => {
  it('laufendes Jahr: die Lücke zwischen letzter Zeile und heute kommt dazu', () => {
    // Das ist N-65: Juli hat Daten, aber keine Zeile — bisher fiel er heraus.
    expect(zuLadendeMonate(WINTERBORN, 2026, AM_2_AUGUST)).toEqual(bis(8))
  })

  it('mehrere offene Monate werden mitgefangen — es ist ein Intervall, keine Aufzählung', () => {
    // Gernot 2026-08-02: „es könnten ja auch mehrere fehlen". Zeilen nur bis März,
    // heute August ⇒ April–August sind offen und werden trotzdem gefragt.
    const rows = [...jahresZeilen(2026, bis(3)), ...jahresZeilen(2025, bis(12))]
    expect(zuLadendeMonate(rows, 2026, AM_2_AUGUST)).toEqual(bis(8))
  })

  it('Lücke MITTEN im Jahr wird geschlossen, nicht nur der Rand', () => {
    const rows = [...jahresZeilen(2026, [1, 2, 5, 6]), ...jahresZeilen(2025, bis(12))]
    expect(zuLadendeMonate(rows, 2026, AM_2_AUGUST)).toEqual(bis(8))
  })

  it('REGRESSION — abgeschlossenes Jahr: exakt dieselbe Menge wie bisher', () => {
    // Kein zusätzlicher Request für vergangene Jahre; die Ladezeit des
    // Umschaltpfads bleibt dort unberührt.
    expect(zuLadendeMonate(WINTERBORN, 2025, AM_2_AUGUST)).toEqual(bis(12))
    expect(zuLadendeMonate(WINTERBORN, 2024, AM_2_AUGUST)).toEqual(bis(12))
  })

  it('REGRESSION — Startjahr beginnt bei der Inbetriebnahme, nicht im Januar', () => {
    // 2023 lief ab Juni. Jan–Mai zu fragen wäre das blinde Fanout: der Endpoint
    // antwortete dort mit SOLL + Tarif und blähte die Jahres-Kennzahlen auf.
    expect(zuLadendeMonate(WINTERBORN, 2023, AM_2_AUGUST)).toEqual([6, 7, 8, 9, 10, 11, 12])
  })

  it('Jahr vor der Inbetriebnahme und künftiges Jahr ⇒ nichts zu laden', () => {
    expect(zuLadendeMonate(WINTERBORN, 2022, AM_2_AUGUST)).toEqual([])
    expect(zuLadendeMonate(WINTERBORN, 2027, AM_2_AUGUST)).toEqual([])
    expect(zuLadendeMonate([], 2026, AM_2_AUGUST)).toEqual([])
  })

  it('eine erfasste Zeile zählt immer — auch außerhalb des Intervalls', () => {
    // Nachtrag für einen künftigen Monat (Handeingabe): die Menge ist NIE kleiner
    // als die bisherige, sonst verschwände eine bereits angezeigte Zahl.
    const rows = [...jahresZeilen(2026, [...bis(6), 11]), ...jahresZeilen(2025, bis(12))]
    expect(zuLadendeMonate(rows, 2026, AM_2_AUGUST)).toEqual([...bis(8), 11])
  })

  it('Obermenge-Invariante über alle Jahre der Box-Fixture', () => {
    for (const jahr of [2023, 2024, 2025, 2026]) {
      const alt = [...new Set(WINTERBORN.filter((r) => r.jahr === jahr).map((r) => r.monat))]
      const neu = zuLadendeMonate(WINTERBORN, jahr, AM_2_AUGUST)
      for (const m of alt) expect(neu).toContain(m)
    }
  })
})

describe('monatHatDaten — Messung oder nur Stammdaten?', () => {
  const antwort = (felder: Partial<AktuellerMonatResponse>) =>
    aktuellerMonat(2023, 1, felder)

  it('Monat vor der Inbetriebnahme: SOLL + Preise + Kapazität sind KEINE Daten', () => {
    // 1:1 die Box-Antwort für Januar 2023 (Anlage lief ab Juni).
    expect(monatHatDaten(antwort({
      soll_pv_kwh: 396.1, netzbezug_preis_cent: 40, einspeise_preis_cent: 8.2,
      speicher_kapazitaet_kwh: 12.8,
    }))).toBe(false)
  })

  it('eine gemessene Menge genügt — auch 0, das ist eine Messung', () => {
    expect(monatHatDaten(antwort({ pv_erzeugung_kwh: 0 }))).toBe(true)
    expect(monatHatDaten(antwort({ netzbezug_kwh: 12.5 }))).toBe(true)
    // Auch ein Monat, in dem nur eine Komponente lief, zählt.
    expect(monatHatDaten(antwort({ wp_strom_kwh: 60 }))).toBe(true)
  })

  it('leere Antwort ⇒ kein Monat', () => {
    expect(monatHatDaten(antwort({}))).toBe(false)
  })
})

describe('abgeschlosseneMonate — der laufende Monat gehört in keinen Vergleich', () => {
  it('laufendes Jahr: der heutige Monat fällt raus', () => {
    expect(abgeschlosseneMonate(bis(8), 2026, AM_2_AUGUST)).toEqual(bis(7))
  })

  it('REGRESSION — abgeschlossenes Jahr: unverändert', () => {
    expect(abgeschlosseneMonate(bis(12), 2025, AM_2_AUGUST)).toEqual(bis(12))
  })

  it('Januar: die Grundgesamtheit ist leer, nicht der Dezember des Vorjahres', () => {
    expect(abgeschlosseneMonate([1], 2026, new Date(2026, 0, 15))).toEqual([])
  })
})

describe('kennzahlenFensterAus — der Unterschied wird benannt', () => {
  it('Kopfzahl umfasst mehr Monate als der Vergleich ⇒ Fenster steht dran', () => {
    expect(kennzahlenFensterAus(bis(8), bis(7))).toBe('Jan–Aug')
  })

  it('Dezember: ein VOLLES Fenster ist hier gerade erklärungsbedürftig', () => {
    // Die 12-Monats-Ausnahme von `monatsFensterAus` darf hier NICHT greifen —
    // Jan–Dez enthält den angefangenen Dezember, der Vergleich nur Jan–Nov.
    expect(kennzahlenFensterAus(bis(12), bis(11))).toBe('Jan–Dez')
    expect(monatsFensterAus(bis(12))).toBeNull()
  })

  it('REGRESSION — deckungsgleich ⇒ nichts zu sagen', () => {
    expect(kennzahlenFensterAus(bis(12), bis(12))).toBeNull()
    expect(kennzahlenFensterAus([1, 2, 4], [1, 2, 4])).toBeNull()
    expect(kennzahlenFensterAus([], [])).toBeNull()
  })

  it('Lücke im Jahr wird als unterbrochenes Fenster geschrieben', () => {
    expect(kennzahlenFensterAus([1, 2, 4, 5, 6, 7, 8], [1, 2, 4, 5, 6, 7])).toBe('Jan–Feb, Apr–Aug')
  })
})
