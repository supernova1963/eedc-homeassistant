/**
 * Cockpit → Live mit Fokus-Deep-Link (FD-1/FD-5) — Render-Probe.
 *
 * Die reine Regel prüft `CockpitLiveFokus.test.ts`. Hier geht es um das, was
 * eine reine Funktion nicht zeigen kann: **dass die Sicht beim Landen wirklich
 * das Overlay rendert** statt ihres normalen Layouts — und im Fehlfall den
 * Hinweis statt der ganzen Live-Sicht.
 *
 * ⚠ Der Deep-Link wird über `window.location.hash` gestellt, nicht über
 * `renderMitProvidern({ route })`: der füllt nur `MemoryRouter.initialEntries`
 * und lässt `window.location` unberührt.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import type {
  BoersenpreisResponse, LiveDashboardResponse, LiveWetterResponse, TagesverlaufResponse,
} from '../api/liveDashboard'
import { renderMitProvidern, stubMatchMedia } from '../test/render'

const daten: LiveDashboardResponse = {
  anlage_id: 1, anlage_name: 'Demo', zeitpunkt: '2026-09-22T12:00:00', verfuegbar: true,
  // ⚠ Mindestens EINE Komponente: `EnergieFluss` gibt bei leerer Liste `null`
  // zurück (`EnergieFluss.tsx:408`) — mit leerer Fixture prüfte die Probe eine
  // Kachel, die gar nichts zeichnet.
  komponenten: [{ key: 'pv_1', label: 'PV', icon: 'sun', erzeugung_kw: 3, verbrauch_kw: null }],
  summe_erzeugung_kw: 3, summe_verbrauch_kw: 1, summe_pv_kw: 3,
  gauges: [], heute_pv_kwh: 12, heute_einspeisung_kwh: 4, heute_netzbezug_kwh: 2,
  heute_eigenverbrauch_kwh: 8, gestern_pv_kwh: 10, gestern_einspeisung_kwh: 3,
  gestern_netzbezug_kwh: 2, gestern_eigenverbrauch_kwh: 7,
  heute_kwh_pro_komponente: null, warmwasser_temperatur_c: null,
}

/** `null` ⇒ die Sicht hat kein Wetter (der Fall „Kachel nicht gemountet"). */
let wetterAntwort: LiveWetterResponse | null = null
const leererVerlauf: TagesverlaufResponse = { anlage_id: 1, datum: '2026-09-22', serien: [], punkte: [] }
const keinePreise: BoersenpreisResponse = {
  anlage_id: 1, markt: 'DE', tage: [], monats_durchschnitt_cent: null,
  aktuelle_stunde: null, heute: null, hinweis: null, endpreis_jetzt_cent: null,
}

vi.mock('../api/liveDashboard', () => ({
  liveDashboardApi: {
    getData: vi.fn(() => Promise.resolve(daten)),
    getWetter: vi.fn(() => (wetterAntwort ? Promise.resolve(wetterAntwort) : Promise.reject(new Error('kein Wetter')))),
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
import { liveDashboardApi } from '../api/liveDashboard'
import { _clearSwrCacheForTests } from '../hooks/useApiData'

const URSPRUNG = window.location.hash

describe('Cockpit → Live mit ?fokus=', () => {
  beforeEach(() => {
    localStorage.clear()
    // Der Live-Seed (`swrCachePeek`, R18-2) ueberlebt den Unmount: ohne diese
    // Leerung startet jede Probe mit den Daten der vorigen, und der Fall
    // "Abruf-Fehler OHNE Daten" (frische Karte, Backend weg) waere im Dateilauf
    // unerreichbar (gemessen 22.09.: Sprengsatz isoliert rot, im Dateilauf gruen).
    _clearSwrCacheForTests()
    stubMatchMedia()
    wetterAntwort = null
    window.location.hash = ''
  })
  afterEach(() => { window.location.hash = URSPRUNG })

  it('?fokus=live:energiefluss öffnet den Energiefluss im Vollbild — ohne Zurück und ohne ⤢', async () => {
    window.location.hash = '#/cockpit/live?fokus=live:energiefluss'
    renderMitProvidern(<CockpitLiveV4 anlageId={1} />)
    // Der Titel steht als Überschrift in der Overlay-Kopfzeile (`FokusVollbild`) —
    // `findByRole('heading')` statt `findByText`, damit die Probe nicht auf einen
    // beliebigen Treffer im normalen Layout hereinfällt.
    // `level: 2` = die Overlay-Kopfzeile; der Energiefluss bringt DARIN seine
    // eigene h3 mit — beide heißen „Energiefluss".
    expect(await screen.findByRole('heading', { name: 'Energiefluss', level: 2 })).toBeInTheDocument()
    expect(screen.queryByText('Zurück')).not.toBeInTheDocument()
    expect(screen.queryByText('Fokus / Vollbild')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Energiefluss: Fokus / Vollbild')).not.toBeInTheDocument()
  })

  it('?fokus=gibtesnicht ⇒ Hinweis statt der ganzen Live-Sicht (FD-5 Fall 1)', async () => {
    window.location.hash = '#/cockpit/live?fokus=gibtesnicht'
    renderMitProvidern(<CockpitLiveV4 anlageId={1} />)
    expect(await screen.findByText(/gibt es in dieser Sicht nicht/)).toBeInTheDocument()
    // Ohne Zeitraum-Teil: Live hat keine Zeitraum-Navigation.
    expect(screen.queryByText(/nicht für diesen Zeitraum/)).not.toBeInTheDocument()
    expect(screen.queryByText('Zurück')).not.toBeInTheDocument()
  })

  it('?fokus=live:wetter-heute ohne Wetterdaten ⇒ derselbe Hinweis (kein Leerbild)', async () => {
    window.location.hash = '#/cockpit/live?fokus=live:wetter-heute'
    renderMitProvidern(<CockpitLiveV4 anlageId={1} />)
    expect(await screen.findByText(/gibt es in dieser Sicht nicht/)).toBeInTheDocument()
  })

  it('Abruf-Fehler ohne Daten ⇒ Fehlerbanner, NICHT „gibt es nicht" (Nachmessung 22.09., Punkt 3)', async () => {
    // Ein Backend-Neustart oder ein Netzausfall ist kein Urteil über die Anzeige.
    // Stünde hier der FD-5-Hinweis, läse sich jeder Ausfall in der HA-Karte als
    // „Anzeige existiert nicht" — bis der nächste Poll Daten bringt.
    // ⚠ Dauerhaft ablehnen, nicht `Once`: die Sicht ruft `getData` mehr als einmal
    // (Effekt + Auto-Refresh); ein einmaliger Fehler wäre vom zweiten Abruf
    // überholt, und die Probe sähe in beiden Bauformen dasselbe Bild (gemessen
    // 22.09.: der Sprengsatz blieb grün).
    vi.mocked(liveDashboardApi.getData).mockRejectedValue(new Error('Backend nicht erreichbar'))
    try {
      window.location.hash = '#/cockpit/live?fokus=live:energiefluss'
      renderMitProvidern(<CockpitLiveV4 anlageId={1} />)
      expect(await screen.findByRole('alert')).toBeInTheDocument()
      // Kurz warten, dass kein späterer Render den Hinweis doch noch bringt.
      await new Promise((r) => setTimeout(r, 150))
      expect(screen.queryByText(/gibt es in dieser Sicht nicht/)).not.toBeInTheDocument()
    } finally {
      vi.mocked(liveDashboardApi.getData).mockImplementation(() => Promise.resolve(daten))
    }
  })

  it('ohne ?fokus= rendert die Sicht wie bisher (Gegenrichtung)', async () => {
    window.location.hash = '#/cockpit/live'
    renderMitProvidern(<CockpitLiveV4 anlageId={1} />)
    // Der Energiefluss trägt sein ⤢ wie bisher (in seiner eigenen Kopfzeile).
    await waitFor(() => expect(screen.getByLabelText('Energiefluss: Fokus / Vollbild')).toBeInTheDocument())
    expect(screen.getByLabelText('Auf einen Blick: Fokus / Vollbild')).toBeInTheDocument()
    expect(screen.queryByText(/gibt es in dieser Sicht nicht/)).not.toBeInTheDocument()
  })
})
