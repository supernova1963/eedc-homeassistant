/**
 * «Auf einen Blick» E-Mobilität — K2a «Fahrzeug am Ladepunkt, Gast, Zuordnung» (P-433-2b, Bauplan K2 §3 E4, §5 K2a;
 * Entscheide D1/D2). Schwesterdatei: `UeberblickKarteEmob.test.tsx` (K1).
 *
 * Fälle: Treffer der Steuerung (nur dieses Auto, Tooltip «gemeldet von der Steuerung», Dienstwagen-Zeile), K1-Zeile
 * ohne Steuerung unverändert, Gast «lädt»/«verbunden» ohne Leiste und ohne eigene Farbe, «Fahrzeug der Steuerung
 * unbekannt» mit Fußzeile (D2: kein Name), W4 «alle Autos» nur aus «geschätzt»-Wallboxen, Auto-Karte: Ort an der
 * Treffer-Wallbox, ohne Ort und mit eigenem Chip, wenn ein Gast die einzige Wallbox belegt.
 */
import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import UeberblickKarteEmob, {
  FAHRZEUG_UNBEKANNT, FUSSZEILE_UNBEKANNT, GAST_LAEDT, GAST_VERBUNDEN, TOOLTIP_STEUERUNG, alleAutosAnWallboxen,
} from './UeberblickKarteEmob'
import { SATZ_ZUORDNUNG_UNBEKANNT } from '../../live/EnergieFluss'
import type { LiveDashboardResponse, LiveFahrzeug, LiveKomponente } from '../../../api/liveDashboard'
import type { Investition } from '../../../types'

const inv = (id: number, typ: string, bez: string): Investition =>
  ({ id, anlage_id: 1, typ, bezeichnung: bez, aktiv: true, parameter: {} } as Investition)
const wb = (id: number, extra: Partial<LiveKomponente> = {}): LiveKomponente =>
  ({ key: `wallbox_${id}`, label: `WB ${id}`, icon: 'plug', erzeugung_kw: null, verbrauch_kw: 7.4, typ: 'wallbox', ...extra })
const fz = (id: number, label: string, extra: Partial<LiveFahrzeug> = {}): LiveFahrzeug =>
  ({ investition_id: id, label, soc: null, kw: null, v2h: false, ...extra })
const live = (extra: Partial<LiveDashboardResponse> = {}): LiveDashboardResponse => ({
  anlage_id: 1, anlage_name: 'Test', zeitpunkt: '', verfuegbar: true,
  komponenten: [], summe_erzeugung_kw: 0, summe_verbrauch_kw: 0, summe_pv_kw: 0, gauges: [],
  heute_pv_kwh: null, heute_einspeisung_kwh: null, heute_netzbezug_kwh: null, heute_eigenverbrauch_kwh: null,
  gestern_pv_kwh: null, gestern_einspeisung_kwh: null, gestern_netzbezug_kwh: null, gestern_eigenverbrauch_kwh: null,
  heute_kwh_pro_komponente: null, warmwasser_temperatur_c: null, innengeraete: null,
  ...extra,
})
const zeichne = (i: Investition, l: LiveDashboardResponse | null) =>
  render(<UeberblickKarteEmob inv={i} live={l} tag={null} mehrereGeraete />).container
const fahrzeugZeilen = (c: HTMLElement) => [...c.querySelectorAll('[data-zeile="fahrzeug"]')] as HTMLElement[]

const GARAGE = inv(4, 'wallbox', 'Garage')
const CARPORT = inv(6, 'wallbox', 'Carport')
const IONIQ = inv(9, 'e-auto', 'Ioniq')
const ZOE = inv(8, 'e-auto', 'Zoe')

/** Zwei Wallboxen: die Garage meldet den Ioniq (Treffer), der Carport ist die einzige Rest-Wallbox (D1) mit der Zoe. */
const trefferLive = (ioniq: Partial<LiveFahrzeug> = {}) => live({ komponenten: [
  wb(4, { label: 'Garage', ladezustand: 'laedt', ladezustand_label: 'Lädt', fahrzeuge_zuordnung: 'eindeutig',
    fahrzeuge_quelle: 'steuerung', fahrzeuge: [fz(9, 'Ioniq', { soc: 55, ...ioniq })] }),
  wb(6, { label: 'Carport', fahrzeuge_zuordnung: 'eindeutig', fahrzeuge: [fz(8, 'Zoe', { soc: 20 })] }),
] })

describe('UeberblickKarteEmob K2a — Wallbox', () => {
  it('Treffer: nur das gemeldete Auto, Tooltip «gemeldet von der Steuerung», kein Satz «weiß eedc noch nicht»', () => {
    const c = zeichne(GARAGE, trefferLive())
    const z = fahrzeugZeilen(c)
    expect(z.map((x) => x.textContent)).toEqual(['Ioniq · 55 %'])
    expect(z[0].getAttribute('title')).toBe(TOOLTIP_STEUERUNG)
    expect(c.textContent).not.toContain('Zoe')
    expect(c.textContent).not.toContain(SATZ_ZUORDNUNG_UNBEKANNT)
    expect(c.querySelector('[data-ladestand-fuellung]')).not.toBeNull()
  })

  it('D1: die einzige Rest-Wallbox nennt ihr Auto «eindeutig», ohne Tooltip der Steuerung', () => {
    const c = zeichne(CARPORT, trefferLive())
    const z = fahrzeugZeilen(c)
    expect(z.map((x) => x.textContent)).toEqual(['Zoe · 20 %'])
    expect(z[0].getAttribute('title')).toBeNull()
    expect(c.textContent).not.toContain('Ioniq')
  })

  it('Dienstwagen: «Dienstwagen ‹Name›» nur, wenn die Steuerung das Auto meldet', () => {
    expect(fahrzeugZeilen(zeichne(GARAGE, trefferLive({ dienstwagen: true })))[0].textContent).toBe('Dienstwagen Ioniq · 55 %')
    const ohneSteuerung = live({ komponenten: [wb(4, { fahrzeuge_zuordnung: 'eindeutig',
      fahrzeuge: [fz(9, 'Ioniq', { soc: 55, dienstwagen: true })] })] })
    expect(fahrzeugZeilen(zeichne(GARAGE, ohneSteuerung))[0].textContent).toBe('Ioniq · 55 %')
  })

  it('Gast: «Gastfahrzeug lädt» bzw. «verbunden», keine Leiste, keine eigene Farbe', () => {
    const gast = (zustand: string, label: string) => live({ komponenten: [wb(4, {
      ladezustand: zustand, ladezustand_label: label, fahrzeuge_zuordnung: 'eindeutig', fahrzeuge_quelle: 'steuerung',
      gast: true, fahrzeuge: [] })], fahrzeuge_ohne_wallbox: [fz(8, 'Zoe', { soc: 40 })] })
    const c = zeichne(GARAGE, gast('laedt', 'Lädt'))
    const z = fahrzeugZeilen(c)
    expect(z.map((x) => x.textContent)).toEqual([GAST_LAEDT])
    expect(z[0].getAttribute('title')).toBe(TOOLTIP_STEUERUNG)
    expect(z[0].className).toBe('text-sm text-gray-700 dark:text-gray-300')
    expect(c.querySelector('[data-ladestand-fuellung]')).toBeNull()
    expect(c.textContent).not.toContain('Zoe')
    for (const [zustand, label] of [['verbunden', 'Verbunden'], ['wartet', 'Wartet'], ['fertig', 'Fertig']]) {
      expect(fahrzeugZeilen(zeichne(GARAGE, gast(zustand, label))).map((x) => x.textContent)).toEqual([GAST_VERBUNDEN])
    }
  })

  it('unbekannt (D2): «Fahrzeug der Steuerung unbekannt» mit Fußzeile — kein Name, kein Auto', () => {
    const c = zeichne(GARAGE, live({ komponenten: [wb(4, { fahrzeuge_zuordnung: 'eindeutig', fahrzeuge_quelle: 'steuerung',
      fahrzeug_unbekannt: true, fahrzeuge: [] })], fahrzeuge_ohne_wallbox: [fz(8, 'Zoe', { soc: 40 })] }))
    expect(fahrzeugZeilen(c).map((x) => x.textContent)).toEqual([FAHRZEUG_UNBEKANNT])
    expect(c.querySelector('[data-fusszeile]')?.textContent).toBe(FUSSZEILE_UNBEKANNT)
    expect(c.textContent).not.toContain('Zoe')
  })

  it('W4: bei «geschätzt» nennt die Karte nur die Autos der «geschätzt»-Wallboxen, nicht das gemeldete', () => {
    const l = live({ komponenten: [
      wb(4, { fahrzeuge_zuordnung: 'eindeutig', fahrzeuge_quelle: 'steuerung', fahrzeuge: [fz(9, 'Ioniq', { soc: 55 })] }),
      wb(6, { fahrzeuge_zuordnung: 'geschaetzt', fahrzeuge: [fz(8, 'Zoe', { soc: 20 })] }),
      wb(7, { fahrzeuge_zuordnung: 'geschaetzt', fahrzeuge: [fz(10, 'ID3', { soc: 70 })] }),
    ] })
    expect(alleAutosAnWallboxen(l).map((f) => f.label)).toEqual(['Zoe', 'ID3'])
    const c = zeichne(CARPORT, l)
    expect(fahrzeugZeilen(c).map((x) => x.textContent)).toEqual(['Zoe · 20 %', 'ID3 · 70 %'])
    expect(c.textContent).toContain(SATZ_ZUORDNUNG_UNBEKANNT)
  })
})

describe('UeberblickKarteEmob K2a — E-Auto', () => {
  it('am Treffer: Ort «an ‹Wallbox›», kein eigener Chip (Leitsatz 8)', () => {
    const c = zeichne(IONIQ, trefferLive({ ladezustand: 'laedt', ladezustand_label: 'Lädt' }))
    expect(c.querySelector('[data-zeile="ort"]')?.textContent).toContain('an Garage')
    expect(c.querySelector('[data-modus-chip]')).toBeNull()
  })

  it('Gast belegt die einzige Wallbox: das Auto hat keinen Ort, trägt seinen eigenen Chip', () => {
    const l = live({ komponenten: [wb(4, { fahrzeuge_zuordnung: 'eindeutig', fahrzeuge_quelle: 'steuerung', gast: true,
      fahrzeuge: [] })], fahrzeuge_ohne_wallbox: [fz(8, 'Zoe', { soc: 40, ladezustand: 'nicht_verbunden',
      ladezustand_label: 'Nicht verbunden' })] })
    const c = zeichne(ZOE, l)
    expect(c.querySelector('[data-zeile="ort"]')).toBeNull()
    expect(c.querySelector('[data-modus-chip="nicht_verbunden"]')?.textContent).toBe('Nicht verbunden')
  })
})
