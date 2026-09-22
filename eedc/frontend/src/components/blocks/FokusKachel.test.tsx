import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { FokusKachel } from './FokusKachel'

describe('FokusKachel', () => {
  it('zeigt Inhalt + ⤢ und schaltet auf Vollbild (Zurück) um', () => {
    render(
      <FokusKachel titel="Energiefluss" fokusId="live:energiefluss">
        <p>Karten-Inhalt</p>
      </FokusKachel>,
    )
    expect(screen.getByText('Karten-Inhalt')).toBeInTheDocument()
    expect(screen.queryByText('Zurück')).not.toBeInTheDocument()

    fireEvent.click(screen.getByLabelText('Energiefluss: Fokus / Vollbild'))
    // Im Vollbild: Titel-Header + Zurück, Inhalt nur einmal (im Overlay).
    expect(screen.getByText('Zurück')).toBeInTheDocument()
    expect(screen.getByText('Energiefluss')).toBeInTheDocument()
    expect(screen.getAllByText('Karten-Inhalt')).toHaveLength(1)

    fireEvent.click(screen.getByText('Zurück'))
    expect(screen.queryByText('Zurück')).not.toBeInTheDocument()
    expect(screen.getByText('Karten-Inhalt')).toBeInTheDocument()
  })

  it('blendet den Titel in der Kartenkopfzeile nur mit zeigeTitel ein', () => {
    const { rerender } = render(<FokusKachel titel="Temperaturen" fokusId="live:temperaturen"><span>x</span></FokusKachel>)
    expect(screen.queryByText('Temperaturen')).not.toBeInTheDocument() // nur im Vollbild

    rerender(<FokusKachel titel="Temperaturen" fokusId="live:temperaturen" zeigeTitel><span>x</span></FokusKachel>)
    expect(screen.getByText('Temperaturen')).toBeInTheDocument()
  })
})

// ── FD: Deep-Link je Kachel (`#/cockpit/live?fokus=live:…`) ──────────────────
describe('FokusKachel — Fokus-Deep-Link (FD-1)', () => {
  const URSPRUNG = window.location.hash
  beforeEach(() => { window.location.hash = '' })
  afterEach(() => { window.location.hash = URSPRUNG })

  it('öffnet beim Laden, wenn die Adresse GENAU diese Kachel nennt — ohne Zurück und ohne ⤢', () => {
    window.location.hash = '#/cockpit/live?fokus=live:tagesverlauf'
    render(
      <FokusKachel titel="Tagesverlauf" fokusId="live:tagesverlauf">
        <p>Karten-Inhalt</p>
      </FokusKachel>,
    )
    expect(screen.getByText('Karten-Inhalt')).toBeInTheDocument()
    expect(screen.getByText('Tagesverlauf')).toBeInTheDocument()   // Overlay-Kopfzeile
    expect(screen.queryByText('Zurück')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Tagesverlauf: Fokus / Vollbild')).not.toBeInTheDocument()
  })

  it('eine ANDERE Kachel bleibt zu — und behält ihr ⤢ nicht (die Sicht ist im Deep-Link-Modus)', () => {
    window.location.hash = '#/cockpit/live?fokus=live:tagesverlauf'
    render(
      <FokusKachel titel="Wetter heute" fokusId="live:wetter-heute" zeigeTitel>
        <p>Wetter-Inhalt</p>
      </FokusKachel>,
    )
    // Sie rendert normal als KARTE (h3 im Kartenkopf), nicht als Overlay (h2) —
    // ⚠ genau daran hängt die Probe: `getByText('Wetter-Inhalt')` allein wäre
    // blind, die Kinder stehen in beiden Fällen im DOM (gemessen per Sprengsatz).
    expect(screen.getByRole('heading', { name: 'Wetter heute', level: 3 })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Wetter heute', level: 2 })).not.toBeInTheDocument()
    expect(screen.getByText('Wetter-Inhalt')).toBeInTheDocument()
    // Und ohne Bedienelement: es gäbe keinen Weg zurück.
    expect(screen.queryByLabelText('Wetter heute: Fokus / Vollbild')).not.toBeInTheDocument()
  })

  it('ansicht=tabelle startet die Kachel in der Tabellen-Ablesung (CT-5)', () => {
    window.location.hash = '#/cockpit/live?fokus=live:tagesverlauf&ansicht=tabelle'
    render(
      <FokusKachel titel="Tagesverlauf" fokusId="live:tagesverlauf" tabelle={<p>Tabellen-Inhalt</p>}>
        <p>Chart-Inhalt</p>
      </FokusKachel>,
    )
    expect(screen.getByText('Tabellen-Inhalt')).toBeInTheDocument()
    expect(screen.queryByText('Chart-Inhalt')).not.toBeInTheDocument()
  })
})
