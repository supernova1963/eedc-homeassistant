/**
 * Hub-Block «Überblick» (P-433-2 E1): nur auf der Typ-Seite Wärmepumpe, als
 * oberster Block (auch bei gespeicherter Reihenfolge, `voranstellen`), Summary
 * statisch, Park-IDs `el:ueberblick-schaubild`/`el:ueberblick-karte` (beide
 * geparkt ⇒ Block weg), Fokus-ID `ueberblick` (Snapshot-Zuwachs).
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { screen } from '@testing-library/react'

vi.mock('../api/liveDashboard', () => ({
  liveDashboardApi: {
    getData: vi.fn(() => new Promise(() => {})),
    getWetter: vi.fn(() => new Promise(() => {})),
  },
}))
vi.mock('../api/energie_profil', () => ({
  energieProfilApi: { getTagDetail: vi.fn(() => new Promise(() => {})) },
}))

import { geraetBloecke, UEBERBLICK_TYPEN, VORANSTELLEN } from './KomponentenTypV4'
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
  it('nur für den Typ Wärmepumpe — und dort als erster Block', () => {
    expect(UEBERBLICK_TYPEN).toEqual(['waermepumpe'])
    const wp = geraetBloecke(geraet(7, 'waermepumpe'), 'waermepumpe', 1, park(), {}, () => {})
    expect(wp[0].id).toBe('ueberblick')
    expect(wp[0].title).toBe('Überblick')
    expect(wp[0].defaultOpen).toBe(true)
    expect(wp[0].summary).toBe('Schaubild · Gerät 7')
    for (const typ of ['speicher', 'wallbox', 'e-auto', 'pv-module', 'sonstiges', 'balkonkraftwerk']) {
      expect(geraetBloecke(geraet(7, typ), typ, 1, park(), {}, () => {}).map((b) => b.id)).not.toContain('ueberblick')
    }
  })

  it('Aggregat ohne eigene Investition (id ≤ 0) bekommt keinen Überblick', () => {
    expect(geraetBloecke(geraet(0, 'waermepumpe'), 'waermepumpe', 1, park(), {}, () => {}).map((b) => b.id)).not.toContain('ueberblick')
  })

  it('Park: einer geparkt ⇒ Block bleibt; beide geparkt ⇒ Block weg', () => {
    const ids = (g: string[]) => geraetBloecke(geraet(7, 'waermepumpe'), 'waermepumpe', 1, park(g), {}, () => {}).map((b) => b.id)
    expect(ids(['el:ueberblick-schaubild'])).toContain('ueberblick')
    expect(ids(['el:ueberblick-karte'])).toContain('ueberblick')
    expect(ids(['el:ueberblick-schaubild', 'el:ueberblick-karte'])).not.toContain('ueberblick')
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
