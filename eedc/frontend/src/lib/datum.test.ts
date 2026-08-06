import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { formatDatum, formatZeitraumKurz, jaNein, heuteIso, toIsoDatum, verschiebeIsoTage } from './datum'

// Drift-Gate (detLAN-Gegencheck 6, 2026-06-28): Runtime-Absicherung des Datums-/
// Boolean-Anzeige-SoT. `check-de-de.mjs` flaggt rohe ISO-Datums-Anzeigen statisch;
// dieser Test sichert das tatsächliche Format (TT.MM.JJJJ, TZ-robust, Ja/Nein).
describe('formatDatum (R1: de-DE TT.MM.JJJJ)', () => {
  it('reine Datums-ISO → TT.MM.JJJJ', () => {
    expect(formatDatum('2023-06-01')).toBe('01.06.2023')
    expect(formatDatum('2026-12-31')).toBe('31.12.2026')
  })
  it('TZ-robust: Datum kippt nicht auf den Vortag', () => {
    // ohne Mittag-Anker würde UTC-Mitternacht in DE-Zeit auf 31.05. kippen.
    expect(formatDatum('2023-06-01')).toBe('01.06.2023')
  })
  it('voller ISO-String mit Zeit → Datum', () => {
    expect(formatDatum('2023-06-01T08:30:00Z')).toBe('01.06.2023')
  })
  it('leer/null/undefined → Fallback —', () => {
    expect(formatDatum(null)).toBe('—')
    expect(formatDatum(undefined)).toBe('—')
    expect(formatDatum('')).toBe('—')
  })
})

describe('formatZeitraumKurz (#360: gemessener Connector-Zeitraum)', () => {
  it('gleicher Monat → Von-Tag verkürzt, Bis-Datum vollständig', () => {
    expect(formatZeitraumKurz('2025-07-28T14:03:00', '2025-07-30T09:12:00')).toBe('28.–30.07.2025')
  })
  it('gleiches Jahr, anderer Monat → Von mit Monat', () => {
    expect(formatZeitraumKurz('2025-06-28', '2025-07-03')).toBe('28.06.–03.07.2025')
  })
  it('Jahreswechsel → beide Daten vollständig', () => {
    expect(formatZeitraumKurz('2024-12-28', '2025-01-03')).toBe('28.12.2024–03.01.2025')
  })
  it('ohne/mit kaputtem Bis-Datum bleibt das Von-Datum allein', () => {
    expect(formatZeitraumKurz('2025-07-28', null)).toBe('28.07.2025')
    expect(formatZeitraumKurz('2025-07-28', 'kein-datum')).toBe('28.07.2025')
  })
  it('ohne Von-Datum → Fallback —', () => {
    expect(formatZeitraumKurz(null, '2025-07-30')).toBe('—')
  })
})

describe('jaNein (Boolean → Ja/Nein)', () => {
  it('true/false → Ja/Nein', () => {
    expect(jaNein(true)).toBe('Ja')
    expect(jaNein(false)).toBe('Nein')
  })
  it('null/undefined → Fallback —', () => {
    expect(jaNein(null)).toBe('—')
    expect(jaNein(undefined)).toBe('—')
  })
})

// ── F-5: Datums-Keys aus der lokalen Uhr, nicht aus UTC ──────────────────────
// Gemeldet von rapahl (06.08.2026, Screenshots um 00:40 und 01:15 Ortszeit):
// der Prognosen-Vergleich zeigte zwei Kalendertage mit identischen Werten in
// allen drei Quellenspalten. Ursache war `new Date().toISOString().slice(0,10)`
// — UTC, und damit zwischen 00:00 und 02:00 MESZ noch gestern.
//
// Die Uhr wird hier GESTELLT. Ohne das prüft ein Test dieser Art nur, ob er
// zufällig zwischen 00:00 und 02:00 läuft — und ist 22 von 24 Stunden grün,
// obwohl der Fehler drinsteckt. Genau deshalb haben die vorhandenen Tests ihn
// nie gesehen.
describe('heuteIso / toIsoDatum / verschiebeIsoTage (F-5)', () => {
  beforeEach(() => { vi.useFakeTimers() })
  afterEach(() => { vi.useRealTimers() })

  it('00:30 Ortszeit im Sommer: heute ist HEUTE, nicht der UTC-Vortag', () => {
    // 2026-08-06 00:30 MESZ = 2026-08-05 22:30 UTC.
    vi.setSystemTime(new Date('2026-08-05T22:30:00Z'))
    expect(new Date().toISOString().slice(0, 10)).toBe('2026-08-05')  // der alte Weg
    expect(heuteIso()).toBe('2026-08-06')                             // der richtige
  })

  it('00:30 Ortszeit im Winter: dieselbe Falle mit einer Stunde Versatz', () => {
    // 2026-12-15 00:30 MEZ = 2026-12-14 23:30 UTC.
    vi.setSystemTime(new Date('2026-12-14T23:30:00Z'))
    expect(new Date().toISOString().slice(0, 10)).toBe('2026-12-14')
    expect(heuteIso()).toBe('2026-12-15')
  })

  it('tagsüber sind beide Wege gleich — deshalb fiel es nie auf', () => {
    vi.setSystemTime(new Date('2026-08-06T10:00:00Z'))
    expect(heuteIso()).toBe(new Date().toISOString().slice(0, 10))
  })

  it('toIsoDatum liest die lokale Uhr des übergebenen Datums', () => {
    expect(toIsoDatum(new Date('2026-08-05T22:30:00Z'))).toBe('2026-08-06')
    expect(toIsoDatum(new Date('2026-08-06T10:00:00Z'))).toBe('2026-08-06')
  })

  it('verschiebeIsoTage rechnet über Monats- und Jahresgrenzen', () => {
    expect(verschiebeIsoTage('2026-08-06', 1)).toBe('2026-08-07')
    expect(verschiebeIsoTage('2026-08-31', 1)).toBe('2026-09-01')
    expect(verschiebeIsoTage('2026-01-01', -1)).toBe('2025-12-31')
    expect(verschiebeIsoTage('2026-08-06', 14)).toBe('2026-08-20')
  })

  it('verschiebeIsoTage überlebt die Sommerzeit-Umstellung', () => {
    // In der Nacht auf den 29.03.2026 fehlt eine Stunde, auf den 25.10. gibt es
    // eine doppelt. Ein Tageswechsel über +24 h würde hier kippen.
    expect(verschiebeIsoTage('2026-03-28', 1)).toBe('2026-03-29')
    expect(verschiebeIsoTage('2026-03-29', 1)).toBe('2026-03-30')
    expect(verschiebeIsoTage('2026-10-24', 1)).toBe('2026-10-25')
    expect(verschiebeIsoTage('2026-10-25', 1)).toBe('2026-10-26')
  })
})
