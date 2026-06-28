/**
 * Render-Tests der aus `pages/LiveDashboard.tsx` extrahierten Live-Bausteine
 * (IA-V4 A.3) — sichern die geteilte Code-Wahrheit (IST-Live + Cockpit/Live).
 */
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import LiveHeuteKacheln from './LiveHeuteKacheln'
import LiveSocBalken from './LiveSocBalken'
import LiveTemperaturen from './LiveTemperaturen'
import SolarAussicht3Tage from './SolarAussicht3Tage'
import type { LiveDashboardResponse, LiveGauge } from '../../api/liveDashboard'
import type { SolarPrognoseTag } from '../../api/wetter'

const heute = (over: Partial<LiveDashboardResponse> = {}): LiveDashboardResponse =>
  ({
    heute_pv_kwh: 20, heute_einspeisung_kwh: 5, heute_netzbezug_kwh: 2,
    heute_eigenverbrauch_kwh: 8, gestern_pv_kwh: null, gestern_einspeisung_kwh: null,
    gestern_netzbezug_kwh: null, gestern_eigenverbrauch_kwh: null,
    heute_kwh_pro_komponente: null, warmwasser_temperatur_c: null, gauges: [],
    ...over,
  }) as unknown as LiveDashboardResponse

describe('LiveHeuteKacheln', () => {
  it('rendert PV-Erzeugung, Einspeisung + abgeleitete Autarkie/EV-Quote', () => {
    render(<LiveHeuteKacheln data={heute()} />)
    expect(screen.getByText('PV-Erzeugung')).toBeInTheDocument()
    expect(screen.getByText('Einspeisung')).toBeInTheDocument()
    expect(screen.getByText('Autarkie')).toBeInTheDocument()
    expect(screen.getByText('20,0')).toBeInTheDocument() // PV heute (de-DE)
    expect(screen.getByText('80')).toBeInTheDocument()    // Autarkie 8/(8+2)
  })

  it('rendert nichts, wenn keine Tageswerte vorliegen', () => {
    const { container } = render(
      <LiveHeuteKacheln data={heute({ heute_pv_kwh: null, heute_einspeisung_kwh: null, heute_netzbezug_kwh: null })} />,
    )
    expect(container).toBeEmptyDOMElement()
  })
})

describe('LiveSocBalken', () => {
  const soc = (key: string, label: string, wert: number): LiveGauge =>
    ({ key, label, wert, min_wert: 0, max_wert: 100, einheit: '%' })

  it('rendert nur soc_*-Gauges', () => {
    render(<LiveSocBalken gauges={[soc('soc_3', 'Batterie', 72), { key: 'netz', label: 'Netz', wert: 150, min_wert: -3000, max_wert: 3000, einheit: 'W' } as LiveGauge]} />)
    expect(screen.getByText('Ladezustand')).toBeInTheDocument()
    expect(screen.getByText('Batterie')).toBeInTheDocument()
    expect(screen.queryByText('Netz')).not.toBeInTheDocument()
  })

  it('rendert nichts ohne soc-Gauges', () => {
    const { container } = render(<LiveSocBalken gauges={[]} />)
    expect(container).toBeEmptyDOMElement()
  })
})

describe('LiveTemperaturen', () => {
  it('rendert Außen + Warmwasser', () => {
    render(<LiveTemperaturen aussenC={12.4} tempMinC={5} tempMaxC={18} warmwasserC={52.3} />)
    expect(screen.getByText('Außen Temperatur')).toBeInTheDocument()
    expect(screen.getByText('Warmwasser Temperatur')).toBeInTheDocument()
  })

  it('rendert nichts, wenn keine Temperatur vorliegt', () => {
    const { container } = render(<LiveTemperaturen aussenC={null} tempMinC={null} tempMaxC={null} warmwasserC={null} />)
    expect(container).toBeEmptyDOMElement()
  })
})

describe('SolarAussicht3Tage', () => {
  const tag = (datum: string, kwh: number): SolarPrognoseTag => ({ datum, pv_ertrag_kwh: kwh } as SolarPrognoseTag)

  it('rendert Heute/Morgen/Übermorgen-Zeilen', () => {
    render(
      <SolarAussicht3Tage
        prognose3Tage={[tag('2026-06-22', 30), tag('2026-06-23', 25), tag('2026-06-24', 28)]}
        wetter={null}
        heutePvKwh={10}
      />,
    )
    expect(screen.getByText('Heute')).toBeInTheDocument()
    expect(screen.getByText('Morgen')).toBeInTheDocument()
    expect(screen.getByText('Übermorgen')).toBeInTheDocument()
  })

  it('rendert nichts ohne Prognose', () => {
    const { container } = render(<SolarAussicht3Tage prognose3Tage={[]} wetter={null} heutePvKwh={null} />)
    expect(container).toBeEmptyDOMElement()
  })
})
