/**
 * N-690 (ADR-002 P4): eine Teilsumme sagt es selbst.
 *
 * Fallen lokaler und Kanon-Fan-out gleichzeitig unvollständig aus, bleibt in
 * Cockpit → Live der lokale, um die ausgefallenen PV-Teilanlagen zu kleine
 * Tageswert stehen. Das Backend lässt die Zahl stehen und liefert seit N-690
 * `pv_prognose_hinweis` (`test_n690_live_wetter_teilsumme.py`); beide
 * Darsteller des Tageswerts zeigen den Satz — das Wetter-Widget („~x kWh PV",
 * PV-Kurve) und die Heute-Zeile der Solar-Aussicht.
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import WetterWidget from './WetterWidget'
import SolarAussicht3Tage from './SolarAussicht3Tage'
import { renderMitProvidern, stubMatchMedia } from '../../test/render'
import type { LiveWetterResponse } from '../../api/liveDashboard'
import type { SolarPrognoseTag } from '../../api/wetter'

const HINWEIS = 'Der Wetterabruf war unvollständig: nicht alle PV-Teilanlagen haben eine '
  + 'Einstrahlungsprognose geliefert. Die eedc-Werte für heute (Tagesprognose, PV-Kurve) '
  + 'sind deshalb unvollständig und können zu niedrig sein — bitte später erneut laden.'

const wetter = (over: Record<string, unknown>) => ({
  anlage_id: 1, verfuegbar: true, aktuell: null, stunden: [],
  temperatur_min_c: null, temperatur_max_c: null, sonnenstunden: null,
  sonnenstunden_bisher: null, sonnenstunden_rest: null,
  pv_prognose_kwh: 31.0, pv_prognose_rest_kwh: null, pv_prognose_heute_rollend_kwh: null,
  pv_ist_bisher_kwh: 13.2, grundlast_kw: null, verbrauchsprofil: [],
  prognose_quelle: 'eedc', sunset: '23:59',
  ...over,
} as unknown as LiveWetterResponse)

const tage = [{ datum: '2026-10-11', pv_ertrag_kwh: null } as unknown as SolarPrognoseTag]

describe('N-690: Teilsumme mit Hinweis', () => {
  // Das Wetter-Widget liest die Achsenfarben aus dem ThemeProvider.
  beforeEach(() => { stubMatchMedia() })

  it('Wetter-Widget zeigt den Satz neben dem stehengebliebenen Wert', () => {
    renderMitProvidern(<WetterWidget wetter={wetter({ pv_prognose_hinweis: HINWEIS })} tagesverlauf={null} anlageId={1} />)
    expect(screen.getByText(HINWEIS)).toBeInTheDocument()
    expect(screen.getByText('~31 kWh PV')).toBeInTheDocument()
  })

  it('Wetter-Widget bleibt ohne Hinweis still', () => {
    renderMitProvidern(<WetterWidget wetter={wetter({})} tagesverlauf={null} anlageId={1} />)
    expect(screen.queryByText(/Wetterabruf war unvollständig/)).not.toBeInTheDocument()
  })

  it('Solar-Aussicht zeigt den Satz über der Heute-Zeile', () => {
    render(<SolarAussicht3Tage prognose3Tage={tage} wetter={wetter({ pv_prognose_hinweis: HINWEIS })} heutePvKwh={13.2} />)
    expect(screen.getByText(HINWEIS)).toBeInTheDocument()
    expect(screen.getByText('31,0')).toBeInTheDocument()
  })

  it('Solar-Aussicht zeigt ihn nicht unter einer Fremdquelle (dort steht keine eedc-Zahl für heute)', () => {
    render(<SolarAussicht3Tage prognose3Tage={tage}
      wetter={wetter({ pv_prognose_hinweis: HINWEIS, prognose_quelle: 'solcast', pv_prognose_kwh: 18.6 })}
      heutePvKwh={13.2} />)
    expect(screen.queryByText(HINWEIS)).not.toBeInTheDocument()
  })
})
