/**
 * Reparatur-Werkbank — ein Plan «nichts zu tun» (Etappe E3, Gegenprüfung Ü4; Nachbesserung nach der Nachmessung E3).
 *
 * Die neuen Operationen der Daten-Checker-Knöpfe melden einen Konflikt der Route (z. B. «Monat hat noch eine
 * Zählerzeile», «Feld ist am Gerät vorgesehen») bzw. «nichts zu ändern» im **Plan** als `operation_preview.nichts_zu_tun`.
 * Die Werkbank zeigt dann den Satz und bietet **kein** Ausführen an — wie der Vorschau-Kasten im Daten-Checker
 * (`components/datenchecker/BefundHandgriff.test.tsx`). Ohne den Satz bleibt alles wie bisher.
 * Schwesterdatei: `RepairWorkbench.test.tsx`.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { fireEvent, screen } from '@testing-library/react'
import type { RepairPlan } from '../../api/repair'

const planFn = vi.fn()

vi.mock('../../api/repair', async (importOriginal) => {
  const echt = await importOriginal<typeof import('../../api/repair')>()
  return {
    ...echt,
    repairApi: {
      ...echt.repairApi,
      listPlans: vi.fn(() => Promise.resolve({ plans: [] })),
      plan: (...args: unknown[]) => planFn(...args),
    },
  }
})

import RepairWorkbench from './RepairWorkbench'
import { renderMitProvidern, stubMatchMedia } from '../../test/render'

function plan(over: Partial<RepairPlan>): { plan: RepairPlan; expires_in_seconds: number } {
  return {
    expires_in_seconds: 3600,
    plan: {
      plan_id: 'p-1', anlage_id: 7, operation: 'temperatur_aus_messung', operation_params: {},
      created_at: '2026-11-10T11:00:00+00:00', expires_at: '2026-11-10T12:00:00+00:00',
      estimated_changes: {}, diff_preview: [], diff_total_count: 0, warnings: [], operation_preview: {}, ...over,
    },
  }
}

async function planErstellen() {
  renderMitProvidern(<RepairWorkbench anlageId={7} />)
  fireEvent.change(screen.getByRole('combobox'), { target: { value: 'temperatur_aus_messung' } })
  fireEvent.click(screen.getByRole('button', { name: /Plan erstellen/ }))
}

describe('RepairWorkbench — Plan «nichts zu tun»', () => {
  beforeEach(() => {
    // Feste Uhr (Wächter `feste-uhr-in-tests`): der Plan trägt feste Zeitpunkte.
    vi.setSystemTime(new Date(2026, 10, 10, 12))
    planFn.mockReset()
    stubMatchMedia()
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('zeigt den Satz des Plans und bietet kein Ausführen an', async () => {
    planFn.mockResolvedValue(plan({ operation_preview: {
      nichts_zu_tun: 'Für die Monate ohne Ø Temperatur reicht deine Messreihe nicht zurück — es gibt nichts nachzutragen.',
    } }))
    await planErstellen()
    expect(await screen.findByText(/reicht deine Messreihe nicht zurück/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Operation ausführen|anwenden/ })).toBeNull()
    expect(screen.getByRole('button', { name: /Plan verwerfen/ })).toBeInTheDocument()
  })

  it('ohne den Satz bleibt der Ausführen-Knopf wie bisher', async () => {
    planFn.mockResolvedValue(plan({ estimated_changes: { monate_temperatur_gefuellt: 2, monate_ohne_temperatur: 3 },
      operation_preview: { monate: ['01/2026', '02/2026'] } }))
    await planErstellen()
    expect(await screen.findByRole('button', { name: /Operation ausführen/ })).toBeInTheDocument()
  })
})
