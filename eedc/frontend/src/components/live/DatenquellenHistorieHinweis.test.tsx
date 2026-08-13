/**
 * Konzept #192 B — die Fläche sagt, dass eine neue Zuordnung nicht rückwirkend gilt.
 *
 * Die gespeicherten Tages- und Stundenwerte tragen die Zuordnung ihres
 * Aggregationslaufs. Bis 2026-08-13 quittierte die Fläche eine Änderung
 * kommentarlos, und der Anwender merkte es über Drift oder gar nicht.
 *
 * ⚠ Geprüft wird die **Wirkung für den Anwender** (Text da / weg / Aufruf), nicht
 * die Existenz einzelner Elemente.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import DatenquellenZuordnung from './DatenquellenZuordnung'
import { datenquellenApi } from '../../api/datenquellen'

const HINWEIS = {
  felder: [
    { id: 'basis_energy_netzbezug', label: 'Netzbezug (kWh)' },
    { id: 'inv_energy_7_pv_erzeugung_kwh', label: 'Süd – PV-Erzeugung (kWh)' },
  ],
  seit: '2026-08-13T06:12:00+02:00',
}

vi.mock('../../api/datenquellen', () => {
  const f = {
    id: 'basis_energy_netzbezug', feld: 'netzbezug', typ: 'basis',
    label: 'Netzbezug', einheit: 'kWh', kategorie: 'energy',
    hinweis: '', standard_topic: 'eedc/1/energy/netzbezug_kwh',
    quelle: 'keine', gateway_topic: null, ha_entity: null, ha_name: null,
    invertieren: false, wert: null, wert_zeit: null, probleme: [],
    bedarf: 'optional', bedarf_grund: null, bedarf_text: null,
  }
  return {
    VERBINDUNG_GEAENDERT_EVENT: 'eedc:verbindung-geaendert',
    datenquellenApi: {
      getFelder: vi.fn(() => Promise.resolve({
        gruppen: [{ id: 'basis', titel: 'Anlage (Basis)', typ: 'basis', felder: [f] }],
        verfuegbarkeit: { ha: true, mqtt: true, ha_quelle: 'ha_app' },
        historie_hinweis: null,
      })),
      setQuelle: vi.fn(() => Promise.resolve({
        gespeichert: true, field_id: f.id, quelle: 'mqtt_inbound_standard',
        historie_hinweis: null,
      })),
      setInvert: vi.fn(() => Promise.resolve({
        field_id: f.id, invertieren: true, historie_hinweis: null,
      })),
      quittiereHistorieHinweis: vi.fn(() => Promise.resolve({ quittiert: true })),
      haSensoren: vi.fn(() => Promise.resolve({
        sensoren: [], vorschlaege: [], integrationen: [], warnungen: {},
      })),
      taktCheck: vi.fn(() => Promise.resolve({ geprueft: false })),
    },
  }
})

vi.mock('../../hooks', async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  useSelectedAnlage: () => ({ selectedAnlageId: 1, selectedAnlage: { id: 1, anlagenname: 'Test' } }),
}))

const api = datenquellenApi as unknown as Record<string, ReturnType<typeof vi.fn>>

describe('Datenquellen-Fläche — Hinweis auf die unberührte Historie', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    api.getFelder.mockResolvedValue({
      gruppen: [{
        id: 'basis', titel: 'Anlage (Basis)', typ: 'basis',
        felder: [{
          id: 'basis_energy_netzbezug', feld: 'netzbezug', typ: 'basis',
          label: 'Netzbezug', einheit: 'kWh', kategorie: 'energy',
          hinweis: '', standard_topic: 'eedc/1/energy/netzbezug_kwh',
          quelle: 'keine', gateway_topic: null, ha_entity: null, ha_name: null,
          invertieren: false, wert: null, wert_zeit: null, probleme: [],
          bedarf: 'optional', bedarf_grund: null, bedarf_text: null,
        }],
      }],
      verfuegbarkeit: { ha: true, mqtt: true, ha_quelle: 'ha_app' },
      historie_hinweis: null,
    })
  })

  it('schweigt, solange keine Zuordnung geändert wurde', async () => {
    render(<DatenquellenZuordnung />)
    expect(await screen.findByText(/Pro eedc-Feld genau eine Datenquelle/)).toBeInTheDocument()
    expect(screen.queryByText(/Zuordnung geändert/)).not.toBeInTheDocument()
  })

  it('nennt die geänderten Felder und sagt, was mit den alten Werten ist', async () => {
    api.getFelder.mockResolvedValueOnce({
      gruppen: [{ id: 'basis', titel: 'Anlage (Basis)', typ: 'basis', felder: [] }],
      verfuegbarkeit: { ha: true, mqtt: true, ha_quelle: 'ha_app' },
      historie_hinweis: HINWEIS,
    })
    render(<DatenquellenZuordnung />)
    expect(await screen.findByText(/Zuordnung geändert/)).toBeInTheDocument()
    expect(screen.getByText(/Netzbezug \(kWh\) · Süd – PV-Erzeugung \(kWh\)/)).toBeInTheDocument()
    // Der Kern der Aussage: die bereits gespeicherten Werte ändern sich NICHT.
    expect(screen.getByText(/stammen weiter aus der vorherigen Zuordnung/)).toBeInTheDocument()
    // Und der Weg dorthin, statt „melde dich beim Support".
    expect(screen.getByRole('button', { name: /Reparatur-Werkbank/ })).toBeInTheDocument()
  })

  it('erscheint sofort nach einer Änderung — ohne Neuladen der Seite', async () => {
    api.setQuelle.mockResolvedValueOnce({
      gespeichert: true, field_id: 'basis_energy_netzbezug',
      quelle: 'mqtt_inbound_standard', historie_hinweis: HINWEIS,
    })
    render(<DatenquellenZuordnung />)
    const inbound = await screen.findByRole('button', { name: /Inbound/i })
    fireEvent.click(inbound)
    expect(await screen.findByText(/Zuordnung geändert/)).toBeInTheDocument()
  })

  it('„Verstanden" quittiert beim Server und blendet den Hinweis aus', async () => {
    api.getFelder.mockResolvedValueOnce({
      gruppen: [{ id: 'basis', titel: 'Anlage (Basis)', typ: 'basis', felder: [] }],
      verfuegbarkeit: { ha: true, mqtt: true, ha_quelle: 'ha_app' },
      historie_hinweis: HINWEIS,
    })
    render(<DatenquellenZuordnung />)
    fireEvent.click(await screen.findByRole('button', { name: /Verstanden/ }))

    await waitFor(() => expect(api.quittiereHistorieHinweis).toHaveBeenCalledWith(1))
    expect(screen.queryByText(/Zuordnung geändert/)).not.toBeInTheDocument()
  })

  it('benennt bei vielen Feldern nur die ersten und zählt den Rest', async () => {
    api.getFelder.mockResolvedValueOnce({
      gruppen: [{ id: 'basis', titel: 'Anlage (Basis)', typ: 'basis', felder: [] }],
      verfuegbarkeit: { ha: true, mqtt: true, ha_quelle: 'ha_app' },
      historie_hinweis: {
        seit: HINWEIS.seit,
        felder: Array.from({ length: 9 }, (_, i) => ({ id: `f${i}`, label: `Feld ${i}` })),
      },
    })
    render(<DatenquellenZuordnung />)
    expect(await screen.findByText(/und 3 weiteren Feldern/)).toBeInTheDocument()
  })
})
