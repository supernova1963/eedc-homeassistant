/**
 * Abgabe an Dritte (Konzept §9.2, 05.09.2026) — der dritte Weg auf der Verwendungsseite.
 *
 * Cockpit → Monat zeigt ein Gerät der Kategorie „abgabe" in einem eigenen Block
 * „Sonstiges – Abgabe an Dritte" (Abgabe kWh, Erlös €), die Monatsbilanz bekommt
 * die Zeile „Abgabe an Dritte" nur, wo es sie gibt.
 *
 * Schwesterdateien: KomponentenSektionen.test.tsx (die zwei Sonstiges-Blöcke bisher),
 * MonatBilanz.test.tsx (die Bilanzzeilen).
 */
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { baueKomponentenBloecke } from './KomponentenSektionen'
import { MonatBilanz } from './MonatBilanz'
import type { ParkApi } from '../components/park'
import type { AktuellerMonatResponse } from '../api/aktuellerMonat'
import { aktuellerMonat, monatsZeile } from '../test/factories'

const NOOP: ParkApi = {
  aktiv: false, istGeparkt: () => false, park: () => {}, entparke: () => {},
  zuruecksetzen: () => {}, geparkt: [], registriere: () => () => {}, parkbareAnzahl: 0,
}

const mitAbgabe = (over: Partial<AktuellerMonatResponse> = {}) => aktuellerMonat(2025, 7, {
  pv_erzeugung_kwh: 1000, eigenverbrauch_kwh: 576, einspeisung_kwh: 200, netzbezug_kwh: 300,
  abgabe_dritte_kwh: 224,
  sonstiges_geraete: [{ bezeichnung: 'Victron-EG', kategorie: 'abgabe', abgabe_kwh: 224, erloes_euro: 40 }],
  ...over,
})

describe('§9.2 — Abgabe an Dritte in Cockpit → Monat', () => {
  it('eigener Block „Sonstiges – Abgabe an Dritte" mit Abgabe und Erlös', () => {
    const block = baueKomponentenBloecke(mitAbgabe(), NOOP, 'monat').find((b) => b.id === 'k-sonstiges-abgabe')
    expect(block).toBeDefined()
    expect(block!.summary).toContain('224')
    render(<>{block!.render(false)}</>)
    expect(screen.getByText('Victron-EG')).toBeInTheDocument()
    expect(screen.getAllByText(/Abgabe/).length).toBeGreaterThan(0)
    expect(screen.getByText('Erlös')).toBeInTheDocument()
  })

  it('kein Abgabe-Gerät, kein Block — und kein Erzeuger-Block für die Abgabe', () => {
    const bloecke = baueKomponentenBloecke(mitAbgabe({ abgabe_dritte_kwh: null, sonstiges_geraete: [] }), NOOP, 'monat')
    expect(bloecke.find((b) => b.id === 'k-sonstiges-abgabe')).toBeUndefined()
    const mit = baueKomponentenBloecke(mitAbgabe(), NOOP, 'monat')
    expect(mit.find((b) => b.id === 'k-sonstiges-erzeuger')).toBeUndefined()
  })

  it('die Monatsbilanz trägt die Zeile „Abgabe an Dritte" nur mit Abgabe', () => {
    const { unmount } = render(<MonatBilanz d={mitAbgabe()} vm={monatsZeile(2025, 6, {})} glMonStats={null} monatName="Juli" />)
    expect(screen.getAllByText('Abgabe an Dritte').length).toBeGreaterThan(0)
    unmount()
    render(<MonatBilanz d={mitAbgabe({ abgabe_dritte_kwh: null })} vm={monatsZeile(2025, 6, {})} glMonStats={null} monatName="Juli" />)
    expect(screen.queryByText('Abgabe an Dritte')).toBeNull()
  })
})
