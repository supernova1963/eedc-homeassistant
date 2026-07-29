/**
 * TagBilanz — KPI-Bauer der Tages-Sicht.
 *
 * Schwerpunkt: die Kosten-Kacheln (R15-1) und ihre Sichtbarkeits-Regel.
 * „0 kWh aus dem Netz geladen" ist eine Aussage und bleibt sichtbar
 * (Rainer-PN 2026-07-25); ein fehlender Speicher blendet die Kachel aus.
 */
import { describe, it, expect } from 'vitest'
import { baueTagKpis } from './TagBilanz'
import type { TagWerte } from '../api/energie_profil'

const tag = (over: Partial<TagWerte> = {}): TagWerte => ({
  datum: '2026-07-25',
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
} as TagWerte)

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
})

describe('baueTagKpis — die beiden Eigenverbrauchs-Begriffe (F3)', () => {
  it('nennt den Tages-Wert „PV-Eigenverbrauch" und sagt „inkl. Speicherladung"', () => {
    // Der Tag rechnet PV − Einspeisung, der Kanon (Live/Monat/Jahr/ROI) den
    // PV-gedeckten Hausverbrauch. Zwei Größen, ein Name — das war der Befund.
    const kpis = baueTagKpis(tag(), null)
    expect(kachel(kpis, 'Eigenverbrauch')).toBeUndefined()
    const k = kachel(kpis, 'PV-Eigenverbrauch')!
    expect(k.value).toBe('2')
    expect(k.subtitle).toContain('inkl. Speicherladung')
    expect(k.formel).toContain('inkl. Speicherladung')
  })

  it('rechnet den PV-Eigenverbrauch aus PV − Einspeisung vor', () => {
    const k = kachel(baueTagKpis(tag({ erzeugung: 7, einspeisung: 5, eigenverbrauch: 2 }), null), 'PV-Eigenverbrauch')!
    expect(k.berechnung).toBe('7 − 5 kWh')
    expect(k.ergebnis).toBe('= 2 kWh')
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
