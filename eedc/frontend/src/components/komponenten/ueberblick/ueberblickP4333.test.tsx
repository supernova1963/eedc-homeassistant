/**
 * P-433-3 S1 (#432, Konzept #433 Stufe 3): Vorlauf · Rücklauf, Zusatzheizung und Warmwasser je Gerät im
 * Hub-Überblick — Kacheln an `ANKER_VORLAUF` (G)/`ANKER_ZUSATZHEIZUNG` (D), nur mit Wert, **nicht** in der «Ohne
 * Sensor»-Zeile (G7/E-P3-13); Warmwasser-Kachel E aus dem Gerätewert (E-P3-7, Zwei-WP-Probe); Karte mit Zeilen
 * Vorlauf, Rücklauf, Spreizung (vom Backend geliefert, `spreizung_k`), Zusatzheizung und dem gedämpften Chip
 * «Zusatzheizung aktiv»; Rang der neuen Wert-Kacheln im Layout (Nacharbeit Master 25.10.).
 *
 * Fixture: Matheks Nibe S1255 (Sole, passiv) mit den Werten seiner Entitäten
 * (`sensor.supply_line_bt2_30006`, `sensor.return_line_bt3_30008`, `sensor.power_internal_additional_heat_31028`),
 * so wie der Builder sie an den Knoten legt (`backend/tests/test_p433_3_s1_live_temperaturen.py`).
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { render } from '@testing-library/react'
import UeberblickKarte from './UeberblickKarte'
import UeberblickSchaubild from './UeberblickSchaubild'
import { layoutReihen, layoutUeberblick, type LayoutKachel, type Platz } from './ueberblickLayout'
import {
  ANKER_VORLAUF, ANKER_ZUSATZHEIZUNG, baueUeberblickKacheln, warmwasserC, zusatzheizungAktiv,
} from './kachelAnker'
import { ThemeProvider } from '../../../context/ThemeContext'
import { stubMatchMedia } from '../../../test/render'
import type { LiveDashboardResponse, LiveKomponente } from '../../../api/liveDashboard'
import type { Investition } from '../../../types'

beforeEach(() => { stubMatchMedia(); localStorage.clear() })

const wpInv = (id: number, bezeichnung: string, parameter: Record<string, unknown> = {}): Investition =>
  ({ id, anlage_id: 1, typ: 'waermepumpe', bezeichnung, aktiv: true, parameter } as Investition)
const knoten = (id: number, kw: number, extra: Partial<LiveKomponente> = {}): LiveKomponente =>
  ({ key: `waermepumpe_${id}`, label: `WP ${id}`, icon: 'heater', erzeugung_kw: null, verbrauch_kw: kw, typ: 'waermepumpe', ...extra })
const liveAntwort = (extra: Partial<LiveDashboardResponse> = {}): LiveDashboardResponse => ({
  anlage_id: 1, anlage_name: 'Test', zeitpunkt: '2026-10-25T12:00:00', verfuegbar: true,
  komponenten: [], summe_erzeugung_kw: 0, summe_verbrauch_kw: 0, summe_pv_kw: 0, gauges: [],
  heute_pv_kwh: null, heute_einspeisung_kwh: null, heute_netzbezug_kwh: null, heute_eigenverbrauch_kwh: null,
  gestern_pv_kwh: null, gestern_einspeisung_kwh: null, gestern_netzbezug_kwh: null, gestern_eigenverbrauch_kwh: null,
  heute_kwh_pro_komponente: null, warmwasser_temperatur_c: null, innengeraete: null,
  ...extra,
})

const MATHEK = wpInv(7, 'Nibe S1255', { wp_art: 'sole_wasser', kuehlung_art: 'passiv' })
const matheksKnoten = (extra: Partial<LiveKomponente> = {}) => knoten(7, 1.2, {
  betriebsmodus: 'heizen', betriebsmodus_label: 'Heizen',
  vorlauf_c: 34.2, ruecklauf_c: 29.1, spreizung_k: 5.1, warmwasser_c: 48.3, heizstab_w: 1500, ...extra,
})
const matheksLive = (extra: Partial<LiveKomponente> = {}) => liveAntwort({
  komponenten: [matheksKnoten(extra)], warmwasser_temperatur_c: 48.3, heute_kwh_pro_komponente: { waermepumpe_7: 6.4 },
})
const baue = (geraete: Investition[], live: LiveDashboardResponse | null) =>
  baueUeberblickKacheln({ geraete, live, wetter: null, referenz: 'referenz' })

describe('Kacheln Vorlauf · Rücklauf und Zusatzheizung', () => {
  it('Matheks Fall: «34,2 → 29,1 °C» an G, «Zusatzheizung 1.500 W» an D, Tooltip mit Spreizung', () => {
    const { kacheln } = baue([MATHEK], matheksLive())
    const v = kacheln.find((k) => k.id === 'wert-vorlauf-7')!
    expect([v.anker, v.label, v.wertText, v.art, v.investitionId]).toEqual(
      [ANKER_VORLAUF, 'Vorlauf · Rücklauf', '34,2 → 29,1 °C', 'wert', 7])
    expect(v.tip.split('\n')).toEqual(
      // S2-8: die Zeile «am Gerät gemessen» — die Kachel steht am Heizkreis, gemessen wird an der Wärmepumpe.
      ['Nibe S1255', 'Vorlauf: 34,2 °C', 'Rücklauf: 29,1 °C', 'Spreizung: 5,1 K',
        'Vorlauf der Wärmepumpe am Gerät gemessen', 'Quelle: Live-Snapshot'])
    const z = kacheln.find((k) => k.id === 'wert-zusatzheizung-7')!
    expect([z.anker, z.label, z.wertText, z.art]).toEqual([ANKER_ZUSATZHEIZUNG, 'Zusatzheizung', '1.500 W', 'wert'])
    expect([ANKER_VORLAUF, ANKER_ZUSATZHEIZUNG]).toEqual(['G', 'D'])
  })

  it('eine Regel für alle Bauarten: der Anker hängt nicht an der Bauart', () => {
    for (const wp_art of ['luft_wasser', 'sole_wasser', 'brauchwasser', 'luft_luft']) {
      const inv = wpInv(7, 'X', { wp_art })
      const { kacheln } = baue([inv], matheksLive())
      expect(kacheln.find((k) => k.id === 'wert-vorlauf-7')?.anker, wp_art).toBe(ANKER_VORLAUF)
      expect(kacheln.find((k) => k.id === 'wert-zusatzheizung-7')?.anker, wp_art).toBe(ANKER_ZUSATZHEIZUNG)
    }
  })

  it('nur ein Wert: «Vorlauf 34,2 °C» bzw. «Rücklauf»; 0 W ist ein Wert («steht»)', () => {
    const nurVorlauf = baue([MATHEK], matheksLive({ ruecklauf_c: null, spreizung_k: null, heizstab_w: 0 })).kacheln
    expect(nurVorlauf.find((k) => k.id === 'wert-vorlauf-7')).toMatchObject({ label: 'Vorlauf', wertText: '34,2 °C' })
    expect(nurVorlauf.find((k) => k.id === 'wert-zusatzheizung-7')?.wertText).toBe('0 W')
    const nurRueck = baue([MATHEK], matheksLive({ vorlauf_c: null, spreizung_k: null })).kacheln
    expect(nurRueck.find((k) => k.id === 'wert-vorlauf-7')).toMatchObject({ label: 'Rücklauf', wertText: '29,1 °C' })
  })

  it('ohne Sensor: keine Kachel und KEIN Eintrag in der «Ohne Sensor»-Zeile (G7)', () => {
    const { kacheln, ohneSensor } = baue([MATHEK], liveAntwort({ komponenten: [knoten(7, 1.2)] }))
    expect(kacheln.map((k) => k.id)).toEqual(['geraet-7'])
    expect(ohneSensor).toEqual(['Warmwasser-Temperatur', 'Strom heute'])
    expect(ohneSensor.join(' ')).not.toMatch(/Vorlauf|Rücklauf|Zusatzheizung/)
  })

  it('mehrere Geräte: Name an der Kachel, je Gerät nur mit eigenem Wert', () => {
    const zweite = wpInv(8, 'Zweit-WP', { wp_art: 'luft_wasser' })
    const live = liveAntwort({ komponenten: [matheksKnoten(), knoten(8, 0.6)] })
    const ids = baue([MATHEK, zweite], live).kacheln.map((k) => k.id)
    expect(ids).toContain('wert-vorlauf-7')
    expect(ids).not.toContain('wert-vorlauf-8')
    expect(baue([MATHEK, zweite], live).kacheln.find((k) => k.id === 'wert-zusatzheizung-7')?.label)
      .toBe('Zusatzheizung Nibe S1255')
  })

  it('Schaubild zeichnet die neuen Kacheln mit Tooltip (Desktop)', () => {
    const { kacheln, ohneSensor } = baue([MATHEK], matheksLive())
    const { container } = render(<ThemeProvider><UeberblickSchaubild kacheln={kacheln} ohneSensor={ohneSensor} /></ThemeProvider>)
    const titel = [...container.querySelectorAll('svg g[data-title]')].map((g) => g.getAttribute('data-title') ?? '')
    expect(titel.some((t) => t.includes('Vorlauf: 34,2 °C'))).toBe(true)
    expect(titel.some((t) => t.includes('Zusatzheizung: 1.500 W'))).toBe(true)
  })
})

describe('Warmwasser-Kachel E je Gerät (E-P3-7)', () => {
  it('zwei Wärmepumpen: je Gerät seine Temperatur — nicht zweimal der Anlagenwert', () => {
    const zweite = wpInv(8, 'Zweit-WP', { wp_art: 'luft_wasser' })
    const live = liveAntwort({
      komponenten: [knoten(7, 1.2, { warmwasser_c: 48.0 }), knoten(8, 0.6, { warmwasser_c: 52.4 })],
      warmwasser_temperatur_c: 48.0,
    })
    const ww = baue([MATHEK, zweite], live).kacheln.filter((k) => k.anker === 'E')
    expect(ww.map((k) => [k.id, k.label, k.wertText, k.investitionId])).toEqual([
      ['wert-warmwasser-7', 'Warmwasser Nibe S1255', '48,0 °C', 7],
      ['wert-warmwasser-8', 'Warmwasser Zweit-WP', '52,4 °C', 8],
    ])
    expect([warmwasserC(live, 7), warmwasserC(live, 8)]).toEqual([48.0, 52.4])
  })

  it('kein Knoten trägt einen Gerätewert: wie bisher EINE Kachel mit dem Anlagenwert', () => {
    const live = liveAntwort({ komponenten: [knoten(7, 1.2)], warmwasser_temperatur_c: 48.5 })
    const ww = baue([MATHEK], live).kacheln.filter((k) => k.anker === 'E')
    expect(ww.map((k) => [k.id, k.label, k.wertText, k.investitionId])).toEqual([['wert-warmwasser', 'Warmwasser', '48,5 °C', null]])
    expect(warmwasserC(live, 7)).toBe(48.5)
  })

  it('Gerätewert vorhanden: ein anderes Gerät ohne eigenen Wert erbt den Anlagenwert NICHT', () => {
    const live = liveAntwort({ komponenten: [knoten(7, 1.2, { warmwasser_c: 48.0 }), knoten(8, 0.6)], warmwasser_temperatur_c: 48.0 })
    expect(warmwasserC(live, 8)).toBeNull()
  })
})

describe('Hilfsfunktionen', () => {
  it('Zusatzheizung aktiv nur über 0 W', () => {
    expect([zusatzheizungAktiv({ heizstab_w: 1500 }), zusatzheizungAktiv({ heizstab_w: 0 }),
      zusatzheizungAktiv({ heizstab_w: null }), zusatzheizungAktiv(undefined)]).toEqual([true, false, false, false])
  })
})

const zeilen = (c: HTMLElement) => [...c.querySelectorAll('[data-zeile]')].map((z) => z.getAttribute('data-zeile'))

describe('Karte «Auf einen Blick»', () => {
  it('Matheks Fall: Vorlauf, Rücklauf, Spreizung, Zusatzheizung; Chip «Zusatzheizung aktiv» neben dem Modus', () => {
    const { container } = render(
      <UeberblickKarte inv={MATHEK} live={matheksLive()} wetter={null} tag={null} mehrereGeraete={false} />)
    // P-433-2c: Reihenfolge der Gerätekarte nach Mockup — Warmwasser · Zusatzheizung · Vorlauf · Rücklauf · Spreizung.
    expect(zeilen(container)).toEqual(['leistung', 'warmwasser', 'zusatzheizung', 'vorlauf', 'ruecklauf', 'spreizung', 'strom-heute'])
    expect(container.textContent).toContain('34,2 °C')
    expect(container.textContent).toContain('29,1 °C')
    expect(container.textContent).toContain('5,1 K')
    expect(container.textContent).toContain('1.500 W')
    expect(container.querySelector('[data-modus-chip="heizen"]')).not.toBeNull()
    const chip = container.querySelector('[data-zusatz-chip]')
    expect(chip?.textContent).toBe('Zusatzheizung aktiv')
    expect(chip?.className).toContain('text-gray-500')
  })

  it('Zusatzheizung steht (0 W): Zeile ja, Chip nein; ohne Rücklauf keine Spreizung', () => {
    const { container } = render(
      <UeberblickKarte inv={MATHEK} live={matheksLive({ heizstab_w: 0, ruecklauf_c: null, spreizung_k: null })} wetter={null} tag={null} mehrereGeraete={false} />)
    expect(zeilen(container)).toEqual(['leistung', 'warmwasser', 'zusatzheizung', 'vorlauf', 'strom-heute'])
    expect(container.querySelector('[data-zusatz-chip]')).toBeNull()
  })

  it('Chip auch ohne Modus-Sensor', () => {
    const { container } = render(
      <UeberblickKarte inv={MATHEK} live={matheksLive({ betriebsmodus: null, betriebsmodus_label: null })} wetter={null} tag={null} mehrereGeraete={false} />)
    expect(container.querySelector('[data-modus-chip]')).toBeNull()
    expect(container.querySelector('[data-zusatz-chip]')?.textContent).toBe('Zusatzheizung aktiv')
  })

  it('Warmwasser der Karte ist der Wert des gewählten Geräts', () => {
    const zweite = wpInv(8, 'Zweit-WP', { wp_art: 'luft_wasser' })
    const live = liveAntwort({ komponenten: [knoten(7, 1.2, { warmwasser_c: 48.0 }), knoten(8, 0.6, { warmwasser_c: 52.4 })], warmwasser_temperatur_c: 48.0 })
    const { container } = render(<UeberblickKarte inv={zweite} live={live} wetter={null} tag={null} mehrereGeraete />)
    expect(container.querySelector('[data-zeile="warmwasser"]')?.textContent).toContain('52,4 °C')
  })
})

describe('Spreizung: der Client zeigt den gelieferten Wert (Nacharbeit A3)', () => {
  it('Karte und Tooltip zeigen `spreizung_k`, auch wenn er von Vorlauf − Rücklauf abweicht — gerechnet wird nicht', () => {
    const live = matheksLive({ spreizung_k: 7.7 })
    const { container } = render(<UeberblickKarte inv={MATHEK} live={live} wetter={null} tag={null} mehrereGeraete={false} />)
    expect(container.querySelector('[data-zeile="spreizung"]')?.textContent).toContain('7,7 K')
    expect(baue([MATHEK], live).kacheln.find((k) => k.id === 'wert-vorlauf-7')?.tip).toContain('Spreizung: 7,7 K')
  })

  it('ohne geliefertes `spreizung_k` keine Spreizung — auch wenn Vorlauf und Rücklauf da sind', () => {
    const live = matheksLive({ spreizung_k: null })
    const { container } = render(<UeberblickKarte inv={MATHEK} live={live} wetter={null} tag={null} mehrereGeraete={false} />)
    expect(container.querySelector('[data-zeile="spreizung"]')).toBeNull()
    expect(baue([MATHEK], live).kacheln.find((k) => k.id === 'wert-vorlauf-7')?.tip).not.toContain('Spreizung')
  })
})

/** Was in einer Reihe steht: Einzel-ID oder „Gruppe(Mitglieder)". */
const platzName = (p: Platz) => (p.gruppe ? `${p.gruppe}(${p.mitglieder.map((m) => m.id).join(',')})` : p.mitglieder[0].id)

describe('Rang der neuen Wert-Kacheln (Leistung · Warmwasser · Strom · Vorlauf/Rücklauf · Zusatzheizung · Außen)', () => {
  const wert = (id: string, anker: LayoutKachel['anker']): LayoutKachel => ({ id, art: 'wert', anker })
  const sechs: LayoutKachel[] = [
    { id: 'wp', art: 'geraet', anker: 'C' }, wert('ww', 'E'), wert('strom', 'I'),
    wert('vorlauf', ANKER_VORLAUF), wert('zusatz', ANKER_ZUSATZHEIZUNG), wert('aussen', 'HIMMEL'),
  ]

  it('Matheks Reihe mit 6 Kacheln: Desktop-Kapazität 6 ⇒ alle einzeln, oben (seit P-433-2e die WP im linken Platz)', () => {
    const { kacheln } = baueUeberblickKacheln({
      geraete: [MATHEK], live: matheksLive(),
      wetter: { aktuell: { zeit: '12:00', temperatur_c: 7.4 } } as unknown as Parameters<typeof baueUeberblickKacheln>[0]['wetter'],
      referenz: 'referenz',
    })
    expect(kacheln).toHaveLength(6)
    const r = layoutReihen(kacheln, 900)   // die zwei Reihen ohne Plätze
    expect([r.oben.length, r.unten.length]).toEqual([6, 0])
    expect(r.oben.every((p) => p.gruppe == null)).toBe(true)
    const l = layoutUeberblick(kacheln, 900)
    expect(l.links?.mitglieder[0].art).toBe('geraet')
    expect([l.oben.length, l.unten.length]).toEqual([5, 0])
    expect(l.oben.every((p) => p.gruppe == null)).toBe(true)
  })

  it('volle Reihe: zuerst Außen, dann Zusatzheizung, dann Vorlauf/Rücklauf nach «Weitere»', () => {
    // Desktop (W 600, ab 5 Kacheln nodeW 80) fasst 6 Plätze: 7 Kacheln ⇒ 5 einzeln + «Weitere (2)». Der Rang gilt der
    // Reihe — geprüft an den zwei Reihen ohne Plätze (`layoutReihen`; am Desktop nähmen die Plätze die Geräte heraus).
    const sieben = [...sechs, { id: 'wp2', art: 'geraet' as const, anker: 'F' as const }]
    const weitere7 = layoutReihen(sieben, 900).oben.find((p) => p.gruppe === 'weitere')
    expect(weitere7 && platzName(weitere7)).toBe('weitere(zusatz,aussen)')
    // 8 Kacheln ⇒ 5 einzeln + «Weitere (3)»: jetzt wandert auch Vorlauf/Rücklauf.
    const acht = [...sieben, { id: 'klima', art: 'geraet' as const, anker: 'O' as const }]
    const weitere8 = layoutReihen(acht, 900).oben.find((p) => p.gruppe === 'weitere')
    expect(weitere8 && platzName(weitere8)).toBe('weitere(vorlauf,zusatz,aussen)')
    // Handy 390 px (W 450, 4 Plätze): Gerät, Warmwasser, Strom bleiben; Vorlauf, Zusatz, Außen gehen.
    const handy = layoutUeberblick(sechs, 390).oben
    expect(handy.map(platzName).sort()).toEqual(['strom', 'weitere(vorlauf,zusatz,aussen)', 'wp', 'ww'].sort())
  })
})
