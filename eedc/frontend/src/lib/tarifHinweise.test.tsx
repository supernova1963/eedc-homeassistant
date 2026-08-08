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
import { EINSPEISEVERGUETUNG_FLAT_HINWEIS } from './tarifHinweise'
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
