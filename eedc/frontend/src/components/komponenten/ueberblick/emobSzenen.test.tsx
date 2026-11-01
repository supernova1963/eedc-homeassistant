/**
 * Fall-Proben der zwei Szenen der E-Mobilität (P-433-2b S1b E4, Bauplan Fassung 2 §3 gekürzt um §9) und die
 * Selektor-Proben (§9 neu): die Szene gehört dem gewählten Gerät — ein Wechsel im Selektor wechselt die Kacheln mit.
 * Die Fälle laufen gegen die Kachel-Bauer (`emobKachelAnker.ts`) und — wo Bild, Pegel oder Zeile zählen — gegen das
 * gerenderte Schaubild mit dem Deskriptor der Szene (Ist-Anker, gemessen am Bild 1.11.2026).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render } from '@testing-library/react'
import type { ReactElement } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { ThemeProvider } from '../../../context/ThemeContext'
import type { LiveDashboardResponse, LiveFahrzeug, LiveKomponente } from '../../../api/liveDashboard'
import type { EmobHeuteZeile, TagDetail } from '../../../api/energie_profil'
import type { Investition } from '../../../types'
import { KATEGORIE_FARBEN } from '../../../lib'
import { SATZ_ZUORDNUNG_UNBEKANNT, formatPower, socColor } from '../../live/EnergieFluss'
import { renderMitProvidern, stubMatchMedia } from '../../../test/render'
import { baueFahrzeugKacheln, baueLadepunktKacheln, fahrzeugZustandZeile } from './emobKachelAnker'
import { FAHRZEUG_PANORAMA_DEF, LADEPUNKT_PANORAMA_DEF } from './emobPanoramaAnker'
import { LADUNG_TAG_TOOLTIP, LADUNG_TOOLTIP } from './UeberblickKarteEmob'
import { layoutUeberblick } from './ueberblickLayout'
import UeberblickSchaubild from './UeberblickSchaubild'
import type { UeberblickKachel } from './kachelAnker'

const REF = 'referenz'   // Referenzfarbe des Themas — ein Platzhalter wie in den Wärme-Proben
const inv = (id: number, typ: string, bez: string): Investition =>
  ({ id, anlage_id: 1, typ, bezeichnung: bez, aktiv: true, parameter: {} } as Investition)
const GO_E = inv(6, 'wallbox', 'go-eCharger')
const CARPORT = inv(7, 'wallbox', 'Carport')
const ID4 = inv(8, 'e-auto', 'ID.4')
const ZOE = inv(9, 'e-auto', 'Zoe')
const SMART = inv(5, 'e-auto', 'Smart #1')
const ECHARGER = inv(4, 'wallbox', 'SMA eCharger 22')

const auto = (id: number, label: string, extra: Partial<LiveFahrzeug> = {}): LiveFahrzeug =>
  ({ investition_id: id, label, soc: null, kw: null, v2h: false, ...extra })
const wallbox = (id: number, label: string, extra: Partial<LiveKomponente> = {}): LiveKomponente =>
  ({ key: `wallbox_${id}`, label, icon: 'plug', erzeugung_kw: null, verbrauch_kw: null, typ: 'wallbox', ...extra })
const live = (komponenten: LiveKomponente[], extra: Partial<LiveDashboardResponse> = {}): LiveDashboardResponse =>
  ({ komponenten, gauges: [], heute_kwh_pro_komponente: null, ...extra } as unknown as LiveDashboardResponse)
const tag = (zeilen: EmobHeuteZeile[]) => ({ emob_heute: zeilen, emob_betrieb: [] } as unknown as TagDetail)

/** Demo: go-eCharger mit ID.4 (von der Steuerung gemeldet, lädt), Carport mit Zoe (einzige Wallbox ohne Aussage). */
const DEMO = live([
  wallbox(6, 'go-eCharger', {
    verbrauch_kw: 7.4, ladezustand: 'laedt', ladezustand_label: 'Lädt', lademodus_label: 'PV',
    fahrzeuge: [auto(8, 'ID.4', { soc: 52, kw: 7.4 })], fahrzeuge_zuordnung: 'eindeutig', fahrzeuge_quelle: 'steuerung',
    sitzung: { kwh: 9.8, dauer_s: 7800 }, phasen_aktiv: 3, ladestrom_a: 16,
  }),
  wallbox(7, 'Carport', {
    verbrauch_kw: 0, ladezustand: 'verbunden', ladezustand_label: 'Verbunden',
    fahrzeuge: [auto(9, 'Zoe', { soc: 81, kw: 0 })], fahrzeuge_zuordnung: 'eindeutig',
  }),
], { heute_kwh_pro_komponente: { wallbox_6: 3.3, wallbox_7: 1.2, wallbox: 4.5 } })

const lp = (i: Investition, l: LiveDashboardResponse | null, t: TagDetail | null = null, geraete = [GO_E, CARPORT]) =>
  baueLadepunktKacheln({ inv: i, geraete, live: l, tag: t, referenz: REF })
const fz = (i: Investition, l: LiveDashboardResponse | null, t: TagDetail | null = null) =>
  baueFahrzeugKacheln({ inv: i, geraete: [i], live: l, tag: t, referenz: REF })
const an = (ks: UeberblickKachel[], anker: string) => ks.filter((k) => k.anker === anker)
const eine = (ks: UeberblickKachel[], anker: string) => {
  const treffer = an(ks, anker)
  expect(treffer, `Anker ${anker}`).toHaveLength(1)
  return treffer[0]
}

beforeEach(() => { stubMatchMedia() })

describe('Szene «Ladepunkt» — Fall-Proben (§3, gekürzt um §9)', () => {
  it('Demo go-eCharger: A links «7.400 W» + Auto-Zeile «ID.4 52 %», Z mit Rückfall-Tageswert, S «9,8 kWh · 2 h 10 min», F «ID.4 52 %» mit Pegel', () => {
    const { kacheln, ohneSensor } = lp(GO_E, DEMO)
    expect(ohneSensor).toEqual([])
    const a = eine(kacheln, 'A')
    expect([a.art, a.label, a.wertText, a.isActive]).toEqual(['geraet', 'go-eCharger', formatPower(7.4), true])
    expect(a.zweiteZeile).toEqual({ text: 'ID.4 52 %', fill: socColor(52) })   // «Lädt» ⇒ kein Chip, die Auto-Zeile
    expect(a.color).toBe(KATEGORIE_FARBEN.wallbox)
    expect(a.tip).toContain('Zustand: Lädt · PV')
    expect(a.tip).toContain('Auto ID.4: 52 %, lädt 7,40 kW')
    const z = eine(kacheln, 'Z')
    expect([z.wertText, z.zweiteZeile, z.tip.includes(LADUNG_TOOLTIP)]).toEqual(['3,3 kWh', null, true])
    const s = eine(kacheln, 'S')
    expect([s.label, s.wertText, s.zweiteZeile?.text]).toEqual(['Sitzung', '9,8 kWh', '2 h 10 min'])
    expect(s.tip).toContain('3 Phasen · 16 A · 9,8 kWh in dieser Sitzung · 2 h 10 min')
    const f = eine(kacheln, 'F')
    expect([f.art, f.label, f.wertText, f.zweiteZeile?.text, f.color]).toEqual(['wert', 'ID.4', '52 %', `lädt ${formatPower(7.4)}`, KATEGORIE_FARBEN.eauto])
    expect(f.pegel).toEqual({ prozent: 52, fill: socColor(52), opacity: 0.3 })
    expect(f.tip).toContain('gemeldet von der Steuerung')
    // Desktop: A im Platz links, rechts kein Platz (§9).
    const l = layoutUeberblick(kacheln, 1150, LADEPUNKT_PANORAMA_DEF)
    expect(l.links?.key).toBe(a.id)
    expect(l.rechts).toBeNull()
  })

  it('Ziel der Steuerung ⇒ F zweite Zeile «Ziel 80 %» (vor der Richtung)', () => {
    const l = live([wallbox(6, 'go-eCharger', {
      verbrauch_kw: 7.4, fahrzeuge: [auto(8, 'ID.4', { soc: 52, kw: 7.4 })], fahrzeuge_zuordnung: 'eindeutig', ziel_prozent: 80,
    })])
    expect(eine(lp(GO_E, l).kacheln, 'F').zweiteZeile?.text).toBe('Ziel 80 %')
  })

  it('«geschätzt» ⇒ kein F; der A-Tooltip nennt alle Autos und den Satz', () => {
    const l = live([
      wallbox(6, 'go-eCharger', { verbrauch_kw: 7.4, fahrzeuge: [auto(8, 'ID.4', { soc: 52 })], fahrzeuge_zuordnung: 'geschaetzt' }),
      wallbox(7, 'Carport', { fahrzeuge: [auto(9, 'Zoe', { soc: 81 })], fahrzeuge_zuordnung: 'geschaetzt' }),
    ])
    const { kacheln } = lp(GO_E, l)
    expect(an(kacheln, 'F')).toEqual([])
    const a = eine(kacheln, 'A')
    expect(a.zweiteZeile).toBeNull()   // keine Auto-Zeile bei «geschätzt» (Ü3)
    expect(a.tip).toContain(SATZ_ZUORDNUNG_UNBEKANNT)
    expect(a.tip).toContain('• ID.4: 52 %')
    expect(a.tip).toContain('• Zoe: 81 %')
  })

  it('Gast ⇒ kein F; A-Tooltip «Gastfahrzeug lädt», Zeile «Lädt» wird der Chip nicht', () => {
    const l = live([wallbox(6, 'go-eCharger', {
      verbrauch_kw: 11, ladezustand: 'laedt', ladezustand_label: 'Lädt', fahrzeuge: [], fahrzeuge_zuordnung: 'eindeutig',
      fahrzeuge_quelle: 'steuerung', gast: true,
    })])
    const { kacheln } = lp(GO_E, l)
    expect(an(kacheln, 'F')).toEqual([])
    expect(eine(kacheln, 'A').tip).toContain('Gastfahrzeug lädt')
  })

  it('`kein_fahrzeug` + Sitzung ⇒ S «12,4 kWh · letzte Sitzung», A-Chip «Kein Fahrzeug» gedämpft', () => {
    const l = live([wallbox(6, 'go-eCharger', {
      verbrauch_kw: 0, ladezustand: 'kein_fahrzeug', ladezustand_label: 'Kein Fahrzeug', sitzung: { kwh: 12.4, dauer_s: 3600 },
      fahrzeuge: [], fahrzeuge_zuordnung: 'eindeutig',
    })])
    const { kacheln } = lp(GO_E, l)
    const s = eine(kacheln, 'S')
    expect([s.wertText, s.zweiteZeile?.text]).toEqual(['12,4 kWh', 'letzte Sitzung'])
    expect(s.tip).toContain('letzte Sitzung 12,4 kWh')
    const a = eine(kacheln, 'A')
    expect(a.zweiteZeile?.text).toBe('Kein Fahrzeug')
    expect(a.zweiteZeile?.chip?.gedaempft).toBe(true)
    expect(a.isActive).toBe(false)
  })

  it('Sitzung ohne kWh ⇒ keine S-Kachel und kein Eintrag in der Zeile (Zusatzfeld, G7)', () => {
    const l = live([wallbox(6, 'go-eCharger', { verbrauch_kw: 1, sitzung: { kwh: null, dauer_s: 60 } })], { heute_kwh_pro_komponente: { wallbox_6: 1 } })
    const { kacheln, ohneSensor } = lp(GO_E, l)
    expect(an(kacheln, 'S')).toEqual([])
    expect(ohneSensor).toEqual([])
  })

  it('Wallbox ohne Knoten ⇒ Zeile «Leistung ‹Wallbox›»; Z nach Datenlage (Tag-Detail), kein S, kein F', () => {
    const { kacheln, ohneSensor } = lp(GO_E, live([]), tag([{ investition_id: 6, typ: 'wallbox', ladung_kwh: 14.7 }]))
    expect(ohneSensor).toEqual(['Leistung go-eCharger'])
    expect(kacheln.map((k) => k.anker)).toEqual(['Z'])
    expect(eine(kacheln, 'Z').tip).toContain(LADUNG_TAG_TOOLTIP)
  })

  it('PV-Anteil nur mit `pv_anteil_prozent`: Z zweite Zeile «PV-Anteil 67 %»; ohne Anteil keine zweite Zeile, auch wenn beide Mengen da sind', () => {
    const mit = lp(GO_E, DEMO, tag([{ investition_id: 6, typ: 'wallbox', ladung_kwh: 14.7, ladung_pv_kwh: 9.8, pv_anteil_prozent: 67 }]))
    const z = eine(mit.kacheln, 'Z')
    expect([z.wertText, z.zweiteZeile?.text]).toEqual(['14,7 kWh', 'PV-Anteil 67 %'])
    expect(z.tip).toContain('PV-Anteil heute: 67 % (9,8 kWh PV ÷ 14,7 kWh)')
    expect(z.tip).toContain(LADUNG_TAG_TOOLTIP)
    // Der Client teilt nicht: 9,8 ÷ 14,7 wären 67 % — ohne Backend-Zahl steht keine.
    const ohne = lp(GO_E, DEMO, tag([{ investition_id: 6, typ: 'wallbox', ladung_kwh: 14.7, ladung_pv_kwh: 9.8, pv_anteil_prozent: null }]))
    expect(eine(ohne.kacheln, 'Z').zweiteZeile).toBeNull()
    // Die Backend-Zahl gilt, auch wenn der Quotient eine andere wäre.
    const backend = lp(GO_E, DEMO, tag([{ investition_id: 6, typ: 'wallbox', ladung_kwh: 14.7, ladung_pv_kwh: 9.8, pv_anteil_prozent: 50 }]))
    expect(eine(backend.kacheln, 'Z').zweiteZeile?.text).toBe('PV-Anteil 50 %')
  })

  it('Tageswert-Regel: mehrere Wallboxen ⇒ nur der exakte Key; eine Wallbox ⇒ auch der Typ-Key', () => {
    const l = live([wallbox(6, 'go-eCharger', { verbrauch_kw: 1 })], { heute_kwh_pro_komponente: { wallbox: 4.5 } })
    expect(an(lp(GO_E, l).kacheln, 'Z')).toEqual([])
    expect(lp(GO_E, l).ohneSensor).toEqual(['Ladung heute go-eCharger'])
    expect(eine(lp(GO_E, l, null, [GO_E]).kacheln, 'Z').wertText).toBe('4,5 kWh')
  })

  it('Lab heute (eCharger ohne Knoten, Smart mit SoC an keiner Wallbox) ⇒ Zeile «Leistung …» und «Ladung heute …», kein F', () => {
    const l = live([], { fahrzeuge_ohne_wallbox: [auto(5, 'Smart #1', { soc: 62 })] })
    const { kacheln, ohneSensor } = lp(ECHARGER, l, null, [ECHARGER])
    expect(kacheln).toEqual([])
    expect(ohneSensor).toEqual(['Leistung SMA eCharger 22', 'Ladung heute SMA eCharger 22'])
  })

  it('mehrere eindeutige Autos: das erste nach ID ist F (Wert-Kachel, einzeln), der Rest Gerätekacheln an F ⇒ «E-Autos (2)»', () => {
    const l = live([wallbox(6, 'go-eCharger', {
      verbrauch_kw: 0, fahrzeuge_zuordnung: 'eindeutig',
      fahrzeuge: [auto(12, 'Kona', { soc: 40 }), auto(8, 'ID.4', { soc: 52 }), auto(9, 'Zoe', { soc: 81 }), auto(13, 'ohne SoC')],
    })])
    const f = an(lp(GO_E, l).kacheln, 'F')
    expect(f.map((k) => [k.label, k.art])).toEqual([['ID.4', 'wert'], ['Zoe', 'geraet'], ['Kona', 'geraet']])
    for (const ctr of [1150, 390]) {
      const lay = layoutUeberblick(lp(GO_E, l).kacheln, ctr, LADEPUNKT_PANORAMA_DEF)
      const gruppe = lay.unten.find((p) => p.gruppe === 'geraete')!
      expect(gruppe.anker, `${ctr}`).toBe('F')
      expect(LADEPUNKT_PANORAMA_DEF.gruppenName(gruppe.gruppe!, gruppe.anker)).toBe('E-Autos')
      expect(gruppe.mitglieder.map((m) => m.label), `${ctr}`).toEqual(['Zoe', 'Kona'])
      expect(lay.unten.some((p) => p.key === 'fahrzeug-8'), `${ctr}`).toBe(true)
    }
  })

  it('vor der ersten Live-Antwort: keine Kachel aus dem Live-Pfad und keine Zeile', () => {
    expect(lp(GO_E, null)).toEqual({ kacheln: [], ohneSensor: [] })
  })
})

describe('Szene «Fahrzeug» — Fall-Proben (§3, gekürzt um §9)', () => {
  const SMART_LIVE = (f: Partial<LiveFahrzeug> = {}, wb: Partial<LiveKomponente> = {}) => live([wallbox(4, 'SMA eCharger 22', {
    verbrauch_kw: 11, fahrzeuge_zuordnung: 'eindeutig',
    fahrzeuge: [auto(5, 'Smart #1', {
      soc: 62, kw: 11, ladezustand: 'laedt', ladezustand_label: 'Lädt', ziel_prozent: 90, restzeit_min: 80,
      reichweite_km: 312, km_stand: 23044, zu_hause: true, ...f,
    })], ...wb,
  })])
  const FAHRT = tag([{ investition_id: 5, typ: 'e-auto', km: 42, fahrverbrauch_kwh: 7.8 }])

  it('Smart an eCharger: L «11,0 kW» + Chip «Lädt», B «62 %» Pegel + Ziel, C Reichweite + Stand, R Gefahren + kWh, H «Zu Hause»', () => {
    const { kacheln, ohneSensor } = fz(SMART, SMART_LIVE(), FAHRT)
    expect(ohneSensor).toEqual([])
    const l = eine(kacheln, 'L')
    expect([l.art, l.label, l.wertText, l.isActive, l.color]).toEqual(['geraet', 'Laden', '11,0 kW', true, KATEGORIE_FARBEN.eauto])
    expect(l.zweiteZeile?.text).toBe('Lädt')
    expect(l.zweiteZeile?.chip?.gedaempft).toBe(false)
    expect(l.tip).toContain('an SMA eCharger 22')
    const b = eine(kacheln, 'B')
    expect([b.wertText, b.zweiteZeile?.text]).toEqual(['62 %', '90 % · noch 1 h 20 min'])
    expect(b.pegel).toEqual({ prozent: 62, fill: socColor(62), opacity: 0.3 })
    const c = eine(kacheln, 'C')
    expect([c.label, c.wertText, c.zweiteZeile?.text]).toEqual(['Reichweite', '312 km', 'Stand 23.044 km'])
    const r = eine(kacheln, 'R')
    expect([r.label, r.wertText, r.zweiteZeile?.text]).toEqual(['Gefahren heute', '42 km', '7,8 kWh'])
    const h = eine(kacheln, 'H')
    expect([h.label, h.wertText]).toEqual(['Standort', 'Zu Hause'])
    expect(an(kacheln, 'HIMMEL')).toEqual([])   // Reserve, keine Kachel (E-2b-28)
    const lay = layoutUeberblick(kacheln, 1150, FAHRZEUG_PANORAMA_DEF)
    expect(lay.links?.key).toBe(l.id)
    expect(lay.rechts).toBeNull()
  })

  it('Zoe nur SoC (Gauge, an keiner Wallbox) ⇒ nur B', () => {
    const l = live([], { gauges: [{ key: 'soc_9', label: 'Zoe', wert: 45, min_wert: 0, max_wert: 100, einheit: '%' }] })
    const { kacheln, ohneSensor } = fz(ZOE, l)
    expect(kacheln.map((k) => [k.anker, k.wertText])).toEqual([['B', '45 %']])
    expect(ohneSensor).toEqual([])
  })

  it('Anlage ohne Wallbox: L zeigt den Zustand als Text («Lädt DC»), Tooltip «ohne Wallbox»; ohne Leistung keine zweite Zeile', () => {
    const l = live([], { fahrzeuge_ohne_wallbox: [auto(8, 'ID.4', { soc: 70, ladezustand: 'laedt_dc', ladezustand_label: 'Lädt DC' })] })
    const lk = eine(fz(ID4, l).kacheln, 'L')
    expect([lk.wertText, lk.zweiteZeile, lk.isActive]).toEqual(['Lädt DC', null, false])
    expect(lk.tip).toContain('ohne Wallbox')
  })

  it('V2H `kw < 0` ⇒ L «3.000 W» (Betrag, `formatPower`) + «entlädt (V2H)»', () => {
    const lk = eine(fz(SMART, SMART_LIVE({ kw: -3, ladezustand: 'verbunden', ladezustand_label: 'Verbunden' })).kacheln, 'L')
    expect([lk.wertText, lk.zweiteZeile?.text]).toEqual([formatPower(3), 'entlädt (V2H)'])
    expect(lk.tip).toContain('entlädt, V2H')
  })

  it('`zu_hause` false ⇒ H «Unterwegs»; L ohne Leistung und ohne Zustand fehlt (kein Zeilen-Eintrag)', () => {
    const { kacheln, ohneSensor } = fz(SMART, live([], { fahrzeuge_ohne_wallbox: [auto(5, 'Smart #1', { soc: 30, zu_hause: false })] }))
    expect(eine(kacheln, 'H').wertText).toBe('Unterwegs')
    expect(an(kacheln, 'L')).toEqual([])
    expect(ohneSensor).toEqual([])
  })

  it('nur Kilometerstand ⇒ C «Kilometerstand»; nur Fahrverbrauch ⇒ R «Fahrverbrauch heute»', () => {
    const { kacheln } = fz(SMART, SMART_LIVE({ reichweite_km: null }), tag([{ investition_id: 5, typ: 'e-auto', km: null, fahrverbrauch_kwh: 7.8 }]))
    const c = eine(kacheln, 'C')
    expect([c.label, c.wertText, c.zweiteZeile]).toEqual(['Kilometerstand', '23.044 km', null])
    const r = eine(kacheln, 'R')
    expect([r.label, r.wertText, r.zweiteZeile]).toEqual(['Fahrverbrauch heute', '7,8 kWh', null])
  })

  it('«geschätzt» ⇒ L ohne «an ‹Wallbox›» (eedc rät nicht)', () => {
    const lk = eine(fz(SMART, SMART_LIVE({}, { fahrzeuge_zuordnung: 'geschaetzt' })).kacheln, 'L')
    expect(lk.tip).not.toContain('an SMA eCharger 22')
  })

  it('Auto ohne jeden Wert ⇒ Zeile «Ladestand ‹Auto›», keine Kachel', () => {
    expect(fz(ZOE, live([]))).toEqual({ kacheln: [], ohneSensor: ['Ladestand Zoe'] })
  })

  it('Zustands-Chip des Fahrzeugs: Form von `ladezustandZeile`, auch bei «Lädt»; Ruhe gedämpft; ohne Zustand keiner', () => {
    expect(fahrzeugZustandZeile({ ladezustand: 'laedt', ladezustand_label: 'Lädt' }, REF)?.chip?.gedaempft).toBe(false)
    expect(fahrzeugZustandZeile({ ladezustand: 'nicht_verbunden', ladezustand_label: 'Nicht verbunden' }, REF))
      .toMatchObject({ text: 'Nicht verbunden', fill: REF, chip: { gedaempft: true } })
    expect(fahrzeugZustandZeile({ ladezustand: null, ladezustand_label: null }, REF)).toBeNull()
  })
})

describe('Schaubild der Szenen (gerendert): Bild, Pegel, Zeile', () => {
  it('Ladepunkt: aria «Schaubild Ladepunkt», beide Bilder, F mit Pegel, A im Platz links', () => {
    const { kacheln, ohneSensor } = lp(GO_E, DEMO)
    const c = renderMitProvidern(<UeberblickSchaubild kacheln={kacheln} ohneSensor={ohneSensor} panorama={LADEPUNKT_PANORAMA_DEF} />).container
    expect(c.querySelector('svg')?.getAttribute('aria-label')).toBe('Schaubild Ladepunkt')
    expect(c.querySelector('[data-panorama="tag"]')?.getAttribute('href')).toBe('./backgrounds/emob-ladepunkt-tag.webp')
    expect(c.querySelector('[data-panorama="nacht"]')?.getAttribute('href')).toBe('./backgrounds/emob-ladepunkt-nacht.webp')
    expect(c.querySelector('[data-platz="fahrzeug-8"]')?.textContent).toContain('52 %')
    expect(c.querySelector('[data-ohne-sensor]')).toBeNull()
  })

  it('Fahrzeug ohne Ladestand: Zeile «Ohne Sensor, deshalb ohne Kachel: Ladestand Zoe → Datenquellen zuordnen»', () => {
    const { kacheln, ohneSensor } = fz(ZOE, live([]))
    const c = renderMitProvidern(<UeberblickSchaubild kacheln={kacheln} ohneSensor={ohneSensor} panorama={FAHRZEUG_PANORAMA_DEF} />).container
    expect(c.querySelector('svg')?.getAttribute('aria-label')).toBe('Schaubild Fahrzeug')
    expect(c.querySelector('[data-ohne-sensor]')?.textContent).toContain('Ladestand Zoe')
  })
})

// ── Selektor-Proben (§9 neu): die Szene gehört dem gewählten Gerät ─────────────

const liveMock = vi.hoisted(() => ({ wert: { live: null as LiveDashboardResponse | null, wetter: null, tag: null as TagDetail | null } }))
vi.mock('./useLiveUeberblick', () => ({ useLiveUeberblick: () => liveMock.wert }))
const { UeberblickBlockEmob } = await import('./UeberblickBlock')

/** Derselbe Provider-Turm wie `renderMitProvidern` — hier mit `rerender` für den Selektor-Wechsel. */
const rahmen = (ui: ReactElement) => <MemoryRouter><ThemeProvider>{ui}</ThemeProvider></MemoryRouter>
const kachelTexte = () => [...document.querySelectorAll('[data-ueberblick-schaubild] [data-platz]')].map((g) => g.getAttribute('data-platz'))

describe('Selektor-Proben (§9): ein Wechsel des Geräts wechselt die Kacheln der Szene', () => {
  it('Wallbox: go-eCharger ⇒ A/Z/S/F des go-eChargers; Carport gewählt ⇒ A Carport, F Zoe — Karte wechselt mit', () => {
    liveMock.wert = { live: DEMO, wetter: null, tag: null }
    const { rerender } = render(rahmen(<UeberblickBlockEmob anlageId={1} geraete={[GO_E, CARPORT]} inv={GO_E} />))
    expect(kachelTexte().sort()).toEqual(['fahrzeug-8', 'geraet-6', 'wert-ladung-6', 'wert-sitzung-6'])
    expect(document.querySelector('[data-ueberblick-emob="wallbox"]')?.textContent).toContain('go-eCharger')
    rerender(rahmen(<UeberblickBlockEmob anlageId={1} geraete={[GO_E, CARPORT]} inv={CARPORT} />))
    expect(kachelTexte().sort()).toEqual(['fahrzeug-9', 'geraet-7', 'wert-ladung-7'])
    expect(document.querySelector('[data-platz="fahrzeug-9"]')?.textContent).toContain('Zoe')
    expect(document.querySelector('[data-ueberblick-schaubild] svg')?.getAttribute('aria-label')).toBe('Schaubild Ladepunkt')
  })

  it('E-Auto: ID.4 ⇒ L/B des ID.4; Zoe gewählt ⇒ L/B der Zoe; Szene «Fahrzeug»', () => {
    liveMock.wert = { live: DEMO, wetter: null, tag: null }
    const { rerender } = render(rahmen(<UeberblickBlockEmob anlageId={1} geraete={[ID4, ZOE]} inv={ID4} />))
    expect(document.querySelector('[data-ueberblick-schaubild] svg')?.getAttribute('aria-label')).toBe('Schaubild Fahrzeug')
    expect(kachelTexte().sort()).toEqual(['geraet-8', 'wert-ladestand-8'])
    expect(document.querySelector('[data-platz="wert-ladestand-8"]')?.textContent).toContain('52 %')
    rerender(rahmen(<UeberblickBlockEmob anlageId={1} geraete={[ID4, ZOE]} inv={ZOE} />))
    expect(kachelTexte().sort()).toEqual(['geraet-9', 'wert-ladestand-9'])
    expect(document.querySelector('[data-platz="wert-ladestand-9"]')?.textContent).toContain('81 %')
  })
})
