/**
 * BlockStackSkeleton — B8-Lade-Skeleton in BlockShell-Form (R3b S15, 2026-07-05).
 *
 * Ersetzt die nackten Vollbereichs-Spinner der v4-Sichten beim Erst-Load:
 * 1 offener Block (Inhaltsform kpi/chart/tabelle) + n zugeklappte Block-Köpfe,
 * exakt in den BlockShell-Maßen (rounded-xl-Karte, 44-px-Kopf, space-y-3) —
 * kein Layout-Sprung beim Nachladen. Bewusst generisch 1-offen+n-zu, wo die
 * Ziel-Blockzahl datenabhängig ist (falsche Struktur vortäuschen wäre schlechter
 * als ein neutraler Platzhalter); exakte Blockzahl nur wo deterministisch.
 * Der IST-Ladetext ist ab R18-13 (rapahl #213/#218) auch SICHTBAR: nach ~400 ms
 * Verzögerung eingeblendet (schnelle Loads flackern nicht), Platz von Anfang an
 * reserviert (kein Layout-Sprung). Screenreader bekommen ihn sofort (sr-only).
 */
import { useEffect, useState } from 'react'
import { Skeleton, KpiStripSkeleton, ChartSkeleton, TabellenSkeleton } from '../ui/Skeleton'

// R18-13: Einblende-Verzögerung des sichtbaren Ladetexts — kurz genug, dass er
// bei echtem Warten früh erklärt, lang genug, dass warme Loads (<400 ms) still bleiben.
const LABEL_DELAY_MS = 400

function BlockKarte({ children }: { children?: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 overflow-hidden">
      <div className="flex items-center gap-2 px-3 min-h-[44px]">
        <Skeleton className="h-4 w-4" />
        <Skeleton className="h-3.5 w-28" />
      </div>
      {children && <div className="px-3 pb-3">{children}</div>}
    </div>
  )
}

export function BlockStackSkeleton({ label, offen = 'kpi', zu = 3, pillen = 0 }: {
  /** IST-Ladetext (sr-only + aria-label) — z. B. „Lade Monat…". */
  label: string
  /** Inhaltsform des offenen Blocks; null = nur zugeklappte Köpfe. */
  offen?: 'kpi' | 'chart' | 'tabelle' | null
  /** Anzahl zugeklappter Block-Köpfe. */
  zu?: number
  /** Optionale Pillen-Zeile darüber (Tab-/Selektor-Platzhalter, STEUER_H-Maß). */
  pillen?: number
}) {
  const [labelSichtbar, setLabelSichtbar] = useState(false)
  useEffect(() => {
    const t = setTimeout(() => setLabelSichtbar(true), LABEL_DELAY_MS)
    return () => clearTimeout(t)
  }, [])

  return (
    <div className="space-y-3" role="status" aria-busy="true" aria-label={label}>
      <span className="sr-only">{label}</span>
      {/* R18-13: sichtbarer Ladetext — immer gerendert (Platz reserviert), erst
          nach LABEL_DELAY_MS eingeblendet; aria-hidden (sr-only-Zwilling oben). */}
      <p
        aria-hidden="true"
        className={`text-sm text-center text-gray-500 dark:text-gray-400 transition-opacity duration-300 ${labelSichtbar ? 'opacity-100' : 'opacity-0'}`}
      >
        {label}
      </p>
      {pillen > 0 && (
        <div className="flex items-center gap-2" aria-hidden="true">
          {Array.from({ length: pillen }, (_, i) => (
            <Skeleton key={i} className="h-8 w-24 rounded-lg" />
          ))}
        </div>
      )}
      {offen && (
        <BlockKarte>
          {offen === 'kpi' ? <KpiStripSkeleton /> : offen === 'chart' ? <ChartSkeleton /> : <TabellenSkeleton />}
        </BlockKarte>
      )}
      {Array.from({ length: zu }, (_, i) => (
        <BlockKarte key={i} />
      ))}
    </div>
  )
}
