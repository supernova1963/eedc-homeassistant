/**
 * Cockpit → Live: ohne Kurve sagt die Seite, warum der Tagesverlauf fehlt (Handgriff Triage-4 §3).
 *
 * Der Block «Tagesverlauf» erscheint nur mit Punkten und Serien (`hatTagesverlauf`). Die Kurve kommt aus der
 * Leistungs-Zuordnung unter Datenquellen (`live`-Eintrag, Home Assistant) oder aus den MQTT-Snapshots der Inbound-
 * Leistungen — ohne Home Assistant (Standalone-Gleichstand S3) und seit S4 auch mit Home Assistant ohne Zuordnung bzw.
 * für Geräte ohne HA-Entität (Mischform, `live_tagesverlauf_service.py`). Leer bleibt sie ohne beides und bis zur ersten
 * MQTT-Aufzeichnung. Bis hierher fehlte der Block dann wortlos — der Hinweis «Nicht dargestellt …» steht nur IM Chart.
 * Jetzt: ein Satz an der Stelle des Blocks, der beide Wege nennt.
 * Schwester: `CockpitLiveSolarSoll.test.tsx` (dieselbe Render-Probe über die echte Sicht).
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { waitFor } from '@testing-library/react'
import type { BoersenpreisResponse, LiveDashboardResponse, TagesverlaufResponse } from '../api/liveDashboard'
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

const leererVerlauf: TagesverlaufResponse = { anlage_id: 1, datum: '2026-09-28', serien: [], punkte: [] }
const keinePreise: BoersenpreisResponse = {
  anlage_id: 1, markt: 'DE', tage: [], monats_durchschnitt_cent: null,
  aktuelle_stunde: null, heute: null, hinweis: null, endpreis_jetzt_cent: null,
}

let verlauf: TagesverlaufResponse | null = leererVerlauf
const getTagesverlauf = vi.fn(() => (verlauf ? Promise.resolve(verlauf) : Promise.reject(new Error('weg'))))
vi.mock('../api/liveDashboard', () => ({
  liveDashboardApi: {
    getData: vi.fn(() => Promise.resolve(daten)),
    getWetter: vi.fn(() => Promise.reject(new Error('kein Wetter im Test'))),
    getTagesverlauf: () => getTagesverlauf(),
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
const SATZ = 'Tagesverlauf: braucht eine Leistungs-Zuordnung unter Datenquellen (Home Assistant) oder Leistungswerte über MQTT-Inbound; die MQTT-Kurve beginnt mit der ersten Aufzeichnung.'

async function sichtGeladen() {
  await waitFor(() => expect(document.body.querySelector('svg.flex-1')).not.toBeNull())
  await waitFor(() => expect(getTagesverlauf).toHaveBeenCalled())
  await tick()
  await tick()
}

describe('Cockpit → Live: Tagesverlauf ohne Kurve sagt warum', () => {
  beforeEach(() => {
    localStorage.clear()
    _clearSwrCacheForTests()
    stubMatchMedia()
    window.location.hash = '#/cockpit/live'
    getTagesverlauf.mockClear()
    verlauf = leererVerlauf
  })
  afterEach(() => {
    window.location.hash = URSPRUNG
    vi.unstubAllGlobals()
  })

  it('leere Antwort (HA ohne Zuordnung oder MQTT noch ohne Aufzeichnung): der Satz steht an der Stelle des Blocks', async () => {
    renderMitProvidern(<CockpitLiveV4 anlageId={1} />)
    await sichtGeladen()
    await waitFor(() => expect(document.body.textContent).toContain(SATZ))
  })

  it('Gegenprobe: mit Kurve kein Satz', async () => {
    verlauf = {
      anlage_id: 1, datum: '2026-09-28',
      serien: [{ key: 'pv_11', label: 'PV Süd', kategorie: 'pv', farbe: 'currentColor', seite: 'quelle', bidirektional: false }],
      punkte: [{ zeit: '10:00', werte: { pv_11: 2.0 } }, { zeit: '10:10', werte: { pv_11: 2.2 } }],
    }
    renderMitProvidern(<CockpitLiveV4 anlageId={1} />)
    await sichtGeladen()
    expect(document.body.textContent).not.toContain(SATZ)
  })

  it('Gegenprobe: Antwort fehlt (Abruf gescheitert) — kein Satz, die Seite behauptet nichts', async () => {
    verlauf = null
    renderMitProvidern(<CockpitLiveV4 anlageId={1} />)
    await sichtGeladen()
    expect(document.body.textContent).not.toContain(SATZ)
  })
})
