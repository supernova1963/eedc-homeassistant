/**
 * Diagnose-Paket v4 (Konzept «Diagnose-Paket v4» §6, Bauplan §3.4/§5 S2) — Dialog im Kopf des Daten-Checkers.
 *
 * Beim Öffnen stellt eedc das Paket bereit (`…/bereitstellen`, synchron, Variante A nach S0): eine ZIP-Datei mit dem
 * Datenauszug dieser Anlage liegt danach 15 Minuten (`gueltig_s`) unter einer Marke bereit. Der Dialog zeigt die
 * Inhaltsliste mit den Zahlen dieses Pakets, die Größe und den Versandweg; «Herunterladen» holt die fertige Datei.
 *
 * Weg des Herunterladens (Entscheid Master nach S0, 15.11.2026):
 * - außerhalb von Home Assistant und **im HA-Rahmen auf iPhone/iPad** über `downloadFile` (fetch + Blob) — in der
 *   iPhone-App zeigt eine direkte Navigation die Datei als Seite und lässt die Ansicht hängen;
 * - **im HA-Rahmen sonst** (Desktop, Android) erst ein Prüfabruf (`&pruefen=1`, 204/404), dann `window.location.assign` —
 *   die Route sendet `Content-Disposition: attachment`, die Seite bleibt stehen. Ohne Prüfabruf ersetzte ein 404
 *   (abgelaufen, ersetzt, Neustart) die eedc-Seite ohne Text (K8).
 * Der Client vergleicht keine Größen (Ingress sendet ab 10 MB `chunked` statt `Content-Length`).
 * Nach dem Auslösen steht unter dem Knopf «Download gestartet: <Dateiname>» (Lab rc35, Android: ohne Rückmeldung
 * wirkte der Knopf ohne Funktion); während des Auslösens ist der Knopf gesperrt.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { Download, RefreshCw } from 'lucide-react'
import { Alert, Button, LoadingSpinner, Modal } from '../ui'
import {
  datenCheckerApi, diagnosePaketPruefen, diagnosePaketUrl, type DiagnosePaketBereit,
} from '../../api/datenChecker'
import { DownloadFehler, downloadFile, istAppleMobil, istImHaRahmen } from '../../lib/download'
import { mitAnzahl } from '../../lib/plural'
import { fmtZahl } from '../../lib/einheiten'

export const TEXT_ABGELAUFEN_NEU = 'Das Paket ist abgelaufen — es wird neu zusammengestellt.'
export const TEXT_ABGELAUFEN = 'Das Paket ist abgelaufen.'

interface Props {
  isOpen: boolean
  onClose: () => void
  anlageId: number
}

/** Im HA-Rahmen lädt die Seite per Navigation — außer auf iPhone/iPad, dort nur der Blob-Weg (S0). */
function perNavigation(): boolean {
  return istImHaRahmen() && !istAppleMobil()
}

/** Löst den Download aus; `false` heißt: die Marke ist nicht mehr bereit (Prüfabruf 404, Navigationsweg). */
async function ausloesen(anlageId: number, paket: DiagnosePaketBereit): Promise<boolean> {
  const url = diagnosePaketUrl(anlageId, paket.marke)
  if (perNavigation()) {
    if (!(await diagnosePaketPruefen(anlageId, paket.marke))) return false
    window.location.assign(url)
    return true
  }
  await downloadFile(url, paket.dateiname)
  return true
}

function Inhaltsliste({ paket }: { paket: DiagnosePaketBereit }) {
  const i = paket.inhalt
  return (
    <div className="text-sm text-gray-700 dark:text-gray-300 space-y-1">
      <p className="font-medium">Drin ist:</p>
      <ul className="list-disc pl-5 space-y-1">
        <li>Standort: Ort, PLZ, Koordinaten auf zwei Nachkommastellen gerundet</li>
        <li>
          Anlagenname, {mitAnzahl(i.geraete, 'Gerät', 'Geräte')}, {mitAnzahl(i.tarife, 'Tarif', 'Tarife')}, Kosten und
          steuerliche Einordnung
        </li>
        <li>
          {mitAnzahl(i.zuordnungen, 'Zuordnung', 'Zuordnungen')} mit Entity-Namen und MQTT-Topics — sie können
          Seriennummern tragen
        </li>
        <li>
          {fmtZahl(i.monatswerte)} Monatswerte, {fmtZahl(i.tageswerte)} Tageswerte, {fmtZahl(i.stundenwerte)} Stundenwerte —
          Stundenwerte zeigen, wann jemand zu Hause ist
        </li>
        <li>Eigene Notizen und Beschreibungen ({fmtZahl(i.notizen)})</li>
        <li>
          Protokolle und Prüfergebnisse der ganzen Installation ({fmtZahl(i.protokollzeilen)} Zeilen,{' '}
          {fmtZahl(i.befunde)} Befunde) — mit Netzwerkadressen von Broker und Geräten und Gerätekennungen wie
          Seriennummern; bei mehreren Anlagen auch Zeilen zu den anderen
        </li>
      </ul>
      <p>Nicht drin: Zugangsdaten, Straße, Fotos, Infothek, Kontakt- und Vertragsangaben aus den Geräte-Stammdaten.</p>
    </div>
  )
}

function Versand({ paket }: { paket: DiagnosePaketBereit }) {
  return (
    <div className="text-sm text-gray-700 dark:text-gray-300 space-y-1">
      <p>Größe: {fmtZahl(paket.megabyte, 1)} MB</p>
      <p data-testid="versand-satz">
        {paket.versandweg === 'email'
          ? 'Schick die Datei per E-Mail an die Adresse aus unserer Antwort — nicht öffentlich posten.'
          : 'Die Datei ist zu groß für eine E-Mail: lege sie in einen Cloud-Speicher (etwa Dropbox oder Google Drive) und schick den Freigabe-Link an die Adresse aus unserer Antwort — nicht öffentlich posten.'}
      </p>
      <p data-testid="versand-hinweis">
        eedc verschickt die Datei nicht — den Weg zu uns wählst du. Die Datei ist nicht verschlüsselt.
      </p>
    </div>
  )
}

export default function DiagnosePaketDialog({ isOpen, onClose, anlageId }: Props) {
  const [paket, setPaket] = useState<DiagnosePaketBereit | null>(null)
  const [laedt, setLaedt] = useState(false)
  const [fehler, setFehler] = useState<string | null>(null)
  const [downloadFehler, setDownloadFehler] = useState<string | null>(null)
  const [hinweis, setHinweis] = useState<string | null>(null)
  const [abgelaufen, setAbgelaufen] = useState(false)
  const [laeuft, setLaeuft] = useState(false)
  const [gestartet, setGestartet] = useState<string | null>(null)
  // Laufnummer: nur die Antwort des jüngsten Bereitstellens im offenen Dialog zählt (Schließen/erneutes Öffnen).
  const lauf = useRef(0)
  const zeitgeber = useRef<ReturnType<typeof setTimeout> | null>(null)

  const zeitgeberAus = () => {
    if (zeitgeber.current !== null) clearTimeout(zeitgeber.current)
    zeitgeber.current = null
  }

  const bereitstellen = useCallback(async () => {
    zeitgeberAus()
    setLaedt(true)
    setFehler(null)
    setDownloadFehler(null)
    setGestartet(null)
    setAbgelaufen(false)
    setPaket(null)
    const nr = ++lauf.current
    const gilt = () => nr === lauf.current
    try {
      const p = await datenCheckerApi.diagnosePaketBereitstellen(anlageId)
      if (!gilt()) return
      setPaket(p)
      zeitgeber.current = setTimeout(() => { if (gilt()) setAbgelaufen(true) }, p.gueltig_s * 1000)
    } catch (e) {
      if (!gilt()) return
      const detail = e instanceof Error && e.message ? ` ${e.message}` : ''
      setFehler(`Das Diagnose-Paket konnte nicht erstellt werden.${detail}`)
    } finally {
      if (gilt()) setLaedt(false)
    }
  }, [anlageId])

  useEffect(() => {
    if (!isOpen) return
    setHinweis(null)
    void bereitstellen()
    return () => {
      lauf.current += 1
      zeitgeberAus()
    }
  }, [isOpen, bereitstellen])

  const neuWeilAbgelaufen = () => {
    setHinweis(TEXT_ABGELAUFEN_NEU)
    void bereitstellen()
  }

  const herunterladen = async () => {
    if (!paket || laeuft) return
    setHinweis(null)
    setDownloadFehler(null)
    setGestartet(null)
    setLaeuft(true)
    const nr = lauf.current
    try {
      if (!(await ausloesen(anlageId, paket))) neuWeilAbgelaufen()
      else if (nr === lauf.current) setGestartet(paket.dateiname)
    } catch (e) {
      if (e instanceof DownloadFehler && e.status === 404) neuWeilAbgelaufen()
      else setDownloadFehler('Die Datei konnte nicht heruntergeladen werden.')
    } finally {
      setLaeuft(false)
    }
  }

  const neuZusammenstellen = () => {
    setHinweis(null)
    void bereitstellen()
  }

  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Diagnose-Paket" size="xl">
      <div className="space-y-3">
        <p className="text-sm text-gray-600 dark:text-gray-400">
          Lade das Paket erst herunter, wenn wir dich in unserer Antwort darum bitten. Es enthält die Daten dieser Anlage,
          damit wir deine Frage nachvollziehen können.
        </p>
        {hinweis && <Alert type="info">{hinweis}</Alert>}
        {fehler && <Alert type="error">{fehler}</Alert>}
        {laedt && <LoadingSpinner text="Diagnose-Paket wird zusammengestellt …" />}
        {paket && !laedt && (
          <>
            <Inhaltsliste paket={paket} />
            {paket.teilfehler.length > 0 && (
              <Alert type="warning">
                Ein Teil fehlt im Paket ({paket.teilfehler.join(', ')}). Das Paket ist trotzdem brauchbar; der Grund steht
                darin.
              </Alert>
            )}
            <Versand paket={paket} />
          </>
        )}
        {downloadFehler && <Alert type="error">{downloadFehler}</Alert>}
        {abgelaufen && <p className="text-sm text-gray-600 dark:text-gray-400">{TEXT_ABGELAUFEN}</p>}
        <div className="flex flex-wrap justify-end gap-2">
          {!laedt && (fehler || abgelaufen) && (
            <Button variant="secondary" size="sm" onClick={neuZusammenstellen}>
              <RefreshCw className="h-4 w-4 mr-2" />
              Neu zusammenstellen
            </Button>
          )}
          {!laedt && paket && !abgelaufen && (
            <Button size="sm" onClick={herunterladen} disabled={laeuft}>
              <Download className="h-4 w-4 mr-2" />
              Herunterladen
            </Button>
          )}
        </div>
        {gestartet && !abgelaufen && (
          <p data-testid="download-gestartet" className="text-sm text-gray-600 dark:text-gray-400 text-right">
            Download gestartet: {gestartet}
          </p>
        )}
      </div>
    </Modal>
  )
}
