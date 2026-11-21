/**
 * Sensorwechsel mit Grund (Sitzung 3b) — die Abfrage an der Datenquellen-Fläche.
 *
 * (1) Ohne Frage sendet die Fläche nach der Prüfung ohne Grund (kein Dialog). (2) Mit Frage öffnet der Dialog, und **nichts**
 * wird gesendet, bevor «Übernehmen» geklickt ist; «Abbrechen» sendet nie. (3) «Fortsetzung» sendet den Grund. (4) Weg B: genau
 * zwei Antworten; «Daten vor der Änderung löschen» zeigt die Sätze der Prüf-Antwort (`loeschen`) ohne weitere Anfrage und sendet
 * `loeschen`; kein «verwerfen», kein «Falsch seit». (5) Der Fortschritt eines Laufs zeigt die Backend-Zahlen (auch
 * `art: 'loeschen'`). (6) Der Einstieg «Zähler getauscht» zeigt den Weg aus dem Backend und trägt nur beim Weg «fortsetzung» ein.
 *
 * Schwesterdateien: DatenquellenZuordnung.test.tsx (Quellen-Knöpfe), DatenquellenZuordnung.k4.test.tsx (Preset).
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import DatenquellenZuordnung from './DatenquellenZuordnung'
import SensorwechselDialog, { FALSCH_SEIT_LABEL, GRUND_FORTSETZUNG, GRUND_LOESCHEN, werteSatz } from './SensorwechselDialog'
import KorrekturFortschritt, {
  FORTSCHRITT_INTERVALL_MS, LOESCHEN_FERTIG_TAGE, LOESCHEN_LAEUFT, SATZ_FUELLEN_OFFEN, fortschrittSatz, tageText,
} from './KorrekturFortschritt'
import ZaehlerGetauschtDialog, { ZG_TITEL } from './ZaehlerGetauschtDialog'
import { datenquellenApi, type KorrekturLaufStand, type KorrekturVorschau, type QuellePruefung } from '../../api/datenquellen'
import { ApiError } from '../../api/client'

const FRAGE: QuellePruefung = {
  grund_erforderlich: true, erster_wert: '2025-11-01T02:00:00', tage: 649, stand_alt: 3615.0, stand_neu: 1500.25,
  sensor_key: 'basis:pv_gesamt', label: 'PV-Erzeugung Zählerstand', verzeichnet: true,
  loeschen: { saetze: ['Gelöscht werden nur die Daten dieses Felds vor der Änderung.', 'Für 10/2026 ist ein Monatswert gespeichert.'],
    monate: ['2026-10'] },
}

vi.mock('../../api/datenquellen', () => {
  const f = {
    id: 'basis_energy_pv_gesamt_kwh', feld: 'pv_gesamt_kwh', typ: 'basis',
    label: 'PV-Erzeugung Zählerstand', einheit: 'kWh', kategorie: 'energy',
    hinweis: '', standard_topic: 'eedc/1/energy/pv_gesamt_kwh',
    quelle: 'ha_app', gateway_topic: null, ha_entity: 'sensor.pv_alt', ha_name: null,
    invertieren: false, wert: 42, wert_zeit: null, probleme: [],
  }
  return {
    VERBINDUNG_GEAENDERT_EVENT: 'eedc:verbindung-geaendert',
    datenquellenApi: {
      getFelder: vi.fn(() => Promise.resolve({
        gruppen: [{ id: 'basis', label: 'Anlage (Basis)', typ: 'basis', felder: [f] }],
        verfuegbarkeit: { ha: true, mqtt: true, ha_quelle: 'ha_app' },
      })),
      pruefeQuelle: vi.fn(),
      korrekturLaeufe: vi.fn(() => Promise.resolve([])),
      wartendeWechsel: vi.fn(() => Promise.resolve([])),
      setQuelle: vi.fn(() => Promise.resolve({ korrektur: [] })),
      setInvert: vi.fn(() => Promise.resolve({})),
      korrekturLauf: vi.fn(),
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

const FID = 'basis_energy_pv_gesamt_kwh'

// Feste Uhr (Wächter N7): die Fixtures tragen Datums-Literale; «Getauscht am» liest «jetzt».
beforeEach(() => { vi.useFakeTimers({ now: new Date(2026, 10, 17, 12, 0), shouldAdvanceTime: true }) })
afterEach(() => { vi.useRealTimers() })
/** Die Wahl eines Grunds — der Wortlaut steht im Etikett (mit dem Folge-Satz). */
const radio = (wert: string) => {
  const r = document.querySelector(`input[type="radio"][value="${wert}"]`) as HTMLInputElement
  expect(r.closest('label')?.textContent).toContain(wert === 'loeschen' ? GRUND_LOESCHEN : GRUND_FORTSETZUNG)
  return r
}

describe('Sensorwechsel S3b — Abfrage an der Fläche', () => {
  beforeEach(() => vi.clearAllMocks())

  it('ohne Frage: prüfen, dann ohne Grund senden — kein Dialog', async () => {
    vi.mocked(datenquellenApi.pruefeQuelle).mockResolvedValue({ ...FRAGE, grund_erforderlich: false })
    render(<DatenquellenZuordnung />)
    fireEvent.click(await screen.findByRole('button', { name: /Inbound/i }))
    await waitFor(() => expect(datenquellenApi.setQuelle).toHaveBeenCalledWith(
      1, FID, 'mqtt_inbound_standard', undefined, undefined, undefined))
    expect(document.querySelector('[data-sensorwechsel-dialog]')).toBeNull()
  })

  it('mit Frage: Dialog, nichts gesendet; Abbrechen sendet nie; Fortsetzung sendet den Grund', async () => {
    vi.mocked(datenquellenApi.pruefeQuelle).mockResolvedValue(FRAGE)
    render(<DatenquellenZuordnung />)
    fireEvent.click(await screen.findByRole('button', { name: /Inbound/i }))
    await waitFor(() => expect(document.querySelector('[data-sensorwechsel-dialog]')).not.toBeNull())
    expect(datenquellenApi.setQuelle).not.toHaveBeenCalled()
    expect((document.querySelector('[data-sensorwechsel-ok]') as HTMLButtonElement).disabled).toBe(true)
    fireEvent.click(screen.getByRole('button', { name: 'Abbrechen' }))
    await waitFor(() => expect(document.querySelector('[data-sensorwechsel-dialog]')).toBeNull())
    expect(datenquellenApi.setQuelle).not.toHaveBeenCalled()

    fireEvent.click(screen.getByRole('button', { name: /Inbound/i }))
    await waitFor(() => expect(document.querySelector('[data-sensorwechsel-dialog]')).not.toBeNull())
    fireEvent.click(radio('fortsetzung'))
    fireEvent.click(document.querySelector('[data-sensorwechsel-ok]') as HTMLElement)
    await waitFor(() => expect(datenquellenApi.setQuelle).toHaveBeenCalledWith(
      1, FID, 'mqtt_inbound_standard', undefined, undefined, { grund: 'fortsetzung' }))
  })

  it('Weg B: genau zwei Antworten; «löschen» zeigt die Sätze der Prüf-Antwort und sendet `loeschen`', async () => {
    vi.mocked(datenquellenApi.pruefeQuelle).mockResolvedValue(FRAGE)
    render(<DatenquellenZuordnung />)
    fireEvent.click(await screen.findByRole('button', { name: /Inbound/i }))
    await waitFor(() => expect(document.querySelector('[data-sensorwechsel-dialog]')).not.toBeNull())
    expect([...document.querySelectorAll('input[type="radio"]')].map((r) => (r as HTMLInputElement).value))
      .toEqual(['fortsetzung', 'loeschen'])
    fireEvent.click(radio('loeschen'))
    expect(screen.getByText(FRAGE.loeschen!.saetze[0])).toBeInTheDocument()
    expect(screen.getByText(FRAGE.loeschen!.saetze[1])).toBeInTheDocument()
    expect(screen.queryByLabelText(FALSCH_SEIT_LABEL)).toBeNull()
    expect(datenquellenApi.pruefeQuelle).toHaveBeenCalledTimes(1)          // keine Vorschau-Anfrage: die Sätze kamen mit der Prüfung
    expect(datenquellenApi.setQuelle).not.toHaveBeenCalled()
    fireEvent.click(document.querySelector('[data-sensorwechsel-ok]') as HTMLElement)
    await waitFor(() => expect(datenquellenApi.setQuelle).toHaveBeenCalledWith(
      1, FID, 'mqtt_inbound_standard', undefined, undefined, { grund: 'loeschen' }))
  })
})

describe('SensorwechselDialog — Sperre und Anzeige', () => {
  it('ohne Wahl gesperrt; mit «löschen» frei; Zahlen nur angezeigt', () => {
    const bestaetigen = vi.fn()
    render(<SensorwechselDialog isOpen fragen={[FRAGE]} onBestaetigen={bestaetigen} onAbbrechen={() => {}} />)
    expect((document.querySelector('[data-sensorwechsel-ok]') as HTMLButtonElement).disabled).toBe(true)
    fireEvent.click(radio('loeschen'))
    expect((document.querySelector('[data-sensorwechsel-ok]') as HTMLButtonElement).disabled).toBe(false)
    fireEvent.click(document.querySelector('[data-sensorwechsel-ok]') as HTMLElement)
    expect(bestaetigen).toHaveBeenCalledWith({ 'basis:pv_gesamt': { grund: 'loeschen' } })
    expect(werteSatz(FRAGE)).toContain('649 Tage')
  })

  it('Fortschritt eines Laufs «löschen»: die Sätze nennen das Löschen, keine Korrektur', () => {
    const z = (p: Partial<KorrekturLaufStand>): KorrekturLaufStand => ({
      lauf: 'l', sensor_key: 'inv:1:pv_erzeugung_kwh', status: 'laeuft', tage: 2, erledigt: 0, fehler: [], beginn: null,
      ende: null, fuellen_offen: false, art: 'loeschen', ...p })
    expect(fortschrittSatz(z({}))).toBe(LOESCHEN_LAEUFT)
    expect(fortschrittSatz(z({ status: 'fertig', erledigt: 2 }))).toBe(LOESCHEN_FERTIG_TAGE(tageText(2)))
    expect(fortschrittSatz(z({ status: 'fertig', erledigt: 2 }))).not.toContain('Korrektur')
  })
})

describe('Fortschritt und Einstieg «Zähler getauscht»', () => {
  beforeEach(() => vi.clearAllMocks())

  it('Fortschritt: Backend-Zahlen, fertig ohne weiteres Abfragen', async () => {
    vi.mocked(datenquellenApi.korrekturLauf).mockResolvedValue({
      lauf: 'abc', sensor_key: 'inv:2:ladung_kwh', status: 'fertig', tage: 649, erledigt: 649,
      fehler: [{ tag: '2026-10-05', grund: 'x' }], beginn: null, ende: null, fuellen_offen: false })
    render(<KorrekturFortschritt anlageId={1} lauf="abc" />)
    expect(await screen.findByText(/Korrektur abgeschlossen, 649 Tage bearbeitet\. 1 Tag konnte nicht neu gebildet werden\./))
      .toBeInTheDocument()
    expect(datenquellenApi.korrekturLauf).toHaveBeenCalledTimes(1)
    expect(fortschrittSatz({ lauf: 'x', sensor_key: null, status: 'laeuft', tage: 10, erledigt: 3, fehler: [], beginn: null,
      ende: null, fuellen_offen: false })).toBe('Tage werden im Hintergrund neu gebildet: 3 von 10.')
  })

  it('Zähler getauscht: Weg Home Assistant ohne «Eintragen», Weg Fortsetzung trägt ein', async () => {
    vi.mocked(datenquellenApi.pruefeZaehlerGetauscht).mockResolvedValue({
      weg: 'home_assistant', sensor_key: 'basis:pv_gesamt', saetze: ['In Home Assistant anpassen.'], eintragen: false,
      getauscht_am: null })
    const { unmount } = render(<ZaehlerGetauschtDialog anlageId={1} feldId={FID} feldLabel="PV" onClose={() => {}} />)
    expect(await screen.findByText('In Home Assistant anpassen.')).toBeInTheDocument()
    expect(document.querySelector('[data-zg-eintragen]')).toBeNull()
    unmount()

    vi.mocked(datenquellenApi.pruefeZaehlerGetauscht).mockResolvedValue({
      weg: 'fortsetzung', sensor_key: 'inv:2:ladung_kwh', saetze: ['eedc überbrückt den Tausch.'], eintragen: true,
      getauscht_am: '2026-11-17T09:15:00' })
    vi.mocked(datenquellenApi.zaehlerGetauscht).mockResolvedValue({
      weg: 'fortsetzung', sensor_key: 'inv:2:ladung_kwh', saetze: ['eedc überbrückt den Tausch.'], eintragen: true,
      getauscht_am: '2026-11-17T09:15:00', eingetragen: true })
    render(<ZaehlerGetauschtDialog anlageId={1} feldId={FID} feldLabel="PV" onClose={() => {}} />)
    await waitFor(() => expect(document.querySelector('[data-zg-eintragen]')).not.toBeNull())
    fireEvent.click(document.querySelector('[data-zg-eintragen]') as HTMLElement)
    expect(await screen.findByText('Eingetragen.')).toBeInTheDocument()
    expect(datenquellenApi.zaehlerGetauscht).toHaveBeenCalledTimes(1)
  })
})

const STAND: KorrekturLaufStand = {
  lauf: 'L', sensor_key: 'basis:pv_gesamt', status: 'laeuft', tage: 9, erledigt: 2, fehler: [], beginn: null, ende: null,
  fuellen_offen: false,
}

describe('Korrekturrunde 3b-K — Fortschritt übersteht das Neuladen, Proben der unbemerkten Mutanten', () => {
  beforeEach(() => vi.clearAllMocks())

  it('Nr. 50: die Fläche zeigt beim Laden die laufenden Läufe der Anlage', async () => {
    vi.mocked(datenquellenApi.korrekturLaeufe).mockResolvedValueOnce(
      [{ lauf: 'L9', sensor_key: 'basis:pv_gesamt', label: 'PV-Erzeugung Zählerstand', beginn: null }])
    vi.mocked(datenquellenApi.korrekturLauf).mockResolvedValue({ ...STAND, lauf: 'L9' })
    render(<DatenquellenZuordnung />)
    expect(await screen.findByText('Tage werden im Hintergrund neu gebildet: 2 von 9.')).toBeInTheDocument()
    expect(datenquellenApi.korrekturLaeufe).toHaveBeenCalledWith(1)
    expect(datenquellenApi.korrekturLauf).toHaveBeenCalledWith(1, 'L9')
  })

  it.each([
    ['F03: der Lauf aus der Antwort der Feld-Route zeigt seinen Fortschritt', false],
    ['je Lauf eine Anzeige, auch wenn er schon beim Laden kam', true],
  ])('%s', async (_name, vorgeladen) => {
    vi.mocked(datenquellenApi.pruefeQuelle).mockResolvedValue(FRAGE)
    vi.mocked(datenquellenApi.korrekturLaeufe).mockResolvedValueOnce(vorgeladen
      ? [{ lauf: 'L3', sensor_key: 'basis:pv_gesamt', label: 'PV-Erzeugung Zählerstand', beginn: null }] : [])
    vi.mocked(datenquellenApi.setQuelle).mockResolvedValueOnce({ gespeichert: true, field_id: FID, quelle: 'x',
      korrektur: [{ lauf: 'L3', sensor_key: 'basis:pv_gesamt', label: 'PV', tage_neu: 9, zaehlerstaende_geloescht: 1 }] })
    vi.mocked(datenquellenApi.korrekturLauf).mockResolvedValue({ ...STAND, lauf: 'L3' })
    render(<DatenquellenZuordnung />)
    fireEvent.click(await screen.findByRole('button', { name: /Inbound/i }))
    await waitFor(() => expect(document.querySelector('[data-sensorwechsel-dialog]')).not.toBeNull())
    fireEvent.click(radio('fortsetzung'))
    fireEvent.click(document.querySelector('[data-sensorwechsel-ok]') as HTMLElement)
    await waitFor(() => expect(datenquellenApi.setQuelle).toHaveBeenCalled())
    await waitFor(() => expect(document.querySelectorAll('[data-korrektur-fortschritt="L3"]')).toHaveLength(1))
  })

  it('F04/F05: ein Füllen-Fehler zählt nicht als Tag; der Satz «Füllen steht aus» steht bei offenem Füllen', async () => {
    const z = { ...STAND, fehler: [{ tag: null, grund: 'Füllen: RuntimeError: HA weg' }], fuellen_offen: true }
    expect(fortschrittSatz(z)).toBe('Tage werden im Hintergrund neu gebildet: 2 von 9.')
    vi.mocked(datenquellenApi.korrekturLauf).mockResolvedValue({ ...z, status: 'fertig' })
    render(<KorrekturFortschritt anlageId={1} lauf="L" />)
    expect(await screen.findByText(SATZ_FUELLEN_OFFEN)).toBeInTheDocument()
  })

  it('Nr. 50: nach einem Abruf-Fehler fragt der Fortschritt weiter; ein unbekannter Lauf (404) beendet es', async () => {
    vi.mocked(datenquellenApi.korrekturLauf).mockRejectedValueOnce(new Error('Netz weg')).mockResolvedValue(STAND)
    const { unmount } = render(<KorrekturFortschritt anlageId={1} lauf="L" />)
    await waitFor(() => expect(datenquellenApi.korrekturLauf).toHaveBeenCalledTimes(1))
    vi.advanceTimersByTime(FORTSCHRITT_INTERVALL_MS)
    expect(await screen.findByText('Tage werden im Hintergrund neu gebildet: 2 von 9.')).toBeInTheDocument()
    unmount()

    vi.mocked(datenquellenApi.korrekturLauf).mockReset()
    vi.mocked(datenquellenApi.korrekturLauf).mockRejectedValue(new ApiError('Korrektur-Lauf nicht gefunden', 404))
    render(<KorrekturFortschritt anlageId={1} lauf="weg" />)
    await waitFor(() => expect(datenquellenApi.korrekturLauf).toHaveBeenCalledTimes(1))
    vi.advanceTimersByTime(FORTSCHRITT_INTERVALL_MS * 5)
    await new Promise((r) => setTimeout(r, 0))
    expect(datenquellenApi.korrekturLauf).toHaveBeenCalledTimes(1)
  })

  it('F12: kein Symbol «Zähler getauscht» an einem Feld ohne Quelle', async () => {
    const felder = await datenquellenApi.getFelder(1)
    const gruppe = felder.gruppen[0]
    vi.mocked(datenquellenApi.getFelder).mockResolvedValueOnce({
      ...felder, gruppen: [{ ...gruppe, felder: [{ ...gruppe.felder[0], quelle: 'keine', ha_entity: null }] }] })
    render(<DatenquellenZuordnung />)
    await screen.findByRole('button', { name: /Inbound/i })
    expect(screen.queryByRole('button', { name: ZG_TITEL })).toBeNull()
  })

  it('F17: ein geändertes «Falsch seit» lädt eine neue Vorschau; eine überholte Antwort wird verworfen', async () => {
    let erste: (v: KorrekturVorschau) => void = () => {}
    const onVorschau = vi.fn((_k: string, f: string) => (f === '2026-10-18T11:00'
      ? new Promise<KorrekturVorschau>((r) => { erste = r })
      : Promise.resolve({ saetze: [`Vorschau ab ${f}`], startbar: true })))
    // Weg B (B1): «Falsch seit» gibt es nur noch beim Nachtrag eines Grunds (Rückbau B2) — die Probe läuft dort.
    render(<SensorwechselDialog isOpen fragen={[{ ...FRAGE, vorgabe_falsch_seit: '2026-10-18T11:00:00' }]} onVorschau={onVorschau}
      onBestaetigen={() => {}} onAbbrechen={() => {}}
      nachtrag={{ wechselSatz: 'Am …', gruende: ['fortsetzung', 'korrektur'] }} />)
    fireEvent.click(document.querySelector('input[type="radio"][value="korrektur"]') as HTMLElement)
    fireEvent.change(document.querySelector('[data-falsch-seit]') as HTMLElement, { target: { value: '2026-09-01T07:00' } })
    expect(onVorschau).toHaveBeenLastCalledWith('basis:pv_gesamt', '2026-09-01T07:00')
    expect(await screen.findByText('Vorschau ab 2026-09-01T07:00')).toBeInTheDocument()
    erste({ saetze: ['ÜBERHOLT'], startbar: true })
    await new Promise((r) => setTimeout(r, 0))
    expect(screen.queryByText('ÜBERHOLT')).toBeNull()
    expect(screen.getByText('Vorschau ab 2026-09-01T07:00')).toBeInTheDocument()
  })

  it('F14: «Getauscht am» wird beim Eintragen gesendet; vor dem ersten Wert bleibt die Zeit wählbar, ohne «Eintragen»', async () => {
    vi.mocked(datenquellenApi.pruefeZaehlerGetauscht).mockImplementation((_a, _f, t) => Promise.resolve(
      t === '2020-01-01T08:00'
        ? { weg: 'vor_erstem_wert', sensor_key: 'x', saetze: ['Erst ab 01.09.2026 12:00 Uhr.'], eintragen: false,
            getauscht_am: t }
        : { weg: 'fortsetzung', sensor_key: 'x', saetze: ['eedc überbrückt den Tausch.'], eintragen: true,
            getauscht_am: t ?? null }))
    vi.mocked(datenquellenApi.zaehlerGetauscht).mockResolvedValue({ weg: 'fortsetzung', sensor_key: 'x', saetze: [],
      eintragen: true, getauscht_am: '2026-11-10T08:15', eingetragen: true })
    render(<ZaehlerGetauschtDialog anlageId={1} feldId={FID} feldLabel="PV" onClose={() => {}} />)
    await waitFor(() => expect(document.querySelector('[data-getauscht-am]')).not.toBeNull())
    fireEvent.change(document.querySelector('[data-getauscht-am]') as HTMLElement, { target: { value: '2020-01-01T08:00' } })
    expect(await screen.findByText('Erst ab 01.09.2026 12:00 Uhr.')).toBeInTheDocument()
    expect(document.querySelector('[data-getauscht-am]')).not.toBeNull()
    expect(document.querySelector('[data-zg-eintragen]')).toBeNull()
    fireEvent.change(document.querySelector('[data-getauscht-am]') as HTMLElement, { target: { value: '2026-11-10T08:15' } })
    await waitFor(() => expect(document.querySelector('[data-zg-eintragen]')).not.toBeNull())
    fireEvent.click(document.querySelector('[data-zg-eintragen]') as HTMLElement)
    await waitFor(() => expect(datenquellenApi.zaehlerGetauscht).toHaveBeenCalledWith(1, FID, '2026-11-10T08:15'))
  })
})
