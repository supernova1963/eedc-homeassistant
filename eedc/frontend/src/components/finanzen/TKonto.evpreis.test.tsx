/**
 * N-607 (A-2) im Client — die Herleitung der Eigenverbrauchs-Ersparnis nennt den Preis, mit dem die Zahl entstanden ist.
 *
 * Bei gemessenen Stundenpreisen bewertet das Backend den Eigenverbrauch mit dem EV-gewichteten Ø (`ev_preis_cent`,
 * Herkunft „ev_gemessen"), die Stromrechnung mit dem Bezugs-Ø. T-Konto und Komponenten-Tabelle müssen in ihrer Rechenzeile
 * den EV-Preis einsetzen — sonst stünde „400 kWh × 40 ct" neben 40,00 €. Nachmessung C5: bis dahin ungesichert
 * (`evPreis = netzPreis` blieb grün).
 *
 * Schwesterdateien: backend/tests/test_n607_ev_preis_monatsroute.py, TKonto.test.tsx.
 */
import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import { baueTKonto } from './TKonto'
import { KomponentenFinanzTabelle } from './KomponentenFinanzTabelle'
import { aktuellerMonat } from '../../test/factories'

const D = aktuellerMonat(2025, 7, {
  eigenverbrauch_kwh: 400, ev_ersparnis_euro: 40, einspeise_erloes_euro: 48, einspeisung_kwh: 600,
  netzbezug_kwh: 200, netzbezug_kosten_euro: 90, netzbezug_preis_cent: 30, netzbezug_durchschnittspreis_cent: 40,
  netzbezug_preis_effektiv_cent: 40, ev_preis_cent: 10, ev_preis_herkunft: 'ev_gemessen',
  netto_ertrag_euro: 88, ergebnis_vor_betriebskosten_euro: -2, ergebnis_euro: -2,
})

describe('N-607 — Herleitung mit dem Preis der vermiedenen Stunden', () => {
  it('T-Konto: Eigenverbrauch × EV-Preis, mit Namen', () => {
    const zeile = baueTKonto(D).habenPosten.find((p) => p.label === 'Eigenverbrauch-Ersparnis')!
    expect(zeile.berechnung).toBe('400,0 kWh × 10,00 ct/kWh')
    expect(zeile.formel).toContain('Ø-Preis der vermiedenen Stunden')
  })

  it('Komponenten-Tabelle: der Tooltip der PV-Zeile nennt den EV-Preis', () => {
    const { container } = render(<KomponentenFinanzTabelle d={D} />)
    const titel = [...container.querySelectorAll('[title]')].map((e) => e.getAttribute('title') ?? '')
    expect(titel.some((t) => t.includes('Ø-Preis der vermiedenen Stunden (10,00 ct/kWh)'))).toBe(true)
  })
})
