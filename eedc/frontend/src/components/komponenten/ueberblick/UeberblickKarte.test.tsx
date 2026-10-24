/**
 * «Auf einen Blick» (P-433-2 E2): jede Zeile nur mit Wert, «Kühlen (passiv)»,
 * Ring nur mit der Gauge `eigenverbrauch`, ohne `wp_geraete`-Zeile keine
 * Heute-Werte aus dem Tag-Detail; Strom heute nach der Ein-Geräte-Regel.
 */
import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import UeberblickKarte from './UeberblickKarte'
import { stromHeute } from './kachelAnker'
import type { LiveDashboardResponse, LiveKomponente, LiveWetterResponse } from '../../../api/liveDashboard'
import type { TagDetail } from '../../../api/energie_profil'
import type { Investition } from '../../../types'

const wpInv = (id: number, parameter: Record<string, unknown> = {}): Investition =>
  ({ id, anlage_id: 1, typ: 'waermepumpe', bezeichnung: `WP ${id}`, aktiv: true, parameter } as Investition)
const knoten = (id: number, kw: number, extra: Partial<LiveKomponente> = {}): LiveKomponente =>
  ({ key: `waermepumpe_${id}`, label: `WP ${id}`, icon: 'heater', erzeugung_kw: null, verbrauch_kw: kw, ...extra })
const live = (extra: Partial<LiveDashboardResponse> = {}): LiveDashboardResponse => ({
  anlage_id: 1, anlage_name: 'Test', zeitpunkt: '', verfuegbar: true,
  komponenten: [], summe_erzeugung_kw: 0, summe_verbrauch_kw: 0, summe_pv_kw: 0, gauges: [],
  heute_pv_kwh: null, heute_einspeisung_kwh: null, heute_netzbezug_kwh: null, heute_eigenverbrauch_kwh: null,
  gestern_pv_kwh: null, gestern_einspeisung_kwh: null, gestern_netzbezug_kwh: null, gestern_eigenverbrauch_kwh: null,
  heute_kwh_pro_komponente: null, warmwasser_temperatur_c: null, innengeraete: null,
  ...extra,
})
const wetter = (t: number) => ({ aktuell: { zeit: '12:00', temperatur_c: t } } as unknown as LiveWetterResponse)
const tag = (zeilen: TagDetail['wp_geraete']) => ({ wp_geraete: zeilen } as unknown as TagDetail)
const EV = { key: 'eigenverbrauch', label: 'Eigenverbrauch', wert: 83.4, min_wert: 0, max_wert: 100, einheit: '%' }

const zeilen = (c: HTMLElement) => [...c.querySelectorAll('[data-zeile]')].map((z) => z.getAttribute('data-zeile'))

describe('UeberblickKarte', () => {
  it('ohne Werte: nur der Kopf — keine Zeile, kein Ring, kein Chip', () => {
    const { container } = render(<UeberblickKarte inv={wpInv(7)} live={live()} wetter={null} tag={null} mehrereGeraete={false} />)
    expect(container.textContent).toContain('WP 7')
    expect(zeilen(container)).toEqual([])
    expect(container.querySelector('[data-anlagen-ring]')).toBeNull()
    expect(container.querySelector('[data-modus-chip]')).toBeNull()
  })

  it('jede Zeile nur mit Wert: Leistung, Warmwasser, Außen, Strom/Wärme/AZ heute, AZ je Betriebsart nur mit Zahl', () => {
    const { container } = render(
      <UeberblickKarte
        inv={wpInv(7)}
        live={live({ komponenten: [knoten(7, 1.25)], warmwasser_temperatur_c: 48.5, heute_kwh_pro_komponente: { waermepumpe_7: 6.4 } })}
        wetter={wetter(7.4)}
        tag={tag([{ investition_id: 7, name: 'WP 7', strom_kwh: 6.4, waerme_kwh: 25.1, jaz: 3.92, jaz_heizen: 4.1, jaz_warmwasser: null, jaz_kuehlen: null }])}
        mehrereGeraete={false}
      />,
    )
    expect(zeilen(container)).toEqual(['leistung', 'warmwasser', 'aussen', 'strom-heute', 'waerme-heute', 'az-heute', 'az-heizen'])
    expect(container.textContent).toContain('1.250 W')
    expect(container.textContent).toContain('48,5 °C')
    expect(container.textContent).toContain('25,1 kWh')
    expect(container.textContent).toContain('3,92')
  })

  it('Gerät ohne `wp_geraete`-Zeile ⇒ keine Wärme/AZ heute (benannte Grenze), Strom aus der Live-Antwort bleibt', () => {
    const { container } = render(
      <UeberblickKarte
        inv={wpInv(7)} live={live({ heute_kwh_pro_komponente: { waermepumpe_7: 2 } })} wetter={null}
        tag={tag([{ investition_id: 8, name: 'andere', waerme_kwh: 10, jaz: 3 }])} mehrereGeraete={false}
      />,
    )
    expect(zeilen(container)).toEqual(['strom-heute'])
  })

  it('Modus-Chip mit Kanon-Label; «Kühlen (passiv)» bei kuehlung_art passiv', () => {
    const k = knoten(7, 0.4, { betriebsmodus: 'kuehlen', betriebsmodus_label: 'Kühlen' })
    const passiv = render(<UeberblickKarte inv={wpInv(7, { kuehlung_art: 'passiv' })} live={live({ komponenten: [k] })} wetter={null} tag={null} mehrereGeraete={false} />)
    expect(passiv.container.querySelector('[data-modus-chip]')!.textContent).toBe('Kühlen (passiv)')
    const aktiv = render(<UeberblickKarte inv={wpInv(7, { kuehlung_art: 'aktiv' })} live={live({ komponenten: [k] })} wetter={null} tag={null} mehrereGeraete={false} />)
    expect(aktiv.container.querySelector('[data-modus-chip]')!.textContent).toBe('Kühlen')
  })

  it('P-433-1: gemessene Ruhe ⇒ Chip «Heizen · Leerlauf», gedämpft — aus der Live-Antwort, ohne Kopie', () => {
    const k = knoten(7, 0.008, { betriebsmodus: 'heizen', betriebsmodus_label: 'Heizen', betriebsmodus_aktion: 'leerlauf', betriebsmodus_aktion_label: 'Leerlauf' })
    const chip = render(<UeberblickKarte inv={wpInv(7)} live={live({ komponenten: [k] })} wetter={null} tag={null} mehrereGeraete={false} />)
      .container.querySelector('[data-modus-chip]')!
    expect(chip.textContent).toBe('Heizen · Leerlauf')
    expect(chip.hasAttribute('data-modus-aktion')).toBe(true)
  })

  it('Anlagen-Ring = Gauge `eigenverbrauch`, beschriftet «Eigenverbrauch jetzt x % (Anlage)» — nur, wenn geliefert', () => {
    const mit = render(<UeberblickKarte inv={wpInv(7)} live={live({ gauges: [EV] })} wetter={null} tag={null} mehrereGeraete={false} />)
    expect(mit.container.querySelector('[data-anlagen-ring]')!.textContent).toContain('Eigenverbrauch jetzt 83 % (Anlage)')
    const ohne = render(<UeberblickKarte inv={wpInv(7)} live={live({ gauges: [{ ...EV, key: 'autarkie' }] })} wetter={null} tag={null} mehrereGeraete={false} />)
    expect(ohne.container.querySelector('[data-anlagen-ring]')).toBeNull()
  })

  it('keine Kosten-, CO₂- oder Ersparniszahl', () => {
    const { container } = render(<UeberblickKarte inv={wpInv(7)} live={live({ gauges: [EV], komponenten: [knoten(7, 1)] })} wetter={wetter(5)} tag={null} mehrereGeraete={false} />)
    expect(container.textContent).not.toMatch(/€|CO₂|Ersparnis/)
  })
})

describe('stromHeute — eine Regel für Kachel und Karte', () => {
  it('exakter Key; der Typ-Key nur bei einem einzigen Gerät', () => {
    const l = live({ heute_kwh_pro_komponente: { waermepumpe: 9 } })
    expect(stromHeute(l, 7, false)).toBe(9)
    expect(stromHeute(l, 7, true)).toBeNull()
    expect(stromHeute(live({ heute_kwh_pro_komponente: { waermepumpe_7: 3, waermepumpe: 9 } }), 7, true)).toBe(3)
    expect(stromHeute(live(), 7, false)).toBeNull()
  })
})
