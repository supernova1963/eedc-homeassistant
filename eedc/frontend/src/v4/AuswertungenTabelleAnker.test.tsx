/**
 * N-368 — Der Tages-Block der Werte-Werkbank hat seinen EIGENEN Anker.
 *
 * Gemeldet von OB73-gif (GitHub #395, 01./02.09.2026): Bei offenem August-Abschluss
 * stand die Tagesansicht auf einem alten Monat, obwohl September gemessen war, und
 * der Chip „Aktueller Monat" sprang nicht auf den laufenden.
 *
 * Die Regel hat ZWEI Haelften, und jede wird hier einzeln festgehalten:
 *   1. Der Zeitraum kommt aus der TAGESSPUR (`getVerfuegbareMonate`), nicht aus den
 *      Monaten mit Abschluss — mit Deckel auf den laufenden Monat und mit Rueckfall
 *      auf den Abschluss-Anker, wenn es gar keine Tagesspur gibt (Handpflege).
 *   2. Der offene Abschluss wird BENANNT statt angedeutet (Gernot 2026-09-02):
 *      der richtige Zeitraum darf das Versaeumnis nicht verschlucken.
 *
 * ⚠ Die Uhr wird gestellt (`vi.setSystemTime`), nicht gelesen — eine Probe, die die
 * echte Uhr nimmt, ist nicht hermetisch (N-167).
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen } from '@testing-library/react'

// Monate MIT Abschluss — der Melderfall: letzter Abschluss Juli, August offen.
const monatsRows = { current: [{ jahr: 2026, monat: 7, erzeugung: 1960, eigenverbrauch: 634, einspeisung: 1318, netzbezug: 9, gesamtverbrauch: 644, autarkie: 98.5, evQuote: 31.9 }] }
// Monate MIT TAGESSPUR — bei ihm laeuft die Aggregation durch bis September.
const tagMonate: { current: Array<{ jahr: number; monat: number; tage: number }> | null } = { current: [] }

vi.mock('../hooks', () => ({
  useSchmaleAchse: () => false,
  useInvestitionen: () => ({ investitionen: [], loading: false, error: null }),
  useSelectedAnlage: () => ({
    anlagen: [{ id: 1, anlagenname: 'Test' }], selectedAnlageId: 1,
    selectedAnlage: { id: 1, anlagenname: 'Test' }, loading: false,
  }),
  useApiData: () => ({ data: tagMonate.current, loading: false, error: null }),
}))
vi.mock('./useWerteZeitreihe', () => ({
  useWerteZeitreihe: () => ({
    rows: monatsRows.current,
    jahre: [...new Set(monatsRows.current.map((r) => r.jahr))], loading: false, error: null,
  }),
}))
// Der Tages-Block ist `defaultOpen: false` — fuer den Zeitraum reicht die Block-Summary,
// die von/bis traegt. Die Tageswerte selbst sind hier nicht der Gegenstand.
vi.mock('./useTagesWerte', () => ({
  useTagesWerte: () => ({ rows: [], vorjahrRows: null, loading: false, error: null }),
  minusEinJahr: (s: string) => s,
}))

import AuswertungenTabelleV4 from './AuswertungenTabelleV4'
import type { AuswertungBasis } from './useAuswertungBasis'

const basisMock = {
  daten: [], gefiltert: [], strompreis: null, alleTarife: [], jahr: 'alle',
  setJahr: () => {}, jahre: [2026], zeitraumLabel: '2026',
  loading: false, error: null, refresh: async () => {},
} as unknown as AuswertungBasis

/** Die Summary des Tages-Blocks — sie traegt „von – bis · Vgl. …". */
function tagesZeitraum(): string {
  const treffer = screen.getAllByText(/\d{4}-\d{2}-\d{2} – \d{4}-\d{2}-\d{2} · Vgl\./)
  return treffer[0].textContent ?? ''
}

describe('N-368 — Tages-Anker der Werte-Werkbank', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date(2026, 8, 2))   // 2. September 2026
    monatsRows.current = [{ jahr: 2026, monat: 7, erzeugung: 1960, eigenverbrauch: 634, einspeisung: 1318, netzbezug: 9, gesamtverbrauch: 644, autarkie: 98.5, evQuote: 31.9 }]
    tagMonate.current = []
  })
  afterEach(() => { vi.useRealTimers() })

  it('Melderfall: Abschluss bis Juli, Tagesspur bis September ⇒ Tagesansicht steht auf September', () => {
    tagMonate.current = [{ jahr: 2026, monat: 9, tage: 2 }, { jahr: 2026, monat: 8, tage: 31 }, { jahr: 2026, monat: 7, tage: 31 }]
    render(<AuswertungenTabelleV4 basis={basisMock} />)
    expect(tagesZeitraum()).toContain('2026-09-01')
    // Der MONATS-Block bleibt am Abschluss-Anker — das ist dort richtig (N-99).
    expect(screen.getAllByText(/2026-01 – 2026-12/).length).toBeGreaterThan(0)
  })

  it('ohne JEDEN Abschluss laedt der Tages-Block trotzdem — frische Installation', () => {
    monatsRows.current = []            // keine einzige Abschluss-Zeile
    tagMonate.current = [{ jahr: 2026, monat: 9, tage: 2 }, { jahr: 2026, monat: 8, tage: 20 }]
    render(<AuswertungenTabelleV4 basis={basisMock} />)
    // Vorher: `anker` null ⇒ `tagVon` leer ⇒ gar kein Zeitraum, `enabled: false`.
    expect(tagesZeitraum()).toContain('2026-09-01')
  })

  it('ein Monat NACH dem laufenden wird nicht vorgewaehlt', () => {
    tagMonate.current = [{ jahr: 2026, monat: 11, tage: 1 }, { jahr: 2026, monat: 9, tage: 2 }]
    render(<AuswertungenTabelleV4 basis={basisMock} />)
    expect(tagesZeitraum()).toContain('2026-09-01')
    expect(tagesZeitraum()).not.toContain('2026-11')
  })

  it('GEGENPROBE — ohne Tagesspur bleibt es beim Abschluss-Anker (reine Handpflege)', () => {
    tagMonate.current = []
    render(<AuswertungenTabelleV4 basis={basisMock} />)
    expect(tagesZeitraum()).toContain('2026-07-01')
  })

  it('der offene Abschluss wird benannt — mit Monat und Weg dorthin', () => {
    tagMonate.current = [{ jahr: 2026, monat: 9, tage: 2 }]
    render(<AuswertungenTabelleV4 basis={basisMock} />)
    expect(screen.getByText(/August/)).toBeInTheDocument()
    expect(screen.getByText('Abschluss starten')).toBeInTheDocument()
  })

  it('der LAUFENDE Monat gilt nicht als offener Abschluss', () => {
    // Abschluss bis August ⇒ nichts offen; September laeuft noch.
    monatsRows.current = [{ jahr: 2026, monat: 8, erzeugung: 1960, eigenverbrauch: 634, einspeisung: 1318, netzbezug: 9, gesamtverbrauch: 644, autarkie: 98.5, evQuote: 31.9 }]
    tagMonate.current = [{ jahr: 2026, monat: 9, tage: 2 }]
    render(<AuswertungenTabelleV4 basis={basisMock} />)
    expect(screen.queryByText('Abschluss starten')).not.toBeInTheDocument()
  })
})
