/**
 * Monats-Lücken-Ableitung (Monatsabschluss-V4 §7, V-b) — die EINE
 * Vollständigkeits-Quelle für Tabellen-Färbung + „nächster offener Monat"-Sprung.
 * Kern-Invariante: Sprung == frühester fehlender Monat aus DERSELBEN Ableitung
 * (nicht die naive Backend-„letzter+1"-Logik).
 */
import { describe, it, expect } from 'vitest'
import {
  monatIndex,
  ausMonatIndex,
  ermittleStartAnker,
  ermittleFehlendeMonate,
  naechsterOffenerMonat,
  type MonatRef,
} from './monatsLuecken'

const M = (jahr: number, monat: number): MonatRef => ({ jahr, monat })

describe('monatIndex / ausMonatIndex', () => {
  it('ist umkehrbar und ordnet chronologisch', () => {
    expect(monatIndex(2026, 1)).toBeLessThan(monatIndex(2026, 2))
    expect(monatIndex(2025, 12) + 1).toBe(monatIndex(2026, 1)) // Jahresgrenze
    expect(ausMonatIndex(monatIndex(2024, 7))).toEqual(M(2024, 7))
  })
})

describe('ermittleStartAnker', () => {
  it('nimmt das Anlage-Installationsdatum — es schlägt jedes Geräte-Datum', () => {
    expect(
      ermittleStartAnker({
        anlageInstallationsdatum: '2022-04-01',
        erzeugerAnschaffungsdaten: ['2023-06-01'],
        vorhandene: [M(2024, 1)],
      }),
    ).toEqual(M(2022, 4))
  })

  it('fällt auf den ältesten ERZEUGER zurück, wenn die Anlage kein Datum trägt', () => {
    expect(
      ermittleStartAnker({
        erzeugerAnschaffungsdaten: ['2023-12-01', '2023-06-01', null],
        vorhandene: [M(2024, 1)],
      }),
    ).toEqual(M(2023, 6))
  })

  it('lässt ein Gerät, das älter ist als die Anlage, den Anker NICHT ziehen (N-243)', () => {
    // fridolin22 (Forum T77723 #773): E-Auto von 2017 an einer Anlage von 2022 —
    // Basisdaten wurden ab 2017 verlangt, er hat das Auto umdatiert und dessen
    // echte Historie verloren. Nicht-Erzeuger erreichen die Ableitung nicht mehr.
    expect(
      ermittleStartAnker({
        anlageInstallationsdatum: '2022-04-01',
        erzeugerAnschaffungsdaten: [],
        vorhandene: [M(2022, 5)],
      }),
    ).toEqual(M(2022, 4))
  })

  it('fällt zuletzt auf die früheste vorhandene Datenzeile zurück', () => {
    expect(
      ermittleStartAnker({
        erzeugerAnschaffungsdaten: [],
        vorhandene: [M(2024, 5), M(2024, 3), M(2024, 9)],
      }),
    ).toEqual(M(2024, 3))
  })

  it('gibt null, wenn keine Quelle greift', () => {
    expect(ermittleStartAnker({ erzeugerAnschaffungsdaten: [], vorhandene: [] })).toBeNull()
  })
})

describe('ermittleFehlendeMonate', () => {
  it('findet innere Lücken (Demo-Fall: Jan–Mär 2026 fehlen)', () => {
    // Bereich 2023/06 … 2026/06 (heute=2026/07), alles vorhanden außer 3 Monate.
    const alle: MonatRef[] = []
    for (let i = monatIndex(2023, 6); i <= monatIndex(2026, 6); i++) alle.push(ausMonatIndex(i))
    const vorhandene = alle.filter(
      (m) => !(m.jahr === 2026 && [1, 2, 3].includes(m.monat)),
    )
    const fehlend = ermittleFehlendeMonate({
      vorhandene,
      start: M(2023, 6),
      heute: M(2026, 7),
    })
    expect(fehlend).toEqual([M(2026, 1), M(2026, 2), M(2026, 3)])
  })

  it('schließt den laufenden Monat aus (heute nicht abgeschlossen)', () => {
    const fehlend = ermittleFehlendeMonate({
      vorhandene: [M(2026, 5)],
      start: M(2026, 5),
      heute: M(2026, 7),
    })
    // Bereich 2026/05 … 2026/06 → nur Juni fehlt, Juli (heute) NICHT.
    expect(fehlend).toEqual([M(2026, 6)])
  })

  it('findet nachlaufende Lücken (letzter Monat weit zurück)', () => {
    const fehlend = ermittleFehlendeMonate({
      vorhandene: [M(2026, 3)],
      start: M(2026, 3),
      heute: M(2026, 7),
    })
    expect(fehlend).toEqual([M(2026, 4), M(2026, 5), M(2026, 6)])
  })

  it('ist leer bei lückenlosem Bereich', () => {
    expect(
      ermittleFehlendeMonate({
        vorhandene: [M(2026, 4), M(2026, 5)],
        start: M(2026, 4),
        heute: M(2026, 6),
      }),
    ).toEqual([])
  })

  it('ist leer ohne Anker', () => {
    expect(
      ermittleFehlendeMonate({ vorhandene: [M(2026, 1)], start: null, heute: M(2026, 7) }),
    ).toEqual([])
  })
})

describe('naechsterOffenerMonat (== frühester fehlender, EINE Quelle)', () => {
  it('liefert die früheste innere Lücke — nicht letzter+1', () => {
    // Naive Backend-Logik würde auf 2026/07 (letzter+1) zielen; wir wollen Jan 2026.
    const alle: MonatRef[] = []
    for (let i = monatIndex(2023, 6); i <= monatIndex(2026, 6); i++) alle.push(ausMonatIndex(i))
    const vorhandene = alle.filter((m) => !(m.jahr === 2026 && [1, 2, 3].includes(m.monat)))
    expect(
      naechsterOffenerMonat({ vorhandene, start: M(2023, 6), heute: M(2026, 7) }),
    ).toEqual(M(2026, 1))
  })

  it('ist null bei lückenlosem Bereich', () => {
    expect(
      naechsterOffenerMonat({
        vorhandene: [M(2026, 4), M(2026, 5)],
        start: M(2026, 4),
        heute: M(2026, 6),
      }),
    ).toBeNull()
  })
})
