import { describe, it, expect, vi, beforeEach } from 'vitest'
import type { MonatsZeitreihe } from '../../pages/auswertung/types'
import type { TagWerte } from '../../api/energie_profil'
import {
  WERTE_METRIKEN, WERTE_GRUPPEN, METRIK_BY_KEY, getMonatWert, getTagWert,
  metrikenFuer, monatsZeile, tagesZeile,
  aggregiere, bewerteDelta, exportWerteCsv,
} from './index'

// exportToCSV löst im echten Code einen Download aus — fürs Schema-Testen mocken.
vi.mock('../../utils/export', () => ({ exportToCSV: vi.fn() }))
import { exportToCSV } from '../../utils/export'

function mz(monat: number, jahr: number, over: Partial<MonatsZeitreihe> = {}): MonatsZeitreihe {
  return {
    name: `${monat}/${jahr}`, jahr, monat,
    erzeugung: 100, eigenverbrauch: 60, einspeisung: 40, netzbezug: 30,
    gesamtverbrauch: 90, direktverbrauch: 50,
    autarkie: 70, evQuote: 60, spezErtrag: 80,
    globalstrahlung: null, sonnenstunden: null,
    speicher_ladung: null, speicher_entladung: null, speicher_effizienz: null,
    wp_waerme: null, wp_strom: null, wp_cop: null,
    wp_strom_heizen: null, wp_strom_warmwasser: null,
    wp_waerme_heizen: null, wp_waerme_warmwasser: null,
    eauto_km: null, eauto_ladung: null, eauto_pv_anteil: null,
    wallbox_ladung: null, wallbox_pv_ladung: null, wallbox_pv_anteil: null,
    einspeise_erloes: 5, ev_ersparnis: 12, netzbezug_kosten: 9,
    netto_ertrag: 8, netto_bilanz: 8, netzbezug_preis_cent: null, co2_einsparung: 25,
    ...over,
  }
}

function tw(datum: string, over: Partial<TagWerte> = {}): TagWerte {
  return {
    datum, stunden_verfuegbar: 24, datenquelle: 'ha_sensor',
    erzeugung: 30, eigenverbrauch: 18, einspeisung: 12, netzbezug: 6,
    gesamtverbrauch: 24, direktverbrauch: 15,
    autarkie: 75, evQuote: 60, spezErtrag: 3,
    speicher_ladung: null, speicher_entladung: null, speicher_effizienz: null,
    wp_strom: null,
    einspeise_erloes: 1, ev_ersparnis: 2, netzbezug_kosten: 1.5,
    netto_ertrag: 3, netto_bilanz: 1.5, co2_einsparung: 11.4,
    ueberschuss_kwh: 8, defizit_kwh: 2, peak_pv_kw: 6.2,
    peak_netzbezug_kw: 1.1, peak_einspeisung_kw: 4.0,
    performance_ratio: 0.85, batterie_vollzyklen: 0.4,
    temperatur_min_c: 10, temperatur_max_c: 22,
    strahlung_summe_wh_m2: 5000, boersenpreis_avg_cent: 9.5,
    boersenpreis_min_cent: -1, negative_preis_stunden: 1,
    einspeisung_neg_preis_kwh: 0,
    ...over,
  }
}

describe('W1-Registry', () => {
  it('hat 43 Metriken (33 Monat + 10 Tag-native), jede mit gültiger Gruppe + granular', () => {
    expect(WERTE_METRIKEN).toHaveLength(43)
    for (const m of WERTE_METRIKEN) {
      expect(WERTE_GRUPPEN).toContain(m.gruppe)
      expect(m.granular.length).toBeGreaterThan(0)
    }
  })
  it('METRIK_BY_KEY findet per key', () => {
    expect(METRIK_BY_KEY['autarkie'].aggregation).toBe('avg')
    expect(METRIK_BY_KEY['erzeugung'].aggregation).toBe('sum')
  })
  it('getMonatWert liest Property bzw. null', () => {
    const r = mz(5, 2025, { erzeugung: 412 })
    expect(getMonatWert(r, 'erzeugung')).toBe(412)
    expect(getMonatWert(r, 'speicher_ladung')).toBeNull()
  })
  it('getTagWert liest Property bzw. null', () => {
    const r = tw('2026-05-10', { erzeugung: 41 })
    expect(getTagWert(r, 'erzeugung')).toBe(41)
    expect(getTagWert(r, 'peak_pv_kw')).toBe(6.2)
    expect(getTagWert(r, 'speicher_ladung')).toBeNull()
  })
})

describe('metrikenFuer (Granularität)', () => {
  it('Monat = 33 Registry-Metriken, kein Tag-natives Feld', () => {
    const m = metrikenFuer('monat')
    expect(m).toHaveLength(33)
    expect(m.find((x) => x.key === 'peak_pv_kw')).toBeUndefined()
    expect(m.find((x) => x.key === 'wp_waerme')).toBeDefined()
    // Vollständigkeits-Spalten (Gernot 2026-06-26): verfügbare Felder als wählbare Spalten.
    expect(m.find((x) => x.key === 'globalstrahlung')).toBeDefined()
    expect(m.find((x) => x.key === 'wallbox_pv_anteil')).toBeDefined()
    expect(m.find((x) => x.key === 'netzbezug_preis_cent')).toBeDefined()
  })
  it('Tag = ohne WP-Wärme/COP/E-Auto, mit Tag-nativen', () => {
    const keys = metrikenFuer('tag').map((x) => x.key)
    expect(keys).toContain('peak_pv_kw')
    expect(keys).toContain('ueberschuss_kwh')
    expect(keys).toContain('erzeugung')
    expect(keys).not.toContain('wp_waerme')
    expect(keys).not.toContain('eauto_km')
  })
})

describe('zeile-Normalisierung', () => {
  it('monatsZeile: Label/sortKey/vergleichKey', () => {
    const z = monatsZeile(mz(5, 2025, { erzeugung: 123 }))
    expect(z.vergleichKey).toBe(5)
    expect(z.sortKey).toBe(2025 * 100 + 5)
    expect(z.wert('erzeugung')).toBe(123)
  })
  it('tagesZeile: vergleichKey = Tag-im-Monat, sortKey aufsteigend', () => {
    const z = tagesZeile(tw('2026-05-10', { erzeugung: 41 }))
    expect(z.vergleichKey).toBe(10)
    expect(z.id).toBe('2026-05-10')
    expect(z.wert('erzeugung')).toBe(41)
    expect(z.wert('peak_pv_kw')).toBe(6.2)
    expect(tagesZeile(tw('2026-05-11')).sortKey).toBeGreaterThan(z.sortKey)
  })
})

describe('aggregiere', () => {
  const metriken = metrikenFuer('monat')
  const rows = [monatsZeile(mz(1, 2025, { erzeugung: 100, autarkie: 60 })), monatsZeile(mz(2, 2025, { erzeugung: 200, autarkie: 80 }))]
  it('summiert sum-Metriken', () => {
    expect(aggregiere(rows, metriken)['erzeugung']).toBe(300)
  })
  it('mittelt avg-Metriken', () => {
    expect(aggregiere(rows, metriken)['autarkie']).toBe(70)
  })
  it('liefert null für leere Spalte (alle null)', () => {
    expect(aggregiere(rows, metriken)['speicher_ladung']).toBeNull()
  })
  it('aggregiert Tageszeilen (Σ Überschuss)', () => {
    const tage = [tagesZeile(tw('2026-05-10', { ueberschuss_kwh: 8 })), tagesZeile(tw('2026-05-11', { ueberschuss_kwh: 5 }))]
    expect(aggregiere(tage, metrikenFuer('tag'))['ueberschuss_kwh']).toBe(13)
  })
})

describe('bewerteDelta', () => {
  it('höher-besser: Anstieg gut, Rückgang schlecht', () => {
    expect(bewerteDelta(120, 100, true)).toBe('gut')
    expect(bewerteDelta(80, 100, true)).toBe('schlecht')
  })
  it('niedriger-besser: Anstieg schlecht', () => {
    expect(bewerteDelta(120, 100, false)).toBe('schlecht')
    expect(bewerteDelta(80, 100, false)).toBe('gut')
  })
  it('neutral bei undefined, Gleichstand oder null', () => {
    expect(bewerteDelta(120, 100, undefined)).toBe('neutral')
    expect(bewerteDelta(100, 100, true)).toBe('neutral')
    expect(bewerteDelta(null, 100, true)).toBe('neutral')
  })
})

describe('exportWerteCsv (Schema)', () => {
  beforeEach(() => vi.mocked(exportToCSV).mockClear())
  const rows = [monatsZeile(mz(1, 2025)), monatsZeile(mz(2, 2025))]
  const metriken = [METRIK_BY_KEY['erzeugung'], METRIK_BY_KEY['autarkie']]

  it('ohne Vergleich: Zeitraum + eine Spalte je Metrik + Agg-Zeile', () => {
    exportWerteCsv({ rows, vorjahrRows: null, jahrLabel: 2025, vergleichLabel: null, metriken, einheitLabel: 'Monate', dateiname: 'x.csv' })
    const [headers, out, name] = vi.mocked(exportToCSV).mock.calls[0]
    expect(headers[0]).toBe('Zeitraum')
    expect(headers).toContain('PV-Erzeugung (kWh)')
    expect(name).toBe('x.csv')
    // letzte Zeile = Aggregat („2 Monate")
    expect(out[out.length - 1][0]).toBe('2 Monate')
  })

  it('Tages-Export nutzt Einheit „Tage"', () => {
    const tage = [tagesZeile(tw('2026-05-10')), tagesZeile(tw('2026-05-11'))]
    exportWerteCsv({ rows: tage, vorjahrRows: null, jahrLabel: 'Mai', vergleichLabel: null, metriken, einheitLabel: 'Tage', dateiname: 't.csv' })
    const [, out] = vi.mocked(exportToCSV).mock.calls[0]
    expect(out[out.length - 1][0]).toBe('2 Tage')
  })

  it('mit Vergleich: drei Spalten je Metrik inkl. Δ-Header', () => {
    exportWerteCsv({ rows, vorjahrRows: [monatsZeile(mz(1, 2024)), monatsZeile(mz(2, 2024))], jahrLabel: 2025, vergleichLabel: 2024, metriken, einheitLabel: 'Monate', dateiname: 'x.csv' })
    const [headers] = vi.mocked(exportToCSV).mock.calls[0]
    expect(headers).toContain('PV-Erzeugung (kWh) 2025')
    expect(headers).toContain('PV-Erzeugung (kWh) 2024')
    expect(headers).toContain('Δ vs. 2024')
  })
})
