import { describe, it, expect } from 'vitest'
import { prepBkwJahresVerwendung } from './BkwJahresvergleich'
import { prepBkwMonate } from './BkwCharts'
import type { BkwMonatsWert } from '../../api/investitionen'

/** Ein Monat der bewerteten Reihe (`monatsreihe`, N-638) — die Form, die das Backend sendet. */
const mw = (jahr: number, monat: number, w: Partial<BkwMonatsWert>): BkwMonatsWert => ({
  jahr, monat, erzeugung_kwh: 0, eigenverbrauch_kwh: 0, eigenverbrauch_quelle: 'anteilig',
  einspeisung_kwh: 0, einspeisung_quelle: 'abgeleitet', speicher_ladung_kwh: 0, speicher_entladung_kwh: 0, ...w,
})

describe('prepBkwJahresVerwendung', () => {
  it('summiert Verwendung (EV/Einspeisung) je Jahr, chronologisch', () => {
    const daten = prepBkwJahresVerwendung([
      mw(2025, 1, { eigenverbrauch_kwh: 80, einspeisung_kwh: 20 }),
      mw(2025, 2, { eigenverbrauch_kwh: 70, einspeisung_kwh: 30 }),
      mw(2024, 12, { eigenverbrauch_kwh: 40, einspeisung_kwh: 60 }),
    ])
    expect(daten.map((d) => d.jahr)).toEqual([2024, 2025])
    const y2025 = daten[1]
    expect(y2025.eigenverbrauch).toBe(150)
    expect(y2025.einspeisung).toBe(50)
    expect(y2025.gesamt).toBe(200)
  })

  it('ein nicht bewertbarer Monat (null) trägt nichts bei, statt die Summe zu verfälschen', () => {
    const daten = prepBkwJahresVerwendung([
      mw(2026, 5, { erzeugung_kwh: 40, eigenverbrauch_kwh: 30, einspeisung_kwh: 10 }),
      mw(2026, 6, { erzeugung_kwh: 45.1, eigenverbrauch_kwh: null, eigenverbrauch_quelle: 'nicht_bewertbar',
        einspeisung_kwh: null, einspeisung_quelle: null }),
    ])
    expect(daten).toEqual([{ jahr: 2026, eigenverbrauch: 30, einspeisung: 10, gesamt: 40 }])
  })
})

describe('prepBkwMonate (N-638)', () => {
  it('Erzeugung kommt aus der Reihe — eine Zeile nur mit Erzeugung ist nicht mehr 0/0/0', () => {
    // BAU-N636-RALFZ.md Messung 2: `verbrauch_daten` nur mit `pv_erzeugung_kwh: 45.1` ergab 0/0/0.
    const [z] = prepBkwMonate([mw(2026, 6, { erzeugung_kwh: 45.1, eigenverbrauch_kwh: 31.6, einspeisung_kwh: 13.5 })])
    expect(z).toMatchObject({ name: 'Jun 26', erzeugung: 45.1, eigenverbrauch: 31.6, einspeisung: 13.5 })
  })

  it('nicht bewertbar bleibt null (Tabelle „—", Diagramm Lücke) — keine 0', () => {
    const [z] = prepBkwMonate([mw(2026, 6, { erzeugung_kwh: 45.1, eigenverbrauch_kwh: null,
      eigenverbrauch_quelle: 'nicht_bewertbar', einspeisung_kwh: null, einspeisung_quelle: null })])
    expect(z.erzeugung).toBe(45.1)
    expect(z.eigenverbrauch).toBeNull()
    expect(z.einspeisung).toBeNull()
  })

  it('reicht die BKW-eigenen Speicherfelder unverändert durch', () => {
    const [z] = prepBkwMonate([mw(2026, 6, { speicher_ladung_kwh: 4.2, speicher_entladung_kwh: 3.9 })])
    expect(z.speicher_ladung).toBe(4.2)
    expect(z.speicher_entladung).toBe(3.9)
  })
})
