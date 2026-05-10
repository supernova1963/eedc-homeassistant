/**
 * Reparatur-Werkbank API (Etappe 3d Päckchen 4).
 *
 * Wrapper über /api/repair/* — siehe routes/repair.py + services/repair_orchestrator.py.
 *
 * Plan-Lebenszyklus: 1h in-memory. plan_id muss nach erfolgreichem
 * /plan persistiert werden, weil /execute/{plan_id} sie braucht.
 */

import { api } from './client'

export type RepairOperationType =
  | 'reaggregate_day'
  | 'reaggregate_today'
  | 'vollbackfill'
  | 'kraftstoffpreis_backfill'
  | 'delete_monatsdaten'
  | 'reset_cloud_import'
  | 'solcast_rewrite'

export interface RepairOperationRequest {
  anlage_id: number | null
  operation: RepairOperationType
  params: Record<string, unknown>
}

export interface FieldDiff {
  table: string
  row_pk: Record<string, unknown>
  field: string
  old_value: unknown
  new_value: unknown
  source_before: string | null
  source_after: string
  decision: 'applied' | 'rejected_lower_priority' | 'no_op_same_value'
}

export interface RepairPlan {
  plan_id: string
  anlage_id: number | null
  operation: RepairOperationType
  operation_params: Record<string, unknown>
  created_at: string
  expires_at: string
  estimated_changes: Record<string, number>
  diff_preview: FieldDiff[]
  diff_total_count: number
  warnings: string[]
  operation_preview: Record<string, unknown>
}

export interface RepairResult {
  plan_id: string
  anlage_id: number | null
  operation: RepairOperationType
  executed_at: string
  actual_changes: Record<string, number>
  audit_log_ids: number[]
  operation_summary: Record<string, unknown>
}

export interface RepairPlanView {
  plan: RepairPlan
  result: RepairResult | null
}

export interface PlanResponse {
  plan: RepairPlan
  expires_in_seconds: number
}

export interface PlansListResponse {
  plans: RepairPlanView[]
}

/**
 * Operation-Metadaten für die UI: Label, Kurzbeschreibung, ob in
 * Werkbank gelistet werden soll (REAGGREGATE_TODAY + DELETE_MONATSDATEN
 * sind Single-Click-Aktionen mit eigenem UX-Pfad).
 */
export interface OperationMeta {
  type: RepairOperationType
  label: string
  description: string
  inWorkbench: boolean
}

export const OPERATION_META: OperationMeta[] = [
  {
    type: 'reaggregate_day',
    label: 'Tag neu aggregieren',
    description:
      'Lädt SensorSnapshots eines Tages frisch aus HA-Statistics und baut Stundenwerte + Tageszusammenfassung neu. Idempotent.',
    inWorkbench: true,
  },
  {
    type: 'vollbackfill',
    label: 'Lücken aus HA-LTS nachfüllen',
    description:
      'Füllt fehlende Tage aus HA Long-Term Statistics — additiv, bestehende Tage bleiben unverändert.',
    inWorkbench: true,
  },
  {
    type: 'kraftstoffpreis_backfill',
    label: 'Kraftstoffpreise nachpflegen',
    description:
      'EU Oil Bulletin Wochenpreise (Euro-Super 95) für offene Tages- bzw. Monatsdaten-Zeilen.',
    inWorkbench: true,
  },
  {
    type: 'reset_cloud_import',
    label: 'Cloud-Import-Werte zurücksetzen',
    description:
      'Setzt alle Felder zurück, die zuletzt von einem Cloud-Connector geschrieben wurden. Hierarchie wird durchbrochen (force_override). Optional pro Provider filterbar.',
    inWorkbench: true,
  },
  {
    type: 'reaggregate_today',
    label: 'Heutigen Tag neu aggregieren',
    description: 'Triggert sofortige Neu-Aggregation für alle Anlagen.',
    inWorkbench: false,
  },
  {
    type: 'delete_monatsdaten',
    label: 'Monatsdaten löschen',
    description: 'Löscht eine Monatsdaten-Row mit Audit-Log.',
    inWorkbench: false,
  },
  {
    type: 'solcast_rewrite',
    label: 'Solcast-Schreiber konsolidieren',
    description: 'Päckchen 6 — noch nicht implementiert.',
    inWorkbench: false,
  },
]

export const repairApi = {
  plan: (req: RepairOperationRequest, signal?: AbortSignal): Promise<PlanResponse> =>
    api.post('/repair/plan', req, { signal }),

  execute: (planId: string, signal?: AbortSignal): Promise<RepairResult> =>
    api.post(`/repair/execute/${planId}`, undefined, { signal }),

  listPlans: (anlageId: number, limit = 20): Promise<PlansListResponse> =>
    api.get(`/repair/plans?anlage_id=${anlageId}&limit=${limit}`),

  discard: (planId: string): Promise<void> =>
    api.delete(`/repair/plans/${planId}`),
}
