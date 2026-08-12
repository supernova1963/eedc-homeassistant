import { useEffect, useState } from 'react'
import { Alert } from '../ui'
import { portalImportApi, type ManuelleWerteInfo } from '../../api/portalImport'

/**
 * Sagt VOR dem Import, wie viel Handarbeit „Bestehende Monate überschreiben"
 * ersetzen würde.
 *
 * **Warum es das gibt.** Bis zum 2026-08-12 schützte die Provenance-Hierarchie
 * manuell gepflegte Werte auch dann, wenn der Anwender den Haken ausdrücklich
 * gesetzt hatte — der Import meldete hinterher „6 Felder durch manuell
 * gepflegte Werte geschützt" und tat damit etwas anderes als angeordnet.
 * Seitdem gewinnt der Haken. Das ist nur vertretbar, wenn eedc vorher sagt,
 * was es kostet: Ohne diesen Hinweis wäre aus einer Bevormundung ein stiller
 * Datenverlust geworden.
 *
 * Ohne Haken bleibt Handarbeit unangetastet (FrodoVDR #251) — dann zeigt die
 * Komponente nichts.
 *
 * **Eine Komponente für beide Wizards** (Cloud + Portal): derselbe Satz an
 * zwei Stellen wäre die klassische Drift, sobald ihn jemand präzisiert.
 */
export function ManuelleWerteHinweis({
  anlageId,
  perioden,
  aktiv,
}: {
  anlageId: number | null
  /** Gewählte Monate als `YYYY-MM`. */
  perioden: string[]
  /** Der Überschreiben-Haken. Ist er aus, wird nichts geprüft und nichts gezeigt. */
  aktiv: boolean
}) {
  const [info, setInfo] = useState<ManuelleWerteInfo | null>(null)

  const schluessel = perioden.join(',')
  useEffect(() => {
    if (!aktiv || !anlageId || perioden.length === 0) {
      setInfo(null)
      return
    }
    let abgebrochen = false
    portalImportApi
      .getManuelleWerte(anlageId, perioden)
      .then((res) => {
        if (!abgebrochen) setInfo(res)
      })
      // Ein fehlgeschlagener Hinweis darf den Import nicht blockieren — er
      // ist eine Auskunft, keine Vorbedingung.
      .catch(() => {
        if (!abgebrochen) setInfo(null)
      })
    return () => {
      abgebrochen = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [anlageId, schluessel, aktiv])

  if (!aktiv || !info?.betroffen) return null

  const felder = info.felder === 1 ? '1 Wert' : `${info.felder} Werte`
  const monate = info.monate === 1 ? 'einem Monat' : `${info.monate} Monaten`

  return (
    <Alert type="warning" className="mt-3">
      <div className="font-medium">
        {felder} in {monate} wurden von Hand gepflegt und werden ersetzt.
      </div>
      {info.beispiele.length > 0 && (
        <div className="mt-1 text-sm">
          Zum Beispiel: {info.beispiele.join(' · ')}
          {info.felder > info.beispiele.length && ' …'}
        </div>
      )}
      <div className="mt-1 text-sm">
        Ohne den Haken bleiben diese Werte erhalten; der Import ergänzt dann nur,
        was noch fehlt.
      </div>
    </Alert>
  )
}
