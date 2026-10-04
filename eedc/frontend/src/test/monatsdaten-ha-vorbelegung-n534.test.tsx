/**
 * N-534 (Frank85, T89667 #349) + N-622: „Aus HA laden" belegt das Monatsdaten-Formular vor.
 *
 * Das Backend liefert die Basisfelder unter ihrem Datenbanknamen (`einspeisung_kwh`);
 * das Formular suchte bis zum 19.09.2026 die Mapping-Kurzform (`einspeisung`) und fand
 * nichts — seit v2.5.3 kam die Vorbelegung bei jedem Anwender leer an.
 *
 * ⚠ N-622 (04.10.2026): Diese Probe fütterte bis dahin `{ feld: 'pv_erzeugung_kwh' }` —
 * einen Namen, den das Backend nie sendete (es lieferte `pv_gesamt`). Sie war grün, die
 * Vorbelegung des PV-Gesamtzählers wirkte produktiv nie. Seitdem kommt die Eingabe aus
 * der Fixture, die `test_n622_ha_monatswerte_pv_gesamtzaehler.py` bitgleich gegen die
 * Route `/ha-statistics/monatswerte` hält, und läuft durch denselben Client
 * (`haStatisticsApi.getMonatswerte` → `convertBackendToMonatswerte`) wie in der App.
 *
 * Was hier festgehalten wird: der PV-Gesamtzähler steht in einer eigenen, sichtbaren
 * Zeile — auch neben „PV-Erzeugung (berechnet)" —, gesendet wird nur, was darin steht,
 * und ohne HA bleibt das Formular, wie es war.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import type { Investition } from '../types'
import type { MonatsdatenSubmitData } from '../components/forms/MonatsdatenForm'
import fixture from './ha-monatswerte-n622.fixture.json'

const zustand: {
  invs: Investition[]
  rows: Array<{ investition_id: number; verbrauch_daten: Record<string, number> }>
} = { invs: [], rows: [] }

vi.mock('../hooks', () => ({
  useInvestitionen: () => ({ investitionen: zustand.invs, loading: false }),
  useAktuellerStrompreis: () => ({ strompreis: null }),
}))

vi.mock('../api', () => ({
  wetterApi: { getMonatsdaten: () => Promise.reject(new Error('kein Wetter im Test')) },
  monatsabschlussApi: { getStatus: () => Promise.reject(new Error('kein Status im Test')) },
  investitionenApi: {
    getMonatsdatenByMonth: () => Promise.resolve(zustand.rows.map((r, i) => ({
      id: i + 1, jahr: 2025, monat: 5, einsparung_monat_euro: null, co2_einsparung_kg: null, ...r,
    }))),
  },
}))

// Die Route antwortet mit der Fixture — derselbe Client-Weg wie „Aus HA laden".
vi.mock('../api/client', () => ({
  api: { get: () => Promise.resolve(structuredClone(fixture)) },
}))

const MonatsdatenForm = (await import('../components/forms/MonatsdatenForm')).default
const { haStatisticsApi } = await import('../api/haStatistics')

const ZEILE = 'PV-Gesamtzähler aus Home Assistant'
// N-622 Nacharbeit: derselbe Platz für einen gespeicherten Anlagenwert ohne HA-Vorbelegung.
const ZEILE_NEUTRAL = 'PV-Gesamtwert der Anlage'
const MODUL_ZEILEN = [
  { investition_id: 1, verbrauch_daten: { pv_erzeugung_kwh: 550 } },
  { investition_id: 2, verbrauch_daten: { pv_erzeugung_kwh: 380 } },
]
const monat = (pv?: number) => ({ id: 9, anlage_id: 1, jahr: 2025, monat: 5, einspeisung_kwh: 400, netzbezug_kwh: 200, ...(pv !== undefined ? { pv_erzeugung_kwh: pv } : {}) })
const feld = (name: string) => document.querySelector(`input[name="${name}"]`) as HTMLInputElement | null
const pvFelder = () => document.querySelectorAll('input[name="pv_erzeugung_kwh"]')

const inv = (id: number, typ: Investition['typ'], bezeichnung: string, kwp: number): Investition => ({
  id, anlage_id: 1, typ, bezeichnung, anschaffungsdatum: '2024-01-01', aktiv: true, parameter: {}, leistung_kwp: kwp,
})
// Dieselben Geräte wie die Fixture (Form 1: Süd und West gemessen, Balkonkraftwerk ohne Zähler).
const SUED_WEST_BKW = [inv(1, 'pv-module', 'Süd', 6), inv(2, 'pv-module', 'West', 4), inv(3, 'balkonkraftwerk', 'Balkon', 0.8)]

async function oeffne(opt: { ha: boolean; monatsdaten?: Record<string, unknown> | null }) {
  const onSubmit = vi.fn((_d: MonatsdatenSubmitData) => Promise.resolve())
  const haVorausfuellung = opt.ha ? await haStatisticsApi.getMonatswerte(1, 2025, 5) : null
  render(
    <MonatsdatenForm
      anlageId={1}
      onSubmit={onSubmit}
      onCancel={() => {}}
      monatsdaten={(opt.monatsdaten ?? null) as never}
      haVorausfuellung={haVorausfuellung}
    />,
  )
  await waitFor(() => expect(feld('einspeisung_kwh')).not.toBeNull())
  return onSubmit
}

async function speichern(onSubmit: ReturnType<typeof vi.fn>): Promise<MonatsdatenSubmitData> {
  fireEvent.submit(document.querySelector('form')!)
  await waitFor(() => expect(onSubmit).toHaveBeenCalled())
  return onSubmit.mock.calls[0][0] as MonatsdatenSubmitData
}

beforeEach(() => {
  zustand.invs = []
  zustand.rows = []
})

describe('Formular-Vorbelegung aus HA (N-534, N-622)', () => {
  it('die Fixture ist die Antwort, die das Backend sendet: der Gesamtzähler heißt pv_erzeugung_kwh', () => {
    expect(fixture.basis.map((b) => b.feld)).toEqual(['einspeisung_kwh', 'netzbezug_kwh', 'pv_erzeugung_kwh'])
  })

  it('ohne Geräte: Einspeisung, Netzbezug und der PV-Gesamtzähler stehen vorbelegt in ihren Zeilen', async () => {
    await oeffne({ ha: true })
    expect(feld('einspeisung_kwh')!.value).toBe('400')
    expect(feld('netzbezug_kwh')!.value).toBe('200')
    expect(pvFelder()).toHaveLength(1)
    expect((screen.getByLabelText(ZEILE) as HTMLInputElement).value).toBe('1000')
  })

  it('mit Modulwerten: die Zeile steht neben „PV-Erzeugung (berechnet)", beide Zahlen lesbar', async () => {
    zustand.invs = SUED_WEST_BKW
    await oeffne({ ha: true })
    await waitFor(() => expect(screen.getByText('PV-Erzeugung (berechnet)')).toBeTruthy())
    expect(document.body.textContent).toContain('930,0 kWh')
    expect(pvFelder()).toHaveLength(1)
    expect((screen.getByLabelText(ZEILE) as HTMLInputElement).value).toBe('1000')
    expect(document.body.textContent).toContain('Gesamtzähler der Anlage: 1.000,0 kWh')
    expect(document.body.textContent).toContain('der Gesamtwert füllt nur, was sie nicht erklären')
    expect(document.body.textContent).toContain('Ist das Feld beim Speichern leer, hat der Monat keinen Gesamtwert.')
  })

  it('gespeichert wird, was in der Zeile steht — auch ein geänderter Wert', async () => {
    zustand.invs = SUED_WEST_BKW
    const onSubmit = await oeffne({ ha: true })
    fireEvent.change(await waitFor(() => screen.getByLabelText(ZEILE)), { target: { value: '990' } })
    expect((await speichern(onSubmit)).pv_erzeugung_kwh).toBe(990)
  })


  it('eine geleerte Zeile speichert keinen Anlagenwert', async () => {
    zustand.invs = SUED_WEST_BKW
    const onSubmit = await oeffne({ ha: true })
    fireEvent.change(await waitFor(() => screen.getByLabelText(ZEILE)), { target: { value: '' } })
    expect((await speichern(onSubmit)).pv_erzeugung_kwh).toBeUndefined()
  })

  it('Bearbeiten mit gespeichertem Anlagenwert und HA: die Zeile nennt den gespeicherten, Speichern nimmt den HA-Wert', async () => {
    zustand.invs = SUED_WEST_BKW
    zustand.rows = MODUL_ZEILEN
    const onSubmit = await oeffne({ ha: true, monatsdaten: monat(990) })
    expect((screen.getByLabelText(ZEILE) as HTMLInputElement).value).toBe('1000')
    expect(document.body.textContent).toContain('Bisher gespeichert: 990,0 kWh.')
    // „Mit HA-Werten fortfahren" + Speichern trägt den Zähler in einen bestehenden Monat nach.
    expect((await speichern(onSubmit)).pv_erzeugung_kwh).toBe(1000)
  })

  it('Bearbeiten mit gespeichertem Anlagenwert und HA: geleerte Zeile entfernt ihn (null)', async () => {
    zustand.invs = SUED_WEST_BKW
    zustand.rows = MODUL_ZEILEN
    const onSubmit = await oeffne({ ha: true, monatsdaten: monat(990) })
    fireEvent.change(screen.getByLabelText(ZEILE), { target: { value: '' } })
    expect((await speichern(onSubmit)).pv_erzeugung_kwh).toBeNull()
  })

  it('ohne HA: ein gespeicherter Anlagenwert steht neutral beschriftet in der Zeile und geht unverändert mit', async () => {
    zustand.invs = SUED_WEST_BKW
    zustand.rows = MODUL_ZEILEN
    const onSubmit = await oeffne({ ha: false, monatsdaten: monat(1000) })
    await waitFor(() => expect(document.body.textContent).toContain('930,0 kWh'))
    expect(screen.queryByLabelText(ZEILE)).toBeNull()
    expect((screen.getByLabelText(ZEILE_NEUTRAL) as HTMLInputElement).value).toBe('1000')
    expect(pvFelder()).toHaveLength(1)
    // Abweichungssatz: „Gesamtwert", nicht „Gesamtzähler" — der Wert kommt nicht aus HA.
    expect(document.body.textContent).toContain('Gesamtwert der Anlage: 1.000,0 kWh')
    expect(document.body.textContent).not.toContain('Gesamtzähler der Anlage')
    expect(document.body.textContent).not.toContain('Bisher gespeichert')
    expect((await speichern(onSubmit)).pv_erzeugung_kwh).toBe(1000)
  })

  it('ohne HA: den gespeicherten Anlagenwert ändern', async () => {
    zustand.invs = SUED_WEST_BKW
    zustand.rows = MODUL_ZEILEN
    const onSubmit = await oeffne({ ha: false, monatsdaten: monat(1000) })
    fireEvent.change(await waitFor(() => screen.getByLabelText(ZEILE_NEUTRAL)), { target: { value: '980' } })
    expect((await speichern(onSubmit)).pv_erzeugung_kwh).toBe(980)
  })

  it('ohne HA: den gespeicherten Anlagenwert entfernen — geleerte Zeile sendet null', async () => {
    zustand.invs = SUED_WEST_BKW
    zustand.rows = MODUL_ZEILEN
    const onSubmit = await oeffne({ ha: false, monatsdaten: monat(1000) })
    fireEvent.change(await waitFor(() => screen.getByLabelText(ZEILE_NEUTRAL)), { target: { value: '' } })
    expect((await speichern(onSubmit)).pv_erzeugung_kwh).toBeNull()
  })

  it('Gegenprobe ohne HA und ohne gespeicherten Wert, mit Modulwerten: Formular und Nutzlast wie bisher', async () => {
    zustand.invs = SUED_WEST_BKW
    zustand.rows = MODUL_ZEILEN
    const onSubmit = await oeffne({ ha: false, monatsdaten: monat() })
    await waitFor(() => expect(document.body.textContent).toContain('930,0 kWh'))
    expect(screen.queryByLabelText(ZEILE)).toBeNull()
    expect(screen.queryByLabelText(ZEILE_NEUTRAL)).toBeNull()
    expect(pvFelder()).toHaveLength(0)
    expect(document.body.textContent).not.toContain('der Anlage:')
    expect((await speichern(onSubmit)).pv_erzeugung_kwh).toBeUndefined()
  })

  it('Gegenprobe: mit den alten Kurzformen bliebe alles leer', async () => {
    render(
      <MonatsdatenForm
        anlageId={1}
        onSubmit={() => Promise.resolve()}
        onCancel={() => {}}
        haVorausfuellung={{
          jahr: 2025, monat: 5, monat_name: 'Mai', investitionen: [],
          basis: [{ feld: 'einspeisung', wert: 400 }, { feld: 'netzbezug', wert: 200 }, { feld: 'pv_gesamt', wert: 1000 }],
        }}
      />,
    )
    expect(feld('einspeisung_kwh')!.value).toBe('')
    expect(feld('netzbezug_kwh')!.value).toBe('')
    expect(screen.queryByLabelText(ZEILE)).toBeNull()
  })
})
