/**
 * useBefundAktion — die **eine** Mechanik einer Checker-Aktion (Etappe E3, Konzept §3.1 R6, Wächter W-10): Plan →
 * Vorschau-Kasten → «Anwenden» (Ausführen) oder «Abbrechen» (Plan verwerfen). Geteilt von der Befund-Zeile
 * (`BefundHandgriff`) und der Gruppenzeile (`BefundGruppe`, E5) — keine Wrapper-Route.
 */
import { useState } from 'react'
import type { CheckErgebnis } from '../../api/datenChecker'
import { repairApi, type RepairOperationType, type RepairPlan } from '../../api/repair'
import type { ReparaturMeldung } from '../../pages/datenCheckerMeldungen'
import { ergebnisMeldung } from './vorschauZeile'

function fehlerText(e: unknown, ersatz: string): string {
  return e instanceof Error && e.message ? e.message : ersatz
}

export function useBefundAktion(e: CheckErgebnis, anlageId: number, { onVorgang, onErgebnis }: {
  onVorgang?: (aktiv: boolean) => void
  onErgebnis?: (m: ReparaturMeldung) => void
}) {
  const [plan, setPlan] = useState<RepairPlan | null>(null)
  const [busy, setBusy] = useState(false)
  const [fehler, setFehler] = useState<string | null>(null)
  const knopf = e.knopf ?? 'Ausführen'

  const ende = () => { setPlan(null); setBusy(false); onVorgang?.(false) }

  /** Plan für den Befund — oder für ein anderes Glied derselben Gruppe (`BefundGruppe`, gleiche Operation). */
  const planen = async (b: CheckErgebnis = e) => {
    if (!b.action) return
    setFehler(null)
    setBusy(true)
    onVorgang?.(true)
    try {
      const r = await repairApi.plan({
        anlage_id: anlageId, operation: b.action.operation as RepairOperationType, params: b.action.params ?? {},
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

  return { plan, busy, fehler, offen: plan !== null || busy, planen, anwenden, abbrechen }
}
