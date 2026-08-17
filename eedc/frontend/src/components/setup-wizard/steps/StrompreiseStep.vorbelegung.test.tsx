/**
 * „Gültig ab" im Setup-Wizard — Vorbelegung aus dem Inbetriebnahme-Datum.
 *
 * **Warum es diese Probe gibt (N-257).** Der Wizard belegt seit jeher mit dem
 * Inbetriebnahme-Datum vor. Das war gut gemeint und stellte trotzdem eine
 * Falle: Die Monatsrechnung fragt mit dem **Monatsersten** nach dem gültigen
 * Tarif, ein Tarif ab dem 03.08. deckt den August also nicht ab — der ganze
 * Monat rechnet dann mit Standardwerten. Gefunden hat es ein Anwender, der
 * 14,27 € gegen 16,05 € von Hand nachrechnete (Forum simon42 #89667/165).
 *
 * Die Grenze steht in `lib/datum.ts::monatsersterVon`: Nur die Vorbelegung aus
 * dem Inbetriebnahme-Datum wird gezogen. Die Stichtagsregel selbst bleibt —
 * ein Monat hat EINEN Preis (ADR-002/P8).
 *
 * ⚠ Ohne diese Probe wäre ein Rückbau an der Aufrufstelle **stumm**: Der
 * Helfer-Test in `lib/datum.test.ts` prüft die Funktion, nicht ihre Benutzung.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'

import StrompreiseStep from './StrompreiseStep'
import type { Anlage } from '../../../types'

/** Der DatumPicker rendert als Button mit ausgeschriebenem Datum, kein <input>. */
function gueltigAbText(): string {
  return screen.getByRole('button', { name: /Gültig ab/ }).textContent ?? ''
}

function alsAnzeige(iso: string): string {
  return new Date(`${iso}T12:00:00`).toLocaleDateString('de-DE', {
    day: 'numeric', month: 'long', year: 'numeric',
  })
}

function renderStep(anlage: Partial<Anlage> | null) {
  render(
    <StrompreiseStep
      anlage={anlage as Anlage | null}
      isLoading={false}
      error={null}
      onSubmit={vi.fn()}
      onUseDefaults={vi.fn()}
      onBack={vi.fn()}
    />,
  )
}

describe('StrompreiseStep — „Gültig ab" (N-257)', () => {
  it('zieht das Inbetriebnahme-Datum auf den Monatsersten', () => {
    renderStep({ id: 1, installationsdatum: '2023-04-17' })

    expect(gueltigAbText()).toContain(alsAnzeige('2023-04-01'))
    expect(gueltigAbText()).not.toContain(alsAnzeige('2023-04-17'))
  })

  it('lässt einen bereits am Monatsersten liegenden Tag unverändert', () => {
    renderStep({ id: 1, installationsdatum: '2023-04-01' })

    expect(gueltigAbText()).toContain(alsAnzeige('2023-04-01'))
  })

  it('fällt ohne Inbetriebnahme-Datum auf heute zurück — nicht auf den Monatsersten', () => {
    // Bewusst NICHT gerundet: Ohne gepflegtes Datum hat niemand etwas
    // eingegeben, und ein stiller Sprung an den Monatsanfang wäre eine
    // Behauptung über einen Zeitraum, den der Anwender nie genannt hat.
    renderStep({ id: 1, installationsdatum: undefined })

    const heute = new Date()
    expect(gueltigAbText()).toContain(
      alsAnzeige(
        `${heute.getFullYear()}-${String(heute.getMonth() + 1).padStart(2, '0')}-${String(heute.getDate()).padStart(2, '0')}`,
      ),
    )
  })
})
