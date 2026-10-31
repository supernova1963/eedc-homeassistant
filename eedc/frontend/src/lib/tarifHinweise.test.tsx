/**
 * Der Flat-Hinweis steht an BEIDEN Eingaben der Einspeisevergütung.
 *
 * Anlass: Forum T89667 #120 (Phir0n) fragte, ob eedc flat mit der eingetragenen
 * Zahl rechnet oder den Misch-Vergütungssatz im Hintergrund aus der
 * Anlagengröße ermittelt. Das Feld hieß an beiden Stellen nur
 * „Einspeisevergütung (ct/kWh)" und beantwortete die Frage nicht; im
 * Setup-Wizard stand daneben sogar ein Satz *einer EEG-Stufe*, was den
 * gegenteiligen Eindruck erzeugte. Zugesagt in T89667 #122.
 *
 * Die Probe hält beide Stellen an derselben Konstante fest — ein Hinweis, der
 * nur an einer der beiden Eingaben steht, ist der gemeldete Befund noch einmal.
 */
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'

import { StrompreisForm } from '../pages/StrompreiseTeile'
import StrompreiseStep from '../components/setup-wizard/steps/StrompreiseStep'
import { EINSPEISEVERGUETUNG_FLAT_HINWEIS, evWpTarifText, grundgebuehrAufteilungText, netzbezugAnteileBerechnung, verwendungLabel } from './tarifHinweise'
import type { Anlage } from '../types'

function anlageMit(kwp: number): Anlage {
  return { id: 1, anlagenname: 'Test', leistung_kwp: kwp } as Anlage
}

function wizardProps(anlage: Anlage | null) {
  return {
    anlage,
    isLoading: false,
    error: null,
    onSubmit: async () => {},
    onUseDefaults: async () => {},
    onBack: () => {},
  }
}

describe('Einspeisevergütung — Hinweis auf die flache Rechnung', () => {
  it('steht an der Pflege-Route (Einstellungen → Strompreise)', () => {
    render(<StrompreisForm anlageId={1} onCreate={async () => {}} onCancel={() => {}} />)

    expect(screen.getByText(new RegExp(EINSPEISEVERGUETUNG_FLAT_HINWEIS))).toBeTruthy()
  })

  it('steht im Setup-Wizard', () => {
    render(<StrompreiseStep {...wizardProps(anlageMit(9.9))} />)

    expect(screen.getByText(new RegExp(EINSPEISEVERGUETUNG_FLAT_HINWEIS))).toBeTruthy()
  })

  it('rät im Wizard keinen Satz — 0, unabhängig von der Anlagengröße', () => {
    // Bis 08.08.2026 leitete der Wizard eine EEG-Stufe aus `leistung_kwp` ab
    // (8,2 / 7,1 / 5,8) und schlug damit über 10 kWp einen zu NIEDRIGEN Satz
    // vor — gestaffelt wird nach installierter Leistung, für die Gesamtanlage
    // gilt der gewichtete Mischsatz. Entfernt statt korrigiert: die Sätze
    // ändern sich laufend, eine Tabelle im Code veraltet garantiert.
    const wert = () =>
      (screen.getByLabelText(/Einspeisevergütung/) as HTMLInputElement).value

    const { unmount } = render(<StrompreiseStep {...wizardProps(anlageMit(9.9))} />)
    expect(wert()).toBe('0')
    unmount()

    render(<StrompreiseStep {...wizardProps(anlageMit(50))} />)
    expect(wert()).toBe('0')
  })

  it('sagt bei 0 ct, was das für den Erlös bedeutet — an beiden Eingaben', () => {
    // Eine 0 im Feld ist die Vorbelegung und darf nicht still bleiben: der
    // Einspeise-Erlös des Zeitraums ist dann 0 €, was erst Monate später in
    // den Auswertungen auffällt.
    const { unmount } = render(<StrompreiseStep {...wizardProps(anlageMit(9.9))} />)
    expect(screen.getByText(/kein Einspeise-Erlös berechnet/)).toBeTruthy()
    unmount()

    render(<StrompreisForm anlageId={1} onCreate={async () => {}} onCancel={() => {}} />)
    expect(screen.getByText(/kein Einspeise-Erlös berechnet/)).toBeTruthy()
  })
})

describe('N-769: Grundgebühr je Tarif', () => {
  const fmt = (e: number) => e.toFixed(2).replace('.', ',')

  it('nennt die Tarife in der Reihenfolge des Backends, mit den Namen der Tarifliste', () => {
    expect(grundgebuehrAufteilungText({ allgemein: 14, waermepumpe: 10 }, fmt))
      .toBe(' (Standard 14,00 € · Wärmepumpe 10,00 €)')
    expect(grundgebuehrAufteilungText({ waermepumpe: 10, wallbox: 5 }, fmt))
      .toBe(' (Wärmepumpe 10,00 € · Wallbox 5,00 €)')
  })

  it('bleibt ohne Aufteilung leer (nur der allgemeine Tarif)', () => {
    expect(grundgebuehrAufteilungText(null, fmt)).toBe('')
    expect(grundgebuehrAufteilungText(undefined, fmt)).toBe('')
    expect(grundgebuehrAufteilungText({}, fmt)).toBe('')
  })

  it('verwendungLabel ist derselbe Name wie in der Tarifliste', () => {
    expect(verwendungLabel('allgemein')).toBe('Standard')
    expect(verwendungLabel('waermepumpe')).toBe('Wärmepumpe')
    expect(verwendungLabel('wallbox')).toBe('Wallbox')
  })
})

describe('N-770/N-771 — Anteile zum Komponenten-Tarif', () => {
  const k = (v: number) => v.toFixed(1).replace('.', ',')
  it('nennt Rest zum Haushaltspreis und jeden Anteil mit seinem Preis', () => {
    expect(netzbezugAnteileBerechnung(373.9, 30, [
      { verwendung: 'waermepumpe', kwh: 256, cent: 22, euro: 56.32, gemessen_kwh: 256, geklemmt: false },
    ], k, k)).toBe('117,9 kWh × 30,0 ct/kWh + 256,0 kWh × 22,0 ct/kWh (Wärmepumpe)')
  })
  it('sagt, wenn ein Anteil begrenzt wurde', () => {
    expect(netzbezugAnteileBerechnung(9.73, 30, [
      { verwendung: 'waermepumpe', kwh: 9.73, cent: 22, euro: 2.14, gemessen_kwh: 105.1, geklemmt: true },
    ], k, k)).toContain('gemessen 105,1 kWh, begrenzt')
  })
  it('ohne Anteile null, ohne WP-Anteil kein Zusatz', () => {
    expect(netzbezugAnteileBerechnung(100, 30, null, k, k)).toBeNull()
    expect(netzbezugAnteileBerechnung(100, 30, [], k, k)).toBeNull()
    expect(evWpTarifText(null, 22, k, k)).toBe('')
    expect(evWpTarifText(170.7, 22, k, k)).toBe(' · davon 170,7 kWh PV-Strom der Wärmepumpe zum WP-Tarif 22,0 ct/kWh')
  })
})

describe('F12 (N-770/N-771 E6) — gemeinsamer Zähler Wärmepumpe und Wallbox', () => {
  const k = (v: number) => v.toFixed(1).replace('.', ',')
  const fmt = (e: number) => e.toFixed(2).replace('.', ',')

  it('das Formular bietet die Verwendung «Wärmepumpe und Wallbox (gemeinsamer Zähler)» an', () => {
    render(<StrompreisForm anlageId={1} onCreate={async () => {}} onCancel={() => {}} />)
    expect(screen.getByText('Wärmepumpe und Wallbox (gemeinsamer Zähler)')).toBeTruthy()
    expect(screen.getByText(/Den gemeinsamen Netzbezug trägt das Feld an der Wärmepumpe/)).toBeTruthy()
  })

  it('Tarifliste und Grundgebühr nennen den gemeinsamen Tarif einmal', () => {
    expect(verwendungLabel('waermepumpe_wallbox')).toBe('Wärmepumpe und Wallbox')
    expect(grundgebuehrAufteilungText({ allgemein: 14, waermepumpe_wallbox: 10 }, fmt))
      .toBe(' (Standard 14,00 € · Wärmepumpe und Wallbox 10,00 €)')
  })

  it('die Rechnung der Ø-Preis-Kachel nennt den gemeinsamen Anteil als solchen', () => {
    expect(netzbezugAnteileBerechnung(400, 30, [
      { verwendung: 'waermepumpe_wallbox', kwh: 250, cent: 22, euro: 55, gemessen_kwh: 250, geklemmt: false },
    ], k, k)).toBe('150,0 kWh × 30,0 ct/kWh + 250,0 kWh × 22,0 ct/kWh (Wärmepumpe und Wallbox, gemeinsamer Zähler)')
  })
})
