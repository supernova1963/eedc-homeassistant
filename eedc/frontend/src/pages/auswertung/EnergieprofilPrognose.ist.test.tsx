/**
 * Stundenwerte-Tabelle: IST-Spalte für den heutigen Tag (R22-6, PN 89768).
 *
 * Rainer: „Mit den IST-Einträgen meinte ich die bisherigen Stunden. Dann müsste
 * man nicht in die Auswertungen springen." Die Spalte ist deshalb optional und
 * erscheint nur, wenn der Aufrufer gemessene Stunden mitgibt — für morgen gibt
 * es keine. Ohne das Prop muss die Tabelle unverändert aussehen.
 */
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'

import { PrognoseTabelle } from './EnergieprofilPrognose'
import type { TagesPrognose } from '../../api/energie_profil'

const stunde = (h: number, pv: number) => ({
  stunde: h, pv_kw: pv, verbrauch_kw: 0.4, netto_kw: pv - 0.4,
  netzbezug_kw: 0, einspeisung_kw: pv, soc_prozent: null,
})

const daten = {
  datum: '2026-07-27',
  stunden: [stunde(9, 2), stunde(10, 3), stunde(11, 4)],
  pv_summe_kwh: 9, verbrauch_summe_kwh: 1.2,
  netzbezug_summe_kwh: 0, einspeisung_summe_kwh: 9,
  eigenverbrauch_kwh: 1.2, autarkie_prozent: 100,
  speicher_kapazitaet_kwh: null, verbrauch_basis: 'historisch',
  pv_quelle: 'eedc', daten_tage: 30, hinweise: [],
} as unknown as TagesPrognose

describe('PrognoseTabelle — IST-Spalte', () => {
  it('ohne istStunden bleibt die Tabelle wie bisher', () => {
    render(<PrognoseTabelle daten={daten} />)

    expect(screen.queryByText('PV IST')).not.toBeInTheDocument()
  })

  it('zeigt gemessene Stunden und lässt künftige leer', () => {
    const { container } = render(
      <PrognoseTabelle
        daten={daten}
        istStunden={[{ stunde: 9, kw: 1.8 }, { stunde: 10, kw: 2.6 }, { stunde: 11, kw: null }]}
        aktuelleStunde={11}
      />,
    )

    expect(screen.getByText('PV IST')).toBeInTheDocument()
    expect(screen.getByText('1,80')).toBeInTheDocument()
    expect(screen.getByText('2,60')).toBeInTheDocument()
    // Σ nur über das Gemessene — 1,8 + 2,6, die offene Stunde zählt nicht mit.
    expect(container.textContent).toMatch(/4,4/)
  })

  it('die Prognose-Spalte bleibt daneben stehen', () => {
    render(
      <PrognoseTabelle daten={daten} istStunden={[{ stunde: 9, kw: 1.8 }]} aktuelleStunde={10} />,
    )

    expect(screen.getByText('PV')).toBeInTheDocument()
    // 2,00 = Prognose der 9-Uhr-Stunde; sie steht weiter da, neben dem IST 1,80.
    expect(screen.getAllByText('2,00').length).toBeGreaterThan(0)
    expect(screen.getByText('1,80')).toBeInTheDocument()
  })
})
