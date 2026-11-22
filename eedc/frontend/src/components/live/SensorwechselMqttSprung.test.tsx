/**
 * Sensorwechsel U3 Lauf b (Rechenweg G4) — der Sprung des Daten-Checkers an MQTT-Reihen.
 *
 * Befund «Zählerstand springt (MQTT)»: der Sprung `?feld=…&getauscht=<Zeit>` öffnet an der Datenquellen-Fläche den Dialog
 * «Zähler getauscht (gleiche Quelle)» beim Feld, «Getauscht am» steht auf der Zeit aus dem Befund, die Prüfung fragt mit ihr; ohne
 * `getauscht` öffnet nichts. Der Client rechnet nichts. Der Befund «versetzter Abschnitt» (G7) samt Stück-Dialog ist seit Weg B,
 * Sitzung B3a, entfernt.
 *
 * Schwesterdatei: ZaehlerGetauschtDialog (Einstieg am Feld).
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import DatenquellenZuordnung from './DatenquellenZuordnung'
import { ZG_TITEL } from './ZaehlerGetauschtDialog'
import { datenquellenApi } from '../../api/datenquellen'

vi.mock('../../api/datenquellen', () => {
  const f = {
    id: 'basis_energy_netzbezug_kwh', feld: 'netzbezug_kwh', typ: 'basis',
    label: 'Netzbezug', einheit: 'kWh', kategorie: 'energy',
    hinweis: '', standard_topic: 'eedc/1/energy/netzbezug_kwh',
    quelle: 'mqtt_inbound', gateway_topic: null, ha_entity: null, ha_name: null,
    invertieren: false, wert: 42, wert_zeit: null, probleme: [],
  }
  return {
    VERBINDUNG_GEAENDERT_EVENT: 'eedc:verbindung-geaendert',
    datenquellenApi: {
      getFelder: vi.fn(() => Promise.resolve({
        gruppen: [{ id: 'basis', label: 'Anlage (Basis)', typ: 'basis', felder: [f] }],
        verfuegbarkeit: { ha: false, mqtt: true, ha_quelle: null },
      })),
      pruefeQuelle: vi.fn(),
      korrekturLaeufe: vi.fn(() => Promise.resolve([])),
      wartendeWechsel: vi.fn(() => Promise.resolve([])),
      korrekturLauf: vi.fn(() => new Promise(() => {})),
      setQuelle: vi.fn(),
      pruefeZaehlerGetauscht: vi.fn(),
      zaehlerGetauscht: vi.fn(),
      haSensoren: vi.fn(() => Promise.resolve({ sensoren: [], vorschlaege: [], integrationen: [], warnungen: {} })),
      taktCheck: vi.fn(() => Promise.resolve({ geprueft: false })),
    },
  }
})

vi.mock('../../hooks', async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  useSelectedAnlage: () => ({ selectedAnlageId: 1, selectedAnlage: { id: 1, anlagenname: 'Test' } }),
}))

beforeEach(() => { vi.useFakeTimers({ now: new Date(2026, 5, 18, 12, 0), shouldAdvanceTime: true }) })
afterEach(() => { vi.useRealTimers() })

const ANTWORT = {
  weg: 'fortsetzung' as const, sensor_key: 'basis:netzbezug', eintragen: true, getauscht_am: '2026-06-17T10:20:00',
  saetze: ['eedc trägt den Tausch am 17.06.2026 10:20 Uhr ein: dort springt der Zählerstand von 5.197,0 auf 7.197,1 kWh.'],
}

describe('Sensorwechsel U3 b — Sprung «Zähler getauscht» mit Zeit', () => {
  beforeEach(() => vi.clearAllMocks())

  it('getauscht= öffnet den Dialog beim Feld mit vorbelegtem «Getauscht am»', async () => {
    vi.mocked(datenquellenApi.pruefeZaehlerGetauscht).mockResolvedValue(ANTWORT)
    render(<DatenquellenZuordnung sprung={{ feld: 'netzbezug_kwh', getauscht: '2026-06-17T10:20' }} />)
    await waitFor(() => expect(document.querySelector('[data-zaehler-getauscht="basis_energy_netzbezug_kwh"]')).not.toBeNull())
    expect(screen.getByText(`${ZG_TITEL} — Netzbezug (kWh)`)).toBeInTheDocument()
    await waitFor(() => expect(datenquellenApi.pruefeZaehlerGetauscht)
      .toHaveBeenCalledWith(1, 'basis_energy_netzbezug_kwh', '2026-06-17T10:20'))
    expect(await screen.findByText(ANTWORT.saetze[0])).toBeInTheDocument()
    expect((document.querySelector('[data-getauscht-am]') as HTMLInputElement).value).toBe('2026-06-17T10:20')
    expect(datenquellenApi.zaehlerGetauscht).not.toHaveBeenCalled()
  })

  it('ohne getauscht= öffnet kein Dialog', async () => {
    render(<DatenquellenZuordnung sprung={{ feld: 'netzbezug_kwh' }} />)
    await waitFor(() => expect(datenquellenApi.getFelder).toHaveBeenCalled())
    await waitFor(() => expect(document.querySelector('[data-feld="basis_energy_netzbezug_kwh"]')).not.toBeNull())
    expect(document.querySelector('[data-zaehler-getauscht]')).toBeNull()
    expect(datenquellenApi.pruefeZaehlerGetauscht).not.toHaveBeenCalled()
  })
})
