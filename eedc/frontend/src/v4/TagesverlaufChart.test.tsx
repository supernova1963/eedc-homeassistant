import { describe, it, expect } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { TagesverlaufChart, baueVerlaufDaten, baueFlussDaten } from './TagesverlaufChart'
import type { TagWerte } from '../api/energie_profil'

function tw(datum: string, over: Partial<TagWerte> = {}): TagWerte {
  return {
    datum, stunden_verfuegbar: 24, datenquelle: 'ha_sensor',
    erzeugung: 30, eigenverbrauch: 18, einspeisung: 12, netzbezug: 6,
    gesamtverbrauch: 24, direktverbrauch: 15,
    autarkie: 75, evQuote: 60, spezErtrag: 3,
    speicher_ladung: null, speicher_entladung: null, speicher_effizienz: null,
    wp_strom: null,
    einspeise_erloes: 1, ev_ersparnis: 2, netzbezug_kosten: 1.5,
    netto_ertrag: 3, netto_bilanz: 1.5, co2_einsparung: 11.4,
    ueberschuss_kwh: 8, defizit_kwh: 2, peak_pv_kw: 6.2,
    peak_netzbezug_kw: 1.1, peak_einspeisung_kw: 4.0,
    performance_ratio: 0.85, batterie_vollzyklen: 0.4,
    temperatur_min_c: 10, temperatur_max_c: 22,
    strahlung_summe_wh_m2: 5000, boersenpreis_avg_cent: 9.5,
    boersenpreis_min_cent: -1, negative_preis_stunden: 1,
    einspeisung_neg_preis_kwh: 0,
    ...over,
  }
}

describe('baueVerlaufDaten', () => {
  it('eine Säule je Tag, Netzbezug negativ, aufsteigend sortiert', () => {
    const d = baueVerlaufDaten([tw('2026-05-11', { netzbezug: 6 }), tw('2026-05-10')])
    expect(d.map((p) => p.tag)).toEqual([10, 11])
    expect(d[0].eigenverbrauch).toBe(18)
    expect(d[0].einspeisung).toBe(12)
    expect(d[0].netzbezug).toBe(-6) // Senke nach unten
  })
})

describe('baueFlussDaten', () => {
  it('Erzeugung = EV+Einspeisung, Verbrauch = EV+Netzbezug (Monats-Σ)', () => {
    const f = baueFlussDaten([tw('2026-05-10'), tw('2026-05-11')])
    const erz = f.find((b) => b.name === 'Erzeugung')!
    const vbr = f.find((b) => b.name === 'Verbrauch')!
    expect(erz.eigenverbrauch).toBe(36) // 2 × 18
    expect(erz.einspeisung).toBe(24)    // 2 × 12
    expect(erz.netzbezug).toBe(0)
    expect(vbr.eigenverbrauch).toBe(36)
    expect(vbr.netzbezug).toBe(12)      // 2 × 6
    expect(vbr.einspeisung).toBe(0)
  })
})

describe('TagesverlaufChart', () => {
  it('Linsen-Toggle schaltet Tagesverlauf ⇄ Monats-Fluss', () => {
    render(<TagesverlaufChart tage={[tw('2026-05-10'), tw('2026-05-11')]} />)
    const fluss = screen.getByRole('button', { name: /Monats-Fluss/ })
    const verlauf = screen.getByRole('button', { name: /Tagesverlauf/ })
    expect(verlauf).toHaveClass('shadow-sm') // default aktiv
    fireEvent.click(fluss)
    expect(fluss).toHaveClass('shadow-sm')
  })

  it('leerer Monat → Hinweis statt Chart', () => {
    render(<TagesverlaufChart tage={[]} />)
    expect(screen.getByText(/Keine Tagesdaten/)).toBeInTheDocument()
  })
})
