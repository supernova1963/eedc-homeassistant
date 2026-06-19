import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { isValidElement } from 'react'
import { finanzTeaserBlock, communityBlock, MonatHeader } from './MonatRahmen'
import type { AktuellerMonatResponse } from '../api/aktuellerMonat'
import type { MonatsVergleich } from '../api/community'

const d = {
  netto_ertrag_euro: 128, einspeise_erloes_euro: 15, ev_ersparnis_euro: 120, netzbezug_kosten_euro: 7,
  autarkie_prozent: 61, eigenverbrauch_quote_prozent: 54, einspeisung_kwh: 189, netzbezug_kwh: 143,
  feld_quellen: {},
} as unknown as AktuellerMonatResponse

describe('finanzTeaserBlock', () => {
  it('Block mit Netto-Ertrag-Summary + Cross-Link-Heimat', () => {
    const b = finanzTeaserBlock(d)
    expect(b.id).toBe('finanzen')
    expect(b.summary).toMatch(/\+128,00 € Netto-Ertrag/)
  })

  it('C3: Tarif-Info-Zeile zeigt flexiblen Netzbezug-Ø + Einspeisepreis', () => {
    const dd = { ...d, netzbezug_durchschnittspreis_cent: 32.5, einspeise_preis_cent: 8.2 } as AktuellerMonatResponse
    const block = finanzTeaserBlock(dd)
    const node = block.render(false)
    if (!isValidElement(node)) throw new Error('render() ergab kein Element')
    render(node)
    expect(screen.getByText(/32,50 ct\/kWh/)).toBeInTheDocument()
    expect(screen.getByText(/\(flex\)/)).toBeInTheDocument()
    expect(screen.getByText(/Einspeisung 8,20 ct\/kWh/)).toBeInTheDocument()
  })

  it('C3: ohne Tarif-Felder keine Tarif-Zeile', () => {
    const node = finanzTeaserBlock(d).render(false)
    if (!isValidElement(node)) throw new Error('render() ergab kein Element')
    render(node)
    expect(screen.queryByText(/ct\/kWh/)).not.toBeInTheDocument()
  })
})

describe('MonatHeader — C1/C2 Sicht-Aktionen', () => {
  it('C1: Aktualisieren nur im laufenden Monat', () => {
    const onReload = vi.fn()
    const { rerender } = render(<MonatHeader titel="Mai 2026" laufend d={d} onReload={onReload} />)
    screen.getByRole('button', { name: /Aktualisieren/ }).click()
    expect(onReload).toHaveBeenCalledOnce()
    rerender(<MonatHeader titel="Apr 2026" laufend={false} d={d} onReload={onReload} />)
    expect(screen.queryByRole('button', { name: /Aktualisieren/ })).not.toBeInTheDocument()
  })

  it('C2: Abschluss-Cross-Link nur laufend + offene Abschlüsse, zeigt auf Einstellungen/Daten', () => {
    render(<MonatHeader titel="Mai 2026" laufend d={d} zeigeAbschlussLink />)
    const link = screen.getByRole('link', { name: /Abschluss starten/ })
    expect(link).toHaveAttribute('href', '#/einstellungen/monatsdaten')
  })

  it('C2: kein Abschluss-Link wenn keine offenen Abschlüsse', () => {
    render(<MonatHeader titel="Mai 2026" laufend d={d} zeigeAbschlussLink={false} />)
    expect(screen.queryByRole('link', { name: /Abschluss starten/ })).not.toBeInTheDocument()
  })
})

describe('communityBlock — data-gated (O4)', () => {
  it('null wenn keine Anlagen im Monat', () => {
    const v = { anzahl_anlagen: 0 } as MonatsVergleich
    expect(communityBlock(v, d, 'Mai', 2026)).toBeNull()
  })

  it('Block mit Anlagenzahl-Summary wenn Daten vorhanden', () => {
    const v = {
      anzahl_anlagen: 2,
      autarkie: { durchschnitt: 60, median: 58, min: 40, max: 80, anzahl_anlagen: 2 },
    } as MonatsVergleich
    const b = communityBlock(v, d, 'Mai', 2026)
    expect(b).not.toBeNull()
    expect(b!.id).toBe('community')
    expect(b!.summary).toMatch(/2 Anlagen im Mai/)
  })

  it('Singular bei genau einer Anlage', () => {
    const v = { anzahl_anlagen: 1 } as MonatsVergleich
    expect(communityBlock(v, d, 'Mai', 2026)!.summary).toMatch(/1 Anlage im Mai/)
  })

  it('spez.-Ertrag-Abweichung zum Median in der Summary (abs + rel)', () => {
    const v = { anzahl_anlagen: 5, spez_ertrag: { median: 131 } } as unknown as MonatsVergleich
    const dd = { ...d, spez_ertrag: 142 } as AktuellerMonatResponse
    // 142 − 131 = +11 ; 11 / 131 = +8 %
    expect(communityBlock(v, dd, 'Mai', 2026)!.summary).toMatch(/spez\. Ertrag 142 kWh\/kWp \(\+11 \/ \+8 % vs\. Median\)/)
  })

  it('ohne eigenen spez. Ertrag keine Abweichung in der Summary', () => {
    const v = { anzahl_anlagen: 5, spez_ertrag: { median: 131 } } as unknown as MonatsVergleich
    expect(communityBlock(v, d, 'Mai', 2026)!.summary).not.toMatch(/spez\. Ertrag/)
  })
})
