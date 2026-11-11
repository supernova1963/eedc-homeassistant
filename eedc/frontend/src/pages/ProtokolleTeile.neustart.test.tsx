/**
 * E6.B G1 (Lab rc32 Nr. 8): nach «Neustart» stehen Knopf «Startet neu...» und der Satz `NEUSTART_LAEUFT`, **bevor**
 * `systemLogsApi.restart()` antwortet — im Add-on wartet der Aufruf auf den Supervisor, bis dahin stand nichts da.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, act } from '@testing-library/react'

const restart = vi.fn()
const health = vi.fn()
vi.mock('../api/systemLogs', () => ({
  systemLogsApi: {
    getLogs: () => Promise.resolve([]),
    getActivities: () => Promise.resolve({ items: [], total: 0 }),
    getKategorien: () => Promise.resolve([]),
    cleanupActivities: () => Promise.resolve({ erfolg: true, message: '' }),
    getLogLevel: () => Promise.resolve({ level: 'INFO' }),
    setLogLevel: () => Promise.resolve({ erfolg: true, level: 'INFO' }),
    restart: () => restart(),
  },
}))
vi.mock('../api/system', () => ({ systemApi: { health: () => health() } }))

import { ProtokolleVerwaltung } from './ProtokolleTeile'
import { NEUSTART_LAEUFT } from '../hooks/useNeustartWarten'

describe('ProtokolleVerwaltung — Neustart', () => {
  beforeEach(() => {
    restart.mockReset()
    health.mockReset()
    vi.spyOn(window, 'confirm').mockReturnValue(true)
  })
  afterEach(() => { vi.restoreAllMocks() })

  it('zeigt den Hinweis, bevor restart() antwortet', async () => {
    restart.mockReturnValue(new Promise(() => {}))  // antwortet nie (Supervisor hält die Verbindung)
    render(<ProtokolleVerwaltung />)
    expect(screen.queryByText(NEUSTART_LAEUFT)).toBeNull()
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: /Neustart/ })) })
    expect(restart).toHaveBeenCalledTimes(1)
    expect(screen.getByText(NEUSTART_LAEUFT)).toBeTruthy()
    expect(screen.getByRole('button', { name: /Startet neu/ })).toHaveProperty('disabled', true)
    expect(health).not.toHaveBeenCalled()
  })
})
