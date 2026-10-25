/**
 * «Auf einen Blick» (P-433-2 E2): jede Zeile nur mit Wert, «Kühlen (passiv)»,
 * Ring nur mit der Gauge `eigenverbrauch`, ohne `wp_geraete`-Zeile keine
 * Heute-Werte aus dem Tag-Detail; Strom heute nach der Ein-Geräte-Regel.
 * P-433-2c: Gestalt nach Mockup — Gerätekarte mit großer Leistung und Ring «Eigenverbrauch (Anlage)», Karte
 * «AZ heute» mit Herleitung aus Zähler/Nenner (`herleitungMengen`), Karte «Betrieb heute» aus `betrieb_stunden`.
 */
import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import UeberblickKarte from './UeberblickKarte'
import { stromHeute } from './kachelAnker'
import { BETRIEB_TOOLTIP, FUSSZEILE_OHNE_VORLAUF, RING_TOOLTIP } from './UeberblickKarte'
import { herleitungMengen } from '../../../v4/wpFunktionsGruppen'
import { funktionsFarbe } from '../../../lib/funktionsFarben'
import { KPI_WERT_SCHRIFT } from '../../ui/KPICard'
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
    // P-433-2c: die Arbeitszahl steht groß oben in der Karte «AZ heute», je Funktion in ihrer Unterzeile, Strom und
    // Wärme heute darunter.
    expect(zeilen(container)).toEqual(['leistung', 'warmwasser', 'aussen', 'az-heute', 'az-heizen', 'strom-heute', 'waerme-heute'])
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

  it('Anlagen-Ring = Gauge `eigenverbrauch`, beschriftet «Eigenverbrauch (Anlage)» (P-433-2c) — nur, wenn geliefert', () => {
    const mit = render(<UeberblickKarte inv={wpInv(7)} live={live({ gauges: [EV] })} wetter={null} tag={null} mehrereGeraete={false} />)
    const ring = mit.container.querySelector('[data-anlagen-ring]')!
    expect(ring.textContent).toBe('83 %Eigenverbrauch (Anlage)')
    expect(ring.getAttribute('title')).toBe(RING_TOOLTIP)
    expect(RING_TOOLTIP).toContain('kein Wert je Gerät')
    const ohne = render(<UeberblickKarte inv={wpInv(7)} live={live({ gauges: [{ ...EV, key: 'autarkie' }] })} wetter={null} tag={null} mehrereGeraete={false} />)
    expect(ohne.container.querySelector('[data-anlagen-ring]')).toBeNull()
  })

  it('keine Kosten-, CO₂- oder Ersparniszahl', () => {
    const { container } = render(<UeberblickKarte inv={wpInv(7)} live={live({ gauges: [EV], komponenten: [knoten(7, 1)] })} wetter={wetter(5)} tag={null} mehrereGeraete={false} />)
    expect(container.textContent).not.toMatch(/€|CO₂|Ersparnis/)
  })
})

const karte = (c: HTMLElement, name: string) => c.querySelector(`[data-karte="${name}"]`)
const MIT_ZEILE = (extra: Record<string, unknown> = {}) =>
  tag([{ investition_id: 7, name: 'WP 7', strom_kwh: 3.3, waerme_kwh: 23.0, jaz: 6.97, jaz_zaehler_kwh: 23.04, jaz_nenner_kwh: 3.306,
    jaz_heizen: 7.2, jaz_warmwasser: 5.9, jaz_kuehlen: null, ...extra }] as TagDetail['wp_geraete'])

describe('P-433-2c Gestalt nach Mockup', () => {
  it('ohne Werte: nur die Gerätekarte mit Kopf — keine AZ-, keine Betrieb-Karte', () => {
    const { container } = render(<UeberblickKarte inv={wpInv(7)} live={null} wetter={null} tag={null} mehrereGeraete={false} />)
    expect([...container.querySelectorAll('[data-karte]')].map((k) => k.getAttribute('data-karte'))).toEqual(['geraet'])
    expect(container.querySelector('[data-fusszeile]')).toBeNull()
  })

  it('Gerätekarte: Leistung groß im Schriftgrad der Cockpit-KPI-Kachel, Ring rechts nur mit Gauge', () => {
    const { container } = render(
      <UeberblickKarte inv={wpInv(7)} live={live({ komponenten: [knoten(7, 0.77)], gauges: [EV] })} wetter={null} tag={null} mehrereGeraete={false} />)
    const leistung = karte(container, 'geraet')!.querySelector('[data-zeile="leistung"]')!
    expect(leistung.textContent).toBe('Leistung jetzt770 W')
    expect(leistung.lastElementChild!.className).toContain(KPI_WERT_SCHRIFT)
    expect(karte(container, 'geraet')!.querySelector('[data-anlagen-ring]')).not.toBeNull()
    const ohne = render(<UeberblickKarte inv={wpInv(7)} live={live({ komponenten: [knoten(7, 0.77)] })} wetter={null} tag={null} mehrereGeraete={false} />)
    expect(ohne.container.querySelector('[data-anlagen-ring]')).toBeNull()
    expect(ohne.container.querySelector('[data-zeile="leistung"]')).not.toBeNull()
  })

  it('Fußzeile nur, wenn Vorlauf UND Rücklauf fehlen — ohne Leerlauf-Satz', () => {
    const ohne = render(<UeberblickKarte inv={wpInv(7)} live={live({ komponenten: [knoten(7, 1)] })} wetter={null} tag={null} mehrereGeraete={false} />)
    expect(ohne.container.querySelector('[data-fusszeile]')!.textContent).toBe(FUSSZEILE_OHNE_VORLAUF)
    expect(FUSSZEILE_OHNE_VORLAUF).not.toMatch(/Leerlauf/)
    for (const extra of [{ vorlauf_c: 34.2 }, { ruecklauf_c: 29.1 }]) {
      const mit = render(<UeberblickKarte inv={wpInv(7)} live={live({ komponenten: [knoten(7, 1, extra)] })} wetter={null} tag={null} mehrereGeraete={false} />)
      expect(mit.container.querySelector('[data-fusszeile]')).toBeNull()
    }
  })

  it('Karte «AZ heute»: Zahl groß, Herleitung über `herleitungMengen` (Text-Gleichheit), je Funktion nur mit Wert', () => {
    const { container } = render(
      <UeberblickKarte inv={wpInv(7)} live={live({ heute_kwh_pro_komponente: { waermepumpe_7: 3.3 } })} wetter={null} tag={MIT_ZEILE()} mehrereGeraete={false} />)
    const az = karte(container, 'az-heute')!
    expect(az.textContent).toContain('AZ heute')
    expect(az.querySelector('[data-zeile="az-heute"]')!.textContent).toBe('6,97')
    expect(az.querySelector('[data-zeile="az-heute"]')!.className).toContain(KPI_WERT_SCHRIFT)
    expect(az.querySelector('[data-herleitung]')!.textContent).toBe(
      `${herleitungMengen(23.04, 3.306)} · Heizen 7,20 · Warmwasser 5,90`)
    expect(az.querySelector('[data-herleitung]')!.textContent).toBe('23,0 kWh Wärme ÷ 3,3 kWh Strom · Heizen 7,20 · Warmwasser 5,90')
    expect(zeilen(az as HTMLElement)).toEqual(['az-heute', 'az-heizen', 'az-warmwasser', 'strom-heute', 'waerme-heute'])
  })

  it('ohne Zähler/Nenner keine Herleitung; ohne `jaz` keine Zahl — Mengen bleiben in der Karte «Heute», der Grund als Tooltip', () => {
    const ohneHerleitung = render(<UeberblickKarte inv={wpInv(7)} live={live()} wetter={null}
      tag={MIT_ZEILE({ jaz_zaehler_kwh: null, jaz_nenner_kwh: null, jaz_heizen: null, jaz_warmwasser: null })} mehrereGeraete={false} />)
    expect(ohneHerleitung.container.querySelector('[data-herleitung]')).toBeNull()
    const ohneAz = render(<UeberblickKarte inv={wpInv(7)} live={live({ heute_kwh_pro_komponente: { waermepumpe_7: 3.3 } })} wetter={null}
      tag={MIT_ZEILE({ jaz: null, jaz_grund: 'kein Wärmemengenzähler zugeordnet', jaz_zaehler_kwh: null, jaz_nenner_kwh: null,
        jaz_heizen: null, jaz_warmwasser: null, waerme_kwh: null })} mehrereGeraete={false} />)
    const k = karte(ohneAz.container, 'az-heute')!
    expect(k.textContent).not.toContain('AZ heute')
    expect(k.querySelector('[data-zeile="az-heute"]')).toBeNull()
    expect(k.querySelector('[title="kein Wärmemengenzähler zugeordnet"]')!.textContent).toBe('Heute')
    expect(zeilen(k as HTMLElement)).toEqual(['strom-heute'])
    const nichts = render(<UeberblickKarte inv={wpInv(7)} live={live()} wetter={null} tag={null} mehrereGeraete={false} />)
    expect(karte(nichts.container, 'az-heute')).toBeNull()
  })

  it('Karte «Betrieb heute»: Lese-Reihenfolge, nur Betriebsarten > 0, Farbe je Funktion, Tooltip', () => {
    const { container } = render(<UeberblickKarte inv={wpInv(7)} live={live()} wetter={null}
      tag={MIT_ZEILE({ betrieb_stunden: { lueften: 0.5, warmwasser: 1.6, heizen: 9.4, kuehlen: 0, entfeuchten: 0 } })} mehrereGeraete={false} />)
    const b = karte(container, 'betrieb-heute')!
    expect(zeilen(b as HTMLElement)).toEqual(['betrieb-heizen', 'betrieb-warmwasser', 'betrieb-lueften'])
    expect(b.querySelector('[data-zeile="betrieb-heizen"]')!.textContent).toBe('Heizen9,4 h')
    expect(b.querySelector('[data-zeile="betrieb-warmwasser"]')!.textContent).toBe('Warmwasser1,6 h')
    expect((b.querySelector('[data-betrieb-farbe="heizen"]') as HTMLElement).style.backgroundColor).not.toBe('')
    const farbe = document.createElement('span')
    farbe.style.backgroundColor = funktionsFarbe('lueften')
    expect((b.querySelector('[data-betrieb-farbe="lueften"]') as HTMLElement).style.backgroundColor).toBe(farbe.style.backgroundColor)
    expect(b.querySelector(`[title="${BETRIEB_TOOLTIP}"]`)!.textContent).toBe('Betrieb heute')
    expect(BETRIEB_TOOLTIP).toContain('Leerlauf wird nicht mitgeschrieben')
    expect(b.querySelector('[data-betrieb-ohne]')).toBeNull()
  })

  it('Betrieb heute entfällt ohne Feld; gemessene 0 überall ⇒ «Heute kein Betrieb»', () => {
    const ohne = render(<UeberblickKarte inv={wpInv(7)} live={live()} wetter={null} tag={MIT_ZEILE({ betrieb_stunden: null })} mehrereGeraete={false} />)
    expect(karte(ohne.container, 'betrieb-heute')).toBeNull()
    const null0 = render(<UeberblickKarte inv={wpInv(7)} live={live()} wetter={null}
      tag={MIT_ZEILE({ betrieb_stunden: { heizen: 0, warmwasser: 0 } })} mehrereGeraete={false} />)
    const b = karte(null0.container, 'betrieb-heute')!
    expect(zeilen(b as HTMLElement)).toEqual([])
    expect(b.querySelector('[data-betrieb-ohne]')!.textContent).toBe('Heute kein Betrieb')
  })

  it('passiv kühlendes Gerät: «Kühlen passiv» mit Stunden, sonst «Kühlen passiv, heute kein Betrieb»', () => {
    const passiv = wpInv(7, { kuehlung_art: 'passiv' })
    const mit = render(<UeberblickKarte inv={passiv} live={live()} wetter={null}
      tag={MIT_ZEILE({ betrieb_stunden: { heizen: 2, kuehlen: 3.5 } })} mehrereGeraete={false} />)
    expect(karte(mit.container, 'betrieb-heute')!.querySelector('[data-zeile="betrieb-kuehlen"]')!.textContent).toBe('Kühlen passiv3,5 h')
    expect(karte(mit.container, 'betrieb-heute')!.querySelector('[data-betrieb-ohne]')).toBeNull()
    const ohne = render(<UeberblickKarte inv={passiv} live={live()} wetter={null}
      tag={MIT_ZEILE({ betrieb_stunden: { heizen: 9.4, kuehlen: 0 } })} mehrereGeraete={false} />)
    expect(karte(ohne.container, 'betrieb-heute')!.querySelector('[data-betrieb-ohne]')!.textContent).toBe('Kühlen passiv, heute kein Betrieb')
    const aktiv = render(<UeberblickKarte inv={wpInv(7, { kuehlung_art: 'aktiv' })} live={live()} wetter={null}
      tag={MIT_ZEILE({ betrieb_stunden: { heizen: 9.4, kuehlen: 1 } })} mehrereGeraete={false} />)
    expect(karte(aktiv.container, 'betrieb-heute')!.querySelector('[data-zeile="betrieb-kuehlen"]')!.textContent).toBe('Kühlen1,0 h')
    expect(karte(aktiv.container, 'betrieb-heute')!.querySelector('[data-betrieb-ohne]')).toBeNull()
  })

  it('keine PV-Anteil-Karte, kein «seit»', () => {
    const { container } = render(<UeberblickKarte inv={wpInv(7)} live={live({ gauges: [EV], komponenten: [knoten(7, 1)] })} wetter={wetter(5)}
      tag={MIT_ZEILE({ betrieb_stunden: { heizen: 9.4 } })} mehrereGeraete={false} />)
    expect(container.textContent).not.toMatch(/aus PV|Strom heute aus|seit \d/)
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
