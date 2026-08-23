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
import type { LiveDashboardResponse, LiveGauge, LiveWetterResponse } from '../../api/liveDashboard'
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

  // 0 ≠ nicht vorhanden ([[feedback_sensor_ableitbar_nicht_weglassen]], Erweiterung
  // 2026-07-25). Die „verbl."-Zeile ist eine Differenz aus Tagesprognose und
  // bereits erzeugter Menge — ist die Menge unbekannt, gibt es keine Differenz.
  // Forum #22 (Algie, 2026-07-28): `?? 0` machte daraus „nichts erzeugt" und die
  // Zeile behauptete die volle Tagesprognose als ausstehend (60,4 kWh Prognose →
  // „~60,4 verbl."), obwohl die Anlage längst lieferte.
  describe('„verbleibend" ist der gemessene Rest, nicht die Differenz', () => {
    const drei = [tag('2026-07-28', 60.4), tag('2026-07-29', 52.9), tag('2026-07-30', 40.6)]
    // sunset spät genug, damit der Nach-Sonnenuntergang-Zweig nicht greift.
    const basis = { pv_prognose_kwh: 60.4, sunset: '23:59', verbrauchsprofil: [] }
    const wetter = basis as unknown as LiveWetterResponse

    it('nimmt den Rest aus der Route — rapahls Fall (PN 2026-08-23)', () => {
      // Seine Zahlen: Tagesprognose 35,7 · bereits erzeugt 29,8 · Restprognose
      // 12,0. Die alte Rechnung (Prognose − IST) ergab 5,9 und behauptete
      // damit, der Tag sei fast durch — während die Sonne noch 12 kWh lieferte.
      const seins = {
        ...basis,
        pv_prognose_kwh: 35.7,
        pv_prognose_rest_kwh: 12.0,
        pv_prognose_heute_rollend_kwh: 41.8,
      } as unknown as LiveWetterResponse
      render(
        <SolarAussicht3Tage
          prognose3Tage={[tag('2026-08-23', 35.7), drei[1], drei[2]]}
          wetter={seins}
          heutePvKwh={29.8}
        />,
      )
      expect(screen.getByText(/~12,0 verbl\./)).toBeInTheDocument()
      expect(screen.queryByText(/~5,9 verbl\./)).not.toBeInTheDocument()
    })

    it('zeigt die Tagesabweichung, sobald sie über dem Rauschen liegt', () => {
      // 41,8 gegen 35,7 sind +17 % — der Tag läuft besser als vorhergesagt.
      const seins = {
        ...basis,
        pv_prognose_kwh: 35.7,
        pv_prognose_rest_kwh: 12.0,
        pv_prognose_heute_rollend_kwh: 41.8,
      } as unknown as LiveWetterResponse
      render(<SolarAussicht3Tage prognose3Tage={drei} wetter={seins} heutePvKwh={29.8} />)
      expect(screen.getByText(/\(\+17 %\)/)).toBeInTheDocument()
    })

    it('schweigt bei kleiner Abweichung — 3 % sind kein Signal', () => {
      const knapp = {
        ...basis,
        pv_prognose_kwh: 60.4,
        pv_prognose_rest_kwh: 8.0,
        pv_prognose_heute_rollend_kwh: 62.2,   // +3 %
      } as unknown as LiveWetterResponse
      render(<SolarAussicht3Tage prognose3Tage={drei} wetter={knapp} heutePvKwh={54.2} />)
      expect(screen.getByText(/~8,0 verbl\./)).toBeInTheDocument()
      expect(screen.queryByText(/%\)/)).not.toBeInTheDocument()
    })

    // Forum #22 (Algie, 2026-07-28) — die Lehre gilt weiter, nur an anderer
    // Stelle: Damals machte `?? 0` aus „Erzeugung unbekannt" ein „nichts
    // erzeugt", und die Zeile behauptete die volle Tagesprognose als
    // ausstehend. Seit der Rest aus der Route kommt, ist er von der
    // IST-Kenntnis unabhängig — die ABWEICHUNG ist es nicht: Ohne IST bestünde
    // der nachgeführte Wert nur aus dem Rest und läse sich als Einbruch.
    it('zeigt keine Abweichung, wenn die heutige Erzeugung unbekannt ist', () => {
      const ohneIst = {
        ...basis,
        pv_prognose_rest_kwh: 20.0,
        pv_prognose_heute_rollend_kwh: 20.0,   // = nur der Rest, IST fehlt
      } as unknown as LiveWetterResponse
      render(<SolarAussicht3Tage prognose3Tage={drei} wetter={ohneIst} heutePvKwh={null} />)
      expect(screen.queryByText(/%\)/)).not.toBeInTheDocument()
      // Der Rest selbst bleibt sichtbar — er ist reine Prognose.
      expect(screen.getByText(/~20,0 verbl\./)).toBeInTheDocument()
      expect(screen.getByText('60,4')).toBeInTheDocument()
    })

    it('behandelt 0 als Aussage: die volle Restmenge steht aus', () => {
      const frueh = {
        ...basis,
        pv_prognose_rest_kwh: 60.4,
        pv_prognose_heute_rollend_kwh: 60.4,
      } as unknown as LiveWetterResponse
      render(<SolarAussicht3Tage prognose3Tage={drei} wetter={frueh} heutePvKwh={0} />)
      expect(screen.getByText('~60,4 verbl.')).toBeInTheDocument()
    })

    it('sagt nichts, wenn die Route keinen Rest liefert', () => {
      render(<SolarAussicht3Tage prognose3Tage={drei} wetter={wetter} heutePvKwh={10} />)
      expect(screen.queryByText(/verbl\./)).not.toBeInTheDocument()
    })
  })
})
