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

  it('meldet ✓ für Anlage/Strompreise/Datenquellen, wenn keine Befunde vorliegen', async () => {
    globalStatus.mockReturnValue(gs({ datencheckErgebnisse: [] }))
    const { result } = renderHook(() => useEinstellungenStatus())
    await waitFor(() => expect(result.current.solarprognose).toBeDefined())
    expect(result.current.anlage).toEqual({ status: 'ok' })
    expect(result.current.strompreise).toEqual({ status: 'ok' })
    // B7: die Sensor-Mapping-Befunde tragen jetzt die Datenquellen-Ampel.
    expect(result.current.datenquellen).toEqual({ status: 'ok' })
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

  it('leitet MQTT-Export aus dem MQTT-Status ab', () => {
    globalStatus.mockReturnValue(gs({ mqtt: { verfuegbar: true, subscriber_aktiv: true } }))
    const { result } = renderHook(() => useEinstellungenStatus())
    expect(result.current['ha-export']).toEqual({ status: 'ok' })
    // B7: kein eigener mqtt-inbound-Block mehr → keine Ampel dafür.
    expect(result.current['mqtt-inbound']).toBeUndefined()
  })

  it('meldet „neu" für MQTT ohne Konfiguration (mit Grund)', () => {
    globalStatus.mockReturnValue(gs({ mqtt: { verfuegbar: false, subscriber_aktiv: false, grund: 'Kein Broker' } }))
    const { result } = renderHook(() => useEinstellungenStatus())
    expect(result.current['ha-export']).toEqual({ status: 'neu', hinweis: 'Kein Broker' })
  })

  it('warnt bei der Solarprognose, wenn sie nicht mehr zur Anlage passt', async () => {
    getAktivePrognose.mockResolvedValue({
      abgerufen_am: new Date().toISOString(),
      passt_zur_anlage: false,
      abweichung_text: 'Nennleistung 9,80 → 2,40 kWp',
    })
    const { result } = renderHook(() => useEinstellungenStatus())
    await waitFor(() => expect(result.current.solarprognose?.status).toBe('warn'))
    expect(result.current.solarprognose?.hinweis).toBe(
      'Passt nicht mehr zur Anlage: Nennleistung 9,80 → 2,40 kWp.',
    )
  })

  // Die ABGRENZUNG zur abgelösten Regel (#363): bis v4.0.11 warnte die Kachel ab
  // sieben Tagen Alter. Eine alte, aber passende Prognose ist kein Befund —
  // PVGIS rechnet auf einem festen Klimamittel, ein Neuabruf brächte dieselbe
  // Zahl. Diese Probe fällt, sobald jemand die Alters-Regel zurückholt.
  it('schweigt bei einer alten Prognose, solange sie zur Anlage passt', async () => {
    const vorEinemJahr = new Date(Date.now() - 365 * 86_400_000).toISOString()
    getAktivePrognose.mockResolvedValue({
      abgerufen_am: vorEinemJahr,
      passt_zur_anlage: true,
      abweichung_text: null,
    })
    const { result } = renderHook(() => useEinstellungenStatus())
    await waitFor(() => expect(result.current.solarprognose).toEqual({ status: 'ok' }))
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
