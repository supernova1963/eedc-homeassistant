/**
 * F-25 (#375 kingcap1, 2026-08-11) — die Übersicht liest den NEUESTEN Monat.
 *
 * Der Community-Server liefert `anlage.monatswerte` **absteigend**
 * (`eedc-community/backend/api/benchmark.py`: `order_by(jahr.desc(), monat.desc())`;
 * an der Prod-Box nachgemessen: erste Zeile 2026-06, letzte 2023-06). Die Übersicht
 * las den Monat als `[length - 1]` und zeigte damit den **ältesten** — im Melder-Bild
 * 100 % Autarkie im Cockpit gegen ~5 % im Radar.
 *
 * Die Proben füttern deshalb BEIDE Reihenfolgen: absteigend ist der reale Fall,
 * aufsteigend der Fall der zweiten, gleichnamigen Quelle (`/community/preview/{id}`).
 * Ein Helfer, der nur eine von beiden richtig behandelt, fällt hier durch.
 */
import { describe, it, expect } from 'vitest'
import { neuesterMonat, letzteMonate } from './CommunityUebersichtTeile'

type Zeile = { jahr: number; monat: number; autarkie_prozent: number }

// Winter zuerst erfasst (5 %), Sommer zuletzt (100 %) — die Konstellation des Melders.
const AUFSTEIGEND: Zeile[] = [
  { jahr: 2025, monat: 12, autarkie_prozent: 5 },
  { jahr: 2026, monat: 1, autarkie_prozent: 12 },
  { jahr: 2026, monat: 7, autarkie_prozent: 100 },
]
const ABSTEIGEND: Zeile[] = [...AUFSTEIGEND].reverse()

describe('neuesterMonat', () => {
  it('findet den jüngsten Monat in der absteigenden Server-Reihenfolge', () => {
    // Ohne den Fix stand hier die 5 aus 2025-12 (letztes Element der Liste).
    expect(neuesterMonat(ABSTEIGEND)).toEqual({ jahr: 2026, monat: 7, autarkie_prozent: 100 })
  })

  it('findet denselben Monat in aufsteigender Reihenfolge', () => {
    expect(neuesterMonat(AUFSTEIGEND)).toEqual({ jahr: 2026, monat: 7, autarkie_prozent: 100 })
  })

  it('sortiert über die Jahresgrenze, nicht nach Monatszahl', () => {
    // Dez 2025 hat die größere Monatszahl — das Jahr entscheidet.
    expect(neuesterMonat([
      { jahr: 2026, monat: 1, autarkie_prozent: 12 },
      { jahr: 2025, monat: 12, autarkie_prozent: 5 },
    ])).toMatchObject({ jahr: 2026, monat: 1 })
  })

  it('verträgt leere und fehlende Listen', () => {
    expect(neuesterMonat([])).toBeUndefined()
    expect(neuesterMonat(undefined)).toBeUndefined()
  })
})

describe('letzteMonate', () => {
  const zwoelf: Zeile[] = Array.from({ length: 14 }, (_, i) => ({
    jahr: 2025 + Math.floor(i / 12),
    monat: (i % 12) + 1,
    autarkie_prozent: i,
  }))

  it('nimmt aus der absteigenden Liste die JÜNGSTEN zwölf', () => {
    const gewaehlt = letzteMonate([...zwoelf].reverse(), 12)
    expect(gewaehlt).toHaveLength(12)
    // Die beiden ältesten (2025-01, 2025-02) fallen heraus, nicht die jüngsten.
    expect(gewaehlt[0]).toMatchObject({ jahr: 2025, monat: 3 })
    expect(gewaehlt[11]).toMatchObject({ jahr: 2026, monat: 2 })
  })

  it('liefert chronologisch aufsteigend, unabhängig von der Eingangs-Reihenfolge', () => {
    const ab = letzteMonate([...zwoelf].reverse(), 12)
    const auf = letzteMonate(zwoelf, 12)
    expect(ab).toEqual(auf)
  })

  it('ändert die Eingangsliste nicht', () => {
    const eingabe = [...ABSTEIGEND]
    letzteMonate(eingabe, 2)
    expect(eingabe).toEqual(ABSTEIGEND)
  })
})
