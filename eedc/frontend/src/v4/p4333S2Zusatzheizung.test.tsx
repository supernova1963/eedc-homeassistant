/**
 * P-433-3 Sitzung 2 (#432, E-P3-5) — «AZ ohne Zusatzheizung» in Tag, Monat, Jahr, Hub und Monatstabelle.
 *
 * Die Zahl entsteht im Layer (`waermepumpe_kennzahl.arbeitszahl_ohne_zusatzheizung`, Backend-Proben
 * `test_p433_3_s2_heizstab_zusatzheizung.py`); der Client liest Wert ODER Grund, Zähler und Nenner und rechnet nichts
 * nach. Sie steht nur mit Heizstab-Zähler da (B2) — ohne ihn bleibt jede Sicht, wie sie war.
 *
 * Mathek-Lage (#432): 26 kWh Wärme, 6 kWh Strom, davon 0,4 kWh Heizstab ⇒ 25,6 ÷ 5,6 = 4,57.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'

const getWaermepumpeDashboard = vi.fn()
vi.mock('../api/investitionen', () => ({
  investitionenApi: { getWaermepumpeDashboard: (...a: unknown[]) => getWaermepumpeDashboard(...a) },
}))

import { wpFunktionsGruppen } from './wpFunktionsGruppen'
import { baueTagAlsMonat } from './TagKomponenten'
import type { TagDetail } from '../api/energie_profil'
import { baueKomponentenBloecke } from './KomponentenSektionen'
import { KOMPONENTEN_ADAPTER } from './komponentenAdapter'
import { WaermepumpeMonatsTabelle } from '../components/waermepumpe/WaermepumpeCharts'
import type { ParkApi } from '../components/park'
import type { AktuellerMonatResponse } from '../api/aktuellerMonat'
import type { WpMonatsWert } from '../api/investitionen'
import { aktuellerMonat, tagWerte } from '../test/factories'

const NOOP: ParkApi = {
  aktiv: false, istGeparkt: () => false, park: () => {}, entparke: () => {},
  zuruecksetzen: () => {}, geparkt: [], registriere: () => () => {}, parkbareAnzahl: 0,
}
const d = (over: Partial<AktuellerMonatResponse>) => aktuellerMonat(2026, 10, over)

const TAG: Partial<AktuellerMonatResponse> = {
  wp_strom_kwh: 6, wp_waerme_kwh: 26, wp_jaz: 4.33, wp_jaz_zaehler_kwh: 26, wp_jaz_nenner_kwh: 6,
}
const MIT_HEIZSTAB: Partial<AktuellerMonatResponse> = {
  ...TAG,
  wp_heizstab_kwh: 0.4, wp_jaz_ohne_zusatzheizung: 4.5714, wp_jaz_ohne_zusatzheizung_grund: null,
  wp_jaz_ohne_zusatzheizung_hinweis: 'gerechnet: Heizstab mit Wirkungsgrad 1 abgezogen',
  wp_jaz_ohne_zusatzheizung_zaehler_kwh: 25.6, wp_jaz_ohne_zusatzheizung_nenner_kwh: 5.6,
}

function rendereWp(over: Partial<AktuellerMonatResponse>) {
  const block = baueKomponentenBloecke(d(over), NOOP, 'tag').find((b) => b.id === 'k-waermepumpe')
  expect(block).toBeDefined()
  render(<>{block!.render(false)}</>)
}

describe('Tag «Je Funktion»: davon Zusatzheizung · AZ ohne Zusatzheizung', () => {
  it('ohne Heizstab-Zähler keine Zeile und kein Schlüssel', () => {
    expect(wpFunktionsGruppen(d(TAG)).zusatzheizung).toBeUndefined()
    rendereWp(TAG)
    expect(screen.queryByText('davon Zusatzheizung')).toBeNull()
  })

  it('Mathek: «0,4 kWh · AZ ohne Zusatzheizung 4,57 (gerechnet)», Herleitung beim Überfahren', () => {
    expect(wpFunktionsGruppen(d(MIT_HEIZSTAB)).zusatzheizung).toEqual({
      kwh: 0.4, az: 4.5714, grund: null, hinweis: 'gerechnet: Heizstab mit Wirkungsgrad 1 abgezogen',
      zaehlerKwh: 25.6, nennerKwh: 5.6,
    })
    rendereWp(MIT_HEIZSTAB)
    expect(screen.getByText('Je Funktion')).toBeInTheDocument()
    expect(screen.getByText('davon Zusatzheizung')).toBeInTheDocument()
    const wert = screen.getByText('0,4 kWh · AZ ohne Zusatzheizung 4,57 (gerechnet)')
    expect(wert.getAttribute('title')).toBe(
      'gerechnet: Heizstab mit Wirkungsgrad 1 abgezogen · 25,6 kWh Wärme ÷ 5,6 kWh Strom')
  })

  it('gesperrt: «—» ohne «(gerechnet)», der Grund beim Überfahren', () => {
    rendereWp({
      ...TAG, wp_heizstab_kwh: 7, wp_jaz_ohne_zusatzheizung: null,
      wp_jaz_ohne_zusatzheizung_grund: 'Zusatzheizung größer als der Gerätestrom',
    })
    const wert = screen.getByText('7,0 kWh · AZ ohne Zusatzheizung —')
    expect(wert.getAttribute('title')).toBe('Zusatzheizung größer als der Gerätestrom')
  })
})

describe('Nacharbeit: Monat und Jahr zeigen dieselbe Zeile (E-P3-5, eine Regel für alle Perioden)', () => {
  it.each(['monat', 'jahr'] as const)('%s: «davon Zusatzheizung …» aus denselben Feldern', (periode) => {
    const block = baueKomponentenBloecke(d(MIT_HEIZSTAB), NOOP, periode).find((b) => b.id === 'k-waermepumpe')
    render(<>{block!.render(false)}</>)
    expect(screen.getByText('0,4 kWh · AZ ohne Zusatzheizung 4,57 (gerechnet)')).toBeInTheDocument()
  })

  it('Geräte-Regel: «—» mit dem Grund «nicht alle Geräte melden Zusatzheizung»', () => {
    const block = baueKomponentenBloecke(d({
      ...TAG, wp_heizstab_kwh: 40, wp_jaz_ohne_zusatzheizung: null,
      wp_jaz_ohne_zusatzheizung_grund: 'nicht alle Geräte melden Zusatzheizung',
    }), NOOP, 'monat').find((b) => b.id === 'k-waermepumpe')
    render(<>{block!.render(false)}</>)
    expect(screen.getByText('40,0 kWh · AZ ohne Zusatzheizung —').getAttribute('title'))
      .toBe('nicht alle Geräte melden Zusatzheizung')
  })
})

describe('Tag: die Tagesantwort erreicht den Block', () => {
  it('baueTagAlsMonat reicht Heizstab-Strom und Ausweis-Zahl der Tagesantwort durch', () => {
    const tag = baueTagAlsMonat(tagWerte('2026-10-24', { wp_strom: 6 }), [], [], {
      wp_heizstab_kwh: 0.4, wp_jaz_ohne_zusatzheizung: 4.5714, wp_jaz_ohne_zusatzheizung_grund: null,
      wp_jaz_ohne_zusatzheizung_hinweis: 'gerechnet: Heizstab mit Wirkungsgrad 1 abgezogen',
      wp_jaz_ohne_zusatzheizung_zaehler_kwh: 25.6, wp_jaz_ohne_zusatzheizung_nenner_kwh: 5.6,
    } as TagDetail)
    expect(wpFunktionsGruppen(tag).zusatzheizung).toMatchObject({ kwh: 0.4, az: 4.5714, zaehlerKwh: 25.6, nennerKwh: 5.6 })
    const ohne = baueTagAlsMonat(tagWerte('2026-10-24', { wp_strom: 6 }), [], [], {} as TagDetail)
    expect(wpFunktionsGruppen(ohne).zusatzheizung).toBeUndefined()
  })
})

describe('Hub: Kennzahl «AZ ohne Zusatzheizung» neben der JAZ', () => {
  beforeEach(() => getWaermepumpeDashboard.mockReset())
  const hub = (z: Record<string, unknown>) => {
    getWaermepumpeDashboard.mockResolvedValue([{
      investition: { id: 1, anlage_id: 1, typ: 'waermepumpe', bezeichnung: 'WP', aktiv: true },
      zusammenfassung: { durchschnitt_cop: 4.33, gesamt_waerme_kwh: 2600, gesamt_stromverbrauch_kwh: 600,
        gesamt_heizenergie_kwh: 0, gesamt_warmwasser_kwh: 0, ersparnis_euro: 100, co2_ersparnis_kg: 50, ...z },
      monatsdaten: [],
    }])
    return KOMPONENTEN_ADAPTER.waermepumpe.fetch(1)
  }

  it('mit Zähler: Wert, Herkunft und Herleitung aus der Antwort; die JAZ bleibt die Hauptzahl', async () => {
    const [g] = await hub({
      gesamt_heizstab_kwh: 40, jaz_ohne_zusatzheizung: 4.57, jaz_ohne_zusatzheizung_grund: null,
      jaz_ohne_zusatzheizung_hinweis: 'gerechnet: Heizstab mit Wirkungsgrad 1 abgezogen',
      jaz_ohne_zusatzheizung_zaehler_kwh: 2560, jaz_ohne_zusatzheizung_nenner_kwh: 560,
    })
    expect(g.status[0].title).toBe('JAZ')
    const kpi = g.sekundaer!.kpis.find((x) => x.title === 'AZ ohne Zusatzheizung')!
    expect(kpi.value).toBe('4,57')
    expect(kpi.subtitle).toBe('gerechnet: Heizstab mit Wirkungsgrad 1 abgezogen')
    // P-433-3 S3-9: dieselbe Herleitung wie am Tag (`herleitungMengen`, eine Stelle, eine Nachkommastelle).
    expect(kpi.berechnung).toBe('2.560,0 kWh Wärme ÷ 560,0 kWh Strom')
  })

  it('gesperrt: «—» mit Grund; ohne Zähler keine Kachel', async () => {
    const [gesperrt] = await hub({
      gesamt_heizstab_kwh: 700, jaz_ohne_zusatzheizung: null,
      jaz_ohne_zusatzheizung_grund: 'Zusatzheizung größer als der Gerätestrom',
    })
    const kpi = gesperrt.sekundaer!.kpis.find((x) => x.title === 'AZ ohne Zusatzheizung')!
    expect([kpi.value, kpi.subtitle]).toEqual(['—', 'Zusatzheizung größer als der Gerätestrom'])
    const [ohne] = await hub({})
    expect((ohne.sekundaer?.kpis ?? []).some((x) => x.title === 'AZ ohne Zusatzheizung')).toBe(false)
  })
})

describe('Monatstabelle: Spalte «AZ ohne Zusatzheizung» nur mit Heizstab-Zähler', () => {
  const md = (monat: number): WpMonatsWert => ({
    jahr: 2026, monat, strom_kwh: 600, heizung_kwh: null, warmwasser_kwh: null, waerme_kwh: 2600,
  })
  const jaz = (monat: number, extra = {}) => ({
    jahr: 2026, monat, wert: 4.33, grund: null, zaehler_kwh: 2600, nenner_kwh: 600, ...extra,
  })

  it('ohne Heizstab: keine Spalte', () => {
    render(<WaermepumpeMonatsTabelle monatsreihe={[md(9)]} jazJeMonat={[jaz(9)]} hatWarmwasserAchse={false} />)
    expect(screen.queryByText('AZ ohne Zusatzheizung')).toBeNull()
  })

  it('mit Heizstab in einem Monat: Wert dort, leer im Monat ohne Zähler, Grund am Strich', () => {
    const { container } = render(<WaermepumpeMonatsTabelle
      monatsreihe={[md(9), md(10), md(11)]}
      jazJeMonat={[
        jaz(9),
        jaz(10, { heizstab_kwh: 40, ohne_zusatzheizung_wert: 4.57, ohne_zusatzheizung_zaehler_kwh: 2560,
          ohne_zusatzheizung_nenner_kwh: 560 }),
        jaz(11, { heizstab_kwh: 700, ohne_zusatzheizung_wert: null,
          ohne_zusatzheizung_grund: 'Zusatzheizung größer als der Gerätestrom' }),
      ]}
      hatWarmwasserAchse={false}
    />)
    expect(screen.getByText('AZ ohne Zusatzheizung')).toBeInTheDocument()
    const zellen = [...container.querySelectorAll('[data-spalte="ohne-zusatzheizung"]')]
    expect(zellen.map((z) => z.textContent)).toEqual(['', '4,57', '—'])
    expect(zellen[1].getAttribute('title')).toBe('Zusatzheizung 40 kWh · 2.560 ÷ 560 kWh')
    expect(zellen[2].getAttribute('title')).toBe('Zusatzheizung größer als der Gerätestrom')
  })
})
