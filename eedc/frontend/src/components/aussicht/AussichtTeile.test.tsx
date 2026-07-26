/**
 * Anzeige-Regel der Solar-Prognose: gezeigt wird der eedc-korrigierte Tageswert,
 * bei dessen Fehlen der OpenMeteo-Rohwert — und die Beschriftung sagt, welcher
 * von beiden es war.
 *
 * Anlass (Rainer-PN „Nachtrag" 2026-07-25): der 14-Tage-Balken zeigte 13 kWh,
 * die Stundenwerte-Summe darunter 10,8 kWh für denselben Tag. Ohne diesen Test
 * kann ein Balken wieder still auf den Rohwert zurückfallen.
 */
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import type { SolarPrognose, SolarPrognoseTag } from '../../api/wetter'
import { prognoseSummeKwh, prognoseDurchschnittKwh, prognoseQuelleLabel } from '../../lib'
import { TagesPrognose, KurzfristDetails } from './AussichtTeile'

const basisTag = (datum: string, om: number): SolarPrognoseTag => ({
  datum, pv_ertrag_kwh: om, gti_kwh_m2: 5, ghi_kwh_m2: 5, sonnenstunden: 8,
  temperatur_max_c: 24, wetter_symbol: 'sunny',
  pv_ertrag_morgens_kwh: om * 0.4, pv_ertrag_nachmittags_kwh: om * 0.6,
})

const mitEedc = (t: SolarPrognoseTag, eedc: number): SolarPrognoseTag => ({
  ...t, eedc_kwh: eedc, eedc_morgens_kwh: eedc * 0.4, eedc_nachmittags_kwh: eedc * 0.6,
})

const prognose = (tage: SolarPrognoseTag[], eedcAggregate: boolean): SolarPrognose => ({
  anlage_id: 1, anlagenname: 'Demo', kwp_gesamt: 10, neigung: 30, ausrichtung: 0,
  system_losses_prozent: 14, prognose_zeitraum: { von: null, bis: null },
  summe_kwh: 26, durchschnitt_kwh_tag: 13,
  tage, tageswerte: tage, datenquelle: 'Best Match', abgerufen_am: '', hinweise: [],
  eedc_summe_kwh: eedcAggregate ? 21.6 : null,
  eedc_durchschnitt_kwh_tag: eedcAggregate ? 10.8 : null,
  anzeige_quelle: eedcAggregate ? 'eedc' : 'openmeteo',
  anlage: { id: 1, name: 'Demo', leistung_kwp: 10, neigung: 30, azimut: 0 },
})

const KORRIGIERT = [
  mitEedc(basisTag('2026-07-26', 13), 10.8),
  mitEedc(basisTag('2026-07-27', 13), 10.8),
]
const ROH = [basisTag('2026-07-26', 13), basisTag('2026-07-27', 13)]

describe('Solar-Prognose-Anzeige — eedc-Wert vor OpenMeteo-Rohwert', () => {
  it('Balken zeigen den eedc-Wert, nicht den Rohwert', () => {
    render(<TagesPrognose tage={KORRIGIERT} quelleLabel={prognoseQuelleLabel(prognose(KORRIGIERT, true))} />)
    // Balken runden auf 0 NK (unverändert): 10,8 → „11", der Rohwert wäre „13".
    expect(screen.getAllByText('11').length).toBeGreaterThan(0)
    expect(screen.queryByText('13')).not.toBeInTheDocument()
  })

  it('ohne eedc-Wert bleibt der Rohwert stehen — und die Quelle sagt es', () => {
    render(<TagesPrognose tage={ROH} quelleLabel={prognoseQuelleLabel(prognose(ROH, false))} />)
    expect(screen.getAllByText('13').length).toBeGreaterThan(0)
    expect(screen.getAllByText(/Quelle: Open-Meteo \(ohne Korrektur\)/).length).toBeGreaterThan(0)
    expect(screen.queryByText(/Quelle: eedc/)).not.toBeInTheDocument()
  })

  it('Balken-Legende nennt eedc, wenn eedc-Werte gezeigt werden', () => {
    render(<TagesPrognose tage={KORRIGIERT} quelleLabel={prognoseQuelleLabel(prognose(KORRIGIERT, true))} />)
    expect(screen.getAllByText(/Quelle: eedc-Prognose \(Open-Meteo \+ Korrektur\)/).length).toBeGreaterThan(0)
  })

  it('14-Tage-Tabelle zeigt eedc-Wert und passende VM/NM-Hälften', () => {
    render(<KurzfristDetails tage={KORRIGIERT} />)
    expect(screen.getAllByText('10,8').length).toBe(2)   // PV-Prognose je Tag
    expect(screen.getAllByText('4,3').length).toBe(2)    // VM = 10,8 × 0,4
    expect(screen.getAllByText('6,5').length).toBe(2)    // NM = 10,8 × 0,6
    expect(screen.queryByText('13,0')).not.toBeInTheDocument()
  })

  it('Aggregate folgen den angezeigten Werten (Σ und Ø/Tag)', () => {
    const korrigiert = prognose(KORRIGIERT, true)
    expect(prognoseSummeKwh(korrigiert)).toBe(21.6)
    expect(prognoseDurchschnittKwh(korrigiert)).toBe(10.8)
    // Fallback: ohne eedc-Aggregat gelten die Rohwerte — passend zu den Balken.
    const roh = prognose(ROH, false)
    expect(prognoseSummeKwh(roh)).toBe(26)
    expect(prognoseDurchschnittKwh(roh)).toBe(13)
  })
})
