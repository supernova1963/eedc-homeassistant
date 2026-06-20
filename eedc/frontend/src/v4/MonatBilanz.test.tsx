import { describe, it, expect } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import { baueMonatKpis, MonatBilanz } from './MonatBilanz'
import type { AktuellerMonatResponse } from '../api/aktuellerMonat'
import type { AggregierteMonatsdaten } from '../api/monatsdaten'

// baueMonatKpis liest nur eine Handvoll Felder — Teil-Fixture genügt.
function d(over: Partial<AktuellerMonatResponse> = {}): AktuellerMonatResponse {
  return {
    pv_erzeugung_kwh: 412, einspeisung_kwh: 189, netzbezug_kwh: 143,
    eigenverbrauch_kwh: 223, gesamtverbrauch_kwh: 366,
    autarkie_prozent: 61, eigenverbrauch_quote_prozent: 54,
    direktverbrauch_kwh: 180,
    netto_ertrag_euro: 128, soll_pv_kwh: 450, vorjahr: null,
    ...over,
  } as AktuellerMonatResponse
}

const vm = { pv_erzeugung_kwh: 380, autarkie_prozent: 58, eigenverbrauch_kwh: 210, einspeisung_kwh: 170, netzbezug_kwh: 150 } as AggregierteMonatsdaten

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
    const vmX = { ...vm, gesamtverbrauch_kwh: 300, autarkie_prozent: 58 } as AggregierteMonatsdaten
    render(<MonatBilanz d={d({ gesamtverbrauch_kwh: 366 })} vm={vmX} glMonStats={null} monatName="Mai" />)
    const badge = deltaIn('Gesamtverbrauch')
    expect(badge.textContent).toContain('▲') // Verbrauch stieg
    expect(badge.className).toMatch(/red/)    // mehr Verbrauch = schlechter
  })

  it('Eigenverbrauch-Anstieg ist rot, wenn die Autarkie fiel', () => {
    const vmX = { ...vm, eigenverbrauch_kwh: 210, autarkie_prozent: 65 } as AggregierteMonatsdaten
    render(<MonatBilanz d={d({ eigenverbrauch_kwh: 223, autarkie_prozent: 61 })} vm={vmX} glMonStats={null} monatName="Mai" />)
    const badge = deltaIn('Eigenverbrauch')
    expect(badge.textContent).toContain('▲') // EV stieg absolut
    expect(badge.className).toMatch(/red/)    // aber Autarkie fiel → rot
  })

  it('Eigenverbrauch-Anstieg ist grün, wenn die Autarkie stieg', () => {
    const vmX = { ...vm, eigenverbrauch_kwh: 210, autarkie_prozent: 58 } as AggregierteMonatsdaten
    render(<MonatBilanz d={d({ eigenverbrauch_kwh: 223, autarkie_prozent: 61 })} vm={vmX} glMonStats={null} monatName="Mai" />)
    expect(deltaIn('Eigenverbrauch').className).toMatch(/green/)
  })
})
