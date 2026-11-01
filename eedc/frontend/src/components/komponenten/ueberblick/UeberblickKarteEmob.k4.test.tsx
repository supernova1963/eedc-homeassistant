/**
 * Karten «Heute» und Gerätekarte E-Mobilität (P-433-2b K4, Bauplan K4-6): Kopfzahl «PV-Anteil heute» nur mit
 * `emob_heute.pv_anteil_prozent` (nie aus dem Live-Pfad, S1), Herleitung aus denselben zwei Zahlen des Backends,
 * «Ladung heute» mit Tag-Detail-Vorrang und Live-Rückfall, E-Auto «Gefahren heute» / «Fahrverbrauch heute» nur mit Wert,
 * «Kilometerstand» an der Gerätekarte. Der Client rechnet nichts.
 */
import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import UeberblickKarteEmob, {
  LADUNG_TAG_TOOLTIP, LADUNG_TOOLTIP, herleitungPvAnteil, heuteZeile,
} from './UeberblickKarteEmob'
import type { EmobHeuteZeile, TagDetail } from '../../../api/energie_profil'
import type { LiveDashboardResponse } from '../../../api/liveDashboard'
import type { Investition } from '../../../types'

const inv = (id: number, typ: string, bez: string): Investition =>
  ({ id, anlage_id: 1, typ, bezeichnung: bez, aktiv: true, parameter: {} } as Investition)
const WB = inv(4, 'wallbox', 'SMA eCharger 22')
const AUTO = inv(5, 'e-auto', 'Smart #1')

const tag = (zeilen: EmobHeuteZeile[] | undefined, pv: number | null = 9.8) =>
  ({ emob_ladung_pv_kwh: pv, emob_betrieb: [], emob_heute: zeilen } as unknown as TagDetail)
const live = (extra: Partial<LiveDashboardResponse> = {}) =>
  ({ komponenten: [], gauges: [], heute_kwh_pro_komponente: { wallbox_4: 3.3, eauto_5: 1.1 }, ...extra } as unknown as LiveDashboardResponse)
const zeichne = (i: Investition, l: LiveDashboardResponse | null, t: TagDetail | null) =>
  render(<UeberblickKarteEmob inv={i} live={l} tag={t} mehrereGeraete={false} />).container
const heute = (c: HTMLElement) => c.querySelector('[data-karte="heute"]') as HTMLElement | null

const WB_ZEILE: EmobHeuteZeile = { investition_id: 4, typ: 'wallbox', ladung_kwh: 14.7, ladung_pv_kwh: 9.8, pv_anteil_prozent: 67 }

describe('Karte «Heute» Wallbox (K4)', () => {
  it('Kopfzahl «67 %» mit Herleitung «9,8 kWh PV ÷ 14,7 kWh», Ladung heute aus dem Tag-Detail', () => {
    const k = heute(zeichne(WB, live(), tag([WB_ZEILE])))!
    expect(k.textContent).toContain('PV-Anteil heute')
    expect(k.querySelector('[data-zeile="pv-anteil-heute"]')?.textContent).toBe('67 %')
    expect(k.querySelector('[data-herleitung]')?.textContent).toBe('9,8 kWh PV ÷ 14,7 kWh')
    const ladung = k.querySelector('[data-zeile="ladung-heute"]')!
    expect(ladung.textContent).toContain('14,7 kWh')
    expect(ladung.parentElement?.getAttribute('title')).toBe(LADUNG_TAG_TOOLTIP)
  })

  it('Kopfzahl ohne `emob_heute` fehlt — auch wenn der Live-Pfad eine Ladung hat (S1); Live ist Rückfall', () => {
    const k = heute(zeichne(WB, live(), tag(undefined)))!
    expect(k.querySelector('[data-zeile="pv-anteil-heute"]')).toBeNull()
    expect(k.textContent).toContain('Heute')
    expect(k.textContent).not.toContain('PV-Anteil heute')
    const ladung = k.querySelector('[data-zeile="ladung-heute"]')!
    expect(ladung.textContent).toContain('3,3 kWh')
    expect(ladung.parentElement?.getAttribute('title')).toBe(LADUNG_TOOLTIP)
  })

  it('Zeile ohne Anteil (nur Ladung): keine Kopfzahl, Ladung aus dem Tag-Detail', () => {
    const k = heute(zeichne(WB, live(), tag([{ investition_id: 4, typ: 'wallbox', ladung_kwh: 8, ladung_pv_kwh: null, pv_anteil_prozent: null }])))!
    expect(k.querySelector('[data-zeile="pv-anteil-heute"]')).toBeNull()
    expect(k.querySelector('[data-zeile="ladung-heute"]')?.textContent).toContain('8,0 kWh')
  })

  it('S2: die Kopfzahl ist die Zahl des Backends, der Client teilt nicht selbst', () => {
    // 9,8 ÷ 14,7 wären 67 % — das Backend sagt 50 %, also steht 50 % da (der Client formatiert nur).
    const k = heute(zeichne(WB, live(), tag([{ ...WB_ZEILE, pv_anteil_prozent: 50 }])))!
    expect(k.querySelector('[data-zeile="pv-anteil-heute"]')?.textContent).toBe('50 %')
    // Ohne Backend-Anteil keine Kopfzahl, auch wenn beide Mengen da sind.
    const ohne = heute(zeichne(WB, live(), tag([{ ...WB_ZEILE, pv_anteil_prozent: null }])))!
    expect(ohne.querySelector('[data-zeile="pv-anteil-heute"]')).toBeNull()
  })

  it('heuteZeile wählt das Gerät; herleitungPvAnteil nur mit beiden Zahlen', () => {
    expect(heuteZeile(tag([WB_ZEILE, { investition_id: 9, typ: 'wallbox' }]), 4)).toEqual(WB_ZEILE)
    expect(heuteZeile(tag(undefined), 4)).toBeNull()
    expect(herleitungPvAnteil(9.8, 14.7)).toBe('9,8 kWh PV ÷ 14,7 kWh')
    expect(herleitungPvAnteil(null, 14.7)).toBeNull()
  })
})

describe('E-Auto: Fahrt heute und Kilometerstand (K4)', () => {
  it('«Gefahren heute» und «Fahrverbrauch heute» nur mit Wert, keine Kopfzahl', () => {
    const k = heute(zeichne(AUTO, live(), tag([{ investition_id: 5, typ: 'e-auto', km: 42.4, fahrverbrauch_kwh: 7.5 }])))!
    expect(k.querySelector('[data-zeile="gefahren-heute"]')?.textContent).toContain('42 km')
    expect(k.querySelector('[data-zeile="fahrverbrauch-heute"]')?.textContent).toContain('7,5 kWh')
    expect(k.querySelector('[data-zeile="pv-anteil-heute"]')).toBeNull()
    const ohne = heute(zeichne(AUTO, live(), tag([{ investition_id: 5, typ: 'e-auto', km: 12 }])))!
    expect(ohne.querySelector('[data-zeile="fahrverbrauch-heute"]')).toBeNull()
  })

  it('Gerätekarte zeigt «Kilometerstand 23.037 km» nur mit `km_stand`', () => {
    const mit = live({ fahrzeuge_ohne_wallbox: [{ investition_id: 5, label: 'Smart #1', soc: 62, kw: null, v2h: false, km_stand: 23037 }] })
    const c = zeichne(AUTO, mit, null)
    expect(c.querySelector('[data-zeile="kilometerstand"]')?.textContent).toBe('Kilometerstand23.037 km')
    const ohne = live({ fahrzeuge_ohne_wallbox: [{ investition_id: 5, label: 'Smart #1', soc: 62, kw: null, v2h: false }] })
    expect(zeichne(AUTO, ohne, null).querySelector('[data-zeile="kilometerstand"]')).toBeNull()
  })
})

describe('Nachlauf 4.2.0 K3: Gerätekarte E-Auto am Handy — Ladestand und Reichweite überlagern sich nicht', () => {
  it('die Reihe bricht unter `sm` um (Reichweite unter den Ladestand), ab `sm` nebeneinander wie bisher', () => {
    const mit = live({ fahrzeuge_ohne_wallbox: [{ investition_id: 5, label: 'Smart #1', soc: 62, kw: null, v2h: false, reichweite_km: 312 }] })
    const c = zeichne(AUTO, mit, null)
    const reihe = c.querySelector('[data-reihe="ladestand"]') as HTMLElement
    expect(reihe.querySelector('[data-zeile="ladestand"]')).not.toBeNull()
    expect(reihe.querySelector('[data-zeile="reichweite"]')?.textContent).toBe('312 km')
    expect(reihe.className.split(' ')).toEqual(expect.arrayContaining(['flex', 'flex-wrap', 'sm:flex-nowrap', 'items-baseline', 'gap-x-3']))
  })

  it('K3b (360/320 px): unter `sm` bricht auch die äußere Reihe um, die Spalte behält ihre Inhaltsbreite, der Ring rückt darunter', () => {
    const mit = live({
      fahrzeuge_ohne_wallbox: [{ investition_id: 5, label: 'Smart #1', soc: 62, kw: null, v2h: false, reichweite_km: 312 }],
      gauges: [{ key: 'eigenverbrauch', label: 'Eigenverbrauch', wert: 80, min_wert: 0, max_wert: 100, einheit: '%' }],
    })
    const c = zeichne(AUTO, mit, null)
    const aussen = c.querySelector('[data-reihe="ladestand-ring"]') as HTMLElement
    expect(aussen.className.split(' ')).toEqual(expect.arrayContaining(['flex', 'max-sm:flex-wrap', 'items-center', 'justify-between']))
    expect(aussen.className.split(' ')).not.toContain('flex-wrap')   // ab `sm` unverändert nebeneinander
    const spalte = aussen.querySelector('[data-spalte="ladestand"]') as HTMLElement
    expect(spalte.className.split(' ')).toEqual(expect.arrayContaining(['min-w-0', 'max-sm:min-w-fit', 'flex-1']))
    expect(aussen.querySelector('[data-anlagen-ring]')).not.toBeNull()
  })
})
