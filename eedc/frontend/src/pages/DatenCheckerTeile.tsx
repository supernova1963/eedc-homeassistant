/**
 * Daten-Checker — geteilte Teile (Prüf-Lauf + Kategorie-Sektionen + Reparatur-
 * Werkbank).
 *
 * EINE Code-Wahrheit für IST (`pages/DatenChecker.tsx`, dünner Komposer) und
 * IA-V4 (Einstellungen-Katalog-Block „Daten-Checker", inline wie Strompreise/
 * Monatsdaten — Gernot 2026-07-01). Der Aufrufer reicht die bereits aufgelöste
 * `anlageId` und – im Mehr-Anlagen-Fall – einen `kopfZusatz` (Anlage-Auswahl).
 * Zahlen de-DE über `fmtZahl`.
 */
import { useState, useEffect, useMemo, type ReactNode } from 'react'
import {
  RefreshCw, XCircle, AlertTriangle, Info,
  CheckCircle, ChevronRight, ChevronDown, FileText,
} from 'lucide-react'
import { LoadingSpinner, Button } from '../components/ui'
import { KPICard } from '../components/ui'
import { datenCheckerApi, type DatenCheckResponse, type CheckErgebnis } from '../api/datenChecker'
import DiagnosePaketDialog from '../components/datenchecker/DiagnosePaketDialog'
import BefundHandgriff from '../components/datenchecker/BefundHandgriff'
import LoesungswegPanel from '../components/datenchecker/LoesungswegPanel'
import type { ReparaturMeldung } from './datenCheckerMeldungen'
import { useSchmaleAchse } from '../hooks/useSchmaleAchse'
import { fmtZahl } from '../lib'
import {
  KATEGORIE_LABELS as kategorieLabels,
  KATEGORIE_REIHENFOLGE as kategorieReihenfolge,
} from '../config/datenCheckerKategorien'

// ─── Severity-Helfer ──────────────────────────────────────────────────────────
// Kategorie-Labels/-Reihenfolge + Severity-Config sind SoT in
// config/datenCheckerKategorien.ts (geteilt mit dem IA-V4-Komponenten-Hub).

function severityBadge(counts: Record<string, number>) {
  const parts: string[] = []
  if (counts.error > 0) parts.push(`${counts.error} Fehler`)  // Singular = Plural
  if (counts.warning > 0) {
    parts.push(`${counts.warning} ${counts.warning === 1 ? 'Warnung' : 'Warnungen'}`)
  }
  if (counts.info > 0) {
    parts.push(`${counts.info} ${counts.info === 1 ? 'Hinweis' : 'Hinweise'}`)
  }
  if (parts.length === 0) return 'OK'
  return parts.join(', ')
}

// ─── Kategorie-Sektion ─────────────────────────────────────────────────────────

function KategorieSektion({
  kategorie,
  ergebnisse,
  defaultOpen,
  anlageId,
  vorgangAktiv,
  onVorgang,
  onErgebnis,
  onLoesungsweg,
}: {
  kategorie: string
  ergebnisse: CheckErgebnis[]
  defaultOpen: boolean
  anlageId: number
  /** E3: ein Vorgang zur Zeit (Vorschau offen oder Lauf) — die übrigen Knöpfe sind gesperrt. */
  vorgangAktiv: boolean
  onVorgang: (aktiv: boolean) => void
  onErgebnis: (m: ReparaturMeldung) => void
  onLoesungsweg: (befund: CheckErgebnis) => void
}) {
  const [open, setOpen] = useState(defaultOpen)
  // E3 (Konzept §5): jede Zeile rendert `BefundHandgriff` — ein Knopf je Befund (Aktion mit Vorschau · Sprung ·
  // Auskunft) und der Text-Link «Lösungsweg». Keine eigenen Handler (Wächter W-10, `npm run check:eine-mechanik`).

  const counts = useMemo(() => {
    const c = { error: 0, warning: 0, info: 0, ok: 0 }
    ergebnisse.forEach((e) => { c[e.schwere] = (c[e.schwere] || 0) + 1 })
    return c
  }, [ergebnisse])

  const hasIssues = counts.error > 0 || counts.warning > 0

  return (
    <div className="border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden">
      <div className="bg-gray-50 dark:bg-gray-800">
        <Button
          type="button"
          variant="ghost"
          onClick={() => setOpen(!open)}
          aria-expanded={open}
          className="w-full justify-between text-left"
        >
          <span className="flex items-center gap-2">
            {open ? (
              <ChevronDown className="h-4 w-4 text-gray-400 dark:text-gray-500" />
            ) : (
              <ChevronRight className="h-4 w-4 text-gray-400 dark:text-gray-500" />
            )}
            <span className="font-medium text-sm text-gray-900 dark:text-white">
              {kategorieLabels[kategorie] || kategorie}
            </span>
          </span>
          <span className={`text-xs px-2 py-0.5 rounded-full ${
            hasIssues
              ? 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400'
              : 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
          }`}>
            {severityBadge(counts)}
          </span>
        </Button>
      </div>

      {open && (
        <div className="divide-y divide-gray-100 dark:divide-gray-800">
          {ergebnisse.map((e, i) => (
            <BefundHandgriff
              key={i}
              befund={e}
              anlageId={anlageId}
              gesperrt={vorgangAktiv}
              onVorgang={onVorgang}
              onErgebnis={onErgebnis}
              onLoesungsweg={onLoesungsweg}
            />
          ))}
        </div>
      )}
    </div>
  )
}

// ─── Verwaltung (Prüf-Lauf + KPI + Abdeckung + Kategorien + Lösungsweg) ───────

/**
 * Voller Daten-Checker. Genau eine Einbettung: der Katalog-Block `datenchecker`
 * der Kategorie *Daten* (`einstellungenKatalog.tsx`) — die fruehere V3-Seite ist
 * mit dem V4-Flip entfallen. `anlageId` ist bereits aufgelöst; `kopfZusatz`
 * (z. B. Anlage-Auswahl) wandert links in die Kopfleiste.
 */
export function DatenCheckerVerwaltung({ anlageId, kopfZusatz }: { anlageId: number; kopfZusatz?: ReactNode }) {
  const [result, setResult] = useState<DatenCheckResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [refreshKey, setRefreshKey] = useState(0)
  const [diagnoseOffen, setDiagnoseOffen] = useState(false)
  // E3: ein Vorgang zur Zeit (Vorschau offen oder Lauf) und der offene Lösungsweg.
  const [vorgangAktiv, setVorgangAktiv] = useState(false)
  const [loesungsweg, setLoesungsweg] = useState<CheckErgebnis | null>(null)
  // `hinweis` (bernstein) ist der dritte Zustand, den es braucht: der Lauf ist
  // durchgelaufen, hat aber nichts (oder nur teilweise etwas) geschrieben —
  // weder Erfolg noch Fehler.
  const [reparaturMessage, setReparaturMessage] = useState<ReparaturMeldung | null>(null)
  const schmal = useSchmaleAchse()

  // Nach «Anwenden»: der Satz des Laufs, dann prüft der Checker neu (der Befund verschwindet oder ändert sich, W-11).
  const nachDemLauf = (m: ReparaturMeldung) => {
    setReparaturMessage(m)
    setRefreshKey(k => k + 1)
  }

  // Check laden wenn Anlage ausgewählt / neu angefordert
  useEffect(() => {
    const load = async () => {
      try {
        setLoading(true)
        setError(null)
        const data = await datenCheckerApi.check(anlageId)
        setResult(data)
      } catch {
        setError('Fehler beim Laden der Prüfergebnisse')
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [anlageId, refreshKey])

  // Ergebnisse nach Kategorie gruppieren
  const grouped = useMemo(() => {
    if (!result) return {}
    const groups: Record<string, CheckErgebnis[]> = {}
    for (const e of result.ergebnisse) {
      if (!groups[e.kategorie]) groups[e.kategorie] = []
      groups[e.kategorie].push(e)
    }
    return groups
  }, [result])

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-2">{kopfZusatz}</div>
        <div className="flex items-center gap-2">
          {/* E1: Diagnose-Paket zum Kopieren oder Herunterladen (Konzept Daten-Checker §8.3). */}
          <Button variant="secondary" size="sm" onClick={() => setDiagnoseOffen(true)} title="Diagnose-Paket">
            <FileText className="h-4 w-4 mr-2" />
            Diagnose-Paket
          </Button>
          <Button
            variant="secondary"
            size="sm"
            onClick={() => { setResult(null); setRefreshKey(k => k + 1) }}
            disabled={loading}
            title="Aktualisieren"
          >
            <RefreshCw className={`h-4 w-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
            Aktualisieren
          </Button>
        </div>
      </div>
      <DiagnosePaketDialog isOpen={diagnoseOffen} onClose={() => setDiagnoseOffen(false)} anlageId={anlageId} />

      {error && (
        <div className="p-3 rounded-lg bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-300 text-sm">
          {error}
        </div>
      )}

      {loading && (
        <div className="flex justify-center py-8">
          <LoadingSpinner />
        </div>
      )}

      {result && !loading && (
        <>
          {/* KPI-Karten */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <KPICard
              title="Fehler"
              value={result.zusammenfassung.error}
              icon={XCircle}
              color={result.zusammenfassung.error > 0 ? 'red' : 'gray'}
            />
            <KPICard
              title="Warnungen"
              value={result.zusammenfassung.warning}
              icon={AlertTriangle}
              color={result.zusammenfassung.warning > 0 ? 'yellow' : 'gray'}
            />
            <KPICard
              title="Hinweise"
              value={result.zusammenfassung.info}
              icon={Info}
              color={result.zusammenfassung.info > 0 ? 'blue' : 'gray'}
            />
            <KPICard
              title="OK"
              value={result.zusammenfassung.ok}
              icon={CheckCircle}
              color="green"
            />
          </div>

          {/* Monatsdaten-Abdeckung */}
          {result.monatsdaten_abdeckung && result.monatsdaten_abdeckung.erwartet > 0 && (
            <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
                  Monatsdaten-Abdeckung
                </span>
                <span className="text-sm text-gray-500">
                  {result.monatsdaten_abdeckung.vorhanden} von {result.monatsdaten_abdeckung.erwartet} Monate ({fmtZahl(result.monatsdaten_abdeckung.prozent, 0)} %)
                </span>
              </div>
              <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-sm h-2.5">
                <div
                  className={`h-2.5 rounded-sm transition-all ${
                    result.monatsdaten_abdeckung.prozent >= 90
                      ? 'bg-green-500'
                      : result.monatsdaten_abdeckung.prozent >= 70
                        ? 'bg-amber-500'
                        : 'bg-red-500'
                  }`}
                  style={{ width: `${Math.min(100, result.monatsdaten_abdeckung.prozent)}%` }}
                />
              </div>
            </div>
          )}

          {/* Reparatur-Status-Toast */}
          {reparaturMessage && (
            <div className={`px-3 py-2 rounded text-sm ${
              reparaturMessage.art === 'ok'
                ? 'bg-green-50 dark:bg-green-900/20 text-green-700 dark:text-green-300 border border-green-200 dark:border-green-800'
                : reparaturMessage.art === 'hinweis'
                ? 'bg-amber-50 dark:bg-amber-900/20 text-amber-700 dark:text-amber-300 border border-amber-200 dark:border-amber-800'
                : 'bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-300 border border-red-200 dark:border-red-800'
            }`}>
              {reparaturMessage.text}
            </div>
          )}

          {/* Kategorien — E3: mit offenem Lösungsweg zweispaltig (Panel neben der Liste), auf dem Handy als Dialog. */}
          <div className={loesungsweg && !schmal ? 'grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,26rem)] items-start' : ''}>
          <div className="space-y-3">
            {kategorieReihenfolge.map((kat) => {
              const items = grouped[kat]
              if (!items || items.length === 0) return null
              const hasIssues = items.some((e) => e.schwere === 'error' || e.schwere === 'warning')
              return (
                <KategorieSektion
                  key={kat}
                  kategorie={kat}
                  ergebnisse={items}
                  defaultOpen={hasIssues}
                  anlageId={anlageId}
                  vorgangAktiv={vorgangAktiv}
                  onVorgang={setVorgangAktiv}
                  onErgebnis={nachDemLauf}
                  onLoesungsweg={setLoesungsweg}
                />
              )
            })}
          </div>
          {loesungsweg && (
            <LoesungswegPanel befund={loesungsweg} als={schmal ? 'dialog' : 'einschub'} onClose={() => setLoesungsweg(null)} />
          )}
          </div>
        </>
      )}
    </div>
  )
}
