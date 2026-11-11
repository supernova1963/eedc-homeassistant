/**
 * N-790 (ottokar, simon42 PN T95600) — «Aus Home Assistant neu übernehmen» im Daten-Checker, seit E3 über die eine
 * Mechanik (Konzept §3.1 R6, Wächter W-10).
 *
 * Ein Drift-Befund einer Anlage mit HA-Spiegel trägt die Aktion `spiegel_abgleich_tag` (`{datum}`). Der Knopf erstellt
 * zuerst den Plan (`POST /repair/plan`, ohne HA), zeigt die Vorschau mit der Vorbedingung, führt erst auf «Anwenden» aus
 * (`POST /repair/execute/{id}`), zeigt den Satz `meldung` des Laufs und lässt den Checker neu laufen. Die Route
 * `spiegel-abgleich-tag` ruft der Checker nicht mehr. Schwesterdatei: `components/datenchecker/BefundHandgriff.test.tsx`.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

const check = vi.fn()
const plan = vi.fn()
const execute = vi.fn()

vi.mock('../api/datenChecker', () => ({ datenCheckerApi: { check: (...a: unknown[]) => check(...a) } }))
vi.mock('../api/repair', async (orig) => ({
  ...(await orig<typeof import('../api/repair')>()),
  repairApi: { plan: (...a: unknown[]) => plan(...a), execute: (...a: unknown[]) => execute(...a), discard: vi.fn() },
}))

import { DatenCheckerVerwaltung } from './DatenCheckerTeile'
import { baueSpiegelAbgleichMeldung } from './datenCheckerMeldungen'

const MELDUNG = 'Statistik aus Home Assistant neu übernommen, 1 Kanal ab 02.11. 07:00 korrigiert; Tag 02.11.2026 neu aufgebaut.'

function antwort(ergebnisse: unknown[]) {
  return {
    anlage_id: 7, anlage_name: 'Haus', ergebnisse,
    zusammenfassung: { error: 0, warning: 0, info: ergebnisse.length, ok: 0 },
  }
}

const DRIFT = {
  kategorie: 'datenquelle_drift', schwere: 'info',
  meldung: 'Wärmepumpe: 1 Tag(e) weichen von HA-Statistics ab (größte Abweichung 2026-11-02: 123.909,6 → 13,7 kWh)',
  details: 'Für diese Komponente steht in eedc an 1 Tag(en) ein anderer Wert als in Home Assistant.',
  code: 'drift_komponente',
  action: { operation: 'spiegel_abgleich_tag', params: { datum: '2026-11-02' }, label: 'Aus Home Assistant neu übernehmen' },
  knopf: 'Aus Home Assistant neu übernehmen',
}

/** E5 K2: jede Aktion steht oben in der Leiste «Das kannst du jetzt tun» (und in ihrer Kategorie, K1 offen). */
async function leiste() {
  return within(await screen.findByTestId('handgriff-leiste'))
}

const PLAN = {
  plan_id: 'p-7', anlage_id: 7, operation: 'spiegel_abgleich_tag', operation_params: { datum: '2026-11-02' },
  created_at: '2026-11-10T11:00:00+00:00', expires_at: '2026-11-10T12:00:00+00:00',
  estimated_changes: { spiegel_kanaele: 1, spiegel_abschnitte: 1, tage_neu_aufgebaut: 1 }, diff_preview: [],
  diff_total_count: 0, warnings: [], operation_preview: { hat_spiegel: true, vorbedingung: true },
}

function renderVerwaltung() {
  return render(
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <DatenCheckerVerwaltung anlageId={7} />
    </MemoryRouter>,
  )
}

describe('Daten-Checker: «Aus Home Assistant neu übernehmen» (N-790, E3: Plan → Vorschau → Anwenden)', () => {
  beforeEach(() => {
    // Feste Uhr (Wächter `feste-uhr-in-tests`): die Befunde tragen ein festes Datum, «heute» ist der Tag der Meldung.
    vi.setSystemTime(new Date(2026, 10, 10, 12))
    check.mockReset()
    plan.mockReset()
    execute.mockReset()
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('plant mit dem Tag, zeigt die Vorschau, führt erst auf «Anwenden» aus, zeigt den Satz und prüft neu', async () => {
    check.mockResolvedValueOnce(antwort([DRIFT])).mockResolvedValue(antwort([]))
    plan.mockResolvedValue({ plan: PLAN, expires_in_seconds: 3600 })
    execute.mockResolvedValue({
      plan_id: 'p-7', anlage_id: 7, operation: 'spiegel_abgleich_tag', actual_changes: {}, audit_log_ids: [],
      operation_summary: { anlage_id: 7, datum: '2026-11-02', meldung: MELDUNG,
        abgleich: { fehler: 0 }, reaggregation: { status: 'ok', datum: '2026-11-02' } },
    })
    renderVerwaltung()
    fireEvent.click((await leiste()).getByRole('button', { name: /Aus Home Assistant neu übernehmen/ }))
    await waitFor(() => expect(plan).toHaveBeenCalledWith({
      anlage_id: 7, operation: 'spiegel_abgleich_tag', params: { datum: '2026-11-02' },
    }))
    expect(execute).not.toHaveBeenCalled()
    expect(await screen.findByText(/wirksam, wenn du in Home Assistant korrigiert hast/)).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Anwenden' }))
    await waitFor(() => expect(execute).toHaveBeenCalledWith('p-7'))
    expect(await screen.findByText(MELDUNG)).toBeTruthy()
    await waitFor(() => expect(check).toHaveBeenCalledTimes(2))
  })

  it('zeigt den Fehler des Laufs (503: Home Assistant nicht erreichbar), der Befund bleibt', async () => {
    check.mockResolvedValue(antwort([DRIFT]))
    plan.mockResolvedValue({ plan: PLAN, expires_in_seconds: 3600 })
    execute.mockRejectedValue(new Error('Home Assistant ist nicht erreichbar'))
    renderVerwaltung()
    fireEvent.click((await leiste()).getByRole('button', { name: /Aus Home Assistant neu übernehmen/ }))
    fireEvent.click(await screen.findByRole('button', { name: 'Anwenden' }))
    expect(await screen.findByText('Home Assistant ist nicht erreichbar')).toBeTruthy()
    expect(screen.getAllByText(DRIFT.meldung).length).toBeGreaterThan(0)
  })

  it('«Lösungsweg» öffnet das Panel neben der Liste', async () => {
    check.mockResolvedValue(antwort([DRIFT]))
    renderVerwaltung()
    fireEvent.click((await leiste()).getByRole('button', { name: 'Lösungsweg' }))
    expect(await screen.findByTestId('loesungsweg-panel')).toBeTruthy()
  })
})

describe('baueSpiegelAbgleichMeldung', () => {
  const basis = { anlage_id: 7, datum: '2026-11-02', meldung: MELDUNG }

  it('ist «ok», wenn der Abgleich vollständig lief und der Tag neu aufgebaut ist', () => {
    const m = baueSpiegelAbgleichMeldung({
      ...basis, abgleich: { fehler: 0 } as never, reaggregation: { status: 'ok', datum: '2026-11-02' },
    })
    expect(m).toEqual({ art: 'ok', text: MELDUNG })
  })

  it('ist «hinweis», wenn der Tag nicht neu aufgebaut werden konnte oder ein Kanal ungeprüft blieb', () => {
    expect(baueSpiegelAbgleichMeldung({
      ...basis, abgleich: { fehler: 0 } as never, reaggregation: { status: 'fehler', datum: '2026-11-02', fehler: 'x' },
    }).art).toBe('hinweis')
    expect(baueSpiegelAbgleichMeldung({
      ...basis, abgleich: { fehler: 1 } as never, reaggregation: { status: 'ok', datum: '2026-11-02' },
    }).art).toBe('hinweis')
  })
})
