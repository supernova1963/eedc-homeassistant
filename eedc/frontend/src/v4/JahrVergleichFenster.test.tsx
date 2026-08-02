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
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ThemeProvider } from '../context/ThemeContext'
import { jahrVergleichAus, mittelJahre, monatsFenster } from './JahrAggregat'
import { baueJahrKpis, JahrBilanz } from './JahrBilanz'
import type { AggregierteMonatsdaten } from '../api/monatsdaten'
import type { AktuellerMonatResponse } from '../api/aktuellerMonat'

/** Eine aggregierte Monatszeile mit gleichmäßigen Werten — Summen sind so
 *  ablesbar (n × 100 kWh PV), ohne dass der Test rechnet. */
const zeile = (jahr: number, monat: number): AggregierteMonatsdaten => ({
  jahr, monat,
  pv_erzeugung_kwh: 100, eigenverbrauch_kwh: 60, direktverbrauch_kwh: 40,
  einspeisung_kwh: 40, netzbezug_kwh: 30, gesamtverbrauch_kwh: 90,
} as unknown as AggregierteMonatsdaten)

const jahresZeilen = (jahr: number, monate: number[]) => monate.map((m) => zeile(jahr, m))
const bis = (n: number) => Array.from({ length: n }, (_, i) => i + 1)

describe('jahrVergleichAus — Beschneidung auf die Grundgesamtheit', () => {
  it('laufendes Jahr mit 7 Monaten ⇒ das Vorjahr summiert dieselben 7', () => {
    const rows = [...jahresZeilen(2026, bis(7)), ...jahresZeilen(2025, bis(12))]
    const vj = jahrVergleichAus(rows, 2025, bis(7))

    expect(vj.monate).toEqual(bis(7))
    expect(vj.pv).toBe(700)
    expect(vj.ev).toBe(420)
    // Die Quote wird aus den beschnittenen Summen NEU gebildet, nicht gemittelt.
    expect(vj.autarkie).toBeCloseTo((420 / 630) * 100, 6)

    // Gegenprobe: ohne Auswahl stünde weiterhin das volle Jahr da — das war N-37.
    expect(jahrVergleichAus(rows, 2025).pv).toBe(1200)
  })

  it('Lücke im angezeigten Jahr nimmt denselben Monat auch dem Vergleichsjahr', () => {
    // 2026 ohne März: die Regel ist „gleiche Monate", nicht „die ersten N".
    const g = [1, 2, 4, 5, 6, 7]
    const rows = [...jahresZeilen(2026, g), ...jahresZeilen(2025, bis(12))]
    const vj = jahrVergleichAus(rows, 2025, g)

    expect(vj.monate).toEqual(g)
    expect(vj.pv).toBe(600)
    // Kein volles Jahr ⇒ das Fenster steht dran, Lücke inklusive.
    expect(monatsFenster(vj)).toBe('Jan–Feb, Apr–Jul')
  })

  it('Lücke im VERGLEICHSjahr verkleinert das Fenster — und wird beschriftet', () => {
    // 2026 Jan–Jul, 2025 erst ab März in Betrieb: der Schnitt liegt in der
    // Überschneidung, nicht in der Grundgesamtheit.
    const rows = [...jahresZeilen(2026, bis(7)), ...jahresZeilen(2025, [3, 4, 5, 6, 7])]
    const vj = jahrVergleichAus(rows, 2025, bis(7))

    expect(vj.monate).toEqual([3, 4, 5, 6, 7])
    expect(vj.pv).toBe(500)
    expect(monatsFenster(vj)).toBe('Mär–Jul')
  })

  it('REGRESSION — abgeschlossenes Jahr: Werte identisch zu vorher, keine Beschriftung', () => {
    // Beide Jahre voll ⇒ die Beschneidung ist wirkungslos. Dieser Test sichert
    // ausdrücklich, dass die bestehende Anzeige sich NICHT ändert.
    const rows = [...jahresZeilen(2025, bis(12)), ...jahresZeilen(2024, bis(12))]
    const ohne = jahrVergleichAus(rows, 2024)
    const mit = jahrVergleichAus(rows, 2024, bis(12))

    expect(mit).toEqual(ohne)
    expect(mit.pv).toBe(1200)
    expect(monatsFenster(mit)).toBeNull()
  })

  it('kein überschneidender Monat ⇒ leeres Fenster und null — nicht 0', () => {
    // Anlage erst im angezeigten Jahr in Betrieb (bzw. Vorjahr nur im Spätherbst).
    const rows = [...jahresZeilen(2026, bis(7)), ...jahresZeilen(2025, [11, 12])]
    const vj = jahrVergleichAus(rows, 2025, bis(7))

    expect(vj.monate).toEqual([])
    expect(vj.pv).toBeNull()
    expect(vj.autarkie).toBeNull()
    expect(monatsFenster(vj)).toBeNull()   // nichts zu beschriften, es gibt keinen Vergleich
  })
})

describe('mittelJahre — Ø nur über die Jahre, die die Grundgesamtheit decken', () => {
  // Nachgestellt: Anlage Winterborn (Box 10.100.1.13) — 2023 ab Juni, 2026 bis Juni.
  const winterborn = [
    ...jahresZeilen(2026, bis(6)),
    ...jahresZeilen(2025, bis(12)),
    ...jahresZeilen(2024, bis(12)),
    ...jahresZeilen(2023, [6, 7, 8, 9, 10, 11, 12]),
  ]
  const oJahre = (rows: AggregierteMonatsdaten[], jahre: number[], g: number[]) =>
    mittelJahre(jahre.map((j) => jahrVergleichAus(rows, j, g)), g)

  it('teilweise Überschneidung zählt NICHT mit — sie wäre der Fund eine Ebene tiefer', () => {
    // 2023 deckt von Jan–Jun nur den Juni ab: eine Ein-Monats-Summe in einem
    // Sechs-Monats-Ø. Raus damit, und `count` sagt es.
    const oj = oJahre(winterborn, [2025, 2024, 2023], bis(6))

    expect(oj).not.toBeNull()
    expect(oj!.count).toBe(2)
    expect(oj!.pv).toBe(600)            // Ø aus 600 und 600 — nicht (600+600+100)/3
    expect(oj!.monate).toEqual(bis(6))
    expect(monatsFenster(oj)).toBe('Jan–Jun')
  })

  it('gar keine Überschneidung fällt genauso raus', () => {
    const rows = [...jahresZeilen(2026, bis(7)), ...jahresZeilen(2025, [11, 12])]
    expect(mittelJahre([jahrVergleichAus(rows, 2025, bis(7))], bis(7))).toBeNull()
  })

  it('REGRESSION — abgeschlossenes Jahr: volle Jahre, `count` und Werte wie bisher', () => {
    const oj = oJahre(winterborn, [2024, 2023], bis(12))
    // 2023 (Jun–Dez) deckt ein volles Kalenderjahr nicht ab → nur 2024 trägt.
    expect(oj!.count).toBe(1)
    expect(oj!.pv).toBe(1200)
    expect(monatsFenster(oj)).toBeNull()
  })
})

describe('monatsFenster — Beschriftung', () => {
  const mitMonaten = (monate: number[]) => ({ monate } as ReturnType<typeof jahrVergleichAus>)

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

const jahresAggregat = (): AktuellerMonatResponse => ({
  anlage_id: 1, anlage_name: 'Demo', jahr: 2026, monat: 0, monat_name: '2026',
  aktualisiert_um: '', quellen: {},
  pv_erzeugung_kwh: 4200, einspeisung_kwh: 1800, netzbezug_kwh: 900,
  eigenverbrauch_kwh: 2400, direktverbrauch_kwh: 1500, gesamtverbrauch_kwh: 3300,
  autarkie_prozent: 72.7, eigenverbrauch_quote_prozent: 57.1,
  soll_pv_kwh: null,
  investitionen_financials: [], komponenten_geraete: {}, feld_quellen: {},
  vorjahr: null,
} as unknown as AktuellerMonatResponse)

const vergleich2025 = { jahr: 2025, pv: 3890, ev: 2200, direkt: 1400, einsp: 1690, netz: 850, gesamt: 3050, autarkie: 72.1, monate: bis(7) }

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
    // ThemeProvider fragt `prefers-color-scheme` ab — jsdom kennt matchMedia nicht.
    vi.stubGlobal('matchMedia', vi.fn().mockReturnValue({
      matches: false, media: '', onchange: null,
      addEventListener: vi.fn(), removeEventListener: vi.fn(),
      addListener: vi.fn(), removeListener: vi.fn(), dispatchEvent: vi.fn(),
    }))
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
