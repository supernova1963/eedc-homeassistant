/**
 * N-790 (ottokar, simon42 PN T95600) — «Aus Home Assistant neu übernehmen» im Daten-Checker.
 *
 * Ein Drift-Befund einer Anlage mit HA-Spiegel trägt `action_kind: 'spiegel_abgleich_tag'`. Der Knopf erscheint in
 * der Zeile, ruft `POST /energie-profil/{id}/spiegel-abgleich-tag` mit dem Tag, zeigt den Satz `meldung` des Backends
 * und lässt den Checker neu laufen — nach dem Muster von «Tag reparieren» (`reaggregate_day`).
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

const check = vi.fn()
const spiegelAbgleichTag = vi.fn()
const reaggregateTag = vi.fn()

vi.mock('../api/datenChecker', () => ({ datenCheckerApi: { check: (...a: unknown[]) => check(...a) } }))
vi.mock('../api/repair', () => ({ repairApi: { spiegelAbgleichTag: (...a: unknown[]) => spiegelAbgleichTag(...a) } }))
vi.mock('../api/energie_profil', () => ({ energieProfilApi: { reaggregateTag: (...a: unknown[]) => reaggregateTag(...a) } }))
vi.mock('../api/monatsdaten', () => ({ monatsdatenApi: {} }))

import { DatenCheckerVerwaltung } from './DatenCheckerTeile'
import { baueSpiegelAbgleichMeldung } from './datenCheckerMeldungen'

const MELDUNG = 'Statistik aus Home Assistant neu übernommen, 1 Kanal ab 02.11. 07:00 korrigiert; Tag 02.11.2026 neu aufgebaut.'

function antwort(ergebnisse: unknown[]) {
  return {
    anlage_id: 7, anlage_name: 'Haus', ergebnisse,
    zusammenfassung: { error: 0, warning: 0, info: ergebnisse.length, ok: 0 },
  }
}

const DRIFT = {
  kategorie: 'datenquelle_drift', schwere: 'info',
  meldung: 'Wärmepumpe: 1 Tag(e) weichen von HA-Statistics ab (größte Abweichung 2026-11-02: 123.909,6 → 13,7 kWh)',
  details: 'Für diese Komponente steht in eedc an 1 Tag(en) ein anderer Wert als in Home Assistant.',
  link: '/einstellungen/daten?block=energieprofil&karte=werkbank',
  action_kind: 'spiegel_abgleich_tag',
  action_params: { anlage_id: 7, datum: '2026-11-02' },
  action_label: 'Aus Home Assistant neu übernehmen',
}

function renderVerwaltung() {
  return render(
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <DatenCheckerVerwaltung anlageId={7} />
    </MemoryRouter>,
  )
}

describe('Daten-Checker: «Aus Home Assistant neu übernehmen» (N-790)', () => {
  beforeEach(() => {
    // Feste Uhr (Wächter `feste-uhr-in-tests`): die Befunde tragen ein festes Datum, «heute» ist der Tag der Meldung.
    vi.setSystemTime(new Date(2026, 10, 10, 12))
    check.mockReset()
    spiegelAbgleichTag.mockReset()
    reaggregateTag.mockReset()
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('zeigt den Knopf, ruft die Route mit dem Tag, zeigt den Satz und prüft neu', async () => {
    check.mockResolvedValueOnce(antwort([DRIFT])).mockResolvedValue(antwort([]))
    spiegelAbgleichTag.mockResolvedValue({
      anlage_id: 7, datum: '2026-11-02', meldung: MELDUNG,
      abgleich: { fehler: 0 }, reaggregation: { status: 'ok', datum: '2026-11-02' },
    })
    renderVerwaltung()
    // Ein INFO-Befund klappt seine Kategorie nicht von selbst auf.
    fireEvent.click(await screen.findByText('Datenquelle – Drift zu HA-Statistics'))
    const knopf = await screen.findByRole('button', { name: /Aus Home Assistant neu übernehmen/ })
    expect(screen.queryByRole('button', { name: /Beheben/ })).toBeNull()

    fireEvent.click(knopf)
    await waitFor(() => expect(spiegelAbgleichTag).toHaveBeenCalledWith(7, '2026-11-02'))
    expect(reaggregateTag).not.toHaveBeenCalled()
    expect(await screen.findByText(MELDUNG)).toBeTruthy()
    await waitFor(() => expect(check).toHaveBeenCalledTimes(2))
  })

  it('zeigt den Fehler der Route (503: Home Assistant nicht erreichbar)', async () => {
    check.mockResolvedValue(antwort([DRIFT]))
    spiegelAbgleichTag.mockRejectedValue(new Error('Home Assistant ist nicht erreichbar'))
    renderVerwaltung()
    fireEvent.click(await screen.findByText('Datenquelle – Drift zu HA-Statistics'))
    fireEvent.click(await screen.findByRole('button', { name: /Aus Home Assistant neu übernehmen/ }))
    expect(await screen.findByText('Home Assistant ist nicht erreichbar')).toBeTruthy()
  })
})

describe('baueSpiegelAbgleichMeldung', () => {
  const basis = { anlage_id: 7, datum: '2026-11-02', meldung: MELDUNG }

  it('ist «ok», wenn der Abgleich vollständig lief und der Tag neu aufgebaut ist', () => {
    const m = baueSpiegelAbgleichMeldung({
      ...basis, abgleich: { fehler: 0 } as never, reaggregation: { status: 'ok', datum: '2026-11-02' },
    })
    expect(m).toEqual({ art: 'ok', text: MELDUNG })
  })

  it('ist «hinweis», wenn der Tag nicht neu aufgebaut werden konnte oder ein Kanal ungeprüft blieb', () => {
    expect(baueSpiegelAbgleichMeldung({
      ...basis, abgleich: { fehler: 0 } as never, reaggregation: { status: 'fehler', datum: '2026-11-02', fehler: 'x' },
    }).art).toBe('hinweis')
    expect(baueSpiegelAbgleichMeldung({
      ...basis, abgleich: { fehler: 1 } as never, reaggregation: { status: 'ok', datum: '2026-11-02' },
    }).art).toBe('hinweis')
  })
})
