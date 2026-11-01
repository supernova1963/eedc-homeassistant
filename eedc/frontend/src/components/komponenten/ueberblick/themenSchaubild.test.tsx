/**
 * Themen-Kacheln im gezeichneten Schaubild (4.2.0 TH-E2, Bauplan §2.4; Entscheid Master 1.11.2026 zu H1/H3):
 * - die Zeichnung kürzt Wert- und zweite Zeile einer Themen-Kachel auf das Zeichenbudget der Dims (der Wert bleibt),
 *   der Tooltip (`data-title`) trägt alle Einträge ungekürzt;
 * - «Fahrzeug mit vier Themen» am Handy (390 px): Standort und Reichweite bleiben, ein Thema im Bild, «Weitere (3)»
 *   mit je Thema der Zeile «‹Name›  ‹Wert-Zeile› · ‹zweite Zeile›» (ungekürzt);
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

const e = (id: string, label: string, wert: string, einheit = ''): LiveThemaEintrag =>
  ({ id, label, wert, einheit, zeitpunkt: null, device_class: null, quelle: 'ha' })
const IONIQ = { id: 7, anlage_id: 1, typ: 'e-auto', bezeichnung: 'Ioniq', aktiv: true, parameter: {} } as Investition
const THEMEN: LiveThema[] = [
  { investition_id: 7, id: 't1', name: 'Fahrzeugzustand', eintraege: [e('e1', 'Türen', 'locked'), e('e2', 'Reifen vorne links', '259.5', 'kPa')] },
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
  it('Desktop, eine Themen-Kachel (Dims ≤ 3): Wert-Zeile «Tür… · locked», zweite Zeile «259,5 kPa», Tooltip ungekürzt', () => {
    const { container } = zeichne(baueThemenKacheln(THEMEN.slice(0, 1), IONIQ, 'HIMMEL', 'c'), FAHRZEUG_PANORAMA_DEF, 900)
    expect(texte(container, 'thema-7-t1')).toEqual(['Tür… · locked', '259,5 kPa', 'Fahrzeugzust…'])   // Name nach `labelMaxChars` 14 wie jede Kachel
    const tip = container.querySelector('g[data-platz="thema-7-t1"] [data-title]')!.getAttribute('data-title')
    expect(tip).toBe('Fahrzeugzustand\nTüren: locked\nReifen vorne links: 259,5 kPa')
  })

  it('Handy 390 px, Fahrzeug mit Standort, Reichweite und vier Themen: ein Thema im Bild, «Weitere (3)» mit den Zeilen', () => {
    const kacheln = [
      wertKachel('wert-reichweite-7', 'C', 'Reichweite', '312 km'), wertKachel('wert-standort-7', 'H', 'Standort', 'Zu Hause'),
      ...baueThemenKacheln(THEMEN, IONIQ, 'HIMMEL', 'c'),
    ]
    const { container } = zeichne(kacheln, FAHRZEUG_PANORAMA_DEF, 390)
    const plaetze = [...container.querySelectorAll('g[data-platz]')].map((g) => g.getAttribute('data-platz'))
    expect(plaetze).toEqual(['wert-standort-7', 'wert-reichweite-7', 'thema-7-t1', 'grp-weitere'])
    // Dims(4): Wert-Budget 12 ⇒ «locked» allein, zweite Zeile 13 ⇒ «259,5 kPa».
    expect(texte(container, 'thema-7-t1')).toEqual(['locked', '259,5 kPa', 'Fahrzeugzu…'])
    const weitere = container.querySelector('g[data-gruppe="grp-weitere"]')!
    fireEvent.click(weitere)
    const zeilen = [...container.querySelectorAll('[data-gruppen-liste] li')].map((li) => [...li.querySelectorAll('span')].map((s) => s.textContent))
    expect(zeilen).toEqual([
      ['Service', 'Tage bis Service · 41'],
      ['Klima', 'Innen · 21,5 °C · Soll · 22 °C'],
      ['Plan', 'Start · ready'],
    ])
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
