/**
 * useWerkbankPlanAusUrl — die Werkbank zeigt einen vorhandenen Plan aus der Adresse (`plan=<id>`, Etappe E3).
 *
 * Der Vorschau-Kasten im Daten-Checker springt mit «Details in der Werkbank» hierher
 * (`/einstellungen/daten?block=energieprofil&karte=werkbank&plan=<id>`). Der Hook liest `plan` an **einer** Stelle,
 * sucht ihn im Verlauf der Anlage (`GET /repair/plans`, kein neuer Endpunkt), reicht ihn einmal an `onPlan` und entfernt
 * den Parameter danach (Muster `bearbeiten`). Ein abgelaufener oder ausgeführter Plan wird nicht gezeigt.
 */
import { useEffect } from 'react'
import { useSearchParams } from 'react-router-dom'
import { repairApi, type RepairPlan } from '../api/repair'

export function useWerkbankPlanAusUrl(anlageId: number, onPlan: (plan: RepairPlan) => void): void {
  const [searchParams, setSearchParams] = useSearchParams()
  const planId = searchParams.get('plan')

  useEffect(() => {
    if (!planId) return
    let ab = false
    repairApi.listPlans(anlageId)
      .then((r) => {
        if (ab) return
        const treffer = r.plans.find((v) => v.plan.plan_id === planId && !v.result)
        if (treffer) onPlan(treffer.plan)
      })
      .catch(() => undefined)
      .finally(() => {
        if (ab) return
        const naechste = new URLSearchParams(searchParams)
        naechste.delete('plan')
        setSearchParams(naechste, { replace: true })
      })
    return () => { ab = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [planId, anlageId])
}
