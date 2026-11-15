/**
 * Diagnose-Paket-Dialog v4 (Bauplan §5 S2 Schritt 3): Bereitstellen beim Öffnen (Variante A, synchron), Inhaltsliste,
 * Versand-Satz nach `versandweg`, Weg des Herunterladens (außerhalb des HA-Rahmens und auf dem iPhone `downloadFile`,
 * im HA-Rahmen sonst Prüfabruf + Navigation), abgelaufene Marke (K8), `gueltig_s`, Teilfehler; Abschluss-Meldung
 * (Lab rc36): Kreisel und gesperrter Knopf während des Downloads, «Heruntergeladen: …» bzw. «Der Download läuft im
 * Hintergrund …» nach höchstens 90 s Abfrage auf dem Navigationsweg, «Schließen», kein automatisches Schließen.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import DiagnosePaketDialog, {
  ABFRAGE_MS, TEXT_ABGELAUFEN, TEXT_ABGELAUFEN_NEU, WARTEZEIT_MS,
} from './DiagnosePaketDialog'
import type { DiagnosePaketBereit } from '../../api/datenChecker'

// `downloadFile` wird ersetzt: die echte Fassung klickt einen `<a download>` (jsdom kennt keine Navigation).
const download = vi.fn().mockResolvedValue(undefined)
const imHaRahmen = vi.fn(() => false)
const appleMobil = vi.fn(() => false)
vi.mock('../../lib/download', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../lib/download')>()),
  downloadFile: (...a: unknown[]) => download(...a),
  istImHaRahmen: () => imHaRahmen(),
  istAppleMobil: () => appleMobil(),
}))
const bereitstellen = vi.fn()
const pruefen = vi.fn()
vi.mock('../../api/datenChecker', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../api/datenChecker')>()),
  datenCheckerApi: { diagnosePaketBereitstellen: (...a: unknown[]) => bereitstellen(...a) },
  diagnosePaketPruefen: (...a: unknown[]) => pruefen(...a),
}))

const URL_A = './api/system/diagnose-paket/7?marke=m-a'
/** Zusatz Versand-Hinweis (Entscheid Gernot 15.11.2026): steht bei beiden Versandwegen. */
const VERSAND_HINWEIS = 'eedc verschickt die Datei nicht — den Weg zu uns wählst du. Die Datei ist nicht verschlüsselt.'

function paket(teil: Partial<DiagnosePaketBereit> = {}): DiagnosePaketBereit {
  return {
    marke: 'm-a',
    dateiname: 'eedc_diagnose_Haus_2026-11-15.zip',
    bytes: 2_345_678,
    megabyte: 2.345678,
    gueltig_s: 900,
    versandweg: 'email',
    inhalt: {
      geraete: 5, tarife: 1, zuordnungen: 12, monatswerte: 41, tageswerte: 400, stundenwerte: 281_000,
      notizen: 2, protokollzeilen: 1234, protokollzeilen_ohne_anlage: 10, befunde: 25,
    },
    teilfehler: [],
    ...teil,
  }
}

/** Antwort des Prüfabrufs: gültig mit Zählerstand, oder 404. */
const stand = (ausgeliefert: number) => ({ gueltig: true, ausgeliefert })
const NICHT_BEREIT = { gueltig: false, ausgeliefert: 0 }

let vorherLocation: Location
let assign: ReturnType<typeof vi.fn>

function haRahmenMitNavigation() {
  imHaRahmen.mockReturnValue(true)
  assign = vi.fn()
  Object.defineProperty(window, 'location', { configurable: true, value: { ...vorherLocation, assign } })
}

describe('DiagnosePaketDialog', () => {
  beforeEach(() => {
    download.mockReset().mockResolvedValue(undefined)
    imHaRahmen.mockReturnValue(false)
    appleMobil.mockReturnValue(false)
    bereitstellen.mockReset().mockResolvedValue(paket())
    pruefen.mockReset().mockResolvedValue(stand(0))
    vorherLocation = window.location
    assign = vi.fn()
  })

  afterEach(() => {
    vi.useRealTimers()
    Object.defineProperty(window, 'location', { configurable: true, value: vorherLocation })
  })

  it('stellt beim Öffnen bereit und zeigt die Inhaltsliste', async () => {
    render(<DiagnosePaketDialog isOpen onClose={() => {}} anlageId={7} />)
    expect(screen.getByText('Diagnose-Paket wird zusammengestellt …')).toBeTruthy()
    expect(await screen.findByText('Drin ist:')).toBeTruthy()
    expect(bereitstellen).toHaveBeenCalledWith(7)
    expect(screen.getByText(/5 Geräte, 1 Tarif, Kosten und/)).toBeTruthy()
    expect(screen.getByText(/12 Zuordnungen mit Entity-Namen und MQTT-Topics/)).toBeTruthy()
    expect(screen.getByText(/41 Monatswerte, 400 Tageswerte, 281\.000 Stundenwerte/)).toBeTruthy()
    expect(screen.getByText(/Eigene Notizen und Beschreibungen \(2\)/)).toBeTruthy()
    expect(screen.getByText(/der ganzen Installation \(1\.234 Zeilen, 25 Befunde\)/)).toBeTruthy()
    expect(screen.getByText(/^Nicht drin: Zugangsdaten, Straße, Fotos, Infothek/)).toBeTruthy()
    expect(screen.getByText('Größe: 2,3 MB')).toBeTruthy()
    expect(screen.getByText(/Lade das Paket erst herunter, wenn wir dich in unserer Antwort darum bitten/)).toBeTruthy()
    expect(screen.getByRole('button', { name: /Herunterladen/ })).toBeTruthy()
  })

  it('lädt nichts, solange der Dialog zu ist', () => {
    render(<DiagnosePaketDialog isOpen={false} onClose={() => {}} anlageId={7} />)
    expect(bereitstellen).not.toHaveBeenCalled()
  })

  it('zeigt den Fehlertext, wenn das Bereitstellen scheitert', async () => {
    bereitstellen.mockRejectedValueOnce(new Error('OSError: kein Platz'))
    render(<DiagnosePaketDialog isOpen onClose={() => {}} anlageId={7} />)
    expect(await screen.findByText('Das Diagnose-Paket konnte nicht erstellt werden. OSError: kein Platz')).toBeTruthy()
    expect(screen.queryByRole('button', { name: /Herunterladen/ })).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: /Neu zusammenstellen/ }))
    expect(await screen.findByText('Drin ist:')).toBeTruthy()
    expect(bereitstellen).toHaveBeenCalledTimes(2)
  })

  it('Versand-Satz nach versandweg', async () => {
    const { unmount } = render(<DiagnosePaketDialog isOpen onClose={() => {}} anlageId={7} />)
    expect((await screen.findByTestId('versand-satz')).textContent).toBe(
      'Schick die Datei per E-Mail an die Adresse aus unserer Antwort — nicht öffentlich posten.')
    expect(screen.getByTestId('versand-hinweis').textContent).toBe(VERSAND_HINWEIS)
    unmount()
    bereitstellen.mockResolvedValue(paket({ versandweg: 'freigabe_link', bytes: 12_000_000, megabyte: 12 }))
    render(<DiagnosePaketDialog isOpen onClose={() => {}} anlageId={7} />)
    expect((await screen.findByTestId('versand-satz')).textContent).toBe(
      'Die Datei ist zu groß für eine E-Mail: lege sie in einen Cloud-Speicher (etwa Dropbox oder Google Drive) und '
      + 'schick den Freigabe-Link an die Adresse aus unserer Antwort — nicht öffentlich posten.')
    expect(screen.getByTestId('versand-hinweis').textContent).toBe(VERSAND_HINWEIS)
    expect(screen.getByText('Größe: 12,0 MB')).toBeTruthy()
  })

  it('außerhalb des HA-Rahmens lädt «Herunterladen» per downloadFile mit Marke', async () => {
    render(<DiagnosePaketDialog isOpen onClose={() => {}} anlageId={7} />)
    fireEvent.click(await screen.findByRole('button', { name: /Herunterladen/ }))
    await waitFor(() => expect(download).toHaveBeenCalledWith(URL_A, 'eedc_diagnose_Haus_2026-11-15.zip'))
    expect(pruefen).not.toHaveBeenCalled()
  })

  it('außerhalb des HA-Rahmens bei 404 derselbe Text und neu bereitstellen; anderer Fehler mit eigenem Text', async () => {
    const { DownloadFehler } = await import('../../lib/download')
    download.mockRejectedValueOnce(new DownloadFehler('Diagnose-Paket nicht (mehr) bereit', 404))
    render(<DiagnosePaketDialog isOpen onClose={() => {}} anlageId={7} />)
    fireEvent.click(await screen.findByRole('button', { name: /Herunterladen/ }))
    expect(await screen.findByText(TEXT_ABGELAUFEN_NEU)).toBeTruthy()
    await waitFor(() => expect(bereitstellen).toHaveBeenCalledTimes(2))

    download.mockRejectedValueOnce(new DownloadFehler('HTTP 500', 500))
    fireEvent.click(await screen.findByRole('button', { name: /Herunterladen/ }))
    expect(await screen.findByText('Die Datei konnte nicht heruntergeladen werden.')).toBeTruthy()
    expect(bereitstellen).toHaveBeenCalledTimes(2)
  })

  it('im HA-Rahmen prüft zuerst und navigiert bei gültiger Marke', async () => {
    haRahmenMitNavigation()
    render(<DiagnosePaketDialog isOpen onClose={() => {}} anlageId={7} />)
    fireEvent.click(await screen.findByRole('button', { name: /Herunterladen/ }))
    await waitFor(() => expect(assign).toHaveBeenCalledWith(URL_A))
    expect(pruefen).toHaveBeenCalledWith(7, 'm-a')
    expect(pruefen.mock.invocationCallOrder[0]).toBeLessThan(assign.mock.invocationCallOrder[0])
    expect(download).not.toHaveBeenCalled()
  })

  it('im HA-Rahmen bei 404 kein location.assign, Text sichtbar, stellt neu bereit', async () => {
    haRahmenMitNavigation()
    pruefen.mockResolvedValueOnce(NICHT_BEREIT)
    render(<DiagnosePaketDialog isOpen onClose={() => {}} anlageId={7} />)
    fireEvent.click(await screen.findByRole('button', { name: /Herunterladen/ }))
    expect(await screen.findByText(TEXT_ABGELAUFEN_NEU)).toBeTruthy()
    await waitFor(() => expect(bereitstellen).toHaveBeenCalledTimes(2))
    expect(assign).not.toHaveBeenCalled()
    expect(download).not.toHaveBeenCalled()
  })

  it('im HA-Rahmen auf dem iPhone lädt «Herunterladen» per downloadFile, kein location.assign', async () => {
    haRahmenMitNavigation()
    appleMobil.mockReturnValue(true)
    render(<DiagnosePaketDialog isOpen onClose={() => {}} anlageId={7} />)
    fireEvent.click(await screen.findByRole('button', { name: /Herunterladen/ }))
    await waitFor(() => expect(download).toHaveBeenCalledWith(URL_A, 'eedc_diagnose_Haus_2026-11-15.zip'))
    expect(assign).not.toHaveBeenCalled()
    expect(pruefen).not.toHaveBeenCalled()
  })

  it('nach gueltig_s erscheint «Neu zusammenstellen»', async () => {
    bereitstellen.mockResolvedValueOnce(paket({ gueltig_s: 0.05 }))
    render(<DiagnosePaketDialog isOpen onClose={() => {}} anlageId={7} />)
    expect(await screen.findByRole('button', { name: /Herunterladen/ })).toBeTruthy()
    expect(await screen.findByText(TEXT_ABGELAUFEN)).toBeTruthy()
    expect(screen.queryByRole('button', { name: /Herunterladen/ })).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: /Neu zusammenstellen/ }))
    expect(await screen.findByRole('button', { name: /Herunterladen/ })).toBeTruthy()
    expect(bereitstellen).toHaveBeenCalledTimes(2)
  })

  it('nennt Teilfehler', async () => {
    bereitstellen.mockResolvedValueOnce(paket({ teilfehler: ['kanal_statistik', 'lage.ha_abgleich'] }))
    render(<DiagnosePaketDialog isOpen onClose={() => {}} anlageId={7} />)
    expect(await screen.findByText(
      'Ein Teil fehlt im Paket (kanal_statistik, lage.ha_abgleich). Das Paket ist trotzdem brauchbar; der Grund steht darin.',
    )).toBeTruthy()
  })

  it('vergleicht keine Größen', async () => {
    // Ingress sendet ab 10 MB `chunked` ohne `Content-Length`: der Client gibt nur Adresse und Dateiname weiter.
    bereitstellen.mockResolvedValueOnce(paket({ bytes: 21_000_000, megabyte: 21, versandweg: 'freigabe_link' }))
    render(<DiagnosePaketDialog isOpen onClose={() => {}} anlageId={7} />)
    fireEvent.click(await screen.findByRole('button', { name: /Herunterladen/ }))
    await waitFor(() => expect(download).toHaveBeenCalledTimes(1))
    expect(download.mock.calls[0]).toEqual([URL_A, 'eedc_diagnose_Haus_2026-11-15.zip'])
    expect(screen.queryByText('Die Datei konnte nicht heruntergeladen werden.')).toBeNull()
  })

  // Abschluss-Meldung (Lab rc36): Kreisel, «Heruntergeladen: …» bzw. Hintergrund-Satz, «Schließen».
  const FERTIG = 'Heruntergeladen: eedc_diagnose_Haus_2026-11-15.zip'
  const HINTERGRUND = 'Der Download läuft im Hintergrund. Die Datei eedc_diagnose_Haus_2026-11-15.zip liegt gleich in '
    + 'deinen Downloads.'
  const knopfHerunterladen = async () => await screen.findByRole('button', { name: /Herunterladen/ }) as HTMLButtonElement
  /** Der Knopf «Schließen» unter dem Text (das Kreuz des Modals trägt nur `aria-label="Schließen"`, keinen Text). */
  const schliessenKnopf = () => screen.queryByText('Schließen', { selector: 'button' })
  /** Navigationsweg mit Uhr in der Hand des Tests (die Zeit läuft mit, damit `findBy…` weiter wartet). */
  function navigationMitUhr() {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    haRahmenMitNavigation()
  }

  it('Kreisel im Knopf und gesperrt, solange der Download läuft', async () => {
    let fertig: () => void = () => {}
    download.mockImplementationOnce(() => new Promise<void>((r) => { fertig = r }))
    render(<DiagnosePaketDialog isOpen onClose={() => {}} anlageId={7} />)
    const knopf = await knopfHerunterladen()
    expect(knopf.querySelector('.animate-spin')).toBeNull()
    fireEvent.click(knopf)
    await waitFor(() => expect(knopf.disabled).toBe(true))
    expect(knopf.querySelector('.animate-spin')).not.toBeNull()
    fireEvent.click(knopf)
    expect(download).toHaveBeenCalledTimes(1)
    expect(screen.queryByTestId('download-fertig')).toBeNull()
    fertig()
    expect((await screen.findByTestId('download-fertig')).textContent).toBe(FERTIG)
    expect(knopf.disabled).toBe(false)
    expect(knopf.querySelector('.animate-spin')).toBeNull()
    fireEvent.click(knopf)
    await waitFor(() => expect(download).toHaveBeenCalledTimes(2))
  })

  it('Navigationsweg: Zähler steigt ⇒ «Heruntergeladen: …»', async () => {
    navigationMitUhr()
    pruefen.mockResolvedValueOnce(stand(3)).mockResolvedValueOnce(stand(3)).mockResolvedValue(stand(4))
    render(<DiagnosePaketDialog isOpen onClose={() => {}} anlageId={7} />)
    const knopf = await knopfHerunterladen()
    fireEvent.click(knopf)
    await waitFor(() => expect(assign).toHaveBeenCalledWith(URL_A))
    expect(knopf.disabled).toBe(true)
    expect(knopf.querySelector('.animate-spin')).not.toBeNull()
    await vi.advanceTimersByTimeAsync(ABFRAGE_MS)
    expect(screen.queryByTestId('download-fertig')).toBeNull()
    expect(knopf.disabled).toBe(true)
    await vi.advanceTimersByTimeAsync(ABFRAGE_MS)
    expect((await screen.findByTestId('download-fertig')).textContent).toBe(FERTIG)
    expect(pruefen).toHaveBeenCalledTimes(3)
    expect(knopf.disabled).toBe(false)
    expect(screen.queryByTestId('download-hintergrund')).toBeNull()
    await vi.advanceTimersByTimeAsync(WARTEZEIT_MS)
    expect(pruefen).toHaveBeenCalledTimes(3)                       // nach dem Ende keine Abfrage mehr
  })

  it('Navigationsweg: Zähler steigt nicht bis zum Ende der Wartezeit ⇒ Hintergrund-Satz', async () => {
    navigationMitUhr()
    pruefen.mockResolvedValue(stand(0))
    render(<DiagnosePaketDialog isOpen onClose={() => {}} anlageId={7} />)
    const knopf = await knopfHerunterladen()
    fireEvent.click(knopf)
    await waitFor(() => expect(assign).toHaveBeenCalledWith(URL_A))
    await vi.advanceTimersByTimeAsync(WARTEZEIT_MS - ABFRAGE_MS)
    expect(screen.queryByTestId('download-hintergrund')).toBeNull()
    expect(knopf.disabled).toBe(true)
    await vi.advanceTimersByTimeAsync(2 * ABFRAGE_MS)
    expect((await screen.findByTestId('download-hintergrund')).textContent).toBe(HINTERGRUND)
    expect(screen.queryByTestId('download-fertig')).toBeNull()
    expect(knopf.disabled).toBe(false)
    const abrufe = pruefen.mock.calls.length
    expect(abrufe).toBeLessThanOrEqual(1 + WARTEZEIT_MS / ABFRAGE_MS + 1)
    await vi.advanceTimersByTimeAsync(WARTEZEIT_MS)
    expect(pruefen).toHaveBeenCalledTimes(abrufe)
  })

  it('Navigationsweg: 404 während des Wartens beendet still', async () => {
    navigationMitUhr()
    pruefen.mockResolvedValueOnce(stand(0)).mockResolvedValue(NICHT_BEREIT)
    render(<DiagnosePaketDialog isOpen onClose={() => {}} anlageId={7} />)
    const knopf = await knopfHerunterladen()
    fireEvent.click(knopf)
    await waitFor(() => expect(assign).toHaveBeenCalledTimes(1))
    await vi.advanceTimersByTimeAsync(ABFRAGE_MS)
    await waitFor(() => expect(knopf.disabled).toBe(false))
    expect(pruefen).toHaveBeenCalledTimes(2)
    expect(screen.queryByTestId('download-fertig')).toBeNull()
    expect(screen.queryByTestId('download-hintergrund')).toBeNull()
    expect(screen.queryByText(TEXT_ABGELAUFEN_NEU)).toBeNull()
    expect(bereitstellen).toHaveBeenCalledTimes(1)
  })

  it('Navigationsweg: 404 beim ersten Prüfabruf ⇒ neu bereitstellen, kein location.assign, keine Meldung', async () => {
    haRahmenMitNavigation()
    pruefen.mockResolvedValueOnce(NICHT_BEREIT)
    render(<DiagnosePaketDialog isOpen onClose={() => {}} anlageId={7} />)
    fireEvent.click(await knopfHerunterladen())
    expect(await screen.findByText(TEXT_ABGELAUFEN_NEU)).toBeTruthy()
    await waitFor(() => expect(bereitstellen).toHaveBeenCalledTimes(2))
    expect((await knopfHerunterladen()).disabled).toBe(false)
    expect(assign).not.toHaveBeenCalled()
    expect(screen.queryByTestId('download-fertig')).toBeNull()
    expect(schliessenKnopf()).toBeNull()
  })

  it('Blob-Weg (iPhone-Kennung im HA-Rahmen) ⇒ «Heruntergeladen: …» ohne Abfrage', async () => {
    haRahmenMitNavigation()
    appleMobil.mockReturnValue(true)
    render(<DiagnosePaketDialog isOpen onClose={() => {}} anlageId={7} />)
    fireEvent.click(await knopfHerunterladen())
    expect((await screen.findByTestId('download-fertig')).textContent).toBe(FERTIG)
    expect(download).toHaveBeenCalledTimes(1)
    expect(pruefen).not.toHaveBeenCalled()
    expect(assign).not.toHaveBeenCalled()
  })

  it('«Schließen» erscheint erst nach dem Download und schließt; «Herunterladen» bleibt daneben', async () => {
    const onClose = vi.fn()
    render(<DiagnosePaketDialog isOpen onClose={onClose} anlageId={7} />)
    fireEvent.click(await knopfHerunterladen())
    expect(schliessenKnopf()).toBeNull()
    await screen.findByTestId('download-fertig')
    expect(screen.getByRole('button', { name: /Herunterladen/ })).toBeTruthy()
    fireEvent.click(schliessenKnopf()!)
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('«Schließen» auch nach dem Hintergrund-Satz', async () => {
    navigationMitUhr()
    const onClose = vi.fn()
    render(<DiagnosePaketDialog isOpen onClose={onClose} anlageId={7} />)
    fireEvent.click(await knopfHerunterladen())
    await waitFor(() => expect(assign).toHaveBeenCalledTimes(1))
    await vi.advanceTimersByTimeAsync(WARTEZEIT_MS + ABFRAGE_MS)
    await screen.findByTestId('download-hintergrund')
    fireEvent.click(schliessenKnopf()!)
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('kein automatisches Schließen: Versand-Satz und Hinweis bleiben lesbar', async () => {
    navigationMitUhr()
    const onClose = vi.fn()
    pruefen.mockResolvedValueOnce(stand(0)).mockResolvedValue(stand(1))
    render(<DiagnosePaketDialog isOpen onClose={onClose} anlageId={7} />)
    fireEvent.click(await knopfHerunterladen())
    await vi.advanceTimersByTimeAsync(ABFRAGE_MS)
    await screen.findByTestId('download-fertig')
    await vi.advanceTimersByTimeAsync(5 * WARTEZEIT_MS)
    expect(onClose).not.toHaveBeenCalled()
    expect(screen.getByTestId('versand-satz')).toBeTruthy()
    expect(screen.getByTestId('versand-hinweis').textContent).toBe(VERSAND_HINWEIS)
    expect(screen.getByTestId('download-fertig').textContent).toBe(FERTIG)
  })

  it('Abbau während des Wartens beendet die Abfrage (kein Zeitgeber bleibt)', async () => {
    navigationMitUhr()
    const { unmount } = render(<DiagnosePaketDialog isOpen onClose={() => {}} anlageId={7} />)
    fireEvent.click(await knopfHerunterladen())
    await waitFor(() => expect(assign).toHaveBeenCalledTimes(1))
    await vi.advanceTimersByTimeAsync(ABFRAGE_MS)
    const abrufe = pruefen.mock.calls.length
    unmount()
    expect(vi.getTimerCount()).toBe(0)
    await vi.advanceTimersByTimeAsync(WARTEZEIT_MS)
    expect(pruefen).toHaveBeenCalledTimes(abrufe)
  })

  it('Schließen des Fensters während des Wartens beendet die Abfrage', async () => {
    navigationMitUhr()
    const { rerender } = render(<DiagnosePaketDialog isOpen onClose={() => {}} anlageId={7} />)
    fireEvent.click(await knopfHerunterladen())
    await waitFor(() => expect(assign).toHaveBeenCalledTimes(1))
    rerender(<DiagnosePaketDialog isOpen={false} onClose={() => {}} anlageId={7} />)
    const abrufe = pruefen.mock.calls.length
    await vi.advanceTimersByTimeAsync(WARTEZEIT_MS)
    expect(pruefen).toHaveBeenCalledTimes(abrufe)
  })

  it('keine Meldung bei 404 auf dem Blob-Weg; nach Erfolg verschwindet sie beim nächsten Fehler', async () => {
    const { DownloadFehler } = await import('../../lib/download')
    download.mockRejectedValueOnce(new DownloadFehler('Diagnose-Paket nicht (mehr) bereit', 404))
    render(<DiagnosePaketDialog isOpen onClose={() => {}} anlageId={7} />)
    fireEvent.click(await knopfHerunterladen())
    expect(await screen.findByText(TEXT_ABGELAUFEN_NEU)).toBeTruthy()
    await waitFor(() => expect(bereitstellen).toHaveBeenCalledTimes(2))
    expect(screen.queryByTestId('download-fertig')).toBeNull()

    fireEvent.click(await knopfHerunterladen())
    expect((await screen.findByTestId('download-fertig')).textContent).toBe(FERTIG)

    download.mockRejectedValueOnce(new DownloadFehler('HTTP 500', 500))
    fireEvent.click(screen.getByRole('button', { name: /Herunterladen/ }))
    expect(await screen.findByText('Die Datei konnte nicht heruntergeladen werden.')).toBeTruthy()
    expect(screen.queryByTestId('download-fertig')).toBeNull()
  })

  it('keine Meldung bei anderem Fehler', async () => {
    const { DownloadFehler } = await import('../../lib/download')
    download.mockRejectedValueOnce(new DownloadFehler('HTTP 500', 500))
    render(<DiagnosePaketDialog isOpen onClose={() => {}} anlageId={7} />)
    fireEvent.click(await knopfHerunterladen())
    expect(await screen.findByText('Die Datei konnte nicht heruntergeladen werden.')).toBeTruthy()
    expect(screen.queryByTestId('download-fertig')).toBeNull()
    expect(schliessenKnopf()).toBeNull()
  })

  it('Meldung verschwindet beim Ablauf und bleibt nach «Neu zusammenstellen» weg', async () => {
    bereitstellen.mockResolvedValueOnce(paket({ gueltig_s: 0.5 }))
    render(<DiagnosePaketDialog isOpen onClose={() => {}} anlageId={7} />)
    fireEvent.click(await knopfHerunterladen())
    expect((await screen.findByTestId('download-fertig')).textContent).toBe(FERTIG)
    expect(await screen.findByText(TEXT_ABGELAUFEN, undefined, { timeout: 3000 })).toBeTruthy()
    expect(screen.queryByTestId('download-fertig')).toBeNull()
    expect(schliessenKnopf()).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: /Neu zusammenstellen/ }))
    expect(await knopfHerunterladen()).toBeTruthy()
    expect(bereitstellen).toHaveBeenCalledTimes(2)
    expect(screen.queryByTestId('download-fertig')).toBeNull()
  })

  it('keine Ersatzweg-Zeile', async () => {
    haRahmenMitNavigation()
    const { container } = render(<DiagnosePaketDialog isOpen onClose={() => {}} anlageId={7} />)
    await screen.findByText('Drin ist:')
    const text = document.body.textContent ?? container.textContent ?? ''
    expect(text).not.toMatch(/Kopieren|im Browser öffnen|Speichert die App/)
    expect(screen.queryByRole('textbox')).toBeNull()
  })
})
