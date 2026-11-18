import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'

// Triage 3.11.2026 (B2/B1): der Integrations-Schritt zeigt bei einem Abruffehler einen Satz statt des
// Endlos-Ladetexts, und neben den Vorschlägen den Hinweis auf weitere Quellen des Energie-Dashboards.

// Plain-Funktion statt vi.fn: mit `mockRejectedValue`/`mockImplementation` meldete vitest die Ablehnung als
// Testfehler, obwohl die Komponente sie fängt (gemessen 3.11.2026; Ursache nicht weiter verfolgt).
let antwort: () => Promise<unknown> = () => new Promise(() => {})
const getHAEnergySuggestions = (_id: number) => antwort()

vi.mock('../../../hooks/useHAAvailable', () => ({ useHAAvailable: () => true }))
vi.mock('../../../api/sensorMapping', () => ({
  sensorMappingApi: { getHAEnergySuggestions: (id: number) => getHAEnergySuggestions(id) },
}))
vi.mock('../../../api/datenquellen', () => ({ datenquellenApi: { uebernehmeEnergyVorschlaege: vi.fn() } }))
vi.mock('../../../api/haRemote', () => ({ haRemoteApi: { test: vi.fn(), saveSettings: vi.fn() } }))
vi.mock('../../../api/liveDashboard', () => ({ liveDashboardApi: { saveMqttSettings: vi.fn() } }))
vi.mock('../../../api/ha', () => ({ haApi: { setAutoPublish: vi.fn() } }))

import IntegrationStep, { UEBERSPRUNGEN_SATZ } from './IntegrationStep'
import { datenquellenApi } from '../../../api/datenquellen'

function aufbau() {
  render(<IntegrationStep anlageId={1} onNext={vi.fn()} onBack={vi.fn()} onSkip={vi.fn()} />)
}

describe('IntegrationStep — Energy-Dashboard-Vorschläge', () => {
  beforeEach(() => { antwort = () => new Promise(() => {}) })

  it('Abruffehler: ein Satz statt «Vorschläge werden geladen …»', async () => {
    antwort = () => Promise.reject(new Error('kein JSON'))
    aufbau()
    expect(await screen.findByText(/Die Vorschläge ließen sich nicht abrufen/)).toBeInTheDocument()
    expect(screen.queryByText(/Vorschläge werden geladen/)).not.toBeInTheDocument()
  })

  it('mit Vorschlägen: Hinweis auf weitere Quellen des Energie-Dashboards', async () => {
    antwort = () => Promise.resolve({
      available: true, basis: { netzbezug: 'sensor.netz' }, investitionen: {},
      device_consumption_raw: [], investition_matches: [],
    })
    aufbau()
    expect(await screen.findByText(/eedc schlägt je Feld eine Quelle vor/)).toBeInTheDocument()
    expect(screen.getByText(/sensor\.netz/)).toBeInTheDocument()
  })

  it('Sensorwechsel 3b-K (Mutant F07): Felder mit eigenen Werten werden nicht übernommen und genannt', async () => {
    antwort = () => Promise.resolve({
      available: true, basis: { netzbezug: 'sensor.netz' }, investitionen: {},
      device_consumption_raw: [], investition_matches: [],
    })
    vi.mocked(datenquellenApi.uebernehmeEnergyVorschlaege).mockResolvedValue({
      anzahl: 0, uebersprungen: [{ field_id: 'basis_energy_netzbezug_kwh', label: 'Netzbezug Zählerstand' }],
    } as never)
    aufbau()
    fireEvent.click(await screen.findByRole('button', { name: 'Ausgewählte übernehmen' }))
    const satz = await screen.findByText((_t, el) => el?.hasAttribute('data-uebersprungen') ?? false)
    expect(satz.textContent).toBe(`${UEBERSPRUNGEN_SATZ} Netzbezug Zählerstand`)
  })
})
