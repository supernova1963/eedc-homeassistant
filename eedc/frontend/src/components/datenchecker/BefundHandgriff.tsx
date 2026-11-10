/**
 * BefundHandgriff — eine Befund-Zeile mit genau einem Handgriff (Etappe E3, Konzept §3–§5; eine Komponente für den
 * Daten-Checker und den Komponenten-Hub, Entscheid §11 Nr. 2).
 *
 * Links Schwere-Icon, Meldung, Details und der Text-Link «Lösungsweg» (öffnet das Panel neben der Liste); rechts **ein**
 * Knopf aus der Klasse des Befunds:
 * - **Aktion** (`action_kind`): Klick 1 `repairApi.plan` ⇒ `VorschauKasten` unter der Zeile; «Anwenden» ⇒
 *   `repairApi.execute` ⇒ Ergebnis-Satz an den Aufrufer, der neu prüft. Fehler ⇒ roter Satz, der Befund bleibt.
 * - **Sprung** (`link`): «Beheben» ⇒ `navigate(link)` (E4 schaltet auf `ziel` um).
 * - **Auskunft** (weder noch, nicht OK): «Was gilt» ⇒ das Lösungsweg-Panel.
 * Ein Vorgang zur Zeit (`gesperrt`). **Eine Mechanik** (Wächter W-10, `npm run check:eine-mechanik`): keine Wrapper-
 * Route, nur Plan/Ausführen.
 */
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ChevronRight, Wrench } from 'lucide-react'
import { Button, InlineAktion } from '../ui'
import type { CheckErgebnis } from '../../api/datenChecker'
import { repairApi, type RepairOperationType, type RepairPlan } from '../../api/repair'
import { v3RouteZuV4 } from '../../config/v3ZuV4Route'
import { SEVERITY_CONFIG, type CheckSchwere } from '../../config/datenCheckerKategorien'
import type { ReparaturMeldung } from '../../pages/datenCheckerMeldungen'
import VorschauKasten from './VorschauKasten'
import { ergebnisMeldung } from './vorschauZeile'

function fehlerText(e: unknown, ersatz: string): string {
  return e instanceof Error && e.message ? e.message : ersatz
}

export default function BefundHandgriff({
  befund: e, anlageId, gesperrt = false, onVorgang, onErgebnis, onLoesungsweg, kompakt = false,
}: {
  befund: CheckErgebnis
  anlageId: number
  /** Ein anderer Vorgang läuft — Knopf gesperrt. */
  gesperrt?: boolean
  onVorgang?: (aktiv: boolean) => void
  /** Ergebnis nach «Anwenden»; der Aufrufer zeigt den Satz und prüft neu. */
  onErgebnis?: (m: ReparaturMeldung) => void
  onLoesungsweg?: (befund: CheckErgebnis) => void
  /** Komponenten-Hub: dichtere Zeile. */
  kompakt?: boolean
}) {
  const navigate = useNavigate()
  const [plan, setPlan] = useState<RepairPlan | null>(null)
  const [busy, setBusy] = useState(false)
  const [fehler, setFehler] = useState<string | null>(null)
  const cfg = SEVERITY_CONFIG[e.schwere as CheckSchwere]
  const Icon = cfg?.icon
  const knopf = e.action_label ?? 'Ausführen'
  const offen = plan !== null || busy

  const ende = () => { setPlan(null); setBusy(false); onVorgang?.(false) }

  const planen = async () => {
    if (!e.action_kind) return
    setFehler(null)
    setBusy(true)
    onVorgang?.(true)
    try {
      const r = await repairApi.plan({
        anlage_id: anlageId, operation: e.action_kind as RepairOperationType, params: e.action_params ?? {},
      })
      setPlan(r.plan)
      setBusy(false)
    } catch (err) {
      setFehler(fehlerText(err, 'Die Vorschau konnte nicht erstellt werden'))
      ende()
    }
  }

  const anwenden = async () => {
    if (!plan) return
    setFehler(null)
    setBusy(true)
    try {
      const result = await repairApi.execute(plan.plan_id)
      ende()
      onErgebnis?.(ergebnisMeldung(result, knopf))
    } catch (err) {
      setFehler(fehlerText(err, `${knopf}: fehlgeschlagen`))
      setBusy(false)
    }
  }

  const abbrechen = async () => {
    if (plan) await repairApi.discard(plan.plan_id).catch(() => undefined)
    setFehler(null)
    ende()
  }

  let handgriff = null
  if (e.action_kind) {
    handgriff = (
      <Button type="button" variant="secondary" size="sm" className="flex-shrink-0"
        onClick={planen} disabled={gesperrt || offen} loading={busy && !plan}>
        {!(busy && !plan) && <Wrench className="h-3 w-3 mr-1" />}
        {knopf}
      </Button>
    )
  } else if (e.link) {
    handgriff = (
      <Button type="button" variant="ghost" size="sm" className="flex-shrink-0"
        onClick={() => navigate(v3RouteZuV4(e.link!) ?? e.link!)}>
        Beheben
        <ChevronRight className="h-3 w-3 ml-0.5" />
      </Button>
    )
  } else if (e.schwere !== 'ok' && onLoesungsweg) {
    handgriff = (
      <Button type="button" variant="ghost" size="sm" className="flex-shrink-0" onClick={() => onLoesungsweg(e)}>
        Was gilt
      </Button>
    )
  }

  return (
    <div className={kompakt ? 'text-sm' : 'px-4 py-2.5'} data-testid="befund-zeile">
      <div className="flex items-start gap-3">
        {Icon && <Icon className={`h-4 w-4 mt-0.5 flex-shrink-0 ${cfg.colorClass}`} />}
        <div className="flex-1 min-w-0">
          <p className="text-sm text-gray-800 dark:text-gray-200">{e.meldung}</p>
          {e.details && (
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5 whitespace-pre-line">{e.details}</p>
          )}
          {e.schwere !== 'ok' && onLoesungsweg && (
            <InlineAktion ton="aktion" className="mt-0.5" onClick={() => onLoesungsweg(e)}>Lösungsweg</InlineAktion>
          )}
          {fehler && !plan && <p className="text-sm text-red-600 dark:text-red-400 mt-1">{fehler}</p>}
        </div>
        {handgriff}
      </div>
      {plan && (
        <VorschauKasten plan={plan} laeuft={busy} fehler={fehler} onAnwenden={anwenden} onAbbrechen={abbrechen} />
      )}
    </div>
  )
}
