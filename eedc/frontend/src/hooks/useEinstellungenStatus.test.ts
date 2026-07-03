import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { useEinstellungenStatus } from './useEinstellungenStatus'
import type { GlobalStatus } from '../v4/status/useGlobalStatus'
import type { CheckErgebnis } from '../api/datenChecker'

// ── Quellen mocken (nur vorhandene Signale, kein Netz) ──
const globalStatus = vi.fn()
const selectedAnlage = vi.fn()
const getAktivePrognose = vi.fn()

vi.mock('../v4/status/useGlobalStatus', () => ({ useGlobalStatus: () => globalStatus() }))
vi.mock('./useSelectedAnlage', () => ({ useSelectedAnlage: () => selectedAnlage() }))
vi.mock('../api/pvgis', () => ({ pvgisApi: { getAktivePrognose: (id: number) => getAktivePrognose(id) } }))

/** Voll-Global-Status mit optionalen Befunden. */
function gs(over: Partial<GlobalStatus> = {}): GlobalStatus {
  return {
    update: null, offenerMonat: null, mqtt: null,
    datencheck: null, datencheckErgebnisse: null, communityGeteilt: null, anlageId: 7,
    ...over,
  }
}

const befund = (kategorie: string, schwere: CheckErgebnis['schwere'], meldung = 'x'): CheckErgebnis =>
  ({ kategorie, schwere, meldung })

beforeEach(() => {
  globalStatus.mockReturnValue(gs())
  selectedAnlage.mockReturnValue({ selectedAnlage: { id: 7, community_auto_share: false } })
  getAktivePrognose.mockResolvedValue(null)
})

describe('useEinstellungenStatus — Signal → Status', () => {
  it('projiziert eine Kategorie-Warnung auf warn + Meldung als Hinweis', async () => {
    globalStatus.mockReturnValue(gs({
      datencheckErgebnisse: [befund('strompreise', 'warning', 'Tarif-Lücke ab Mai')],
    }))
    const { result } = renderHook(() => useEinstellungenStatus())
    await waitFor(() => expect(result.current.solarprognose).toBeDefined())
    expect(result.current.strompreise).toEqual({ status: 'warn', hinweis: 'Tarif-Lücke ab Mai' })
  })

  it('meldet ✓ für Anlage/Strompreise/Sensor-Mapping, wenn keine Befunde vorliegen', async () => {
    globalStatus.mockReturnValue(gs({ datencheckErgebnisse: [] }))
    const { result } = renderHook(() => useEinstellungenStatus())
    await waitFor(() => expect(result.current.solarprognose).toBeDefined())
    expect(result.current.anlage).toEqual({ status: 'ok' })
    expect(result.current.strompreise).toEqual({ status: 'ok' })
    expect(result.current['sensor-mapping']).toEqual({ status: 'ok' })
  })

  it('meldet „neu" für Anlage, wenn keine Anlage ausgewählt ist', () => {
    selectedAnlage.mockReturnValue({ selectedAnlage: undefined })
    const { result } = renderHook(() => useEinstellungenStatus())
    expect(result.current.anlage).toEqual({ status: 'neu', hinweis: 'Noch keine Anlage angelegt.' })
    expect(result.current.strompreise).toBeUndefined()
  })

  it('aggregiert das Daten-Checker-Symbol aus den Befunden (schlimmste Schwere)', async () => {
    globalStatus.mockReturnValue(gs({
      datencheckErgebnisse: [befund('monatsdaten_plausibilitaet', 'error'), befund('strompreise', 'warning')],
    }))
    const { result } = renderHook(() => useEinstellungenStatus())
    await waitFor(() => expect(result.current.datenchecker).toBeDefined())
    expect(result.current.datenchecker).toEqual({ status: 'warn', hinweis: '1 Fehler, 1 Warnung.' })
  })

  it('leitet MQTT-Export + -Inbound aus demselben MQTT-Status ab', () => {
    globalStatus.mockReturnValue(gs({ mqtt: { verfuegbar: true, subscriber_aktiv: true } }))
    const { result } = renderHook(() => useEinstellungenStatus())
    expect(result.current['ha-export']).toEqual({ status: 'ok' })
    expect(result.current['mqtt-inbound']).toEqual({ status: 'ok' })
  })

  it('meldet „neu" für MQTT ohne Konfiguration (mit Grund)', () => {
    globalStatus.mockReturnValue(gs({ mqtt: { verfuegbar: false, subscriber_aktiv: false, grund: 'Kein Broker' } }))
    const { result } = renderHook(() => useEinstellungenStatus())
    expect(result.current['mqtt-inbound']).toEqual({ status: 'neu', hinweis: 'Kein Broker' })
  })

  it('leitet Solarprognose aus dem Alter der aktiven Prognose ab', async () => {
    const alt = new Date(Date.now() - 10 * 86_400_000).toISOString()
    getAktivePrognose.mockResolvedValue({ abgerufen_am: alt })
    const { result } = renderHook(() => useEinstellungenStatus())
    await waitFor(() => expect(result.current.solarprognose?.status).toBe('warn'))
    expect(result.current.solarprognose?.hinweis).toMatch(/vor 10 Tagen/)
  })

  it('meldet „neu" für Solarprognose, wenn nie abgerufen', async () => {
    getAktivePrognose.mockResolvedValue(null)
    const { result } = renderHook(() => useEinstellungenStatus())
    await waitFor(() => expect(result.current.solarprognose).toEqual({ status: 'neu', hinweis: 'Noch nie abgerufen.' }))
  })

  it('leitet Community-Share aus dem Auto-Share-Flag ab', () => {
    selectedAnlage.mockReturnValue({ selectedAnlage: { id: 7, community_auto_share: true } })
    const { result } = renderHook(() => useEinstellungenStatus())
    expect(result.current.community).toEqual({ status: 'ok' })
  })
})
