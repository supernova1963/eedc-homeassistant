import { describe, it, expect } from 'vitest'
import { baueJahrChartDaten } from './JahrVerlaufChart'
import type { AggregierteMonatsdaten } from '../api/monatsdaten'

function md(jahr: number, monat: number, over: Partial<AggregierteMonatsdaten> = {}): AggregierteMonatsdaten {
  return {
    jahr, monat,
    eigenverbrauch_kwh: 180, einspeisung_kwh: 120, netzbezug_kwh: 90,
    direktverbrauch_kwh: 140, speicher_entladung_kwh: 40, autarkie_prozent: 66,
    pv_module_kwh: 300, bkw_kwh: 20, einspeisung_neg_preis_kwh: 5,
    speicher_ladung_kwh: 50, speicher_netzladung_kwh: 8,
    eauto_ladung_kwh: 60, eauto_km: 400,
    ...over,
  } as unknown as AggregierteMonatsdaten
}

describe('baueJahrChartDaten', () => {
  it('eine Zeile je Monat, aufsteigend nach Monat sortiert', () => {
    const d = baueJahrChartDaten([md(2025, 3), md(2025, 1), md(2025, 2)])
    expect(d.map((p) => p.monatNr)).toEqual([1, 2, 3])
  })

  it('trägt jahr + monatNr je Punkt (Drill-in-Ziel Cockpit/Monat, B3)', () => {
    const d = baueJahrChartDaten([md(2025, 5)])
    expect(d[0].jahr).toBe(2025)
    expect(d[0].monatNr).toBe(5)
  })

  it('mappt die Vergleich-Serien (PV-Anlage/BKW/§51/Netzladung/E-Auto)', () => {
    const d = baueJahrChartDaten([md(2025, 5)])
    expect(d[0].pvAnlage).toBe(300)
    expect(d[0].bkw).toBe(20)
    expect(d[0].neg51).toBe(5)
    expect(d[0].netzladung).toBe(8)
    expect(d[0].eautoKm).toBe(400)
  })
})
