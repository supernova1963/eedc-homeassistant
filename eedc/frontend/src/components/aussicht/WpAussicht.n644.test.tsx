/**
 * N-644 — *Cockpit → Aussicht*, „Erwartete kommende Heizsaison" der Wärmepumpe liest die bewertete Monatsreihe.
 *
 * Die Zeile las `stromverbrauch_kwh` und `heizenergie_kwh + warmwasser_kwh` roh: bei getrennter Strommessung
 * (Achsen-Matrix M06 WP HW) 0 kWh Strom statt 216, bei gemeinsamem Wärmezähler (M05) 0 kWh Wärme statt 648.
 * Jetzt nimmt sie je Heizmonat Strom und Wärme gesamt der Reihe — dieselbe Faltung wie die Hub-Kacheln.
 */
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'

import { WpAussicht } from './AussichtTeile'
import type { WaermepumpeDashboardResponse, WpMonatsWert } from '../../api/investitionen'

const mw = (monat: number, w: Partial<WpMonatsWert>): WpMonatsWert => ({
  jahr: 2026, monat, strom_kwh: 0, heizung_kwh: 0, warmwasser_kwh: 0, waerme_kwh: 0, ...w,
})

const wp = (monatsreihe: WpMonatsWert[], verbrauch_daten: Record<string, number>) => ({
  investition: { id: 1, bezeichnung: 'WP' },
  // Die Rohzeile trägt absichtlich NICHTS, was die alte Lesart gefunden hätte.
  monatsdaten: monatsreihe.map((m) => ({ jahr: m.jahr, monat: m.monat, verbrauch_daten })),
  monatsreihe,
  zusammenfassung: { durchschnitt_cop: 3, jaz_je_monat: [] },
}) as unknown as WaermepumpeDashboardResponse

describe('WpAussicht (N-644)', () => {
  it('getrennte Strommessung und gemeinsamer Wärmezähler: Strom und Wärme aus der Reihe, nicht 0', () => {
    render(<WpAussicht wpDashboards={[wp(
      [mw(1, { strom_kwh: 216, waerme_kwh: 648 }), mw(2, { strom_kwh: 184, waerme_kwh: 552 })],
      { strom_heizen_kwh: 180, strom_warmwasser_kwh: 36, waerme_kwh: 648 },
    )]} />)
    // Ø (216 + 184) / 2 = 200 · 6 = 1.200 kWh Strom; Ø (648 + 552) / 2 = 600 · 6 = 3.600 kWh Wärme.
    expect(screen.getByText('~1.200 kWh Strom · ~3.600 kWh Wärme')).toBeInTheDocument()
  })

  it('nur Heizmonate gehen ein (Okt–März) — ein Sommermonat zählt nicht', () => {
    render(<WpAussicht wpDashboards={[wp(
      [mw(1, { strom_kwh: 100, waerme_kwh: 300 }), mw(6, { strom_kwh: 999, waerme_kwh: 999 })],
      {},
    )]} />)
    expect(screen.getByText('~600 kWh Strom · ~1.800 kWh Wärme')).toBeInTheDocument()
  })
})
