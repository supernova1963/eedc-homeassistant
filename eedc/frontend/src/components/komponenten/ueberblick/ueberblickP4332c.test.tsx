/**
 * P-433-2c (Mockup Version 25): Kachel «Wärme heute» je Gerät im Schaubild — aus dem Tag-Detail
 * (`wp_geraete[].waerme_kwh`), am Heizkreis-Objekt nach dem Stammdatum `vorlauftemperatur` (dieselbe Regel wie
 * «Vorlauf · Rücklauf»: K Fußbodenheizung · J Heizkörper · sonst G), nur mit Wert, nie in der «Ohne Sensor»-Zeile.
 * Neben der Vorlauf-Kachel am selben Objekt bleibt die bestehende Entkreuzung (Wert-Kacheln gruppieren nicht, Ü6).
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { render } from '@testing-library/react'
import UeberblickSchaubild from './UeberblickSchaubild'
import { hatKreuzung, layoutUeberblick } from './ueberblickLayout'
import {
  ANKER_VORLAUF, ANKER_VORLAUF_FUSSBODENHEIZUNG, ANKER_VORLAUF_HEIZKOERPER, baueUeberblickKacheln,
} from './kachelAnker'
import { ThemeProvider } from '../../../context/ThemeContext'
import { stubMatchMedia } from '../../../test/render'
import { CHART_COLORS } from '../../../lib'
import type { LiveDashboardResponse, LiveKomponente } from '../../../api/liveDashboard'
import type { TagDetail } from '../../../api/energie_profil'
import type { Investition } from '../../../types'

beforeEach(() => { stubMatchMedia(); localStorage.clear() })

const wpInv = (id: number, bezeichnung: string, parameter: Record<string, unknown> = {}): Investition =>
  ({ id, anlage_id: 1, typ: 'waermepumpe', bezeichnung, aktiv: true, parameter } as Investition)
const knoten = (id: number, extra: Partial<LiveKomponente> = {}): LiveKomponente =>
  ({ key: `waermepumpe_${id}`, label: `WP ${id}`, icon: 'heater', erzeugung_kw: null, verbrauch_kw: 0.77, typ: 'waermepumpe', ...extra })
const live = (komponenten: LiveKomponente[]): LiveDashboardResponse => ({
  anlage_id: 1, anlage_name: 'Test', zeitpunkt: '2026-10-25T12:00:00', verfuegbar: true,
  komponenten, summe_erzeugung_kw: 0, summe_verbrauch_kw: 0, summe_pv_kw: 0, gauges: [],
  heute_pv_kwh: null, heute_einspeisung_kwh: null, heute_netzbezug_kwh: null, heute_eigenverbrauch_kwh: null,
  gestern_pv_kwh: null, gestern_einspeisung_kwh: null, gestern_netzbezug_kwh: null, gestern_eigenverbrauch_kwh: null,
  heute_kwh_pro_komponente: { waermepumpe_7: 3.3 }, warmwasser_temperatur_c: 48.5, innengeraete: null,
})
const tag = (zeilen: { investition_id: number; waerme_kwh: number | null }[]) =>
  ({ wp_geraete: zeilen.map((z) => ({ name: `WP ${z.investition_id}`, ...z })) } as unknown as TagDetail)
const SOLE = { wp_art: 'sole_wasser', kuehlung_art: 'passiv' }
const baue = (geraete: Investition[], t: TagDetail | null, komponenten = [knoten(7)]) =>
  baueUeberblickKacheln({ geraete, live: live(komponenten), wetter: null, referenz: 'referenz', tag: t })

describe('Kachel «Wärme heute» (P-433-2c)', () => {
  it('nur mit Wert: «23,0 kWh», Icon flame, Rollenfarbe Wärme, Tooltip mit Quelle', () => {
    const w = baue([wpInv(7, 'Nibe S1255', SOLE)], tag([{ investition_id: 7, waerme_kwh: 23.0 }])).kacheln
      .find((k) => k.id === 'wert-waerme-7')!
    expect([w.label, w.wertText, w.icon, w.color, w.art, w.investitionId]).toEqual(
      ['Wärme heute', '23,0 kWh', 'flame', CHART_COLORS.wpWaerme, 'wert', 7])
    expect(w.tip.split('\n')).toEqual(['Nibe S1255', 'Wärme heute: 23,0 kWh', 'Quelle: Tag-Detail (Wärmemengenzähler)'])
  })

  it('eine gemessene 0 ist ein Wert; ohne Wert, ohne Zeile oder ohne Tag-Detail keine Kachel', () => {
    const inv = wpInv(7, 'Nibe', SOLE)
    expect(baue([inv], tag([{ investition_id: 7, waerme_kwh: 0 }])).kacheln.find((k) => k.id === 'wert-waerme-7')?.wertText).toBe('0,0 kWh')
    for (const t of [tag([{ investition_id: 7, waerme_kwh: null }]), tag([{ investition_id: 8, waerme_kwh: 5 }]), null]) {
      expect(baue([inv], t).kacheln.some((k) => k.id.startsWith('wert-waerme'))).toBe(false)
    }
  })

  it.each([
    ['35', ANKER_VORLAUF_FUSSBODENHEIZUNG], ['55', ANKER_VORLAUF_HEIZKOERPER], [undefined, ANKER_VORLAUF],
  ] as const)('Anker nach Stammdatum vorlauftemperatur %s ⇒ %s — derselbe wie «Vorlauf · Rücklauf»', (vt, anker) => {
    const inv = wpInv(7, 'Nibe', vt === undefined ? SOLE : { ...SOLE, vorlauftemperatur: vt })
    const { kacheln } = baue([inv], tag([{ investition_id: 7, waerme_kwh: 23 }]), [knoten(7, { vorlauf_c: 34.2, ruecklauf_c: 29.1 })])
    expect(kacheln.find((k) => k.id === 'wert-waerme-7')?.anker).toBe(anker)
    expect(kacheln.find((k) => k.id === 'wert-vorlauf-7')?.anker).toBe(anker)
  })

  it('am selben Objekt wie Vorlauf: beide in derselben Reihe, keine Kreuzung — Desktop wie Handy', () => {
    const inv = wpInv(7, 'Nibe', { ...SOLE, vorlauftemperatur: '35' })
    const { kacheln } = baue([inv], tag([{ investition_id: 7, waerme_kwh: 23 }]), [knoten(7, { vorlauf_c: 34.2, ruecklauf_c: 29.1 })])
    for (const ctr of [1150, 600, 390, 360]) {
      const l = layoutUeberblick(kacheln, ctr)
      for (const reihe of [l.oben, l.unten]) expect(hatKreuzung(reihe), `${ctr}`).toBe(false)
      const reiheVon = (id: string) => ([l.oben, l.unten].find((r) => r.some((p) => p.mitglieder.some((m) => m.id === id))))
      expect(reiheVon('wert-waerme-7'), `${ctr}`).toBe(reiheVon('wert-vorlauf-7'))
    }
  })

  it('nie in der «Ohne Sensor»-Zeile (G7) — die Zeile nennt nur Live-Sensoren', () => {
    const ohne = baue([wpInv(7, 'Nibe', SOLE)], tag([{ investition_id: 7, waerme_kwh: null }])).ohneSensor
    expect(ohne.join(' ')).not.toMatch(/Wärme/)
  })

  it('mehrere Geräte: «Wärme <Name>», je Gerät nur mit eigenem Wert, auch ohne Live-Knoten', () => {
    const geraete = [wpInv(7, 'Nibe', SOLE), wpInv(8, 'Zweit-WP', { wp_art: 'luft_wasser' })]
    const { kacheln } = baue(geraete, tag([{ investition_id: 7, waerme_kwh: 23 }, { investition_id: 8, waerme_kwh: 4.5 }]), [knoten(7)])
    expect(kacheln.filter((k) => k.id.startsWith('wert-waerme')).map((k) => [k.id, k.label, k.wertText])).toEqual([
      ['wert-waerme-7', 'Wärme Nibe', '23,0 kWh'], ['wert-waerme-8', 'Wärme Zweit-WP', '4,5 kWh']])
  })

  it('das Schaubild zeichnet die Kachel mit Tooltip', () => {
    const { kacheln, ohneSensor } = baue([wpInv(7, 'Nibe', SOLE)], tag([{ investition_id: 7, waerme_kwh: 23 }]))
    const { container } = render(<ThemeProvider><UeberblickSchaubild kacheln={kacheln} ohneSensor={ohneSensor} /></ThemeProvider>)
    const titel = [...container.querySelectorAll('svg g[data-title]')].map((g) => g.getAttribute('data-title') ?? '')
    expect(titel.some((t) => t.includes('Wärme heute: 23,0 kWh'))).toBe(true)
  })
})
