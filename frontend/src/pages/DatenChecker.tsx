/**
 * Daten-Checker – Datenqualitäts-Prüfung
 *
 * Prüft alle Anlage-Daten auf Vollständigkeit und Plausibilität.
 * 5 Kategorien: Stammdaten, Strompreise, Investitionen,
 * Monatsdaten-Vollständigkeit, Monatsdaten-Plausibilität.
 */

import { useState, useEffect, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  ClipboardCheck, RefreshCw, XCircle, AlertTriangle, Info,
  CheckCircle, ChevronRight, ChevronDown,
} from 'lucide-react'
import { LoadingSpinner } from '../components/ui'
import { KPICard } from '../components/ui'
import { useAnlagen } from '../hooks'
import { datenCheckerApi, type DatenCheckResponse, type CheckErgebnis } from '../api/datenChecker'

// ─── Konstanten ─────────────────────────────────────────────────────────────

const kategorieLabels: Record<string, string> = {
  stammdaten: 'Stammdaten',
  strompreise: 'Strompreise',
  investitionen: 'Investitionen',
  monatsdaten_vollstaendigkeit: 'Monatsdaten – Vollständigkeit',
  monatsdaten_plausibilitaet: 'Monatsdaten – Plausibilität',
}

const kategorieReihenfolge = [
  'stammdaten',
  'strompreise',
  'investitionen',
  'monatsdaten_vollstaendigkeit',
  'monatsdaten_plausibilitaet',
]

function severityIcon(schwere: string) {
  switch (schwere) {
    case 'error': return <XCircle className="h-4 w-4 text-red-500 flex-shrink-0" />
    case 'warning': return <AlertTriangle className="h-4 w-4 text-amber-500 flex-shrink-0" />
    case 'info': return <Info className="h-4 w-4 text-blue-500 flex-shrink-0" />
    case 'ok': return <CheckCircle className="h-4 w-4 text-green-500 flex-shrink-0" />
    default: return null
  }
}

function severityBadge(counts: Record<string, number>) {
  const parts: string[] = []
  if (counts.error > 0) parts.push(`${counts.error} Fehler`)
  if (counts.warning > 0) parts.push(`${counts.warning} Warnungen`)
  if (counts.info > 0) parts.push(`${counts.info} Hinweise`)
  if (parts.length === 0) return 'OK'
  return parts.join(', ')
}

// ─── Kategorie-Sektion ─────────────────────────────────────────────────────

function KategorieSektion({
  kategorie,
  ergebnisse,
  defaultOpen,
}: {
  kategorie: string
  ergebnisse: CheckErgebnis[]
  defaultOpen: boolean
}) {
  const [open, setOpen] = useState(defaultOpen)
  const navigate = useNavigate()

  const counts = useMemo(() => {
    const c = { error: 0, warning: 0, info: 0, ok: 0 }
    ergebnisse.forEach((e) => { c[e.schwere] = (c[e.schwere] || 0) + 1 })
    return c
  }, [ergebnisse])

  const hasIssues = counts.error > 0 || counts.warning > 0

  return (
    <div className="border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between px-4 py-3 bg-gray-50 dark:bg-gray-800 hover:bg-gray-100 dark:hover:bg-gray-750 transition-colors text-left"
      >
        <div className="flex items-center gap-2">
          {open ? (
            <ChevronDown className="h-4 w-4 text-gray-400" />
          ) : (
            <ChevronRight className="h-4 w-4 text-gray-400" />
          )}
          <span className="font-medium text-sm text-gray-900 dark:text-white">
            {kategorieLabels[kategorie] || kategorie}
          </span>
        </div>
        <span className={`text-xs px-2 py-0.5 rounded-full ${
          hasIssues
            ? 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400'
            : 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
        }`}>
          {severityBadge(counts)}
        </span>
      </button>

      {open && (
        <div className="divide-y divide-gray-100 dark:divide-gray-800">
          {ergebnisse.map((e, i) => (
            <div
              key={i}
              className="flex items-start gap-3 px-4 py-2.5"
            >
              <div className="mt-0.5">{severityIcon(e.schwere)}</div>
              <div className="flex-1 min-w-0">
                <p className="text-sm text-gray-800 dark:text-gray-200">{e.meldung}</p>
                {e.details && (
                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">{e.details}</p>
                )}
              </div>
              {e.link && (
                <button
                  onClick={() => navigate(e.link!)}
                  className="flex-shrink-0 text-xs text-blue-600 dark:text-blue-400 hover:underline flex items-center gap-0.5"
                >
                  Beheben
                  <ChevronRight className="h-3 w-3" />
                </button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ─── Hauptkomponente ────────────────────────────────────────────────────────

export default function DatenChecker() {
  const { anlagen, loading: anlagenLoading } = useAnlagen()
  const [selectedAnlageId, setSelectedAnlageId] = useState<number | undefined>()
  const [result, setResult] = useState<DatenCheckResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Erste Anlage auto-selektieren
  useEffect(() => {
    if (anlagen.length > 0 && !selectedAnlageId) {
      setSelectedAnlageId(anlagen[0].id)
    }
  }, [anlagen, selectedAnlageId])

  // Check laden wenn Anlage ausgewählt
  useEffect(() => {
    if (!selectedAnlageId) return

    const load = async () => {
      try {
        setLoading(true)
        setError(null)
        const data = await datenCheckerApi.check(selectedAnlageId)
        setResult(data)
      } catch {
        setError('Fehler beim Laden der Prüfergebnisse')
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [selectedAnlageId])

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

  if (anlagenLoading) {
    return (
      <div className="flex justify-center py-12">
        <LoadingSpinner />
      </div>
    )
  }

  if (anlagen.length === 0) {
    return (
      <div className="space-y-6">
        <div className="flex items-center gap-3">
          <ClipboardCheck className="w-6 h-6 text-gray-500" />
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Daten-Checker</h1>
        </div>
        <div className="text-center py-12 text-gray-500">
          Keine Anlagen vorhanden. Bitte zuerst eine Anlage anlegen.
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-3">
          <ClipboardCheck className="w-6 h-6 text-gray-500" />
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Daten-Checker</h1>
        </div>
        <div className="flex items-center gap-3">
          {anlagen.length > 1 && (
            <select
              value={selectedAnlageId || ''}
              onChange={(e) => setSelectedAnlageId(Number(e.target.value))}
              aria-label="Anlage auswählen"
              className="rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-3 py-2 text-sm"
            >
              {anlagen.map((a) => (
                <option key={a.id} value={a.id}>{a.anlagenname}</option>
              ))}
            </select>
          )}
          <button
            onClick={() => selectedAnlageId && setSelectedAnlageId((prev) => { setResult(null); return prev })}
            disabled={loading}
            className="p-2 rounded-lg text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-700"
            aria-label="Aktualisieren"
          >
            <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

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
                  {result.monatsdaten_abdeckung.vorhanden} von {result.monatsdaten_abdeckung.erwartet} Monate ({result.monatsdaten_abdeckung.prozent}%)
                </span>
              </div>
              <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2.5">
                <div
                  className={`h-2.5 rounded-full transition-all ${
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

          {/* Kategorien */}
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
                />
              )
            })}
          </div>
        </>
      )}
    </div>
  )
}
