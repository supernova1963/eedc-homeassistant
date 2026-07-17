/**
 * Paket Q (Doppel-Fetch-Bereinigung): useGlobalStatus fetcht EINMAL auf
 * Shell-Ebene (GlobalStatusProvider) — zwei Konsumenten teilen sich die
 * Instanz (vorher: Quintett ×2 + doppeltes MQTT-Polling auf einstellungen/*).
 * Ohne Provider gilt der Fallback-Vertrag: lokal fetchen wie zuvor.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, waitFor, act } from '@testing-library/react'
import { GlobalStatusProvider } from './GlobalStatusProvider'
import { useGlobalStatus } from './useGlobalStatus'

const checkUpdate = vi.fn()
const getNaechsterMonat = vi.fn()
const getMqttStatus = vi.fn()
const datenCheck = vi.fn()
const getAnlage = vi.fn()

vi.mock('../../api/system', () => ({ systemApi: { checkUpdate: () => checkUpdate() } }))
vi.mock('../../api/monatsabschluss', () => ({ monatsabschlussApi: { getNaechsterMonat: () => getNaechsterMonat() } }))
vi.mock('../../api/liveDashboard', () => ({ liveDashboardApi: { getMqttStatus: () => getMqttStatus() } }))
vi.mock('../../api/datenChecker', () => ({ datenCheckerApi: { check: () => datenCheck() } }))
vi.mock('../../api/anlagen', () => ({ anlagenApi: { get: () => getAnlage() } }))
vi.mock('../../hooks', () => ({ useSelectedAnlage: () => ({ selectedAnlage: { id: 7 } }) }))

beforeEach(() => {
  vi.clearAllMocks()
  checkUpdate.mockResolvedValue({ update_verfuegbar: false, aktuelle_version: '3.45.9' })
  getNaechsterMonat.mockResolvedValue(null)
  getMqttStatus.mockResolvedValue({ subscriber_aktiv: true })
  datenCheck.mockResolvedValue({ zusammenfassung: { error: 0, warning: 0, info: 0, ok: 5 }, ergebnisse: [] })
  getAnlage.mockResolvedValue({ id: 7, community_hash: 'abc' })
})
afterEach(() => vi.useRealTimers())

/** Konsument, der (wie StatusFusszeile/useEinstellungenStatus) den Hook nutzt. */
function Konsument({ onStatus }: { onStatus?: (geteilt: boolean | null) => void }) {
  const { communityGeteilt } = useGlobalStatus()
  onStatus?.(communityGeteilt)
  return null
}

describe('useGlobalStatus + GlobalStatusProvider (EINE Instanz)', () => {
  it('zwei Konsumenten unter dem Provider → jeder Endpunkt genau 1×', async () => {
    render(
      <GlobalStatusProvider>
        <Konsument />
        <Konsument />
      </GlobalStatusProvider>,
    )
    await waitFor(() => expect(datenCheck).toHaveBeenCalledTimes(1))
    expect(checkUpdate).toHaveBeenCalledTimes(1)
    expect(getNaechsterMonat).toHaveBeenCalledTimes(1)
    expect(getMqttStatus).toHaveBeenCalledTimes(1)
    expect(getAnlage).toHaveBeenCalledTimes(1)
  })

  it('Konsumenten erhalten die Provider-Daten (Context, kein Eigen-State)', async () => {
    let letzter: boolean | null = null
    render(
      <GlobalStatusProvider>
        <Konsument onStatus={(g) => { letzter = g }} />
      </GlobalStatusProvider>,
    )
    await waitFor(() => expect(letzter).toBe(true))
  })

  it('Gegenprobe/Fallback-Vertrag: OHNE Provider fetcht jede Instanz selbst (wie zuvor)', async () => {
    render(<><Konsument /><Konsument /></>)
    await waitFor(() => expect(datenCheck).toHaveBeenCalledTimes(2))
    expect(checkUpdate).toHaveBeenCalledTimes(2)
    expect(getMqttStatus).toHaveBeenCalledTimes(2)
  })

  it('EIN 30-s-MQTT-Poll-Interval trotz zweier Konsumenten', async () => {
    vi.useFakeTimers()
    render(
      <GlobalStatusProvider>
        <Konsument />
        <Konsument />
      </GlobalStatusProvider>,
    )
    await act(async () => { await vi.advanceTimersByTimeAsync(0) })
    expect(getMqttStatus).toHaveBeenCalledTimes(1)
    await act(async () => { await vi.advanceTimersByTimeAsync(30_000) })
    expect(getMqttStatus).toHaveBeenCalledTimes(2)
  })
})
