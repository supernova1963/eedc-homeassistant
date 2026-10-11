/**
 * Cockpit → Live: die Anzeige „Solar Soll ~x kW" im Energiefluss (N-691).
 *
 * Render-Probe über die echte Sicht. `CockpitLiveV4` sucht im Verbrauchsprofil
 * der Live-Wetter-Antwort den Eintrag der laufenden Stunde und reicht dessen
 * PV-Soll an `EnergieFluss` durch. `zeit` ist dort ein Slot-Etikett „HH:00"
 * (`live_wetter.py`, `VerbrauchsStunde.zeit`), kein Datum: bis N-691 baute die
 * Sicht daraus `new Date("14:00")` ⇒ `NaN`, kein Eintrag traf, die Anzeige
 * erschien nie (seit `7332b2c9`, 22.03.2026).
 *
 * Welcher Eintrag „die laufende Stunde" ist, entscheidet die Backward-Slot-SoT
 * (`lib/stundenSlot.ts`, #144/#297): Slot `h` trägt `[h-1, h)`, um 14:30 läuft
 * also Slot 15. Die Probe gibt Slot 14 und Slot 15 verschiedene Werte, damit ein
 * Griff in die vorige Stunde auffiele.
 *
 * Uhrzeit-Fake: nur `Date` wird gefälscht (`toFake: ['Date']`), die Timer der
 * Poll-Schleife und von `waitFor` laufen echt.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { waitFor } from '@testing-library/react'
import type {
  BoersenpreisResponse, LiveDashboardResponse, LiveWetterResponse, TagesverlaufResponse, VerbrauchsStunde,
} from '../api/liveDashboard'
import { renderMitProvidern, stubMatchMedia } from '../test/render'

const daten: LiveDashboardResponse = {
  anlage_id: 1, anlage_name: 'Demo', zeitpunkt: '2026-09-28T14:30:00', verfuegbar: true,
  komponenten: [
    { key: 'pv_11', label: 'PV Süd', icon: 'sun', erzeugung_kw: 3.0, verbrauch_kw: null, typ: 'pv-module', leistung_kwp: 8 },
    { key: 'netz', label: 'Stromnetz', icon: 'zap', erzeugung_kw: null, verbrauch_kw: 2.2 },
    { key: 'haushalt', label: 'Restverbrauch', icon: 'home', erzeugung_kw: null, verbrauch_kw: 0.8 },
  ],
  summe_erzeugung_kw: 3.0, summe_verbrauch_kw: 3.0, summe_pv_kw: 3.0,
  gauges: [], heute_pv_kwh: 20, heute_einspeisung_kwh: 10, heute_netzbezug_kwh: 1,
  heute_eigenverbrauch_kwh: 10, gestern_pv_kwh: 18, gestern_einspeisung_kwh: 9,
  gestern_netzbezug_kwh: 1, gestern_eigenverbrauch_kwh: 9,
  heute_kwh_pro_komponente: null, warmwasser_temperatur_c: null,
}

/** 24 Slot-Etiketten „00:00" … „23:00"; nur Slot 14 und Slot 15 tragen PV. */
function profil(sfmlSlot15: number | null = null): VerbrauchsStunde[] {
  return Array.from({ length: 24 }, (_, h) => ({
    zeit: `${String(h).padStart(2, '0')}:00`,
    pv_ertrag_kw: h === 14 ? 4.1 : h === 15 ? 5.2 : 0,
    verbrauch_kw: 0.5,
    pv_ml_prognose_kw: h === 15 ? sfmlSlot15 : null,
  }))
}

function wetterMit(verbrauchsprofil: VerbrauchsStunde[]): LiveWetterResponse {
  return {
    anlage_id: 1, verfuegbar: true, grund: null, aktuell: null, stunden: [],
    temperatur_min_c: null, temperatur_max_c: null,
    sonnenstunden: null, sonnenstunden_bisher: null, sonnenstunden_rest: null,
    pv_prognose_kwh: null, pv_prognose_rest_kwh: null, pv_prognose_heute_rollend_kwh: null,
    pv_ist_bisher_kwh: null, grundlast_kw: null, verbrauchsprofil,
  }
}

const leererVerlauf: TagesverlaufResponse = { anlage_id: 1, datum: '2026-09-28', serien: [], punkte: [] }
const keinePreise: BoersenpreisResponse = {
  anlage_id: 1, markt: 'DE', tage: [], monats_durchschnitt_cent: null,
  aktuelle_stunde: null, heute: null, hinweis: null, endpreis_jetzt_cent: null,
}

let wetter: LiveWetterResponse = wetterMit(profil())

const getWetter = vi.fn(() => Promise.resolve(wetter))
vi.mock('../api/liveDashboard', () => ({
  liveDashboardApi: {
    getData: vi.fn(() => Promise.resolve(daten)),
    getWetter: () => getWetter(),
    getTagesverlauf: vi.fn(() => Promise.resolve(leererVerlauf)),
    getBoersenpreise: vi.fn(() => Promise.resolve(keinePreise)),
  },
}))
vi.mock('../api/wetter', () => ({
  wetterApi: { getSolarPrognose: vi.fn(() => Promise.resolve({ tage: [] })) },
}))
vi.mock('../api/zaehlerstaende', () => ({
  zaehlerstaendeApi: { heute: vi.fn(() => Promise.resolve([])) },
}))
vi.mock('../hooks', async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  useSelectedAnlage: () => ({ selectedAnlage: { id: 1, name: 'Demo', netz_puffer_w: 100 } }),
}))
vi.mock('./status/AppStatusContext', async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  useDemoMode: () => ({ demoMode: false, setDemoMode: () => {} }),
  useReportDatenStatus: () => {},
}))

import CockpitLiveV4 from './CockpitLiveV4'
import { _clearSwrCacheForTests } from '../hooks/useApiData'

const URSPRUNG = window.location.hash
const tick = () => new Promise(r => setTimeout(r, 0))
const sollText = () => document.body.querySelector('[data-solar-soll]')?.textContent ?? null

/** Uhr auf heute `hh:mm` Ortszeit stellen (nur `Date`, die Timer bleiben echt). */
function uhrAuf(hh: number, mm: number) {
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(new Date(2026, 8, 28, hh, mm, 0))
}

/** Bis der Energiefluss steht und die Wetter-Antwort angekommen ist. */
async function sichtGeladen() {
  await waitFor(() => expect(document.body.querySelector('svg.flex-1')).not.toBeNull())
  await waitFor(() => expect(getWetter).toHaveBeenCalled())
  await tick()
  await tick()
}

describe('Cockpit → Live: „Solar Soll ~x kW" im Energiefluss (N-691)', () => {
  beforeEach(() => {
    localStorage.clear()
    _clearSwrCacheForTests()
    stubMatchMedia()
    window.location.hash = '#/cockpit/live'
    getWetter.mockClear()
    wetter = wetterMit(profil())
  })
  afterEach(() => {
    window.location.hash = URSPRUNG
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  it('um 14:30 zeigt die Anzeige das Soll der laufenden Stunde (Backward-Slot 15), nicht das der vorigen (Slot 14)', async () => {
    uhrAuf(14, 30)
    renderMitProvidern(<CockpitLiveV4 anlageId={1} />)
    await sichtGeladen()
    await waitFor(() => expect(sollText()).toBe('Solar Soll ~5,2 kW'))
  })

  it('trägt der Slot eine Solar-Forecast-ML-Prognose, hat sie Vorrang vor dem eedc-Wert', async () => {
    wetter = wetterMit(profil(6.3))
    uhrAuf(14, 30)
    renderMitProvidern(<CockpitLiveV4 anlageId={1} />)
    await sichtGeladen()
    await waitFor(() => expect(sollText()).toBe('Solar Soll ~6,3 kW'))
  })

  it('Gegenprobe: um 21:30 (Slot 22, PV-Soll 0) erscheint keine Anzeige', async () => {
    uhrAuf(21, 30)
    renderMitProvidern(<CockpitLiveV4 anlageId={1} />)
    await sichtGeladen()
    expect(sollText()).toBeNull()
  })
})
