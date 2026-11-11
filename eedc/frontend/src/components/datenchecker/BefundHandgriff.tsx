/**
 * BefundHandgriff — eine Befund-Zeile mit genau einem Handgriff (Etappe E3, Konzept §3–§5; eine Komponente für den
 * Daten-Checker, seine Handgriff-Leiste und den Komponenten-Hub, Entscheid §11 Nr. 2).
 *
 * Links Schwere-Icon, Meldung, Details und der Text-Link «Lösungsweg» (öffnet das Panel neben der Liste); rechts **ein**
 * Knopf aus der Klasse des Befunds, beschriftet mit `knopf` aus dem Katalog (E5.7 L1 — «Gerät bearbeiten», «Monat
 * erfassen», «Was gilt» …; kein festes «Beheben» mehr):
 * - **Aktion** (`action`): Klick 1 `repairApi.plan` ⇒ `VorschauKasten` unter der Zeile; «Anwenden» ⇒
 *   `repairApi.execute` ⇒ Ergebnis-Satz an den Aufrufer, der neu prüft. Fehler ⇒ roter Satz, der Befund bleibt.
 * - **Sprung** (`ziel`): `navigate(zielPfad(ziel))` — der Pfad trägt alle Parameter des Ziels (Feld, Gerät, Tarif …).
 * - **Auskunft** (weder noch, nicht OK): «Was gilt» ⇒ das Lösungsweg-Panel.
 * Ein Vorgang zur Zeit (`gesperrt`). **Eine Mechanik** (Wächter W-10, `npm run check:eine-mechanik`): keine Wrapper-
 * Route, nur Plan/Ausführen (`useBefundAktion`).
 */
import { useNavigate } from 'react-router-dom'
import { ChevronRight, Wrench } from 'lucide-react'
import { Button, InlineAktion } from '../ui'
import type { CheckErgebnis } from '../../api/datenChecker'
import { SEVERITY_CONFIG, type CheckSchwere } from '../../config/datenCheckerKategorien'
import type { ReparaturMeldung } from '../../pages/datenCheckerMeldungen'
import { zielPfad } from '../../lib/zielPfad'
import VorschauKasten from './VorschauKasten'
import { useBefundAktion } from './useBefundAktion'

export interface HandgriffProps {
  anlageId: number
  /** Ein anderer Vorgang läuft — Knopf gesperrt. */
  gesperrt?: boolean
  onVorgang?: (aktiv: boolean) => void
  /** Ergebnis nach «Anwenden»; der Aufrufer zeigt den Satz und prüft neu. */
  onErgebnis?: (m: ReparaturMeldung) => void
  onLoesungsweg?: (befund: CheckErgebnis) => void
}

export default function BefundHandgriff({
  befund: e, anlageId, gesperrt = false, onVorgang, onErgebnis, onLoesungsweg, kompakt = false, kontext,
}: HandgriffProps & {
  befund: CheckErgebnis
  /** Komponenten-Hub: dichtere Zeile. */
  kompakt?: boolean
  /** Handgriff-Leiste: die Kategorie vor dem Lösungsweg-Link. */
  kontext?: string
}) {
  const navigate = useNavigate()
  const aktion = useBefundAktion(e, anlageId, { onVorgang, onErgebnis })
  const cfg = SEVERITY_CONFIG[e.schwere as CheckSchwere]
  const Icon = cfg?.icon
  const pfad = zielPfad(e.ziel)

  let handgriff = null
  if (e.action) {
    handgriff = (
      <Button type="button" variant="secondary" size="sm" className="flex-shrink-0 self-start"
        onClick={() => aktion.planen()} disabled={gesperrt || aktion.offen} loading={aktion.busy && !aktion.plan}>
        {!(aktion.busy && !aktion.plan) && <Wrench className="h-3 w-3 mr-1" />}
        {e.knopf}
      </Button>
    )
  } else if (pfad && e.knopf) {
    handgriff = (
      <Button type="button" variant="ghost" size="sm" className="flex-shrink-0 self-start" onClick={() => navigate(pfad)}>
        {e.knopf}
        <ChevronRight className="h-3 w-3 ml-0.5" />
      </Button>
    )
  } else if (e.schwere !== 'ok' && onLoesungsweg) {
    handgriff = (
      <Button type="button" variant="ghost" size="sm" className="flex-shrink-0 self-start" onClick={() => onLoesungsweg(e)}>
        {e.knopf ?? 'Was gilt'}
      </Button>
    )
  }

  return (
    <div className={kompakt ? 'text-sm' : 'px-4 py-2.5'} data-testid="befund-zeile">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:gap-3">
        <div className="flex flex-1 min-w-0 items-start gap-3">
          {Icon && <Icon className={`h-4 w-4 mt-0.5 flex-shrink-0 ${cfg.colorClass}`} />}
          <div className="flex-1 min-w-0">
            <p className="text-sm text-gray-800 dark:text-gray-200">{e.meldung}</p>
            {e.details && (
              <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5 whitespace-pre-line">{e.details}</p>
            )}
            {e.schwere !== 'ok' && onLoesungsweg && (
              <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                {kontext && <span>{kontext} · </span>}
                <InlineAktion ton="aktion" onClick={() => onLoesungsweg(e)}>Lösungsweg</InlineAktion>
              </p>
            )}
            {aktion.fehler && !aktion.plan && <p className="text-sm text-red-600 dark:text-red-400 mt-1">{aktion.fehler}</p>}
          </div>
        </div>
        {handgriff}
      </div>
      {aktion.plan && (
        <VorschauKasten plan={aktion.plan} laeuft={aktion.busy} fehler={aktion.fehler}
          onAnwenden={aktion.anwenden} onAbbrechen={aktion.abbrechen} />
      )}
    </div>
  )
}
