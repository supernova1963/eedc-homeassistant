/**
 * Komponenten-Liste: die Detailzeile eines PV-Moduls (R22-1).
 *
 * Anlass: PV-Module teilten sich den `case` mit dem Balkonkraftwerk und wurden
 * deshalb mit dessen Parameter-Keys (`leistung_wp`/`anzahl`) gelesen. Die hat
 * ein PV-Modul nie — die Zeile blieb leer, während jeder andere Gerätetyp
 * Werte zeigte (PN 89782, Rainer). Die Tests pinnen beide Hälften: die
 * eigenen Keys werden gelesen UND die kWp kommt als Anzeige-Wert aus
 * `leistung_kwp_effektiv` (A26/N106), sonst fehlt sie bei Altbestand (#229).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, act } from '@testing-library/react'

const listFuerInvestition = vi.fn()
vi.mock('../api/infothek', () => ({
  infothekApi: { listFuerInvestition: (...a: unknown[]) => listFuerInvestition(...a) },
}))

import { TypGeraeteListe } from './InvestitionenTeile'
import type { Investition } from '../types'

const inv = (over: Partial<Investition>): Investition => ({
  id: 11, anlage_id: 1, typ: 'pv-module', bezeichnung: 'Dach Süd-Ost', aktiv: true, ...over,
} as Investition)

/** Rendert und lässt den Infothek-Fetch der Karte auflösen (sonst act()-Warnung). */
async function zeige(i: Investition) {
  render(<TypGeraeteListe geraete={[i]} onEdit={() => {}} onDelete={() => {}} />)
  await act(async () => {})
}

beforeEach(() => {
  vi.clearAllMocks()
  listFuerInvestition.mockResolvedValue([])
})

describe('TypGeraeteListe — PV-Modul-Details', () => {
  it('zeigt kWp, Modulanzahl und Wp aus den PV-eigenen Schlüsseln', async () => {
    await zeige(inv({
      leistung_kwp: 3.6,
      leistung_kwp_effektiv: 3.6,
      parameter: { anzahl_module: 9, modul_leistung_wp: 400 },
    }))

    expect(screen.getByText('3,6 kWp • 9 Module • 400 Wp')).toBeInTheDocument()
  })

  it('#229: kWp nur im parameter-JSON ⇒ der effektive Wert steht trotzdem da', async () => {
    await zeige(inv({
      leistung_kwp: undefined,
      leistung_kwp_effektiv: 7.2,
      parameter: { kwp: 7.2, anzahl_module: 18 },
    }))

    expect(screen.getByText('7,2 kWp • 18 Module')).toBeInTheDocument()
  })

  it('Gegenprobe: die BKW-Schlüssel erzeugen an einem PV-Modul nichts mehr', async () => {
    // Genau der alte Pfad — er darf nicht still weiterlaufen.
    await zeige(inv({ leistung_kwp_effektiv: null, parameter: { leistung_wp: 400, anzahl: 9 } }))

    expect(screen.queryByText(/Module/)).not.toBeInTheDocument()
    expect(screen.queryByText(/Wp/)).not.toBeInTheDocument()
  })

  it('ohne Nennleistung keine 0,0 kWp', async () => {
    await zeige(inv({ leistung_kwp: undefined, leistung_kwp_effektiv: null, parameter: { anzahl_module: 9 } }))

    expect(screen.getByText('9 Module')).toBeInTheDocument()
    expect(screen.queryByText(/kWp/)).not.toBeInTheDocument()
  })

  it('Balkonkraftwerk bleibt bei seinen eigenen Schlüsseln', async () => {
    await zeige(inv({ typ: 'balkonkraftwerk', bezeichnung: 'BKW Garage', parameter: { leistung_wp: 400, anzahl: 2 } }))

    expect(screen.getByText('400 Wp • 2 Module')).toBeInTheDocument()
  })
})
