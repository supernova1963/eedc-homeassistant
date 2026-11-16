/**
 * N-799 Sitzung 2 (E-11 b/c): die drei stundengepaarten Tagesspalten eines Tages mit Zähler-Rechnung bzw. ohne
 * Stunden-Paarung — Zeichen `geschaetzt` an der vorhandenen Zahl, der Satz sichtbar unter der Tabelle mit dem Link auf den
 * Befund (`befund=erfassung_stillstand`), der Fuß-Hinweis der Summe. Der Client rechnet nichts: Wert, Kennzeichen und Satz
 * kommen aus `tage-werte`.
 *
 * Schwesterdateien: `WerteTabelle.test.tsx` (die Tabelle), `lib/werte/werte.test.ts` (Zeilen), `lib/zielPfad.test.ts`.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { WerteTabelle } from './WerteTabelle'
import { tagesZeile, fensterFussText, ohnePaarungFussText, LINK_DATEN_CHECKER } from '../../lib/werte'
import { tagWerte } from '../../test/factories'

const GRUND_F = 'Für die Stunden von 6 bis 18 Uhr gab es keine Stundenwerte — Überschuss, Defizit und Direktverbrauch sind dort aus den Zählerständen gerechnet.'
const GRUND_N = 'Für die Stunden von 5 bis 7 Uhr gab es keine Stundenwerte, und die Zähler haben ihre Mengen nicht für dieselben Stunden nachgetragen — Überschuss, Defizit und Direktverbrauch lassen sich für diesen Tag nicht bestimmen.'

const SPALTEN = ['direktverbrauch', 'ueberschuss_kwh', 'defizit_kwh']

function zeigen(rows = [
  tagesZeile(tagWerte('2026-11-11', { direktverbrauch: 4, ueberschuss_kwh: 3, defizit_kwh: 5 })),
  tagesZeile(tagWerte('2026-11-12', { direktverbrauch: 5.9, ueberschuss_kwh: 20.04, defizit_kwh: 29.46,
    stundenpaarung: 'fenster', stundenpaarung_grund: GRUND_F })),
  tagesZeile(tagWerte('2026-11-13', { direktverbrauch: null, ueberschuss_kwh: null, defizit_kwh: null,
    stundenpaarung: 'nicht_rechenbar', stundenpaarung_grund: GRUND_N })),
]) {
  return render(
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <WerteTabelle rows={rows} granularitaet="tag" scope="n799-s2" defaultSpalten={SPALTEN} />
    </MemoryRouter>,
  )
}

describe('N-799: Kennzeichen der drei Tagesspalten in der WerteTabelle', () => {
  // Feste Uhr (Wächter `feste-uhr-in-tests`): die Zeilen tragen ein festes Datum.
  beforeEach(() => { vi.setSystemTime(new Date(2026, 10, 16, 12)) })
  afterEach(() => { vi.useRealTimers() })

  it('Zahl mit Zeichen «geschätzt», Satz unter der Tabelle mit Link auf den Befund', () => {
    zeigen()
    const zelle = screen.getAllByTitle(GRUND_F)
    expect(zelle).toHaveLength(3)                                  // drei Spalten, je die Zahl + Zeichen
    expect(within(zelle[0]).getByRole('img', { name: 'geschätzt' })).toBeTruthy()
    const satz = screen.getByText((_t, el) => el?.tagName === 'LI' && (el.textContent ?? '').includes(GRUND_F))
    expect(satz.textContent).toContain('Do 12.11.')
    const link = within(satz).getByRole('link', { name: LINK_DATEN_CHECKER })
    expect(link.getAttribute('href')).toBe('/einstellungen/daten?block=datenchecker&befund=erfassung_stillstand')
  })

  it('«nicht rechenbar»: «—» ohne Zeichen, der Satz und der Link stehen trotzdem da', () => {
    zeigen()
    const leer = screen.getAllByTitle(GRUND_N)
    expect(leer).toHaveLength(3)
    expect(within(leer[0]).queryByRole('img')).toBeNull()
    const satz = screen.getByText((_t, el) => el?.tagName === 'LI' && (el.textContent ?? '').includes(GRUND_N))
    expect(within(satz).getByRole('link', { name: LINK_DATEN_CHECKER })).toBeTruthy()
  })

  it('Fuß-Hinweis: Tage mit Zähler-Rechnung in der Summe, Tage ohne Paarung nicht', () => {
    zeigen()
    expect(screen.getByText(fensterFussText(1))).toBeTruthy()
    expect(screen.getByText(ohnePaarungFussText(1))).toBeTruthy()
  })

  it('ohne Kennzeichen: kein Zeichen, kein Satz, kein Fuß-Hinweis (Sprengsatz der Bedingung)', () => {
    zeigen([tagesZeile(tagWerte('2026-11-11')), tagesZeile(tagWerte('2026-11-12'))])
    expect(screen.queryByRole('img', { name: 'geschätzt' })).toBeNull()
    expect(screen.queryByRole('link', { name: LINK_DATEN_CHECKER })).toBeNull()
    expect(screen.queryByText(/Zähler-Rechnung/)).toBeNull()
  })
})
