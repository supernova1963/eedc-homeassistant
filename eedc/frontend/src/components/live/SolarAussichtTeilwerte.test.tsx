/**
 * N-695 / N-696: Die Solar-Aussicht sagt es an jeder Zahl, die nicht aus der
 * gewählten Quelle kommt — auch an Vormittag/Nachmittag.
 *
 * N-695: Solcast liefert im Live-Pfad nur für heute einen Stundenverlauf. Für
 * Morgen/Übermorgen stand die Solcast-Tageszahl (24,4 · 9,7) neben VM/NM aus
 * dem eedc-Kanon (11,0/14,0 · 13,0/15,0) — ohne Vermerk, und die Teile
 * addierten sich nicht zur Kopfzahl (#401: 9,7 kWh über 13 + 15). Seit N-695
 * trägt jeder Tag `vm_nm_rueckfall` (Backend `_prognose_quelle_tage`), und die
 * Kachel schreibt „eedc" an die Teilwerte. Dieselbe Regel gilt für SFML ohne
 * `forecast`-Attribut (an keinem Tag ein Stundenverlauf).
 *
 * N-696: Liefert Solcast für heute nichts, schaltet das Backend wie bei SFML
 * auf eedc um (`prognose_quelle: 'eedc'` + Hinweis) — die Kachel steht dann
 * nicht mehr unter „(Solcast)". Die Antwortformen unten sind die, die das
 * Backend seit N-695/N-696 liefert (`test_n695_*`, `test_n696_*`).
 */
import { describe, it, expect } from 'vitest'
import { fireEvent, render, screen, within } from '@testing-library/react'
import SolarAussicht3Tage from './SolarAussicht3Tage'
import type { LiveWetterResponse } from '../../api/liveDashboard'
import type { SolarPrognoseTag } from '../../api/wetter'

// Der eedc-Kanon mit VM/NM: 17,6 = 9,0 + 8,6 · 25,0 = 11,0 + 14,0 · 28,0 = 13,0 + 15,0
const tag = (datum: string, kwh: number, vm: number, nm: number): SolarPrognoseTag =>
  ({ datum, pv_ertrag_kwh: kwh, eedc_kwh: kwh, eedc_morgens_kwh: vm, eedc_nachmittags_kwh: nm } as SolarPrognoseTag)
const kanon = [
  tag('2026-10-11', 17.6, 9.0, 8.6),
  tag('2026-10-12', 25.0, 11.0, 14.0),
  tag('2026-10-13', 28.0, 13.0, 15.0),
]

const antwort = (over: Record<string, unknown>) => ({
  sunset: '23:59', verbrauchsprofil: [], prognose_quelle: 'solcast',
  pv_prognose_kwh: 18.6, pv_prognose_rest_kwh: null, pv_prognose_heute_rollend_kwh: null,
  ...over,
} as unknown as LiveWetterResponse)

const VERMERK_TEILWERT = /Vormittag\/Nachmittag stammen aus der eedc-Prognose/

describe('N-695: VM/NM ohne Stundenverlauf der Quelle tragen den Vermerk', () => {
  it('Solcast: Morgen/Übermorgen Tageszahl aus Solcast, VM/NM aus eedc — „eedc" an den Teilwerten', () => {
    const w = antwort({
      prognose_quelle_tage: [
        { datum: '2026-10-11', kwh: 18.6, vm_kwh: 8.1, nm_kwh: 10.5, rueckfall: null, vm_nm_rueckfall: null },
        { datum: '2026-10-12', kwh: 24.4, vm_kwh: null, nm_kwh: null, rueckfall: null, vm_nm_rueckfall: 'eedc' },
        { datum: '2026-10-13', kwh: 9.7, vm_kwh: null, nm_kwh: null, rueckfall: null, vm_nm_rueckfall: 'eedc' },
      ],
      prognose_quelle_hat_profil: true,
    })
    render(<SolarAussicht3Tage prognose3Tage={kanon} wetter={w} heutePvKwh={null} />)
    // Die Zahlen bleiben, wie sie sind: Kopfzahl Solcast, Teile eedc.
    expect(screen.getByText('24,4')).toBeInTheDocument()
    expect(screen.getByText('9,7')).toBeInTheDocument()
    expect(screen.getByText('13,0')).toBeInTheDocument()
    // Genau an den beiden Folgetagen steht der Vermerk an VM/NM — nicht am Tag.
    const vermerke = screen.getAllByTitle(VERMERK_TEILWERT)
    expect(vermerke).toHaveLength(2)
    expect(vermerke.every(v => v.textContent === 'eedc')).toBe(true)
    expect(screen.getAllByText('eedc')).toHaveLength(2)
  })

  it('Solcast mit Heute-Verlauf: Heute-VM/NM kommen aus Solcast und tragen keinen Vermerk', () => {
    const w = antwort({
      prognose_quelle_tage: [
        { datum: '2026-10-11', kwh: 18.6, vm_kwh: 8.1, nm_kwh: 10.5, rueckfall: null, vm_nm_rueckfall: null },
        { datum: '2026-10-12', kwh: 24.4, vm_kwh: null, nm_kwh: null, rueckfall: null, vm_nm_rueckfall: 'eedc' },
        { datum: '2026-10-13', kwh: 9.7, vm_kwh: null, nm_kwh: null, rueckfall: null, vm_nm_rueckfall: 'eedc' },
      ],
    })
    render(<SolarAussicht3Tage prognose3Tage={kanon} wetter={w} heutePvKwh={null} />)
    const heute = screen.getByText('Heute').closest('div') as HTMLElement
    expect(within(heute).getByText('8,1')).toBeInTheDocument()
    expect(within(heute).queryByText('eedc')).not.toBeInTheDocument()
  })

  it('SFML ohne forecast-Attribut: an allen drei Tagen „eedc" an VM/NM', () => {
    const w = antwort({
      prognose_quelle: 'sfml', pv_prognose_kwh: 28.7,
      prognose_quelle_tage: [
        { datum: '2026-10-11', kwh: 28.7, vm_kwh: null, nm_kwh: null, rueckfall: null, vm_nm_rueckfall: 'eedc' },
        { datum: '2026-10-12', kwh: 42.9, vm_kwh: null, nm_kwh: null, rueckfall: null, vm_nm_rueckfall: 'eedc' },
        { datum: '2026-10-13', kwh: 31.0, vm_kwh: null, nm_kwh: null, rueckfall: null, vm_nm_rueckfall: 'eedc' },
      ],
      prognose_quelle_hat_profil: false,
    })
    render(<SolarAussicht3Tage prognose3Tage={kanon} wetter={w} heutePvKwh={null} />)
    expect(screen.getAllByTitle(VERMERK_TEILWERT)).toHaveLength(3)
  })

  it('Tag ganz aus eedc: der Vermerk steht einmal am Tag, nicht zusätzlich an VM/NM', () => {
    const w = antwort({
      prognose_quelle_tage: [
        { datum: '2026-10-11', kwh: 18.6, vm_kwh: 8.1, nm_kwh: 10.5, rueckfall: null, vm_nm_rueckfall: null },
        { datum: '2026-10-12', kwh: null, vm_kwh: null, nm_kwh: null, rueckfall: 'eedc', vm_nm_rueckfall: 'eedc' },
        { datum: '2026-10-13', kwh: null, vm_kwh: null, nm_kwh: null, rueckfall: 'eedc', vm_nm_rueckfall: 'eedc' },
      ],
    })
    render(<SolarAussicht3Tage prognose3Tage={kanon} wetter={w} heutePvKwh={null} />)
    expect(screen.getAllByText('eedc')).toHaveLength(2)                  // je Folgetag einmal
    expect(screen.queryAllByTitle(VERMERK_TEILWERT)).toHaveLength(0)     // nicht doppelt
    expect(screen.getByText('25,0')).toBeInTheDocument()
  })

  it('der Tooltip verspricht nicht mehr „alle Zahlen aus derselben Quelle" und nennt den VM/NM-Vermerk', () => {
    const w = antwort({})
    render(<SolarAussicht3Tage prognose3Tage={kanon} wetter={w} heutePvKwh={null} />)
    const ausloeser = screen.getByRole('heading').querySelector('.cursor-help') as HTMLElement
    fireEvent.mouseEnter(ausloeser)
    const text = screen.getByRole('heading').textContent ?? ''
    expect(text).toMatch(/Zahlen aus der gewählten Quelle/)   // Tooltip ist offen
    expect(text).not.toMatch(/Alle Zahlen aus derselben Quelle/)
    expect(text).toMatch(/„eedc" steht an VM\/NM/)
  })
})

describe('N-696: Solcast liefert heute nichts', () => {
  it('die Kachel steht nicht unter „(Solcast)", wenn das Backend auf eedc umgeschaltet hat', () => {
    // Antwortform seit N-696 (wie der SFML-Rückfall): Quelle eedc + Hinweis, keine Quellen-Tage.
    const w = antwort({
      prognose_quelle: 'eedc', pv_prognose_kwh: 17.6,
      prognose_quelle_hinweis: 'Solcast liefert aktuell keine Daten, eedc-Prognose aktiv.',
      prognose_quelle_tage: null, prognose_quelle_hat_profil: false,
    })
    render(<SolarAussicht3Tage prognose3Tage={kanon} wetter={w} heutePvKwh={null} />)
    const kopf = screen.getByRole('heading')
    expect(kopf.textContent).not.toMatch(/Solcast/)
    expect(screen.getByText('17,6')).toBeInTheDocument()
    expect(screen.queryByText('eedc')).not.toBeInTheDocument()
  })
})
