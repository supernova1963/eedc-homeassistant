/**
 * Bedarfs-Darstellung (§2i-6): Pflicht-Marker, rotes/aufgeklapptes ⓘ, Zählung.
 *
 * Anlass: der Rollup zählte jedes Feld ohne Quelle und färbte es amber. Auf einer
 * korrekt eingerichteten Anlage sind das gerade die Felder, die leer sein SOLLEN
 * (Anlagen-Aggregat neben Modul-Zählern, „Netz kombiniert" neben getrennten
 * Sensoren, optionale Felder) — gemessen 3 von 3 Meldungen Fehlalarm. Umgekehrt
 * blieb ein wirklich fehlendes Pflichtfeld genauso leise.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import DatenquellenZuordnung from './DatenquellenZuordnung'

const basisFeld = (over: Record<string, unknown>) => ({
  id: 'f1', feld: 'einspeisung_kwh', typ: 'basis',
  label: 'Einspeisung Zählerstand', einheit: 'kWh', kategorie: 'energy',
  hinweis: 'Kernwert für Eigenverbrauch und Autarkie.',
  standard_topic: 'eedc/1/energy/einspeisung_kwh',
  quelle: 'keine', gateway_topic: null, ha_entity: null, ha_name: null,
  invertieren: false, wert: null, wert_zeit: null, probleme: [],
  bedarf: 'optional', bedarf_grund: null, bedarf_text: null,
  ...over,
})

const felderMock = vi.hoisted(() => ({ felder: [] as Record<string, unknown>[] }))

vi.mock('../../hooks', async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  useSelectedAnlage: () => ({ selectedAnlageId: 1, selectedAnlage: { id: 1, anlagenname: 'Test' } }),
}))

vi.mock('../../api/datenquellen', () => ({
  VERBINDUNG_GEAENDERT_EVENT: 'eedc:verbindung-geaendert',
  datenquellenApi: {
    getFelder: vi.fn(() => Promise.resolve({
      gruppen: [{ id: 'basis', label: 'Anlage (Basis)', typ: 'basis', felder: felderMock.felder }],
      verfuegbarkeit: { ha: true, mqtt: false, ha_quelle: 'ha_app' },
    })),
    setQuelle: vi.fn(() => Promise.resolve({})),
    getHaSensoren: vi.fn(() => Promise.resolve({ sensoren: [] })),
    scanGatewayTopics: vi.fn(() => Promise.resolve({ topics: [] })),
  },
}))

describe('Bedarfs-Darstellung', () => {
  beforeEach(() => { felderMock.felder = [] })

  it('zeigt beim offenen Pflichtfeld den Marker und den Hinweis ohne Klick', async () => {
    felderMock.felder = [basisFeld({ bedarf: 'pflicht' })]
    render(<DatenquellenZuordnung />)
    await waitFor(() => expect(screen.getByText('Einspeisung Zählerstand (kWh)')).toBeInTheDocument())
    expect(screen.getByTitle('Pflichtfeld')).toBeInTheDocument()
    // Aufgeklappt, obwohl niemand auf das ⓘ geklickt hat.
    expect(screen.getByText(/Kernwert für Eigenverbrauch/)).toBeInTheDocument()
  })

  it('zählt ein leeres Pflichtfeld als offen', async () => {
    felderMock.felder = [basisFeld({ bedarf: 'pflicht' })]
    render(<DatenquellenZuordnung />)
    await waitFor(() => expect(screen.getByText(/1 noch ohne Quelle/)).toBeInTheDocument())
  })

  it('zählt optionale und inaktive Felder NICHT als offen', async () => {
    felderMock.felder = [
      basisFeld({ id: 'f1', bedarf: 'optional' }),
      basisFeld({
        id: 'f2', feld: 'pv_gesamt_kwh', label: 'PV-Erzeugung Zählerstand',
        bedarf: 'inaktiv', bedarf_grund: 'gruppe:pv_energie',
        bedarf_text: 'Die PV-Erzeugung ist bereits an anderer Stelle zugeordnet.',
      }),
    ]
    render(<DatenquellenZuordnung />)
    await waitFor(() => expect(screen.getByText('2 Felder')).toBeInTheDocument())
    expect(screen.queryByText(/ohne Quelle/)).not.toBeInTheDocument()
  })

  it('erklärt bei inaktiv den Grund statt „keine Quelle" zu melden', async () => {
    felderMock.felder = [basisFeld({
      bedarf: 'inaktiv', bedarf_grund: 'keine_wallbox',
      bedarf_text: 'Die Wallbox ist die maßgebliche Quelle der Heimladung — dort zuordnen, nicht hier.',
    })]
    render(<DatenquellenZuordnung />)
    await waitFor(() => expect(screen.getByText(/Die Wallbox ist die maßgebliche Quelle/)).toBeInTheDocument())
    expect(screen.queryByText('keine Quelle')).not.toBeInTheDocument()
  })

  it('lässt ein belegtes Pflichtfeld unmarkiert', async () => {
    felderMock.felder = [basisFeld({
      bedarf: 'pflicht', quelle: 'ha_app', ha_entity: 'sensor.x', ha_name: 'Zähler', wert: 42,
    })]
    render(<DatenquellenZuordnung />)
    await waitFor(() => expect(screen.getByText(/sensor\.x/)).toBeInTheDocument())
    expect(screen.queryByText(/noch ohne Quelle/)).not.toBeInTheDocument()
    // Marker bleibt (es IST ein Pflichtfeld), aber der Hinweis ist zugeklappt.
    expect(screen.getByTitle('Pflichtfeld')).toBeInTheDocument()
    expect(screen.queryByText(/Kernwert für Eigenverbrauch/)).not.toBeInTheDocument()
  })
})
