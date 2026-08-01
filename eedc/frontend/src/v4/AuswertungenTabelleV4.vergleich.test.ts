/**
 * Vergleich der Werte-Werkbank — Bereichs-Ableitung + Ausrichtung, je Granularität.
 *
 * Tage: jeder Modus liefert ein gleich langes, korrekt ausgerichtetes Vergleichs-
 * fenster (löst den alten „Tag-im-Monat"-Match ab, der nur bei deckungsgleichem
 * Einzelmonat griff). Steuerung (Gernot 2026-06-27):
 *  • Vorperiode      → gleich langes Fenster direkt davor, Positions-Ausrichtung.
 *  • Periode im Jahr → selber Spann ins gewählte Jahr, Kalender-Ausrichtung.
 *
 * Monate: Vergleichsfenster = Zeitraum − 1 Jahr; über „Alle Jahre" liegen darin
 * mehrere Jahrgänge desselben Monats. Jede Zeile muss ihr ECHTES Vorjahr finden
 * (PN 90204, Rainer) — vorher erbte sie den jüngsten Jahrgang, Dez 2025 im
 * Extremfall sich selbst.
 */
import { describe, it, expect } from 'vitest'
import { tagVergleich, richteAus, monatsFenster } from './AuswertungenTabelleV4'
import { richteMonateAus, vergleichLookup, type WerteZeile } from '../lib/werte'

const zeile = (datum: string): WerteZeile => {
  const [y, m, d] = datum.split('-').map(Number)
  const key = y * 10000 + m * 100 + d
  return { id: datum, sortKey: key, label: datum, zeitLinks: '', zeitRechts: datum, vergleichKey: key, wert: () => null }
}

const mZeile = (jahr: number, monat: number, v: number | null = null): WerteZeile => ({
  id: `${jahr}-${monat}`, sortKey: jahr * 100 + monat, label: `${monat}/${jahr}`,
  zeitLinks: String(monat), zeitRechts: String(jahr), vergleichKey: jahr * 100 + monat, wert: () => v,
})

describe('tagVergleich — Bereich + Ausrichtung je Modus', () => {
  it('vorperiode: gleich langes Fenster direkt davor, Positions-Ausrichtung', () => {
    const v = tagVergleich('vorperiode', '2026-06-01', '2026-06-30', 0)!
    expect(v.align).toBe('position')
    expect(v.bis).toBe('2026-05-31')        // Tag vor Primär-Start
    expect(v.von).toBe('2026-05-02')        // 30 Tage lang (wie Primär)
  })
  it('periodeImJahr: selber Spann ins gewählte Jahr, Kalender-Ausrichtung', () => {
    const v = tagVergleich('periodeImJahr', '2026-06-01', '2026-06-30', 2024)!
    expect(v.align).toBe('kalender')
    expect(v.von).toBe('2024-06-01')
    expect(v.bis).toBe('2024-06-30')
    expect(v.vor!('2024-06-05')).toBe('2026-06-05') // bildet vorwärts auf Primärtag ab
  })
  it('periodeImJahr: selbes Jahr → kein Vergleich (null)', () => {
    expect(tagVergleich('periodeImJahr', '2026-06-01', '2026-06-30', 2026)).toBeNull()
  })
  it('ohne von/bis → null', () => {
    expect(tagVergleich('vorperiode', '', '', 0)).toBeNull()
  })
})

describe('richteAus — Re-Keying', () => {
  it('position: chronologischer Index als Match-Key (Zeile i ↔ i)', () => {
    const vgl = tagVergleich('vorperiode', '2026-06-01', '2026-06-02', 0)
    const { primZeilen, vglZeilen } = richteAus(
      [zeile('2026-06-02'), zeile('2026-06-01')], [zeile('2026-05-31'), zeile('2026-05-30')], vgl,
    )
    expect(primZeilen.map((z) => z.vergleichKey)).toEqual([0, 1]) // nach sortKey sortiert
    expect(vglZeilen!.map((z) => z.vergleichKey)).toEqual([0, 1])
  })
  it('kalender (periodeImJahr): Vergleich wird vorwärts auf den Primärtag abgebildet', () => {
    const vgl = tagVergleich('periodeImJahr', '2026-06-01', '2026-06-30', 2024)
    const { primZeilen, vglZeilen } = richteAus([zeile('2026-06-05')], [zeile('2024-06-05')], vgl)
    expect(primZeilen[0].vergleichKey).toBe(20260605)
    expect(vglZeilen![0].vergleichKey).toBe(20260605) // == Primär-Key → matcht
  })
  it('kalender: gleicher Tag-im-Monat aus einem anderen Monat matcht NICHT mehr', () => {
    const vgl = tagVergleich('periodeImJahr', '2026-06-01', '2026-06-30', 2024)
    const { primZeilen, vglZeilen } = richteAus([zeile('2026-06-05')], [zeile('2024-07-05')], vgl)
    expect(vglZeilen![0].vergleichKey).not.toBe(primZeilen[0].vergleichKey)
  })
})

describe('Monats-Block: Fenster + Jahres-Ausrichtung (PN 90204)', () => {
  // Datenbestand wie auf 10.100.1.13: Beginn Juni 2023, aktuell Juni 2026.
  const bestand = [
    ...Array.from({ length: 7 }, (_, i) => ({ jahr: 2023, monat: 6 + i })),
    ...Array.from({ length: 12 }, (_, i) => ({ jahr: 2024, monat: 1 + i })),
    ...Array.from({ length: 12 }, (_, i) => ({ jahr: 2025, monat: 1 + i })),
    ...Array.from({ length: 6 }, (_, i) => ({ jahr: 2026, monat: 1 + i })),
  ]

  it('„Alle Jahre": Vergleichsfenster ist der Zeitraum minus ein Jahr', () => {
    const { prim, vergleich } = monatsFenster(bestand, '2023-01', '2026-12')
    expect(prim).toHaveLength(37)
    // Fenster 2022-01..2025-12 → alles außer den sechs Monaten aus 2026.
    expect(vergleich).toHaveLength(31)
    expect(vergleich.some((r) => r.jahr === 2026)).toBe(false)
  })

  it('Einzeljahr: Primär 2026, Vergleich 2025', () => {
    const { prim, vergleich } = monatsFenster(bestand, '2026-01', '2026-12')
    expect(prim.every((r) => r.jahr === 2026)).toBe(true)
    expect(vergleich.every((r) => r.jahr === 2025)).toBe(true)
  })

  it('mehrjährig: jede Zeile findet ihr echtes Vorjahr, nicht den jüngsten Jahrgang', () => {
    // Dez 2024 = 227,9 · Dez 2025 = 432,7 (Werte der Reproduktion).
    const vergleichsFenster = richteMonateAus([mZeile(2024, 12, 227.9), mZeile(2025, 12, 432.7)])!
    const lookup = vergleichLookup(vergleichsFenster)
    expect(lookup.get(mZeile(2025, 12).vergleichKey)!.wert('erzeugung')).toBe(227.9)
    expect(lookup.get(mZeile(2026, 12).vergleichKey)!.wert('erzeugung')).toBe(432.7)
  })

  it('fehlendes Vorjahr: kein Treffer statt gespiegeltem Wert (Datenbeginn 06/2023)', () => {
    const vergleichsFenster = richteMonateAus([mZeile(2023, 12, 227.9)])!
    const lookup = vergleichLookup(vergleichsFenster)
    expect(lookup.get(mZeile(2023, 12).vergleichKey)).toBeUndefined() // NICHT sich selbst
    expect(lookup.get(mZeile(2024, 3).vergleichKey)).toBeUndefined()  // 03/2023 gibt es nicht
  })
})
