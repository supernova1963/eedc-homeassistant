/**
 * KorrekturFortschritt — Fortschritt eines Korrektur-Laufs (Sensorwechsel mit Grund, Bauplan §10 Nr. 40, §11 Nr. 46/50;
 * Sitzung 3b und Korrekturrunde 3b-K).
 *
 * Liest `GET /datenquellen/{anlage}/korrektur-lauf/{lauf}` alle paar Sekunden, solange der Lauf `laeuft`; zeigt nur die
 * Backend-Zahlen (Tage gesamt, erledigt, Tage mit Fehler) — der Client rechnet nichts. Steht an der Datenquellen-Fläche
 * (nach einer Korrektur im Dialog und für jeden laufenden Lauf beim Laden) und am Ergebnis der Werkbank-Operation «Werte vor
 * dem Sensorbeginn verwerfen». Ein Abruf-Fehler hält das Nachfragen nicht an: es fragt mit wachsendem Abstand weiter,
 * höchstens `FORTSCHRITT_VERSUCHE` Mal hintereinander; ein unbekannter Lauf (404) beendet es sofort.
 */
import { useEffect, useState } from 'react'
import { Alert } from '../ui'
import { ApiError } from '../../api/client'
import { datenquellenApi, type KorrekturLaufStand } from '../../api/datenquellen'
import { fmtZahl } from '../../lib/einheiten'

export const FORTSCHRITT_INTERVALL_MS = 3000
/** Höchstens so viele Abruf-Fehler hintereinander, dann hört der Fortschritt auf zu fragen. */
export const FORTSCHRITT_VERSUCHE = 5
export const SATZ_FUELLEN_OFFEN =
  'Das Füllen aus Home Assistant steht noch aus — eedc versucht es jede Stunde und nach jedem Start von selbst wieder, ' +
  'bis es gelingt.'

/** Der Satz zum Stand — nur Anzeige der Backend-Zahlen. */
export function fortschrittSatz(z: KorrekturLaufStand): string {
  const fehler = z.fehler.filter((f) => f.tag != null).length
  const mitFehler = fehler > 0 ? ` ${fmtZahl(fehler)} Tage konnten nicht neu gebildet werden.` : ''
  if (z.status === 'fertig') {
    return z.tage > 0 ? `Korrektur abgeschlossen, ${fmtZahl(z.tage)} Tage bearbeitet.${mitFehler}` : 'Korrektur abgeschlossen.'
  }
  if (z.tage === 0) return 'Korrektur läuft …'
  return `Tage werden im Hintergrund neu gebildet: ${fmtZahl(z.erledigt)} von ${fmtZahl(z.tage)}.${mitFehler}`
}

export default function KorrekturFortschritt({ anlageId, lauf, label }: { anlageId: number; lauf: string; label?: string }) {
  const [stand, setStand] = useState<KorrekturLaufStand | null>(null)

  useEffect(() => {
    let aus = false
    let fehlschlaege = 0
    let timer: ReturnType<typeof setTimeout> | undefined
    const holen = () => {
      datenquellenApi.korrekturLauf(anlageId, lauf)
        .then((z) => {
          if (aus) return
          fehlschlaege = 0
          setStand(z)
          if (z.status === 'laeuft') timer = setTimeout(holen, FORTSCHRITT_INTERVALL_MS)
        })
        .catch((e) => {
          if (aus || (e instanceof ApiError && e.status === 404)) return      // ein verschwundener Lauf zeigt nichts mehr
          fehlschlaege += 1
          if (fehlschlaege < FORTSCHRITT_VERSUCHE) timer = setTimeout(holen, FORTSCHRITT_INTERVALL_MS * fehlschlaege)
        })
    }
    holen()
    return () => { aus = true; if (timer) clearTimeout(timer) }
  }, [anlageId, lauf])

  if (!stand) return null
  return (
    <Alert type={stand.status === 'fertig' ? 'success' : 'info'} title={label}>
      <span data-korrektur-fortschritt={lauf}>{fortschrittSatz(stand)}</span>
      {stand.fuellen_offen && <span className="mt-1 block">{SATZ_FUELLEN_OFFEN}</span>}
    </Alert>
  )
}
