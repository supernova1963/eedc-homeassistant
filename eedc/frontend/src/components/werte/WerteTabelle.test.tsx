import { describe, it, expect, beforeEach } from 'vitest'
import { render, screen, fireEvent, within } from '@testing-library/react'
import { WerteTabelle } from './WerteTabelle'
import type { MonatsZeitreihe } from '../../pages/auswertung/types'

function mz(monat: number, jahr: number, over: Partial<MonatsZeitreihe> = {}): MonatsZeitreihe {
  return {
    name: `${monat}/${jahr}`, jahr, monat,
    erzeugung: 100 * monat, eigenverbrauch: 60, einspeisung: 40, netzbezug: 30,
    gesamtverbrauch: 90, direktverbrauch: 50,
    autarkie: 70, evQuote: 60, spezErtrag: 80,
    speicher_ladung: null, speicher_entladung: null, speicher_effizienz: null,
    wp_waerme: null, wp_strom: null, wp_cop: null,
    eauto_km: null, eauto_ladung: null, eauto_pv_anteil: null,
    einspeise_erloes: 5, ev_ersparnis: 12, netzbezug_kosten: 9,
    netto_ertrag: 8, netto_bilanz: 8, co2_einsparung: 25,
    ...over,
  }
}

const rows = [mz(1, 2025), mz(2, 2025)]

describe('WerteTabelle', () => {
  beforeEach(() => localStorage.clear())

  it('werkbank: Steuerung + Default-Spalten + Footer', () => {
    render(<WerteTabelle rows={rows} modus="werkbank" />)
    expect(screen.getByRole('button', { name: /Spalten/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /CSV/ })).toBeInTheDocument()
    // Default-sichtbare Spalte
    expect(screen.getByText(/PV-Erzeugung \(kWh\)/)).toBeInTheDocument()
    // Footer-Aggregat
    expect(screen.getByText('2 Monate')).toBeInTheDocument()
  })

  it('werkbank: Spalten-Picker blendet eine Spalte aus', () => {
    render(<WerteTabelle rows={rows} modus="werkbank" />)
    expect(screen.getByText(/PV-Erzeugung \(kWh\)/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Spalten/ }))
    // Checkbox „PV-Erzeugung" im Picker abwählen
    const pickerLabel = screen.getByText('PV-Erzeugung').closest('label')!
    fireEvent.click(within(pickerLabel).getByRole('checkbox'))
    expect(screen.queryByText(/PV-Erzeugung \(kWh\)/)).not.toBeInTheDocument()
  })

  it('embed: read-only (kein Picker/CSV) + Cross-Link + fixe Spalten', () => {
    render(<WerteTabelle rows={rows} modus="embed" embedKeys={['erzeugung']} alleWerteHref="/v4/auswertungen/tabelle" />)
    expect(screen.queryByRole('button', { name: /Spalten/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /CSV/ })).not.toBeInTheDocument()
    expect(screen.getByText(/PV-Erzeugung \(kWh\)/)).toBeInTheDocument()
    // andere Spalte NICHT da
    expect(screen.queryByText(/Einspeisung \(kWh\)/)).not.toBeInTheDocument()
    const link = screen.getByRole('link', { name: /Alle Werte/ })
    expect(link).toHaveAttribute('href', '/v4/auswertungen/tabelle')
  })

  it('werkbank: Vergleich-Toggle erscheint bei Vorjahr-Daten und schaltet Δ frei', () => {
    render(
      <WerteTabelle
        rows={rows}
        modus="werkbank"
        vorjahrRows={[mz(1, 2024), mz(2, 2024)]}
        jahrLabel={2025}
        vergleichLabel={2024}
      />,
    )
    const toggle = screen.getByRole('button', { name: /Vergleich 2024/ })
    fireEvent.click(toggle)
    // Δ-Spaltenkopf bzw. Vergleichs-Render aktiv: die Vergleichsspalte verdreifacht
    // sich — prüfe, dass nun ein Delta-Pfeil gerendert ist.
    expect(screen.getAllByText(/[▲▼=]/).length).toBeGreaterThan(0)
  })
})
