/**
 * HubLeerGrund — der Komponenten-Reiter erklärt sich, statt zu schweigen (N-247).
 *
 * **Gemeldet von CHI3fx117 (Forum T89667 #152, 14.08.):** Ein Speicher mit
 * Anschaffungsdatum im laufenden Monat steht in *Cockpit → Tag/Monat*, im Reiter
 * *Komponenten* dagegen bei Null — ohne ein Wort dazu. Seine Frage *„Habe ich
 * etwas falsch gemacht oder sind diese erst nach dem ersten Monatsabschluss dort
 * zu finden?"* ist der Beleg: Der Anwender kann „noch keine Daten" nicht von
 * „falsch eingerichtet" unterscheiden.
 *
 * **Der Grund kommt aus dem Backend** (`getHubLeerGrund`), nicht aus einer
 * Client-Ableitung — dieselbe Linie wie {@link TagLeerGrund} (Gernot 2026-08-06:
 * „zweite Wahrheit ist nicht gut"). Der Server prüft die Leere zusätzlich selbst
 * nach, mit demselben Aktiv-Filter wie die Dashboards; steht dort `leer=false`,
 * zeigt diese Komponente **nichts** an.
 *
 * **Grund immer, Weg nur wo er trägt.** Ein Gerät, das jünger ist als der erste
 * abschließbare Monat, hat nichts abzuschließen — dort verweist der Knopf auf
 * *Cockpit → Monat* statt auf den Monatsabschluss (P-6: kein Hinweis, den
 * niemand auflösen kann).
 *
 * Bausteine sind die vorhandenen (Regel 0a): {@link Alert}, {@link Button}.
 */
import { useNavigate } from 'react-router-dom'
import { ChevronRight } from 'lucide-react'
import { Alert, Button } from '../components/ui'
import { useApiData } from '../hooks'
import { investitionenApi } from '../api/investitionen'

export default function HubLeerGrund({ anlageId, investitionId }: {
  anlageId: number
  investitionId: number
}) {
  const navigate = useNavigate()
  // Eigener Aufruf, bewusst NUR aus dem leeren Zustand heraus — analog
  // TagLeerGrund.
  //
  // ⚠ **Bewusst OHNE `swrKey` (N-270).** Bis 17.08.2026 stand hier
  // `v4-hub-leer:${anlageId}:${investitionId}` mit der Begründung, der Wechsel
  // zwischen zwei Geräten desselben Typs solle nicht den Grund des vorigen
  // stehen lassen. Genau das bewirkte der Cache aber: diese Komponente ist keine
  // Datenanzeige, sondern eine **Aussage über die Abwesenheit** von Daten. Wer
  // den Knopf drückt, Monatswerte erfasst und in *Komponenten* zurückkommt
  // (Tab-Wechsel = Remount), sah für eine API-Runde „noch keine Monatswerte
  // erfasst" — über den nun gefüllten Blöcken. Ohne Cache rendert die
  // Komponente `null`, bis die Antwort da ist: kein Skeleton (es gibt hier
  // keines zu vermeiden), kein Flackern, und der ursprüngliche Grund für den
  // Key ist **besser** erfüllt als mit ihm.
  //
  // {@link TagLeerGrund} behält seinen Key aus eigener, gemessener Begründung:
  // es wird nur aus dem bereits leeren Zustand heraus gerendert, zeigt immer
  // mindestens seinen Text, und sein Key trägt das Datum — ein stale Wert ist
  // dort die stale Verfeinerung einer bereits korrekten Aussage.
  const { data } = useApiData(
    () => investitionenApi.getHubLeerGrund(anlageId, investitionId),
    [anlageId, investitionId],
  )

  if (!data?.leer || !data.meldung) return null

  return (
    <Alert type="info" title={data.meldung}>
      {data.details && <p>{data.details}</p>}
      {data.link && (
        <div className="pt-2">
          <Button
            type="button"
            variant="secondary"
            size="sm"
            onClick={() => navigate(data.link as string)}
          >
            {data.link_label ?? 'Dorthin'}
            <ChevronRight className="h-3 w-3 ml-0.5" />
          </Button>
        </div>
      )}
    </Alert>
  )
}
