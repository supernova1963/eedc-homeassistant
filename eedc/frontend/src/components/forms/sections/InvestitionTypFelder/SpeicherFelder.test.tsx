/**
 * Speicher-Formular: die beiden Arbitrage-Preise sind pflegbar (#397).
 *
 * Anlass (GitHub Issue #397, MeinerB, 26.08.2026): *„ich bekomme einen Hinweis
 * dass ich die Felder bearbeiten soll, kann sie aber nicht finden."* Der
 * Daten-Checker fordert Ø Lade- und Ø Entladepreis, sobald „Arbitrage-fähig"
 * an ist — beide gab es in keinem Formular und in keinem Wizard, nur in der
 * Konstanten-Map. Sein „Beheben"-Knopf führte genau hierher.
 *
 * Die Gegenrichtung steht im Backend: `test_daten_checker_arbitrage_v2h_preise_397.py`
 * hält fest, dass der Hinweis ohne die Werte weiterhin kommt — und dass der
 * gleich aussehende V2H-Hinweis zu Recht entfallen ist (dort ist der Preis ein
 * Override, hier die einzige Quelle).
 *
 * ⚠ Ohne Arbitrage bleiben die Felder weg. Sie ohne den Schalter zu zeigen,
 * wäre zwei Fragen in einem Formular — und der Checker fragt sie dort auch
 * nicht.
 */
import { describe, it, expect } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'

import { SpeicherFelder } from './SpeicherFelder'

const noop = () => {}

/** Rendert und klappt „Netzladung & Arbitrage" auf (`variant="erweitert"` startet zu). */
function zeige(params: Record<string, string | boolean>): string {
  const { container } = render(
    <SpeicherFelder
      paramData={params}
      onInputChange={noop}
      setParam={noop}
      zeige={() => undefined}
      markTouched={noop}
      setFeldRef={() => () => {}}
    />,
  )
  const kopf = screen.getByRole('button', { name: /Netzladung & Arbitrage/ })
  if (kopf.getAttribute('aria-expanded') === 'false') fireEvent.click(kopf)
  return container.textContent ?? ''
}

describe('SpeicherFelder — Arbitrage-Preise (#397)', () => {
  it('zeigt beide Preisfelder, sobald Arbitrage an ist', () => {
    const text = zeige({ arbitrage_faehig: true })

    expect(text).toMatch(/Ø Ladepreis \(ct\/kWh\)/)
    expect(text).toMatch(/Ø Entladepreis \(ct\/kWh\)/)
  })

  it('nennt den Richtwert im Hinweis, statt ihn ins Feld zu schreiben', () => {
    // Bauform von `kopplung` und #331: eine Vorbelegung würde beim ersten
    // Speichern zur gepflegten Zahl — und brächte den Daten-Checker zum
    // Schweigen, ohne dass jemand sie bestätigt hat.
    const { container } = render(
      <SpeicherFelder
        paramData={{ arbitrage_faehig: true }}
        onInputChange={noop} setParam={noop} zeige={() => undefined}
        markTouched={noop} setFeldRef={() => () => {}}
      />,
    )
    const kopf = screen.getByRole('button', { name: /Netzladung & Arbitrage/ })
    if (kopf.getAttribute('aria-expanded') === 'false') fireEvent.click(kopf)

    expect(container.textContent).toMatch(/rechnet eedc mit 12 ct\/kWh/)
    expect(container.textContent).toMatch(/rechnet eedc mit 35 ct\/kWh/)

    const lade = screen.getByRole('spinbutton', { name: /Ø Ladepreis/ })
    const entlade = screen.getByRole('spinbutton', { name: /Ø Entladepreis/ })
    expect(lade).toHaveValue(null)
    expect(entlade).toHaveValue(null)
  })

  it('zeigt gepflegte Werte an', () => {
    zeige({ arbitrage_faehig: true, lade_durchschnittspreis_cent: '15', entlade_vermiedener_preis_cent: '38' })

    expect(screen.getByRole('spinbutton', { name: /Ø Ladepreis/ })).toHaveValue(15)
    expect(screen.getByRole('spinbutton', { name: /Ø Entladepreis/ })).toHaveValue(38)
  })

  it('ohne Arbitrage bleiben beide Felder weg', () => {
    const text = zeige({ arbitrage_faehig: false })

    expect(text).toMatch(/Arbitrage-fähig/)      // der Schalter selbst ist da
    expect(text).not.toMatch(/Ø Ladepreis/)
    expect(text).not.toMatch(/Ø Entladepreis/)
  })
})
