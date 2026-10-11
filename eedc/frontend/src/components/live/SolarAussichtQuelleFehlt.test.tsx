/**
 * N-689: Die Solar-Aussicht zeigt die Zahlen der gewählten Quelle, wenn die
 * Antwort sie trägt — und sagt es, wenn sie fehlen.
 *
 * Bis 11.10.2026 strich das Antwortmodell der Route `GET /live/{id}/wetter`
 * das Feld `prognose_quelle_tage` aus jeder Antwort. Die Kachel fiel dann für
 * Morgen/Übermorgen still auf den eedc-Kanon zurück — unter der Überschrift
 * „Solar-Aussicht (Solcast)" bzw. „(SFML)" und ohne den „eedc"-Vermerk, den
 * sie für genau diesen Fall hat. Die Antwortform unten ist die, die das
 * Backend seit N-689 über HTTP liefert (`test_n689_live_wetter_antwortmodell.py`).
 */
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import SolarAussicht3Tage from './SolarAussicht3Tage'
import type { LiveWetterResponse } from '../../api/liveDashboard'
import type { SolarPrognoseTag } from '../../api/wetter'

const tag = (datum: string, kwh: number): SolarPrognoseTag =>
  ({ datum, pv_ertrag_kwh: kwh } as SolarPrognoseTag)
// Der eedc-Kanon: 17,6 · 25,0 · 28,0
const kanon = [tag('2026-10-11', 17.6), tag('2026-10-12', 25), tag('2026-10-13', 28)]

const solcast = (over: Record<string, unknown>) => ({
  sunset: '23:59', verbrauchsprofil: [], prognose_quelle: 'solcast',
  pv_prognose_kwh: 18.6, pv_prognose_rest_kwh: null, pv_prognose_heute_rollend_kwh: null,
  ...over,
} as unknown as LiveWetterResponse)

describe('N-689: Folgetage der gewählten Quelle', () => {
  it('zeigt die Quellenwerte, wenn die Antwort sie trägt — ohne eedc-Vermerk', () => {
    const w = solcast({
      prognose_quelle_tage: [
        { datum: '2026-10-11', kwh: 18.6, vm_kwh: 8.1, nm_kwh: 10.5, rueckfall: null },
        { datum: '2026-10-12', kwh: 24.4, vm_kwh: null, nm_kwh: null, rueckfall: null },
        { datum: '2026-10-13', kwh: 9.7, vm_kwh: null, nm_kwh: null, rueckfall: null },
      ],
      prognose_quelle_hat_profil: true,
    })
    render(<SolarAussicht3Tage prognose3Tage={kanon} wetter={w} heutePvKwh={null} />)
    expect(screen.getByText('24,4')).toBeInTheDocument()       // Solcast-Morgen
    expect(screen.getByText('9,7')).toBeInTheDocument()        // Solcast-Übermorgen
    expect(screen.queryByText('25,0')).not.toBeInTheDocument() // NICHT der Kanon
    expect(screen.queryByText('28,0')).not.toBeInTheDocument()
    expect(screen.queryByText('eedc')).not.toBeInTheDocument()
  })

  it('fällt ohne das Feld auf den Kanon zurück — und weist es an beiden Folgetagen aus', () => {
    // ⛔ Der Zustand bis N-689: die Antwort trug das Feld nicht. Dann darf die
    // eedc-Zahl unter der Solcast-Überschrift nicht stumm stehen.
    const w = solcast({})
    render(<SolarAussicht3Tage prognose3Tage={kanon} wetter={w} heutePvKwh={null} />)
    expect(screen.getByText('25,0')).toBeInTheDocument()       // Kanon-Morgen
    expect(screen.getByText('28,0')).toBeInTheDocument()       // Kanon-Übermorgen
    expect(screen.getAllByText('eedc')).toHaveLength(2)        // Vermerk Morgen + Übermorgen
    expect(screen.getByText('18,6')).toBeInTheDocument()       // Heute: Tageswert der Quelle
  })

  it('setzt bei eedc als Quelle keinen Vermerk, auch ohne das Feld', () => {
    const w = solcast({ prognose_quelle: 'eedc', pv_prognose_kwh: 17.6 })
    render(<SolarAussicht3Tage prognose3Tage={kanon} wetter={w} heutePvKwh={null} />)
    expect(screen.queryByText('eedc')).not.toBeInTheDocument()
    expect(screen.getByText('25,0')).toBeInTheDocument()
  })
})
