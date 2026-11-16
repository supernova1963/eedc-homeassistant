/**
 * N-799 Sitzung 2 (E-11 c): der Ziel-Parameter `befund=<code>` — die Daten-Checker-Seite klappt die Kategorie des Befunds
 * auf und öffnet seinen Lösungsweg. Getestet mit einem bestehenden Code (`zaehler_versatz`) und mit dem Befund
 * `erfassung_stillstand` (Sitzung 3): er liefert ohne Fund eine OK-Zeile desselben Codes, damit der Link aus der Tagestabelle —
 * auch für einen Tag, der älter als die 90 Tage des Befunds ist — den Lösungsweg öffnet.
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

const STILLSTAND_OK = {
  kategorie: 'energieprofil_plausibilitaet', schwere: 'ok', code: 'erfassung_stillstand', knopf: null,
  meldung: 'Keine Stunden ohne Stundenwerte in den letzten 90 Tagen', details: 'Ein älterer Tag öffnet die Erklärung.',
}

function antwort() {
  return { anlage_id: 7, anlage_name: 'Haus', ergebnisse: [VERSATZ, STILLSTAND_OK],
    zusammenfassung: { error: 0, warning: 0, info: 1, ok: 1 } }
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

  it('N-799 S3: die OK-Zeile von erfassung_stillstand öffnet ihren Lösungsweg (Tag außerhalb der 90 Tage)', async () => {
    zeigen(befundPfad('erfassung_stillstand'))
    expect(await screen.findByTestId('loesungsweg-panel')).toBeTruthy()
    expect(screen.getAllByText('Keine Stunden ohne Stundenwerte in den letzten 90 Tagen').length).toBeGreaterThan(0)
  })

  it('N-799 S3 K7: der Knopf «Zum Daten-Checker» (befund=zaehler_versatz) öffnet den Lösungsweg über die OK-Zeile', async () => {
    check.mockResolvedValueOnce({
      anlage_id: 7, anlage_name: 'Haus', zusammenfassung: { error: 0, warning: 0, info: 0, ok: 1 },
      ergebnisse: [{ kategorie: 'zaehler_versatz', schwere: 'ok', code: 'zaehler_versatz', knopf: null,
        meldung: 'Kein versetzter Abschnitt in den gespeicherten Zählerständen', details: 'Gefunden wurde keiner.' }],
    })
    zeigen(befundPfad('zaehler_versatz'))
    expect(await screen.findByTestId('loesungsweg-panel')).toBeTruthy()
  })

  it('ein Code, den es nicht gibt, öffnet nichts', async () => {
    zeigen(befundPfad('gibt_es_nicht'))
    await screen.findByTestId('checker-kopf')
    expect(screen.queryByTestId('loesungsweg-panel')).toBeNull()
  })
})
