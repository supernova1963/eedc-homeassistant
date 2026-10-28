/**
 * «Auf einen Blick» E-Mobilität (P-433-2b K1, Bauplan E4; Blatt Fassung 3 §1/§2/§4).
 *
 * Fälle des Bauplans: Wallbox eindeutig (Lab-Publisher-Fall «11,0 kW · Smart #1 62 % · 312 km · Ziel 80»), «geschätzt»
 * (zwei Wallboxen ⇒ alle Autos + `SATZ_ZUORDNUNG_UNBEKANNT`), V2H («Abgabe ins Haus»), kein Zustand (Fußzeile; auch
 * mit Leistung kein Chip — Sprengsatz «Zustand aus kW»), «Kein Fahrzeug» mit letzter Sitzung, Auto ohne Wallbox
 * (eigener Chip), Auto an Wallbox (kein eigener Chip, Leitsatz 8), Ladung heute nur mit Knoten (K-6), keine Kopfzahl
 * PV-Anteil (K-7: das Tag-Detail trägt keine Wallbox-kWh), keine Rahmenfarbe nach Zustand (K-3).
 */
import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import UeberblickKarteEmob, {
  FUSSZEILE_EAUTO, FUSSZEILE_WALLBOX, OBERFLAECHE_TEXT, oberflaecheUrl, sitzungsTeile, zielText,
} from './UeberblickKarteEmob'
import { SATZ_ZUORDNUNG_UNBEKANNT } from '../../live/EnergieFluss'
import { fmtDauer, fmtStundenDauer } from '../../../lib'
import type { LiveDashboardResponse, LiveFahrzeug, LiveKomponente } from '../../../api/liveDashboard'
import type { TagDetail } from '../../../api/energie_profil'
import type { Investition } from '../../../types'

const inv = (id: number, typ: string, bez: string, parameter: Record<string, unknown> = {}): Investition =>
  ({ id, anlage_id: 1, typ, bezeichnung: bez, aktiv: true, parameter } as Investition)
const wb = (id: number, kw: number, extra: Partial<LiveKomponente> = {}): LiveKomponente =>
  ({ key: `wallbox_${id}`, label: `WB ${id}`, icon: 'plug', erzeugung_kw: null, verbrauch_kw: kw, typ: 'wallbox', ...extra })
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
const EV = { key: 'eigenverbrauch', label: 'Eigenverbrauch', wert: 83.4, min_wert: 0, max_wert: 100, einheit: '%' }
const tag = (pv: number | null) => ({ emob_ladung_pv_kwh: pv } as unknown as TagDetail)

const zeichne = (i: Investition, l: LiveDashboardResponse | null, t: TagDetail | null = null, mehrere = false) =>
  render(<UeberblickKarteEmob inv={i} live={l} tag={t} mehrereGeraete={mehrere} />).container
const zeilen = (c: HTMLElement) => [...c.querySelectorAll('[data-zeile]')].map((z) => z.getAttribute('data-zeile'))
const text = (c: HTMLElement, zeile: string) => c.querySelector(`[data-zeile="${zeile}"]`)?.textContent ?? null

const SMA = inv(4, 'wallbox', 'SMA eCharger 22')
const SMART = inv(5, 'e-auto', 'Smart #1')
const labLaedt = (extra: Partial<LiveKomponente> = {}) => wb(4, 11, {
  label: 'SMA eCharger 22', ladezustand: 'laedt', ladezustand_label: 'Lädt', lademodus: 'pv', lademodus_label: 'PV',
  sitzung: { kwh: 9.8, dauer_s: 7800 }, ladestrom_a: 16, phasen_aktiv: 3, fahrzeuge_zuordnung: 'eindeutig',
  fahrzeuge: [fz(5, 'Smart #1', { soc: 62, reichweite_km: 312, ziel_prozent: 80 })], ...extra,
})

describe('UeberblickKarteEmob — Wallbox', () => {
  it('Lab-Fall eindeutig: «Lädt · PV», 11,0 kW, Ring, Fahrzeugzeile mit Zielmarke, Sitzungs-Fußzeile', () => {
    const c = zeichne(SMA, live({ komponenten: [labLaedt()], gauges: [EV] }))
    expect(c.querySelector('[data-modus-chip="laedt"]')?.textContent).toBe('Lädt · PV')
    expect(text(c, 'leistung')).toContain('11,0 kW')
    expect(c.querySelector('[data-anlagen-ring]')).not.toBeNull()
    expect(text(c, 'fahrzeug')).toBe('Smart #1 · 62 % · 312 km')
    const marke = c.querySelector('[data-zielmarke]') as HTMLElement
    expect(marke.style.left).toBe('calc(80% - 1px)')
    expect(c.querySelector('[data-ziel-text]')?.textContent).toBe('Ziel 80 %')
    expect((c.querySelector('[data-ladestand-fuellung]') as HTMLElement).style.width).toBe('62%')
    expect(text(c, 'sitzung')).toBe('3 Phasen · 16 A · 9,8 kWh in dieser Sitzung · 2 h 10 min')
    expect(c.querySelector('[data-fusszeile]')).toBeNull()
  })

  it('«geschätzt» (zwei Wallboxen): alle Autos und der Satz — auch wenn an dieser Wallbox nur eines steht', () => {
    const l = live({ komponenten: [
      wb(4, 3, { fahrzeuge_zuordnung: 'geschaetzt', fahrzeuge: [fz(5, 'Smart #1', { soc: 50 })] }),
      wb(9, 0, { fahrzeuge_zuordnung: 'geschaetzt', fahrzeuge: [fz(6, 'Zoe', { soc: 70 })] }),
    ] })
    const c = zeichne(SMA, l, null, true)
    expect(c.querySelector('[data-fahrzeuge="geschaetzt"]')).not.toBeNull()
    expect([...c.querySelectorAll('[data-zeile="fahrzeug"]')].map((z) => z.textContent)).toEqual(['Smart #1 · 50 %', 'Zoe · 70 %'])
    expect(c.textContent).toContain(SATZ_ZUORDNUNG_UNBEKANNT)
  })

  it('V2H: Abgabe ins Haus statt Ladeleistung', () => {
    const c = zeichne(SMA, live({ komponenten: [wb(4, 0, { verbrauch_kw: null, erzeugung_kw: 3.2 })] }))
    expect(text(c, 'leistung')).toContain('Abgabe ins Haus')
    expect(text(c, 'leistung')).toContain('3.200 W')
  })

  it('kein Zustandsfeld: kein Chip — auch bei 11 kW (Zustand nur gemessen, K-2) — und die Fußzeile', () => {
    const c = zeichne(SMA, live({ komponenten: [wb(4, 11)] }))
    expect(c.querySelector('[data-modus-chip]')).toBeNull()
    expect(c.querySelector('[data-fusszeile]')?.textContent).toBe(FUSSZEILE_WALLBOX)
    // Vor der ersten Live-Antwort keine Fußzeile (nichts fehlt, es ist nur noch nicht geladen).
    expect(zeichne(SMA, null).querySelector('[data-fusszeile]')).toBeNull()
  })

  it('«Kein Fahrzeug»: Chip ohne Lademodus, «letzte Sitzung», keine Phasen/Strom', () => {
    const c = zeichne(SMA, live({ komponenten: [labLaedt({
      verbrauch_kw: 0, ladezustand: 'kein_fahrzeug', ladezustand_label: 'Kein Fahrzeug', sitzung: { kwh: 12.4, dauer_s: 9000 },
      fahrzeuge: [],
    })] }))
    expect(c.querySelector('[data-modus-chip="kein_fahrzeug"]')?.textContent).toBe('Kein Fahrzeug')
    expect(text(c, 'sitzung')).toBe('letzte Sitzung 12,4 kWh')
  })

  it('Lab rc13 «Verbunden», nicht ladend: keine «0 Phasen · 0 A», «Ziel 80 %» ohne «noch 0 min», kein Fußzeilen-Hinweis', () => {
    const c = zeichne(SMA, live({ komponenten: [labLaedt({
      verbrauch_kw: 0, ladezustand: 'verbunden', ladezustand_label: 'Verbunden', sitzung: undefined,
      phasen_aktiv: 0, ladestrom_a: 0, ziel_prozent: 80, restzeit_min: 0,
    })] }))
    expect(text(c, 'sitzung')).toBeNull()
    expect(text(c, 'ziel')).toContain('80 %')
    expect(text(c, 'ziel')).not.toContain('noch')
    expect(c.querySelector('[data-fusszeile]')).toBeNull()
    // Ohne Chip und nur mit Nullen zugeordnet: zugeordnet ist zugeordnet — kein «erscheinen hier, sobald zugeordnet».
    const nurNullen = zeichne(SMA, live({ komponenten: [wb(4, 0, { phasen_aktiv: 0, ladestrom_a: 0 })] }))
    expect(text(nurNullen, 'sitzung')).toBeNull()
    expect(nurNullen.querySelector('[data-fusszeile]')).toBeNull()
  })

  it('Lademodus nur hinter «Lädt» und «Wartet»', () => {
    const chip = (zustand: string, label: string) => zeichne(SMA, live({ komponenten: [labLaedt({ ladezustand: zustand, ladezustand_label: label })] }))
      .querySelector('[data-modus-chip]')?.textContent
    expect(chip('wartet', 'Wartet')).toBe('Wartet · PV')
    expect(chip('verbunden', 'Verbunden')).toBe('Verbunden')
    expect(chip('fertig', 'Fertig')).toBe('Fertig')
  })

  it('keine Rahmenfarbe nach Zustand (K-3): die Karte trägt bei jedem Zustand dieselben Klassen', () => {
    // Alle Hüllen von der Karte bis zum Block — eine Rahmen-/Ring-Klasse nach Zustand fiele an irgendeiner davon auf.
    const klassen = (zustand: string) => {
      const c = zeichne(SMA, live({ komponenten: [labLaedt({ ladezustand: zustand, ladezustand_label: zustand })] }))
      const out: string[] = []
      for (let el = c.querySelector('[data-karte="geraet"]') as HTMLElement | null; el && el !== c; el = el.parentElement) {
        out.push(el.className)
      }
      return out.join(' | ')
    }
    const laedt = klassen('laedt')
    for (const z of ['wartet', 'kein_fahrzeug', 'fehler', 'verbunden']) expect(klassen(z)).toBe(laedt)
  })

  it('Ziel · Restzeit und der Link zur Hersteller-Oberfläche (nur http/https)', () => {
    const mitUrl = inv(4, 'wallbox', 'SMA', { oberflaeche_url: 'http://evcc.local:7070' })
    const c = zeichne(mitUrl, live({ komponenten: [labLaedt({ ziel_prozent: 90, restzeit_min: 80 })] }))
    expect(text(c, 'ziel')).toContain('90 % · noch 1 h 20 min')
    const a = c.querySelector('[data-oberflaeche-link]') as HTMLAnchorElement
    expect(a.textContent).toBe(OBERFLAECHE_TEXT)
    expect(a.getAttribute('href')).toBe('http://evcc.local:7070')
    expect(a.getAttribute('rel')).toContain('noopener')
    expect(oberflaecheUrl(inv(4, 'wallbox', 'x', { oberflaeche_url: 'javascript:alert(1)' }))).toBeNull()
    expect(zeichne(SMA, live({ komponenten: [labLaedt()] })).querySelector('[data-oberflaeche-link]')).toBeNull()
  })

  it('«Heute»: Ladung heute (exakter Key) und PV-Ladung (Anlage) — ohne Kopfzahl PV-Anteil (K-7)', () => {
    const c = zeichne(SMA, live({ komponenten: [labLaedt()], heute_kwh_pro_komponente: { wallbox_4: 14.7 } }), tag(9.8))
    expect(c.querySelector('[data-karte="heute"]')).not.toBeNull()
    expect(text(c, 'ladung-heute')).toContain('14,7 kWh')
    expect(text(c, 'pv-ladung-heute')).toContain('9,8 kWh (Anlage)')
    expect(c.textContent).not.toMatch(/PV-Anteil/)
    expect(zeichne(SMA, live({ komponenten: [labLaedt()] })).querySelector('[data-karte="heute"]')).toBeNull()
  })
})

describe('UeberblickKarteEmob — E-Auto', () => {
  it('Auto an der Wallbox: Ladestand groß mit Leiste, Reichweite, Ort — kein eigener Chip (Leitsatz 8)', () => {
    const l = live({ komponenten: [labLaedt({ fahrzeuge: [fz(5, 'Smart #1', {
      soc: 62, reichweite_km: 312, ziel_prozent: 80, ladezustand: 'laedt', ladezustand_label: 'Lädt', zu_hause: true,
    })] })], gauges: [EV] })
    const c = zeichne(SMART, l)
    expect(c.querySelector('[data-modus-chip]')).toBeNull()
    expect(text(c, 'ladestand')).toContain('62 %')
    expect(text(c, 'reichweite')).toBe('312 km')
    expect(c.querySelector('[data-zielmarke]')).not.toBeNull()
    expect(text(c, 'ort')).toContain('an SMA eCharger 22')
    expect(text(c, 'standort')).toContain('Zu Hause')
  })

  it('Auto ohne Wallbox: eigener Chip, «Unterwegs», Chip «Dienstwagen»', () => {
    const l = live({ fahrzeuge_ohne_wallbox: [fz(5, 'Smart #1', {
      soc: 45, ladezustand: 'nicht_verbunden', ladezustand_label: 'Nicht verbunden', zu_hause: false, dienstwagen: true,
    })] })
    const c = zeichne(SMART, l)
    expect(c.querySelector('[data-modus-chip="nicht_verbunden"]')?.textContent).toBe('Nicht verbunden')
    expect(c.querySelector('[data-zusatz-chip]')?.textContent).toBe('Dienstwagen')
    expect(text(c, 'standort')).toContain('Unterwegs')
    expect(text(c, 'ort')).toBeNull()
  })

  it('Ladung heute nur mit eigenem Knoten (K-6/W3) — der Tageswert allein reicht nicht', () => {
    const ohneKnoten = live({ fahrzeuge_ohne_wallbox: [fz(5, 'Smart #1', { soc: 45 })], heute_kwh_pro_komponente: { eauto_5: 8.3 } })
    expect(text(zeichne(SMART, ohneKnoten), 'ladung-heute')).toBeNull()
    const mitKnoten = live({
      komponenten: [{ key: 'eauto_5', label: 'Smart #1', icon: 'car', erzeugung_kw: null, verbrauch_kw: 7.4, typ: 'e-auto' }],
      fahrzeuge_ohne_wallbox: [fz(5, 'Smart #1', { soc: 45, kw: 7.4 })], heute_kwh_pro_komponente: { eauto_5: 8.3 },
    })
    const c = zeichne(SMART, mitKnoten)
    expect(text(c, 'ladung-heute')).toContain('8,3 kWh')
    expect(text(c, 'ladeleistung')).toContain('7.400 W')
  })

  it('Kosmetik rc13 (K-1): Auto-Karte «Ziel 80 %» ohne «noch 0 min»', () => {
    const c = zeichne(SMART, live({ fahrzeuge_ohne_wallbox: [fz(5, 'Smart #1', { soc: 45, ziel_prozent: 80, restzeit_min: 0 })] }))
    expect(text(c, 'ziel')).toContain('80 %')
    expect(text(c, 'ziel')).not.toContain('noch')
    const nurRest = zeichne(SMART, live({ fahrzeuge_ohne_wallbox: [fz(5, 'Smart #1', { soc: 45, restzeit_min: 0 })] }))
    expect(text(nurRest, 'ziel')).toBeNull()
    expect(nurRest.querySelector('[data-fusszeile]')).toBeNull()
  })

  it('«geschätzt»: kein Ort, der Satz statt einer behaupteten Wallbox', () => {
    const l = live({ komponenten: [wb(4, 3, { fahrzeuge_zuordnung: 'geschaetzt', fahrzeuge: [fz(5, 'Smart #1', { soc: 50 })] })] })
    const c = zeichne(SMART, l)
    expect(text(c, 'ort')).toBeNull()
    expect(c.textContent).toContain(SATZ_ZUORDNUNG_UNBEKANNT)
  })

  it('ohne K1-Felder: Fußzeile; ohne Live-Antwort nichts', () => {
    const c = zeichne(SMART, live({ fahrzeuge_ohne_wallbox: [fz(5, 'Smart #1', { soc: 45 })] }))
    expect(c.querySelector('[data-fusszeile]')?.textContent).toBe(FUSSZEILE_EAUTO)
    expect(zeichne(SMART, null).querySelector('[data-fusszeile]')).toBeNull()
    expect(zeilen(zeichne(SMART, null))).toEqual([])
  })
})

describe('Formatierung', () => {
  it('fmtDauer', () => {
    expect(fmtDauer(7800)).toBe('2 h 10 min')
    expect(fmtDauer(21660)).toBe('6 h 01 min')
    expect(fmtDauer(2700)).toBe('45 min')
    expect(fmtDauer(null)).toBe('—')
  })

  it('fmtStundenDauer: Stunden nie dezimal (Lab rc13, Gernot 28.10.2026)', () => {
    expect(fmtStundenDauer(2.6)).toBe('2 h 36 min')
    expect(fmtStundenDauer(0.73)).toBe('44 min')
    expect(fmtStundenDauer(0)).toBe('0 min')
    expect(fmtStundenDauer(null)).toBe('—')
  })
  it('sitzungsTeile und zielText nur mit Feld', () => {
    expect(sitzungsTeile(wb(4, 1, { phasen_aktiv: 1 }))).toEqual(['1 Phase'])
    expect(sitzungsTeile(wb(4, 1))).toEqual([])
    expect(zielText(null, null)).toBeNull()
    expect(zielText(80, null)).toBe('80 %')
  })
  it('Kosmetik rc13 (K-1): Phasen, Strom und Restzeit nur mit Wert > 0 — das Ziel bleibt', () => {
    expect(sitzungsTeile(wb(4, 0, { phasen_aktiv: 0, ladestrom_a: 0 }))).toEqual([])
    expect(sitzungsTeile(wb(4, 0, { phasen_aktiv: 0, ladestrom_a: 0, sitzung: { kwh: 2.5, dauer_s: null } })))
      .toEqual(['2,5 kWh in dieser Sitzung'])
    expect(sitzungsTeile(wb(4, 11, { phasen_aktiv: 3, ladestrom_a: 16 }))).toEqual(['3 Phasen', '16 A'])
    expect(zielText(80, 0)).toBe('80 %')
    expect(zielText(null, 0)).toBeNull()
    expect(zielText(80, 80)).toBe('80 % · noch 1 h 20 min')
  })
})
