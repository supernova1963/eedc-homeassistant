import { describe, it, expect, beforeEach } from 'vitest'
import { render, screen, fireEvent, within } from '@testing-library/react'
import { WerteTabelle } from './WerteTabelle'
import type { MonatsZeitreihe } from '../../pages/auswertung/types'
import type { TagWerte } from '../../api/energie_profil'
import { monatsZeile, tagesZeile } from '../../lib/werte'

function mz(monat: number, jahr: number, over: Partial<MonatsZeitreihe> = {}): MonatsZeitreihe {
  return {
    name: `${monat}/${jahr}`, jahr, monat,
    erzeugung: 100 * monat, eigenverbrauch: 60, einspeisung: 40, netzbezug: 30,
    gesamtverbrauch: 90, direktverbrauch: 50,
    autarkie: 70, evQuote: 60, spezErtrag: 80,
    globalstrahlung: null, sonnenstunden: null,
    speicher_ladung: null, speicher_entladung: null, speicher_effizienz: null,
    wp_waerme: null, wp_strom: null, wp_cop: null,
    wp_strom_heizen: null, wp_strom_warmwasser: null,
    wp_waerme_heizen: null, wp_waerme_warmwasser: null,
    eauto_km: null, eauto_ladung: null, eauto_pv_anteil: null,
    wallbox_ladung: null, wallbox_pv_ladung: null, wallbox_pv_anteil: null,
    einspeise_erloes: 5, ev_ersparnis: 12, netzbezug_kosten: 9,
    netto_ertrag: 8, netto_bilanz: 8, netzbezug_preis_cent: null, co2_einsparung: 25,
    ...over,
  }
}

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

const monatsRows = [mz(1, 2025), mz(2, 2025)].map(monatsZeile)

describe('WerteTabelle', () => {
  beforeEach(() => localStorage.clear())

  it('Steuerung (Picker/CSV) + Default-Spalten + Footer — überall identisch', () => {
    render(<WerteTabelle rows={monatsRows} granularitaet="monat" />)
    expect(screen.getByRole('button', { name: /Spalten/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /CSV/ })).toBeInTheDocument()
    expect(screen.getByText(/PV-Erzeugung \(kWh\)/)).toBeInTheDocument()
    expect(screen.getByText('2 Monate')).toBeInTheDocument()
  })

  it('Spalten-Picker blendet eine Spalte aus', () => {
    render(<WerteTabelle rows={monatsRows} granularitaet="monat" />)
    expect(screen.getByText(/PV-Erzeugung \(kWh\)/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Spalten/ }))
    const pickerLabel = screen.getByText('PV-Erzeugung').closest('label')!
    fireEvent.click(within(pickerLabel).getByRole('checkbox'))
    expect(screen.queryByText(/PV-Erzeugung \(kWh\)/)).not.toBeInTheDocument()
  })

  it('Cockpit-Platzierung hat dieselbe Funktion (Picker/CSV) + Cross-Link', () => {
    render(<WerteTabelle rows={monatsRows} granularitaet="monat" alleWerteHref="/v4/auswertungen/tabelle" />)
    expect(screen.getByRole('button', { name: /Spalten/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /CSV/ })).toBeInTheDocument()
    const link = screen.getByRole('link', { name: /Alle Werte/ })
    expect(link).toHaveAttribute('href', '/v4/auswertungen/tabelle')
  })

  it('Vergleich-Toggle erscheint bei Vergleichs-Daten und schaltet Δ frei', () => {
    render(
      <WerteTabelle
        rows={monatsRows}
        vorjahrRows={[mz(1, 2024), mz(2, 2024)].map(monatsZeile)}
        granularitaet="monat"
        jahrLabel={2025}
        vergleichLabel={2024}
      />,
    )
    const toggle = screen.getByRole('button', { name: /Vergleich 2024/ })
    fireEvent.click(toggle)
    expect(screen.getAllByText(/[▲▼=]/).length).toBeGreaterThan(0)
  })

  it('Spalten-Sortierung: Klick auf Metrik-Header sortiert absteigend, Default bleibt chronologisch (IST-Parität)', () => {
    render(<WerteTabelle rows={monatsRows} granularitaet="monat" />)
    // Default chronologisch aufsteigend: Jan (erzeugung 100) vor Feb (200).
    let rows = screen.getAllByRole('row')
    expect(within(rows[1]).getByText('Jan 2025')).toBeInTheDocument()
    // Klick auf „PV-Erzeugung" → absteigend nach Wert → Feb (200) zuerst.
    fireEvent.click(screen.getByRole('button', { name: /PV-Erzeugung/ }))
    rows = screen.getAllByRole('row')
    expect(within(rows[1]).getByText('Feb 2025')).toBeInTheDocument()
  })

  it('Tages-Granularität: Tag-native Spalte sichtbar, Footer „Tage", kein WP-Wärme', () => {
    const tage = [tw('2026-05-10'), tw('2026-05-11')].map(tagesZeile)
    render(<WerteTabelle rows={tage} granularitaet="tag" />)
    // Tag-natives Default-Feld (Überschuss / Peak PV) erscheint
    expect(screen.getByText(/Überschuss \(kWh\)/)).toBeInTheDocument()
    expect(screen.getByText('2 Tage')).toBeInTheDocument()
    // Picker zeigt keinen monat-only Eintrag „WP Wärme"
    fireEvent.click(screen.getByRole('button', { name: /Spalten/ }))
    expect(screen.queryByText('WP Wärme')).not.toBeInTheDocument()
  })

  it('Tages-Vergleich matcht über Tag-im-Monat (Vergleichsmonat)', () => {
    const aktuell = [tw('2026-05-10', { erzeugung: 30 })].map(tagesZeile)
    const vergleich = [tw('2026-04-10', { erzeugung: 20 })].map(tagesZeile)
    render(
      <WerteTabelle
        rows={aktuell}
        vorjahrRows={vergleich}
        granularitaet="tag"
        jahrLabel="Mai"
        vergleichLabel="Apr"
      />,
    )
    fireEvent.click(screen.getByRole('button', { name: /Vergleich Apr/ }))
    expect(screen.getAllByText(/[▲▼=]/).length).toBeGreaterThan(0)
  })
})
