/**
 * Cockpit/Monat — auf welchem Monat die Sicht aufgeht (N-99, Melder coolxmad
 * #353, ausdrücklich mit Bitte um Roadmap-Aufnahme).
 *
 * Gemeldete Lage: Cockpit → **Monat** öffnet auf dem neuesten Monat **mit
 * Zählerzeile**, den laufenden muss man selbst wählen — während Cockpit → Tag
 * („neuester Tag mit Daten") und Cockpit → Jahr längst auf dem Aktuellen
 * aufgehen.
 *
 * Gernots Auflage (03.08.) macht daraus zwei Lagen statt einer Regel:
 *
 *   offene Abschlüsse   → neuester Monat MIT Monatsdaten (unverändert). Die
 *                         Sicht führt dann zum offenen Abschluss hin.
 *   keine offenen       → neuester Monat, für den es überhaupt Werte gibt,
 *                         also in aller Regel der laufende.
 *
 * ⚠ `heute` wird überall hereingereicht statt gelesen — eine Probe, die die
 * echte Uhr nimmt, ist nicht hermetisch (N-167). Der Mount-Teil stellt die
 * Systemzeit deshalb ebenfalls.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { ThemeProvider } from '../context/ThemeContext'
import type { AggregierteMonatsdaten } from '../api/monatsdaten'
import type { AktuellerMonatResponse } from '../api/aktuellerMonat'

/** Systemzeit: 5. August 2026 — laufender Monat August, Vormonat Juli. */
const HEUTE = new Date(2026, 7, 5, 12, 0, 0)

const zeile = (jahr: number, monat: number, pv = 100): AggregierteMonatsdaten => ({
  id: jahr * 100 + monat,
  anlage_id: 1, jahr, monat,
  pv_erzeugung_kwh: pv, eigenverbrauch_kwh: pv / 2, direktverbrauch_kwh: pv / 4,
  einspeisung_kwh: pv / 2, netzbezug_kwh: 50, gesamtverbrauch_kwh: pv / 2 + 50,
  autarkie_prozent: 80, netzbezug_preis_cent: 40,
} as unknown as AggregierteMonatsdaten)

/** Strenge Liste (Monatsdaten) und volle Liste (inkl. laufendem Monat). */
const STRENG_ABGESCHLOSSEN = [zeile(2026, 7), zeile(2026, 6)]
const STRENG_OFFEN = [zeile(2026, 6)]
const VOLL = [zeile(2026, 8), zeile(2026, 7), zeile(2026, 6)]

/**
 * ⚠ Der Mock **beantwortet die gestellte Frage**, statt immer dieselbe Liste zu
 * liefern (F-4/F-6-Lehre). Genau daran hängt dieser Test: die Umstellung liest
 * eine ANDERE der drei Listen — ein Mock, der die Flags ignoriert, könnte den
 * Unterschied gar nicht zeigen und wäre grün-falsch.
 */
let strengeListe: AggregierteMonatsdaten[] = STRENG_ABGESCHLOSSEN
const listAggregiert = vi.fn(
  (_id: number, _jahr?: number, opts?: { inklOhneZaehlerzeile?: boolean; inklNurTageswerte?: boolean }) =>
    Promise.resolve(opts?.inklNurTageswerte ? VOLL : strengeListe),
)
const getTageWerte = vi.fn((_id: number, _von: string, _bis: string) => Promise.resolve([]))

vi.mock('../api/monatsdaten', () => ({
  monatsdatenApi: {
    listAggregiert: (...a: [number, number?, { inklOhneZaehlerzeile?: boolean; inklNurTageswerte?: boolean }?]) =>
      listAggregiert(...a),
  },
}))
vi.mock('../api/energie_profil', () => ({
  energieProfilApi: {
    getVerfuegbareMonate: vi.fn(() => Promise.resolve([] as Array<{ jahr: number; monat: number; tage: number }>)),
    getTageWerte: (...a: [number, string, string]) => getTageWerte(...a),
    getMonat: vi.fn(() => Promise.resolve(null)),
  },
}))
vi.mock('../api/aktuellerMonat', () => ({
  aktuellerMonatApi: {
    getData: (_id: number, jahr: number, monat: number) => Promise.resolve({
      anlage_id: 1, anlage_name: 'Demo', jahr, monat, monat_name: String(monat),
      aktualisiert_um: '', quellen: {}, feld_quellen: {},
      soll_pv_kwh: null, netzbezug_preis_cent: 40, einspeise_preis_cent: 8.2,
      pv_erzeugung_kwh: 100, einspeisung_kwh: 50, netzbezug_kwh: 50,
      eigenverbrauch_kwh: 50, direktverbrauch_kwh: 25,
      gesamtverbrauch_kwh: 100, autarkie_prozent: 80, eigenverbrauch_quote_prozent: 50,
      investitionen_financials: [], komponenten_geraete: {}, vorjahr: null,
    } as unknown as AktuellerMonatResponse),
  },
}))

import CockpitMonatV4, { hatOffeneAbschluesse, waehleDefaultMonat } from './CockpitMonatV4'
import { _clearSwrCacheForTests } from '../hooks/useApiData'

describe('waehleDefaultMonat — die Regel selbst', () => {
  it('ohne offene Abschlüsse fällt die Wahl auf den laufenden Monat', () => {
    expect(waehleDefaultMonat(STRENG_ABGESCHLOSSEN, [], VOLL, HEUTE)).toEqual({ jahr: 2026, monat: 8 })
  })

  it('mit offenem Abschluss bleibt es beim neuesten Monat MIT Monatsdaten', () => {
    // Juli fehlt in der strengen Liste ⇒ offener Abschluss ⇒ die Sicht führt
    // dorthin und nicht am offenen Monat vorbei in den August.
    expect(waehleDefaultMonat(STRENG_OFFEN, [], VOLL, HEUTE)).toEqual({ jahr: 2026, monat: 6 })
  })

  it('ein Monat NACH dem laufenden wird nie vorgewählt', () => {
    // Die volle Liste kennt auch Monate, deren einzige Spur eine Tagesebene-
    // Zeile ist — eine Snapshot-Streuzeile im September würde sonst eine leere
    // Sicht öffnen.
    const mitZukunft = [zeile(2026, 9), ...VOLL]
    expect(waehleDefaultMonat(STRENG_ABGESCHLOSSEN, [], mitZukunft, HEUTE)).toEqual({ jahr: 2026, monat: 8 })
  })

  it('ohne jede volle Zeile bleibt die strenge Wahl stehen', () => {
    expect(waehleDefaultMonat(STRENG_ABGESCHLOSSEN, [], [], HEUTE)).toEqual({ jahr: 2026, monat: 7 })
  })

  it('ganz ohne Monatsdaten greift die verfügbare Liste', () => {
    // Leere strenge Liste ⇒ `hatOffeneAbschluesse` ist true (nichts ist
    // abgeschlossen) ⇒ Fallback auf die Tagesebene-Monate.
    expect(waehleDefaultMonat([], [{ jahr: 2026, monat: 4 }], VOLL, HEUTE)).toEqual({ jahr: 2026, monat: 4 })
  })

  it('gar keine Daten ⇒ keine Wahl', () => {
    expect(waehleDefaultMonat([], [], [], HEUTE)).toBeNull()
  })
})

describe('hatOffeneAbschluesse — die Auflage', () => {
  it('der Vormonat reicht: ist er abgeschlossen, ist nichts offen', () => {
    expect(hatOffeneAbschluesse(STRENG_ABGESCHLOSSEN, HEUTE)).toBe(false)
  })

  it('fehlt der Vormonat, ist etwas offen', () => {
    expect(hatOffeneAbschluesse(STRENG_OFFEN, HEUTE)).toBe(true)
  })

  it('leere Liste gilt als offen', () => {
    expect(hatOffeneAbschluesse([], HEUTE)).toBe(true)
  })

  it('im Januar ist der Vormonat der Dezember des Vorjahres', () => {
    const januar = new Date(2027, 0, 9, 12, 0, 0)
    expect(hatOffeneAbschluesse([zeile(2026, 12)], januar)).toBe(false)
    expect(hatOffeneAbschluesse([zeile(2026, 11)], januar)).toBe(true)
  })

  it('eine Binnen-Lücke zählt als offen — nicht nur das Ende der Reihe', () => {
    // Genau der Fall, den `lib/monatsLuecken` von der naiven Regel „letzter
    // Monat + 1" unterscheidet: März fehlt, alles danach ist gepflegt. Die
    // Status-Fußzeile meldet ihn seit jeher; die Monats-Sicht rechnete bis
    // 06.08. daran vorbei — und mit N-99 hinge die Vorauswahl daran.
    const mitLuecke = [zeile(2026, 2), zeile(2026, 4), zeile(2026, 5), zeile(2026, 6), zeile(2026, 7)]
    expect(hatOffeneAbschluesse(mitLuecke, HEUTE)).toBe(true)
    expect(waehleDefaultMonat(mitLuecke, [], VOLL, HEUTE)).toEqual({ jahr: 2026, monat: 7 })
  })

  it('lückenlos ab der ersten Datenzeile ⇒ nichts offen', () => {
    // Gegenprobe zur Binnen-Lücke: der Bereich beginnt bei der ERSTEN
    // vorhandenen Zeile, nicht am Jahresanfang — sonst gälte jede Anlage mit
    // unterjähriger Inbetriebnahme dauerhaft als unvollständig.
    const abMaerz = [zeile(2026, 3), zeile(2026, 4), zeile(2026, 5), zeile(2026, 6), zeile(2026, 7)]
    expect(hatOffeneAbschluesse(abMaerz, HEUTE)).toBe(false)
  })
})

function renderView() {
  return render(
    <MemoryRouter initialEntries={['/v4/cockpit/monat']}>
      <ThemeProvider>
        <CockpitMonatV4 anlageId={1} />
      </ThemeProvider>
    </MemoryRouter>,
  )
}

describe('Cockpit/Monat — die Sicht geht auf dem richtigen Monat auf (#353)', () => {
  beforeEach(() => {
    localStorage.clear()
    // Der Sicht-Cache ist ein Modul-Singleton (R18-2) und überlebt sonst den
    // Test: die zweite Lage bekäme die Listen der ersten sofort serviert und
    // wäre grün-falsch.
    _clearSwrCacheForTests()
    strengeListe = STRENG_ABGESCHLOSSEN
    listAggregiert.mockClear()
    getTageWerte.mockClear()
    vi.useFakeTimers({ shouldAdvanceTime: true })
    vi.setSystemTime(HEUTE)
    vi.stubGlobal('matchMedia', vi.fn().mockReturnValue({
      matches: false, media: '', onchange: null,
      addEventListener: vi.fn(), removeEventListener: vi.fn(),
      addListener: vi.fn(), removeListener: vi.fn(), dispatchEvent: vi.fn(),
    }))
  })
  afterEach(() => { vi.useRealTimers() })

  it('lädt beim Aufschlagen den laufenden Monat, wenn nichts offen ist', async () => {
    renderView()
    await screen.findAllByTitle('Aug 2026 — laufender Monat')
    // Der Beleg ist die geladene Spanne, nicht die Rail: die Rail zeigt den
    // August auch dann, wenn die Sicht daneben den Juli darstellt — genau das
    // war der gemeldete Zustand. Der Fetch startet erst, wenn die Vorauswahl
    // steht (eine Runde nach der Rail) — deshalb waitFor.
    await waitFor(() => expect(getTageWerte).toHaveBeenCalledWith(1, '2026-08-01', '2026-08-31'))
    expect(getTageWerte).not.toHaveBeenCalledWith(1, '2026-07-01', '2026-07-31')
  })

  it('GEGENPROBE: bei offenem Abschluss bleibt die Sicht beim Monat mit Daten', async () => {
    strengeListe = STRENG_OFFEN
    renderView()
    await screen.findAllByTitle('Aug 2026 — laufender Monat')
    await waitFor(() => expect(getTageWerte).toHaveBeenCalledWith(1, '2026-06-01', '2026-06-30'))
    expect(getTageWerte).not.toHaveBeenCalledWith(1, '2026-08-01', '2026-08-31')
  })

  it('ein Drill-in mit ?jahr=&monat= schlägt die Vorauswahl weiterhin', async () => {
    render(
      <MemoryRouter initialEntries={['/v4/cockpit/monat?jahr=2026&monat=6']}>
        <ThemeProvider>
          <CockpitMonatV4 anlageId={1} />
        </ThemeProvider>
      </MemoryRouter>,
    )
    await screen.findAllByTitle('Aug 2026 — laufender Monat')
    await waitFor(() => expect(getTageWerte).toHaveBeenCalledWith(1, '2026-06-01', '2026-06-30'))
    expect(getTageWerte).not.toHaveBeenCalledWith(1, '2026-08-01', '2026-08-31')
  })
})
