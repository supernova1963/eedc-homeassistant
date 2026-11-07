/**
 * Hub-Block «Überblick» (P-433-2 E1): auf der Typ-Seite Wärmepumpe (seit P-433-2b K1 auch Wallbox und E-Auto, seit S1b
 * mit ihrer Szene «Ladepunkt» bzw. «Fahrzeug» — die Hub-Probe ist dafür angepasst, Bauplan S1b E3), als
 * oberster Block (auch bei gespeicherter Reihenfolge, `voranstellen`), Summary
 * statisch, Fokus-ID `ueberblick` (Snapshot-Zuwachs). Park seit S1c: Schaubild und je Karte eine ID
 * (`el:ueberblick-karte-geraet|-heute|-betrieb`); das Block-Gate folgt `regVerstecken` — der Block meldet seine gerenderten
 * IDs unter `ueberblick:<inv.id>`; ohne Meldung bleibt er, mit Meldung verschwindet er, wenn alle gemeldeten geparkt sind.
 * Die alte ID `el:ueberblick-karte` gilt als «alle drei Karten geparkt».
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { useState } from 'react'
import { screen, waitFor, fireEvent, within } from '@testing-library/react'

vi.mock('../api/liveDashboard', () => ({
  liveDashboardApi: {
    getData: vi.fn(() => new Promise(() => {})),
    getWetter: vi.fn(() => new Promise(() => {})),
  },
}))
vi.mock('../api/energie_profil', () => ({
  energieProfilApi: { getTagDetail: vi.fn(() => new Promise(() => {})) },
}))

// Nachlauf 4.2.1 N3: die Hub-Sicht lädt ihre Geräte über den Adapter — für die Deep-Link-Probe ein festes Gerät je Typ.
const adapterGeraete = vi.hoisted(() => ({ liste: [] as unknown[] }))
vi.mock('./komponentenAdapter', async (orig) => {
  const o = await orig<typeof import('./komponentenAdapter')>()
  const fest = { fetch: () => Promise.resolve(adapterGeraete.liste) }
  return {
    ...o,
    KOMPONENTEN_ADAPTER: {
      ...o.KOMPONENTEN_ADAPTER,
      waermepumpe: { ...o.KOMPONENTEN_ADAPTER.waermepumpe, ...fest },
      wallbox: { ...o.KOMPONENTEN_ADAPTER.wallbox, ...fest },
      speicher: { ...o.KOMPONENTEN_ADAPTER.speicher, ...fest },
    },
  }
})

import { liveDashboardApi } from '../api/liveDashboard'
import { investitionenApi } from '../api/investitionen'
import KomponentenTypV4, { aktivAusDeepLink, geraetBloecke, geraetEinbettenZusatz, UEBERBLICK_TYPEN, VORANSTELLEN } from './KomponentenTypV4'
import { BlockShell } from '../components/blocks'
import { renderMitProvidern, stubMatchMedia } from '../test/render'
import type { ParkApi } from '../components/park'
import type { KompGeraet } from './komponentenAdapter'
import type { Investition } from '../types'

const park = (geparkt: string[] = []): ParkApi => ({
  aktiv: false, istGeparkt: (id) => geparkt.includes(id), park: () => {}, entparke: () => {}, zuruecksetzen: () => {},
  geparkt: [], registriere: () => () => {}, parkbareAnzahl: 0,
})
const geraet = (id: number, typ: string): KompGeraet => ({
  inv: { id, anlage_id: 1, typ, bezeichnung: `Gerät ${id}`, aktiv: true, parameter: { wp_art: 'sole_wasser' } } as Investition,
  label: `Gerät ${id}`, status: [],
})

beforeEach(() => { localStorage.clear(); stubMatchMedia() })

describe('Block «Überblick» im Komponenten-Hub', () => {
  it('für Wärmepumpe, Wallbox und E-Auto — und dort als erster Block', () => {
    // Ü7 (P-433-2b K1): die E-Mobilität bekommt den Block; seit S1b mit Schaubild (Summary wie Wärme/Klima).
    expect(UEBERBLICK_TYPEN).toEqual(['waermepumpe', 'wallbox', 'e-auto'])
    const wp = geraetBloecke(geraet(7, 'waermepumpe'), 'waermepumpe', 1, park(), {}, () => {})
    expect(wp[0].id).toBe('ueberblick')
    expect(wp[0].title).toBe('Überblick')
    expect(wp[0].defaultOpen).toBe(true)
    expect(wp[0].summary).toBe('Schaubild · Gerät 7')
    for (const typ of ['wallbox', 'e-auto']) {
      const b = geraetBloecke(geraet(7, typ), typ, 1, park(), {}, () => {})
      expect(b[0].id).toBe('ueberblick')
      expect(b[0].summary).toBe('Schaubild · Gerät 7')
    }
    for (const typ of ['speicher', 'pv-module', 'sonstiges', 'balkonkraftwerk']) {
      expect(geraetBloecke(geraet(7, typ), typ, 1, park(), {}, () => {}).map((b) => b.id)).not.toContain('ueberblick')
    }
  })

  const S = 'el:ueberblick-schaubild'
  const G = 'el:ueberblick-karte-geraet'
  const H = 'el:ueberblick-karte-heute'
  const B = 'el:ueberblick-karte-betrieb'
  const ALT = 'el:ueberblick-karte'

  it.each(['waermepumpe', 'wallbox', 'e-auto'])('S1c %s: Gate nach der Meldung des Blocks (regVerstecken)', (typ) => {
    const ids = (g: string[], gemeldet: Record<string, string[]>) =>
      geraetBloecke(geraet(7, typ), typ, 1, park(g), gemeldet, () => {}).map((b) => b.id)
    const alle = { 'ueberblick:7': [S, G, H, B] }
    const ohneHeuteBetrieb = { 'ueberblick:7': [S, G] }
    // Ohne Meldung (vor der ersten Live- und Tag-Antwort) bleibt der Block — auch wenn alles geparkt ist.
    expect(ids([S, G, H, B], {})).toContain('ueberblick')
    // keine / eine / alle Karten geparkt, Schaubild geparkt: Block bleibt, solange ein gemeldeter Teil offen ist.
    expect(ids([], alle)).toContain('ueberblick')
    expect(ids([H], alle)).toContain('ueberblick')
    expect(ids([G, H, B], alle)).toContain('ueberblick')
    expect(ids([S], alle)).toContain('ueberblick')
    expect(ids([S, G, H], alle)).toContain('ueberblick')
    // alles Gemeldete geparkt ⇒ Block weg.
    expect(ids([S, G, H, B], alle)).not.toContain('ueberblick')
    // Heute/Betrieb nicht gerendert (nicht gemeldet) ⇒ Schaubild + Gerät genügen — kein leerer Block (L2).
    expect(ids([S, G], ohneHeuteBetrieb)).not.toContain('ueberblick')
    // Alte ID: die ganze Karte war geparkt ⇒ gilt für alle drei Karten.
    expect(ids([S, ALT], alle)).not.toContain('ueberblick')
    expect(ids([ALT], alle)).toContain('ueberblick')
    // Die Meldung gilt je Gerät: die eines anderen Geräts versteckt diesen Block nicht.
    expect(ids([S, G], { 'ueberblick:8': [S, G] })).toContain('ueberblick')
  })

  it('S1c: der Block meldet unter `ueberblick:<inv.id>` an das Gate', () => {
    const melde = vi.fn()
    const b = geraetBloecke(geraet(7, 'waermepumpe'), 'waermepumpe', 1, park(), {}, melde)
    expect(b[0].id).toBe('ueberblick')
    const el = b[0].render(false) as { props: { meldeParkIds: (ids: string[]) => void } }
    el.props.meldeParkIds([S, G])
    expect(melde).toHaveBeenCalledWith('ueberblick:7', [S, G])
  })

  it.each([
    ['wallbox', 'Schaubild Ladepunkt', 'emob-ladepunkt-tag.webp'],
    ['e-auto', 'Schaubild Fahrzeug', 'emob-fahrzeug-tag.webp'],
  ])('E-Mobilität %s: die Szene gehört dem Typ (%s) — Schaubild und Karte montiert', (typ, aria, bild) => {
    const bloecke = geraetBloecke(geraet(7, typ), typ, 1, park(), {}, () => {})
    renderMitProvidern(<BlockShell persistKey={`v4-komponenten-${typ}`} bloecke={bloecke} sortierbar voranstellen={VORANSTELLEN} />)
    expect(document.querySelector('[data-ueberblick-schaubild]')).not.toBeNull()
    expect(document.querySelector('[data-ueberblick-schaubild] svg')?.getAttribute('aria-label')).toBe(aria)
    expect(document.querySelector('[data-panorama="tag"]')?.getAttribute('href')).toBe(`./backgrounds/${bild}`)
    expect(document.querySelector('[data-ueberblick-karte]')).not.toBeNull()
    expect(document.querySelector(`[data-ueberblick-emob="${typ}"]`)).not.toBeNull()
  })

  it('Aggregat ohne eigene Investition (id ≤ 0) bekommt keinen Überblick', () => {
    expect(geraetBloecke(geraet(0, 'waermepumpe'), 'waermepumpe', 1, park(), {}, () => {}).map((b) => b.id)).not.toContain('ueberblick')
  })

  it('gespeicherte Reihenfolge ohne `ueberblick` (Bestandsanwender) ⇒ Überblick steht vorn', () => {
    localStorage.setItem('eedc-bloecke:v4-komponenten-waermepumpe', JSON.stringify({
      order: ['status', 'verlauf', 'vergleich', 'infothek', 'daten-checker', 'einstellungen'], zu: ['verlauf', 'vergleich', 'infothek', 'daten-checker', 'einstellungen'],
    }))
    const bloecke = geraetBloecke(geraet(7, 'waermepumpe'), 'waermepumpe', 1, park(), {}, () => {}, [geraet(7, 'waermepumpe').inv, geraet(8, 'waermepumpe').inv])
    renderMitProvidern(<BlockShell persistKey="v4-komponenten-waermepumpe" bloecke={bloecke} sortierbar voranstellen={VORANSTELLEN} />)
    const titel = [...document.querySelectorAll('section')].map((s) => s.querySelector('span.font-semibold')?.textContent)
    expect(titel[0]).toBe('Überblick')
    expect(titel[1]).toBe('Kennzahlen (gesamte Laufzeit)')
    // Inhalt montiert (offen): Schaubild und Karte.
    expect(document.querySelector('[data-ueberblick-schaubild]')).not.toBeNull()
    expect(document.querySelector('[data-ueberblick-karte]')).not.toBeNull()
    expect(screen.getByText('Gerät 7')).toBeInTheDocument()
  })
})

/**
 * Nachlauf 4.2.1 (Lab-Befunde Gernot 2.11.2026). N2: `Block.render(fokus)` gibt `vollbild` an den Überblick weiter.
 * N3: `#/komponenten/<typ>?fokus=ueberblick:schaubild` ist keine Block-ID — der Hub rendert an Stelle der BlockShell das
 * Schaubild-Vollbild des gewählten Geräts (rahmenlos), ohne Überblick-Block oder mit geparktem Schaubild den Hinweis.
 */
describe('Nachlauf 4.2.1: Fokus des Überblicks', () => {
  it.each(['waermepumpe', 'wallbox', 'e-auto'])('N2 %s: render(true) ⇒ vollbild, render(false) ⇒ nicht; das Schaubild trägt `data-vollbild`', (typ) => {
    const b = geraetBloecke(geraet(7, typ), typ, 1, park(), {}, () => {})[0]
    expect(b.id).toBe('ueberblick')
    expect((b.render(true) as { props: { vollbild?: boolean } }).props.vollbild).toBe(true)
    expect((b.render(false) as { props: { vollbild?: boolean } }).props.vollbild).toBe(false)
    renderMitProvidern(<>{b.render(true)}</>)
    expect(document.querySelector('[data-ueberblick-schaubild]')?.getAttribute('data-vollbild')).toBe('true')
  })

  const URSPRUNG = window.location.hash
  afterEach(() => { window.location.hash = URSPRUNG })
  const overlay = () => document.querySelector<HTMLElement>('.fixed.inset-0.z-50')

  it.each(['waermepumpe', 'wallbox'])('N3 %s: ?fokus=ueberblick:schaubild ⇒ das Schaubild-Vollbild statt der Blöcke, rahmenlos', async (typ) => {
    adapterGeraete.liste = [geraet(7, typ)]
    window.location.hash = `#/komponenten/${typ}?fokus=ueberblick:schaubild`
    renderMitProvidern(<KomponentenTypV4 typ={typ} anlageId={1} />)
    expect(await screen.findByRole('heading', { name: 'Überblick · Schaubild', level: 2 })).toBeInTheDocument()
    const o = overlay()!
    expect(o.querySelector('[data-ueberblick-schaubild][data-vollbild]')).not.toBeNull()
    expect(document.querySelector('[data-ueberblick-karte]')).toBeNull()
    expect(screen.queryByText(/gibt es in dieser Sicht nicht/)).not.toBeInTheDocument()
    expect(screen.queryByText('Zurück')).not.toBeInTheDocument()
    expect(document.querySelector('section')).toBeNull() // keine BlockShell-Sektionen
  })

  it('N3: ohne Überblick-Block (Speicher) ⇒ Hinweis «gibt es nicht» statt der Sicht', async () => {
    adapterGeraete.liste = [geraet(7, 'speicher')]
    window.location.hash = '#/komponenten/speicher?fokus=ueberblick:schaubild'
    renderMitProvidern(<KomponentenTypV4 typ="speicher" anlageId={1} />)
    expect(await screen.findByText(/gibt es in dieser Sicht nicht/)).toBeInTheDocument()
    expect(document.querySelector('[data-ueberblick-schaubild]')).toBeNull()
  })

  it('N3: Schaubild geparkt ⇒ Hinweis (Muster `liveFokusVorhanden`)', async () => {
    adapterGeraete.liste = [geraet(7, 'waermepumpe')]
    localStorage.setItem('eedc-park:v4-komponenten-waermepumpe', JSON.stringify([{ id: 'el:ueberblick-schaubild', titel: 'Schaubild' }]))
    window.location.hash = '#/komponenten/waermepumpe?fokus=ueberblick:schaubild'
    renderMitProvidern(<KomponentenTypV4 typ="waermepumpe" anlageId={1} />)
    expect(await screen.findByText(/gibt es in dieser Sicht nicht/)).toBeInTheDocument()
    expect(document.querySelector('[data-ueberblick-schaubild]')).toBeNull()
  })

  it('N3: ohne Deep-Link bleibt die Sicht die BlockShell, das Schaubild trägt seinen ⤢', async () => {
    adapterGeraete.liste = [geraet(7, 'waermepumpe')]
    window.location.hash = '#/komponenten/waermepumpe'
    renderMitProvidern(<KomponentenTypV4 typ="waermepumpe" anlageId={1} />)
    await waitFor(() => expect(document.querySelector('[data-ueberblick-schaubild]')).not.toBeNull())
    expect(screen.getByRole('button', { name: 'Schaubild: Fokus / Vollbild' })).toBeInTheDocument()
    expect(overlay()).toBeNull()
  })
})

/**
 * Nachlauf 4.2.1 N5 (Entscheid Gernot 2.11.2026): `&geraet=<investition_id>` wählt auf einer Typ-Seite mit mehreren
 * Geräten das Gerät — sonst zeigte eine Dashboard-Karte immer das erste. Unbekannte ID ⇒ still das erste. «Link /
 * Einbetten» (Block-⤢ der BlockShell und Schaubild-⤢) schreibt den Parameter nur bei ≥ 2 Geräten des Typs.
 * Belegt wird das gewählte Gerät im Schaubild über die «Ohne Sensor»-Zeile der Szene «Ladepunkt» — sie nennt das Gerät,
 * dessen Szene gezeichnet ist (`baueLadepunktKacheln` für `inv`), sobald eine Live-Antwort da ist.
 */
describe('Nachlauf 4.2.1 N5: Gerät in der Deep-Link-Adresse', () => {
  const URSPRUNG = window.location.hash
  const ohneLive = () => new Promise(() => {})
  afterEach(() => {
    window.location.hash = URSPRUNG
    vi.mocked(liveDashboardApi.getData).mockImplementation(ohneLive as never)
  })
  const overlay = () => document.querySelector<HTMLElement>('.fixed.inset-0.z-50')
  const aktiverSelektor = () => screen.getAllByRole('button').filter((b) => b.className.includes('bg-primary-100')).map((b) => b.textContent)

  it('reine Helfer: Index aus der ID, Zusatz nur bei ≥ 2 echten Geräten', () => {
    const zwei = [geraet(7, 'wallbox'), geraet(8, 'wallbox')]
    expect(aktivAusDeepLink(zwei, 8)).toBe(1)
    expect(aktivAusDeepLink(zwei, 99)).toBe(0)
    expect(aktivAusDeepLink(zwei, null)).toBe(0)
    expect(geraetEinbettenZusatz(zwei[1], zwei.map((g) => g.inv))).toEqual({ geraet: '8' })
    expect(geraetEinbettenZusatz(zwei[0], [zwei[0].inv])).toBeUndefined()
    // Ein Pseudo-Gerät ohne echte ID (id 0) zählt nicht und bekommt keinen Parameter.
    expect(geraetEinbettenZusatz(zwei[0], [zwei[0].inv, geraet(0, 'wallbox').inv])).toBeUndefined()
    expect(geraetEinbettenZusatz(geraet(0, 'wallbox'), zwei.map((g) => g.inv))).toBeUndefined()
  })

  it('zwei Wallboxen + &geraet=<zweite> ⇒ das zweite Gerät ist gewählt, das Deep-Link-Overlay zeigt dessen Schaubild', async () => {
    vi.mocked(liveDashboardApi.getData).mockResolvedValue({ komponenten: [], gauges: [] } as never)
    adapterGeraete.liste = [geraet(7, 'wallbox'), geraet(8, 'wallbox')]
    window.location.hash = '#/komponenten/wallbox?fokus=ueberblick:schaubild&geraet=8'
    renderMitProvidern(<KomponentenTypV4 typ="wallbox" anlageId={1} />)
    expect(await screen.findByRole('heading', { name: 'Überblick · Schaubild', level: 2 })).toBeInTheDocument()
    const zeile = await within(overlay()!).findByText(/Ohne Sensor/)
    expect(zeile).toHaveTextContent('Leistung Gerät 8')
    expect(zeile).not.toHaveTextContent('Gerät 7')
    expect(aktiverSelektor()).toEqual(['Gerät 8'])
    // Deep-Link-Ansicht ohne Knopf bleibt ohne Knopf.
    expect(screen.queryByRole('button', { name: /Link \/ Einbetten/ })).not.toBeInTheDocument()
  })

  it('unbekannte ID ⇒ still das erste Gerät, kein Hinweis-Overlay', async () => {
    vi.mocked(liveDashboardApi.getData).mockResolvedValue({ komponenten: [], gauges: [] } as never)
    adapterGeraete.liste = [geraet(7, 'wallbox'), geraet(8, 'wallbox')]
    window.location.hash = '#/komponenten/wallbox?fokus=ueberblick:schaubild&geraet=99'
    renderMitProvidern(<KomponentenTypV4 typ="wallbox" anlageId={1} />)
    expect(await screen.findByRole('heading', { name: 'Überblick · Schaubild', level: 2 })).toBeInTheDocument()
    const zeile = await within(overlay()!).findByText(/Ohne Sensor/)
    expect(zeile).toHaveTextContent('Leistung Gerät 7')
    expect(aktiverSelektor()).toEqual(['Gerät 7'])
    expect(screen.queryByText(/gibt es in dieser Sicht nicht/)).not.toBeInTheDocument()
  })

  /** Öffnet «Link / Einbetten» im offenen Overlay und liefert die angezeigte Adresse. */
  const adresse = () => {
    fireEvent.click(within(overlay()!).getByRole('button', { name: /Link \/ Einbetten/ }))
    return screen.getByText(/#\/komponenten\/wallbox\?fokus=/).textContent
  }

  it('zwei Geräte: Schaubild-⤢ schreibt &geraet=<gewähltes>', async () => {
    adapterGeraete.liste = [geraet(7, 'wallbox'), geraet(8, 'wallbox')]
    window.location.hash = '#/komponenten/wallbox'
    renderMitProvidern(<KomponentenTypV4 typ="wallbox" anlageId={1} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Gerät 8' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Schaubild: Fokus / Vollbild' }))
    expect(adresse()).toMatch(/#\/komponenten\/wallbox\?fokus=ueberblick%3Aschaubild&geraet=8$/)
  })

  it('zwei Geräte: Block-⤢ «Überblick» schreibt &geraet=<gewähltes>', async () => {
    adapterGeraete.liste = [geraet(7, 'wallbox'), geraet(8, 'wallbox')]
    window.location.hash = '#/komponenten/wallbox'
    renderMitProvidern(<KomponentenTypV4 typ="wallbox" anlageId={1} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Gerät 8' }))
    await waitFor(() => expect(document.querySelector('[data-ueberblick-schaubild]')).not.toBeNull())
    fireEvent.click(screen.getAllByRole('button', { name: 'Fokus / Vollbild' })[0])
    expect(adresse()).toMatch(/#\/komponenten\/wallbox\?fokus=ueberblick&geraet=8$/)
  })

  it('ein Gerät: die Adresse bleibt ohne geraet (bestehende Karten werden nicht länger)', async () => {
    adapterGeraete.liste = [geraet(7, 'wallbox')]
    window.location.hash = '#/komponenten/wallbox'
    renderMitProvidern(<KomponentenTypV4 typ="wallbox" anlageId={1} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Schaubild: Fokus / Vollbild' }))
    expect(adresse()).toMatch(/#\/komponenten\/wallbox\?fokus=ueberblick%3Aschaubild$/)
  })
})

/**
 * Päckchen R N2 (Lab rc24/rc26: `GET …/hub-leer-grund/4/39` ⇒ 404, Investition 39 gehört zu Anlage 1): beim
 * Anlagenwechsel rendert der Hub einmal mit der neuen `anlageId` und dem Gerät der alten Liste — der Leer-Grund darf
 * dann nicht gefragt werden (die Frage wäre «Gerät der Anlage 1 in Anlage 4»).
 */
describe('Päckchen R N2: Leer-Grund nur für ein Gerät der gewählten Anlage', () => {
  it('Anlagenwechsel: kein getHubLeerGrund(neue Anlage, altes Gerät)', async () => {
    const spy = vi.spyOn(investitionenApi, 'getHubLeerGrund').mockResolvedValue({ leer: false } as never)
    adapterGeraete.liste = [{ ...geraet(39, 'speicher'), monatswerte: 0 }]
    window.location.hash = '#/komponenten/speicher'
    function Umschalter() {
      const [anlageId, setAnlageId] = useState(1)
      return <><button onClick={() => setAnlageId(4)}>Anlage 4</button><KomponentenTypV4 typ="speicher" anlageId={anlageId} /></>
    }
    renderMitProvidern(<Umschalter />)
    await waitFor(() => expect(spy).toHaveBeenCalledWith(1, 39))
    const neu = geraet(40, 'speicher')
    adapterGeraete.liste = [{ ...neu, inv: { ...neu.inv, anlage_id: 4 }, monatswerte: 0 }]
    fireEvent.click(screen.getByRole('button', { name: 'Anlage 4' }))
    await waitFor(() => expect(spy).toHaveBeenCalledWith(4, 40))
    expect(spy).not.toHaveBeenCalledWith(4, 39)
    spy.mockRestore()
  })
})
