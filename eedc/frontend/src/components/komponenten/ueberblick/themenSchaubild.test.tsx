/**
 * Themen-Kacheln im gezeichneten Schaubild (4.2.0 TH-E2, Bauplan §2.4; Kachelform Nachlauf 4.2.1 N4, Entscheid Gernot
 * 2.11.2026):
 * - ein Eintrag ⇒ Wert-Kachel: Beschriftung = Bezeichnung, Wert allein, keine zweite Zeile, kein Knopf;
 * - mehrere Einträge ⇒ dreizeilige Gruppenkachel wie die Geräte-Kachel (Entscheid Gernot 2.11.2026): Wert des ersten
 *   Eintrags (ganz), seine Bezeichnung (am Ende gekürzt), «‹Thema› (n)»; Stapel-Optik, Tipp öffnet die Liste
 *   Bezeichnung · Wert · Stand; im Layout **ein** Platz (Schlüssel `thema-<inv>-<t>`);
 * - «Fahrzeug mit vier Themen» am Handy (390 px): Standort und Reichweite bleiben, ein Thema im Bild, «Weitere (3)»
 *   mit je Thema einer Zeile — die Themen wandern zuerst; eine Themen-Gruppe dort als «‹Thema› (n) · ‹Bezeichnung› · ‹Wert›»
 *   des ersten Eintrags, in der Liste mit dessen Stand, Einzel-Themen unverändert (Nachlauf 4.2.1 N6);
 * - Wärme: Themen am Himmel rechts neben Außen, ohne Linie.
 *
 * Schwesterdateien: themenKacheln.test.ts, emobLayout.test.ts, UeberblickSchaubild.test.tsx.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, fireEvent } from '@testing-library/react'
import UeberblickSchaubild from './UeberblickSchaubild'
import { FAHRZEUG_PANORAMA_DEF } from './emobPanoramaAnker'
import { WAERME_PANORAMA_DEF } from './waermePanoramaAnker'
import { baueThemenKacheln } from './themenKacheln'
import type { UeberblickKachel } from './kachelAnker'
import { ThemeProvider } from '../../../context/ThemeContext'
import { stubMatchMedia } from '../../../test/render'
import type { LiveThema, LiveThemaEintrag } from '../../../api/liveDashboard'
import type { Investition } from '../../../types'
import type { PanoramaDef } from './panorama'

const ORIGINAL_RO = globalThis.ResizeObserver
function mitBreite(px: number) {
  vi.stubGlobal('ResizeObserver', class {
    private cb: ResizeObserverCallback
    constructor(cb: ResizeObserverCallback) { this.cb = cb }
    observe(target: Element) {
      this.cb([{ target, contentRect: { width: px, height: 500 } } as unknown as ResizeObserverEntry], this as unknown as ResizeObserver)
    }
    unobserve() {}
    disconnect() {}
  })
}
beforeEach(() => { stubMatchMedia(); localStorage.clear() })
afterEach(() => { vi.unstubAllGlobals(); globalThis.ResizeObserver = ORIGINAL_RO })

const e = (id: string, label: string, wert: string, einheit = '', zeitpunkt: string | null = null): LiveThemaEintrag =>
  ({ id, label, wert, einheit, zeitpunkt, device_class: null, quelle: 'ha' })
// Zeitpunkte aus der lokalen Uhr am heutigen Tag ⇒ «Stand hh:mm» in jeder Zeitzone (CI: UTC und Auckland).
const heute = (h: number, m: number) => { const d = new Date(); d.setHours(h, m, 0, 0); return d.toISOString() }
const IONIQ = { id: 7, anlage_id: 1, typ: 'e-auto', bezeichnung: 'Ioniq', aktiv: true, parameter: {} } as Investition
const THEMEN: LiveThema[] = [
  { investition_id: 7, id: 't1', name: 'Fahrzeugzustand', eintraege: [
    e('e1', 'Türen', 'locked', '', heute(6, 20)), e('e2', 'Reifen vorne links', '259.5', 'kPa', heute(11, 27)), e('e7', 'Fenster', 'closed'),
  ] },
  { investition_id: 7, id: 't2', name: 'Service', eintraege: [e('e3', 'Tage bis Service', '41')] },
  { investition_id: 7, id: 't3', name: 'Klima', eintraege: [e('e4', 'Innen', '21.5', '°C'), e('e5', 'Soll', '22', '°C')] },
  { investition_id: 7, id: 't4', name: 'Plan', eintraege: [e('e6', 'Start', 'ready')] },
]
const wertKachel = (id: string, anker: string, label: string, wertText: string): UeberblickKachel =>
  ({ id, art: 'wert', anker, label, icon: 'car', color: 'c', isActive: true, wertText, zweiteZeile: null, tip: label, investitionId: 7 })

function zeichne(kacheln: UeberblickKachel[], panorama: PanoramaDef, breite: number) {
  mitBreite(breite)
  return render(<ThemeProvider><UeberblickSchaubild kacheln={kacheln} ohneSensor={[]} panorama={panorama} /></ThemeProvider>)
}
const texte = (c: HTMLElement, key: string) => [...c.querySelectorAll(`g[data-platz="${key}"] text`)].map((t) => t.textContent)

describe('Themen-Kacheln im Schaubild (TH-E2)', () => {
  it('ein Eintrag ⇒ Wert-Kachel: Beschriftung = Bezeichnung, Wert, keine zweite Zeile, kein Knopf; Tooltip-Kopf = Thema', () => {
    const { container } = zeichne(baueThemenKacheln([THEMEN[1]], IONIQ, 'HIMMEL', 'c'), FAHRZEUG_PANORAMA_DEF, 900)
    expect(texte(container, 'thema-7-t2')).toEqual(['41', 'Tage bis Ser…'])   // Wert, Beschriftung nach `labelMaxChars` 14
    expect(container.querySelector('g[data-platz="thema-7-t2"] [data-gruppe]')).toBeNull()
    const tip = container.querySelector('g[data-platz="thema-7-t2"] [data-title]')!.getAttribute('data-title')
    expect(tip).toBe('Service\nTage bis Service: 41')
  })

  it('drei Einträge ⇒ dreizeilige Gruppenkachel «locked / Türen / Fahrzeugzustand (3)», ein Platz; Tipp öffnet die Liste mit Stand', () => {
    const { container, getByRole } = zeichne(baueThemenKacheln(THEMEN.slice(0, 1), IONIQ, 'HIMMEL', 'c'), FAHRZEUG_PANORAMA_DEF, 900)
    expect([...container.querySelectorAll('g[data-platz]')].map((g) => g.getAttribute('data-platz'))).toEqual(['thema-7-t1'])
    // Dims(1): Wert ganz, Bezeichnung (Budget 15) ganz, Titel-Budget 16 ⇒ «Fahrzeugzus… (3)» (Anzahl bleibt ganz).
    expect(texte(container, 'thema-7-t1')).toEqual(['locked', 'Türen', 'Fahrzeugzus… (3)'])
    const knopf = getByRole('button', { name: 'Fahrzeugzustand (3): Liste öffnen' })
    expect(knopf.getAttribute('data-title')).toBe('Fahrzeugzustand (3)\n• Türen: locked\n• Reifen vorne links: 259,5 kPa\n• Fenster: closed\nStand 11:27')
    expect(container.querySelector('[data-gruppen-liste]')).toBeNull()
    fireEvent.click(knopf)
    const liste = container.querySelector('[data-gruppen-liste="thema-7-t1"]')!
    expect(liste.textContent).toContain('Fahrzeugzustand (3)')
    const zeilen = [...liste.querySelectorAll('li')].map((li) => [...li.querySelectorAll('span')].map((s) => s.textContent))
    expect(zeilen).toEqual([
      ['Türen', 'lockedStand 06:20', 'locked', 'Stand 06:20'],
      ['Reifen vorne links', '259,5 kPaStand 11:27', '259,5 kPa', 'Stand 11:27'],
      ['Fenster', 'closed', 'closed'],
    ])
    fireEvent.click(getByRole('button', { name: 'schließen' }))
    expect(container.querySelector('[data-gruppen-liste]')).toBeNull()
  })

  it('Handy 390 px, Fahrzeug mit Standort, Reichweite und vier Themen: ein Thema im Bild, «Weitere (3)» mit den Zeilen', () => {
    const kacheln = [
      wertKachel('wert-reichweite-7', 'C', 'Reichweite', '312 km'), wertKachel('wert-standort-7', 'H', 'Standort', 'Zu Hause'),
      ...baueThemenKacheln(THEMEN, IONIQ, 'HIMMEL', 'c'),
    ]
    const { container } = zeichne(kacheln, FAHRZEUG_PANORAMA_DEF, 390)
    const plaetze = [...container.querySelectorAll('g[data-platz]')].map((g) => g.getAttribute('data-platz'))
    expect(plaetze).toEqual(['wert-standort-7', 'wert-reichweite-7', 'thema-7-t1', 'grp-weitere'])
    // Dims(4): die Gruppe zählt als ein Platz; dieselben drei Zeilen, Titel-Budget 15 — kein nackter Wert.
    expect(texte(container, 'thema-7-t1')).toEqual(['locked', 'Türen', 'Fahrzeugzu… (3)'])
    const weitere = container.querySelector('g[data-gruppe="grp-weitere"]')!
    fireEvent.click(weitere)
    const zeilen = [...container.querySelectorAll('[data-gruppen-liste] li')].map((li) => [...li.querySelectorAll('span')].map((s) => s.textContent))
    expect(zeilen).toEqual([
      ['Tage bis Service', '41'],
      ['Klima (2)', 'Innen · 21,5 °C', 'Innen · 21,5 °C'],   // N6: Themen-Gruppe mit «(n)», ohne Zeitpunkt kein Stand
      ['Start', 'ready'],
    ])
  })

  it('N6: volle Reihe, Themen-Gruppe in «Weitere» ⇒ Tooltip und Liste «‹Thema› (n) · ‹Bezeichnung› · ‹Wert›», Liste mit Stand', () => {
    // Service (Einzel-Thema) vorn ⇒ es bleibt im Bild, die Gruppe «Fahrzeugzustand (3)» wandert mit Klima und Plan nach «Weitere».
    const themen = [THEMEN[1], THEMEN[0], THEMEN[2], THEMEN[3]]
    const kacheln = [
      wertKachel('wert-reichweite-7', 'C', 'Reichweite', '312 km'), wertKachel('wert-standort-7', 'H', 'Standort', 'Zu Hause'),
      ...baueThemenKacheln(themen, IONIQ, 'HIMMEL', 'c'),
    ]
    const { container } = zeichne(kacheln, FAHRZEUG_PANORAMA_DEF, 390)
    const plaetze = [...container.querySelectorAll('g[data-platz]')].map((g) => g.getAttribute('data-platz'))
    expect(plaetze).toEqual(['wert-standort-7', 'wert-reichweite-7', 'thema-7-t2', 'grp-weitere'])
    const weitere = container.querySelector('g[data-gruppe="grp-weitere"]')!
    expect(weitere.getAttribute('data-title')).toBe(
      'Weitere (3)\n• Fahrzeugzustand (3) · Türen · locked\n• Klima (2) · Innen · 21,5 °C\n• Start: ready',
    )
    fireEvent.click(weitere)
    const zeilen = [...container.querySelectorAll('[data-gruppen-liste] li')].map((li) => [...li.querySelectorAll('span')].map((s) => s.textContent))
    expect(zeilen).toEqual([
      ['Fahrzeugzustand (3)', 'Türen · lockedStand 06:20', 'Türen · locked', 'Stand 06:20'],   // Stand des ersten Eintrags
      ['Klima (2)', 'Innen · 21,5 °C', 'Innen · 21,5 °C'],
      ['Start', 'ready'],                                                                      // Einzel-Thema unverändert
    ])
    expect([...container.querySelectorAll('[data-gruppen-liste] [data-thema-gruppe]')].map((li) => li.getAttribute('data-thema-gruppe')))
      .toEqual(['thema-7-t1', 'thema-7-t3'])
  })

  it('Wärme: Themen am Himmel rechts neben Außen, ohne Linie', () => {
    const wp = { ...IONIQ, id: 3, typ: 'waermepumpe', bezeichnung: 'WP' } as Investition
    const themen = THEMEN.slice(0, 2).map((t) => ({ ...t, investition_id: 3 }))
    const kacheln = [wertKachel('wert-aussen', 'HIMMEL', 'Außen', '4,2 °C'), ...baueThemenKacheln(themen, wp, 'HIMMEL', 'c')]
    const { container } = zeichne(kacheln, WAERME_PANORAMA_DEF, 900)
    const x = (key: string) => Number(/translate\(([\d.]+) /.exec(container.querySelector(`g[data-platz="${key}"]`)!.getAttribute('transform')!)?.[1])
    expect(x('thema-3-t1')).toBeGreaterThan(x('wert-aussen'))
    expect(x('thema-3-t2')).toBeGreaterThan(x('thema-3-t1'))
    expect(container.querySelectorAll('[data-linie]')).toHaveLength(0)
  })
})
