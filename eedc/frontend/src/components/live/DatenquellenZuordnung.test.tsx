/**
 * DatenquellenZuordnung — Klick-Semantik der Quellen-Knöpfe.
 *
 * Bis v4.0.0 schaltete ein erneuter Klick auf die AKTIVE Quelle auf „keine
 * Quelle" zurück. Damit bedeutete derselbe Knopf je nach Zustand „Picker öffnen"
 * oder „Zuordnung verwerfen" — wer nur nachsehen wollte, welcher Sensor
 * hinterlegt ist, verlor ihn ohne Rückfrage (Rainer-PN 2026-07-25). Zum
 * Entfernen gibt es den eigenen „Keine"-Knopf.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import DatenquellenZuordnung from './DatenquellenZuordnung'
import { datenquellenApi } from '../../api/datenquellen'

const feld = {
  id: 'basis.pv_gesamt_kwh', feld: 'pv_gesamt_kwh', typ: 'basis',
  label: 'PV-Erzeugung Zählerstand', einheit: 'kWh', kategorie: 'energy' as const,
  hinweis: '', standard_topic: 'eedc/1/energy/pv_gesamt_kwh',
  quelle: 'ha_app', gateway_topic: null,
  ha_entity: 'sensor.pv_gesamt', ha_name: 'PV Gesamt Zähler',
  invertieren: false, wert: 42, wert_zeit: null, probleme: [],
}

// Die Factory wird gehoistet — Fixture und Spione müssen darin entstehen.
vi.mock('../../api/datenquellen', () => {
  const f = {
    id: 'basis.pv_gesamt_kwh', feld: 'pv_gesamt_kwh', typ: 'basis',
    label: 'PV-Erzeugung Zählerstand', einheit: 'kWh', kategorie: 'energy',
    hinweis: '', standard_topic: 'eedc/1/energy/pv_gesamt_kwh',
    quelle: 'ha_app', gateway_topic: null,
    ha_entity: 'sensor.pv_gesamt', ha_name: 'PV Gesamt Zähler',
    invertieren: false, wert: 42, wert_zeit: null, probleme: [],
  }
  return {
    VERBINDUNG_GEAENDERT_EVENT: 'eedc:verbindung-geaendert',
    datenquellenApi: {
      getFelder: vi.fn(() => Promise.resolve({
        gruppen: [{ id: 'basis', label: 'Anlage (Basis)', typ: 'basis', felder: [f] }],
        verfuegbarkeit: { ha: true, mqtt: false, ha_quelle: 'ha_app' },
      })),
      setQuelle: vi.fn(() => Promise.resolve()),
      setInvert: vi.fn(() => Promise.resolve()),
      // Der Picker lädt beim Öffnen die Sensorliste.
      haSensoren: vi.fn(() => Promise.resolve({
        sensoren: [{ entity_id: 'sensor.pv_gesamt', friendly_name: 'PV Gesamt Zähler', unit: 'kWh', state: 42 }],
        vorschlaege: [], integrationen: [], warnungen: {},
      })),
      taktCheck: vi.fn(() => Promise.resolve({ geprueft: false })),
    },
  }
})

vi.mock('../../hooks', async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  useSelectedAnlage: () => ({ selectedAnlageId: 1, selectedAnlage: { id: 1, anlagenname: 'Test' } }),
}))

describe('DatenquellenZuordnung — Quellen-Knöpfe', () => {
  beforeEach(() => vi.clearAllMocks())

  it('zeigt den Klarnamen der zugeordneten Entity neben der ID', async () => {
    render(<DatenquellenZuordnung />)
    expect(await screen.findByText(/PV Gesamt Zähler · sensor\.pv_gesamt/)).toBeInTheDocument()
  })

  it('löscht die Zuordnung NICHT, wenn die aktive Quelle erneut geklickt wird', async () => {
    render(<DatenquellenZuordnung />)
    const haKnopf = await screen.findByRole('button', { name: /HA-Sensor/i })

    fireEvent.click(haKnopf)

    // Statt zu löschen öffnet der Klick den Picker — mit geladener Sensorliste.
    await waitFor(() => expect(datenquellenApi.haSensoren).toHaveBeenCalled())
    expect(datenquellenApi.setQuelle).not.toHaveBeenCalled()
    expect(screen.queryByText(/keine Quelle/)).not.toBeInTheDocument()
  })

  it('entfernt die Zuordnung über den „Keine"-Knopf', async () => {
    render(<DatenquellenZuordnung />)
    const keineKnopf = await screen.findByRole('button', { name: /Keine/i })

    fireEvent.click(keineKnopf)

    await waitFor(() => expect(datenquellenApi.setQuelle).toHaveBeenCalledWith(1, feld.id, 'keine'))
  })
})
