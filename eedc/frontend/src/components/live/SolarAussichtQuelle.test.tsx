/**
 * Eine Quelle für alle Zahlen der Solar-Aussicht (Entscheid Gernot, 2026-08-30).
 *
 * Zwei Melder am selben Tag, aus entgegengesetzter Richtung:
 * * **Burkard** (#401): bei SFML standen 28,7 „heute" gegen 6,9 IST + 9,0 Rest.
 * * **rapahl** (PN 91821): bei eedc standen 17,6 „heute" gegen 23,5 kWh erzeugt.
 *
 * Beide Male stimmte die Bilanz nicht, weil die Kopfzahl die ursprüngliche
 * Tagesprognose war und die Zahlen darunter etwas anderes meinten.
 */
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import SolarAussicht3Tage from './SolarAussicht3Tage'
import type { LiveWetterResponse } from '../../api/liveDashboard'
import type { SolarPrognoseTag } from '../../api/wetter'

const tag = (datum: string, kwh: number): SolarPrognoseTag =>
  ({ datum, pv_ertrag_kwh: kwh } as SolarPrognoseTag)
const drei = [tag('2026-08-30', 17.6), tag('2026-08-31', 25), tag('2026-09-01', 28)]
const basis = { sunset: '23:59', verbrauchsprofil: [] }

describe('Kopfzahl „Heute" ist der nachgeführte Wert', () => {
  it('zeigt rollend oben und die Tagesprognose klein daneben — rapahls Fall', () => {
    // Seine Zahlen vom 30.08.: 23,5 kWh erzeugt, 1,7 Rest, Prognose 17,6.
    // 23,5 + 1,7 = 25,2 — die Bilanz, die ein Anwender nachrechnen kann.
    const seins = {
      ...basis, pv_prognose_kwh: 17.6, pv_prognose_rest_kwh: 1.7,
      pv_prognose_heute_rollend_kwh: 25.2,
    } as unknown as LiveWetterResponse
    render(<SolarAussicht3Tage prognose3Tage={drei} wetter={seins} heutePvKwh={23.5} />)
    expect(screen.getByText('25,2')).toBeInTheDocument()          // nachgeführt, oben
    expect(screen.getByText(/Prognose 17,6 kWh/)).toBeInTheDocument()  // Ursprung, klein
  })

  it('zeigt die Tagesprognose oben, solange die Erzeugung unbekannt ist', () => {
    // ⚠ Ohne bekanntes IST liefert der Kanon `ist_bisher` als 0,0 statt null —
    // die nachgeführte Zahl bestünde dann allein aus dem Rest und sähe nach
    // einem Einbruch aus, obwohl nur die Messung fehlt.
    const ohneIst = {
      ...basis, pv_prognose_kwh: 17.6, pv_prognose_rest_kwh: 1.7,
      pv_prognose_heute_rollend_kwh: 1.7,
    } as unknown as LiveWetterResponse
    render(<SolarAussicht3Tage prognose3Tage={drei} wetter={ohneIst} heutePvKwh={null} />)
    expect(screen.getByText('17,6')).toBeInTheDocument()
    expect(screen.queryByText(/Prognose 17,6 kWh/)).not.toBeInTheDocument()
  })
})

describe('Die Zahlen folgen der gewählten Quelle', () => {
  const mitQuelle = (over: Record<string, unknown>) => ({
    ...basis, prognose_quelle: 'sfml', pv_prognose_kwh: 28.7,
    pv_prognose_rest_kwh: 21.2, pv_prognose_heute_rollend_kwh: 28.1,
    ...over,
  } as unknown as LiveWetterResponse)

  it('nimmt Tageswert und VM/NM der Folgetage aus der Quelle, nicht aus dem Kanon', () => {
    // Der Kanon sagt für morgen 25 kWh (aus `drei`), SFML sagt 42,9.
    const w = mitQuelle({
      prognose_quelle_tage: [
        { datum: '2026-08-30', kwh: 28.7, vm_kwh: 12.0, nm_kwh: 16.7, rueckfall: null },
        { datum: '2026-08-31', kwh: 42.9, vm_kwh: 20.0, nm_kwh: 22.9, rueckfall: null },
        { datum: '2026-09-01', kwh: null, vm_kwh: null, nm_kwh: null, rueckfall: 'eedc' },
      ],
    })
    render(<SolarAussicht3Tage prognose3Tage={drei} wetter={w} heutePvKwh={6.9} />)
    expect(screen.getByText('42,9')).toBeInTheDocument()       // SFML-Morgen
    expect(screen.queryByText('25,0')).not.toBeInTheDocument() // NICHT der Kanon
    expect(screen.getByText('20,0')).toBeInTheDocument()       // VM aus SFML
  })

  it('weist den Rückfall aus, wo die Quelle einen Tag nicht abdeckt', () => {
    // ⭐ Der Punkt: eine eedc-Zahl darf nicht stumm unter der SFML-Überschrift
    // stehen. Burkards Punkt 3 war genau das, eine Sicht weiter.
    const w = mitQuelle({
      prognose_quelle_tage: [
        { datum: '2026-08-30', kwh: 28.7, vm_kwh: null, nm_kwh: null, rueckfall: null },
        { datum: '2026-08-31', kwh: null, vm_kwh: null, nm_kwh: null, rueckfall: 'eedc' },
        { datum: '2026-09-01', kwh: null, vm_kwh: null, nm_kwh: null, rueckfall: 'eedc' },
      ],
    })
    render(<SolarAussicht3Tage prognose3Tage={drei} wetter={w} heutePvKwh={6.9} />)
    expect(screen.getAllByText('eedc')).toHaveLength(2)
  })

  it('setzt keine Rückfall-Marke, wo die Quelle liefert', () => {
    const w = mitQuelle({
      prognose_quelle_tage: [
        { datum: '2026-08-30', kwh: 28.7, vm_kwh: null, nm_kwh: null, rueckfall: null },
        { datum: '2026-08-31', kwh: 42.9, vm_kwh: null, nm_kwh: null, rueckfall: null },
        { datum: '2026-09-01', kwh: 37.0, vm_kwh: null, nm_kwh: null, rueckfall: null },
      ],
    })
    render(<SolarAussicht3Tage prognose3Tage={drei} wetter={w} heutePvKwh={6.9} />)
    expect(screen.queryByText('eedc')).not.toBeInTheDocument()
  })
})
