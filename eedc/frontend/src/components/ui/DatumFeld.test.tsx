import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { DatumFeld } from './DatumFeld'

// Bewertungsgrenze E5 (2026-08-16): `warnung` ist die Warn-MELDUNG unterhalb der
// Fehler-Schwelle (F3-Status-Achse: warnung ≠ error) — für Felder, deren Fehlen
// die Auswertung beeinträchtigt, das Speichern aber nicht blockieren soll.
//
// Bewusst eine Meldung und kein Rand-Zustand wie bei `Input`: Der DatumPicker
// trägt seine Rahmenfarbe fest im Trigger, VOR dem durchgereichten `className`
// — welche Tailwind-Utility dann gewinnt, entscheidet die Reihenfolge im
// generierten Stylesheet. Ein amber Rand von außen wäre nicht verlässlich, und
// dieser Test hätte es nicht gemerkt.

describe('DatumFeld — Warnung', () => {
  it('zeigt die Warn-Meldung, wenn sie gesetzt ist', () => {
    render(
      <DatumFeld
        label="Inbetriebnahme"
        value=""
        onChange={vi.fn()}
        warnung="Fehlt — ohne dieses Datum weiß eedc nichts."
      />
    )
    expect(screen.getByText('Fehlt — ohne dieses Datum weiß eedc nichts.')).toBeInTheDocument()
  })

  it('schweigt ohne Warnung', () => {
    render(<DatumFeld label="Inbetriebnahme" value="2024-03-01" onChange={vi.fn()} hint="Ein Hinweis" />)
    expect(screen.queryByText(/Fehlt/)).not.toBeInTheDocument()
    expect(screen.getByText('Ein Hinweis')).toBeInTheDocument()
  })

  it('zeigt Warnung UND Hinweis nebeneinander — die Warnung ersetzt den Hinweis nicht', () => {
    render(
      <DatumFeld
        label="Inbetriebnahme"
        value=""
        onChange={vi.fn()}
        warnung="Fehlt."
        hint="Stammdatum der Gesamt-Anlage."
      />
    )
    expect(screen.getByText('Fehlt.')).toBeInTheDocument()
    expect(screen.getByText('Stammdatum der Gesamt-Anlage.')).toBeInTheDocument()
  })
})
