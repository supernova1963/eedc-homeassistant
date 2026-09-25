/**
 * N-557 — „Ladung gesamt" im E-Mobilitäts-Block zählt die externe Ladung mit.
 *
 * Konzept Heimladung/Fahrverbrauch, Regel 10: „Ladung gesamt" ist Heim + Extern,
 * soweit Extern bekannt ist, mit Untertitel „davon extern … kWh"; der PV-Anteil
 * daneben bleibt auf die HEIMladung bezogen („PV-Anteil (Heim)"). Bis zum
 * 25.09.2026 zeigte die Kachel nur die Heimladung, der E-Auto-Hub dagegen
 * Heim + Extern — zwei Zahlen unter demselben Namen (Johnny_1993 #375).
 *
 * Gerendert, nicht am Block-Objekt abgelesen (die Kacheln entstehen erst in
 * `render()`, s. `KomponentenSektionen.speicher-kapazitaet.test.tsx`).
 */
import { describe, it, expect, afterEach } from 'vitest'
import { render, screen, cleanup } from '@testing-library/react'
import { baueKomponentenBloecke } from './KomponentenSektionen'
import type { ParkApi } from '../components/park'
import type { AktuellerMonatResponse } from '../api/aktuellerMonat'
import { aktuellerMonat } from '../test/factories'

const NOOP: ParkApi = {
  aktiv: false, istGeparkt: () => false, park: () => {}, entparke: () => {},
  zuruecksetzen: () => {}, geparkt: [], registriere: () => () => {}, parkbareAnzahl: 0,
}

afterEach(() => cleanup())

function emobBlock(over: Partial<AktuellerMonatResponse>, periode: 'tag' | 'monat' | 'jahr' = 'monat') {
  const block = baueKomponentenBloecke(aktuellerMonat(2025, 3, over), NOOP, periode)
    .find((b) => b.id === 'k-emob')
  expect(block, 'E-Mobilitäts-Block muss entstehen').toBeDefined()
  cleanup()
  render(<>{block!.render(false)}</>)
  return block!
}

const MAERZ: Partial<AktuellerMonatResponse> = {
  emob_ladung_kwh: 250, emob_ladung_pv_kwh: 100, emob_ladung_netz_kwh: 150,
  emob_ladung_extern_kwh: 50, emob_ladung_gesamt_kwh: 300, emob_km: 1500,
  hat_emobilitaet: true,
}

describe('E-Mobilität — „Ladung gesamt" = Heim + Extern (N-557)', () => {
  it('zeigt 300 kWh mit „davon extern 50 kWh"', () => {
    const block = emobBlock(MAERZ)
    expect(screen.getByText('Ladung gesamt')).toBeInTheDocument()
    expect(screen.getByText('300')).toBeInTheDocument()
    expect(screen.getByText('davon extern 50 kWh')).toBeInTheDocument()
    expect(block.summary).toMatch(/^300 kWh geladen/)
  })

  it('der PV-Anteil bleibt auf die Heimladung bezogen (100 von 250 = 40 %)', () => {
    emobBlock(MAERZ)
    expect(screen.getByText('PV-Anteil (Heim)')).toBeInTheDocument()
    expect(screen.getByText('40')).toBeInTheDocument()
  })

  it('ohne Extern kein Untertitel, und am Tag (ohne Feld) ist es die Heimladung', () => {
    emobBlock({ ...MAERZ, emob_ladung_extern_kwh: null, emob_ladung_gesamt_kwh: 250 })
    expect(screen.queryByText(/davon extern/)).toBeNull()
    emobBlock({ ...MAERZ, emob_ladung_extern_kwh: null, emob_ladung_gesamt_kwh: undefined }, 'tag')
    expect(screen.getByText('250')).toBeInTheDocument()
  })
})
