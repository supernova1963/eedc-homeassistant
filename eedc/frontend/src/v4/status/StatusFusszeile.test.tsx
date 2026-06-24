import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { StatusFusszeile } from './StatusFusszeile'
import { AppStatusProvider, useReportDatenStatus, type SichtStatus } from './AppStatusContext'

// Global-Zone-Quellen mocken (Shell-Ebene, P2).
const checkUpdate = vi.fn()
const getNaechsterMonat = vi.fn()
const getMqttStatus = vi.fn()
const datenCheck = vi.fn()

vi.mock('../../api/system', () => ({ systemApi: { checkUpdate: () => checkUpdate() } }))
vi.mock('../../api/monatsabschluss', () => ({ monatsabschlussApi: { getNaechsterMonat: () => getNaechsterMonat() } }))
vi.mock('../../api/liveDashboard', () => ({ liveDashboardApi: { getMqttStatus: () => getMqttStatus() } }))
vi.mock('../../api/datenChecker', () => ({ datenCheckerApi: { check: () => datenCheck() } }))
vi.mock('../../hooks', () => ({ useSelectedAnlage: () => ({ selectedAnlage: { id: 7 } }) }))

beforeEach(() => {
  checkUpdate.mockResolvedValue({ update_verfuegbar: false, aktuelle_version: '3.45.5' })
  getNaechsterMonat.mockResolvedValue(null)
  getMqttStatus.mockResolvedValue({ subscriber_aktiv: false })
  datenCheck.mockResolvedValue({ zusammenfassung: { error: 0, warning: 0, info: 0, ok: 5 } })
})

/** Hilfs-Sicht, die einen Status meldet — simuliert eine echte v4-Sicht. */
function MeldeSicht({ status }: { status: SichtStatus }) {
  useReportDatenStatus(status)
  return null
}

function renderMit(status: SichtStatus, search = '') {
  return render(
    <MemoryRouter initialEntries={[`/v4/cockpit/live${search}`]}>
      <AppStatusProvider>
        <MeldeSicht status={status} />
        <StatusFusszeile />
      </AppStatusProvider>
    </MemoryRouter>,
  )
}

describe('StatusFusszeile — Sicht-Zone (P1)', () => {
  it('zeigt die Frische der gemeldeten Sicht', () => {
    renderMit({ live: true, aktualisiertText: '09:59:57', intervallText: '(5s)' })
    expect(screen.getByText(/09:59:57/)).toBeInTheDocument()
  })

  it('öffnet ein Popover mit Detail beim Klick', () => {
    renderMit({ live: true, aktualisiertText: '09:59:57', intervallText: '(5s)' })
    fireEvent.click(screen.getByLabelText('Live-Daten aktuell'))
    expect(screen.getByRole('dialog')).toHaveTextContent('Aktualisiert 09:59:57')
  })

  it('blendet den Demo-Schalter nur unter ?debug ein', () => {
    renderMit({ aktualisiertText: '10:00:00' })
    expect(screen.queryByText(/Demo/)).not.toBeInTheDocument()
    renderMit({ aktualisiertText: '10:00:00' }, '?debug')
    expect(screen.getByText(/Demo/)).toBeInTheDocument()
  })

  it('zeigt die Datenquelle (Provenance), wenn die Sicht sie meldet (P5)', () => {
    renderMit({ quelle: 'Live-Sensoren', aktualisiertText: '10:00:00' })
    const btn = screen.getByLabelText('Datenquelle')
    fireEvent.click(btn)
    expect(screen.getByRole('dialog')).toHaveTextContent('Live-Sensoren')
  })
})

describe('StatusFusszeile — Global-Zone (P2)', () => {
  it('zeigt das Versions-Update-Symbol nur bei verfügbarem Update', async () => {
    checkUpdate.mockResolvedValue({ update_verfuegbar: true, aktuelle_version: '3.45.5', neueste_version: '3.46.0', release_url: 'https://x/y' })
    renderMit({})
    expect(await screen.findByLabelText(/eedc v3\.46\.0 verfügbar/)).toBeInTheDocument()
  })

  it('zeigt offenen Monatsabschluss (warning) mit Deep-Link', async () => {
    getNaechsterMonat.mockResolvedValue({ anlage_id: 7, jahr: 2025, monat: 12, monat_name: 'Dezember' })
    renderMit({})
    const btn = await screen.findByLabelText('Monatsabschluss offen')
    fireEvent.click(btn)
    expect(screen.getByRole('dialog')).toHaveTextContent('Dezember 2025')
    expect(screen.getByText('Öffnen →')).toBeInTheDocument()
  })

  it('zeigt das MQTT-Symbol nur bei aktivem Subscriber', async () => {
    getMqttStatus.mockResolvedValue({ subscriber_aktiv: true, broker: 'test', empfangene_nachrichten: 42 })
    renderMit({})
    await waitFor(() => expect(screen.getByLabelText('MQTT-Inbound aktiv')).toBeInTheDocument())
  })

  it('zeigt das Daten-Checker-Symbol nur bei Befunden, mit schlimmster Severity im Detail', async () => {
    datenCheck.mockResolvedValue({ zusammenfassung: { error: 0, warning: 2, info: 1, ok: 3 } })
    renderMit({})
    const btn = await screen.findByLabelText('Daten-Checker')
    fireEvent.click(btn)
    expect(screen.getByRole('dialog')).toHaveTextContent('2 Warnungen · 1 Hinweis')
  })

  it('blendet das Daten-Checker-Symbol bei „alles ok" aus', async () => {
    datenCheck.mockResolvedValue({ zusammenfassung: { error: 0, warning: 0, info: 0, ok: 9 } })
    renderMit({})
    // MQTT-Symbol erscheint nicht (inaktiv) — auf einen stabilen Zustand warten:
    await waitFor(() => expect(checkUpdate).toHaveBeenCalled())
    expect(screen.queryByLabelText('Daten-Checker')).not.toBeInTheDocument()
  })
})
