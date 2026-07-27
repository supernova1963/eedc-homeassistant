/**
 * String-Tabelle: Ertragsanteil, Summenzeile und die Erklärung zur Performance
 * (R22-3, PN 89782 Rainer).
 *
 * Anlass: In der Tabelle stand „Performance" (IST gegen die PVGIS-Prognose DES
 * STRINGS) direkt neben dem absoluten IST. Gelesen wurde das als Rangliste der
 * Dächer — das kleinere Dach „20 % besser", obwohl es weniger liefert. Es
 * fehlten der erklärende Satz, das Gewicht (Ertragsanteil) und jede Summe.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'

const getPVStringsGesamtlaufzeit = vi.fn()
vi.mock('../../api/cockpit', () => ({
  cockpitApi: { getPVStringsGesamtlaufzeit: (...a: unknown[]) => getPVStringsGesamtlaufzeit(...a) },
}))

import { PVStringVergleich } from './PVStringVergleich'
import { ParkProvider } from '../park'
import type { PVStringsGesamtlaufzeitResponse } from '../../api/cockpit'

const string = (id: number, bezeichnung: string, kwp: number, ist: number, ausrichtung: string) => ({
  investition_id: id, bezeichnung, leistung_kwp: kwp, ausrichtung, neigung_grad: 30,
  wechselrichter_name: null,
  prognose_gesamt_kwh: ist, ist_gesamt_kwh: ist, abweichung_gesamt_prozent: 0,
  performance_ratio_gesamt: 1, spezifischer_ertrag_kwh_kwp: ist / kwp,
  ist_quelle: 'gemessen' as const, jahreswerte: [], saisonalwerte: [],
})

/** Rainers Anlage: 18 Module Nord-West (mehr Ertrag) vs. 9 Module Süd-Ost (bessere kWh/kWp). */
const antwort = (over: Partial<PVStringsGesamtlaufzeitResponse> = {}): PVStringsGesamtlaufzeitResponse => ({
  anlage_id: 1, hat_prognose: true, prognose_warnung: null,
  anlagen_leistung_kwp: 10.8, erstes_jahr: 2023, letztes_jahr: 2026,
  anzahl_jahre: 4, anzahl_monate: 40,
  prognose_gesamt_kwh: 10000, ist_gesamt_kwh: 10000,
  abweichung_gesamt_kwh: 0, abweichung_gesamt_prozent: 0,
  strings: [string(11, 'Dach Nord-West', 7.2, 6000, 'Nord-West'), string(12, 'Dach Süd-Ost', 3.6, 4000, 'Süd-Ost')],
  saisonal_aggregiert: [], bester_string: 'Dach Süd-Ost', schlechtester_string: 'Dach Nord-West',
  ist_quelle: 'gemessen', vergleich_hinweis: null,
  ...over,
})

async function zeige(data: PVStringsGesamtlaufzeitResponse) {
  getPVStringsGesamtlaufzeit.mockResolvedValue(data)
  const { container } = render(
    <ParkProvider persistKey="test:pv-string-vergleich">
      <PVStringVergleich anlageId={1} />
    </ParkProvider>,
  )
  await waitFor(() => expect(screen.getByText('Einzelne Strings / Module (Gesamtlaufzeit)')).toBeInTheDocument())
  return container
}

beforeEach(() => vi.clearAllMocks())

describe('PVStringVergleich — String-Tabelle', () => {
  it('erklärt, wogegen „Performance" misst', async () => {
    const container = await zeige(antwort())

    expect(container.textContent).toMatch(/Performance misst jeden String gegen seine eigene Prognose/)
    expect(container.textContent).toMatch(/zählt kWh\/kWp/)
  })

  it('zeigt den Ertragsanteil je String', async () => {
    await zeige(antwort())

    // 6000 bzw. 4000 von 10000 kWh — das Gewicht, das der Performance-Spalte fehlte.
    expect(screen.getAllByText('60,0 %').length).toBeGreaterThan(0)
    expect(screen.getAllByText('40,0 %').length).toBeGreaterThan(0)
  })

  it('summiert kWp, SOLL und IST in der Fußzeile', async () => {
    const container = await zeige(antwort())

    expect(screen.getAllByText('Gesamt').length).toBeGreaterThan(0)
    // Σ kWp = Rainers „Summe der Modul-Leistung", aus der Response, nicht nachaddiert
    expect(screen.getAllByText('10,8').length).toBeGreaterThan(0)
    expect(container.textContent).toMatch(/10,0 MWh/)
  })

  it('ein einzelner String bekommt keine Summenzeile', async () => {
    await zeige(antwort({
      strings: [string(11, 'Dach Süd', 10.8, 10000, 'Süd')],
      bester_string: null, schlechtester_string: null,
    }))

    expect(screen.queryByText('Gesamt')).not.toBeInTheDocument()
  })

  it('ohne gemessenes IST bleibt der Anteil leer statt 0 %', async () => {
    const container = await zeige(antwort({
      ist_gesamt_kwh: 0,
      strings: [
        { ...string(11, 'Dach Nord-West', 7.2, 0, 'Nord-West'), spezifischer_ertrag_kwh_kwp: null },
        { ...string(12, 'Dach Süd-Ost', 3.6, 0, 'Süd-Ost'), spezifischer_ertrag_kwh_kwp: null },
      ],
    }))

    // Mobil-Karte rendert „Anteil" + Wert direkt hintereinander — dort prüfbar,
    // ohne die KPI-Kachel „Abweichung +0,0 %" mitzufangen.
    expect(container.textContent).toMatch(/Anteil—/)
    expect(container.textContent).not.toMatch(/Anteil0,0 %/)
  })
})
