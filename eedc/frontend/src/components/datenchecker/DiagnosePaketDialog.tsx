/**
 * Diagnose-Paket (Etappe E1, Konzept Daten-Checker §8.3) — Dialog im Kopf des Daten-Checkers.
 *
 * Zeigt die Kopieren-Fassung (höchstens 20 KB) in einem bearbeitbaren Textfeld: der Anwender kann schwärzen, was er
 * nicht teilen will, und kopiert dann genau diesen Text. «Als Datei herunterladen» holt die ungekürzte Datei-Fassung:
 * außerhalb von Home Assistant über `lib/download.ts` (fetch + Blob), **im HA-Rahmen** (E5.7 L4) per direkter Navigation
 * auf die Datei-Adresse — die Route sendet `Content-Disposition: attachment`, die Seite bleibt stehen; Blob-Downloads kamen
 * in der Companion-App nicht an (Gernot, Lab rc29). Darunter immer der Hinweis auf das Kopieren.
 */
import { useEffect, useState } from 'react'
import { Copy, Download } from 'lucide-react'
import { Alert, Button, LoadingSpinner, Modal, Textarea } from '../ui'
import { datenCheckerApi, diagnosePaketUrl } from '../../api/datenChecker'
import { useCopyFeedback } from '../../hooks/useCopyFeedback'
import { downloadFile, istImHaRahmen } from '../../lib/download'

/** E5.7 L4: der Weg, wenn die App keine Datei speichert (Companion-App, manche Foren nehmen keine Datei). */
export const DATEI_HINWEIS = 'Speichert die App keine Datei: Kopieren und in eine Notiz einfügen.'

export const DIAGNOSE_HINWEIS =
  'Enthält Entity-Namen, Standort und Preise — entferne, was du nicht teilen willst. Zugangsdaten enthält es nie.'

interface Props {
  isOpen: boolean
  onClose: () => void
  anlageId: number
}

export default function DiagnosePaketDialog({ isOpen, onClose, anlageId }: Props) {
  const [text, setText] = useState('')
  const [dateiname, setDateiname] = useState('')
  const [laedt, setLaedt] = useState(false)
  const [fehler, setFehler] = useState<string | null>(null)
  const { istKopiert, kopiere } = useCopyFeedback()

  useEffect(() => {
    if (!isOpen) return
    let aktiv = true
    setLaedt(true)
    setFehler(null)
    datenCheckerApi.diagnosePaket(anlageId, 'kopie')
      .then(p => {
        if (!aktiv) return
        setText(p.text)
        setDateiname(p.dateiname)
      })
      .catch(e => { if (aktiv) setFehler(e instanceof Error ? e.message : 'Das Diagnose-Paket konnte nicht erstellt werden') })
      .finally(() => { if (aktiv) setLaedt(false) })
    return () => { aktiv = false }
  }, [isOpen, anlageId])

  const herunterladen = async () => {
    setFehler(null)
    if (istImHaRahmen()) {
      window.location.assign(diagnosePaketUrl(anlageId, 'datei'))
      return
    }
    try {
      await downloadFile(diagnosePaketUrl(anlageId, 'datei'), dateiname || `eedc_diagnose_${anlageId}.md`)
    } catch (e) {
      setFehler(e instanceof Error ? e.message : 'Die Datei konnte nicht heruntergeladen werden')
    }
  }

  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Diagnose-Paket" size="xl">
      <div className="space-y-3">
        <p className="text-sm text-gray-600 dark:text-gray-400">{DIAGNOSE_HINWEIS}</p>
        {fehler && <Alert type="error">{fehler}</Alert>}
        {laedt ? (
          <LoadingSpinner text="Diagnose-Paket wird erstellt …" />
        ) : (
          <Textarea
            aria-label="Diagnose-Paket"
            value={text}
            onChange={e => setText(e.target.value)}
            rows={16}
            spellCheck={false}
            className="font-mono text-xs"
          />
        )}
        <div className="flex flex-wrap justify-end gap-2">
          <Button variant="secondary" size="sm" onClick={herunterladen} disabled={laedt}>
            <Download className="h-4 w-4 mr-2" />
            Als Datei herunterladen
          </Button>
          <Button size="sm" onClick={() => kopiere(text)} disabled={laedt || !text}>
            <Copy className="h-4 w-4 mr-2" />
            {istKopiert() ? 'Kopiert' : 'Kopieren'}
          </Button>
        </div>
        <p className="text-right text-xs text-gray-500 dark:text-gray-400" data-testid="datei-hinweis">{DATEI_HINWEIS}</p>
      </div>
    </Modal>
  )
}
