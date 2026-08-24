import { describe, it, expect } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import { baueMonatKpis, MonatBilanz } from './MonatBilanz'
import type { AktuellerMonatResponse } from '../api/aktuellerMonat'
import { aktuellerMonat, monatsZeile } from '../test/factories'

// baueMonatKpis liest nur eine Handvoll Felder — die übrigen bleiben auf
// Nullstellung, statt hier von Hand aufgezählt zu werden.
const d = (over: Partial<AktuellerMonatResponse> = {}) =>
  aktuellerMonat(2026, 8, {
    pv_erzeugung_kwh: 412, einspeisung_kwh: 189, netzbezug_kwh: 143,
    eigenverbrauch_kwh: 223, gesamtverbrauch_kwh: 366,
    autarkie_prozent: 61, eigenverbrauch_quote_prozent: 54,
    direktverbrauch_kwh: 180,
    netto_ertrag_euro: 128, soll_pv_kwh: 450,
    ...over,
  })

const vm = monatsZeile(2025, 8, {
  pv_erzeugung_kwh: 380, autarkie_prozent: 58, eigenverbrauch_kwh: 210,
  einspeisung_kwh: 170, netzbezug_kwh: 150,
})

describe('baueMonatKpis', () => {
  it('liefert 5 Energie-Cards + Netto-Ertrag + Monatsergebnis (7)', () => {
    const k = baueMonatKpis(d(), vm)
    expect(k.map((x) => x.title)).toEqual([
      'PV-Erzeugung', 'Autarkie', 'Eigenverbrauch', 'Einspeisung', 'Netzbezug', 'Netto-Ertrag', 'Monatsergebnis',
    ])
  })

  it('Monatsergebnis = Gesamt-Nettoertrag − Betriebskosten + Sonstiges (nach BK)', () => {
    const me = baueMonatKpis(d({ gesamtnettoertrag_euro: 150, betriebskosten_anteilig_euro: 30, sonstige_netto_euro: 5 }), vm)
      .find((x) => x.title === 'Monatsergebnis')!
    expect(me.unit).toBe('€')
    expect(me.value).toBe('125,00') // 150 − 30 + 5
    expect(me.subtitle).toBe('nach Betriebskosten')
  })

  it('Monatsergebnis bleibt — wenn Gesamt-Nettoertrag fehlt', () => {
    const me = baueMonatKpis(d({ gesamtnettoertrag_euro: null }), vm).find((x) => x.title === 'Monatsergebnis')!
    expect(me.value).toBe('—')
  })

  it('PV-Card trägt SOLL-Annotation (O2) statt VM, wenn SOLL vorhanden', () => {
    const pv = baueMonatKpis(d(), vm)[0]
    expect(pv.subtitle).toMatch(/SOLL 450 kWh · 92 %/) // 412/450 = 91,6 → 92
  })

  it('ohne SOLL fällt die PV-Card auf den Vormonat zurück', () => {
    const pv = baueMonatKpis(d({ soll_pv_kwh: null }), vm)[0]
    expect(pv.subtitle).toMatch(/VM: 380 kWh/)
  })

  it('andere Energie-Cards zeigen den Vormonat in der Zweitzeile', () => {
    const k = baueMonatKpis(d(), vm)
    expect(k.find((x) => x.title === 'Einspeisung')?.subtitle).toMatch(/VM: 170 kWh/)
    expect(k.find((x) => x.title === 'Netzbezug')?.subtitle).toMatch(/VM: 150 kWh/)
  })

  it('Netto-Ertrag in € ohne Vergleich', () => {
    const ne = baueMonatKpis(d(), vm).find((x) => x.title === 'Netto-Ertrag')!
    expect(ne.unit).toBe('€')
    expect(ne.value).toBe('128,00')
  })

  // M1-Wiederherstellung: PR Ø des Monats als neutrale Kachel, nur wenn gesetzt.
  it('fügt PR-Ø-Kachel hinzu, wenn prAvg gesetzt', () => {
    const pr = baueMonatKpis(d(), vm, 0.86).find((x) => x.title === 'Performance Ratio')!
    expect(pr.value).toBe('0,86')
    expect(pr.subtitle).toBe('Monats-Ø')
  })

  it('ohne prAvg (null/undefined) keine PR-Kachel', () => {
    expect(baueMonatKpis(d(), vm, null).find((x) => x.title === 'Performance Ratio')).toBeUndefined()
    expect(baueMonatKpis(d(), vm).find((x) => x.title === 'Performance Ratio')).toBeUndefined()
  })
})

describe('MonatBilanz — Mobil-Ansicht (gestapelte Karten < sm)', () => {
  it('rendert VM-Vergleichschips statt Tabellenspalten', () => {
    render(<MonatBilanz d={d()} vm={vm} glMonStats={null} monatName="Mai" />)
    // Pro Kennzahl ein „VM …"-Chip (gestapelte Mobil-Karten, immer im DOM).
    expect(screen.getAllByText(/^VM\b/).length).toBeGreaterThan(0)
  })

  it('zeigt die Direktverbrauch-Zeile (günstigster Verbrauch)', () => {
    render(<MonatBilanz d={d()} vm={vm} glMonStats={null} monatName="Mai" />)
    expect(screen.getAllByText('Direktverbrauch').length).toBeGreaterThan(0)
  })
})

describe('MonatBilanz — PV-Verteilung (O3-Revision: Balken wie IST)', () => {
  it('rendert EV/Einspeisung-Balken mit Prozent aus PV-Erzeugung', () => {
    render(<MonatBilanz d={d()} vm={vm} glMonStats={null} monatName="Mai" />)
    expect(screen.getByText('PV-Verteilung')).toBeInTheDocument()
    // VerteilungsBalken: Label · Wert kWh · % (Anteil an EV+Einspeisung = 223+189 = 412)
    expect(screen.getByText('Eigenverbr.')).toBeInTheDocument()
    expect(screen.getByText('223 kWh · 54 %')).toBeInTheDocument()
    expect(screen.getByText('189 kWh · 46 %')).toBeInTheDocument()
  })

  it('ohne PV-Erzeugung kein Verteilungs-Block', () => {
    render(<MonatBilanz d={d({ pv_erzeugung_kwh: 0 })} vm={vm} glMonStats={null} monatName="Mai" />)
    expect(screen.queryByText('PV-Verteilung')).not.toBeInTheDocument()
  })

  it('PV-Geräte-Hinweis bei mehreren Strings + WR', () => {
    render(<MonatBilanz d={d({ komponenten_geraete: { 'pv-module': ['Süddach', 'Ostdach', 'Westdach'], 'wechselrichter': ['Fronius'] } })} vm={vm} glMonStats={null} monatName="Mai" />)
    expect(screen.getByText(/PV-Erzeugung aus:/)).toBeInTheDocument()
    expect(screen.getByText(/Süddach · Ostdach · Westdach · Fronius/)).toBeInTheDocument()
  })

  it('PV-Geräte-Hinweis aus bei nur einem Gerät', () => {
    render(<MonatBilanz d={d({ komponenten_geraete: { 'pv-module': ['Süddach'] } })} vm={vm} glMonStats={null} monatName="Mai" />)
    expect(screen.queryByText(/PV-Erzeugung aus/)).not.toBeInTheDocument()
  })
})

describe('MonatBilanz — Vergleichs-Färbung (#337)', () => {
  // Label steht jetzt doppelt im DOM (Mobil-Karte + Tabelle) — die Tabellen-Instanz
  // ist die mit einem <tr>-Vorfahren.
  const deltaIn = (label: string) => {
    const row = screen.getAllByText(label).map((el) => el.closest('tr')).find(Boolean)!
    return within(row).getByText(/%/)
  }

  it('Gesamtverbrauch-Anstieg ist rot', () => {
    const vmX = { ...vm, gesamtverbrauch_kwh: 300, autarkie_prozent: 58 }
    render(<MonatBilanz d={d({ gesamtverbrauch_kwh: 366 })} vm={vmX} glMonStats={null} monatName="Mai" />)
    const badge = deltaIn('Gesamtverbrauch')
    expect(badge.textContent).toContain('▲') // Verbrauch stieg
    expect(badge.className).toMatch(/red/)    // mehr Verbrauch = schlechter
  })

  it('Eigenverbrauch-Anstieg ist rot, wenn die Autarkie fiel', () => {
    const vmX = { ...vm, eigenverbrauch_kwh: 210, autarkie_prozent: 65 }
    render(<MonatBilanz d={d({ eigenverbrauch_kwh: 223, autarkie_prozent: 61 })} vm={vmX} glMonStats={null} monatName="Mai" />)
    const badge = deltaIn('Eigenverbrauch')
    expect(badge.textContent).toContain('▲') // EV stieg absolut
    expect(badge.className).toMatch(/red/)    // aber Autarkie fiel → rot
  })

  it('Eigenverbrauch-Anstieg ist grün, wenn die Autarkie stieg', () => {
    const vmX = { ...vm, eigenverbrauch_kwh: 210, autarkie_prozent: 58 }
    render(<MonatBilanz d={d({ eigenverbrauch_kwh: 223, autarkie_prozent: 61 })} vm={vmX} glMonStats={null} monatName="Mai" />)
    expect(deltaIn('Eigenverbrauch').className).toMatch(/green/)
  })
})

// R15-1 (Rainer-PN #88625): Kosten-Kacheln „Batterieladung Netz" + „Durchschnittspreis Netz".
describe('baueNetzKostenKpis (via baueMonatKpis)', () => {
  it('ohne Kosten-Daten bleiben es die 7 Basis-Kacheln', () => {
    expect(baueMonatKpis(d(), vm)).toHaveLength(7)
  })

  it('0 kWh Netzladung zeigt die Kachel trotzdem — mit „—" als Ladepreis', () => {
    // Rainer-PN 2026-07-25: „Nichtverbrauch" ist auch eine Aussage. Früher fiel
    // die Kachel bei 0 weg und man musste in HA nachsehen, ob wirklich nichts lief.
    const k = baueMonatKpis(d({
      speicher_ladung_netz_kwh: 0,
      speicher_ladung_netz_kosten_euro: 0,
      speicher_ladung_netz_preis_cent: null,
    }), vm).find((x) => x.title === 'Batterieladung Netz')!
    expect(k).toBeDefined()
    expect(k.value).toBe('—')
    expect(k.subtitle).toBe('0 kWh · 0,00 €')
    // Keine Pseudo-Herleitung „0 kWh × — ct/kWh".
    expect(k.berechnung).toBeUndefined()
  })

  it('ohne Speicher bleibt die Kachel aus (null ≠ 0)', () => {
    const kpis = baueMonatKpis(d({ speicher_ladung_netz_kwh: null }), vm)
    expect(kpis.find((x) => x.title === 'Batterieladung Netz')).toBeUndefined()
  })

  it('Batterieladung Netz zeigt Ø-Ladepreis als Hauptwert, kWh·€ als Zweitzeile (R16-A)', () => {
    const k = baueMonatKpis(d({
      speicher_ladung_netz_kwh: 112,
      speicher_ladung_netz_kosten_euro: 25.12,
      speicher_ladung_netz_preis_cent: 22.4,
      speicher_ladung_netz_preis_quelle: 'tep',
    }), vm).find((x) => x.title === 'Batterieladung Netz')!
    expect(k.unit).toBe('ct/kWh')
    expect(k.value).toBe('22,4')
    expect(k.subtitle).toBe('112 kWh · 25,12 €')
  })

  it('Batterieladung Netz benennt die tatsächliche Preis-Herkunft', () => {
    // Forum simon42 #89667/56 (MartyBr): die Kachel sagte pauschal „aus der
    // Strompreis-Mitschrift", auch wenn der Preis aus dem Tarif kam. Ein
    // falsches Etikett schickt den Anwender auf die falsche Fehlersuche.
    const herkunft = (quelle: string | null) => baueMonatKpis(d({
      speicher_ladung_netz_kwh: 19,
      speicher_ladung_netz_kosten_euro: 5.45,
      speicher_ladung_netz_preis_cent: 28.7,
      speicher_ladung_netz_preis_quelle: quelle,
    }), vm).find((x) => x.title === 'Batterieladung Netz')!.formel

    expect(herkunft('tep')).toContain('aus der Strompreis-Mitschrift')
    expect(herkunft('imd')).toContain('aus deiner Eingabe im Monatsabschluss')
    expect(herkunft('bezugspreis')).toContain('Arbeitspreis deines Tarifs')
    // Festpreis-Anlage: gerade NICHT die Mitschrift behaupten.
    expect(herkunft('bezugspreis')).not.toContain('Mitschrift')
    // Unbekannte/fehlende Quelle behauptet lieber nichts.
    expect(herkunft(null)).toContain('Herkunft unbekannt')
  })

  it('Ø-Preis Netz bevorzugt den dynamischen Monats-Ø vor dem Tarif', () => {
    const k = baueMonatKpis(d({
      netzbezug_kwh: 1153,
      // 1153 × 26,1 ct = 300,93 € Arbeitspreis, + 25,98 € Grundpreis = 326,91 €
      netzbezug_kosten_euro: 326.91,
      netzbezug_arbeitspreis_kosten_euro: 300.93,
      grundgebuehr_euro: 25.98,
      netzbezug_durchschnittspreis_cent: 26.1,
      netzbezug_preis_cent: 30,
    }), vm).find((x) => x.title === 'Ø-Preis Netz')!
    expect(k.unit).toBe('ct/kWh')
    expect(k.value).toBe('26,1')
    // Unterzeile = Arbeitspreis-Anteil, nicht die Gesamtkosten.
    expect(k.subtitle).toBe('1.153 kWh · 300,93 €')
  })

  it('Ø-Preis Netz fällt ohne dynamischen Ø auf den Tarif-Arbeitspreis zurück', () => {
    const k = baueMonatKpis(d({
      netzbezug_kwh: 143, netzbezug_kosten_euro: 42.9,
      netzbezug_arbeitspreis_kosten_euro: 42.9, netzbezug_preis_cent: 30,
    }), vm).find((x) => x.title === 'Ø-Preis Netz')!
    expect(k.value).toBe('30,0')
  })

  // ── Der gemeldete Fall (Forum simon42 #89667, Algie) ──────────────────────

  it('Ø-Preis Netz: kWh und € der Unterzeile ergeben den Kopfwert', () => {
    // Algies Zahlen: 559 kWh, Kachel zeigt 33 ct, Gesamtkosten 210,45 €.
    // Er hat 210,45 / 559 gerechnet und kam auf 37,6 ct — die Kachel stellte
    // zwei Zahlen nebeneinander, die sich scheinbar ineinander umrechnen
    // lassen. Der Tooltip „inkl. Grundpreis" wird erst nach dem Stolpern
    // gelesen und ist deshalb keine Lösung.
    const k = baueMonatKpis(d({
      netzbezug_kwh: 559,
      netzbezug_kosten_euro: 210.45,
      netzbezug_arbeitspreis_kosten_euro: 184.47,
      grundgebuehr_euro: 25.98,
      netzbezug_preis_cent: 33,
    }), vm).find((x) => x.title === 'Ø-Preis Netz')!

    expect(k.value).toBe('33,0')
    expect(k.subtitle).toBe('559 kWh · 184,47 €')

    // Die Division, die der Melder gemacht hat — jetzt geht sie auf.
    const [kwhTeil, euroTeil] = k.subtitle!.split(' · ')
    const kwh = parseFloat(kwhTeil.replace(/\./g, '').replace(' kWh', ''))
    const euro = parseFloat(euroTeil.replace(' €', '').replace(',', '.'))
    expect((euro / kwh) * 100).toBeCloseTo(33.0, 1)
    // Mit den alten Gesamtkosten wäre es weiterhin 37,6 ct gewesen.
    expect((210.45 / 559) * 100).toBeCloseTo(37.6, 1)
  })

  it('Ø-Preis Netz weist den Grundpreis in der Herleitung aus, statt ihn zu verstecken', () => {
    const k = baueMonatKpis(d({
      netzbezug_kwh: 559, netzbezug_kosten_euro: 210.45,
      netzbezug_arbeitspreis_kosten_euro: 184.47, grundgebuehr_euro: 25.98,
      netzbezug_preis_cent: 33,
    }), vm).find((x) => x.title === 'Ø-Preis Netz')!
    expect(k.berechnung).toBe('559 kWh × 33,0 ct/kWh')
    expect(k.ergebnis).toContain('25,98 € Grundpreis')
    expect(k.ergebnis).toContain('210,45 € gesamt')
    expect(k.formel).toContain('ohne Grundpreis')
  })

  it('ohne Grundpreis bleibt die Herleitung schlicht', () => {
    const k = baueMonatKpis(d({
      netzbezug_kwh: 143, netzbezug_kosten_euro: 42.9,
      netzbezug_arbeitspreis_kosten_euro: 42.9, grundgebuehr_euro: 0,
      netzbezug_preis_cent: 30,
    }), vm).find((x) => x.title === 'Ø-Preis Netz')!
    expect(k.ergebnis).toBe('= 42,90 € Kosten')
    expect(k.ergebnis).not.toContain('Grundpreis')
  })
})
