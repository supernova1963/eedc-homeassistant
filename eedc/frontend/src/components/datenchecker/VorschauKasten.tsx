/**
 * VorschauKasten — was eine Aktion des Daten-Checkers ändern wird, bevor sie es tut (Etappe E3, Konzept §5).
 *
 * Unter der Befund-Zeile, volle Breite (Handy): **eine Zeile** in Anwender-Sprache aus dem Plan (`vorschauAussage`),
 * darunter die Werkbank-Warnungen unverändert (Gegenprüfung Ü3), dann «Anwenden» / «Abbrechen» und der Sprung
 * «Details in der Werkbank» (`plan=<id>`). Lösch-Operationen tragen «endgültig» und einen roten Knopf; ein Plan
 * «nichts zu tun» zeigt nur den Satz (kein «Anwenden»). `window.confirm` entfällt (Konzept §11 Nr. 6).
 */
import { useNavigate } from 'react-router-dom'
import { Button, InlineAktion } from '../ui'
import type { RepairPlan } from '../../api/repair'
import { vorschauAussage } from './vorschauZeile'

/** Die Werkbank im Daten-Block, mit dem vorhandenen Plan (`RepairWorkbench` liest `plan=`). */
export function werkbankMitPlan(planId: string): string {
  return `/einstellungen/daten?block=energieprofil&karte=werkbank&plan=${planId}`
}

export default function VorschauKasten({ plan, laeuft, fehler, onAnwenden, onAbbrechen }: {
  plan: RepairPlan
  laeuft: boolean
  fehler: string | null
  onAnwenden: () => void
  onAbbrechen: () => void
}) {
  const navigate = useNavigate()
  const a = vorschauAussage(plan)
  return (
    <div className="w-full mt-2 rounded border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800/60 p-3 space-y-2"
      data-testid="vorschau-kasten">
      <p className="text-sm text-gray-800 dark:text-gray-200">{a.satz}</p>
      {plan.warnings.length > 0 && (
        <ul className="list-disc pl-5 text-xs text-gray-600 dark:text-gray-400 space-y-0.5">
          {plan.warnings.map((w, i) => <li key={i}>{w}</li>)}
        </ul>
      )}
      {fehler && <p className="text-sm text-red-600 dark:text-red-400">{fehler}</p>}
      <div className="flex flex-wrap items-center gap-2">
        {!a.nichtsZuTun && (
          <Button size="sm" variant={a.endgueltig ? 'danger' : 'primary'} onClick={onAnwenden} loading={laeuft}>
            Anwenden
          </Button>
        )}
        <Button size="sm" variant="secondary" onClick={onAbbrechen} disabled={laeuft}>
          {a.nichtsZuTun ? 'Schließen' : 'Abbrechen'}
        </Button>
        <InlineAktion ton="aktion" onClick={() => navigate(werkbankMitPlan(plan.plan_id))} disabled={laeuft}>
          Details in der Werkbank
        </InlineAktion>
        {!a.nichtsZuTun && (
          <span className="text-xs text-gray-500 dark:text-gray-400">gültig bis {a.gueltigBis}</span>
        )}
      </div>
    </div>
  )
}
