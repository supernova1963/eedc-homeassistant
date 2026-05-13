/**
 * Reparatur-Werkbank (Etappe 3d Päckchen 4).
 *
 * Vereinheitlichte UI für alle Reparatur-Operationen über das
 * Plan/Execute-Modell aus services/repair_orchestrator.py:
 *
 *   1. Operation auswählen + Parameter angeben
 *   2. Plan erstellen → Vorschau mit Diff-Tabelle + Warnungen
 *   3. Bestätigen → Execute schreibt + sammelt audit_log_ids
 *   4. Verlauf der letzten 20 Pläne pro Anlage
 *
 * Wird in pages/Energieprofil.tsx als zusätzliche Card unterhalb der
 * heutigen Datenverwaltung-Sektion gemountet. Die alten Schnellbuttons
 * (Vollbackfill / Kraftstoffpreis-Tages) bleiben — sie rufen heute über
 * die Wrapper-Endpoints denselben Orchestrator, ohne UI-Vorschau.
 *
 * Memory-Linien:
 * - `feedback_reparatur_statt_loesch_features.md`: Vorschau ist die
 *   zentrale UX-Antwort, keine Direkt-Klick-Reparatur ohne Diff-Sicht.
 * - `feedback_daten_checker_kein_akzeptiert.md`: keine Quittier-Knöpfe
 *   für Daten-Checker-Hinweise — Werkbank ist der Repair-Pfad, nicht
 *   die Akzeptanz-Schiene.
 * - `feedback_ios_companion_app.md`: overscroll-contain auf Sticky-Header
 *   der Diff-Tabelle.
 */

import { useEffect, useRef, useState } from 'react'
import { Activity, AlertTriangle, ChevronDown, ChevronRight, Clock, FileWarning, History, Loader2, Play, Wrench } from 'lucide-react'

import { Alert, Button, Card, Select } from '../ui'
import {
  OPERATION_META,
  REAGGREGATE_RANGE_MAX_DAYS,
  type FieldDiff,
  type RepairOperationRequest,
  type RepairOperationType,
  type RepairPlan,
  type RepairPlanView,
  type RepairResult,
  repairApi,
} from '../../api/repair'

interface Props {
  anlageId: number
  /** Heißt die Anlage, für Verlaufs-Header. */
  anlagenname?: string
}

interface OperationParamsState {
  // reaggregate_day
  datum: string
  mit_resnap: boolean
  // vollbackfill / reaggregate_range
  von: string
  bis: string
  // reaggregate_range: Pflicht-Bestätigung "ohne Support-Anspruch"
  range_confirmed: boolean
  // kraftstoffpreis_backfill
  scope: 'tages' | 'monats' | 'beides'
  // reset_cloud_import
  providers: string  // Komma-Liste, leer = alle
}

const DEFAULT_PARAMS: OperationParamsState = {
  datum: '',
  mit_resnap: true,
  von: '',
  bis: '',
  range_confirmed: false,
  scope: 'beides',
  providers: '',
}

const WORKBENCH_OPERATIONS = OPERATION_META.filter((o) => o.inWorkbench)


export default function RepairWorkbench({ anlageId, anlagenname }: Props) {
  const [selectedOp, setSelectedOp] = useState<RepairOperationType>(
    WORKBENCH_OPERATIONS[0].type
  )
  const [params, setParams] = useState<OperationParamsState>(DEFAULT_PARAMS)
  const [plan, setPlan] = useState<RepairPlan | null>(null)
  const [planLoading, setPlanLoading] = useState(false)
  const [executeRunning, setExecuteRunning] = useState(false)
  const [showCancelHint, setShowCancelHint] = useState(false)
  const [executeResult, setExecuteResult] = useState<RepairResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [history, setHistory] = useState<RepairPlanView[]>([])
  const [historyOpen, setHistoryOpen] = useState(false)
  const [historyLoading, setHistoryLoading] = useState(false)

  // AbortController für laufende Execute-Operation — nach 30s zeigen wir Cancel-Hint.
  const executeAbortRef = useRef<AbortController | null>(null)
  const cancelTimerRef = useRef<number | null>(null)

  // Verlauf bei Anlage-Wechsel + nach Execute neu laden
  const reloadHistory = async () => {
    try {
      setHistoryLoading(true)
      const res = await repairApi.listPlans(anlageId)
      setHistory(res.plans)
    } catch (e) {
      // Verlauf-Fehler nicht prominent — ist nur Diagnose
      console.warn('Verlauf laden fehlgeschlagen', e)
    } finally {
      setHistoryLoading(false)
    }
  }

  useEffect(() => {
    reloadHistory()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [anlageId])

  // #235 detLAN: Bei Parameter-Änderung Execute-Result-Banner verwerfen,
  // sonst bleibt der "Plan erstellen"-Button hinter dem letzten Result
  // versteckt (`!plan && !executeResult`-Bedingung) und User muss
  // Operation wechseln und zurück, um wieder einen Plan erstellen zu können.
  useEffect(() => {
    setExecuteResult(null)
    setError(null)
  }, [
    params.datum, params.von, params.bis, params.mit_resnap,
    params.range_confirmed, params.scope, params.providers,
  ])

  // Operation-Wechsel: Plan-Vorschau + Result zurücksetzen
  const handleOpChange = (op: RepairOperationType) => {
    setSelectedOp(op)
    setPlan(null)
    setExecuteResult(null)
    setError(null)
  }

  const buildOperationParams = (): Record<string, unknown> => {
    switch (selectedOp) {
      case 'reaggregate_day':
        return { datum: params.datum, mit_resnap: params.mit_resnap }
      case 'reaggregate_range':
        return {
          von: params.von,
          bis: params.bis,
          mit_resnap: params.mit_resnap,
        }
      case 'vollbackfill':
        return {
          von: params.von || null,
          bis: params.bis || null,
        }
      case 'kraftstoffpreis_backfill':
        return { scope: params.scope }
      case 'reset_cloud_import': {
        const provs = params.providers
          .split(',')
          .map((p) => p.trim())
          .filter(Boolean)
        return provs.length > 0 ? { providers: provs } : {}
      }
      default:
        return {}
    }
  }

  const validateParams = (): string | null => {
    if (selectedOp === 'reaggregate_day' && !params.datum) {
      return 'Bitte einen Tag auswählen.'
    }
    if (selectedOp === 'reaggregate_range') {
      if (!params.von || !params.bis) {
        return 'Bitte Start- und Enddatum auswählen.'
      }
      const von = new Date(params.von)
      const bis = new Date(params.bis)
      if (bis < von) {
        return 'Enddatum liegt vor Startdatum.'
      }
      const today = new Date()
      today.setHours(0, 0, 0, 0)
      if (bis >= today) {
        return 'Enddatum muss vor heute liegen — der laufende Tag ist Snapshot-instabil.'
      }
      const tage = Math.round((bis.getTime() - von.getTime()) / 86_400_000) + 1
      if (tage > REAGGREGATE_RANGE_MAX_DAYS) {
        return `Maximal ${REAGGREGATE_RANGE_MAX_DAYS} Tage pro Lauf (du hast ${tage} gewählt). In mehreren Schüben ausführen.`
      }
      if (!params.range_confirmed) {
        return 'Bitte die Bestätigung anhaken — Datenverlust-Hinweise wurden zur Kenntnis genommen.'
      }
    }
    return null
  }

  const handleCreatePlan = async () => {
    const validationError = validateParams()
    if (validationError) {
      setError(validationError)
      return
    }
    setError(null)
    setExecuteResult(null)
    setPlanLoading(true)
    try {
      const req: RepairOperationRequest = {
        anlage_id: anlageId,
        operation: selectedOp,
        params: buildOperationParams(),
      }
      const res = await repairApi.plan(req)
      setPlan(res.plan)
      // Verlauf hat den neuen Pending-Plan jetzt drin
      reloadHistory()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Plan erstellen fehlgeschlagen')
    } finally {
      setPlanLoading(false)
    }
  }

  const handleExecute = async () => {
    if (!plan) return
    setError(null)
    setExecuteRunning(true)
    setShowCancelHint(false)

    const ctrl = new AbortController()
    executeAbortRef.current = ctrl

    cancelTimerRef.current = window.setTimeout(() => {
      setShowCancelHint(true)
    }, 30_000) as unknown as number

    try {
      const result = await repairApi.execute(plan.plan_id, ctrl.signal)
      setExecuteResult(result)
      // Optimistic: Plan ist jetzt verbraucht → Frontend in Auswahl-Zustand
      setPlan(null)
      reloadHistory()
    } catch (e) {
      if (ctrl.signal.aborted) {
        setError('Ausführung abgebrochen — der Server kann den Lauf trotzdem zu Ende geführt haben.')
      } else {
        setError(e instanceof Error ? e.message : 'Ausführung fehlgeschlagen')
      }
    } finally {
      setExecuteRunning(false)
      setShowCancelHint(false)
      if (cancelTimerRef.current !== null) {
        clearTimeout(cancelTimerRef.current)
        cancelTimerRef.current = null
      }
      executeAbortRef.current = null
    }
  }

  const handleCancel = async () => {
    executeAbortRef.current?.abort()
  }

  const handleDiscardPlan = async () => {
    if (!plan) return
    try {
      await repairApi.discard(plan.plan_id)
    } catch (e) {
      console.warn('Plan discard fehlgeschlagen', e)
    }
    setPlan(null)
    setError(null)
    reloadHistory()
  }

  const opMeta = OPERATION_META.find((o) => o.type === selectedOp)

  return (
    <Card>
      <div className="p-6">
        <div className="flex items-center gap-3 mb-1">
          <Wrench className="h-6 w-6 text-primary-500" />
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
            Reparatur-Werkbank
          </h2>
        </div>
        <p className="text-sm text-gray-600 dark:text-gray-400 mb-5">
          Reparatur-Operationen mit Vorschau und Verlauf.
          {anlagenname ? ` Anlage: ${anlagenname}.` : ''}
        </p>

        {/* Operation-Auswahl */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              Operation
            </label>
            <Select
              value={selectedOp}
              onChange={(e) => handleOpChange(e.target.value as RepairOperationType)}
              disabled={planLoading || executeRunning}
              options={WORKBENCH_OPERATIONS.map((o) => ({ value: o.type, label: o.label }))}
            />
            {opMeta && (
              <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                {opMeta.description}
              </p>
            )}
          </div>

          {/* Operation-spezifische Parameter */}
          <OperationParamsEditor
            operation={selectedOp}
            params={params}
            setParams={setParams}
            disabled={planLoading || executeRunning}
          />
        </div>

        {/* Plan erstellen */}
        {!plan && !executeResult && (
          <div className="flex justify-end">
            <Button onClick={handleCreatePlan} disabled={planLoading}>
              {planLoading ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <Activity className="h-4 w-4 mr-2" />}
              Plan erstellen
            </Button>
          </div>
        )}

        {error && (
          <div className="mt-4">
            <Alert type="error">{error}</Alert>
          </div>
        )}

        {/* Plan-Vorschau */}
        {plan && (
          <PlanPreviewBlock
            plan={plan}
            executeRunning={executeRunning}
            showCancelHint={showCancelHint}
            onExecute={handleExecute}
            onCancel={handleCancel}
            onDiscard={handleDiscardPlan}
          />
        )}

        {/* Execute-Ergebnis */}
        {executeResult && (
          <div className="mt-4">
            <Alert type="success">{summarizeResult(executeResult)}</Alert>
          </div>
        )}

        {/* Verlauf */}
        <div className="mt-6 border-t border-gray-200 dark:border-gray-700 pt-4">
          <button
            type="button"
            className="flex items-center gap-2 text-sm font-medium text-gray-700 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white"
            onClick={() => setHistoryOpen((v) => !v)}
          >
            {historyOpen ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
            <History className="h-4 w-4" />
            Verlauf der letzten {history.length} Reparaturen
          </button>
          {historyOpen && (
            <div className="mt-3">
              {historyLoading ? (
                <div className="text-sm text-gray-500"><Loader2 className="inline h-4 w-4 mr-1 animate-spin" /> wird geladen …</div>
              ) : history.length === 0 ? (
                <div className="text-sm text-gray-500 dark:text-gray-400 italic">
                  Noch kein Verlauf — neue Pläne erscheinen hier (max. 20 Einträge, 1h Cache).
                </div>
              ) : (
                <HistoryList views={history} />
              )}
            </div>
          )}
        </div>
      </div>
    </Card>
  )
}


// ── Operation-spezifische Parameter ─────────────────────────────────────────


interface ParamsEditorProps {
  operation: RepairOperationType
  params: OperationParamsState
  setParams: React.Dispatch<React.SetStateAction<OperationParamsState>>
  disabled: boolean
}

function OperationParamsEditor({ operation, params, setParams, disabled }: ParamsEditorProps) {
  if (operation === 'reaggregate_day') {
    return (
      <div>
        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
          Tag
        </label>
        <input
          type="date"
          aria-label="Tag, der neu aggregiert werden soll"
          value={params.datum}
          onChange={(e) => setParams((p) => ({ ...p, datum: e.target.value }))}
          disabled={disabled}
          className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white text-sm"
        />
        <label className="mt-2 inline-flex items-center gap-2 text-sm text-gray-600 dark:text-gray-400">
          <input
            type="checkbox"
            checked={params.mit_resnap}
            onChange={(e) => setParams((p) => ({ ...p, mit_resnap: e.target.checked }))}
            disabled={disabled}
          />
          Snapshots vorher aus HA-Statistics frisch ziehen (Default an)
        </label>
      </div>
    )
  }
  if (operation === 'reaggregate_range') {
    return (
      <div>
        <div className="grid grid-cols-2 gap-2">
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              Von
            </label>
            <input
              type="date"
              aria-label="Mehrere-Tage-Reaggregate Startdatum"
              value={params.von}
              onChange={(e) => setParams((p) => ({ ...p, von: e.target.value }))}
              disabled={disabled}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white text-sm"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              Bis
            </label>
            <input
              type="date"
              aria-label="Mehrere-Tage-Reaggregate Enddatum"
              value={params.bis}
              onChange={(e) => setParams((p) => ({ ...p, bis: e.target.value }))}
              disabled={disabled}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white text-sm"
            />
          </div>
        </div>
        <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
          Max. {REAGGREGATE_RANGE_MAX_DAYS} Tage pro Lauf. Enddatum muss vor heute liegen.
        </p>

        <label className="mt-3 inline-flex items-center gap-2 text-sm text-gray-600 dark:text-gray-400">
          <input
            type="checkbox"
            checked={params.mit_resnap}
            onChange={(e) => setParams((p) => ({ ...p, mit_resnap: e.target.checked }))}
            disabled={disabled}
          />
          Snapshots pro Tag aus HA-Statistics frisch ziehen (Default an)
        </label>

        <div className="mt-3 p-3 border border-amber-300 dark:border-amber-700 rounded-lg bg-amber-50 dark:bg-amber-900/20">
          <label className="inline-flex items-start gap-2 text-sm text-amber-900 dark:text-amber-200 cursor-pointer">
            <input
              type="checkbox"
              checked={params.range_confirmed}
              onChange={(e) => setParams((p) => ({ ...p, range_confirmed: e.target.checked }))}
              disabled={disabled}
              className="mt-0.5"
            />
            <span>
              <strong>Bestätigung:</strong> Per-Feld-Provenance älterer Verfahrensläufe wird überschrieben.
              MQTT-Only-Daten und Strompreis-Sensor-Werte ohne HA-LTS-Pendant gehen verloren, falls vorhanden.
              Prognosen + Korrekturprofil-Daten bleiben erhalten.
              Reparatur erfolgt <strong>ohne Support-Anspruch</strong> auf Rekonstruktion überschriebener Felder.
            </span>
          </label>
        </div>
      </div>
    )
  }
  if (operation === 'vollbackfill') {
    return (
      <div className="grid grid-cols-2 gap-2">
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            Von (optional)
          </label>
          <input
            type="date"
            aria-label="Vollbackfill-Startdatum"
            value={params.von}
            onChange={(e) => setParams((p) => ({ ...p, von: e.target.value }))}
            disabled={disabled}
            className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white text-sm"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            Bis (optional)
          </label>
          <input
            type="date"
            aria-label="Vollbackfill-Enddatum"
            value={params.bis}
            onChange={(e) => setParams((p) => ({ ...p, bis: e.target.value }))}
            disabled={disabled}
            className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white text-sm"
          />
        </div>
      </div>
    )
  }
  if (operation === 'kraftstoffpreis_backfill') {
    return (
      <div>
        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
          Bereich
        </label>
        <Select
          value={params.scope}
          onChange={(e) => setParams((p) => ({ ...p, scope: e.target.value as OperationParamsState['scope'] }))}
          disabled={disabled}
          options={[
            { value: 'beides', label: 'Tages- und Monatsdaten' },
            { value: 'tages', label: 'Nur Tagesdaten' },
            { value: 'monats', label: 'Nur Monatsdaten' },
          ]}
        />
      </div>
    )
  }
  if (operation === 'reset_cloud_import') {
    return (
      <div>
        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
          Provider-Filter (optional, kommagetrennt)
        </label>
        <input
          type="text"
          placeholder="z. B. solaredge,fronius_solarweb (leer = alle)"
          value={params.providers}
          onChange={(e) => setParams((p) => ({ ...p, providers: e.target.value }))}
          disabled={disabled}
          className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white text-sm"
        />
        <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
          Setzt alle von dem/den Provider(n) geschriebenen Felder auf Default zurück.
        </p>
      </div>
    )
  }
  return null
}


// ── Plan-Vorschau-Block ─────────────────────────────────────────────────────


interface PlanPreviewProps {
  plan: RepairPlan
  executeRunning: boolean
  showCancelHint: boolean
  onExecute: () => void
  onCancel: () => void
  onDiscard: () => void
}

function PlanPreviewBlock({
  plan, executeRunning, showCancelHint, onExecute, onCancel, onDiscard,
}: PlanPreviewProps) {
  const totalDiff = plan.diff_total_count
  const truncated = totalDiff > plan.diff_preview.length

  return (
    <div className="mt-4 border border-amber-200 dark:border-amber-800 rounded-lg p-4 bg-amber-50/40 dark:bg-amber-900/10">
      <div className="flex items-center gap-2 mb-3">
        <FileWarning className="h-5 w-5 text-amber-600 dark:text-amber-400" />
        <h3 className="font-medium text-gray-900 dark:text-white">Plan-Vorschau</h3>
        <span className="text-xs text-gray-500 dark:text-gray-400 ml-auto inline-flex items-center gap-1">
          <Clock className="h-3 w-3" /> Plan gültig bis {formatTime(plan.expires_at)}
        </span>
      </div>

      {/* Geschätzte Änderungen */}
      <div className="mb-3 flex flex-wrap gap-2">
        {Object.entries(plan.estimated_changes).map(([k, v]) => (
          <span key={k} className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 text-xs text-gray-700 dark:text-gray-300">
            <strong>{v}</strong> {k}
          </span>
        ))}
      </div>

      {/* Warnungen */}
      {plan.warnings.length > 0 && (
        <ul className="mb-3 space-y-1">
          {plan.warnings.map((w, i) => (
            <li key={i} className="flex items-start gap-2 text-sm text-amber-800 dark:text-amber-300">
              <AlertTriangle className="h-4 w-4 flex-shrink-0 mt-0.5" />
              <span>{w}</span>
            </li>
          ))}
        </ul>
      )}

      {/* Diff-Tabelle */}
      {plan.diff_preview.length > 0 && (
        <DiffPreviewTable diffs={plan.diff_preview} truncated={truncated} totalCount={totalDiff} />
      )}

      {/* Aktionen */}
      <div className="mt-4 flex flex-wrap items-center gap-2">
        <Button onClick={onExecute} disabled={executeRunning}>
          {executeRunning ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <Play className="h-4 w-4 mr-2" />}
          {totalDiff > 0
            ? `Diese ${totalDiff} ${totalDiff === 1 ? 'Änderung' : 'Änderungen'} anwenden`
            : 'Operation ausführen'}
        </Button>
        <button
          type="button"
          onClick={onDiscard}
          disabled={executeRunning}
          className="px-3 py-2 text-sm text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white disabled:opacity-50"
        >
          Plan verwerfen
        </button>
        {executeRunning && showCancelHint && (
          <button
            type="button"
            onClick={onCancel}
            className="ml-auto px-3 py-2 text-sm text-amber-700 dark:text-amber-300 border border-amber-300 dark:border-amber-700 rounded-lg hover:bg-amber-100 dark:hover:bg-amber-900/30"
          >
            Abbrechen
          </button>
        )}
      </div>
    </div>
  )
}


// ── Diff-Tabelle ────────────────────────────────────────────────────────────


function DiffPreviewTable({ diffs, truncated, totalCount }: {
  diffs: FieldDiff[]; truncated: boolean; totalCount: number
}) {
  // Gruppieren nach table für bessere Lesbarkeit
  const byTable = new Map<string, FieldDiff[]>()
  for (const d of diffs) {
    const arr = byTable.get(d.table)
    if (arr) arr.push(d)
    else byTable.set(d.table, [d])
  }

  return (
    <div className="border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden bg-white dark:bg-gray-900">
      <div className="max-h-96 overflow-y-auto overscroll-contain">
        <table className="w-full text-sm">
          <thead className="sticky top-0 z-10 bg-gray-50 dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700">
            <tr>
              <th className="text-left px-3 py-2 font-medium text-gray-700 dark:text-gray-300">Tabelle / Feld</th>
              <th className="text-left px-3 py-2 font-medium text-gray-700 dark:text-gray-300">PK</th>
              <th className="text-right px-3 py-2 font-medium text-gray-700 dark:text-gray-300">vorher</th>
              <th className="text-right px-3 py-2 font-medium text-gray-700 dark:text-gray-300">nachher</th>
              <th className="text-left px-3 py-2 font-medium text-gray-700 dark:text-gray-300">Quelle</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
            {[...byTable.entries()].map(([table, items]) => (
              <>
                <tr key={`grp-${table}`} className="bg-gray-50/60 dark:bg-gray-800/40">
                  <td colSpan={5} className="px-3 py-1 text-xs font-semibold text-gray-600 dark:text-gray-400 uppercase tracking-wide">
                    {table} ({items.length})
                  </td>
                </tr>
                {items.map((d, i) => (
                  <tr key={`${table}-${i}`} className={decisionRowClass(d.decision)}>
                    <td className="px-3 py-1.5 text-gray-900 dark:text-gray-100 font-mono text-xs">
                      {d.field}
                    </td>
                    <td className="px-3 py-1.5 text-gray-500 dark:text-gray-400 font-mono text-xs">
                      {formatPk(d.row_pk)}
                    </td>
                    <td className="px-3 py-1.5 text-right text-gray-700 dark:text-gray-300">
                      {formatVal(d.old_value)}
                    </td>
                    <td className="px-3 py-1.5 text-right text-gray-700 dark:text-gray-300">
                      {formatVal(d.new_value)}
                    </td>
                    <td className="px-3 py-1.5 text-xs text-gray-500 dark:text-gray-400">
                      <span title={`${d.source_before ?? '∅'} → ${d.source_after}`}>
                        {d.source_before ?? '∅'}<br />→ {d.source_after}
                      </span>
                    </td>
                  </tr>
                ))}
              </>
            ))}
          </tbody>
        </table>
      </div>
      {truncated && (
        <div className="px-3 py-2 bg-gray-50 dark:bg-gray-800 text-xs text-gray-600 dark:text-gray-400 border-t border-gray-200 dark:border-gray-700">
          … und {totalCount - diffs.length} weitere Felder werden ebenfalls geändert
          (Vorschau ist auf {diffs.length} Einträge gekappt).
        </div>
      )}
    </div>
  )
}


// ── Verlauf ─────────────────────────────────────────────────────────────────


function HistoryList({ views }: { views: RepairPlanView[] }) {
  return (
    <ul className="space-y-2">
      {views.map((v) => {
        const meta = OPERATION_META.find((o) => o.type === v.plan.operation)
        const opLabel = meta?.label ?? v.plan.operation
        const status = v.result ? 'ausgeführt' : 'offen'
        return (
          <li
            key={v.plan.plan_id}
            className="border border-gray-200 dark:border-gray-700 rounded-lg p-3 bg-white dark:bg-gray-900"
          >
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <span className="font-medium text-gray-900 dark:text-white">{opLabel}</span>
              <span className={`text-xs px-2 py-0.5 rounded ${
                v.result
                  ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-300'
                  : 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300'
              }`}>
                {status}
              </span>
              <span className="text-xs text-gray-500 dark:text-gray-400 ml-auto">
                {v.result ? formatTime(v.result.executed_at) : formatTime(v.plan.created_at)}
              </span>
            </div>
            <div className="mt-1 text-xs text-gray-600 dark:text-gray-400 flex flex-wrap gap-2">
              {v.result
                ? Object.entries(v.result.actual_changes).map(([k, val]) => (
                    <span key={k}><strong>{val}</strong> {k}</span>
                  ))
                : Object.entries(v.plan.estimated_changes).map(([k, val]) => (
                    <span key={k}>geschätzt <strong>{val}</strong> {k}</span>
                  ))
              }
              {v.result && v.result.audit_log_ids.length > 0 && (
                <span className="ml-auto" title={v.result.audit_log_ids.join(', ')}>
                  Audit-Log: {v.result.audit_log_ids.length} Einträge
                </span>
              )}
            </div>
          </li>
        )
      })}
    </ul>
  )
}


// ── Helpers ─────────────────────────────────────────────────────────────────


function decisionRowClass(decision: FieldDiff['decision']): string {
  if (decision === 'applied') return 'bg-emerald-50/40 dark:bg-emerald-900/10'
  if (decision === 'rejected_lower_priority') return 'bg-yellow-50/40 dark:bg-yellow-900/10'
  return ''
}


function formatVal(v: unknown): string {
  if (v === null || v === undefined) return '∅'
  if (typeof v === 'number') return v.toLocaleString('de-DE', { maximumFractionDigits: 3 })
  if (typeof v === 'string') return v
  if (typeof v === 'object') return JSON.stringify(v)
  return String(v)
}


function formatPk(pk: Record<string, unknown>): string {
  return Object.entries(pk)
    .map(([k, v]) => `${k}=${v}`)
    .join(', ')
}


function formatTime(iso: string): string {
  try {
    return new Date(iso).toLocaleString('de-DE', {
      year: 'numeric', month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit',
    })
  } catch {
    return iso
  }
}


function summarizeResult(result: RepairResult): string {
  const parts: string[] = []
  for (const [k, v] of Object.entries(result.actual_changes)) {
    parts.push(`${v} ${k}`)
  }
  const audit = result.audit_log_ids.length
  parts.push(`${audit} Audit-Log-Eintrag${audit === 1 ? '' : 'e'}`)
  const meta = OPERATION_META.find((o) => o.type === result.operation)
  const opLabel = meta?.label ?? result.operation
  return `${opLabel} ausgeführt: ${parts.join(' · ')}.`
}


