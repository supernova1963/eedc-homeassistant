/**
 * Themen-Kacheln (4.2.0 TH-E2, Bauplan §2.1/§2.4): der Kachel-Bauer `baueThemenKacheln` — Zeilen «Label · Wert»,
 * kompakter Wert, Tooltip mit allen Einträgen und Stand, Zeitstempel/Zahl/wörtlich, zwei Einträge sichtbar, ein Thema
 * ohne Eintrag mit Wert fehlt (P1), Einträge ohne Wert rücken nicht vor (P2) — und die Kürzung der Zeichnung
 * (`kuerzeThemenZeile`, `themenKachelTexte`; Entscheid Master 1.11.2026 zu H1: der Wert ist das Wichtige).
 * Zeitpunkte werden aus der lokalen Uhr gebaut, damit die Probe in jeder Zeitzone (CI: UTC und Auckland) gilt.
 *
 * Schwesterdateien: ueberblickLayout.test.ts, emobLayout.test.ts, ueberblickParken.test.tsx.
 */
import { describe, it, expect } from 'vitest'
import type { LiveThema, LiveThemaEintrag } from '../../../api/liveDashboard'
import type { Investition } from '../../../types'
import { KATEGORIE_FARBEN } from '../../../lib'
import { computeDims } from '../../live/energieFlussLayout'
import { baueUeberblickKacheln } from './kachelAnker'
import { baueFahrzeugKacheln, baueLadepunktKacheln } from './emobKachelAnker'
import {
  baueThemenKacheln, kuerzeThemenZeile, themaStand, themaWert, themaWertKurz, themaZeile, themenKachelTexte, themenVon,
} from './themenKacheln'
import type { LiveDashboardResponse } from '../../../api/liveDashboard'

const JETZT = new Date(2026, 10, 1, 12, 0)
const heute = (h: number, m: number) => new Date(2026, 10, 1, h, m).toISOString()
const morgen = (h: number, m: number) => new Date(2026, 10, 2, h, m).toISOString()

const eintrag = (id: string, label: string, wert: string, extra: Partial<LiveThemaEintrag> = {}): LiveThemaEintrag =>
  ({ id, label, wert, einheit: '', zeitpunkt: null, device_class: null, quelle: 'ha', ...extra })
const thema = (inv: number, id: string, name: string, eintraege: LiveThemaEintrag[]): LiveThema =>
  ({ investition_id: inv, id, name, eintraege })
const inv = (id: number, typ: string, bez: string): Investition =>
  ({ id, anlage_id: 1, typ, bezeichnung: bez, aktiv: true, parameter: {} } as Investition)
const IONIQ = inv(7, 'e-auto', 'Ioniq')

const ZUSTAND = thema(7, 't1', 'Fahrzeugzustand', [
  eintrag('e1', 'Türen', 'locked', { zeitpunkt: heute(6, 20) }),
  eintrag('e2', 'Reifen vorne links', '259.5', { einheit: 'kPa', zeitpunkt: heute(11, 27) }),
  eintrag('e3', 'Fenster', 'closed'),
])

describe('Wert wie der HA-State — nur formatiert (Bauplan §0)', () => {
  it.each([
    ['259.5', 'kPa', null, '259,5 kPa'],
    ['12.3846', '', null, '12,38'],
    ['7', '%', null, '7 %'],
    ['-3.10', '°C', null, '-3,10 °C'],
    ['locked', '', null, 'locked'],
    ['not_home', '', null, 'not_home'],
    ['on', '', 'door', 'on'],
  ])('%s %s (%s) ⇒ «%s»', (wert, einheit, dc, soll) => {
    expect(themaWert(eintrag('e', 'x', wert, { einheit, device_class: dc }), JETZT)).toBe(soll)
  })

  it('Zeitstempel: heute nur die Uhrzeit, an einem anderen Tag Datum und Uhrzeit; reines Datum ⇒ Datum', () => {
    expect(themaWert(eintrag('e', 'Plan', heute(7, 5), { device_class: 'timestamp' }), JETZT)).toBe('07:05')
    expect(themaWert(eintrag('e', 'Plan', morgen(7, 0)), JETZT)).toBe('02.11.2026, 07:00')
    expect(themaWert(eintrag('e', 'Service', '2027-03-15', { device_class: 'date' }), JETZT)).toBe('15.03.2027')
    expect(themaStand(heute(11, 27), JETZT)).toBe('Stand 11:27')
    expect(themaStand(null, JETZT)).toBeNull()
  })
})

describe('K1 (Nachlauf 4.2.0): Zeitstempel in der Kachel kurz «TT.MM. HH:MM», Tooltip und Karte voll', () => {
  const plan = (iso: string) => eintrag('e', 'Plan', iso, { device_class: 'timestamp' })

  it('heute nur die Uhrzeit, anderer Tag «02.11. 07:00» — themaWert kurz, die Kachelzeile, kompakt', () => {
    expect(themaWert(plan(heute(9, 0)), JETZT, true)).toBe('09:00')
    expect(themaWert(plan(morgen(7, 0)), JETZT, true)).toBe('02.11. 07:00')
    expect(themaZeile(plan(morgen(7, 0)), JETZT)).toBe('Plan · 02.11. 07:00')
    expect(themaWert(plan(morgen(7, 0)), JETZT)).toBe('02.11.2026, 07:00')  // ohne `kurz`: volle Form (Karte)
  })

  it('Jahreswechsel: ohne Jahr in der Kachel, mit Jahr im Tooltip', () => {
    const silvester = new Date(2026, 11, 31, 23, 30)
    const neujahr = new Date(2027, 0, 1, 0, 15).toISOString()
    expect(themaWert(plan(neujahr), silvester, true)).toBe('01.01. 00:15')
    expect(themaWert(plan(neujahr), silvester)).toBe('01.01.2027, 00:15')
    expect(themaWert(plan(new Date(2026, 11, 31, 23, 59).toISOString()), new Date(2027, 0, 1, 8, 0), true)).toBe('31.12. 23:59')
  })

  it('baueThemenKacheln: Kachel kurz (Wert-Zeile, kompakt, Teile, zweite Zeile), Tooltip voll', () => {
    const wartung = new Date(2026, 11, 11, 9, 0).toISOString()
    const t = thema(7, 't2', 'Service', [
      eintrag('e1', 'Nächste Wartung', wartung, { device_class: 'timestamp' }),
      eintrag('e2', 'Ladeplan', wartung),
    ])
    const [k] = baueThemenKacheln([t], IONIQ, 'HIMMEL', KATEGORIE_FARBEN.eauto, false, JETZT)
    expect(k.wertText).toBe('Nächste Wartung · 11.12. 09:00')
    expect(k.wertTextKompakt).toBe('11.12. 09:00')
    expect(k.themaTeile?.erste.wert).toBe('11.12. 09:00')
    expect(k.zweiteZeile?.text).toBe('Ladeplan · 11.12. 09:00')
    expect(k.themaTeile?.zweite?.wert).toBe('11.12. 09:00')
    expect(k.tip).toBe('Service\nNächste Wartung: 11.12.2026, 09:00\nLadeplan: 11.12.2026, 09:00')
  })

  it('K1b (Entscheid Master 1.11.2026): passt «TT.MM. HH:MM» nicht ins Budget, steht nur «TT.MM.»; heute die Uhrzeit', () => {
    expect(kuerzeThemenZeile('', '11.12. 09:00', 11, '11.12.')).toBe('11.12.')
    expect(kuerzeThemenZeile('', '11.12. 09:00', 13, '11.12.')).toBe('11.12. 09:00')
    expect(kuerzeThemenZeile('', '11.12. 09:00', 12, '11.12.')).toBe('11.12. 09:00')
    expect(themaWertKurz(plan(morgen(7, 0)), JETZT)).toBe('02.11.')
    expect(themaWertKurz(plan(heute(9, 0)), JETZT)).toBeUndefined()            // heute: Uhrzeit, keine Notform
    expect(themaWertKurz(eintrag('e', 'x', 'locked'), JETZT)).toBeUndefined()
    expect(themaWertKurz(eintrag('e', 'x', '2027-03-15', { device_class: 'date' }), JETZT)).toBeUndefined()

    const wartung = new Date(2026, 11, 11, 9, 0).toISOString()
    const t = thema(7, 't5', 'Service', [
      eintrag('e6', 'Nächste Wartung', wartung, { device_class: 'timestamp' }),
      eintrag('e7', 'Ladeplan', wartung),
    ])
    const [k] = baueThemenKacheln([t], IONIQ, 'HIMMEL', KATEGORIE_FARBEN.waermepumpe, false, JETZT)
    expect(k.themaTeile?.erste.wertKurz).toBe('11.12.')
    const d6 = themenKachelTexte(k, computeDims(6))   // kompakt: Wert-Budget 11 < 12 ⇒ «11.12.»; zweite Zeile Budget 13
    expect(d6.wertText).toBe('11.12.')
    expect(d6.zweiteZeile?.text).toBe('11.12. 09:00')
    const d3 = themenKachelTexte(k, computeDims(3))   // Budget 13: die Kurzform passt ganz
    expect(d3.wertText).toBe('11.12. 09:00')
    expect(k.tip).toContain('Nächste Wartung: 11.12.2026, 09:00')   // Tooltip voll
    const [heuteK] = baueThemenKacheln([thema(7, 't6', 'Heute', [plan(heute(9, 0))])], IONIQ, 'HIMMEL', KATEGORIE_FARBEN.waermepumpe, false, JETZT)
    expect(themenKachelTexte(heuteK, computeDims(6)).wertText).toBe('09:00')
  })
})

describe('baueThemenKacheln (Bauplan §2.1)', () => {
  it('je Thema eine Kachel: Name, «Label · Wert» erster und zweiter Eintrag, kompakt nur der Wert, Tooltip alle + Stand', () => {
    const [k] = baueThemenKacheln([ZUSTAND], IONIQ, 'HIMMEL', KATEGORIE_FARBEN.eauto, false, JETZT)
    expect([k.id, k.art, k.anker, k.label, k.icon, k.color, k.isActive]).toEqual(
      ['thema-7-t1', 'thema', 'HIMMEL', 'Fahrzeugzustand', 'tags', KATEGORIE_FARBEN.eauto, true])
    expect(k.wertText).toBe('Türen · locked')
    expect(k.wertTextKompakt).toBe('locked')
    expect(k.zweiteZeile).toEqual({ text: 'Reifen vorne links · 259,5 kPa', fill: null })
    expect(k.tip).toBe('Fahrzeugzustand\nTüren: locked\nReifen vorne links: 259,5 kPa\nFenster: closed\nStand 11:27')
    expect([k.investitionId, k.pegel, k.leistungKw]).toEqual([7, undefined, undefined])
    expect(themaZeile(ZUSTAND.eintraege[2], JETZT)).toBe('Fenster · closed')   // dritter Eintrag nur im Tooltip
  })

  it('ein Eintrag ⇒ keine zweite Zeile; kein Zeitpunkt ⇒ kein Stand im Tooltip', () => {
    const [k] = baueThemenKacheln([thema(7, 't2', 'Service', [eintrag('e4', 'Tage bis Service', '41')])], IONIQ, 'HIMMEL', 'f', false, JETZT)
    expect([k.wertText, k.zweiteZeile, k.tip]).toEqual(['Tage bis Service · 41', null, 'Service\nTage bis Service: 41'])
  })

  it('P1: ein Thema ohne Eintrag mit Wert fehlt; P2: fehlt Eintrag 1, zeigt die Kachel 2 und 3', () => {
    // Live liefert nur Einträge mit Wert (TH-E1) — fehlt «Türen», rückt «Reifen» an die erste Stelle.
    const ohneErsten = thema(7, 't1', 'Fahrzeugzustand', ZUSTAND.eintraege.slice(1))
    const leer = thema(7, 't3', 'Komfort', [])
    const ks = baueThemenKacheln([leer, ohneErsten], IONIQ, 'HIMMEL', 'f', false, JETZT)
    expect(ks.map((k) => k.id)).toEqual(['thema-7-t1'])
    expect([ks[0].wertText, ks[0].zweiteZeile?.text]).toEqual(['Reifen vorne links · 259,5 kPa', 'Fenster · closed'])
    expect(themenVon({ themen: [leer, ohneErsten] }, 7).map((t) => t.id)).toEqual(['t1'])
  })

  it('nur die Themen des Geräts; Wärme mit mehreren Geräten: Tooltip-Kopf «‹Gerät› · ‹Thema›»', () => {
    const wp = inv(3, 'waermepumpe', 'WP Keller')
    const fremd = thema(4, 't1', 'Fremd', [eintrag('e1', 'a', '1')])
    const eigen = thema(3, 't1', 'Service', [eintrag('e1', 'Filter', 'ok')])
    const ks = baueThemenKacheln([fremd, eigen], wp, 'HIMMEL', 'f', true, JETZT)
    expect(ks.map((k) => [k.id, k.tip])).toEqual([['thema-3-t1', 'WP Keller · Service\nFilter: ok']])
    expect(baueThemenKacheln(null, wp, 'HIMMEL', 'f')).toEqual([])
  })

  it('Einbau: Wärme am HIMMEL nach der Außentemperatur, Wallbox/Auto am HIMMEL der Szene — je in der Rollenfarbe', () => {
    const wp = inv(3, 'waermepumpe', 'WP Keller')
    const live = { komponenten: [], gauges: [], heute_kwh_pro_komponente: null, themen: [thema(3, 't1', 'Service', [eintrag('e1', 'Filter', 'ok')])] } as unknown as LiveDashboardResponse
    const wetter = { aktuell: { temperatur_c: 4.2 } } as never
    const w = baueUeberblickKacheln({ geraete: [wp], live, wetter, referenz: 'r' }).kacheln
    expect(w.map((k) => k.id).slice(-2)).toEqual(['wert-aussen', 'thema-3-t1'])
    expect(w.at(-1)?.color).toBe(KATEGORIE_FARBEN.waermepumpe)
    const wb = inv(6, 'wallbox', 'go-e')
    const liveWb = { ...live, themen: [thema(6, 't1', 'Plan', [eintrag('e1', 'Start', '07:00')]), thema(7, 't1', 'Zustand', [eintrag('e2', 'Türen', 'locked')])] } as LiveDashboardResponse
    const lp = baueLadepunktKacheln({ inv: wb, geraete: [wb], live: liveWb, tag: null, referenz: 'r' })
    expect(lp.kacheln.filter((k) => k.art === 'thema').map((k) => [k.id, k.anker, k.color])).toEqual([['thema-6-t1', 'HIMMEL', KATEGORIE_FARBEN.wallbox]])
    expect(lp.ohneSensor).not.toContain('Plan')
    const fz = baueFahrzeugKacheln({ inv: IONIQ, geraete: [IONIQ], live: liveWb, tag: null, referenz: 'r' })
    expect(fz.kacheln.filter((k) => k.art === 'thema').map((k) => [k.id, k.anker, k.color])).toEqual([['thema-7-t1', 'HIMMEL', KATEGORIE_FARBEN.eauto]])
  })
})

describe('Kürzung der Zeichnung (Entscheid Master 1.11.2026 zu H1): erst das Label, der Wert bleibt ganz', () => {
  it('«Türen · locked» bei Budget 13 · 12 · 11', () => {
    expect(kuerzeThemenZeile('Türen', 'locked', 14)).toBe('Türen · locked')
    expect(kuerzeThemenZeile('Türen', 'locked', 13)).toBe('Tür… · locked')
    expect(kuerzeThemenZeile('Türen', 'locked', 12)).toBe('locked')   // Label hätte < 3 Zeichen ⇒ Wert allein
    expect(kuerzeThemenZeile('Türen', 'locked', 11)).toBe('locked')
  })

  it('«Reifen vorne links · 259,5 kPa» bei Budget 15 · 13 — und wo das Label gekürzt stehen bleibt', () => {
    expect(kuerzeThemenZeile('Reifen vorne links', '259,5 kPa', 15)).toBe('259,5 kPa')
    expect(kuerzeThemenZeile('Reifen vorne links', '259,5 kPa', 13)).toBe('259,5 kPa')
    expect(kuerzeThemenZeile('Reifen vorne links', '259,5 kPa', 20)).toBe('Reifen… · 259,5 kPa')
    expect(kuerzeThemenZeile('Reifen vorne links', '259,5 kPa', 16)).toBe('Rei… · 259,5 kPa')
  })

  it('passt der Wert allein nicht, wird er am Ende gekürzt; ohne Label nur diese Stufe', () => {
    expect(kuerzeThemenZeile('Status', 'not_charging_waiting', 11)).toBe('not_chargi…')
    expect(kuerzeThemenZeile('', 'locked', 11)).toBe('locked')
    expect(kuerzeThemenZeile('', 'not_charging_waiting', 13)).toBe('not_charging…')
  })

  it('themenKachelTexte: Budget je Dims (Wert kwFontSize, zweite Zeile socFontSize); kompakt der Wert allein', () => {
    const [k] = baueThemenKacheln([ZUSTAND], IONIQ, 'HIMMEL', 'f', false, JETZT)
    const d3 = themenKachelTexte(k, computeDims(3))   // Budget Wert 13, zweite Zeile 15
    expect([d3.wertText, d3.zweiteZeile]).toEqual(['Tür… · locked', { text: '259,5 kPa', fill: null }])
    const d4 = themenKachelTexte(k, computeDims(4))   // 12 / 13
    expect([d4.wertText, d4.zweiteZeile?.text]).toEqual(['locked', '259,5 kPa'])
    const d5 = themenKachelTexte(k, computeDims(5))   // kompakt: 11 / 13
    expect([d5.wertText, d5.zweiteZeile?.text]).toEqual(['locked', '259,5 kPa'])
    // Andere Kacheln: unverändert (kein `themaTeile`).
    const wert = { wertText: '33,9 → 28,8 °C', wertTextKompakt: '34 → 29 °C', zweiteZeile: null }
    expect(themenKachelTexte(wert, computeDims(5))).toEqual({ wertText: '34 → 29 °C', zweiteZeile: null })
  })
})
