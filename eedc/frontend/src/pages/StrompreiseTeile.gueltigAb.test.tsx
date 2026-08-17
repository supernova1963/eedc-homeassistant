/**
 * „Gültig ab" beim ERSTEN Tarif einer Anlage.
 *
 * Anlass: Das Formular belegte das Feld immer mit dem heutigen Datum vor. Bei
 * einer Neuinstallation, die zuerst Monate aus der HA-Statistik importiert und
 * danach den Tarif anlegt, fielen damit ALLE importierten Altmonate hinter den
 * Tarif — sie rechneten still mit der 30-ct-Vorbelegung, obwohl sichtbar ein
 * Tarif gepflegt war (Forum simon42 #89667/60, Algie).
 *
 * Der Setup-Wizard belegt seit jeher mit dem Inbetriebnahme-Datum vor
 * (`StrompreiseStep`); die Einzelseite folgt jetzt derselben Mechanik — aber
 * nur beim ersten Tarif. Ab dem zweiten ist „heute" richtig (Tarifwechsel).
 */
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'

import { StrompreisForm, erstTarifVorbelegung } from './StrompreiseTeile'
import type { Strompreis } from '../types'

/** Der DatumPicker ist ein Button mit ausgeschriebenem Datum, kein <input>. */
function gueltigAbText(): string {
  return screen.getByRole('button', { name: /Gültig ab/ }).textContent ?? ''
}

function alsAnzeige(iso: string): string {
  return new Date(`${iso}T12:00:00`).toLocaleDateString('de-DE', {
    day: 'numeric', month: 'long', year: 'numeric',
  })
}

const HEUTE = new Date().toISOString().split('T')[0]

describe('StrompreisForm — Vorbelegung „Gültig ab"', () => {
  it('nimmt beim ersten Tarif das Inbetriebnahme-Datum', () => {
    render(
      <StrompreisForm
        anlageId={1}
        onCreate={async () => {}}
        onCancel={() => {}}
        gueltigAbVorbelegung="2023-04-01"
      />,
    )

    expect(gueltigAbText()).toContain(alsAnzeige('2023-04-01'))
  })

  it('fällt ohne Vorbelegung auf heute zurück', () => {
    render(<StrompreisForm anlageId={1} onCreate={async () => {}} onCancel={() => {}} />)

    expect(gueltigAbText()).toContain(alsAnzeige(HEUTE))
  })

  it('lässt einen bestehenden Tarif beim Bearbeiten unangetastet', () => {
    const tarif = {
      id: 7, anlage_id: 1, gueltig_ab: '2024-07-01',
      netzbezug_arbeitspreis_cent_kwh: 28, einspeiseverguetung_cent_kwh: 8.2,
      verwendung: 'allgemein',
    } as Strompreis

    render(
      <StrompreisForm
        strompreis={tarif}
        anlageId={1}
        onUpdate={async () => {}}
        onCancel={() => {}}
        gueltigAbVorbelegung="2023-04-01"
      />,
    )

    expect(gueltigAbText()).toContain(alsAnzeige('2024-07-01'))
  })

  it('sagt am Feld, dass frühere Monate mit der Vorbelegung rechnen', () => {
    render(<StrompreisForm anlageId={1} onCreate={async () => {}} onCancel={() => {}} />)

    expect(screen.getByText(/Monate davor rechnen mit der Vorbelegung/)).toBeInTheDocument()
  })
})

// N-257: Die Ableitung stand bis zum 17.08.2026 als Inline-Ausdruck in der
// Seite — ein Rückbau daran wäre von den Proben oben NICHT bemerkt worden
// (sie reichen `gueltigAbVorbelegung` von außen herein). Deshalb ist sie jetzt
// eine benannte Regel mit eigener Probe.
describe('erstTarifVorbelegung (N-257)', () => {
  it('zieht das Inbetriebnahme-Datum auf den Monatsersten', () => {
    expect(erstTarifVorbelegung(0, '2023-04-17')).toBe('2023-04-01')
    expect(erstTarifVorbelegung(0, '2025-08-03')).toBe('2025-08-01')
  })

  it('lässt einen Monatsersten unverändert', () => {
    expect(erstTarifVorbelegung(0, '2023-04-01')).toBe('2023-04-01')
  })

  it('schweigt ab dem ZWEITEN Tarif — sonst würde ein Wechsel rückdatiert', () => {
    // Die eigentliche Aussage der Regel. Ein Tarifwechsel am 12.09. gilt ab dem
    // 12.09.; auf den 01.09. gezogen bekäme der laufende Monat rückwirkend den
    // neuen Preis.
    expect(erstTarifVorbelegung(1, '2023-04-17')).toBeUndefined()
    expect(erstTarifVorbelegung(5, '2023-04-17')).toBeUndefined()
  })

  it('schweigt ohne gepflegtes Inbetriebnahme-Datum', () => {
    expect(erstTarifVorbelegung(0, null)).toBeUndefined()
    expect(erstTarifVorbelegung(0, undefined)).toBeUndefined()
  })
})
