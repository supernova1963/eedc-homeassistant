/**
 * Reparatur-Werkbank — Knopf „HA-Spiegel jetzt abgleichen" (MartyBr, simon42 #429) und die Operation
 * „Werte vor dem Sensorbeginn verwerfen" (HA-Bauform S3, E-S3-5: Auswahl, Vorbelegung, Plan-Parameter, Vorschau-Sätze
 * aus dem Backend).
 *
 * Nach einer Korrektur in Home Assistant zeigten die Tages-Kennzahlen bis zum Nachtlauf (02:45) den alten
 * HA-Spiegel. Der Werkbank-Eintrag ruft den Lauf von Hand und zeigt die Ergebniszeile aus der Antwort
 * (`meldung`, Backend-Text — der Client rechnet nichts).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fireEvent, screen, waitFor } from '@testing-library/react'
import type { KanalAbgleichErgebnis, KanalAuswahlEintrag, PlanResponse } from '../../api/repair'

const kanalAbgleich = vi.fn()
const kanalAuswahl = vi.fn()
const planFn = vi.fn()

vi.mock('../../api/repair', async (importOriginal) => {
  const echt = await importOriginal<typeof import('../../api/repair')>()
  return {
    ...echt,
    repairApi: {
      ...echt.repairApi,
      listPlans: vi.fn(() => Promise.resolve({ plans: [] })),
      kanalAbgleich: (...args: unknown[]) => kanalAbgleich(...args),
      kanalAuswahl: (...args: unknown[]) => kanalAuswahl(...args),
      plan: (...args: unknown[]) => planFn(...args),
    },
  }
})

import RepairWorkbench from './RepairWorkbench'
import { renderMitProvidern, stubMatchMedia } from '../../test/render'

const antwort = (over: Partial<KanalAbgleichErgebnis> = {}): KanalAbgleichErgebnis => ({
  anlage_id: 7, hat_spiegel: true, kanaele: 3, abschnitte: 3, gleich: 2,
  korrigiert: [{ key: 'basis:einspeisung', ab_ts: 1_760_000_000, zeilen: 12 }],
  gekuerzt: [], uebersprungen: {}, fehler: 0,
  meldung: '1 von 3 Abschnitt(en) wichen von der HA-Statistik ab und wurden ab der ersten Abweichung neu gespiegelt: basis:einspeisung ab 09.10.2025 10:00 (12 Stundenzeile(n)).',
  ...over,
})

function waehleAbgleich() {
  fireEvent.change(screen.getByRole('combobox'), { target: { value: 'kanal_abgleich_direkt' } })
}

describe('RepairWorkbench — HA-Spiegel jetzt abgleichen (#429)', () => {
  beforeEach(() => {
    kanalAbgleich.mockReset()
    stubMatchMedia()
  })

  it('bietet den Eintrag an, erklärt ihn in einem Satz und zeigt die Ergebniszeile', async () => {
    kanalAbgleich.mockResolvedValue(antwort())
    renderMitProvidern(<RepairWorkbench anlageId={7} />)
    waehleAbgleich()
    expect(screen.getByText(/Nach einer Korrektur in Home Assistant/)).toBeInTheDocument()
    // Kein Plan-Knopf: direkter Pfad wie das Löschen.
    expect(screen.queryByRole('button', { name: /Plan erstellen/ })).toBeNull()

    fireEvent.click(screen.getByRole('button', { name: /HA-Spiegel jetzt abgleichen/ }))
    await waitFor(() => expect(kanalAbgleich).toHaveBeenCalledWith(7))
    expect(await screen.findByText(/neu gespiegelt: basis:einspeisung/)).toBeInTheDocument()
  })

  it('ohne HA-Spiegel steht die Antwort des Backends da, kein Fehler', async () => {
    kanalAbgleich.mockResolvedValue(antwort({
      hat_spiegel: false, kanaele: 0, abschnitte: 0, gleich: 0, korrigiert: [],
      meldung: 'Für diese Anlage führt eedc keinen HA-Spiegel — ohne Zähler aus der Home-Assistant-Statistik gibt es nichts abzugleichen.',
    }))
    renderMitProvidern(<RepairWorkbench anlageId={7} />)
    waehleAbgleich()
    fireEvent.click(screen.getByRole('button', { name: /HA-Spiegel jetzt abgleichen/ }))
    expect(await screen.findByText(/keinen HA-Spiegel/)).toBeInTheDocument()
  })

  it('HA nicht erreichbar: der Grund aus der 503-Antwort steht als Fehler da', async () => {
    kanalAbgleich.mockRejectedValue(new Error('Home Assistant ist nicht erreichbar — der Abgleich braucht die HA-Langzeitstatistik.'))
    renderMitProvidern(<RepairWorkbench anlageId={7} />)
    waehleAbgleich()
    fireEvent.click(screen.getByRole('button', { name: /HA-Spiegel jetzt abgleichen/ }))
    expect(await screen.findByText(/nicht erreichbar/)).toBeInTheDocument()
  })
})


const auswahl = (): KanalAuswahlEintrag[] => [
  {
    key: 'inv:6:pv_erzeugung_kwh', label: 'Süddach · Erzeugung', investition_id: 6, typ: 'pv-module',
    quellen: [
      { gueltig_ab: '2025-01-01T00:00', familie: 'spiegel', statistic_id: 'sensor.pv_alt', verworfen_am: null },
      { gueltig_ab: '2026-04-21T00:00', familie: 'spiegel', statistic_id: 'sensor.pv_neu', verworfen_am: null },
    ],
    vorbelegung: '2026-04-21T00:00',
  },
  {
    key: 'basis:einspeisung', label: 'Anlage · Einspeisung', investition_id: null, typ: null,
    quellen: [
      { gueltig_ab: '2025-01-01T00:00', familie: 'spiegel', statistic_id: 'sensor.einsp_alt', verworfen_am: null },
      { gueltig_ab: '2026-05-03T14:00', familie: 'spiegel', statistic_id: 'sensor.einsp_neu', verworfen_am: null },
    ],
    vorbelegung: '2026-05-03T14:00',
  },
]

const planAntwort = (): PlanResponse => ({
  expires_in_seconds: 3600,
  plan: {
    plan_id: 'p1', anlage_id: 7, operation: 'verwerfen_vor_quellbeginn',
    operation_params: { kanal: 'basis:einspeisung', zeitpunkt: '2026-05-03T14:00' },
    created_at: '2026-10-15T10:00:00Z', expires_at: '2026-10-15T11:00:00Z',
    estimated_changes: { kanalzeilen: 1912, bestand_tage: 80, abschluss_monate: 2 },
    diff_preview: [], diff_total_count: 0,
    warnings: ['alter Sensor sensor.einsp_alt von 01.01.2025 00:00 bis 03.05.2026 14:00: 1.912 Stunden im Kanal.'],
    operation_preview: {},
  },
})

function waehleVerwerfen() {
  fireEvent.change(screen.getAllByRole('combobox')[0], { target: { value: 'verwerfen_vor_quellbeginn' } })
}

describe('RepairWorkbench — Werte vor dem Sensorbeginn verwerfen (E-S3-5)', () => {
  beforeEach(() => {
    kanalAuswahl.mockReset()
    planFn.mockReset()
    stubMatchMedia()
  })

  it('listet die Felder mit Sensortausch (Anlage zuerst), belegt den Zeitpunkt vor und schickt kanal + zeitpunkt', async () => {
    kanalAuswahl.mockResolvedValue({ kanaele: auswahl() })
    planFn.mockResolvedValue(planAntwort())
    renderMitProvidern(<RepairWorkbench anlageId={7} />)
    waehleVerwerfen()
    await waitFor(() => expect(kanalAuswahl).toHaveBeenCalledWith(7))
    const feld = await screen.findByRole('combobox', { name: 'Feld' })
    const optionen = Array.from((feld as HTMLSelectElement).options).map((o) => o.textContent)
    expect(optionen).toEqual(['Feld mit Sensortausch wählen', 'Anlage · Einspeisung', 'Süddach · Erzeugung'])

    fireEvent.change(feld, { target: { value: 'basis:einspeisung' } })
    expect(screen.getByText('sensor.einsp_neu')).toBeInTheDocument()
    expect((screen.getByRole('combobox', { name: 'Uhrzeit' }) as HTMLSelectElement).value).toBe('14')

    fireEvent.click(screen.getByRole('button', { name: /Plan erstellen/ }))
    await waitFor(() => expect(planFn).toHaveBeenCalled())
    expect(planFn.mock.calls[0][0]).toEqual({
      anlage_id: 7, operation: 'verwerfen_vor_quellbeginn',
      params: { kanal: 'basis:einspeisung', zeitpunkt: '2026-05-03T14:00' },
    })
    // Die Sätze der Vorschau kommen vom Backend — der Client rechnet nichts.
    expect(await screen.findByText(/1\.912 Stunden im Kanal/)).toBeInTheDocument()
  })

  it('ohne Feld kein Plan — die Werkbank sagt, was fehlt', async () => {
    kanalAuswahl.mockResolvedValue({ kanaele: auswahl() })
    renderMitProvidern(<RepairWorkbench anlageId={7} />)
    waehleVerwerfen()
    await screen.findByRole('combobox', { name: 'Feld' })
    fireEvent.click(screen.getByRole('button', { name: /Plan erstellen/ }))
    expect(await screen.findByText(/Bitte ein Feld mit Sensortausch/)).toBeInTheDocument()
    expect(planFn).not.toHaveBeenCalled()
  })

  it('ohne Sensortausch steht der Grund da', async () => {
    kanalAuswahl.mockResolvedValue({ kanaele: [] })
    renderMitProvidern(<RepairWorkbench anlageId={7} />)
    waehleVerwerfen()
    expect(await screen.findByText(/Kein Feld dieser Anlage hat einen Sensortausch/)).toBeInTheDocument()
  })
})
