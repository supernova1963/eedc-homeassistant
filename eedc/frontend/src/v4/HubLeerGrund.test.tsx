/**
 * N-247: Der Komponenten-Hub nennt den Grund — und den Knopf nur, wo er wirkt.
 *
 * Gemeldet von CHI3fx117 (T89667 #152): ein frisch angeschaffter Speicher steht
 * im Reiter *Komponenten* bei Null, ohne ein Wort dazu. Die schärfste Probe ist
 * hier nicht „der Satz erscheint", sondern die **Absage**: bei `leer=false` darf
 * nichts stehen — sonst hinge der Hinweis über gefüllten Blöcken.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import type { HubLeerGrundResponse } from '../api/investitionen'

const getHubLeerGrund = vi.fn()

vi.mock('../api/investitionen', () => ({
  investitionenApi: { getHubLeerGrund: (...a: unknown[]) => getHubLeerGrund(...a) },
}))

import HubLeerGrund from './HubLeerGrund'

const ZU_JUNG: HubLeerGrundResponse = {
  leer: true,
  art: 'zu_jung',
  meldung: 'Für dieses Gerät gibt es noch keinen abgeschlossenen Monat.',
  details: 'Angeschafft am 01.08.2026. Der erste Monatsabschluss steht noch aus.',
  link: '/cockpit/monat',
  link_label: 'Zu Cockpit → Monat',
}

const ERFASSUNG_FEHLT: HubLeerGrundResponse = {
  leer: true,
  art: 'erfassung_fehlt',
  meldung: 'Für dieses Gerät sind noch keine Monatswerte erfasst.',
  details: 'Angeschafft am 01.07.2026 — seitdem liegt ein abgeschlossener Monat zurück.',
  link: '/einstellungen/daten',
  link_label: 'Zum Monatsabschluss',
}

function zeige() {
  return render(
    <MemoryRouter>
      <HubLeerGrund anlageId={1} investitionId={7} />
    </MemoryRouter>,
  )
}

describe('HubLeerGrund (N-247)', () => {
  beforeEach(() => {
    getHubLeerGrund.mockReset()
  })

  it('nennt den Grund beim frisch angeschafften Gerät', async () => {
    getHubLeerGrund.mockResolvedValue(ZU_JUNG)
    zeige()
    await waitFor(() =>
      expect(screen.getByText(/noch keinen abgeschlossenen Monat/)).toBeInTheDocument(),
    )
    expect(screen.getByText(/Monatsabschluss steht noch aus/)).toBeInTheDocument()
  })

  it('verweist beim zu jungen Gerät auf Cockpit, NICHT auf den Monatsabschluss', async () => {
    // Die P-6-Grenze: es gibt keinen Monat zum Abschließen, also darf der Knopf
    // auch nicht dorthin zeigen.
    getHubLeerGrund.mockResolvedValue(ZU_JUNG)
    zeige()
    await waitFor(() => expect(screen.getByRole('button')).toBeInTheDocument())
    expect(screen.getByRole('button')).toHaveTextContent('Cockpit')
    expect(screen.queryByText('Zum Monatsabschluss')).not.toBeInTheDocument()
  })

  it('führt zum Monatsabschluss, wo es dort etwas zu holen gibt', async () => {
    getHubLeerGrund.mockResolvedValue(ERFASSUNG_FEHLT)
    zeige()
    await waitFor(() => expect(screen.getByRole('button')).toBeInTheDocument())
    expect(screen.getByRole('button')).toHaveTextContent('Monatsabschluss')
  })

  it('schweigt, wenn der Server keine Leere sieht', async () => {
    getHubLeerGrund.mockResolvedValue({ leer: false } as HubLeerGrundResponse)
    zeige()
    await waitFor(() => expect(getHubLeerGrund).toHaveBeenCalled())
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
    expect(screen.queryByText(/Monatswerte/)).not.toBeInTheDocument()
  })
})
