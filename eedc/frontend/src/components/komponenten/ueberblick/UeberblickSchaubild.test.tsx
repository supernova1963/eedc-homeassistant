/**
 * Schaubild des Überblicks (P-433-2 E1): nur zugeordnete Werte haben Kacheln,
 * fehlende stehen in der Zeile darunter, jede Kachel trägt `data-title`, beide
 * Panoramen liegen gestapelt mit dem `dark:`-Opacity-Paar, Gruppen öffnen ihre
 * Liste unter dem Bild.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, fireEvent } from '@testing-library/react'
import { existsSync, statSync } from 'node:fs'
import { join } from 'node:path'
import UeberblickSchaubild from './UeberblickSchaubild'
import { baueUeberblickKacheln, geraeteAnker, modusText } from './kachelAnker'
import { WAERME_PANORAMA } from './waermePanoramaAnker'
import { ThemeProvider } from '../../../context/ThemeContext'
import { stubMatchMedia } from '../../../test/render'
import type { LiveDashboardResponse, LiveInnengeraet, LiveKomponente, LiveWetterResponse } from '../../../api/liveDashboard'
import type { Investition } from '../../../types'

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

const wpInv = (id: number, bezeichnung: string, parameter: Record<string, unknown> = {}): Investition =>
  ({ id, anlage_id: 1, typ: 'waermepumpe', bezeichnung, aktiv: true, parameter } as Investition)
const knoten = (id: number, kw: number, extra: Partial<LiveKomponente> = {}): LiveKomponente =>
  ({ key: `waermepumpe_${id}`, label: `WP ${id}`, icon: 'heater', erzeugung_kw: null, verbrauch_kw: kw, typ: 'waermepumpe', ...extra })
const liveAntwort = (extra: Partial<LiveDashboardResponse> = {}): LiveDashboardResponse => ({
  anlage_id: 1, anlage_name: 'Test', zeitpunkt: '2026-10-24T12:00:00', verfuegbar: true,
  komponenten: [], summe_erzeugung_kw: 0, summe_verbrauch_kw: 0, summe_pv_kw: 0, gauges: [],
  heute_pv_kwh: null, heute_einspeisung_kwh: null, heute_netzbezug_kwh: null, heute_eigenverbrauch_kwh: null,
  gestern_pv_kwh: null, gestern_einspeisung_kwh: null, gestern_netzbezug_kwh: null, gestern_eigenverbrauch_kwh: null,
  heute_kwh_pro_komponente: null, warmwasser_temperatur_c: null, innengeraete: null,
  ...extra,
})
const wetterMit = (t: number | null): LiveWetterResponse =>
  ({ aktuell: t == null ? null : { zeit: '12:00', temperatur_c: t } } as unknown as LiveWetterResponse)
const ig = (inv: number, id: number, name: string, ist: number | null, w: number | null = null): LiveInnengeraet =>
  ({ investition_id: inv, innengeraet_id: id, bezeichnung: name, leistung_w: w, soll_temperatur_c: null, ist_temperatur_c: ist })

/** Matheks Fall: Sole, passiv kühlend; Modus, WW-Temperatur, Strom heute, Außentemperatur. */
const MATHEK = wpInv(7, 'Nibe S1255', { wp_art: 'sole_wasser', kuehlung_art: 'passiv' })
const matheksLive = () => liveAntwort({
  komponenten: [knoten(7, 1.2, { betriebsmodus: 'heizen', betriebsmodus_label: 'Heizen' })],
  warmwasser_temperatur_c: 48.5,
  heute_kwh_pro_komponente: { waermepumpe_7: 6.4 },
})

function zeichne(geraete: Investition[], live: LiveDashboardResponse | null, wetter: LiveWetterResponse | null, breite = 900) {
  mitBreite(breite)
  const { kacheln, ohneSensor } = baueUeberblickKacheln({ geraete, live, wetter, referenz: 'referenz' })
  return render(<ThemeProvider><UeberblickSchaubild kacheln={kacheln} ohneSensor={ohneSensor} /></ThemeProvider>)
}
const kacheln = (c: HTMLElement) => [...c.querySelectorAll('svg g[data-title]')]
const ersteZeilen = (c: HTMLElement) => kacheln(c).map((g) => g.getAttribute('data-title')!.split('\n')[0])

describe('Anker nach Bauart (Gruppe 2: Anzeige-Ort)', () => {
  it('Luft/Wasser → A, Sole/Grundwasser → C, Brauchwasser → F, Luft/Luft → O, ohne Bauart → A', () => {
    expect(geraeteAnker(wpInv(1, 'a', { wp_art: 'luft_wasser' }))).toBe('A')
    expect(geraeteAnker(wpInv(1, 'a', { wp_art: 'sole_wasser' }))).toBe('C')
    expect(geraeteAnker(wpInv(1, 'a', { wp_art: 'grundwasser' }))).toBe('C')
    expect(geraeteAnker(wpInv(1, 'a', { wp_art: 'brauchwasser' }))).toBe('F')
    expect(geraeteAnker(wpInv(1, 'a', { wp_art: 'luft_luft' }))).toBe('O')
    expect(geraeteAnker(wpInv(1, 'a'))).toBe('A')
  })

  it('«Kühlen (passiv)» nur bei kuehlung_art passiv und Modus kühlen', () => {
    const k = { betriebsmodus: 'kuehlen', betriebsmodus_label: 'Kühlen' }
    expect(modusText(k, MATHEK)).toBe('Kühlen (passiv)')
    expect(modusText(k, wpInv(1, 'a', { kuehlung_art: 'aktiv' }))).toBe('Kühlen')
    expect(modusText({ betriebsmodus: 'heizen', betriebsmodus_label: 'Heizen' }, MATHEK)).toBe('Heizen')
    expect(modusText({ betriebsmodus: null, betriebsmodus_label: null }, MATHEK)).toBeNull()
  })
})

describe('Nur zugeordnete Werte haben Kacheln (B2)', () => {
  it('P-433-1: die WP-Kachel trägt denselben Modus-Chip wie der Energiefluss; Leerlauf ⇒ «Leerlauf», Tooltip ganz', () => {
    const ruht = liveAntwort({ komponenten: [knoten(7, 0.008, {
      betriebsmodus: 'heizen', betriebsmodus_label: 'Heizen', betriebsmodus_aktion: 'leerlauf', betriebsmodus_aktion_label: 'Leerlauf',
    })] })
    const { kacheln: k } = baueUeberblickKacheln({ geraete: [MATHEK], live: ruht, wetter: null, referenz: 'referenz' })
    const wp = k.find((x) => x.art === 'geraet')!
    expect(wp.zweiteZeile).toMatchObject({ text: 'Leerlauf', fill: 'referenz', chip: { gedaempft: true } })
    expect(wp.tip).toContain('Betrieb: Heizen · Leerlauf')
    const { container } = zeichne([MATHEK], ruht, null)
    expect(container.querySelector('rect[data-modus-chip="gedaempft"]')).not.toBeNull()
    expect(modusText({ betriebsmodus: 'kuehlen', betriebsmodus_label: 'Kühlen', betriebsmodus_aktion_label: 'Leerlauf' }, MATHEK))
      .toBe('Kühlen (passiv) · Leerlauf')
  })

  it('Mathek: vier Kacheln (WP, Warmwasser, Strom heute, Außen), alle in der oberen Reihe, keine Zeile „ohne Sensor"', () => {
    const { container } = zeichne([MATHEK], matheksLive(), wetterMit(7.4))
    expect(ersteZeilen(container)).toHaveLength(4)
    expect(ersteZeilen(container)).toEqual(expect.arrayContaining(['Nibe S1255', 'Warmwasser-Temperatur', 'Nibe S1255', 'Außentemperatur']))
    expect(container.querySelector('[data-ohne-sensor]')).toBeNull()
    const wp = kacheln(container).find((g) => g.getAttribute('data-title')!.includes('Betrieb: Heizen'))!
    expect(wp.querySelector('title')!.textContent).toBe(wp.getAttribute('data-title'))
  })

  it('fehlende Werte ⇒ keine Kachel, sondern die Zeile mit Link zu den Datenquellen', () => {
    const live = liveAntwort({ komponenten: [knoten(7, 1.2)] })
    const { container } = zeichne([MATHEK], live, wetterMit(null))
    expect(ersteZeilen(container)).toEqual(['Nibe S1255'])
    const zeile = container.querySelector('[data-ohne-sensor]')!
    expect(zeile.textContent).toContain('Ohne Sensor, deshalb ohne Kachel: Warmwasser-Temperatur · Strom heute')
    expect(zeile.querySelector('a')!.getAttribute('href')).toBe('#/einstellungen/datenquellen')
  })

  it('ohne Live-Antwort (noch nicht geladen): weder Kacheln noch Zeile — nur das Bild', () => {
    const { container } = zeichne([MATHEK], null, null)
    expect(kacheln(container)).toHaveLength(0)
    expect(container.querySelector('[data-ohne-sensor]')).toBeNull()
    expect(container.querySelectorAll('image[data-panorama]')).toHaveLength(2)
  })

  it('Wert-Kacheln tragen immer die Rollenfarbe (B12): kein inaktives Grau', () => {
    const { container } = zeichne([MATHEK], matheksLive(), wetterMit(7.4))
    const ww = kacheln(container).find((g) => g.getAttribute('data-title')!.startsWith('Warmwasser'))!
    expect(ww.querySelector('rect')!.getAttribute('stroke-opacity')).toBe('0.7')
  })
})

describe('Bild: beide Panoramen gestapelt (Regel B wie EnergieFlussBackground)', () => {
  it('Tag `opacity-100 dark:opacity-0`, Nacht `opacity-0 dark:opacity-100`, gleiche Maße', () => {
    const { container } = zeichne([MATHEK], matheksLive(), wetterMit(7.4))
    const tag = container.querySelector('image[data-panorama="tag"]')!
    const nacht = container.querySelector('image[data-panorama="nacht"]')!
    expect(tag.getAttribute('class')).toBe('opacity-100 dark:opacity-0')
    expect(nacht.getAttribute('class')).toBe('opacity-0 dark:opacity-100')
    expect(tag.getAttribute('width')).toBe(nacht.getAttribute('width'))
    expect(container.querySelector('svg')!.getAttribute('viewBox')).toBe('0 0 1312 816')
  })

  it('die Bilddateien liegen im public-Ordner, Nachtbild ≤ 200 KB', () => {
    for (const pfad of Object.values(WAERME_PANORAMA)) {
      const datei = join(process.cwd(), 'public', pfad.replace('./', ''))
      expect(existsSync(datei), datei).toBe(true)
    }
    expect(statSync(join(process.cwd(), 'public', WAERME_PANORAMA.nacht.replace('./', ''))).size).toBeLessThanOrEqual(200_000)
  })

  it('Linien mit Saum nur im hellen Bild (`dark:opacity-0`)', () => {
    const { container } = zeichne([MATHEK], matheksLive(), wetterMit(7.4))
    const saeume = [...container.querySelectorAll('path[data-saum]')]
    expect(saeume.length).toBeGreaterThan(0)
    saeume.forEach((s) => expect(s.getAttribute('class')).toBe('dark:opacity-0'))
  })
})

describe('Gruppen (Ü6)', () => {
  it('2× Luft/Wasser: «Wärmepumpen (2)» ist ein Knopf und öffnet die Liste (Name · Wert · Modus)', () => {
    const geraete = [wpInv(1, 'WP Haus', { wp_art: 'luft_wasser' }), wpInv(2, 'WP Anbau', { wp_art: 'luft_wasser' })]
    const live = liveAntwort({ komponenten: [knoten(1, 1.5, { betriebsmodus_label: 'Heizen', betriebsmodus: 'heizen' }), knoten(2, 0)] })
    const { container } = zeichne(geraete, live, null)
    const gruppe = container.querySelector('g[data-gruppe="grp-geraete-A"]')!
    expect(gruppe.getAttribute('role')).toBe('button')
    expect(gruppe.getAttribute('data-title')!.split('\n')[0]).toBe('Wärmepumpen (2)')
    fireEvent.click(gruppe)
    const liste = container.querySelector('[data-gruppen-liste="grp-geraete-A"]')!
    expect(liste.textContent).toContain('WP Haus')
    expect(liste.textContent).toContain('Heizen')
    fireEvent.keyDown(gruppe, { key: 'Enter' })
    expect(container.querySelector('[data-gruppen-liste]')).toBeNull()
  })

  it('Gruppenwert wie im Energiefluss: «Wärmepumpen (n)» zeigt Σ Leistung, kein Ersatzwort', () => {
    const geraete = [wpInv(1, 'WP Haus', { wp_art: 'luft_wasser' }), wpInv(2, 'WP Anbau', { wp_art: 'luft_wasser' })]
    const live = liveAntwort({ komponenten: [knoten(1, 1.5), knoten(2, 0.75)] })
    const { container } = zeichne(geraete, live, null)
    const texte = [...container.querySelector('g[data-gruppe="grp-geraete-A"]')!.querySelectorAll('text')].map((t) => t.textContent)
    expect(texte[0]).toBe('2.250 W')
    expect(texte).not.toContain('Liste')
  })

  it('«Innengeräte (n)»: Σ Leistung nur, wenn jedes Mitglied eine hat — sonst leer', () => {
    const klima = wpInv(9, 'Split', { wp_art: 'luft_luft' })
    const mitAllen = liveAntwort({ innengeraete: [1, 2, 3, 4, 5].map((i) => ig(9, i, `Raum ${i}`, 21, 100 * i)) })
    const voll = zeichne([klima], mitAllen, null, 900).container
    expect(voll.querySelector('g[data-gruppe="grp-innengeraete-rest"] text')!.textContent).toBe('900 W')
    const teils = liveAntwort({ innengeraete: [1, 2, 3, 4, 5].map((i) => ig(9, i, `Raum ${i}`, 21, i === 5 ? null : 100)) })
    const leer = zeichne([klima], teils, null, 900).container
    const g = [...leer.querySelectorAll('g[data-gruppe="grp-innengeraete-rest"]')].at(-1)!
    expect(g.querySelector('text')!.textContent).toBe('')
  })

  it('«Weitere (n)» hat keinen Wert (gemischte Einheiten)', () => {
    const klima = wpInv(9, 'Split', { wp_art: 'luft_luft' })
    const live = liveAntwort({
      komponenten: [knoten(9, 0.9)],
      heute_kwh_pro_komponente: { waermepumpe_9: 3.1 },
      innengeraete: [ig(9, 1, 'Wohnen', 24.5, 400), ig(9, 2, 'Küche', 25, 200), ig(9, 3, 'Schlafen', 22, 300)],
    })
    const { container } = zeichne([klima], live, wetterMit(29), 360)
    const weitere = container.querySelector('g[data-gruppe="grp-weitere"]')!
    expect(weitere.getAttribute('data-title')!.split('\n')[0]).toBe('Weitere (2)')
    expect(weitere.querySelector('text')!.textContent).toBe('')
    expect(container.querySelector('g[data-gruppe="grp-innengeraete"] text')!.textContent).toBe('900 W')
  })

  it('«Innengeräte (n)» öffnet den Innengeräte-Abschnitt (LiveInnengeraete) unter dem Bild', () => {
    const klima = wpInv(9, 'Split', { wp_art: 'luft_luft' })
    const live = liveAntwort({
      komponenten: [knoten(9, 0.6)],
      innengeraete: [ig(9, 1, 'Wohnen', 21.5), ig(9, 2, 'Küche', 22), ig(9, 3, 'Schlafen', 19.5), ig(9, 4, 'Bad', 23), ig(9, 5, 'Büro', 20.5, 300)],
    })
    const { container } = zeichne([klima], live, null, 900)
    const rest = container.querySelector('g[data-gruppe="grp-innengeraete-rest"]')!
    expect(rest.getAttribute('data-title')!.split('\n')[0]).toBe('Innengeräte (2)')
    fireEvent.click(rest)
    const liste = container.querySelector('[data-gruppen-liste]')!
    expect(liste.textContent).toContain('Bad')
    expect(liste.textContent).toContain('Büro')
    expect(liste.textContent).not.toContain('Wohnen')
  })

  it('Einzelkacheln sind keine Knöpfe', () => {
    const { container } = zeichne([MATHEK], matheksLive(), wetterMit(7.4))
    expect(container.querySelectorAll('[role="button"]')).toHaveLength(0)
  })
})
