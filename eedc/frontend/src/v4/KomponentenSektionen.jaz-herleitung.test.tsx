import { describe, it, expect } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { baueKomponentenBloecke } from './KomponentenSektionen'
import { baueTagAlsMonat } from './TagKomponenten'
import type { ParkApi } from '../components/park'
import type { AktuellerMonatResponse } from '../api/aktuellerMonat'
import type { TagDetail } from '../api/energie_profil'
import { aktuellerMonat, tagWerte } from '../test/factories'

/**
 * Die Arbeitszahl-Kachel zeigt die Zahlen, mit denen gerechnet wurde (**A6**).
 *
 * Schwesterdateien: `KomponentenSektionen.tag-arbeitszahl.test.tsx` (N-348 — dass
 * die drei Zeilen je Funktion überhaupt dastehen) und
 * `KomponentenSektionen.soll-waerme-klima.test.tsx`. Backend-Hälfte:
 * `test_arbeitszahl_herleitung.py`.
 *
 * ## Die Regel
 *
 * Style-Guide **A6 (Berechnungs-Transparenz)**: *„Jede abgeleitete/aggregierte
 * Kennzahl zeigt ihre Herleitung auf Abruf — Formel **+ eingesetzte Werte** +
 * Datenquelle/Zeitraum."* Die Arbeitszahl trug bis zum 01.09.2026 nur die
 * symbolische Formel „JAZ = Wärme ÷ Strom".
 *
 * ## Warum das ein Melder-Fall ist
 *
 * dietmar1968 (simon42 T89667 #283) sah über Monate Arbeitszahlen von 0,7 · 0,9
 * · 1,1 — physikalisch unmöglich und damit ein sicheres Zeichen für einen falsch
 * zugeordneten Wärmemengenzähler. Mit „210 kWh Wärme ÷ 314 kWh Strom" daneben
 * wäre die Ursache sofort sichtbar gewesen.
 *
 * ⛔ **Bewusst keine Warnung.** Eine Schranke „unter 1 ⇒ Warnung" träfe
 * ausgerechnet Anlagen mit Heizen und Kühlen auf einem Zähler zu Unrecht. eedc
 * zeigt seine Rechnung und überlässt den Schluss dem Anwender.
 *
 * ## Warum die Zahlen aus der Response kommen und nicht hier gerechnet werden
 *
 * Der Nenner ist **nicht** `wp_strom_kwh`: der funktionsfremde Anteil (Kühlen,
 * Lüften, Entfeuchten) ist abgezogen. Die dritte Probe unten hält genau das
 * fest — sie ist der Grund, warum es diese Datei gibt und nicht nur eine Zeile
 * mehr in der Schwesterdatei.
 */

const NOOP: ParkApi = {
  aktiv: false, istGeparkt: () => false, park: () => {}, entparke: () => {},
  zuruecksetzen: () => {}, geparkt: [], registriere: () => () => {}, parkbareAnzahl: 0,
}

/** Rendert den WP-Block und öffnet den Formel-Tooltip der JAZ-Kachel.
 *
 * ⚠ Der `FormelTooltip` baut seinen Inhalt **erst bei `mouseEnter`** — eine
 * Probe, die nur rendert, misst am Gegenstand vorbei. Muster aus
 * `components/finanzen/TKonto.test.tsx`.
 */
function zeigeJazTooltip(
  over: Partial<AktuellerMonatResponse>,
  angezeigterWert: string,
  periode: 'monat' | 'tag' = 'monat',
) {
  const block = baueKomponentenBloecke(aktuellerMonat(2026, 8, over), NOOP, periode)
    .find((b) => b.id === 'k-waermepumpe')
  expect(block, 'Wärme/Klima-Block muss entstehen').toBeDefined()
  render(<>{block!.render(false)}</>)
  // ⚠ Der Trigger umschließt den **Wert**, nicht den Kacheltitel
  // (`KPICard.tsx:91` legt den `FormelTooltip` um `valueContent`). Ein
  // `mouseEnter` auf „JAZ" öffnet gar nichts — gemessen am DOM, nicht geraten.
  fireEvent.mouseEnter(screen.getAllByText(angezeigterWert)[0])
}

/** Dietmars Lage: die Zahl ist unmöglich, die Herleitung zeigt warum. */
const DIETMAR: Partial<AktuellerMonatResponse> = {
  wp_strom_kwh: 313.6,
  wp_waerme_kwh: 209.7,
  wp_jaz: 0.67,
  wp_jaz_zaehler_kwh: 209.7,
  wp_jaz_nenner_kwh: 313.6,
}

describe('A6 — die Arbeitszahl zeigt ihre eingesetzten Werte', () => {
  it('der Tooltip trägt Formel UND Herleitung', () => {
    zeigeJazTooltip(DIETMAR, '0,67')

    expect(screen.getAllByText(/JAZ = Wärme ÷ Strom/).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/209,7 kWh Wärme ÷ 313,6 kWh Strom/).length).toBeGreaterThan(0)
  })

  it('ohne Arbeitszahl steht auch keine Rechnung da', () => {
    // Zweite Regelhälfte, eigene Probe: Die erste wäre auch dann grün, wenn im
    // Sperrfall eine Rechnung ohne Ergebnis erschiene. Präzedenz für die
    // Haltung ist `MonatBilanz.tsx:156` — „0 kWh × — ct/kWh wäre keine
    // Rechnung, sondern Rauschen."
    zeigeJazTooltip({
      wp_strom_kwh: 313.6,
      wp_waerme_kwh: null,
      wp_jaz: null,
      wp_jaz_grund: 'kein Wärmemengenzähler zugeordnet',
      wp_jaz_zaehler_kwh: null,
      wp_jaz_nenner_kwh: null,
    }, '—')

    expect(screen.getAllByText(/kein Wärmemengenzähler zugeordnet/).length).toBeGreaterThan(0)
    expect(screen.queryByText(/kWh Wärme ÷/)).toBeNull()
  })

  it('der Nenner kommt aus der Response, nicht aus wp_strom_kwh', () => {
    // ⭐ **Der eigentliche Gegenstand.** Bei erfasstem Betriebsmodus zieht der
    // Layer den funktionsfremden Strom ab. Würde der Client die Herleitung aus
    // den Anzeigefeldern nachbauen, stünde hier „100 ÷ 300" neben einer 1,00 —
    // eine Rechnung, die nicht auf die Zahl daneben führt (W-3-Klasse, und
    // diese Fläche war dort schon einmal die dritte Stelle).
    zeigeJazTooltip({
      wp_strom_kwh: 300,        // ausgewiesener Gesamtstrom
      wp_waerme_kwh: 100,
      wp_jaz: 1.0,
      wp_jaz_zaehler_kwh: 100,
      wp_jaz_nenner_kwh: 100,   // bereinigt: 200 kWh gingen ins Kühlen
    }, '1,00')

    expect(screen.getAllByText(/100,0 kWh Wärme ÷ 100,0 kWh Strom/).length).toBeGreaterThan(0)
    expect(screen.queryByText(/÷ 300,0 kWh Strom/)).toBeNull()
  })

  it('die Naht: der Tagespfad reicht beide Zahlen durch', () => {
    // ⚑ Ohne diese Probe wäre der Bau in `TagKomponenten.baueTagAlsMonat`
    // ungedeckt — genau die Lücke, die die Schwesterdatei bei N-348 gemessen
    // hat: Rendering-Proben bekommen ihre Daten direkt und bleiben grün, wenn
    // die Durchreichung entfällt.
    const d = baueTagAlsMonat(
      tagWerte('2026-08-29', { wp_strom: 30.0 }),
      [], [],
      { wp_jaz_zaehler_kwh: 42.5, wp_jaz_nenner_kwh: 12.5 } as unknown as TagDetail,
    )

    expect(d.wp_jaz_zaehler_kwh).toBe(42.5)
    expect(d.wp_jaz_nenner_kwh).toBe(12.5)
  })
})
