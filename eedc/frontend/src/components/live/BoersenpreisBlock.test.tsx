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
  it('nennt aktuellen Preis, Ø und Schwelle', () => {
    const kpis = baueKennzahlen(antwort())

    expect(kpis.map((k) => k.title)).toEqual([
      'Aktueller Preis', 'Ø ohne 3 Peaks', 'Günstig-Schwelle',
    ])
    expect(kpis[0].value).toBe('11,50')          // Stunde 3 → 10 + 1,5
    expect(kpis[0].subtitle).toContain('unter der Günstig-Schwelle')
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
