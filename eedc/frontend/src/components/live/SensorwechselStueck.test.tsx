/**
 * Sensorwechsel mit Grund (Sitzung 4b-1) — «Grund nachtragen» am versetzten Abschnitt (Befund «Zählerstände – versetzter
 * Abschnitt»).
 *
 * (1) Der Sprung `?stueck=<schlüssel>~<sprung>~<rückgang>` öffnet an der Datenquellen-Fläche denselben Dialog: der Kopfsatz vom
 * Backend, nur «Korrektur», statt «Falsch seit» die feste Zeit des Stücks; die Vorschau kommt aus `…/zaehler-versatz/pruefen`
 * mit Grund «korrektur»; nichts wird gesendet, bevor «Übernehmen» geklickt ist; «Übernehmen» sendet das Stück an
 * `…/zaehler-versatz`, gestartete Läufe zeigt die Fläche. (2) Ein unvollständiger Parameter fragt nichts. (3) Gesperrt (etwa
 * verschiedene Quellen) ⇒ kein «Übernehmen». (4) Korrekturrunde 4b-1-K: ein Ladefehler im Stück-Modus steht an der Fläche
 * (kein Dialog), ein Speicherfehler im Dialog und nach «Abbrechen» nirgends; der Weg H-4 (am Rückkehr-Wechsel über
 * `?nachtrag=<id>` mit `stueck` in der Antwort) zeigt die feste Zeit statt «Falsch seit» und trägt über `…/grund` ein. Der
 * Client rechnet nichts.
 *
 * Schwesterdateien: SensorwechselNachtrag.test.tsx (Grund nachtragen am Wechsel), SensorwechselDialog.test.tsx.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import DatenquellenZuordnung from './DatenquellenZuordnung'
import SensorwechselDialog, { NACHTRAG_TITEL, STUECK_GRUND_KORREKTUR_FOLGE, STUECK_ZEIT } from './SensorwechselDialog'
import { STUECK_LADEFEHLER, stueckAusParameter } from './useGrundNachtragen'
import { datenquellenApi, type GrundNachtragPruefung } from '../../api/datenquellen'

const STUECK = { sprung: '2026-07-01T01:00:00', rueckgang: '2026-08-10T19:00:00' }
const PRUEFUNG: GrundNachtragPruefung = {
  grund_erforderlich: true, erster_wert: null, tage: 0, stand_alt: null, stand_neu: null,
  sensor_key: 'inv:2:ladung_pv_kwh', label: 'Wallbox – Ladung PV (kWh)', verzeichnet: false,
  vorgabe_falsch_seit: STUECK.sprung, korrektur: null, wechsel_id: null, feld_id: 'inv_energy_2_ladung_pv_kwh', grund: null,
  wechsel_satz: 'Vom 01.07.2026 01:00 bis 10.08.2026 19:00 Uhr liegen die gespeicherten Zählerstände dieses Felds um 103,1 kWh '
    + 'neben denen davor und danach; davor und danach gilt sensor.a.',
  gruende: ['korrektur'], korrektur_nicht: null, stueck: STUECK,
}
const PARAM = 'inv:2:ladung_pv_kwh~2026-07-01T01:00~2026-08-10T19:00'
const ANGABE = { sensor_key: 'inv:2:ladung_pv_kwh', sprung: '2026-07-01T01:00', rueckgang: '2026-08-10T19:00' }

vi.mock('../../api/datenquellen', () => {
  const f = {
    id: 'inv_energy_2_ladung_pv_kwh', feld: 'ladung_pv_kwh', typ: 'wallbox',
    label: 'Ladung PV', einheit: 'kWh', kategorie: 'energy',
    hinweis: '', standard_topic: 'eedc/1/energy/inv/2/ladung_pv_kwh',
    quelle: 'ha_app', gateway_topic: null, ha_entity: 'sensor.a', ha_name: null,
    invertieren: false, wert: 42, wert_zeit: null, probleme: [],
  }
  return {
    VERBINDUNG_GEAENDERT_EVENT: 'eedc:verbindung-geaendert',
    datenquellenApi: {
      getFelder: vi.fn(() => Promise.resolve({
        gruppen: [{ id: 'inv:2', label: 'Wallbox', typ: 'wallbox', felder: [f] }],
        verfuegbarkeit: { ha: true, mqtt: true, ha_quelle: 'ha_app' },
      })),
      pruefeQuelle: vi.fn(),
      korrekturLaeufe: vi.fn(() => Promise.resolve([])),
      korrekturLauf: vi.fn(() => new Promise(() => {})),
      setQuelle: vi.fn(),
      pruefeGrundNachtragen: vi.fn(),
      grundNachtragen: vi.fn(),
      pruefeStueck: vi.fn(),
      stueckKorrigieren: vi.fn(),
      pruefeZaehlerGetauscht: vi.fn(),
      zaehlerGetauscht: vi.fn(),
      haSensoren: vi.fn(() => Promise.resolve({ sensoren: [], vorschlaege: [], integrationen: [], warnungen: {} })),
      taktCheck: vi.fn(() => Promise.resolve({ geprueft: false })),
    },
  }
})

vi.mock('../../hooks', async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  useSelectedAnlage: () => ({ selectedAnlageId: 1, selectedAnlage: { id: 1, anlagenname: 'Test' } }),
}))

beforeEach(() => { vi.useFakeTimers({ now: new Date(2026, 10, 18, 12, 0), shouldAdvanceTime: true }) })
afterEach(() => { vi.useRealTimers() })

const radio = (wert: string) => document.querySelector(`input[type="radio"][value="${wert}"]`) as HTMLInputElement | null

describe('Sensorwechsel 4b-1 — Grund nachtragen am versetzten Abschnitt', () => {
  beforeEach(() => vi.clearAllMocks())

  it('Sprung mit stueck: nur «Korrektur», feste Zeit, Vorschau aus der Prüf-Route, «Übernehmen» sendet das Stück', async () => {
    vi.mocked(datenquellenApi.pruefeStueck).mockResolvedValue(PRUEFUNG)
    vi.mocked(datenquellenApi.stueckKorrigieren).mockResolvedValue({
      ...PRUEFUNG, eingetragen: true,
      korrektur: [{ lauf: 'L7', sensor_key: 'inv:2:ladung_pv_kwh', label: 'Ladung PV', tage_neu: 0, zaehlerstaende_geloescht: 972 }],
    })
    render(<DatenquellenZuordnung sprung={{ geraet: '2', feld: 'ladung_pv_kwh', stueck: PARAM }} />)
    await waitFor(() => expect(document.querySelector('[data-sensorwechsel-dialog]')).not.toBeNull())
    expect(datenquellenApi.pruefeStueck).toHaveBeenCalledWith(1, ANGABE)
    expect(datenquellenApi.pruefeGrundNachtragen).not.toHaveBeenCalled()
    expect(screen.getByText(NACHTRAG_TITEL)).toBeInTheDocument()
    expect(screen.getByText(PRUEFUNG.wechsel_satz)).toBeInTheDocument()
    await waitFor(() => expect(radio('korrektur')).not.toBeNull())
    expect(radio('fortsetzung')).toBeNull()
    expect(screen.getByText(STUECK_GRUND_KORREKTUR_FOLGE)).toBeInTheDocument()
    vi.mocked(datenquellenApi.pruefeStueck).mockResolvedValue({ ...PRUEFUNG, korrektur: { saetze: ['Stück-Satz.'], startbar: true } })
    fireEvent.click(radio('korrektur') as HTMLElement)
    await waitFor(() => expect(datenquellenApi.pruefeStueck).toHaveBeenLastCalledWith(1, ANGABE, 'korrektur'))
    expect(await screen.findByText('Stück-Satz.')).toBeInTheDocument()
    expect(screen.getByText(STUECK_ZEIT('01.07.2026 01:00', '10.08.2026 19:00'))).toBeInTheDocument()
    expect(document.querySelector('[data-falsch-seit]')).toBeNull()
    expect(datenquellenApi.stueckKorrigieren).not.toHaveBeenCalled()
    fireEvent.click(document.querySelector('[data-sensorwechsel-ok]') as HTMLElement)
    await waitFor(() => expect(datenquellenApi.stueckKorrigieren).toHaveBeenCalledWith(1, ANGABE))
    await waitFor(() => expect(document.querySelector('[data-sensorwechsel-dialog]')).toBeNull())
    await waitFor(() => expect(datenquellenApi.korrekturLauf).toHaveBeenCalledWith(1, 'L7'))
  })

  it('unvollständiger Parameter fragt nichts', async () => {
    expect(stueckAusParameter('inv:2:ladung_pv_kwh~2026-07-01T01:00')).toBeNull()
    expect(stueckAusParameter(undefined)).toBeNull()
    expect(stueckAusParameter(PARAM)).toEqual(ANGABE)
    render(<DatenquellenZuordnung sprung={{ geraet: '2', stueck: 'kaputt' }} />)
    await waitFor(() => expect(datenquellenApi.getFelder).toHaveBeenCalled())
    expect(datenquellenApi.pruefeStueck).not.toHaveBeenCalled()
  })

  it('gesperrt: der Satz statt «Korrektur», kein «Übernehmen»', () => {
    render(<SensorwechselDialog isOpen fragen={[PRUEFUNG]}
      onVorschau={() => Promise.resolve(null)} onBestaetigen={() => {}} onAbbrechen={() => {}}
      nachtrag={{ wechselSatz: PRUEFUNG.wechsel_satz, gruende: [], korrekturNicht: 'Verschiedene Quellen.', stueck: STUECK }} />)
    expect(radio('korrektur')).toBeNull()
    expect(screen.getByText('Verschiedene Quellen.')).toBeInTheDocument()
    expect(document.querySelector('[data-sensorwechsel-ok]')).toBeNull()
  })

  it('Ladefehler im Stück-Modus steht an der Fläche (kein Dialog)', async () => {
    vi.mocked(datenquellenApi.pruefeStueck).mockRejectedValue(new Error('Dieser Abschnitt ist nicht (mehr) zu finden'))
    render(<DatenquellenZuordnung sprung={{ geraet: '2', feld: 'ladung_pv_kwh', stueck: PARAM }} />)
    await waitFor(() => expect(document.body.textContent).toContain(`${STUECK_LADEFEHLER}: Dieser Abschnitt ist nicht (mehr) zu finden`))
    expect(document.querySelector('[data-sensorwechsel-dialog]')).toBeNull()
  })

  it('Speicherfehler im Stück-Modus: im Dialog, nach «Abbrechen» nirgends', async () => {
    const satz = 'Home Assistant ist nicht erreichbar — die Korrektur startet erst, wenn eedc die Langzeitstatistik lesen kann.'
    vi.mocked(datenquellenApi.pruefeStueck).mockResolvedValue({ ...PRUEFUNG, korrektur: { saetze: ['Stück-Satz.'], startbar: true } })
    vi.mocked(datenquellenApi.stueckKorrigieren).mockRejectedValue(new Error(satz))
    render(<DatenquellenZuordnung sprung={{ geraet: '2', feld: 'ladung_pv_kwh', stueck: PARAM }} />)
    await waitFor(() => expect(radio('korrektur')).not.toBeNull())
    fireEvent.click(radio('korrektur') as HTMLElement)
    expect(await screen.findByText('Stück-Satz.')).toBeInTheDocument()
    fireEvent.click(document.querySelector('[data-sensorwechsel-ok]') as HTMLElement)
    await waitFor(() => expect(screen.getByText(satz)).toBeInTheDocument())
    expect(document.querySelector('[data-sensorwechsel-dialog]')).not.toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Abbrechen' }))
    await waitFor(() => expect(document.querySelector('[data-sensorwechsel-dialog]')).toBeNull())
    expect(document.body.textContent).not.toContain(satz)
    expect(document.body.textContent).not.toContain(STUECK_LADEFEHLER)
  })

  it('H-4 am Rückkehr-Wechsel (nachtrag mit stueck): feste Zeit statt «Falsch seit», Eintrag über «Grund nachtragen»', async () => {
    const h4: GrundNachtragPruefung = {
      ...PRUEFUNG, wechsel_id: 5, verzeichnet: true, gruende: ['fortsetzung', 'korrektur'],
      wechsel_satz: 'Am 10.08.2026 19:00 Uhr wechselte die Quelle von sensor.x zu sensor.a.',
    }
    vi.mocked(datenquellenApi.pruefeGrundNachtragen).mockResolvedValue(h4)
    vi.mocked(datenquellenApi.grundNachtragen).mockResolvedValue({ ...h4, eingetragen: true, korrektur: [] })
    render(<DatenquellenZuordnung sprung={{ geraet: '2', feld: 'ladung_pv_kwh', nachtrag: '5' }} />)
    await waitFor(() => expect(radio('korrektur')).not.toBeNull())
    expect(datenquellenApi.pruefeStueck).not.toHaveBeenCalled()
    expect(radio('fortsetzung')).not.toBeNull()
    vi.mocked(datenquellenApi.pruefeGrundNachtragen).mockResolvedValue({ ...h4, korrektur: { saetze: ['H4-Satz.'], startbar: true } })
    fireEvent.click(radio('korrektur') as HTMLElement)
    await waitFor(() => expect(datenquellenApi.pruefeGrundNachtragen).toHaveBeenLastCalledWith(
      1, 5, expect.objectContaining({ grund: 'korrektur' })))
    expect(await screen.findByText('H4-Satz.')).toBeInTheDocument()
    expect(screen.getByText(STUECK_ZEIT('01.07.2026 01:00', '10.08.2026 19:00'))).toBeInTheDocument()
    expect(screen.getByText(STUECK_GRUND_KORREKTUR_FOLGE)).toBeInTheDocument()
    expect(document.querySelector('[data-falsch-seit]')).toBeNull()
    expect(datenquellenApi.grundNachtragen).not.toHaveBeenCalled()
    fireEvent.click(document.querySelector('[data-sensorwechsel-ok]') as HTMLElement)
    await waitFor(() => expect(datenquellenApi.grundNachtragen).toHaveBeenCalledWith(
      1, 5, expect.objectContaining({ grund: 'korrektur' })))
    expect(datenquellenApi.stueckKorrigieren).not.toHaveBeenCalled()
  })
})
