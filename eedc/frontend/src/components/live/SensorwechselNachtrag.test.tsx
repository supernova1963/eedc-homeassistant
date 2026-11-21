/**
 * Sensorwechsel mit Grund (Sitzung 4) — «Grund nachtragen» und der Einstieg ohne Rückweg.
 *
 * (1) Der Sprung `?nachtrag=<id>` (Befund «Zuordnung geändert, Grund fehlt») öffnet an der Datenquellen-Fläche denselben
 * Dialog im Nachtrag-Modus: Titel «Warum wechselte die Quelle?», der Wechsel als Satz, nur die zulässigen Gründe; nichts wird
 * gesendet, bevor «Übernehmen» geklickt ist; «Übernehmen» sendet den Grund an `…/grund`, gestartete Läufe zeigt die Fläche.
 * (2) Ohne zulässigen Grund kein «Übernehmen». (3) Der Einstieg «Zähler getauscht» sagt vor dem Eintragen, dass sich ein
 * Eintrag nicht zurücknehmen lässt (Bauplan §12 Nr. 62).
 * Korrekturrunde 4-K (Bauplan §13 Nr. 69/70): im Nachtrag sagt der Grund-Text «Korrektur», dass bis zum Wechsel verworfen wird;
 * ein Speicherfehler, dann «Abbrechen» lässt keinen Satz an der Fläche stehen (schon gar nicht «ließ sich nicht laden»).
 *
 * Schwesterdateien: SensorwechselDialog.test.tsx (Abfrage beim Wechsel, Fortschritt, Einstieg).
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import DatenquellenZuordnung from './DatenquellenZuordnung'
import SensorwechselDialog, {
  GRUND_FORTSETZUNG_FOLGE, GRUND_KORREKTUR, GRUND_LOESCHEN_FOLGE, NACHTRAG_FORTSETZUNG_ZUSATZ, NACHTRAG_GRUND_KORREKTUR_FOLGE,
  NACHTRAG_NICHTS, NACHTRAG_TITEL,
} from './SensorwechselDialog'
import { NACHTRAG_LADEFEHLER } from './useGrundNachtragen'
import ZaehlerGetauschtDialog, { ZG_ENDGUELTIG } from './ZaehlerGetauschtDialog'
import { datenquellenApi, type GrundNachtragPruefung } from '../../api/datenquellen'

const NACHTRAG: GrundNachtragPruefung = {
  grund_erforderlich: true, erster_wert: '2024-11-01T03:00:00', tage: 681, stand_alt: null, stand_neu: null,
  sensor_key: 'inv:2:ladung_kwh', label: 'SMA eCharger 22 – Ladung gesamt (kWh)', verzeichnet: true,
  vorgabe_falsch_seit: '2024-11-01T03:00:00', korrektur: null, wechsel_id: 5, feld_id: 'inv_energy_2_ladung_kwh', grund: null,
  wechsel_satz: 'Am 18.10.2026 10:47 Uhr wechselte die Quelle von sensor.a zu sensor.b.', gruende: ['fortsetzung', 'korrektur'],
  korrektur_nicht: null,
}

vi.mock('../../api/datenquellen', () => {
  const f = {
    id: 'inv_energy_2_ladung_kwh', feld: 'ladung_kwh', typ: 'wallbox',
    label: 'Ladung gesamt', einheit: 'kWh', kategorie: 'energy',
    hinweis: '', standard_topic: 'eedc/1/energy/inv/2/ladung_kwh',
    quelle: 'ha_app', gateway_topic: null, ha_entity: 'sensor.b', ha_name: null,
    invertieren: false, wert: 42, wert_zeit: null, probleme: [],
  }
  return {
    VERBINDUNG_GEAENDERT_EVENT: 'eedc:verbindung-geaendert',
    datenquellenApi: {
      getFelder: vi.fn(() => Promise.resolve({
        gruppen: [{ id: 'inv:2', label: 'SMA eCharger 22', typ: 'wallbox', felder: [f] }],
        verfuegbarkeit: { ha: true, mqtt: true, ha_quelle: 'ha_app' },
      })),
      pruefeQuelle: vi.fn(),
      korrekturLaeufe: vi.fn(() => Promise.resolve([])),
      wartendeWechsel: vi.fn(() => Promise.resolve([])),
      korrekturLauf: vi.fn(() => new Promise(() => {})),
      setQuelle: vi.fn(),
      pruefeGrundNachtragen: vi.fn(),
      grundNachtragen: vi.fn(),
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

describe('Sensorwechsel S4 — Grund nachtragen', () => {
  beforeEach(() => vi.clearAllMocks())

  it('Sprung mit nachtrag: Dialog in der Vergangenheit, nichts gesendet bis «Übernehmen», dann der Grund und der Lauf', async () => {
    vi.mocked(datenquellenApi.pruefeGrundNachtragen).mockResolvedValue(NACHTRAG)
    vi.mocked(datenquellenApi.grundNachtragen).mockResolvedValue({
      ...NACHTRAG, eingetragen: true,
      korrektur: [{ lauf: 'L9', sensor_key: 'inv:2:ladung_kwh', label: 'Ladung', tage_neu: 3, zaehlerstaende_geloescht: 7 }],
    })
    render(<DatenquellenZuordnung sprung={{ geraet: '2', feld: 'ladung_kwh', nachtrag: '5' }} />)
    await waitFor(() => expect(document.querySelector('[data-sensorwechsel-dialog]')).not.toBeNull())
    expect(datenquellenApi.pruefeGrundNachtragen).toHaveBeenCalledWith(1, 5)
    expect(screen.getByText(NACHTRAG_TITEL)).toBeInTheDocument()
    expect(screen.getByText(NACHTRAG.wechsel_satz)).toBeInTheDocument()
    expect(datenquellenApi.grundNachtragen).not.toHaveBeenCalled()
    await waitFor(() => expect(radio('korrektur')).not.toBeNull())
    vi.mocked(datenquellenApi.pruefeGrundNachtragen).mockResolvedValue({
      ...NACHTRAG, korrektur: { saetze: ['Vorschau-Satz.'], startbar: true } })
    fireEvent.click(radio('korrektur') as HTMLElement)
    await waitFor(() => expect(datenquellenApi.pruefeGrundNachtragen).toHaveBeenLastCalledWith(
      1, 5, { grund: 'korrektur', falsch_seit: '2024-11-01T03:00' }))
    expect(await screen.findByText('Vorschau-Satz.')).toBeInTheDocument()
    expect(datenquellenApi.grundNachtragen).not.toHaveBeenCalled()
    fireEvent.click(document.querySelector('[data-sensorwechsel-ok]') as HTMLElement)
    await waitFor(() => expect(datenquellenApi.grundNachtragen).toHaveBeenCalledWith(
      1, 5, { grund: 'korrektur', falsch_seit: '2024-11-01T03:00' }))
    await waitFor(() => expect(document.querySelector('[data-sensorwechsel-dialog]')).toBeNull())
    await waitFor(() => expect(datenquellenApi.korrekturLauf).toHaveBeenCalledWith(1, 'L9'))
  })

  it('nur die zulässigen Gründe; der Satz, warum «Korrektur» fehlt; ohne Grund kein «Übernehmen»', async () => {
    const { unmount } = render(<SensorwechselDialog isOpen fragen={[NACHTRAG]} onVorschau={() => Promise.resolve(null)}
      onBestaetigen={() => {}} onAbbrechen={() => {}}
      nachtrag={{ wechselSatz: NACHTRAG.wechsel_satz, gruende: ['fortsetzung'], korrekturNicht: 'Nur am jüngsten Wechsel.' }} />)
    expect(radio('fortsetzung')).not.toBeNull()
    expect(radio('korrektur')).toBeNull()
    expect(screen.queryByText(GRUND_KORREKTUR)).toBeNull()
    expect(screen.getByText('Nur am jüngsten Wechsel.')).toBeInTheDocument()
    unmount()
    render(<SensorwechselDialog isOpen fragen={[NACHTRAG]} onVorschau={() => Promise.resolve(null)}
      onBestaetigen={() => {}} onAbbrechen={() => {}} nachtrag={{ wechselSatz: NACHTRAG.wechsel_satz, gruende: [] }} />)
    expect(screen.getByText(NACHTRAG_NICHTS)).toBeInTheDocument()
    expect(document.querySelector('[data-sensorwechsel-ok]')).toBeNull()
    expect(radio('fortsetzung')).toBeNull()
  })
})

describe('Sensorwechsel S4-K — Texte und Fehler im Nachtrag (§13 Nr. 69/70)', () => {
  beforeEach(() => vi.clearAllMocks())

  it('im Nachtrag sagt «Korrektur» «bis zum Wechsel» und «Fortsetzung» den Zusatz, beim Wechsel «bleiben» und «löschen»', () => {
    const fragen = [NACHTRAG]
    const { unmount } = render(<SensorwechselDialog isOpen fragen={fragen} onVorschau={vi.fn()} onBestaetigen={vi.fn()}
      onAbbrechen={vi.fn()} nachtrag={{ wechselSatz: NACHTRAG.wechsel_satz, gruende: ['fortsetzung', 'korrektur'] }} />)
    expect(screen.getByText(NACHTRAG_GRUND_KORREKTUR_FOLGE)).toBeInTheDocument()
    expect(screen.queryByText(GRUND_LOESCHEN_FOLGE)).toBeNull()
    // «Zu §13» Nr. 87: im Nachtrag steht neben dem freigegebenen Fortsetzungs-Satz der Zusatz zum fest gespeicherten Tageswert
    expect(screen.getByText(`${GRUND_FORTSETZUNG_FOLGE} ${NACHTRAG_FORTSETZUNG_ZUSATZ}`)).toBeInTheDocument()
    unmount()
    render(<SensorwechselDialog isOpen fragen={fragen} onVorschau={vi.fn()} onBestaetigen={vi.fn()} onAbbrechen={vi.fn()} />)
    expect(screen.getByText(GRUND_LOESCHEN_FOLGE)).toBeInTheDocument()            // Weg B: beim Wechsel «löschen» statt «verwerfen»
    expect(screen.queryByText(NACHTRAG_GRUND_KORREKTUR_FOLGE)).toBeNull()
    expect(document.body.textContent).not.toContain(GRUND_KORREKTUR)
    expect(screen.getByText(GRUND_FORTSETZUNG_FOLGE)).toBeInTheDocument()
    expect(document.body.textContent).not.toContain(NACHTRAG_FORTSETZUNG_ZUSATZ)
  })

  it('Speicherfehler, dann «Abbrechen»: der Fehler stand im Dialog, danach steht an der Fläche nichts', async () => {
    const satz = 'Home Assistant ist nicht erreichbar — die Korrektur startet erst, wenn eedc die Langzeitstatistik lesen kann.'
    vi.mocked(datenquellenApi.pruefeGrundNachtragen).mockResolvedValue(NACHTRAG)
    vi.mocked(datenquellenApi.grundNachtragen).mockRejectedValue(new Error(satz))
    render(<DatenquellenZuordnung sprung={{ geraet: '2', feld: 'ladung_kwh', nachtrag: '5' }} />)
    await waitFor(() => expect(radio('fortsetzung')).not.toBeNull())
    fireEvent.click(radio('fortsetzung') as HTMLElement)
    fireEvent.click(document.querySelector('[data-sensorwechsel-ok]') as HTMLElement)
    await waitFor(() => expect(screen.getByText(satz)).toBeInTheDocument())
    expect(document.querySelector('[data-sensorwechsel-dialog]')).not.toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Abbrechen' }))
    await waitFor(() => expect(document.querySelector('[data-sensorwechsel-dialog]')).toBeNull())
    expect(document.body.textContent).not.toContain(NACHTRAG_LADEFEHLER)
    expect(document.body.textContent).not.toContain(satz)
  })

  it('ein Ladefehler steht an der Fläche (kein Dialog)', async () => {
    vi.mocked(datenquellenApi.pruefeGrundNachtragen).mockRejectedValue(new Error('Wechsel nicht gefunden'))
    render(<DatenquellenZuordnung sprung={{ geraet: '2', feld: 'ladung_kwh', nachtrag: '999' }} />)
    await waitFor(() => expect(document.body.textContent).toContain(`${NACHTRAG_LADEFEHLER}: Wechsel nicht gefunden`))
    expect(document.querySelector('[data-sensorwechsel-dialog]')).toBeNull()
  })
})

describe('Sensorwechsel S4 — Einstieg ohne Rückweg (§12 Nr. 62)', () => {
  beforeEach(() => vi.clearAllMocks())

  it('vor dem Eintragen steht der Satz; ohne «Eintragen» nicht', async () => {
    vi.mocked(datenquellenApi.pruefeZaehlerGetauscht).mockResolvedValue({
      weg: 'fortsetzung', sensor_key: 'inv:2:ladung_kwh', saetze: ['eedc überbrückt den Tausch.'], eintragen: true,
      getauscht_am: '2026-11-17T09:15:00' })
    const { unmount } = render(<ZaehlerGetauschtDialog anlageId={1} feldId="x" feldLabel="PV" onClose={() => {}} />)
    expect(await screen.findByText(ZG_ENDGUELTIG)).toBeInTheDocument()
    unmount()
    vi.mocked(datenquellenApi.pruefeZaehlerGetauscht).mockResolvedValue({
      weg: 'home_assistant', sensor_key: 'inv:2:ladung_kwh', saetze: ['In Home Assistant anpassen.'], eintragen: false,
      getauscht_am: null })
    render(<ZaehlerGetauschtDialog anlageId={1} feldId="x" feldLabel="PV" onClose={() => {}} />)
    expect(await screen.findByText('In Home Assistant anpassen.')).toBeInTheDocument()
    expect(screen.queryByText(ZG_ENDGUELTIG)).toBeNull()
  })
})
