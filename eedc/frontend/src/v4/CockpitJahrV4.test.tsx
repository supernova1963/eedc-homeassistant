/**
 * CockpitJahrV4 — Struktur-Smoke-Test: Jahr als Monat-Variante.
 * Sichert: Jahres-Auswahl-Kopf (Status-Badge + Rail/Stepper) + die Monat-Block-
 * Reihe auf Jahresebene (Kennzahlen / Energie-Bilanz / Verlauf / Komponenten /
 * Finanzen), gespeist aus Σ der Monats-Antworten + der aggregierten Monatsreihe.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ThemeProvider } from '../context/ThemeContext'
import type { AktuellerMonatResponse } from '../api/aktuellerMonat'
import type { AggregierteMonatsdaten } from '../api/monatsdaten'

// Zwei vergangene Jahre (2024/2025) → Default = neuestes mit Daten = 2025
// (≠ aktuelles Jahr → „abgeschlossen", kein Reload-Button — wie Monat).
const monatsZeile = (jahr: number, monat: number): AggregierteMonatsdaten => ({
  jahr, monat,
  pv_erzeugung_kwh: 300, eigenverbrauch_kwh: 180, einspeisung_kwh: 120,
  netzbezug_kwh: 90, direktverbrauch_kwh: 140, gesamtverbrauch_kwh: 270,
  autarkie_prozent: 66, speicher_entladung_kwh: 40,
} as unknown as AggregierteMonatsdaten)

const aggregiert: AggregierteMonatsdaten[] = [
  ...[1, 2, 3].map((m) => monatsZeile(2025, m)),
  ...[1, 2].map((m) => monatsZeile(2024, m)),
]

const monatsAntwort = (jahr: number, monat: number): AktuellerMonatResponse => ({
  anlage_id: 1, anlage_name: 'Demo', jahr, monat, monat_name: String(monat),
  aktualisiert_um: '', quellen: {},
  pv_erzeugung_kwh: 300, einspeisung_kwh: 120, netzbezug_kwh: 90,
  eigenverbrauch_kwh: 180, direktverbrauch_kwh: 140, gesamtverbrauch_kwh: 270,
  autarkie_prozent: 66, eigenverbrauch_quote_prozent: 60,
  speicher_ladung_kwh: 50, speicher_entladung_kwh: 43, speicher_wirkungsgrad_prozent: 86,
  speicher_vollzyklen: 4, speicher_kapazitaet_kwh: 10, hat_speicher: true,
  speicher_soc_drift_signifikant: false,
  wp_strom_kwh: 60, wp_waerme_kwh: 180, wp_heizung_kwh: 140, wp_warmwasser_kwh: 40,
  hat_waermepumpe: true,
  einspeise_erloes_euro: 12, netzbezug_kosten_euro: 27, ev_ersparnis_euro: 50,
  netto_ertrag_euro: 35, gesamtnettoertrag_euro: 35, betriebskosten_anteilig_euro: 5,
  sonstige_netto_euro: 0, sonstige_ertraege_euro: 0, sonstige_ausgaben_euro: 0,
  soll_pv_kwh: 320,
  investitionen_financials: [], komponenten_geraete: {}, feld_quellen: {},
  vorjahr: null,
} as unknown as AktuellerMonatResponse)

vi.mock('../api/monatsdaten', () => ({
  monatsdatenApi: { listAggregiert: vi.fn(() => Promise.resolve(aggregiert)) },
}))

vi.mock('../api/aktuellerMonat', () => ({
  aktuellerMonatApi: { getData: vi.fn((_id: number, j: number, m: number) => Promise.resolve(monatsAntwort(j, m))) },
}))

import CockpitJahrV4 from './CockpitJahrV4'

function renderView() {
  return render(
    <ThemeProvider>
      <CockpitJahrV4 anlageId={1} />
    </ThemeProvider>,
  )
}

describe('CockpitJahrV4 — Jahr', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.stubGlobal('matchMedia', vi.fn().mockReturnValue({
      matches: false, media: '', onchange: null,
      addEventListener: vi.fn(), removeEventListener: vi.fn(),
      addListener: vi.fn(), removeListener: vi.fn(), dispatchEvent: vi.fn(),
    }))
  })

  it('zeigt Jahres-Kopf (Status-Badge) + Auswahl (Rail/Stepper)', async () => {
    renderView()
    expect(await screen.findByText('abgeschlossen')).toBeInTheDocument()
    expect(screen.getAllByText('2025').length).toBeGreaterThan(0)
    expect(screen.getByRole('button', { name: 'voriges Jahr' })).toBeInTheDocument()
  })

  it('rendert die Monat-Block-Reihe auf Jahresebene (inkl. Komponenten + Finanzen)', async () => {
    renderView()
    expect(await screen.findByText('Kennzahlen')).toBeInTheDocument()
    expect(screen.getByText('Energie-Bilanz')).toBeInTheDocument()
    expect(screen.getByText('Verlauf')).toBeInTheDocument()
    expect(screen.getByText('Speicher')).toBeInTheDocument()
    expect(screen.getByText('Wärme/Klima')).toBeInTheDocument()
    expect(screen.getByText('Finanzen')).toBeInTheDocument()
  })
})
