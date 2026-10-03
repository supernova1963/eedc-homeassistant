/**
 * Cockpit/Jahr — Grundgesamtheit des Vorjahr-/Ø-Jahr-Vergleichs (Fund N-37).
 *
 * Bis v4.0.6 summierte `jahrVergleichAus` **alle** Zeilen eines Jahres: im August
 * standen damit sieben gelaufene Monate von 2026 gegen zwölf volle von 2025.
 * Beschnitten wird jetzt auf die Monate, für die das ANGEZEIGTE Jahr Zeilen hat —
 * und das Fenster wird ausgewiesen (ADR-002/P4 in klein).
 *
 * Abgrenzung zum Tabellenfuß (`lib/werte/vergleich.ts`): der verwirft den
 * Vergleich in derselben Lage ganz, weil ein Fuß die Summe der Spalte über ihm
 * sein MUSS. Eine Vergleichsspalte hat diese Bindung nicht — sie darf beschneiden,
 * solange sie es sagt.
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ThemeProvider } from '../context/ThemeContext'
import { monatsFenster } from '../lib/monatsFenster'
import type { JahrVergleich } from '../api/cockpit'
import { baueJahrKpis, JahrBilanz } from './JahrBilanz'
import { aktuellerMonat } from '../test/factories'
import { stubMatchMedia } from '../test/render'

const bis = (n: number) => Array.from({ length: n }, (_, i) => i + 1)

// `jahrVergleichAus` / `mittelJahre` (Beschneidung auf die Grundgesamtheit, Ø nur über deckende Jahre) sind seit
// 03.10.2026 Backend-Layer (`core/berechnungen/ergebnis.py`): ihre Proben stehen mit denselben Zahlen in
// `backend/tests/test_ergebnis_jahr_portiert.py::test_vergleich_*` / `test_mittel_*`. Hier bleiben Beschriftung
// und Anzeige.

describe('monatsFenster — Beschriftung', () => {
  const mitMonaten = (monate: number[]) => ({ monate } as JahrVergleich)

  it('fasst zusammenhängende Läufe zusammen', () => {
    expect(monatsFenster(mitMonaten(bis(7)))).toBe('Jan–Jul')
    expect(monatsFenster(mitMonaten([1, 2, 4, 5, 6, 7]))).toBe('Jan–Feb, Apr–Jul')
    expect(monatsFenster(mitMonaten([3]))).toBe('Mär')
    expect(monatsFenster(mitMonaten([1, 3, 5]))).toBe('Jan, Mär, Mai')
  })

  it('volles Jahr braucht keine Erklärung', () => {
    expect(monatsFenster(mitMonaten(bis(12)))).toBeNull()
  })

  it('null ohne Vergleich', () => {
    expect(monatsFenster(null)).toBeNull()
  })
})

// ─── Anzeige: das Fenster steht dran ─────────────────────────────────────────

// `monat: 0` + der Name des Jahres: so kommt das Jahres-Aggregat aus der Route.
const jahresAggregat = () =>
  aktuellerMonat(2026, 0, {
    monat_name: '2026',
    pv_erzeugung_kwh: 4200, einspeisung_kwh: 1800, netzbezug_kwh: 900,
    eigenverbrauch_kwh: 2400, direktverbrauch_kwh: 1500, gesamtverbrauch_kwh: 3300,
    autarkie_prozent: 72.7, eigenverbrauch_quote_prozent: 57.1,
  })

const vergleich2025: JahrVergleich = { jahr: 2025, pv: 3890, ev: 2200, direkt: 1400, einsp: 1690, netz: 850, gesamt: 3050, autarkie: 72.1, monate: bis(7) }

describe('baueJahrKpis — Kachel nennt das Fenster', () => {
  it('mit Fenster: „VJ (Jan–Jul): …" an PV, Autarkie, EV, Einspeisung, Netzbezug', () => {
    const kpis = baueJahrKpis(jahresAggregat(), vergleich2025, 'Jan–Jul')
    const sub = (titel: string) => kpis.find((k) => k.title === titel)?.subtitle

    expect(sub('PV-Erzeugung')).toBe('VJ (Jan–Jul): 3.890 kWh')
    expect(sub('Autarkie')).toBe('VJ (Jan–Jul): 72 %')
    expect(sub('Eigenverbrauch')).toContain('VJ (Jan–Jul): 2.200 kWh')
    expect(sub('Einspeisung')).toBe('VJ (Jan–Jul): 1.690 kWh')
    expect(sub('Netzbezug')).toBe('VJ (Jan–Jul): 850 kWh')
  })

  it('REGRESSION — ohne Fenster bleibt es beim bisherigen „VJ: …"', () => {
    const kpis = baueJahrKpis(jahresAggregat(), { ...vergleich2025, monate: bis(12) }, null)
    expect(kpis.find((k) => k.title === 'PV-Erzeugung')?.subtitle).toBe('VJ: 3.890 kWh')
    expect(kpis.find((k) => k.title === 'Autarkie')?.subtitle).toBe('VJ: 72 %')
  })
})

describe('JahrBilanz — Spaltenkopf und Fußnote', () => {
  beforeEach(() => {
    stubMatchMedia()
  })

  const rendere = (vjFenster: string | null, ojFenster: string | null) => render(
    <ThemeProvider>
      <JahrBilanz
        d={jahresAggregat()}
        vj={vergleich2025}
        oj={{ ...vergleich2025, jahr: 0 }}
        ojCount={2}
        vjFenster={vjFenster}
        ojFenster={ojFenster}
      />
    </ThemeProvider>,
  )

  it('beschnitten: Fenster im Kopf beider Vergleichsspalten + eine Fußnote', () => {
    rendere('Jan–Jul', 'Jan–Jul')
    // Kopfzeile: „Vorjahr" / „Ø Jahre" jeweils mit Zweitzeile.
    expect(screen.getAllByText('Jan–Jul')).toHaveLength(2)
    // Zusammengefasst, weil beide Spalten dasselbe Fenster tragen.
    expect(screen.getByText(/Vergleich beschnitten auf die gemeinsamen Monate: Jan–Jul/))
      .toBeInTheDocument()
    expect(screen.getByText(/Ø aus 2 Jahren/)).toBeInTheDocument()
  })

  it('unterschiedliche Fenster werden je Spalte benannt', () => {
    rendere('Mär–Jul', 'Jan–Jul')
    expect(screen.getByText(/Vorjahr Mär–Jul · Ø Jahre Jan–Jul/)).toBeInTheDocument()
  })

  it('REGRESSION — nicht beschnitten: keine Fenster-Angabe, nur der Ø-Hinweis', () => {
    rendere(null, null)
    expect(screen.queryByText(/beschnitten/)).not.toBeInTheDocument()
    expect(screen.getByText('Ø aus 2 Jahren')).toBeInTheDocument()
    expect(screen.getByText('Vorjahr')).toBeInTheDocument()
  })
})
