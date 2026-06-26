/**
 * CockpitTagV4 — Struktur-Smoke-Test: Einzeltag als Monat-Variante.
 * Sichert: Datum-Stepper-Kopf + die vier Blöcke (Kennzahlen / Energie-Bilanz aus
 * dem Tages-SoT, Stundenverlauf / Stundenwerte aus den Stunden).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ThemeProvider } from '../context/ThemeContext'
import type { TagWerte, StundenAntwort } from '../api/energie_profil'

// Default-Datum der Sicht = gestern (TZ-stabil über toISOString).
const iso = (d: Date) => d.toISOString().slice(0, 10)
const gestern = (() => { const d = new Date(); d.setDate(d.getDate() - 1); return iso(d) })()

const tag = {
  datum: gestern, stunden_verfuegbar: 24, datenquelle: 'HA',
  erzeugung: 20, eigenverbrauch: 8, einspeisung: 12, netzbezug: 5,
  gesamtverbrauch: 13, direktverbrauch: 6,
  autarkie: 62, evQuote: 40, spezErtrag: 2,
  speicher_ladung: 11, speicher_entladung: 9.5, speicher_effizienz: 86, wp_strom: 4.2,
  einspeise_erloes: 1.2, ev_ersparnis: 2.3, netzbezug_kosten: 1.6, netto_ertrag: 3.5, netto_bilanz: 1.9,
  co2_einsparung: 4, ueberschuss_kwh: 7, defizit_kwh: 2,
  peak_pv_kw: 4, peak_netzbezug_kw: 1, peak_einspeisung_kw: 3,
  performance_ratio: 0.8, batterie_vollzyklen: null,
  temperatur_min_c: 10, temperatur_max_c: 22, strahlung_summe_wh_m2: 4200,
  boersenpreis_avg_cent: null, boersenpreis_min_cent: null,
  negative_preis_stunden: null, einspeisung_neg_preis_kwh: null,
} as unknown as TagWerte

const stundenAntwort = {
  stunden: Array.from({ length: 24 }, (_, h) => ({
    stunde: h, pv_kw: h >= 8 && h <= 16 ? 2 : 0, verbrauch_kw: 1,
    einspeisung_kw: h >= 8 && h <= 16 ? 1 : 0, netzbezug_kw: h < 8 ? 1 : 0,
    batterie_kw: 0, waermepumpe_kw: 0, wallbox_kw: 0, ueberschuss_kw: 0, defizit_kw: 0,
    temperatur_c: 15, globalstrahlung_wm2: 200, soc_prozent: null, komponenten: null,
    wp_starts_anzahl: null, wp_betriebsstunden: null,
  })),
  serien: [],
} as unknown as StundenAntwort

vi.mock('../api/energie_profil', () => ({
  energieProfilApi: {
    getStunden: vi.fn(() => Promise.resolve(stundenAntwort)),
    getTageWerte: vi.fn(() => Promise.resolve([tag])),
    // R5-F2: Tag holt den ältesten verfügbaren Tag für die Datumsauswahl-Untergrenze.
    getVerfuegbareMonate: vi.fn(() => Promise.resolve([])),
    getTagDetail: vi.fn(() => Promise.resolve({
      datum: gestern,
      wp_strom_heizen_kwh: 3.0, wp_strom_warmwasser_kwh: 1.2,
      speicher_ladung_netz_kwh: 2.5, speicher_effektiver_ladepreis_cent: 22.5,
      speicher_effektiver_ladepreis_quelle: 'dyn-tarif',
    })),
  },
}))

import CockpitTagV4 from './CockpitTagV4'

function renderView() {
  return render(
    <ThemeProvider>
      <CockpitTagV4 anlageId={1} />
    </ThemeProvider>,
  )
}

describe('CockpitTagV4 — Einzeltag', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.stubGlobal('matchMedia', vi.fn().mockReturnValue({
      matches: false, media: '', onchange: null,
      addEventListener: vi.fn(), removeEventListener: vi.fn(),
      addListener: vi.fn(), removeListener: vi.fn(), dispatchEvent: vi.fn(),
    }))
  })

  it('zeigt Header (Status-Badge) + Auswahl (Rail/Stepper) + Aktualisieren', async () => {
    renderView()
    // gestern ≠ heute → „abgeschlossen"-Badge (analog Monat läuft/abgeschlossen).
    expect(await screen.findByText('abgeschlossen')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Aktualisieren' })).toBeInTheDocument()
    // Stepper-Navigation (mobil) + Datums-Direktsprung (Rail/Stepper).
    expect(screen.getByRole('button', { name: 'voriger Tag' })).toBeInTheDocument()
    expect(screen.getAllByLabelText('Datum wählen').length).toBeGreaterThan(0)
  })

  it('rendert die Monat-Block-Reihe auf Tagesebene (inkl. Komponenten + Finanzen)', async () => {
    renderView()
    expect(await screen.findByText('Kennzahlen')).toBeInTheDocument()
    expect(screen.getByText('Energie-Bilanz')).toBeInTheDocument()
    expect(screen.getByText('Stundenverlauf')).toBeInTheDocument()
    expect(screen.getByText('Stundenwerte')).toBeInTheDocument()
    // Komponenten-/Finanz-Blöcke wie im Monat (aus Tagesdaten gegated).
    expect(screen.getByText('Speicher')).toBeInTheDocument()
    expect(screen.getByText('Wärme/Klima')).toBeInTheDocument()
    expect(screen.getByText('Finanzen')).toBeInTheDocument()
  })
})
