import { describe, it, expect } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { TagesverlaufChart, baueChartDaten } from './TagesverlaufChart'
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

describe('baueChartDaten', () => {
  it('eine Zeile je Tag, aufsteigend sortiert, Netzbezug positiv, mit Direktverbrauch + Speicher-Entladung', () => {
    const d = baueChartDaten([tw('2026-05-11'), tw('2026-05-10', { speicher_entladung: 3 })])
    expect(d.map((p) => p.tag)).toEqual([10, 11])
    expect(d[0].eigenverbrauch).toBe(18)
    expect(d[0].einspeisung).toBe(12)
    expect(d[0].netzbezug).toBe(6)         // positiv (gestapelt, kein Vorzeichen-Flip)
    expect(d[0].direktverbrauch).toBe(15)
    expect(d[0].speicherEntladung).toBe(3)
  })

  it('speicher_entladung null → 0', () => {
    const d = baueChartDaten([tw('2026-05-10')])
    expect(d[0].speicherEntladung).toBe(0)
  })
})

describe('TagesverlaufChart', () => {
  it('Toggle Erzeugung ⇄ Verbrauch ändert die Stapel-Beschreibung (Direktverbrauch)', () => {
    render(<TagesverlaufChart tage={[tw('2026-05-10')]} />)
    expect(screen.getByText(/Eigenverbrauch \+ Einspeisung = PV-Erzeugung/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Verbrauch' }))
    expect(screen.getByText(/Direktverbrauch \+ Speicher-Entladung \+ Netzbezug = Gesamtverbrauch/)).toBeInTheDocument()
  })

  it('Autarkie %-Toggle vorhanden', () => {
    render(<TagesverlaufChart tage={[tw('2026-05-10')]} />)
    expect(screen.getByRole('button', { name: 'Autarkie %' })).toBeInTheDocument()
  })

  it('leerer Monat → Hinweis statt Chart', () => {
    render(<TagesverlaufChart tage={[]} />)
    expect(screen.getByText(/Keine Tagesdaten/)).toBeInTheDocument()
  })
})
