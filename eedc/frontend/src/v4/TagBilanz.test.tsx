/**
 * TagBilanz — KPI-Bauer der Tages-Sicht.
 *
 * Schwerpunkt: die Kosten-Kacheln (R15-1) und ihre Sichtbarkeits-Regel.
 * „0 kWh aus dem Netz geladen" ist eine Aussage und bleibt sichtbar
 * (Rainer-PN 2026-07-25); ein fehlender Speicher blendet die Kachel aus.
 */
import { describe, it, expect } from 'vitest'
import { baueTagKpis, tagesPreisFormel } from './TagBilanz'
import type { TagWerte } from '../api/energie_profil'
import { tagWerte } from '../test/factories'

const tag = (over: Partial<TagWerte> = {}) =>
  tagWerte('2026-07-25', {
    stunden_verfuegbar: 24,
    datenquelle: 'ha',
    erzeugung: 7, pv_anlage: 6, bkw: 1,
    eigenverbrauch: 2, einspeisung: 5, netzbezug: 0,
    gesamtverbrauch: 4, direktverbrauch: 2,
    autarkie: 98.9, evQuote: 30, spezErtrag: 0.5,
    speicher_ladung: 1, speicher_entladung: 0.9, speicher_effizienz: 90,
    wp_strom: null,
    einspeise_erloes: 0.4, ev_ersparnis: 0.45, netzbezug_kosten: 0,
    netto_ertrag: 0.85, netto_bilanz: 0.85,
    ...over,
  })

const kachel = (kpis: ReturnType<typeof baueTagKpis>, titel: string) =>
  kpis.find((k) => k.title === titel)

describe('baueTagKpis — Kosten-Kacheln', () => {
  it('zeigt „Batterieladung Netz" auch bei 0 kWh, Kosten „—" ohne Ladepreis', () => {
    const k = kachel(baueTagKpis(tag(), null, null, { kwh: 0, preis_cent: null }), 'Batterieladung Netz')!
    expect(k).toBeDefined()
    expect(k.value).toBe('—')
    expect(k.subtitle).toBe('0,0 kWh')
    expect(k.berechnung).toBeUndefined()
  })

  it('zeigt 0,00 € wenn ein Ladepreis bekannt ist, aber nichts geladen wurde', () => {
    const k = kachel(baueTagKpis(tag(), null, null, { kwh: 0, preis_cent: 22.5 }), 'Batterieladung Netz')!
    expect(k.value).toBe('0,00')
    expect(k.subtitle).toBe('0,0 kWh · Ø 22,5 ct/kWh')
  })

  it('rechnet bei echter Netzladung wie bisher', () => {
    const k = kachel(baueTagKpis(tag(), null, null, { kwh: 2.5, preis_cent: 22.5 }), 'Batterieladung Netz')!
    expect(k.value).toBe('0,56')
    expect(k.ergebnis).toBe('= 0,56 €')
  })

  it('ohne Speicher (kwh null / kein tagDetail) bleibt die Kachel aus', () => {
    expect(kachel(baueTagKpis(tag(), null, null, { kwh: null, preis_cent: null }), 'Batterieladung Netz')).toBeUndefined()
    expect(kachel(baueTagKpis(tag(), null, null, undefined), 'Batterieladung Netz')).toBeUndefined()
  })

  it('„Ø-Preis Netz" entfällt ohne Netzbezug — 0 ÷ 0 ist kein Preis', () => {
    expect(kachel(baueTagKpis(tag({ netzbezug: 0 }), null), 'Ø-Preis Netz')).toBeUndefined()
    const mitBezug = kachel(baueTagKpis(tag({ netzbezug: 4, netzbezug_kosten: 1.2 }), null), 'Ø-Preis Netz')!
    expect(mitBezug.value).toBe('30,0')
  })

  it('„Ø-Preis Netz" nimmt den Tarif, nicht den Quotienten zweier Anzeigewerte', () => {
    // Knallfrosch (T89667 #163): 0,19 kWh Netzbezug ⇒ die Kachel zeigte
    // 31,6 ct/kWh, während dieselbe Seite mit ~29,5 ct rechnete. Der Quotient
    // erbte die Rundung der beiden Zahlen, aus denen er gebildet wurde.
    const t = tag({ netzbezug: 0.19, netzbezug_kosten: 0.06 })
    expect(kachel(baueTagKpis(t, null), 'Ø-Preis Netz')!.value).toBe('31,6')
    const k = kachel(baueTagKpis(t, null, null, undefined, 29.53), 'Ø-Preis Netz')!
    expect(k.value).toBe('29,5')
    expect(k.formel).toContain('Netzbezugspreis des Tages')
    // Die Menge daneben bleibt die gemessene — nur der Preis kommt vom Tarif.
    expect(k.subtitle).toBe('0,2 kWh · 0,06 €')
  })
})

describe('baueTagKpis — ein Eigenverbrauch, dieselbe Formel wie Monat und Live (N-635)', () => {
  // Bis 05.10.2026 (F3, 29.07.) hieß die Kachel „PV-Eigenverbrauch · inkl.
  // Speicherladung" und rechnete „PV − Einspeisung" vor — der Tag hatte eine
  // andere Formel als Live/Monat/Jahr. Seit N-635 rechnet er Direktverbrauch +
  // Speicher-Entladung (Entscheid Gernot: umrechnen statt benennen).
  it('nennt den Tages-Wert „Eigenverbrauch", ohne „inkl. Speicherladung"', () => {
    const kpis = baueTagKpis(tag(), null)
    expect(kachel(kpis, 'PV-Eigenverbrauch')).toBeUndefined()
    const k = kachel(kpis, 'Eigenverbrauch')!
    expect(k.value).toBe('2')
    expect(k.subtitle).not.toContain('Speicherladung')
    expect(k.formel).toBe('Direktverbrauch + Speicher-Entladung')
  })

  it('rechnet mit Speicher (PV − Einspeisung − Ladung) + Entladung vor', () => {
    const k = kachel(baueTagKpis(tag({
      erzeugung: 18, einspeisung: 6, speicher_ladung: 3, speicher_entladung: 2, eigenverbrauch: 11,
    }), null), 'Eigenverbrauch')!
    expect(k.berechnung).toBe('(18 − 6 − 3) + 2 kWh')
    expect(k.ergebnis).toBe('= 11 kWh')
  })

  it('ohne Speicher-Bewegung bleibt der kurze Rechenweg PV − Einspeisung', () => {
    for (const ohne of [{ speicher_ladung: null, speicher_entladung: null }, { speicher_ladung: 0, speicher_entladung: 0 }]) {
      const k = kachel(baueTagKpis(tag({ erzeugung: 7, einspeisung: 5, eigenverbrauch: 2, ...ohne }), null), 'Eigenverbrauch')!
      expect(k.formel).toBe('PV-Erzeugung − Einspeisung')
      expect(k.berechnung).toBe('7 − 5 kWh')
      expect(k.ergebnis).toBe('= 2 kWh')
    }
  })
})

describe('baueTagKpis — Autarkie-Rechenweg passt zum Prozentwert', () => {
  it('rechnet mit (Gesamtverbrauch − Netzbezug), nicht mit dem Eigenverbrauch', () => {
    // N129: das Backend rechnet seit v4.0.2 mit dem netzunabhängig gedeckten
    // Verbrauch. Der alte Rechenweg „Eigenverbrauch ÷ Gesamtverbrauch" las sich
    // an realen Tagen als 111 % — ein Wert, den es nicht geben kann.
    const k = kachel(baueTagKpis(tag({ gesamtverbrauch: 11.3, netzbezug: 0.15, autarkie: 98.7, eigenverbrauch: 12.6 }), null), 'Autarkie')!
    expect(k.formel).toBe('(Gesamtverbrauch − Netzbezug) ÷ Gesamtverbrauch × 100')
    expect(k.berechnung).toBe('(11 − 0) ÷ 11 kWh')
    expect(k.ergebnis).toBe('= 98,7 %')
    // Der Rechenweg darf den angezeigten Wert nicht überschreiten können.
    expect(k.berechnung).not.toContain('13')
  })
})

describe('baueTagKpis — ohne erfasste PV wird nichts behauptet', () => {
  // Forum kaba-kakao (T89667 #109, 2026-08-07): PV nur als Anlagen-Aggregat
  // zugeordnet ⇒ die Tagesebene hat keinen PV-Wert. Vorher stand dort
  // „0 kWh · SOLL 40 kWh · 0 %" neben einem Eigenverbrauch von −25 kWh.
  const ohnePv = () => tag({
    erzeugung: null, eigenverbrauch: null, evQuote: null, spezErtrag: null,
    einspeisung: 25, netzbezug: 0, gesamtverbrauch: 0, direktverbrauch: 0,
  })

  it('zeigt „—" statt 0 kWh bei Erzeugung und Eigenverbrauch', () => {
    const kpis = baueTagKpis(ohnePv(), null)
    expect(kachel(kpis, 'PV-Erzeugung')!.value).toBe('—')
    expect(kachel(kpis, 'Eigenverbrauch')!.value).toBe('—')
    // Die gemessene Einspeisung bleibt sichtbar — sie ist kein Teil der Lücke.
    expect(kachel(kpis, 'Einspeisung')!.value).toBe('25')
  })

  it('nennt das SOLL, aber keine Erfüllung in Prozent', () => {
    const k = kachel(baueTagKpis(ohnePv(), null, 40), 'PV-Erzeugung')!
    expect(k.subtitle).toContain('SOLL 40 kWh')
    expect(k.subtitle).not.toContain('%')
  })

  it('lässt den Vortag weg, wenn dessen Erzeugung nicht erfasst ist', () => {
    const k = kachel(baueTagKpis(tag(), ohnePv()), 'PV-Erzeugung')!
    expect(k.subtitle ?? '').not.toContain('VT:')
  })
})

/**
 * ⭐ **Der Tag nennt die Herkunft seines Preises** (17.09.2026, SOLL Flex-Tarife
 * H-1, F2).
 *
 * Bis dahin stand über der Kachel pauschal „bei flexiblem Tarif der Monats-Ø" —
 * wahr, solange der Tag tatsächlich mit dem Monatswert rechnete. Seit dem
 * Entscheid *„Tage bleiben Messung, Monat bleibt Abrechnung"* kann dieselbe
 * Kachel vier verschiedene Quellen zeigen, und ein gemessener Tages-Ø sieht
 * sonst aus wie ein über den Monat verteilter Wert.
 */
describe('Ø-Preis Netz (Tag) — die Formel nennt die Herkunft', () => {
  const preisKachel = (herkunft: Parameters<typeof tagesPreisFormel>[0]) =>
    kachel(
      baueTagKpis(tag({ netzbezug: 4, netzbezug_kosten: 1.2 }), null, null, undefined, 30, herkunft),
      'Ø-Preis Netz',
    )!

  it('gemessen: nennt die Stundenpreise DIESES Tages', () => {
    expect(preisKachel('gemessen').formel).toContain('dieses Tages')
    expect(preisKachel('gemessen').formel).toContain('gemessenen')
  })

  it('abgerechnet: sagt „verteilt", nicht „gemessen"', () => {
    // ⚠ Der Kern von H-1: Ein über den Monat verteilter Wert darf nicht wie
    // eine Messung dieses Tages klingen.
    const f = preisKachel('abgerechnet').formel!
    expect(f).toContain('verteilt')
    expect(f).not.toContain('gemessen')
  })

  it('vertrag: bleibt beim Arbeitspreis', () => {
    expect(preisKachel('vertrag').formel).toContain('Arbeitspreis')
  })

  it('ohne Feld (alte Antwort) behauptet die Kachel keine Herkunft', () => {
    const f = preisKachel(undefined).formel!
    expect(f).not.toContain('gemessen')
    expect(f).not.toContain('verteilt')
  })
})
