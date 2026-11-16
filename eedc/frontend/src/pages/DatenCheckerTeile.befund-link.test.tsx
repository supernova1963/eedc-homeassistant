/**
 * N-799 Sitzung 2 (E-11 c): der Ziel-Parameter `befund=<code>` — die Daten-Checker-Seite klappt die Kategorie des Befunds
 * auf und öffnet seinen Lösungsweg. Getestet mit einem bestehenden Code (`zaehler_versatz`); der Befund
 * `erfassung_stillstand` kommt in Sitzung 3 — bis dahin landet der Link auf der Seite, ohne etwas zu öffnen.
 *
 * Schwesterdateien: `DatenCheckerTeile.verdichtung.test.tsx`, `lib/zielPfad.test.ts`, `test/sprungziele.test.ts` (W-5).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

const check = vi.fn()
vi.mock('../api/datenChecker', () => ({ datenCheckerApi: { check: (...a: unknown[]) => check(...a) } }))
vi.mock('../hooks/useHelpKatalog', async (orig) => ({
  ...(await orig<typeof import('../hooks/useHelpKatalog')>()),
  useHelpKatalog: () => ({ docs: [], grouped: [], activeDoc: undefined, content: '', loading: false, error: null,
    rewriteLink: () => ({ type: 'external', target: '#' }) }),
}))

import { DatenCheckerVerwaltung } from './DatenCheckerTeile'
import { befundPfad } from '../lib/zielPfad'

const VERSATZ = {
  kategorie: 'zaehlerstaende', schwere: 'info', code: 'zaehler_versatz', knopf: 'Was gilt',
  meldung: 'Zählerstände – versetzter Abschnitt', details: 'Ein Abschnitt der Standreihe ist versetzt.',
}

function antwort() {
  return { anlage_id: 7, anlage_name: 'Haus', ergebnisse: [VERSATZ], zusammenfassung: { error: 0, warning: 0, info: 1, ok: 0 } }
}

function zeigen(pfad: string) {
  render(
    <MemoryRouter initialEntries={[pfad]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <DatenCheckerVerwaltung anlageId={7} />
    </MemoryRouter>,
  )
}

describe('N-799: Sprung auf einen Befund (`befund=`)', () => {
  beforeEach(() => {
    check.mockReset()
    check.mockResolvedValue(antwort())
    Element.prototype.scrollIntoView = vi.fn()
  })

  it('öffnet die Kategorie und den Lösungsweg des Befunds', async () => {
    zeigen(befundPfad('zaehler_versatz'))
    expect(await screen.findByTestId('loesungsweg-panel')).toBeTruthy()
    expect(screen.getAllByText('Zählerstände – versetzter Abschnitt').length).toBeGreaterThan(0)
  })

  it('ohne Parameter bleibt der Lösungsweg zu (INFO-Kategorie zugeklappt)', async () => {
    zeigen('/einstellungen/daten?block=datenchecker')
    await screen.findByTestId('checker-kopf')
    expect(screen.queryByTestId('loesungsweg-panel')).toBeNull()
  })

  it('ein Code, den es (noch) nicht gibt, öffnet nichts', async () => {
    zeigen(befundPfad('erfassung_stillstand'))
    await screen.findByTestId('checker-kopf')
    expect(screen.queryByTestId('loesungsweg-panel')).toBeNull()
  })
})
