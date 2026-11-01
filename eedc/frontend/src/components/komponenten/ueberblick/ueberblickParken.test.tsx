/**
 * P-433-2b S1c «Karten-Teile einzeln parkbar» (Go Gernot 1.11.2026, Entscheid Master Option C): Render-Proben der
 * Überblick-Blöcke beider Hubs unter einem echten `ParkProvider`.
 *
 * - drei Hüllen je Hub (`el:ueberblick-karte-geraet|-heute|-betrieb`), Heute/Betrieb nur mit Werten (keine leere Hülle);
 * - Spaltenlogik: Schaubild + Karte offen ⇒ 2/3 zu 1/3; Schaubild geparkt ⇒ Karten nebeneinander; alle Karten geparkt ⇒
 *   Schaubild volle Breite;
 * - Meldung an das Hub-Gate erst nach Live- **und** Tag-Antwort, mit genau den gerenderten IDs;
 * - Park-Kopfzone an einer Hub-Karte (Long-Press im Kartenkopf);
 * - alte Park-ID `el:ueberblick-karte` aus `localStorage` ⇒ alle drei Karten geparkt, ihr Chip holt alle drei zurück;
 * - TH-E2 (Themen-Kacheln 4.2.0): die vierte Karte «Themen» nur mit Wert des gewählten Geräts, gemeldet, von der alten ID
 *   gedeckt, Spaltenregel (vier Karten ab `xl` nebeneinander), Tooltip «‹Kennung› · Stand».
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { act, fireEvent, screen } from '@testing-library/react'
import { cloneElement, type ReactElement } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { ThemeProvider } from '../../../context/ThemeContext'
import type { LiveDashboardResponse, LiveKomponente, LiveThema, LiveThemaEintrag } from '../../../api/liveDashboard'
import type { TagDetail } from '../../../api/energie_profil'
import type { Investition } from '../../../types'
import { GeparktBlock, ParkProvider } from '../../park'
import { renderMitProvidern, stubMatchMedia } from '../../../test/render'

const liveMock = vi.hoisted(() => ({ wert: { live: null as LiveDashboardResponse | null, wetter: null, tag: null as TagDetail | null } }))
vi.mock('./useLiveUeberblick', () => ({ useLiveUeberblick: () => liveMock.wert }))
const { default: UeberblickBlock, UeberblickBlockEmob } = await import('./UeberblickBlock')

const SICHT = 'test-ueberblick-s1c'
const S = 'el:ueberblick-schaubild'
const G = 'el:ueberblick-karte-geraet'
const H = 'el:ueberblick-karte-heute'
const B = 'el:ueberblick-karte-betrieb'

const inv = (id: number, typ: string, bez: string): Investition =>
  ({ id, anlage_id: 1, typ, bezeichnung: bez, aktiv: true, parameter: {} } as Investition)
const WP = inv(7, 'waermepumpe', 'WP Keller')
const WB = inv(6, 'wallbox', 'go-eCharger')
const EA = inv(8, 'e-auto', 'ID.4')

const live = (komponenten: LiveKomponente[], heute: Record<string, number> | null): LiveDashboardResponse =>
  ({ komponenten, gauges: [], heute_kwh_pro_komponente: heute } as unknown as LiveDashboardResponse)
const WP_LIVE = live([{ key: 'waermepumpe_7', label: 'WP Keller', icon: 'heater', erzeugung_kw: null, verbrauch_kw: 1.2 } as LiveKomponente], { waermepumpe_7: 3.3 })
const WP_TAG = { wp_geraete: [{ investition_id: 7, jaz: 4.1, waerme_kwh: 13.5, betrieb_stunden: { heizen: 5 } }] } as unknown as TagDetail
const WP_TAG_LEER = { wp_geraete: [] } as unknown as TagDetail
const EMOB_LIVE = live([
  { key: 'wallbox_6', label: 'go-eCharger', icon: 'plug', erzeugung_kw: null, verbrauch_kw: 7.4, typ: 'wallbox' } as LiveKomponente,
  { key: 'eauto_8', label: 'ID.4', icon: 'car', erzeugung_kw: null, verbrauch_kw: 7.4, typ: 'e-auto' } as LiveKomponente,
], { wallbox_6: 3.3, eauto_8: 3.3 })
const betrieb = (id: number, typ: string, feld: string) =>
  ({ investition_id: id, typ, feld, stunden: { laedt: 2 }, labels: { laedt: 'Lädt' }, wechsel: null })
const EMOB_TAG = {
  emob_heute: [], emob_betrieb: [betrieb(6, 'wallbox', 'ladezustand'), betrieb(8, 'e-auto', 'ladezustand_fahrzeug')],
} as unknown as TagDetail

function parke(...ids: string[]) {
  localStorage.setItem('eedc-park:' + SICHT, JSON.stringify(ids.map((id) => ({ id, titel: id === 'el:ueberblick-karte' ? 'Auf einen Blick' : id }))))
}
const imPark = (ui: ReactElement) => renderMitProvidern(<ParkProvider persistKey={SICHT}>{ui}<GeparktBlock /></ParkProvider>)
const huellen = () => [...document.querySelectorAll('[data-park-id]')].map((e) => e.getAttribute('data-park-id'))
const block = () => document.querySelector('[data-ueberblick-block]')!
const schaubildHuelle = () => document.querySelector(`[data-park-id="${S}"]`)
const karte = () => document.querySelector('[data-ueberblick-karte]')

type Fall = [string, () => ReactElement, () => void]
const FAELLE: Fall[] = [
  ['Wärme/Klima', () => <UeberblickBlock anlageId={1} geraete={[WP]} inv={WP} />, () => { liveMock.wert = { live: WP_LIVE, wetter: null, tag: WP_TAG } }],
  ['Wallbox', () => <UeberblickBlockEmob anlageId={1} geraete={[WB]} inv={WB} />, () => { liveMock.wert = { live: EMOB_LIVE, wetter: null, tag: EMOB_TAG } }],
  ['E-Auto', () => <UeberblickBlockEmob anlageId={1} geraete={[EA]} inv={EA} />, () => { liveMock.wert = { live: EMOB_LIVE, wetter: null, tag: EMOB_TAG } }],
]

beforeEach(() => { localStorage.clear(); stubMatchMedia() })

describe.each(FAELLE)('S1c %s: drei Hüllen und die Spaltenlogik', (_name, ui, daten) => {
  beforeEach(() => daten())

  it('nichts geparkt: Schaubild + drei Karten-Hüllen, 2/3 zu 1/3', () => {
    imPark(ui())
    expect(huellen()).toEqual([S, G, H, B])
    expect(block().className).toContain('xl:grid-cols-3')
    expect(schaubildHuelle()?.className).toContain('xl:col-span-2')
    // Der Kartenkopf liegt in der Hülle (Kopfzone der Geste).
    expect(document.querySelector(`[data-park-id="${G}"] [data-karte="geraet"]`)).not.toBeNull()
  })

  it('eine Karte geparkt: die anderen bleiben, Spalten wie bisher', () => {
    parke(H)
    imPark(ui())
    expect(huellen()).toEqual([S, G, B])
    expect(block().className).toContain('xl:grid-cols-3')
  })

  it('alle Karten geparkt: keine Karte, das Schaubild nimmt die volle Breite', () => {
    parke(G, H, B)
    imPark(ui())
    expect(huellen()).toEqual([S])
    expect(karte()).toBeNull()
    expect(block().className).not.toContain('xl:grid-cols-3')
    expect(schaubildHuelle()?.className).not.toContain('xl:col-span-2')
  })

  it('Schaubild geparkt: die offenen Karten nebeneinander in voller Breite', () => {
    parke(S)
    imPark(ui())
    expect(huellen()).toEqual([G, H, B])
    expect(block().className).not.toContain('xl:grid-cols-3')
    expect(karte()?.className).toContain('md:grid-cols-3')
    expect(karte()?.className).not.toContain('xl:grid-cols-1')
  })

  it('alles geparkt: der Blockinhalt ist leer (der Hub blendet den Block nach der Meldung aus)', () => {
    parke(S, G, H, B)
    imPark(ui())
    expect(huellen()).toEqual([])
    expect(block().textContent).toBe('')
  })
})

describe('S1c Wärme/Klima: neben dem Schaubild bleiben die Karten untereinander (Gestalt wie bisher)', () => {
  it('Karten-Behälter `space-y-3`, solange das Schaubild offen ist', () => {
    liveMock.wert = { live: WP_LIVE, wetter: null, tag: WP_TAG }
    imPark(<UeberblickBlock anlageId={1} geraete={[WP]} inv={WP} />)
    expect(karte()?.className).toBe('space-y-3')
  })
})

describe('S1c: Heute/Betrieb nur mit Werten — und die Meldung an das Hub-Gate', () => {
  it('ohne Heute- und Betriebswerte: nur die Gerät-Hülle, keine leere Hülle', () => {
    liveMock.wert = { live: live([], null), wetter: null, tag: WP_TAG_LEER }
    imPark(<UeberblickBlock anlageId={1} geraete={[WP]} inv={WP} />)
    expect(huellen()).toEqual([S, G])
  })

  it('gemeldet wird erst nach Live- UND Tag-Antwort, mit genau den gerenderten IDs', () => {
    const melde = vi.fn()
    liveMock.wert = { live: WP_LIVE, wetter: null, tag: null }
    const r = imPark(<UeberblickBlock anlageId={1} geraete={[WP]} inv={WP} meldeParkIds={melde} />)
    expect(melde).not.toHaveBeenCalled()
    liveMock.wert = { live: WP_LIVE, wetter: null, tag: WP_TAG }
    r.rerender(
      <MemoryRouter><ThemeProvider><ParkProvider persistKey={SICHT}>
        <UeberblickBlock anlageId={1} geraete={[WP]} inv={WP} meldeParkIds={melde} /><GeparktBlock />
      </ParkProvider></ThemeProvider></MemoryRouter>,
    )
    expect(melde).toHaveBeenLastCalledWith([S, G, H, B])
  })

  it('ohne Heute/Betrieb meldet der Block nur Schaubild und Gerät', () => {
    const melde = vi.fn()
    liveMock.wert = { live: live([], null), wetter: null, tag: WP_TAG_LEER }
    imPark(<UeberblickBlockEmob anlageId={1} geraete={[WB]} inv={WB} meldeParkIds={melde} />)
    expect(melde).toHaveBeenLastCalledWith([S, G])
  })
})

describe('S1c: Park-Kopfzone an einer Hub-Karte', () => {
  beforeEach(() => { vi.useFakeTimers() })
  afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks() })

  it('Long-Press im Kartenkopf der Wallbox öffnet «Parken»; Parken legt «Wallbox» auf den Parkplatz', () => {
    vi.spyOn(Element.prototype, 'getBoundingClientRect').mockReturnValue({
      top: 100, left: 0, bottom: 400, right: 400, width: 400, height: 300, x: 0, y: 100, toJSON: () => ({}),
    } as DOMRect)
    liveMock.wert = { live: EMOB_LIVE, wetter: null, tag: EMOB_TAG }
    imPark(<UeberblickBlockEmob anlageId={1} geraete={[WB]} inv={WB} />)
    fireEvent.touchStart(screen.getByText('go-eCharger', { selector: '[data-karte="geraet"] span' }), { touches: [{ clientX: 50, clientY: 120 }] })
    act(() => { vi.advanceTimersByTime(600) })
    fireEvent.click(screen.getByRole('button', { name: 'Parken' }))
    expect(huellen()).toEqual([S, H, B])
    expect(JSON.parse(localStorage.getItem('eedc-park:' + SICHT)!)).toEqual([{ id: G, titel: 'Wallbox' }])
  })
})

describe('S1c: alte Park-ID `el:ueberblick-karte` (bis S1c die ganze Karte)', () => {
  it.each(FAELLE)('%s: alle drei Karten geparkt; der Chip «Auf einen Blick» holt alle drei zurück', (_name, ui, daten) => {
    daten()
    parke('el:ueberblick-karte')
    imPark(ui())
    expect(huellen()).toEqual([S])
    expect(block().className).not.toContain('xl:grid-cols-3')
    fireEvent.click(screen.getByText('Parkplatz (1)'))
    fireEvent.click(screen.getByRole('button', { name: 'Auf einen Blick' }))
    expect(huellen()).toEqual([S, G, H, B])
    expect(JSON.parse(localStorage.getItem('eedc-park:' + SICHT)!)).toEqual([])
  })
})

describe('TH-E2: vierte Karte «Themen» (`el:ueberblick-karte-themen`) — nur mit Wert, alte ID deckt sie, Spaltenregel', () => {
  const T = 'el:ueberblick-karte-themen'
  const stand = new Date(2026, 10, 1, 11, 27).toISOString()
  const eintrag = (id: string, label: string, wert: string, kennung: string | null, zeitpunkt: string | null = stand): LiveThemaEintrag =>
    ({ id, label, wert, einheit: '', zeitpunkt, device_class: null, quelle: 'ha', kennung })
  const themen = (inv: number): LiveThema[] => [
    { investition_id: inv, id: 't1', name: 'Fahrzeugzustand', eintraege: [eintrag('e1', 'Türen', 'locked', 'lock.carport'), eintrag('e2', 'Reifen', '259.5', 'eedc/1_A/live/inv/8_ID.4/thema_e2', null)] },
    { investition_id: inv, id: 't2', name: 'Service', eintraege: [eintrag('e3', 'Tage', '41', null, null)] },
  ]
  const MIT: Fall[] = [
    ['Wärme/Klima', FAELLE[0][1], () => { liveMock.wert = { live: { ...WP_LIVE, themen: themen(7) }, wetter: null, tag: WP_TAG } }],
    ['Wallbox', FAELLE[1][1], () => { liveMock.wert = { live: { ...EMOB_LIVE, themen: [...themen(6), ...themen(8)] }, wetter: null, tag: EMOB_TAG } }],
    ['E-Auto', FAELLE[2][1], () => { liveMock.wert = { live: { ...EMOB_LIVE, themen: [...themen(6), ...themen(8)] }, wetter: null, tag: EMOB_TAG } }],
  ]

  it.each(MIT)('%s: mit Themen des gewählten Geräts vier Karten-Hüllen, gemeldet mit der Themen-ID', (_n, ui, daten) => {
    daten()
    const melde = vi.fn()
    imPark(cloneElement(ui(), { meldeParkIds: melde }))
    expect(huellen()).toEqual([S, G, H, B, T])
    expect(melde).toHaveBeenLastCalledWith([S, G, H, B, T])
    const karte = document.querySelector(`[data-park-id="${T}"] [data-karte="themen"]`)!
    expect(karte.textContent).toContain('Themen')
    expect([...karte.querySelectorAll('[data-thema]')].map((d) => d.getAttribute('data-thema'))).toEqual(['t1', 't2'])
    const zeile = (id: string) => karte.querySelector(`[data-zeile="thema-${id}"]`)!
    expect(zeile('e1').textContent).toBe('Türenlocked')
    expect(zeile('e2').textContent).toBe('Reifen259,5')
    // Tooltip «‹Entität bzw. Topic› · Stand hh:mm» (Entscheid Master zu H2); ohne Zeitpunkt nur die Kennung, ohne beides keiner.
    expect(zeile('e1').getAttribute('title')).toBe('lock.carport · Stand 11:27')
    expect(zeile('e2').getAttribute('title')).toBe('eedc/1_A/live/inv/8_ID.4/thema_e2')
    expect(zeile('e3').getAttribute('title')).toBeNull()
  })

  it('Themen nur an einem anderen Gerät ⇒ keine vierte Hülle, keine Meldung der Themen-ID', () => {
    liveMock.wert = { live: { ...WP_LIVE, themen: themen(99) }, wetter: null, tag: WP_TAG }
    const melde = vi.fn()
    imPark(<UeberblickBlock anlageId={1} geraete={[WP]} inv={WP} meldeParkIds={melde} />)
    expect(huellen()).toEqual([S, G, H, B])
    expect(melde).toHaveBeenLastCalledWith([S, G, H, B])
  })

  it.each(MIT)('%s: alte Park-ID `el:ueberblick-karte` parkt auch «Themen»; der Chip holt alle vier zurück', (_n, ui, daten) => {
    daten()
    parke('el:ueberblick-karte')
    imPark(ui())
    expect(huellen()).toEqual([S])
    fireEvent.click(screen.getByText('Parkplatz (1)'))
    fireEvent.click(screen.getByRole('button', { name: 'Auf einen Blick' }))
    expect(huellen()).toEqual([S, G, H, B, T])
  })

  it.each(MIT)('%s: Spaltenregel — Schaubild geparkt ⇒ vier Karten ab `xl` nebeneinander (darunter zwei)', (_n, ui, daten) => {
    daten()
    parke(S)
    imPark(ui())
    expect(huellen()).toEqual([G, H, B, T])
    expect(karte()?.className).toContain('md:grid-cols-2')
    expect(karte()?.className).toContain('xl:grid-cols-4')
    expect(karte()?.className).not.toContain('md:grid-cols-3')
  })

  it.each(MIT)('%s: «Themen» geparkt ⇒ die anderen drei bleiben, Raster wie ohne Themen', (_n, ui, daten) => {
    daten()
    parke(T, S)
    imPark(ui())
    expect(huellen()).toEqual([G, H, B])
    expect(karte()?.className).toContain('md:grid-cols-3')
    expect(karte()?.className).not.toContain('xl:grid-cols-4')
  })

  it.each(MIT)('%s: neben dem Schaubild stehen die vier Karten untereinander', (n, ui, daten) => {
    daten()
    imPark(ui())
    expect(karte()?.className).toContain(n === 'Wärme/Klima' ? 'space-y-3' : 'xl:grid-cols-1')
  })
})
