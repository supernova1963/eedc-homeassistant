/**
 * Cockpit → Live: der gruppierte Energiefluss in Karte, ⤢-Vollbild und
 * Deep-Link (Bau A §A4, #341/#348) — Render-Probe über die echte Sicht.
 *
 * `EnergieFluss.gruppen.test.tsx` prüft die Komponente allein. Hier geht es um
 * die Verdrahtung in `CockpitLiveV4`: im Vollbild (⤢ oder `?fokus=`) reicht die
 * Sicht das Vollbild-Flag durch, und `EnergieFluss` misst die Höhe seiner
 * eigenen Zeichenfläche — die Zeichenfläche nimmt dann deren Verhältnis an
 * (NICHT das des Fensters: das Overlay trägt zwei Kopfzeilen, Bau A W-1). In
 * der Karte bleibt sie 600 × 380 (die Karte wird nie höher), auch wenn eine
 * Höhe gemeldet wird.
 *
 * Seit §A5 dazu die „Liste mit Balken": Öffnen per Klick und Tastatur, ESC-
 * Staffelung über dem ⤢-Vollbild und im Deep-Link, die 5-s-Regel (Key weg ⇒
 * zu), Fokus-Rückgabe und die unberührten Fokus-IDs.
 *
 * ⚠ jsdom hat keinen ResizeObserver; der Stub hier meldet für den Container
 * 1000 px Breite und für das SVG 500 px Höhe (Verhältnis 2) — ein Wert, der
 * weder die Karte (600/380 ≈ 1,58) noch das jsdom-Fenster (1024/768 ≈ 1,33) ist.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { screen, waitFor, fireEvent, within } from '@testing-library/react'
import type {
  BoersenpreisResponse, LiveDashboardResponse, LiveKomponente, TagesverlaufResponse,
} from '../api/liveDashboard'
import { renderMitProvidern, stubMatchMedia } from '../test/render'

const pv = (id: number, label: string, ausr: string, kw: number): LiveKomponente =>
  ({ key: `pv_${id}`, label, icon: 'sun', erzeugung_kw: kw, verbrauch_kw: null, typ: 'pv-module', ausrichtung_label: ausr, leistung_kwp: 3 })
const sp = (id: number, label: string, kw: number): LiveKomponente =>
  ({ key: `batterie_${id}`, label, icon: 'battery', erzeugung_kw: null, verbrauch_kw: kw, typ: 'speicher', kapazitaet_kwh: 10 })

const daten: LiveDashboardResponse = {
  anlage_id: 1, anlage_name: 'Demo', zeitpunkt: '2026-09-28T12:00:00', verfuegbar: true,
  // Neun Strings in drei Richtungen und vier Speicher: bei 600 px Karte
  // bündelt das Layout nach Ausrichtung und zu „Speicher (4)".
  komponenten: [
    pv(11, 'Süd 1', 'Süd', 1.9), pv(12, 'Süd 2', 'Süd', 1.8), pv(13, 'Süd 3', 'Süd', 1.7),
    pv(14, 'Süd 4', 'Süd', 1.2), pv(15, 'Süd 5', 'Süd', 0.9), pv(16, 'Ost 1', 'Ost', 0.6),
    pv(17, 'Ost 2', 'Ost', 0.5), pv(18, 'West 1', 'West', 1.4), pv(19, 'West 2', 'West', 1.3),
    sp(21, 'Akku 1', 1.2), sp(22, 'Akku 2', 0.8), sp(23, 'Akku 3', 0.6), sp(24, 'Akku 4', 0.4),
    { key: 'waermepumpe_31', label: 'Wärmepumpe', icon: 'flame', erzeugung_kw: null, verbrauch_kw: 1.4, typ: 'waermepumpe' },
    { key: 'netz', label: 'Stromnetz', icon: 'zap', erzeugung_kw: null, verbrauch_kw: 5.1 },
    { key: 'haushalt', label: 'Restverbrauch', icon: 'home', erzeugung_kw: null, verbrauch_kw: 0.8 },
  ],
  summe_erzeugung_kw: 11.3, summe_verbrauch_kw: 11.3, summe_pv_kw: 11.3,
  gauges: [], heute_pv_kwh: 40, heute_einspeisung_kwh: 20, heute_netzbezug_kwh: 1,
  heute_eigenverbrauch_kwh: 20, gestern_pv_kwh: 30, gestern_einspeisung_kwh: 15,
  gestern_netzbezug_kwh: 2, gestern_eigenverbrauch_kwh: 15,
  heute_kwh_pro_komponente: null, warmwasser_temperatur_c: null,
}

const leererVerlauf: TagesverlaufResponse = { anlage_id: 1, datum: '2026-09-28', serien: [], punkte: [] }
const keinePreise: BoersenpreisResponse = {
  anlage_id: 1, markt: 'DE', tage: [], monats_durchschnitt_cent: null,
  aktuelle_stunde: null, heute: null, hinweis: null, endpreis_jetzt_cent: null,
}

/** Was der nächste Abruf liefert — eine Probe kann den 5-s-Takt damit umstellen. */
let antwort: LiveDashboardResponse = daten

vi.mock('../api/liveDashboard', () => ({
  liveDashboardApi: {
    getData: vi.fn(() => Promise.resolve(antwort)),
    getWetter: vi.fn(() => Promise.reject(new Error('kein Wetter'))),
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

/** Das Energiefluss-SVG (nicht die Lucide-Icons, die auch `viewBox` tragen). */
function flussSvg(): SVGSVGElement {
  const svg = document.body.querySelector<SVGSVGElement>('svg.flex-1')
  expect(svg, 'kein Energiefluss-SVG').not.toBeNull()
  return svg!
}
const verhaeltnis = (svg: SVGSVGElement) => {
  const [, , w, h] = svg.getAttribute('viewBox')!.split(' ').map(Number)
  return w / h
}
const gruppenTitel = () => [...document.body.querySelectorAll('svg.flex-1 g[data-title]')]
  .filter(g => g.querySelectorAll('rect[data-stapel]').length === 2)
  .map(g => (g.getAttribute('data-title') ?? '').split('\n')[0])

describe('Cockpit → Live: gruppierter Energiefluss', () => {
  beforeEach(() => {
    localStorage.clear()
    _clearSwrCacheForTests()
    stubMatchMedia()
    window.location.hash = ''
    antwort = daten
    vi.stubGlobal('ResizeObserver', class {
      private cb: ResizeObserverCallback
      constructor(cb: ResizeObserverCallback) { this.cb = cb }
      observe(target: Element) {
        const istSvg = target.tagName.toLowerCase() === 'svg'
        this.cb([{ target, contentRect: { width: 1000, height: istSvg ? 500 : 900 } } as unknown as ResizeObserverEntry], this as unknown as ResizeObserver)
      }
      unobserve() {}
      disconnect() {}
    })
  })
  afterEach(() => {
    window.location.hash = URSPRUNG
    vi.unstubAllGlobals()
  })

  it('Deep-Link `?fokus=live:energiefluss`: das Overlay zeigt die Gruppen, die Zeichenfläche hat das Verhältnis der gemessenen Fläche', async () => {
    window.location.hash = '#/cockpit/live?fokus=live:energiefluss'
    renderMitProvidern(<CockpitLiveV4 anlageId={1} />)
    expect(await screen.findByRole('heading', { name: 'Energiefluss', level: 2 })).toBeInTheDocument()
    await waitFor(() => expect(gruppenTitel()).toEqual(['Ost (2)', 'Süd (5)', 'West (2)', 'Speicher (4)']))
    expect(verhaeltnis(flussSvg())).toBeCloseTo(1000 / 500, 6)
    // §A5 (Positiv-Probe, vorher A4-Gegenrichtung): im Deep-Link sind GENAU die
    // Gruppen Knöpfe — die Sicht reicht `onGruppeKlick` auch hier durch.
    const knoepfe = [...flussSvg().querySelectorAll('[role="button"]')]
    expect(knoepfe.map(k => k.getAttribute('data-gruppe'))).toEqual(['pv_grp_ost', 'pv_grp_sued', 'pv_grp_west', 'batterie_grp'])
    expect(flussSvg().querySelectorAll('[tabindex="0"]')).toHaveLength(4)
    expect(flussSvg().querySelectorAll('.cursor-pointer')).toHaveLength(4)
  })

  it('Karte (ohne ?fokus=): dieselben Gruppen, Zeichenfläche 600 × 380 — die gemeldete Höhe bleibt unausgewertet', async () => {
    window.location.hash = '#/cockpit/live'
    renderMitProvidern(<CockpitLiveV4 anlageId={1} />)
    await waitFor(() => expect(gruppenTitel()).toEqual(['Ost (2)', 'Süd (5)', 'West (2)', 'Speicher (4)']))
    expect(flussSvg().getAttribute('viewBox')).toBe('0 0 600 380')
  })
})

// ── §A5: die „Liste mit Balken" in der Sicht ──────────────────────────────────

const tick = () => new Promise(r => setTimeout(r, 0))
const escSenden = () => {
  const e = new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true })
  document.dispatchEvent(e)
  return e
}
const gruppenKachel = async (key: string) => {
  await waitFor(() => expect(document.body.querySelector(`[data-gruppe="${key}"]`)).not.toBeNull())
  return document.body.querySelector<SVGGElement>(`[data-gruppe="${key}"]`)!
}
/** Ein neuer 5-s-Abruf, sofort ausgelöst: die Sicht frischt beim Sichtwechsel auf. */
const naechsterTakt = () => document.dispatchEvent(new Event('visibilitychange'))

describe('Cockpit → Live §A5: Liste mit Balken', () => {
  beforeEach(() => {
    localStorage.clear()
    _clearSwrCacheForTests()
    stubMatchMedia()
    window.location.hash = '#/cockpit/live'
    antwort = daten
    vi.stubGlobal('ResizeObserver', class {
      private cb: ResizeObserverCallback
      constructor(cb: ResizeObserverCallback) { this.cb = cb }
      observe(target: Element) {
        const istSvg = target.tagName.toLowerCase() === 'svg'
        this.cb([{ target, contentRect: { width: 1000, height: istSvg ? 500 : 900 } } as unknown as ResizeObserverEntry], this as unknown as ResizeObserver)
      }
      unobserve() {}
      disconnect() {}
    })
  })
  afterEach(() => {
    window.location.hash = URSPRUNG
    vi.unstubAllGlobals()
  })

  it('Karte: Klick öffnet den Dialog „Süd (5)" mit einer Zeile je Mitglied; Fokus auf „Schließen"; Schließen gibt den Fokus an die Kachel zurück', async () => {
    renderMitProvidern(<CockpitLiveV4 anlageId={1} />)
    const sued = await gruppenKachel('pv_grp_sued')
    fireEvent.click(sued)
    const d = await screen.findByRole('dialog', { name: 'Süd (5)' })
    expect([...d.querySelectorAll('li[data-zeile]')].map(li => li.getAttribute('data-zeile')))
      .toEqual(['pv_11', 'pv_12', 'pv_13', 'pv_14', 'pv_15'])
    const schliessen = within(d).getByRole('button', { name: /Schließen/ })
    expect(document.activeElement).toBe(schliessen)
    fireEvent.click(schliessen)
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    // Rückgabe über den Key (Safari fokussiert beim Mausklick nichts)
    await waitFor(() => expect(document.activeElement).toBe(document.body.querySelector('[data-gruppe="pv_grp_sued"]')))
  })

  it('Karte: Tastatur — Enter öffnet, Leertaste auch; ESC schließt und gibt den Fokus zurück', async () => {
    renderMitProvidern(<CockpitLiveV4 anlageId={1} />)
    const speicher = await gruppenKachel('batterie_grp')
    fireEvent.keyDown(speicher, { key: 'Enter' })
    expect(await screen.findByRole('dialog', { name: 'Speicher (4)' })).toBeInTheDocument()
    expect(escSenden().defaultPrevented).toBe(true)
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    await waitFor(() => expect(document.activeElement).toBe(document.body.querySelector('[data-gruppe="batterie_grp"]')))
    fireEvent.keyDown(await gruppenKachel('pv_grp_west'), { key: ' ' })
    expect(await screen.findByRole('dialog', { name: 'West (2)' })).toBeInTheDocument()
  })

  it('⤢-Vollbild: ESC schließt NUR die Liste, das Vollbild darunter bleibt', async () => {
    renderMitProvidern(<CockpitLiveV4 anlageId={1} />)
    await gruppenKachel('pv_grp_sued')
    fireEvent.click(screen.getByRole('button', { name: 'Energiefluss: Fokus / Vollbild' }))
    expect(await screen.findByRole('button', { name: /Zurück/ })).toBeInTheDocument()
    fireEvent.click(await gruppenKachel('pv_grp_ost'))
    const d = await screen.findByRole('dialog', { name: 'Ost (2)' })
    // Die Liste liegt ÜBER dem Vollbild: ihr Portal steht im body danach.
    const vollbild = screen.getByRole('button', { name: /Zurück/ }).closest('.fixed')!
    expect(vollbild.compareDocumentPosition(d) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    escSenden()
    await tick()
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    // das äußere Vollbild ist noch da (es hat nach defaultPrevented entschieden)
    expect(screen.getByRole('button', { name: /Zurück/ })).toBeInTheDocument()
    expect(screen.getByText('Fokus / Vollbild')).toBeInTheDocument()
  })

  it('Deep-Link: die Liste öffnet ÜBER dem rahmenlosen Vollbild; ESC und „Schließen" schließen nur sie', async () => {
    window.location.hash = '#/cockpit/live?fokus=live:energiefluss'
    renderMitProvidern(<CockpitLiveV4 anlageId={1} />)
    expect(await screen.findByRole('heading', { name: 'Energiefluss', level: 2 })).toBeInTheDocument()
    fireEvent.click(await gruppenKachel('pv_grp_sued'))
    const d = await screen.findByRole('dialog', { name: 'Süd (5)' })
    const deep = screen.getByRole('heading', { name: 'Energiefluss', level: 2 }).closest('.fixed')!
    expect(deep.compareDocumentPosition(d) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    // Der Dialog hat seinen Ausweg, auch wenn das Deep-Link-Vollbild keinen hat
    expect(within(d).getByRole('button', { name: /Schließen/ })).toBeInTheDocument()
    escSenden()
    await tick()
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    expect(screen.getByRole('heading', { name: 'Energiefluss', level: 2 })).toBeInTheDocument()
    // …und noch einmal über „Schließen"
    fireEvent.click(await gruppenKachel('batterie_grp'))
    fireEvent.click(within(await screen.findByRole('dialog', { name: 'Speicher (4)' })).getByRole('button', { name: /Schließen/ }))
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    expect(screen.getByRole('heading', { name: 'Energiefluss', level: 2 })).toBeInTheDocument()
  })

  it('5-s-Takt: die Zeilen folgen den neuen Werten; entfällt der Gruppen-Key, schließt sich die Liste', async () => {
    renderMitProvidern(<CockpitLiveV4 anlageId={1} />)
    fireEvent.click(await gruppenKachel('pv_grp_sued'))
    const d = await screen.findByRole('dialog', { name: 'Süd (5)' })
    const wert = (key: string) => d.querySelector(`li[data-zeile="${key}"] > span:nth-child(3)`)?.textContent
    expect(wert('pv_11')).toBe('1.900 W')
    // Takt 1: neuer Wert, dieselbe Gruppe ⇒ bleibt offen, Zeile aktuell
    antwort = { ...daten, komponenten: daten.komponenten.map(k => (k.key === 'pv_11' ? { ...k, erzeugung_kw: 0.7 } : k)) }
    naechsterTakt()
    await waitFor(() => expect(wert('pv_11')).toBe('700 W'))
    expect(screen.getByRole('dialog', { name: 'Süd (5)' })).toBeInTheDocument()
    // Takt 2: nur noch EIN Süd-String ⇒ keine Gruppe „Süd" mehr ⇒ zu
    antwort = { ...daten, komponenten: daten.komponenten.filter(k => !['pv_12', 'pv_13', 'pv_14', 'pv_15'].includes(k.key)) }
    naechsterTakt()
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    expect(document.body.querySelector('[data-gruppe="pv_grp_sued"]')).toBeNull()
    // Takt 3: die Gruppe kommt zurück — das Fenster ist ZU, nicht nur versteckt,
    // und springt deshalb nicht von selbst wieder auf.
    antwort = daten
    naechsterTakt()
    await gruppenKachel('pv_grp_sued')
    await tick()
    expect(screen.queryByRole('dialog')).toBeNull()
  })

  it('das Fenster bekommt keine Fokus-ID und keinen Einbetten-Knopf (LIVE_FOKUS_IDS unverändert)', async () => {
    const { LIVE_FOKUS_IDS } = await import('./CockpitLiveV4')
    expect([...LIVE_FOKUS_IDS]).toEqual([
      'live:energiefluss', 'live:auf-einen-blick', 'live:wetter-heute', 'live:tagesverlauf', 'live:boersenpreis',
    ])
    renderMitProvidern(<CockpitLiveV4 anlageId={1} />)
    fireEvent.click(await gruppenKachel('pv_grp_sued'))
    const d = await screen.findByRole('dialog', { name: 'Süd (5)' })
    expect(within(d).queryByRole('button', { name: /Link|Einbetten/ })).toBeNull()
  })
})
