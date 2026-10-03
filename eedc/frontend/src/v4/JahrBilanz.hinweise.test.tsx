/**
 * Cockpit → Jahr — die Hinweise der Jahresroute stehen über dem Vergleich (E11, ADR-002/P4).
 *
 * Entscheid Gernot 03.10.2026 (E11, N-584): ein abgeschlossener Monat ohne Monatsabschluss bleibt mit seinen Werten aus
 * Home Assistant in der Kopfzahl und wird in einer Hinweiszeile genannt. Der Satz kommt fertig aus dem Backend
 * (`services/jahres_aggregat.py::hinweis_ohne_abschluss`); die Sicht rendert ihn über `HerkunftZeile` — dieselbe Zeile wie
 * die PV-Teilsumme in Cockpit → Monat.
 *
 * Schwesterdateien: backend/tests/test_jahresroute_hinweise.py, JahrVergleichFenster.test.tsx.
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ThemeProvider } from '../context/ThemeContext'
import { JahrBilanz } from './JahrBilanz'
import { aktuellerMonat } from '../test/factories'
import { stubMatchMedia } from '../test/render'

const SATZ = '1 Monat ohne Monatsabschluss (Sep), Werte aus Home Assistant — Übersicht und Jahresbericht zählen ihn nicht mit.'

const rendere = (hinweise: string[]) => render(
  <ThemeProvider>
    <JahrBilanz
      d={aktuellerMonat(2025, 0, { monat_name: '2025', pv_erzeugung_kwh: 5000, hinweise })}
      vj={null} oj={null} ojCount={0}
    />
  </ThemeProvider>,
)

describe('JahrBilanz — Hinweise der Jahresroute (E11)', () => {
  beforeEach(() => { stubMatchMedia() })

  it('nennt den Monat ohne Monatsabschluss', () => {
    rendere([SATZ])
    expect(screen.getByText(SATZ, { exact: false })).toBeInTheDocument()
  })

  it('ohne Hinweis keine Zeile', () => {
    rendere([])
    expect(screen.queryByText(/ohne Monatsabschluss/)).toBeNull()
  })
})
