/**
 * Spalten je Verbrauchszähler (#377) — bis E6 ohne Test (M9).
 *
 * `lib/zaehlerSpalten.ts` erzeugt die Tabellenspalten der Zählerstände zur
 * Laufzeit, weil sie an der **Anlage** hängen, nicht am Produkt. Gemessen am
 * 2026-08-24: keine Testdatei importierte das Modul.
 *
 * Drei Zusagen stehen hier als Probe:
 *
 * * **Je Gerät eine Spalte, nie eine Sammelspalte** — ein Zählerstand ist eine
 *   Bestandsgröße und summiert sich über nichts (zwei Gaszähler mit 12.345 und
 *   8.900 ergeben nicht 21.245).
 * * **Wer nie abgelesen wurde, bekommt keine Spalte** — sie bestünde aus lauter
 *   „—" und behauptete, es gäbe dort etwas zu sehen.
 * * **Jede Spalte trägt die Einheit ihres Geräts**, mit `m³` als Rückfall.
 */
import { describe, it, expect } from 'vitest'
import { baueZaehlerSpalten, zaehlerInvestitionen, zaehlerMitStand } from './zaehlerSpalten'
import type { Investition } from '../types'

const inv = (
  id: number,
  bezeichnung: string,
  parameter: Record<string, unknown> | null = { kategorie: 'zaehler' },
  typ = 'sonstiges',
): Investition => ({ id, bezeichnung, typ, parameter } as unknown as Investition)

describe('zaehlerInvestitionen', () => {
  it('nimmt nur *Sonstiges* mit Zähler-Kategorie', () => {
    const liste = [
      inv(1, 'Gaszähler'),
      inv(2, 'Poolpumpe', { kategorie: 'verbraucher' }),
      inv(3, 'PV-String', { kategorie: 'zaehler' }, 'pv-module'),
      inv(4, 'Ohne Parameter', null),
    ]
    expect(zaehlerInvestitionen(liste).map((i) => i.id)).toEqual([1])
  })

  it('sortiert stabil nach Bezeichnung, deutsch', () => {
    const liste = [inv(1, 'Wasserzähler'), inv(2, 'Ölzähler'), inv(3, 'Gaszähler')]
    expect(zaehlerInvestitionen(liste).map((i) => i.bezeichnung))
      .toEqual(['Gaszähler', 'Ölzähler', 'Wasserzähler'])
  })

  it('liefert eine leere Liste, wenn es keine Zähler gibt', () => {
    expect(zaehlerInvestitionen([inv(1, 'Wallbox', { kategorie: 'verbraucher' })])).toEqual([])
  })
})

describe('zaehlerMitStand', () => {
  it('sammelt die IDs mit mindestens einem Stand', () => {
    const ids = zaehlerMitStand([
      { zaehler_stand: { '1': 100 } },
      { zaehler_stand: { '2': 250 } },
      { zaehler_stand: { '1': 120 } },
    ])
    expect([...ids].sort()).toEqual(['1', '2'])
  })

  it('eine gemessene NULL zaehlt als Stand', () => {
    // Ein frisch gesetzter Zähler steht auf 0 — das ist ein Wert, keine Luecke.
    expect(zaehlerMitStand([{ zaehler_stand: { '7': 0 } }]).has('7')).toBe(true)
  })

  it('null-Werte und fehlende Felder zaehlen nicht', () => {
    const ids = zaehlerMitStand([
      { zaehler_stand: { '1': null as unknown as number } },
      { zaehler_stand: null },
      {},
    ])
    expect(ids.size).toBe(0)
  })
})

describe('baueZaehlerSpalten', () => {
  it('liefert je Geraet EINE Spalte — keine Sammelspalte', () => {
    const spalten = baueZaehlerSpalten(
      [inv(1, 'Gaszähler'), inv(2, 'Wasserzähler')],
      new Set(['1', '2']),
    )
    expect(spalten).toHaveLength(2)
    expect(spalten.map((s) => s.label)).toEqual(['Gaszähler', 'Wasserzähler'])
    expect(new Set(spalten.map((s) => s.key)).size).toBe(2)
  })

  it('laesst Geraete OHNE jeden Stand weg', () => {
    const spalten = baueZaehlerSpalten(
      [inv(1, 'Gaszähler'), inv(2, 'Nie abgelesen')],
      new Set(['1']),
    )
    expect(spalten.map((s) => s.label)).toEqual(['Gaszähler'])
  })

  it('jede Spalte traegt die Einheit IHRES Geraets', () => {
    const spalten = baueZaehlerSpalten(
      [
        inv(1, 'Gaszähler', { kategorie: 'zaehler', zaehler_einheit: 'm³' }),
        inv(2, 'Wärmemenge', { kategorie: 'zaehler', zaehler_einheit: 'kWh' }),
      ],
      new Set(['1', '2']),
    )
    expect(spalten.map((s) => s.unit)).toEqual(['m³', 'kWh'])
  })

  it('ohne gepflegte Einheit greift der Default m³', () => {
    const [spalte] = baueZaehlerSpalten([inv(1, 'Gaszähler')], new Set(['1']))
    expect(spalte.unit).toBe('m³')
  })

  it('ein Zaehlerstand wird NICHT aggregiert', () => {
    // Bestandsgroesse: Σ ueber Geraete und Zeit ist bedeutungslos (#377).
    const [spalte] = baueZaehlerSpalten([inv(1, 'Gaszähler')], new Set(['1']))
    expect(spalte.aggregation).toBe('none')
    expect(spalte.higherIsBetter).toBeUndefined()
  })

  it('ohne Zaehler entstehen keine Spalten', () => {
    expect(baueZaehlerSpalten([], new Set())).toEqual([])
  })
})
