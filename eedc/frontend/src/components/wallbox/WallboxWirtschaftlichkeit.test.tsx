/**
 * Mitnahme zu N-555 Stufe 3 (Restfunde-Nachmessung, Master 26.09.): die Karte einer
 * **dienstlichen** Wallbox sagt „dienstlich — keine private Ersparnis …" statt
 * „n kWh = 0,00 €" (Konzept Heimladung/Fahrverbrauch, Regel 3).
 */
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { WallboxWirtschaftlichkeit, WALLBOX_DIENSTLICH_HINWEIS } from './WallboxWirtschaftlichkeit'
import type { WallboxDashboardResponse } from '../../api/investitionen'
import type { Investition } from '../../types'

const z = (dienstlich: boolean) => ({
  gesamt_heim_ladung_kwh: 400, ladung_pv_kwh: 150, ladung_netz_kwh: 250, pv_anteil_prozent: 37.5,
  extern_ladung_kwh: 0, extern_kosten_euro: 0, extern_preis_kwh_euro: 0.5,
  heim_kosten_euro: 0, heim_als_extern_kosten_euro: 0, ersparnis_vs_extern_euro: 0,
  kapitaleinsatz_euro: 0, jahres_ersparnis_euro: 0, amortisation_jahre: null, amortisation_annahme: '',
  leistung_kw: 11, gesamt_ladevorgaenge: 0, ladevorgaenge_pro_monat: 0, anzahl_monate: 3, dienstlich,
}) as WallboxDashboardResponse['zusammenfassung']

const inv = { id: 5, anschaffungskosten_gesamt: null } as unknown as Investition

describe('WallboxWirtschaftlichkeit — dienstliche Wallbox (Regel 3)', () => {
  it('zeigt bei dienstlich den Satz statt „n kWh = 0,00 €"', () => {
    render(<WallboxWirtschaftlichkeit zusammenfassung={z(true)} investition={inv} />)
    expect(screen.getByText(WALLBOX_DIENSTLICH_HINWEIS)).toBeTruthy()
    expect(screen.queryByText(/Netz-Ladung zuhause/)).toBeNull()
  })

  it('privat bleibt die Netz-Ladung mit Kosten stehen', () => {
    render(<WallboxWirtschaftlichkeit zusammenfassung={z(false)} investition={inv} />)
    expect(screen.getByText(/Netz-Ladung zuhause: Haushaltsstrom \(250 kWh = 0,00 €\)/)).toBeTruthy()
    expect(screen.queryByText(WALLBOX_DIENSTLICH_HINWEIS)).toBeNull()
  })
})
