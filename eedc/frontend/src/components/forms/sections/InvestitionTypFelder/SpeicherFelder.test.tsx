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

describe('SpeicherFelder — die abgeleitete Entladegrenze steht am Feld (#379)', () => {
  // Anlass (cbrosius auf #379, 30.08.2026): *„Unter Wirtschaftlichkeit wird die
  // resultierende Entladegrenze aktuell schon angezeigt, nicht aber wenn ich die
  // nutzbare Kapazität des Speichers festlegen muss."* Der einzige Hinweis am
  // Feld stammte aus der ersten Frontend-Fassung; die Ableitung kam erst mit
  // v4.0.16 dazu. Bauform wie beim Kopplungs-Hinweis daneben — kein zweites Feld.

  it('rechnet die Grenze vor, sobald beide Kapazitäten stehen', () => {
    // Glens Speicher: 24 von 30 kWh ⇒ 20 % Reserve, leer ab 23 %.
    const text = zeige({ kapazitaet_kwh: '30', nutzbare_kapazitaet_kwh: '24' })

    expect(text).toMatch(/Entladegrenze 20 %/)
    expect(text).toMatch(/ab 23 % Ladestand als leer/)
  })

  it('nennt die Annahme mit, weil nur der Anwender sie prüfen kann', () => {
    // Wer 10/90 fährt, trägt die OBERE Grenze vertragsgemäß mit ein — die
    // abgeleitete Untergrenze fällt dann zu hoch aus (20 % statt 10 %). Ohne
    // diesen Satz sieht das niemand; ein zweites Feld ist verworfen (15.08.).
    const text = zeige({ kapazitaet_kwh: '10', nutzbare_kapazitaet_kwh: '8' })

    expect(text).toMatch(/Entladegrenze 20 %/)
    expect(text).toMatch(/obere\s+Ladegrenze/)
    expect(text).toMatch(/zu hoch/)
  })

  it('behauptet keine Grenze, wo keine abgeleitet werden kann', () => {
    // Nur brutto gepflegt ⇒ Rückfall auf 5 %. Eine „Entladegrenze 0 %" wäre
    // eine Aussage über eine Einstellung, die der Anwender nie gemacht hat —
    // dieselbe Doktrin wie in der Wirtschaftlichkeits-Sicht (N-254).
    const text = zeige({ kapazitaet_kwh: '30' })

    // Nicht „das Wort kommt nicht vor": der Rueckfall-Hinweis NENNT die
    // Ableitung bewusst — genau der Satz, der cbrosius gefehlt hat. Verboten
    // ist der behauptete WERT, den das „⇒" markiert.
    expect(text).not.toMatch(/⇒ Entladegrenze/)
    expect(text).toMatch(/Typisch 90-95 %/)
    expect(text).toMatch(/Daraus leitet eedc die Entladegrenze ab/)
  })

  it('behauptet keine Grenze, wenn nutzbar nicht kleiner als brutto ist', () => {
    const text = zeige({ kapazitaet_kwh: '30', nutzbare_kapazitaet_kwh: '30' })

    expect(text).not.toMatch(/⇒ Entladegrenze/)
  })
})
