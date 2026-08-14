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
  // TagLeerGrund. Der SWR-Key hängt am Gerät, damit der Wechsel zwischen zwei
  // Geräten desselben Typs nicht den Grund des vorigen stehen lässt.
  const { data } = useApiData(
    () => investitionenApi.getHubLeerGrund(anlageId, investitionId),
    [anlageId, investitionId],
    { swrKey: `v4-hub-leer:${anlageId}:${investitionId}` }, /* de-de-allow: Cache-Key, keine Anzeige */
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
