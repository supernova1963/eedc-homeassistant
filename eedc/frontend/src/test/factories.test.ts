/**
 * Selbsttests der Fixture-Factories (Etappe E5 / M8).
 *
 * Der wichtigste Fall steht zuerst: **die Nullstellung darf nichts behaupten.**
 * Er ist der Wächter gegen den Rückfall, der die Factories wertlos machen
 * würde — jemand ergänzt „damit die Sicht etwas anzeigt" einen Default von
 * 300 kWh, und ab da behauptet jeder Test, der die Zahl nicht selbst gesetzt
 * hat, still eine erfundene Menge. Dieselbe Regel wie im Backend
 * (`backend/tests/factories.py`).
 */
import { describe, it, expect } from 'vitest'
import { aktuellerMonat, monatsZeile, tagWerte } from './factories'

/** Felder, die Identität oder Struktur tragen — keine gemessene Menge. */
const IDENTITAET = new Set([
  'anlage_id', 'anlage_name', 'jahr', 'monat', 'monat_name', 'datum',
  'aktualisiert_um', 'id', 'datenquelle', 'emob_verbrauch_quelle',
])

const nurMengen = (o: Record<string, unknown>) =>
  Object.entries(o).filter(([k]) => !IDENTITAET.has(k))

describe('Nullstellung — die Defaults behaupten nichts', () => {
  it.each([
    ['aktuellerMonat', aktuellerMonat(2025, 3) as unknown as Record<string, unknown>],
    ['monatsZeile', monatsZeile(2025, 3) as unknown as Record<string, unknown>],
    ['tagWerte', tagWerte('2025-03-01') as unknown as Record<string, unknown>],
  ])('%s: kein Feld trägt eine erfundene Zahl', (_name, obj) => {
    const erfunden = nurMengen(obj).filter(([, v]) => typeof v === 'number' && v !== 0)
    expect(erfunden).toEqual([])
  })

  it.each([
    ['aktuellerMonat', aktuellerMonat(2025, 3) as unknown as Record<string, unknown>],
    ['monatsZeile', monatsZeile(2025, 3) as unknown as Record<string, unknown>],
    ['tagWerte', tagWerte('2025-03-01') as unknown as Record<string, unknown>],
  ])('%s: kein Feld trägt einen erfundenen Text oder ein true', (_name, obj) => {
    const erfunden = nurMengen(obj).filter(
      ([, v]) => v === true || (typeof v === 'string' && v !== ''),
    )
    expect(erfunden).toEqual([])
  })

  it('emob_verbrauch_quelle steht auf „keine" — der Typ lässt dort kein null zu', () => {
    // 'gemessen' wäre die Behauptung, es habe eine Messung gegeben.
    expect(aktuellerMonat(2025, 3).emob_verbrauch_quelle).toBe('keine')
  })

  it('was der Typ null erlaubt, steht auf null — nicht auf 0', () => {
    // 0 hieße „nichts erzeugt", null heißt „nicht gemessen". Der Unterschied
    // ist im Produkt eine Anzeige-Entscheidung (— statt 0 kWh, #236).
    expect(aktuellerMonat(2025, 3).pv_erzeugung_kwh).toBeNull()
    expect(monatsZeile(2025, 3).pv_erzeugung_kwh).toBeNull()
    expect(tagWerte('2025-03-01').erzeugung).toBeNull()
  })
})

describe('Identität ist Parameter, kein Default', () => {
  it('aktuellerMonat trägt Jahr, Monat und den abgeleiteten Monatsnamen', () => {
    const d = aktuellerMonat(2025, 3)
    expect([d.jahr, d.monat, d.monat_name]).toEqual([2025, 3, 'März'])
  })

  it('monatsZeile trägt eine id — der Marker für „Monat MIT Zählerzeile"', () => {
    expect(monatsZeile(2025, 3).id).toBe(202503)
    // null ist die ganze Kennzeichnung eines Monats ohne Abschluss (N-121).
    expect(monatsZeile(2025, 3, { id: null }).id).toBeNull()
  })

  it('tagWerte trägt das übergebene Datum', () => {
    expect(tagWerte('2025-03-01').datum).toBe('2025-03-01')
  })

  it('Monat 0 = Jahres-Aggregat: der Name fällt auf die Ziffer zurück', () => {
    // Die Route liefert Jahres-Aggregate mit `monat: 0` und dem Jahr als Namen.
    // Die Factory erfindet dort keinen Monatsnamen — wer „2026" braucht,
    // übergibt ihn (so macht es JahrVergleichFenster.test.tsx).
    expect(aktuellerMonat(2026, 0).monat_name).toBe('0')
    expect(aktuellerMonat(2026, 0, { monat_name: '2026' }).monat_name).toBe('2026')
  })
})

describe('Der Override gewinnt', () => {
  it('setzt gezielt einzelne Felder, der Rest bleibt auf Nullstellung', () => {
    const d = aktuellerMonat(2025, 3, { pv_erzeugung_kwh: 412, hat_speicher: true })
    expect(d.pv_erzeugung_kwh).toBe(412)
    expect(d.hat_speicher).toBe(true)
    expect(d.einspeisung_kwh).toBeNull()
  })

  it('überschreibt auch die Identität, wenn ein Test das braucht', () => {
    expect(monatsZeile(2025, 3, { anlage_id: 7 }).anlage_id).toBe(7)
  })
})
