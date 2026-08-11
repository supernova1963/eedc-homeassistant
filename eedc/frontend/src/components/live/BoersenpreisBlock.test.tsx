/**
 * Börsenpreis-Block (#335) — Kennzahlen und was der Block sagt, wenn Daten fehlen.
 *
 * Die drei Kennzahlen sind dieselben Größen, die die HA-Sensoren melden. Wichtig
 * ist hier vor allem die Günstig-Zählung: Sie ist **ungekappt** (N-103) und darf
 * nicht wieder auf die fünf Ränge zurückfallen, aus denen sie bis v4.0 kam.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import type { BoersenpreisResponse, BoersenpreisTag } from '../../api/liveDashboard'
import { ThemeProvider } from '../../context/ThemeContext'
import BoersenpreisBlock, { baueKennzahlen } from './BoersenpreisBlock'

/** Der Chart zieht seine Achsenfarben aus dem Theme — ohne Provider wirft er. */
function zeige(daten: BoersenpreisResponse) {
  return render(<ThemeProvider><BoersenpreisBlock daten={daten} /></ThemeProvider>)
}

beforeEach(() => {
  // Der ThemeProvider fragt die Systemeinstellung ab; jsdom kennt matchMedia nicht.
  vi.stubGlobal('matchMedia', vi.fn().mockReturnValue({
    matches: false, media: '', onchange: null,
    addEventListener: vi.fn(), removeEventListener: vi.fn(),
    addListener: vi.fn(), removeListener: vi.fn(), dispatchEvent: vi.fn(),
  }))
})

function tag(datum: string, opts: Partial<BoersenpreisTag> = {}): BoersenpreisTag {
  return {
    datum,
    stunden: Array.from({ length: 24 }, (_, h) => ({
      stunde: h,
      preis_cent: 10 + h * 0.5,
      rang: h < 5 ? h + 1 : 99,
      unter_schwelle: h < 8,
      // Abstand zum Ø dieses Tages (15,00 ct) — wie ihn die Route liefert.
      abstand_cent: Math.round((10 + h * 0.5 - 15.0) * 1000) / 1000,
    })),
    schwelle_cent: 13.5,
    optimierter_durchschnitt_cent: 15.0,
    ...opts,
  }
}

function antwort(over: Partial<BoersenpreisResponse> = {}): BoersenpreisResponse {
  return {
    anlage_id: 1,
    markt: 'DE',
    tage: [tag('2026-08-06'), tag('2026-08-07')],
    aktuelle_stunde: 3,
    heute: '2026-08-06',
    hinweis: null,
    ...over,
  }
}

describe('baueKennzahlen', () => {
  it('nennt aktuellen Preis, Ø, Schwelle und den ct-Abstand', () => {
    const kpis = baueKennzahlen(antwort())

    // Der Abstand steht am ENDE — die drei seit v4.0.10 ausgelieferten Kacheln
    // behalten ihre Position (N-173).
    expect(kpis.map((k) => k.title)).toEqual([
      'Aktueller Preis', 'Ø ohne 3 Peaks', 'Günstig-Schwelle', 'Abstand zum Ø',
    ])
    expect(kpis[0].value).toBe('11,50')          // Stunde 3 → 10 + 1,5
    expect(kpis[0].subtitle).toContain('unter der Günstig-Schwelle')
  })

  it('zeigt den ct-Abstand der laufenden Stunde mit Vorzeichen (N-173)', () => {
    // Stunde 3: 11,50 ct gegen den Ø 15,00 ct ⇒ −3,50 ct/kWh. Diese Zahl gilt
    // unverändert auch für einen Endpreis mit festen Bestandteilen — genau
    // deshalb gibt es sie neben der Prozentgröße.
    const abstand = baueKennzahlen(antwort()).at(-1)!
    expect(abstand.title).toBe('Abstand zum Ø')
    expect(abstand.value).toBe('-3,50')
    expect(abstand.unit).toBe('ct/kWh')
    expect(abstand.subtitle).toContain('unter dem Ø')
  })

  it('sagt „über dem Ø", wenn die laufende Stunde teurer ist', () => {
    const abstand = baueKennzahlen(antwort({ aktuelle_stunde: 20 })).at(-1)!
    expect(abstand.value).toBe('5,00')           // 20,00 − 15,00
    expect(abstand.subtitle).toContain('über dem Ø')
  })

  it('lässt die Abstands-Kachel weg, wenn die Route sie nicht liefert', () => {
    // Alt-Stand einer laufenden Box, die noch ohne das Feld antwortet: dann
    // fehlt die Kachel, statt „0,00 ct Abstand" zu behaupten.
    const ohneAbstand = tag('2026-08-06')
    ohneAbstand.stunden = ohneAbstand.stunden.map((s) => ({ ...s, abstand_cent: null }))
    const kpis = baueKennzahlen(antwort({ tage: [ohneAbstand] }))
    expect(kpis.map((k) => k.title)).not.toContain('Abstand zum Ø')
  })

  it('zählt günstige Stunden ungekappt (N-103)', () => {
    // Acht Stunden liegen unter der Schwelle, nur fünf tragen einen Rang. Die
    // Kachel muss acht sagen — die alte, an den Rang gebundene Zahl war als
    // Divisor in einer Automation zu klein.
    const kpis = baueKennzahlen(antwort())
    expect(kpis[2].subtitle).toContain('8 Stunden')
  })

  it('sagt es, wenn der aktuelle Preis über der Schwelle liegt', () => {
    const kpis = baueKennzahlen(antwort({ aktuelle_stunde: 20 }))
    expect(kpis[0].subtitle).toContain('über der Günstig-Schwelle')
  })

  it('lässt den aktuellen Preis weg, wenn seine Stunde fehlt', () => {
    // Umstellungstag: die Stunde 2 gibt es nicht. Dann steht dort auch keine
    // Kachel — statt einer 0 oder des Nachbarpreises.
    const ohneStunde2 = tag('2026-08-06')
    ohneStunde2.stunden = ohneStunde2.stunden.filter((s) => s.stunde !== 2)
    const kpis = baueKennzahlen(antwort({ tage: [ohneStunde2], aktuelle_stunde: 2 }))

    expect(kpis.map((k) => k.title)).toEqual(['Ø ohne 3 Peaks', 'Günstig-Schwelle'])
  })

  it('zeigt keine Kennzahlen, wenn nur morgen vorliegt', () => {
    // Sie beziehen sich auf heute; die von morgen wären eine andere Aussage
    // unter demselben Titel.
    const kpis = baueKennzahlen(antwort({ tage: [tag('2026-08-07')], heute: '2026-08-06' }))
    expect(kpis).toEqual([])
  })
})

describe('BoersenpreisBlock', () => {
  it('zeigt den Hinweis, wenn morgen noch fehlt', () => {
    zeige(antwort({
      tage: [tag('2026-08-06')],
      hinweis: 'Für morgen liegen noch keine Börsenpreise vor — die Day-Ahead-Auktion veröffentlicht sie gegen 13:00 Uhr.',
    }))

    expect(screen.getByText(/Day-Ahead-Auktion veröffentlicht sie gegen 13:00/)).toBeInTheDocument()
  })

  it('nennt die Marktzone und dass die Preise netto sind', () => {
    // Ohne diesen Satz hält jemand die Kurve für seinen Lieferantenpreis.
    zeige(antwort({ markt: 'AT' }))

    expect(screen.getByText(/EPEX Österreich/)).toBeInTheDocument()
    expect(screen.getByText(/ohne Steuern, Abgaben und Netzentgelte/)).toBeInTheDocument()
  })

  it('bleibt ohne Preise stumm bis auf den Grund', () => {
    zeige(antwort({
      tage: [], aktuelle_stunde: 3, hinweis: 'Börsenpreise sind derzeit nicht abrufbar.',
    }))

    expect(screen.getByText(/nicht abrufbar/)).toBeInTheDocument()
    expect(screen.queryByText('Aktueller Preis')).not.toBeInTheDocument()
  })
})
