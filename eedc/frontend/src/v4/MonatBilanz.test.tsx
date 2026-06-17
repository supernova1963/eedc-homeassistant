import { describe, it, expect } from 'vitest'
import { baueMonatKpis } from './MonatBilanz'
import type { AktuellerMonatResponse } from '../api/aktuellerMonat'
import type { AggregierteMonatsdaten } from '../api/monatsdaten'

// baueMonatKpis liest nur eine Handvoll Felder — Teil-Fixture genügt.
function d(over: Partial<AktuellerMonatResponse> = {}): AktuellerMonatResponse {
  return {
    pv_erzeugung_kwh: 412, einspeisung_kwh: 189, netzbezug_kwh: 143,
    eigenverbrauch_kwh: 223, gesamtverbrauch_kwh: 366,
    autarkie_prozent: 61, eigenverbrauch_quote_prozent: 54,
    netto_ertrag_euro: 128, soll_pv_kwh: 450, vorjahr: null,
    ...over,
  } as AktuellerMonatResponse
}

const vm = { pv_erzeugung_kwh: 380, autarkie_prozent: 58, eigenverbrauch_kwh: 210, einspeisung_kwh: 170, netzbezug_kwh: 150 } as AggregierteMonatsdaten

describe('baueMonatKpis', () => {
  it('liefert 5 Energie-Cards + Netto-Ertrag (6)', () => {
    const k = baueMonatKpis(d(), vm)
    expect(k.map((x) => x.title)).toEqual([
      'PV-Erzeugung', 'Autarkie', 'Eigenverbrauch', 'Einspeisung', 'Netzbezug', 'Netto-Ertrag',
    ])
  })

  it('PV-Card trägt SOLL-Annotation (O2) statt VM, wenn SOLL vorhanden', () => {
    const pv = baueMonatKpis(d(), vm)[0]
    expect(pv.subtitle).toMatch(/SOLL 450 kWh · 92 %/) // 412/450 = 91,6 → 92
  })

  it('ohne SOLL fällt die PV-Card auf den Vormonat zurück', () => {
    const pv = baueMonatKpis(d({ soll_pv_kwh: null }), vm)[0]
    expect(pv.subtitle).toMatch(/VM: 380 kWh/)
  })

  it('andere Energie-Cards zeigen den Vormonat in der Zweitzeile', () => {
    const k = baueMonatKpis(d(), vm)
    expect(k.find((x) => x.title === 'Einspeisung')?.subtitle).toMatch(/VM: 170 kWh/)
    expect(k.find((x) => x.title === 'Netzbezug')?.subtitle).toMatch(/VM: 150 kWh/)
  })

  it('Netto-Ertrag in € ohne Vergleich', () => {
    const ne = baueMonatKpis(d(), vm).find((x) => x.title === 'Netto-Ertrag')!
    expect(ne.unit).toBe('€')
    expect(ne.value).toBe('128,00')
  })
})
