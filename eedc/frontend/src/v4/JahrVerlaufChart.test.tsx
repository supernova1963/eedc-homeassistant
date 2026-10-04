import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { baueJahrChartDaten, jahrTooltipWert } from './JahrVerlaufChart'
import { verlaufTabellenSpalten } from './verlaufVergleich'
import { ChartTooltip } from '../components/ui'
import type { AggregierteMonatsdaten } from '../api/monatsdaten'
import { monatsZeile } from '../test/factories'

const md = (jahr: number, monat: number, over: Partial<AggregierteMonatsdaten> = {}) =>
  monatsZeile(jahr, monat, {
    eigenverbrauch_kwh: 180, einspeisung_kwh: 120, netzbezug_kwh: 90,
    direktverbrauch_kwh: 140, speicher_entladung_kwh: 40, autarkie_prozent: 66,
    pv_module_kwh: 300, bkw_kwh: 20, einspeisung_neg_preis_kwh: 5,
    speicher_ladung_kwh: 50, speicher_netzladung_kwh: 8,
    eauto_ladung_kwh: 60, eauto_km: 400,
    ...over,
  })

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

  // N-621: der Anteil eines Balkonkraftwerks ohne eigenen Wert am gespeicherten Anlagenwert steckt im
  // `bkw_kwh` der Antwort (eigene 20 + Anteil 50), nicht in `pv_module_kwh` — PV-Anlage + BKW = Erzeugung (1000).
  it('BKW-Serie trägt den Anteil am Anlagenwert mit, Σ mit PV-Anlage = Erzeugung (N-621)', () => {
    const d = baueJahrChartDaten([md(2025, 5, {
      pv_erzeugung_kwh: 1000, pv_module_kwh: 930, bkw_kwh: 70, bkw_aus_anlagenwert_kwh: 50,
    })])
    expect(d[0].pvAnlage).toBe(930)
    expect(d[0].bkw).toBe(70)
    expect(d[0].pvAnlage + d[0].bkw).toBe(1000)
  })

  // N-621 (Fachentscheid Master): der Anteil am Anlagenwert in der BKW-Serie ist geschätzt und wird so genannt —
  // im Tooltip und in der Tabellenansicht, nur wenn er > 0 ist. Der Client zeigt das Feld, er rechnet es nicht.
  it('Tooltip der BKW-Serie nennt „davon geschätzt (kWp-Anteil)" aus dem gelieferten Feld (N-621)', () => {
    const [p] = baueJahrChartDaten([md(2025, 5, { pv_module_kwh: 930, bkw_kwh: 70, bkw_aus_anlagenwert_kwh: 50 })])
    expect(p.bkwGeschaetzt).toBe(50)
    render(<ChartTooltip active label="Mai"
      payload={[{ name: 'Balkonkraftwerk', value: p.bkw, payload: p as unknown as Record<string, unknown> }]}
      formatter={jahrTooltipWert} />)
    expect(screen.getByText('70,0 kWh · davon geschätzt (kWp-Anteil): 50,0 kWh')).toBeTruthy()
  })

  it('ohne Anteil bleibt der Tooltip der BKW-Serie ohne Zusatz, die Tabelle ohne Spalte (N-621)', () => {
    const [p] = baueJahrChartDaten([md(2025, 5, { bkw_kwh: 20, bkw_aus_anlagenwert_kwh: 0 })])
    expect(jahrTooltipWert(p.bkw, 'Balkonkraftwerk', p as unknown as Record<string, unknown>)).toBe('20,0 kWh')
    expect(verlaufTabellenSpalten(true).some((s) => s.key === 'bkwGeschaetzt')).toBe(false)
    expect(verlaufTabellenSpalten(true, true).find((s) => s.key === 'bkwGeschaetzt')?.label)
      .toBe('Balkonkraftwerk, davon geschätzt (kWp-Anteil)')
  })

  // N-121: ein Monat ohne Monatsabschluss wird aus der lokalen Tagesebene
  // gerechnet. Additiv ⇒ beschriften, nicht unterdrücken
  // (docs/KONZEPT-UNVOLLSTAENDIGE-WERTE.md) — der Tooltip hängt an dieser Marke.
  it('markiert Monate, deren Größen aus Tageswerten stammen', () => {
    const d = baueJahrChartDaten([
      md(2026, 6),
      md(2026, 7, { aus_tageswerten: ['pv', 'zaehler'] }),
    ])
    expect(d.map((p) => p.ausTageswerten)).toEqual([false, true])
  })

  it('ein gepflegter Monat bleibt unmarkiert — auch bei leerer Liste', () => {
    // Die Route liefert `null`, wenn nichts aus Tageswerten kommt. Ein leeres
    // Array darf genauso wenig markieren, sonst trüge jede Zeile den Hinweis.
    const d = baueJahrChartDaten([
      md(2026, 1),
      md(2026, 2, { aus_tageswerten: null }),
      md(2026, 3, { aus_tageswerten: [] }),
    ])
    expect(d.every((p) => !p.ausTageswerten)).toBe(true)
  })
})
