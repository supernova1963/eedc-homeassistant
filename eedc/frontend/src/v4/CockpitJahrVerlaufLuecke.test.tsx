/**
 * Cockpit/Jahr — Verlauf und Rail sehen dieselben Monate wie die Kopfzahl (N-68).
 *
 * P-12/N-65 hat die **Kopfzahl** vom Monatsabschluss gelöst: sie zählt seither
 * jeden Monat, der Mengen trägt. Verlauf-Chart und Jahres-Rail blieben an
 * `/monatsdaten/aggregiert` hängen, und das lieferte nur Monate **mit**
 * Zählerzeile — an der Box (02.08.2026) sechs Balken unter einer Kopfzahl, die
 * acht Monate zählte. Seit N-68 fragt die Sicht mit `inklOhneZaehlerzeile`.
 *
 * Eigene Datei statt Ausbau von `CockpitJahrLuecke.test.tsx` (die dieselbe Lage
 * für die Kopfzahl hält): hier braucht die Fixture ein **abgeschlossenes** Jahr
 * mit Lücke — nur dort zeigt die Rail überhaupt eine kWh-Zahl an, beim
 * laufenden Jahr steht dort „läuft". Diese Lücke würde die Erwartungen der
 * Nachbardatei (12 × 200 in jeder Vergleichsspalte) umschreiben.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { ThemeProvider } from '../context/ThemeContext'
import type { AktuellerMonatResponse } from '../api/aktuellerMonat'
import type { AggregierteMonatsdaten } from '../api/monatsdaten'
import type { Nachhaltigkeit } from '../api/cockpit'

const KWH = { 2026: 300, 2025: 200 } as Record<number, number>

/** 2026 läuft (Systemzeit 02.08.): Zählerzeilen bis Juni, Juli+August ohne. */
const OHNE_ZEILE_2026 = [7, 8]
/** 2025 ist abgeschlossen, hat aber den Mai nie abgeschlossen — die Lage, in
 *  der die Rail eine sichtbar zu kleine Zahl anzeigt. */
const OHNE_ZEILE_2025 = [5]

const zeile = (jahr: number, monat: number, mitZaehlerzeile: boolean): AggregierteMonatsdaten => ({
  // `id: null` ist die ganze Kennzeichnung eines Monats ohne Abschluss.
  id: mitZaehlerzeile ? jahr * 100 + monat : null,
  jahr, monat,
  pv_erzeugung_kwh: KWH[jahr], eigenverbrauch_kwh: KWH[jahr] / 2, direktverbrauch_kwh: KWH[jahr] / 4,
  // Ohne Zählerzeile gibt es keine Zählerwerte — genau das liefert die Route.
  einspeisung_kwh: mitZaehlerzeile ? KWH[jahr] / 2 : 0,
  netzbezug_kwh: mitZaehlerzeile ? 50 : 0,
  gesamtverbrauch_kwh: KWH[jahr] / 2 + 50,
} as unknown as AggregierteMonatsdaten)

const jahresZeilen = (jahr: number, ohneZeile: number[], bisMonat: number) =>
  Array.from({ length: bisMonat }, (_, i) => i + 1)
    .map((m) => zeile(jahr, m, !ohneZeile.includes(m)))

const ALLE: AggregierteMonatsdaten[] = [
  ...jahresZeilen(2026, OHNE_ZEILE_2026, 8),
  ...jahresZeilen(2025, OHNE_ZEILE_2025, 12),
]

/** Der Mock verhält sich wie die Route: ohne Flag fallen die Monate ohne
 *  Zählerzeile weg. Ignorierte er das Flag, wäre der Test grün-falsch. */
const listAggregiert = vi.fn(
  (_id: number, _jahr?: number, opts?: { inklOhneZaehlerzeile?: boolean }) =>
    Promise.resolve(opts?.inklOhneZaehlerzeile ? ALLE : ALLE.filter((r) => r.id != null)),
)

const monatsAntwort = (jahr: number, monat: number): AktuellerMonatResponse => ({
  anlage_id: 1, anlage_name: 'Demo', jahr, monat, monat_name: String(monat),
  aktualisiert_um: '', quellen: {},
  soll_pv_kwh: null, netzbezug_preis_cent: 40, einspeise_preis_cent: 8.2,
  pv_erzeugung_kwh: KWH[jahr], einspeisung_kwh: KWH[jahr] / 2, netzbezug_kwh: 50,
  eigenverbrauch_kwh: KWH[jahr] / 2, direktverbrauch_kwh: KWH[jahr] / 4,
  gesamtverbrauch_kwh: KWH[jahr] / 2 + 50,
  autarkie_prozent: 75, eigenverbrauch_quote_prozent: 50,
  investitionen_financials: [], komponenten_geraete: {}, feld_quellen: {}, vorjahr: null,
} as unknown as AktuellerMonatResponse)

vi.mock('../api/monatsdaten', () => ({
  monatsdatenApi: { listAggregiert: (...a: [number, number?, { inklOhneZaehlerzeile?: boolean }?]) => listAggregiert(...a) },
}))
vi.mock('../api/aktuellerMonat', () => ({
  aktuellerMonatApi: { getData: (_id: number, j: number, m: number) => Promise.resolve(monatsAntwort(j, m)) },
}))
const leereNachhaltigkeit: Nachhaltigkeit = {
  anlage_id: 1, co2_gesamt_kg: 0, co2_pv_kg: 0, co2_wp_kg: 0, co2_emob_kg: 0,
  aequivalent_baeume: 0, aequivalent_auto_km: 0, aequivalent_fluege_km: 0,
  autarkie_durchschnitt_prozent: 0, monatswerte: [],
}
vi.mock('../api/cockpit', () => ({
  cockpitApi: { getNachhaltigkeit: vi.fn(() => Promise.resolve(leereNachhaltigkeit)) },
}))

import CockpitJahrV4 from './CockpitJahrV4'

function renderView() {
  return render(
    <MemoryRouter>
      <ThemeProvider>
        <CockpitJahrV4 anlageId={1} />
      </ThemeProvider>
    </MemoryRouter>,
  )
}

/** Verlauf fokussieren und auf die Tabellen-Ablesung umschalten — im jsdom ist
 *  sie der einzige Weg, die Zeilenmenge des Charts zu lesen (Recharts rendert
 *  ohne Layout keine Balken). */
async function verlaufTabelle() {
  const kopf = (await screen.findByText('Verlauf')).closest('div')!
  fireEvent.click(within(kopf).getByLabelText('Fokus / Vollbild'))
  fireEvent.click(await screen.findByText('Tabelle'))
  return screen.getAllByRole('row')
}

describe('Cockpit/Jahr — Verlauf und Rail kennen den Monat ohne Abschluss (N-68)', () => {
  beforeEach(() => {
    localStorage.clear()
    listAggregiert.mockClear()
    vi.useFakeTimers({ shouldAdvanceTime: true })
    vi.setSystemTime(new Date(2026, 7, 2, 12, 0, 0))
    vi.stubGlobal('matchMedia', vi.fn().mockReturnValue({
      matches: false, media: '', onchange: null,
      addEventListener: vi.fn(), removeEventListener: vi.fn(),
      addListener: vi.fn(), removeListener: vi.fn(), dispatchEvent: vi.fn(),
    }))
  })
  afterEach(() => { vi.useRealTimers() })

  it('die Sicht fragt die Monate ohne Zählerzeile ausdrücklich mit an', async () => {
    renderView()
    await screen.findByText('Kennzahlen')
    expect(listAggregiert).toHaveBeenCalledWith(1, undefined, { inklOhneZaehlerzeile: true })
  })

  it('der Verlauf zeichnet auch die Monate ohne Abschluss', async () => {
    renderView()
    const zeilen = await verlaufTabelle()
    const monate = zeilen.slice(1).map((r) => within(r).getAllByRole('cell')[0].textContent)
    // Bis v4.0.6: Jan–Jun. Juli ist gelaufen und trägt 300 kWh, August läuft.
    expect(monate).toEqual(['Jan', 'Feb', 'Mär', 'Apr', 'Mai', 'Jun', 'Jul', 'Aug', 'Σ'])
    // Und die Summenzeile geht auf: 8 × 150 kWh Eigenverbrauch = 1.200 — dieselbe
    // Grundgesamtheit wie die Kennzahl-Kachel darüber. Vorher standen dort sechs
    // Monate unter einer Kopfzahl, die acht zählte
    // ([[feedback_gate_summenzeile_verifizieren]]).
    const summe = zeilen.at(-1)!
    expect(within(summe).getAllByRole('cell')[1]).toHaveTextContent('1.200')
  })

  it('die Rail-Summe eines abgeschlossenen Jahres zählt den Monat ohne Abschluss mit', async () => {
    renderView()
    await screen.findByText('Kennzahlen')
    // 12 × 200 = 2.400. Ohne das Flag fehlte der Mai: 11 × 200 = 2.200 — eine
    // Zahl, die die Rail beim ABGESCHLOSSENEN Jahr auch anzeigt (beim laufenden
    // steht dort „läuft", weshalb dort nur der Mini-Balken zu kurz war).
    expect(screen.getAllByTitle('2025: 2.400 kWh').length).toBeGreaterThanOrEqual(1)
    expect(screen.queryAllByTitle('2025: 2.200 kWh')).toHaveLength(0)
  })

  it('REGRESSION: das laufende Jahr behält seine „läuft"-Beschriftung', async () => {
    // Die Rail behauptet über das laufende Jahr bewusst keine Summe. N-68 ändert
    // daran nichts — nur die Balkenlänge dahinter stimmt jetzt.
    renderView()
    await screen.findByText('Kennzahlen')
    expect(screen.getAllByTitle('2026 — läuft').length).toBeGreaterThanOrEqual(1)
  })
})
