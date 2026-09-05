/**
 * B4 (05.09.2026, C-2) — die Blockfabrik zeigt Herkunft und Vorbehalt (SOLL §6 vom 05.09.).
 *
 * Eine aus Strom × JAZ **geschätzte** Wärme stand in Cockpit → Monat/Jahr wie eine Messung;
 * nur die gesperrte JAZ verriet es. Jetzt steht die Herkunft aus dem Layer unter der
 * Wärme-Kachel, der Vorbehalt unter der Ersparnis — dieselben Worte wie im Hub (B3),
 * für Monat und Jahr aus EINER Fabrik.
 *
 * Schwesterdateien: KomponentenSektionen.soll-waerme-klima.test.tsx (S2/S3 derselben
 * Fabrik), JahrAggregat.b4.test.tsx (woher das Jahr die Felder bekommt).
 */
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { baueKomponentenBloecke } from './KomponentenSektionen'
import type { ParkApi } from '../components/park'
import type { AktuellerMonatResponse } from '../api/aktuellerMonat'
import { aktuellerMonat } from '../test/factories'

const NOOP: ParkApi = {
  aktiv: false, istGeparkt: () => false, park: () => {}, entparke: () => {},
  zuruecksetzen: () => {}, geparkt: [], registriere: () => () => {}, parkbareAnzahl: 0,
}

function rendere(over: Partial<AktuellerMonatResponse>, periode: 'monat' | 'jahr' = 'monat') {
  const block = baueKomponentenBloecke(aktuellerMonat(2025, 7, over), NOOP, periode)
    .find((b) => b.id === 'k-waermepumpe')
  expect(block).toBeDefined()
  render(<>{block!.render(false)}</>)
}

const HERKUNFT = 'geschätzt: Strom × JAZ 3,5'
const VORBEHALT = 'Wärme geschätzt — Ersparnis und CO₂ folgen aus der Schätzung'

describe('B4/C-2 — Herkunft unter der Wärme, Vorbehalt unter der Ersparnis', () => {
  it('Monat: geschätzte Wärme sagt es', () => {
    rendere({ wp_strom_kwh: 1000, wp_waerme_kwh: 3500, wp_jaz: null,
      wp_jaz_grund: 'Wärme ist gerechnet, nicht gemessen', wp_waerme_abgeleitet: true,
      wp_waerme_herkunft: HERKUNFT, wp_ersparnis_euro: 166.67, wp_ersparnis_vorbehalt: VORBEHALT })
    expect(screen.getByText(HERKUNFT)).toBeInTheDocument()
    expect(screen.getByText(VORBEHALT)).toBeInTheDocument()
  })

  it('Jahr: dieselbe Fabrik, dieselben Worte', () => {
    rendere({ wp_strom_kwh: 12000, wp_waerme_kwh: 42000, wp_jaz: null,
      wp_jaz_grund: 'Wärme ist gerechnet, nicht gemessen', wp_waerme_abgeleitet: true,
      wp_waerme_herkunft: HERKUNFT, wp_ersparnis_euro: 2000, wp_ersparnis_vorbehalt: VORBEHALT }, 'jahr')
    expect(screen.getByText(HERKUNFT)).toBeInTheDocument()
    expect(screen.getByText(VORBEHALT)).toBeInTheDocument()
  })

  it('gemessene Wärme bleibt ohne Zusatz (vertraute Anzeige)', () => {
    rendere({ wp_strom_kwh: 1000, wp_waerme_kwh: 3500, wp_jaz: 3.5, wp_waerme_abgeleitet: false,
      wp_waerme_herkunft: 'gemessen', wp_ersparnis_euro: 166.67, wp_ersparnis_vorbehalt: null })
    expect(screen.queryByText(/geschätzt|gemessen$/)).toBeNull()
  })

  it('bivalent (F12): die Zahl bleibt, der Vorbehalt steht darunter', () => {
    const v = 'zweiter Erzeuger am Wärmezähler — Ersparnis und CO₂ enthalten dessen Wärme'
    rendere({ wp_strom_kwh: 1000, wp_waerme_kwh: 3500, wp_jaz: null,
      wp_jaz_grund: 'zweiter Erzeuger am Wärmezähler', wp_ersparnis_euro: 166.67, wp_ersparnis_vorbehalt: v })
    expect(screen.getByText(/166,67/)).toBeInTheDocument()
    expect(screen.getByText(v)).toBeInTheDocument()
  })
})
