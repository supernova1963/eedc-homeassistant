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

import { StrompreisForm } from './StrompreiseTeile'
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
