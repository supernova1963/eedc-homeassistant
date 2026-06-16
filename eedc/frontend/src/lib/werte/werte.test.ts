import { describe, it, expect, vi, beforeEach } from 'vitest'
import type { MonatsZeitreihe } from '../../pages/auswertung/types'
import {
  WERTE_METRIKEN, WERTE_GRUPPEN, METRIK_BY_KEY, getMonatWert,
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
    speicher_ladung: null, speicher_entladung: null, speicher_effizienz: null,
    wp_waerme: null, wp_strom: null, wp_cop: null,
    eauto_km: null, eauto_ladung: null, eauto_pv_anteil: null,
    einspeise_erloes: 5, ev_ersparnis: 12, netzbezug_kosten: 9,
    netto_ertrag: 8, netto_bilanz: 8, co2_einsparung: 25,
    ...over,
  }
}

describe('W1-Registry', () => {
  it('hat 23 Metriken, jede mit gültiger Gruppe', () => {
    expect(WERTE_METRIKEN).toHaveLength(23)
    for (const m of WERTE_METRIKEN) expect(WERTE_GRUPPEN).toContain(m.gruppe)
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
})

describe('aggregiere', () => {
  const rows = [mz(1, 2025, { erzeugung: 100, autarkie: 60 }), mz(2, 2025, { erzeugung: 200, autarkie: 80 })]
  it('summiert sum-Metriken', () => {
    expect(aggregiere(rows)['erzeugung']).toBe(300)
  })
  it('mittelt avg-Metriken', () => {
    expect(aggregiere(rows)['autarkie']).toBe(70)
  })
  it('liefert null für leere Spalte (alle null)', () => {
    expect(aggregiere(rows)['speicher_ladung']).toBeNull()
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
  const rows = [mz(1, 2025), mz(2, 2025)]
  const metriken = [METRIK_BY_KEY['erzeugung'], METRIK_BY_KEY['autarkie']]

  it('ohne Vergleich: Jahr/Monat + eine Spalte je Metrik + Agg-Zeile', () => {
    exportWerteCsv({ rows, vorjahrRows: null, jahrLabel: 2025, vergleichLabel: null, metriken, dateiname: 'x.csv' })
    const [headers, out, name] = vi.mocked(exportToCSV).mock.calls[0]
    expect(headers.slice(0, 2)).toEqual(['Jahr', 'Monat'])
    expect(headers).toContain('PV-Erzeugung (kWh)')
    expect(name).toBe('x.csv')
    // letzte Zeile = Aggregat („2 Monate")
    expect(out[out.length - 1][1]).toBe('2 Monate')
  })

  it('mit Vergleich: drei Spalten je Metrik inkl. Δ-Header', () => {
    exportWerteCsv({ rows, vorjahrRows: [mz(1, 2024), mz(2, 2024)], jahrLabel: 2025, vergleichLabel: 2024, metriken, dateiname: 'x.csv' })
    const [headers] = vi.mocked(exportToCSV).mock.calls[0]
    expect(headers).toContain('PV-Erzeugung (kWh) 2025')
    expect(headers).toContain('PV-Erzeugung (kWh) 2024')
    expect(headers).toContain('Δ vs. 2024')
  })
})
