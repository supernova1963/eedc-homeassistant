/**
 * CockpitAussichtV4 (IA-V4 A.4) — Struktur-Smoke-Test: „Vorwärts-Teleskop".
 * Sichert den Kern-Vertrag der Spec: Horizont-Selektor (7 T · 14 T · 12 Monate,
 * Default 14 T), stabiler Kopf (Kennzahlen + Prognose-Verlauf), horizont-gescopte
 * Detailblöcke + Komponenten-Teaser-Platzhalter, und der Wechsel auf 12 Monate
 * zieht die Langfrist-Blöcke (Saison/Degradation) nach.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { ThemeProvider } from '../context/ThemeContext'

vi.mock('../hooks', () => ({
  useSelectedAnlage: () => ({ selectedAnlage: { id: 1, latitude: 50.1, longitude: 8.7 } }),
}))

const solar = {
  anlage_id: 1, anlagenname: 'Demo', kwp_gesamt: 10, neigung: 30, ausrichtung: 0,
  system_losses_prozent: 14, prognose_zeitraum: { von: null, bis: null },
  summe_kwh: 120, durchschnitt_kwh_tag: 8.6, datenquelle: 'Open-Meteo Solar (GTI)',
  abgerufen_am: '2026-06-23T06:00:00Z', hinweise: [],
  tage: [
    { datum: '2026-06-23', pv_ertrag_kwh: 9.1, gti_kwh_m2: 5, ghi_kwh_m2: 5, sonnenstunden: 8, temperatur_max_c: 24, wetter_symbol: 'sunny', pv_ertrag_morgens_kwh: 4, pv_ertrag_nachmittags_kwh: 5.1 },
    { datum: '2026-06-24', pv_ertrag_kwh: 7.3, gti_kwh_m2: 4, ghi_kwh_m2: 4, sonnenstunden: 6, temperatur_max_c: 22, wetter_symbol: 'partly_cloudy', pv_ertrag_morgens_kwh: 3, pv_ertrag_nachmittags_kwh: 4.3 },
  ],
  tageswerte: [], anlage: { id: 1, name: 'Demo', leistung_kwp: 10, neigung: 30, azimut: 0 },
}

const vergleich = {
  openmeteo_heute_kwh: 9, openmeteo_morgen_kwh: 7, openmeteo_uebermorgen_kwh: 8, openmeteo_tage: [], openmeteo_tageshaelften: [],
  eedc_heute_kwh: 8.5, eedc_morgen_kwh: 6.8, eedc_uebermorgen_kwh: 7.5,
  eedc_stundenprofil: [{ stunde: 11, kw: 2.1, p10_kw: null, p90_kw: null }, { stunde: 12, kw: 3.4, p10_kw: null, p90_kw: null }],
  eedc_lernfaktor: 0.95, eedc_lernfaktor_stufe: null, eedc_prognose_basis: 'eedc', eedc_tageshaelften: [],
  solcast_verfuegbar: false, solcast_status: null, solcast_hinweis: null, solcast_quelle: null,
  solcast_heute_kwh: null, solcast_p10_kwh: null, solcast_p90_kwh: null, solcast_morgen_kwh: null,
  solcast_morgen_p10_kwh: null, solcast_morgen_p90_kwh: null, solcast_uebermorgen_kwh: null,
  solcast_stundenprofil: [], solcast_tage: [], solcast_tageshaelften: [],
  ist_heute_kwh: 4.2, ist_stundenprofil: [], ist_tageshaelfte: null,
  verbleibend_kwh: null, verbleibend_om_kwh: null, verbleibend_eedc_kwh: null, verbleibend_solcast_kwh: null,
  openmeteo_stundenprofil: [], solcast_letzter_abruf: null, openmeteo_modell: null, aktuelle_stunde: 12,
}

const langfrist = {
  anlage_id: 1, anlagenname: 'Demo', anlagenleistung_kwp: 10, prognose_zeitraum: { von: null, bis: null },
  jahresprognose_kwh: 9800,
  monatswerte: [
    { jahr: 2026, monat: 7, monat_name: 'Juli', pvgis_prognose_kwh: 1200, trend_korrigiert_kwh: 1250, konfidenz_min_kwh: 1100, konfidenz_max_kwh: 1400, historische_performance_ratio: 0.96 },
  ],
  trend_analyse: { durchschnittliche_performance_ratio: 0.94, trend_richtung: 'stabil', datenbasis_monate: 18 },
  datenquellen: ['PVGIS', 'Trend'],
}

const trend = {
  anlage_id: 1, anlagenname: 'Demo', anlagenleistung_kwp: 10, analyse_zeitraum: { von: 2023, bis: 2026 },
  jahres_vergleich: [], saisonale_muster: { beste_monate: ['Juni', 'Juli'], schlechteste_monate: ['Dezember', 'Januar'] },
  degradation: { geschaetzt_prozent_jahr: -0.4, hinweis: 'normal', methode: 'vollstaendig', zuverlaessig: true },
  datenquellen: ['Monatsdaten'],
}

const finanz = {
  anlage_id: 1, anlagenname: 'Demo', prognose_zeitraum: { von: null, bis: null },
  einspeiseverguetung_cent_kwh: 8.2, netzbezug_preis_cent_kwh: 32, grundpreis_euro_monat: 12,
  jahres_erzeugung_kwh: 9800, jahres_eigenverbrauch_kwh: 3200, jahres_einspeisung_kwh: 6600, eigenverbrauchsquote_prozent: 33,
  jahres_einspeise_erloes_euro: 541, jahres_ev_ersparnis_euro: 1024, jahres_netto_ertrag_euro: 1565,
  komponenten_beitraege: [],
  speicher_ev_erhoehung_kwh: 0, speicher_ev_erhoehung_euro: 0,
  v2h_rueckspeisung_kwh: 0, v2h_ersparnis_euro: 0, eauto_ladung_pv_kwh: 0, eauto_ersparnis_euro: 0,
  wp_stromverbrauch_kwh: 0, wp_pv_anteil_kwh: 0, wp_pv_ersparnis_euro: 0,
  wp_alternativ_ersparnis_euro: 0, eauto_alternativ_ersparnis_euro: 0,
}

vi.mock('../api/wetter', () => ({ wetterApi: { getSolarPrognose: vi.fn(() => Promise.resolve(solar)) } }))
vi.mock('../api/energie_profil', () => ({ energieProfilApi: { getTagesprognose: vi.fn(() => Promise.resolve(null)) } }))
vi.mock('../api/investitionen', () => ({ investitionenApi: { getWaermepumpeDashboard: vi.fn(() => Promise.resolve([])) } }))
vi.mock('../api/aussichten', () => ({
  aussichtenApi: {
    getPrognosenVergleich: vi.fn(() => Promise.resolve(vergleich)),
    getLangfristPrognose: vi.fn(() => Promise.resolve(langfrist)),
    getTrendAnalyse: vi.fn(() => Promise.resolve(trend)),
    getFinanzPrognose: vi.fn(() => Promise.resolve(finanz)),
  },
}))

import CockpitAussichtV4 from './CockpitAussichtV4'

function renderView() {
  return render(
    <ThemeProvider>
      <MemoryRouter initialEntries={['/v4/cockpit/aussicht']}>
        <CockpitAussichtV4 anlageId={1} />
      </MemoryRouter>
    </ThemeProvider>,
  )
}

describe('CockpitAussichtV4 — Vorwärts-Teleskop', () => {
  beforeEach(() => {
    localStorage.clear()
    // ThemeProvider liest window.matchMedia (in jsdom nicht implementiert).
    vi.stubGlobal('matchMedia', vi.fn().mockReturnValue({
      matches: false, media: '', onchange: null,
      addEventListener: vi.fn(), removeEventListener: vi.fn(),
      addListener: vi.fn(), removeListener: vi.fn(), dispatchEvent: vi.fn(),
    }))
  })

  it('zeigt Titel + 2-stufigen Horizont-Selektor', async () => {
    renderView()
    expect(screen.getByRole('heading', { name: 'Aussicht' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Kurzfristig' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Langfristig' })).toBeInTheDocument()
  })

  it('Default-Horizont Kurzfristig ist aktiv', () => {
    renderView()
    expect(screen.getByRole('button', { name: 'Kurzfristig' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: 'Langfristig' })).toHaveAttribute('aria-pressed', 'false')
  })

  it('Kurzfristig: Kopf (Kennzahlen + gemergte Tages-Prognose) + Stunden-Chart + Teaser, KEIN Quellen-Vergleich', async () => {
    renderView()
    expect(await screen.findByText('Kennzahlen')).toBeInTheDocument()
    // Prognose-Verlauf + Wetter sind zu EINEM „Tages-Prognose"-Block gemergt (Gernot 2026-06-23).
    expect(screen.getByText('Tages-Prognose')).toBeInTheDocument()
    expect(screen.queryByText('Wetter & PV je Tag')).not.toBeInTheDocument()
    expect(screen.getByText('Stunden-Prognose')).toBeInTheDocument()
    expect(screen.getByText('Stundenwerte')).toBeInTheDocument()
    // Dezenter Vorwärts-€-Teaser ganz unten (D2, Gernot 2026-06-23).
    expect(screen.getByText('Finanzen')).toBeInTheDocument()
    // Kein generischer Komponenten-Teaser (AO3 verworfen, Gernot 2026-06-23).
    expect(screen.queryByText('Aussicht je Komponente')).not.toBeInTheDocument()
    // Quellen-Vergleich gehört nicht in Aussicht (Gernot 2026-06-23).
    expect(screen.queryByText(/Quellen-Vergleich/)).not.toBeInTheDocument()
  })

  it('Wechsel auf Langfristig zieht Langfrist-Blöcke (Saison/Degradation) nach', async () => {
    renderView()
    await screen.findByText('Kennzahlen')
    fireEvent.click(screen.getByRole('button', { name: 'Langfristig' }))
    await waitFor(() => expect(screen.getByText('Saisonale Muster')).toBeInTheDocument())
    expect(screen.getByText('Degradations-Prognose')).toBeInTheDocument()
    // Kurzfrist-spezifische Blöcke sind im Langfrist-Horizont weg.
    expect(screen.queryByText('Tages-Prognose')).not.toBeInTheDocument()
    expect(screen.queryByText('Stunden-Prognose')).not.toBeInTheDocument()
  })
})
