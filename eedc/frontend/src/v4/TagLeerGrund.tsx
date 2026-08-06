/**
 * TagLeerGrund — die leere Tagessicht erklärt sich, und der Weg steht daneben (F-2).
 *
 * Bis v4.0.9 stand in Cockpit/Tag für einen Tag ohne Werte ein Satz ohne Grund
 * und ohne Weg nach vorn („Für diesen Tag liegen keine Daten vor. Wähle einen
 * Tag mit Messwerten."). Erreichbar ist der Zustand nicht nur an Lücken-Tagen,
 * sondern systematisch: die Datumsauswahl gibt ab dem ersten Tag des ältesten
 * Monats frei, die Tageszeilen beginnen aber oft später (an einer echten Box
 * gemessen: Auswahl ab 2024-10-01, erste Zeile 2024-10-31 ⇒ 30 leere Tage).
 * Ohne jede Tagesebene — der Fall aus Forum T89667 — trifft es jeden Tag.
 *
 * **Der Grund kommt aus dem Backend** (`getTagStatus`), nicht aus einer
 * Client-Ableitung (Gernot 2026-08-06: „zweite Wahrheit ist nicht gut"): Ob der
 * Tag vor der Inbetriebnahme liegt, ob an ihm überhaupt ein Zähler zugeordnet
 * war und ob Home Assistant für ihn noch Werte hat, weiß nur der Server.
 *
 * **Grund immer, Handlung nur wo sie wirkt.** Der Knopf erscheint ausschließlich
 * bei `aktion_kind === 'reaggregate_day'`; in allen anderen Lagen sagt der Text
 * die Absage offen. Ein Knopf, der garantiert nichts holen kann, ist schlimmer
 * als keiner — dieselbe Linie wie #368/P-8, nur von der anderen Seite.
 *
 * Bausteine sind die vorhandenen (Regel 0a): {@link Button}, {@link Alert} und
 * der Rückmeldungs-SoT `baueTagesMeldung` — die Reparatur darf hier nicht anders
 * antworten als im Daten-Checker.
 */
import { useCallback, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Wrench, ChevronRight } from 'lucide-react'
import { Alert, Button } from '../components/ui'
import { useApiData } from '../hooks'
import { formatDatum } from '../lib'
import { v3RouteZuV4 } from '../config/v3ZuV4Route'
import { baueTagesMeldung, type ReparaturMeldung } from '../pages/datenCheckerMeldungen'
import { energieProfilApi } from '../api/energie_profil'

/** IST-Text der Stelle — bleibt der Satz, solange der Grund noch lädt oder der
 *  Server ihn nicht liefert (vertraute Anzeigen nur ändern, wo nötig). */
export const TAG_LEER_TEXT = 'Für diesen Tag liegen keine Daten vor. Wähle einen Tag mit Messwerten.'

const ALERT_TYP = { ok: 'success', hinweis: 'warning', fehler: 'error' } as const

export default function TagLeerGrund({ anlageId, datum, onRepariert }: {
  anlageId: number
  datum: string
  /** Nach einem Lauf, der etwas geschrieben hat: Sicht neu laden. */
  onRepariert: () => void
}) {
  const navigate = useNavigate()
  const [laeuft, setLaeuft] = useState(false)
  const [meldung, setMeldung] = useState<ReparaturMeldung | null>(null)

  // Eigener Aufruf, bewusst NUR aus dem leeren Zustand heraus: die letzte
  // Prüfung im Backend ist ein HA-LTS-Read für den Tag. Der SWR-Key hängt am
  // Tag, damit der Wechsel zwischen zwei leeren Tagen nicht denselben Grund
  // stehen lässt.
  const statusQ = useApiData(
    () => energieProfilApi.getTagStatus(anlageId, datum),
    [anlageId, datum],
    { swrKey: `v4-tag-status:${anlageId}:${datum}` }, /* de-de-allow: Cache-Key, keine Anzeige */
  )
  const status = statusQ.data

  const reparieren = useCallback(async () => {
    setLaeuft(true)
    setMeldung(null)
    try {
      const r = await energieProfilApi.reaggregateTag(anlageId, datum)
      const m = baueTagesMeldung(r, datum)
      setMeldung(m)
      // Nur nachladen, wenn der Lauf etwas geschrieben haben kann — sonst
      // ersetzte ein Refetch die eben erklärte Lage durch denselben leeren
      // Zustand ohne Meldung.
      if (m.art === 'ok') onRepariert()
    } catch (e) {
      setMeldung({
        art: 'fehler',
        text: `Tag ${formatDatum(datum)} konnte nicht nachgerechnet werden: ${
          e instanceof Error ? e.message : 'unbekannter Fehler'
        }`,
      })
    } finally {
      setLaeuft(false)
    }
  }, [anlageId, datum, onRepariert])

  const ziel = status?.link ? (v3RouteZuV4(status.link) ?? status.link) : null

  return (
    <div className="space-y-2">
      <p className="text-sm text-gray-700 dark:text-gray-300">
        {status?.meldung ?? TAG_LEER_TEXT}
      </p>
      {status?.details && (
        <p className="text-xs text-gray-500 dark:text-gray-400">{status.details}</p>
      )}
      {(status?.aktion_kind === 'reaggregate_day' || ziel) && (
        <div className="flex flex-wrap items-center gap-2 pt-1">
          {status?.aktion_kind === 'reaggregate_day' && (
            <Button
              type="button"
              variant="secondary"
              size="sm"
              onClick={reparieren}
              disabled={laeuft}
              loading={laeuft}
            >
              {!laeuft && <Wrench className="h-3 w-3 mr-1" />}
              {status.aktion_label ?? 'Tag nachrechnen'}
            </Button>
          )}
          {ziel && (
            <Button type="button" variant="ghost" size="sm" onClick={() => navigate(ziel)}>
              Beheben
              <ChevronRight className="h-3 w-3 ml-0.5" />
            </Button>
          )}
        </div>
      )}
      {meldung && (
        <Alert type={ALERT_TYP[meldung.art]}>{meldung.text}</Alert>
      )}
    </div>
  )
}
