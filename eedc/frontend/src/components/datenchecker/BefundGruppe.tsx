/**
 * BefundGruppe — die Gruppenzeile des Daten-Checkers (Etappe E5, Konzept §6 V2, Mockup): «7 Monate fehlen» mit einem
 * Glied je Befund («01/2026 · 02/2026 · …»). Jedes Glied bleibt ein Befund mit eigenem Handgriff: ein Sprung öffnet genau
 * dieses Glied (`zielPfad`), eine Aktion plant genau dieses Glied (`useBefundAktion`, Vorschau-Kasten unter der Zeile).
 * Der Knopf rechts handelt am ersten Glied. Titel, Details und `weitere` (Befunde über der Anzeige-Grenze des Erzeugers)
 * kommen aus der Antwort (`gruppe`) — der Client zählt nichts nach.
 */
import { useNavigate } from 'react-router-dom'
import { ChevronRight, Wrench } from 'lucide-react'
import { Button, InlineAktion } from '../ui'
import type { CheckErgebnis } from '../../api/datenChecker'
import { SEVERITY_CONFIG, type CheckSchwere } from '../../config/datenCheckerKategorien'
import { zielPfad } from '../../lib/zielPfad'
import type { HandgriffProps } from './BefundHandgriff'
import VorschauKasten from './VorschauKasten'
import { useBefundAktion } from './useBefundAktion'

export default function BefundGruppe({
  glieder, anlageId, gesperrt = false, onVorgang, onErgebnis, onLoesungsweg, kontext,
}: HandgriffProps & { glieder: CheckErgebnis[]; kontext?: string }) {
  const navigate = useNavigate()
  const erstes = glieder[0]
  const gruppe = erstes.gruppe!
  const aktion = useBefundAktion(erstes, anlageId, { onVorgang, onErgebnis })
  const cfg = SEVERITY_CONFIG[erstes.schwere as CheckSchwere]
  const Icon = cfg?.icon

  const handeln = (g: CheckErgebnis) => {
    if (g.action) {
      aktion.planen(g)
      return
    }
    const pfad = zielPfad(g.ziel)
    if (pfad) navigate(pfad)
  }

  return (
    <div className="px-4 py-2.5" data-testid="befund-gruppe">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:gap-3">
        <div className="flex flex-1 min-w-0 items-start gap-3">
          {Icon && <Icon className={`h-4 w-4 mt-0.5 flex-shrink-0 ${cfg.colorClass}`} />}
          <div className="flex-1 min-w-0">
            <p className="text-sm text-gray-800 dark:text-gray-200"><strong>{gruppe.titel}</strong></p>
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
              {kontext && <span>{kontext} · </span>}
              {gruppe.details && <span>{gruppe.details} · </span>}
              {onLoesungsweg && <InlineAktion ton="aktion" onClick={() => onLoesungsweg(erstes)}>Lösungsweg</InlineAktion>}
            </p>
          </div>
        </div>
        {erstes.knopf && (
          <Button type="button" variant={erstes.action ? 'secondary' : 'ghost'} size="sm" className="flex-shrink-0 self-start"
            onClick={() => handeln(erstes)} disabled={gesperrt || aktion.offen} loading={aktion.busy && !aktion.plan}>
            {erstes.action && !(aktion.busy && !aktion.plan) && <Wrench className="h-3 w-3 mr-1" />}
            {erstes.knopf}
            {!erstes.action && <ChevronRight className="h-3 w-3 ml-0.5" />}
          </Button>
        )}
      </div>
      <div className="mt-2 flex flex-wrap gap-1.5 sm:pl-7" data-testid="gruppe-glieder">
        {glieder.map((g) => (
          <Button key={g.gruppe?.glied ?? g.meldung} type="button" variant="ghost" size="sm" title={g.meldung}
            onClick={() => handeln(g)} disabled={gesperrt || aktion.offen}
            className="border border-gray-300 dark:border-gray-600">
            {g.gruppe?.glied}
          </Button>
        ))}
        {gruppe.weitere > 0 && (
          <span className="px-1 py-0.5 text-xs text-gray-500 dark:text-gray-400">+ {gruppe.weitere} weitere</span>
        )}
      </div>
      {aktion.fehler && !aktion.plan && <p className="text-sm text-red-600 dark:text-red-400 mt-1">{aktion.fehler}</p>}
      {aktion.plan && (
        <VorschauKasten plan={aktion.plan} laeuft={aktion.busy} fehler={aktion.fehler}
          onAnwenden={aktion.anwenden} onAbbrechen={aktion.abbrechen} />
      )}
    </div>
  )
}
