/**
 * «Betrieb heute» E-Mobilität (P-433-2b K3, Bauplan K3-8 / E5): die dritte Karte an Wallbox und E-Auto aus
 * `TagDetail.emob_betrieb` — Lab-Fall (drei Werte + «Ladevorgänge heute»), E-Auto mit Standort, Karte fehlt ohne
 * Zeile, gemessene 0 ⇒ «Heute kein Betrieb», Farbe nur Rolle (keine Rahmenfarbe, Klassenvergleich wie K1 S5),
 * Zahlen und Klartext aus dem Backend (der Client rechnet nichts).
 */
import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import UeberblickKarteEmob, { BETRIEB_EMOB_TOOLTIP, KEIN_BETRIEB, betriebZeilen } from './UeberblickKarteEmob'
import { funktionsFarbe } from '../../../lib/funktionsFarben'
import type { EmobBetriebZeile, TagDetail } from '../../../api/energie_profil'
import type { Investition } from '../../../types'

const inv = (id: number, typ: string, bez: string): Investition =>
  ({ id, anlage_id: 1, typ, bezeichnung: bez, aktiv: true, parameter: {} } as Investition)
const LABELS: Record<string, string> = {
  laedt: 'Lädt', verbunden: 'Verbunden', wartet: 'Wartet', fertig: 'Fertig', laedt_dc: 'Lädt DC',
  zu_hause: 'Zu Hause', unterwegs: 'Unterwegs',
}
const zeile = (investition_id: number, typ: string, feld: string, stunden: Record<string, number>,
  wechsel: number | null = null): EmobBetriebZeile => ({
  investition_id, typ, feld, stunden, wechsel,
  labels: Object.fromEntries(Object.keys(stunden).map((w) => [w, LABELS[w]])),
})
const tag = (zeilen: EmobBetriebZeile[] | undefined) =>
  ({ emob_ladung_pv_kwh: 2.5, emob_betrieb: zeilen } as unknown as TagDetail)
const zeichne = (i: Investition, t: TagDetail | null) =>
  render(<UeberblickKarteEmob inv={i} live={null} tag={t} mehrereGeraete={false} />).container
const karte = (c: HTMLElement) => c.querySelector('[data-karte="betrieb-heute"]') as HTMLElement | null

const WB = inv(4, 'wallbox', 'SMA eCharger 22')
const AUTO = inv(5, 'e-auto', 'Smart #1')
const LAB = zeile(4, 'wallbox', 'ladezustand', { laedt: 3.2, verbunden: 5.7, wartet: 0.5, fertig: 0 }, 1)

describe('BetriebKarteEmob (K3)', () => {
  it('Lab-Fall Wallbox: Lädt · Verbunden · Wartet in Backend-Reihenfolge, «Fertig» mit 0 h fehlt, «Ladevorgänge heute: 1»', () => {
    const c = zeichne(WB, tag([LAB, zeile(9, 'wallbox', 'ladezustand', { laedt: 9 })]))
    const k = karte(c)!
    expect(k).not.toBeNull()
    expect(k.textContent).toContain('Betrieb heute')
    expect(k.querySelector('[title]')?.getAttribute('title')).toBe(BETRIEB_EMOB_TOOLTIP)
    expect([...k.querySelectorAll('[data-zeile^="betrieb-"]')].map((z) => z.textContent)).toEqual(
      ['Lädt3 h 12 min', 'Verbunden5 h 42 min', 'Wartet30 min'])
    expect(k.querySelector('[data-zeile="ladevorgaenge"]')?.textContent).toBe('Ladevorgänge heute1')
    expect(k.querySelector('[data-betrieb-ohne]')).toBeNull()
    // Die dritte Karte nach Gerät und Heute.
    expect([...c.querySelectorAll('[data-karte]')].map((x) => x.getAttribute('data-karte'))).toEqual(
      ['geraet', 'heute', 'betrieb-heute'])
  })

  it('E-Auto: Laden und Standort als zwei Gruppen, ohne Ladevorgänge', () => {
    const k = karte(zeichne(AUTO, tag([
      zeile(5, 'e-auto', 'ladezustand_fahrzeug', { laedt: 2.1, laedt_dc: 0, verbunden: 0.4 }),
      zeile(5, 'e-auto', 'zu_hause', { zu_hause: 14, unterwegs: 3 }),
    ])))!
    expect([...k.querySelectorAll('[data-gruppe]')].map((g) => g.getAttribute('data-gruppe'))).toEqual(
      ['ladezustand_fahrzeug', 'zu_hause'])
    expect(k.querySelector('[data-gruppe="ladezustand_fahrzeug"]')?.textContent).toBe('LadenLädt2 h 06 minVerbunden24 min')
    expect(k.querySelector('[data-gruppe="zu_hause"]')?.textContent).toBe('StandortZu Hause14 h 00 minUnterwegs3 h 00 min')
    expect(k.querySelector('[data-zeile="ladevorgaenge"]')).toBeNull()
  })

  it('Karte fehlt ohne Zeile (keine Mitschrift, älteres Backend, anderes Gerät)', () => {
    expect(karte(zeichne(WB, null))).toBeNull()
    expect(karte(zeichne(WB, tag(undefined)))).toBeNull()
    expect(karte(zeichne(WB, tag([zeile(9, 'wallbox', 'ladezustand', { laedt: 1 })])))).toBeNull()
    expect(betriebZeilen(tag([LAB]), 4)).toEqual([LAB])
  })

  it('gemessene 0 in allen Werten ⇒ «Heute kein Betrieb», Ladevorgänge 0 bleibt stehen', () => {
    const k = karte(zeichne(WB, tag([zeile(4, 'wallbox', 'ladezustand',
      { laedt: 0, verbunden: 0, wartet: 0, fertig: 0 }, 0)])))!
    expect(k.querySelector('[data-betrieb-ohne]')?.textContent).toBe(KEIN_BETRIEB)
    expect(k.querySelectorAll('[data-zeile^="betrieb-"]').length).toBe(0)
    expect(k.querySelector('[data-zeile="ladevorgaenge"]')?.textContent).toBe('Ladevorgänge heute0')
  })

  it('Farbe nur Rolle: Punkt = funktionsFarbe(wert), keine Rahmenfarbe nach Zustand', () => {
    const k = karte(zeichne(WB, tag([LAB])))!
    for (const w of ['laedt', 'verbunden', 'wartet']) {
      const punkt = k.querySelector(`[data-betrieb-farbe="${w}"]`) as HTMLElement
      expect(punkt.style.backgroundColor).not.toBe('')
      const probe = document.createElement('span')
      probe.style.backgroundColor = funktionsFarbe(w)
      expect(punkt.style.backgroundColor).toBe(probe.style.backgroundColor)
    }
    expect(funktionsFarbe('verbunden')).toBe(funktionsFarbe('kein_fahrzeug'))   // Ruhezustand ⇒ Grau, keine neue Farbe
    const klassen = (t: TagDetail) => {
      const c = zeichne(WB, t)
      const out: string[] = []
      for (let el = karte(c); el && el !== c; el = el.parentElement) out.push(el.className)
      return out.join(' | ')
    }
    expect(klassen(tag([zeile(4, 'wallbox', 'ladezustand', { wartet: 2 })]))).toBe(klassen(tag([LAB])))
  })

  it('der Client rundet nicht nach: 0,1 h aus dem Backend steht wörtlich da', () => {
    const k = karte(zeichne(WB, tag([zeile(4, 'wallbox', 'ladezustand', { laedt: 0.1 })])))!
    expect(k.querySelector('[data-zeile="betrieb-laedt"]')?.textContent).toBe('Lädt6 min')
  })
})
