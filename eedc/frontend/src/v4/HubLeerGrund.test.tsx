/**
 * N-247: Der Komponenten-Hub nennt den Grund — und den Knopf nur, wo er wirkt.
 *
 * Gemeldet von CHI3fx117 (T89667 #152): ein frisch angeschaffter Speicher steht
 * im Reiter *Komponenten* bei Null, ohne ein Wort dazu. Die schärfste Probe ist
 * hier nicht „der Satz erscheint", sondern die **Absage**: bei `leer=false` darf
 * nichts stehen — sonst hinge der Hinweis über gefüllten Blöcken.
 *
 * ⚠ **N-270 (17.08.2026): diese Datei war der einzige Flake im Volllauf** — 1 von
 * 1173 rot, isoliert 3 × 4/4 grün, derselbe Code. Zwei Ursachen, beide behoben:
 *  1. `hooks/useApiData.ts` hält einen **Modul-Singleton**-SWR-Cache, der Tests
 *     überlebt. Alle Proben hier teilten den Key `v4-hub-leer:1:7`; die
 *     Absage-Probe mountete, rendert den `leer: true`-Stand der Probe davor beim
 *     ersten Paint und rannte gegen die Revalidierung. Der **Schwester-Test**
 *     `CockpitTagLeerGrund.test.tsx` ruft `_clearSwrCacheForTests()` an zwei
 *     Stellen, dieser nicht — eine Auslassung, kein Systemproblem.
 *  2. Der Riegel war zu schwach: `waitFor(mock aufgerufen)` sagt nichts über den
 *     **eingeschwungenen** Zustand. Die Absage wartet jetzt darauf, dass nichts
 *     mehr steht.
 *
 * Die Produkthälfte sitzt in `HubLeerGrund.tsx`: die Komponente hat **keinen**
 * `swrKey` mehr. Ein Test, der nur mit Cache-Clear grün ist, bewiese nichts über
 * das Produkt — deshalb beides.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { _clearSwrCacheForTests } from '../hooks/useApiData'
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
    // Der SWR-Cache ist ein Modul-Singleton und überlebt jeden Test (N-270).
    _clearSwrCacheForTests()
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
    // Auf den EINGESCHWUNGENEN Zustand warten, nicht nur auf den Aufruf: der
    // Mock ist aufgerufen, während React noch rendert (N-270).
    await waitFor(() => expect(getHubLeerGrund).toHaveBeenCalled())
    await waitFor(() => expect(screen.queryByRole('button')).not.toBeInTheDocument())
    expect(screen.queryByText(/Monatswerte/)).not.toBeInTheDocument()
  })

  it('bringt beim Remount keinen alten Grund mit — auch nicht für einen Paint', async () => {
    // Die Produkthälfte von N-270 als Zusicherung: erst `leer: true` (der
    // Anwender sieht den Hinweis), dann erfasst er Monatswerte, dann Remount
    // durch den Tab-Wechsel. Mit `swrKey` blitzte hier der alte Hinweis über den
    // nun gefüllten Blöcken auf — an Gernots Box 60–115 ms.
    getHubLeerGrund.mockResolvedValue(ERFASSUNG_FEHLT)
    const ersteSicht = zeige()
    await waitFor(() =>
      expect(screen.getByText(/noch keine Monatswerte erfasst/)).toBeInTheDocument(),
    )
    ersteSicht.unmount()

    getHubLeerGrund.mockResolvedValue({ leer: false } as HubLeerGrundResponse)
    zeige()
    // KEIN `waitFor` davor: die Zusicherung gilt für den ERSTEN Paint.
    expect(screen.queryByText(/noch keine Monatswerte erfasst/)).not.toBeInTheDocument()
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
    await waitFor(() => expect(screen.queryByRole('button')).not.toBeInTheDocument())
  })
})
