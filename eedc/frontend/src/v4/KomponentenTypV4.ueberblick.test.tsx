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
import { screen, waitFor } from '@testing-library/react'

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

import KomponentenTypV4, { geraetBloecke, UEBERBLICK_TYPEN, VORANSTELLEN } from './KomponentenTypV4'
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
