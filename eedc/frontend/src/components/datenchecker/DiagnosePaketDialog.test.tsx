/**
 * Diagnose-Paket-Dialog v4 (Bauplan §5 S2 Schritt 3): Bereitstellen beim Öffnen (Variante A, synchron), Inhaltsliste,
 * Versand-Satz nach `versandweg`, Weg des Herunterladens (außerhalb des HA-Rahmens und auf dem iPhone `downloadFile`,
 * im HA-Rahmen sonst Prüfabruf + Navigation), abgelaufene Marke (K8), `gueltig_s`, Teilfehler.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import DiagnosePaketDialog, { TEXT_ABGELAUFEN, TEXT_ABGELAUFEN_NEU } from './DiagnosePaketDialog'
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
    pruefen.mockReset().mockResolvedValue(true)
    vorherLocation = window.location
    assign = vi.fn()
  })

  afterEach(() => {
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
    unmount()
    bereitstellen.mockResolvedValue(paket({ versandweg: 'freigabe_link', bytes: 12_000_000, megabyte: 12 }))
    render(<DiagnosePaketDialog isOpen onClose={() => {}} anlageId={7} />)
    expect((await screen.findByTestId('versand-satz')).textContent).toBe(
      'Die Datei ist zu groß für eine E-Mail: lege sie in einen Cloud-Speicher (etwa Dropbox oder Google Drive) und '
      + 'schick den Freigabe-Link an die Adresse aus unserer Antwort — nicht öffentlich posten.')
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

  it('im HA-Rahmen prüft zuerst und navigiert bei 204', async () => {
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
    pruefen.mockResolvedValueOnce(false)
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

  it('keine Ersatzweg-Zeile', async () => {
    haRahmenMitNavigation()
    const { container } = render(<DiagnosePaketDialog isOpen onClose={() => {}} anlageId={7} />)
    await screen.findByText('Drin ist:')
    const text = document.body.textContent ?? container.textContent ?? ''
    expect(text).not.toMatch(/Kopieren|im Browser öffnen|Speichert die App/)
    expect(screen.queryByRole('textbox')).toBeNull()
  })
})
