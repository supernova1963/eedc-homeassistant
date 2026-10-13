/**
 * Reparatur-Werkbank — Knopf „HA-Spiegel jetzt abgleichen" (MartyBr, simon42 #429).
 *
 * Nach einer Korrektur in Home Assistant zeigten die Tages-Kennzahlen bis zum Nachtlauf (02:45) den alten
 * HA-Spiegel. Der Werkbank-Eintrag ruft den Lauf von Hand und zeigt die Ergebniszeile aus der Antwort
 * (`meldung`, Backend-Text — der Client rechnet nichts).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fireEvent, screen, waitFor } from '@testing-library/react'
import type { KanalAbgleichErgebnis } from '../../api/repair'

const kanalAbgleich = vi.fn()

vi.mock('../../api/repair', async (importOriginal) => {
  const echt = await importOriginal<typeof import('../../api/repair')>()
  return {
    ...echt,
    repairApi: {
      ...echt.repairApi,
      listPlans: vi.fn(() => Promise.resolve({ plans: [] })),
      kanalAbgleich: (...args: unknown[]) => kanalAbgleich(...args),
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
