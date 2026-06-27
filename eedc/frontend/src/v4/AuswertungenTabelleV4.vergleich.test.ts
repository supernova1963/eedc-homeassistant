/**
 * Tageswerte-Vergleich (Werte-Werkbank) — Bereichs-Ableitung + Ausrichtung.
 * Sichert zu: jedes Modus liefert ein gleich langes, korrekt ausgerichtetes
 * Vergleichsfenster (löst den alten „Tag-im-Monat"-Match ab, der nur bei
 * deckungsgleichem Einzelmonat griff). Steuerung (Gernot 2026-06-27):
 *  • Vorperiode      → gleich langes Fenster direkt davor, Positions-Ausrichtung.
 *  • Periode im Jahr → selber Spann ins gewählte Jahr, Kalender-Ausrichtung.
 */
import { describe, it, expect } from 'vitest'
import { tagVergleich, richteAus } from './AuswertungenTabelleV4'
import type { WerteZeile } from '../lib/werte'

const zeile = (datum: string): WerteZeile => {
  const [y, m, d] = datum.split('-').map(Number)
  return { id: datum, sortKey: y * 10000 + m * 100 + d, label: datum, vergleichKey: d, wert: () => null }
}

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
})
