/**
 * P-433-3 Sitzung 2 — die drei Zusatzpunkte aus der Lab-Sichtprobe (Lab 4.1.11-rc2, 25.10.2026) am Hub-Überblick:
 *
 * - **S2-6** kompakte Dims (ab 5 Kacheln je Reihe, nodeW 80): die Kachel «Vorlauf · Rücklauf» zeigt ganze Grad
 *   («34 → 29 °C»); in den Standard-Dims bleibt eine Nachkommastelle («33,9 → 28,8 °C»). Tooltip und Karte unverändert.
 * - **S2-7** Kreuzungsprobe für Matheks Reihe mit 6 Kacheln (Himmel, C, G, D, E, I): keine zwei Linien schneiden sich;
 *   die Reihenfolge in der Reihe ist Anker-x mit Nachbartausch, der Rang entscheidet nur über «Weitere».
 * - **S2-8** (Entscheid Gernot 25.10.) der Anker der Kachel «Vorlauf · Rücklauf» folgt dem Stammdatum
 *   `vorlauftemperatur`: '35' ⇒ K Fußbodenheizung (untere Reihe), '55' ⇒ J Heizkörper, sonst G Hydraulikmodul;
 *   Karten-Zeile «Vorlauf (Fußbodenheizung)»/«Vorlauf (Heizkörper)»/«Vorlauf», Tooltip «… am Gerät gemessen».
 *
 * Werte: Matheks Lab-Sichtprobe (Vorlauf 33,9 °C, Rücklauf 28,8 °C).
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { render } from '@testing-library/react'
import UeberblickKarte from './UeberblickKarte'
import UeberblickSchaubild from './UeberblickSchaubild'
import { hatKreuzung, layoutUeberblick, type LayoutKachel, type Platz } from './ueberblickLayout'
import {
  ANKER_VORLAUF, ANKER_VORLAUF_FUSSBODENHEIZUNG, ANKER_VORLAUF_HEIZKOERPER, ANKER_ZUSATZHEIZUNG,
  baueUeberblickKacheln, kachelWertText, vorlaufAnker, vorlaufBeschriftung,
} from './kachelAnker'
import { computeDims } from '../../live/energieFlussLayout'
import { heizkreisArt } from '../../../lib/investitionParameter'
import { ThemeProvider } from '../../../context/ThemeContext'
import { stubMatchMedia } from '../../../test/render'
import type { LiveDashboardResponse, LiveKomponente } from '../../../api/liveDashboard'
import type { Investition } from '../../../types'

beforeEach(() => { stubMatchMedia(); localStorage.clear() })

const wpInv = (parameter: Record<string, unknown> = {}): Investition =>
  ({ id: 7, anlage_id: 1, typ: 'waermepumpe', bezeichnung: 'Nibe S1256', aktiv: true, parameter } as Investition)
const knoten = (extra: Partial<LiveKomponente> = {}): LiveKomponente => ({
  key: 'waermepumpe_7', label: 'WP', icon: 'heater', erzeugung_kw: null, verbrauch_kw: 1.64, typ: 'waermepumpe',
  betriebsmodus: 'heizen', betriebsmodus_label: 'Heizen',
  vorlauf_c: 33.9, ruecklauf_c: 28.8, spreizung_k: 5.1, warmwasser_c: 48.5, heizstab_w: 0, ...extra,
})
const live = (extra: Partial<LiveKomponente> = {}): LiveDashboardResponse => ({
  anlage_id: 1, anlage_name: 'Lab', zeitpunkt: '2026-10-25T12:00:00', verfuegbar: true,
  komponenten: [knoten(extra)], summe_erzeugung_kw: 0, summe_verbrauch_kw: 0, summe_pv_kw: 0, gauges: [],
  heute_pv_kwh: null, heute_einspeisung_kwh: null, heute_netzbezug_kwh: null, heute_eigenverbrauch_kwh: null,
  gestern_pv_kwh: null, gestern_einspeisung_kwh: null, gestern_netzbezug_kwh: null, gestern_eigenverbrauch_kwh: null,
  heute_kwh_pro_komponente: { waermepumpe_7: 5.5 }, warmwasser_temperatur_c: 48.5, innengeraete: null,
})
const WETTER = { aktuell: { zeit: '12:00', temperatur_c: 7.8 } } as unknown as
  Parameters<typeof baueUeberblickKacheln>[0]['wetter']
const SOLE = { wp_art: 'sole_wasser', kuehlung_art: 'passiv' }
const baue = (parameter: Record<string, unknown>) =>
  baueUeberblickKacheln({ geraete: [wpInv(parameter)], live: live(), wetter: WETTER, referenz: 'referenz' })
const vorlauf = (parameter: Record<string, unknown>) => baue(parameter).kacheln.find((k) => k.id === 'wert-vorlauf-7')!

// ── S2-6 ────────────────────────────────────────────────────────────────────

describe('S2-6: Werttext «Vorlauf · Rücklauf» je Dims', () => {
  it('kompakte Dims (nodeW 80) ⇒ «34 → 29 °C», Standard (100) und 88 ⇒ «33,9 → 28,8 °C»', () => {
    const v = vorlauf(SOLE)
    expect(kachelWertText(v, computeDims(6))).toBe('34 → 29 °C')
    expect(computeDims(6).nodeW).toBe(80)
    expect(kachelWertText(v, computeDims(3))).toBe('33,9 → 28,8 °C')
    expect(kachelWertText(v, computeDims(4))).toBe('33,9 → 28,8 °C')
  })

  it('Tooltip behält die Nachkommastelle; ein Einzelwert hat keine Kurzform', () => {
    const v = vorlauf(SOLE)
    expect(v.tip).toContain('Vorlauf: 33,9 °C')
    expect(v.tip).toContain('Rücklauf: 28,8 °C')
    const nurVorlauf = baueUeberblickKacheln({
      geraete: [wpInv(SOLE)], live: live({ ruecklauf_c: null, spreizung_k: null }), wetter: null, referenz: 'r',
    }).kacheln.find((k) => k.id === 'wert-vorlauf-7')!
    expect(kachelWertText(nurVorlauf, computeDims(6))).toBe('33,9 °C')
  })

  it('das Schaubild zeichnet in Matheks 6er-Reihe die Kurzform', () => {
    const { kacheln, ohneSensor } = baue(SOLE)
    expect(kacheln).toHaveLength(6)
    const { container } = render(<ThemeProvider><UeberblickSchaubild kacheln={kacheln} ohneSensor={ohneSensor} /></ThemeProvider>)
    const texte = [...container.querySelectorAll('svg text')].map((t) => t.textContent ?? '')
    expect(texte).toContain('34 → 29 °C')
    expect(texte).not.toContain('33,9 → 28,8 °C')
  })
})

// ── S2-7 ────────────────────────────────────────────────────────────────────

const name = (p: Platz) => p.mitglieder[0].id

/** Matheks Reihe aus der Lab-Sichtprobe: Außen (Himmel), Gerät (C), Vorlauf (je Stammdatum), Zusatzheizung (D),
 *  Warmwasser (E), Strom (I). */
const matheksReihe = (vorlaufAnkerId: LayoutKachel['anker']): LayoutKachel[] => [
  { id: 'aussen', art: 'wert', anker: 'HIMMEL' }, { id: 'wp', art: 'geraet', anker: 'C' },
  { id: 'vorlauf', art: 'wert', anker: vorlaufAnkerId }, { id: 'zusatz', art: 'wert', anker: ANKER_ZUSATZHEIZUNG },
  { id: 'ww', art: 'wert', anker: 'E' }, { id: 'strom', art: 'wert', anker: 'I' },
]
const BREITEN = [1440, 1100, 900, 700, 600, 480, 390, 340]

describe('S2-7: keine Kreuzung in Matheks Reihe', () => {
  it.each([
    ['G (ohne Stammdatum)', ANKER_VORLAUF],
    ['K (Fußbodenheizung)', ANKER_VORLAUF_FUSSBODENHEIZUNG],
    ['J (Heizkörper)', ANKER_VORLAUF_HEIZKOERPER],
  ] as const)('%s: an jeder Breite schneiden sich keine zwei Linien einer Reihe', (_, anker) => {
    for (const ctr of BREITEN) {
      const l = layoutUeberblick(matheksReihe(anker), ctr)
      expect(hatKreuzung(l.oben), `oben @${ctr}`).toBe(false)
      expect(hatKreuzung(l.unten), `unten @${ctr}`).toBe(false)
    }
  })

  it('G: die Reihe folgt Anker-x mit Nachbartausch — Vorlauf (G) vor Zusatzheizung (D), weil sich die Linien in reiner x-Folge schneiden', () => {
    const l = layoutUeberblick(matheksReihe(ANKER_VORLAUF), 1440)
    // Gemessen 25.10.: in reiner Anker-x-Folge (D 25,8 % vor G 29,0 %) schneidet die Linie D→Pufferspeicher (tief)
    // die Linie G→Hydraulikmodul (hoch); die Kreuzungsprobe tauscht die Nachbarn. Rang-Folge (Gerät, Warmwasser,
    // Strom, Vorlauf, Zusatz, Außen) stünde hier ganz anders.
    expect(l.oben.map(name)).toEqual(['aussen', 'wp', 'vorlauf', 'zusatz', 'ww', 'strom'])
    expect(l.oben.every((p, i) => i === 0 || p.x > l.oben[i - 1].x)).toBe(true)
  })

  it('K: 5 oben / 1 unten, die Reihen in Anker-x-Folge', () => {
    const l = layoutUeberblick(matheksReihe(ANKER_VORLAUF_FUSSBODENHEIZUNG), 1440)
    expect(l.oben.map(name)).toEqual(['aussen', 'wp', 'zusatz', 'ww', 'strom'])
    expect(l.unten.map(name)).toEqual(['vorlauf'])
  })

  it('J: 5 oben / 1 unten, Vorlauf am Heizkörper unten (P-433-2d «Räume unten»)', () => {
    const l = layoutUeberblick(matheksReihe(ANKER_VORLAUF_HEIZKOERPER), 1440)
    expect(l.oben.map(name)).toEqual(['aussen', 'wp', 'zusatz', 'ww', 'strom'])
    expect(l.unten.map(name)).toEqual(['vorlauf'])
    expect(l.reihenwechsel).toEqual([])
  })
})

// ── S2-8 ────────────────────────────────────────────────────────────────────

describe('S2-8: Anker und Beschriftung nach dem Stammdatum `vorlauftemperatur`', () => {
  it.each([
    ['35', 'fussbodenheizung', ANKER_VORLAUF_FUSSBODENHEIZUNG, 'Vorlauf (Fußbodenheizung)'],
    ['55', 'heizkoerper', ANKER_VORLAUF_HEIZKOERPER, 'Vorlauf (Heizkörper)'],
    [undefined, null, ANKER_VORLAUF, 'Vorlauf'],
    ['45', null, ANKER_VORLAUF, 'Vorlauf'],
  ] as const)('vorlauftemperatur %s ⇒ %s · Anker %s · «%s»', (wert, art, anker, beschriftung) => {
    const p = wert === undefined ? { ...SOLE } : { ...SOLE, vorlauftemperatur: wert }
    expect(heizkreisArt(p)).toBe(art)
    expect(vorlaufAnker(wpInv(p))).toBe(anker)
    expect(vorlaufBeschriftung(wpInv(p))).toBe(beschriftung)
    expect(vorlauf(p).anker).toBe(anker)
  })

  it('[K, J, G] sind die drei Objekte; die Zusatzheizung bleibt an D', () => {
    expect([ANKER_VORLAUF_FUSSBODENHEIZUNG, ANKER_VORLAUF_HEIZKOERPER, ANKER_VORLAUF, ANKER_ZUSATZHEIZUNG])
      .toEqual(['K', 'J', 'G', 'D'])
    expect(baue({ ...SOLE, vorlauftemperatur: '55' }).kacheln.find((k) => k.id === 'wert-zusatzheizung-7')?.anker)
      .toBe(ANKER_ZUSATZHEIZUNG)
  })

  it('Tooltip der Kachel: «Vorlauf der Wärmepumpe am Gerät gemessen»', () => {
    expect(vorlauf({ ...SOLE, vorlauftemperatur: '35' }).tip.split('\n')).toEqual([
      'Nibe S1256', 'Vorlauf: 33,9 °C', 'Rücklauf: 28,8 °C', 'Spreizung: 5,1 K',
      'Vorlauf der Wärmepumpe am Gerät gemessen', 'Quelle: Live-Snapshot',
    ])
  })

  it.each([
    ['35', 'Vorlauf (Fußbodenheizung)'], ['55', 'Vorlauf (Heizkörper)'], [undefined, 'Vorlauf'],
  ] as const)('Karte: vorlauftemperatur %s ⇒ Zeile «%s»', (wert, beschriftung) => {
    const inv = wpInv(wert === undefined ? SOLE : { ...SOLE, vorlauftemperatur: wert })
    const { container } = render(<UeberblickKarte inv={inv} live={live()} wetter={null} tag={null} mehrereGeraete={false} />)
    const zeile = container.querySelector('[data-zeile="vorlauf"]')
    expect(zeile?.textContent).toContain(beschriftung)
    expect(zeile?.textContent).toContain('33,9 °C')
  })
})
