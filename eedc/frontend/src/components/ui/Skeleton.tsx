/**
 * Skeleton — B8-Lade-Bausteine (Style-Guide B8; R3b S15, 2026-07-05).
 *
 * Primitive + die drei Inhaltsformen (Karten-/Chart-/Tabellen-Form) für
 * Sicht- und Block-Erst-Loads: Platzhalter in der Zielform statt nacktem
 * Vollbereichs-Spinner → kein Layout-Sprung beim Nachladen. Der IST-Ladetext
 * („Lade Tageswerte…") wandert als sr-only/aria-label mit (`label`-Prop) —
 * Screenreader-Verhalten bleibt wie beim LoadingSpinner-Vorgänger.
 * LoadingSpinner bleibt für Inline-/Klein-Kontexte legitim (B8-Abgrenzung
 * im Style-Guide); Wächter: check:b8.
 */
import { ReactNode } from 'react'

export function Skeleton({ className = '' }: { className?: string }) {
  return <div className={`animate-pulse rounded bg-gray-200 dark:bg-gray-700 ${className}`} aria-hidden="true" />
}

/** a11y-Hülle: role=status + sr-only-IST-Text, Inhalt selbst ist aria-hidden. */
function MitLabel({ label, children }: { label?: string; children: ReactNode }) {
  if (!label) return <>{children}</>
  return (
    <div role="status" aria-busy="true" aria-label={label}>
      <span className="sr-only">{label}</span>
      {children}
    </div>
  )
}

/** KPI-Kachel-Zeile in KpiStrip-Geometrie (grid auto-fit 248px, gap-3). */
export function KpiStripSkeleton({ kacheln = 4, label }: { kacheln?: number; label?: string }) {
  return (
    <MitLabel label={label}>
      <div className="grid grid-cols-[repeat(auto-fit,minmax(248px,1fr))] gap-3" aria-hidden="true">
        {Array.from({ length: kacheln }, (_, i) => (
          <div key={i} className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-4 space-y-3">
            <Skeleton className="h-3 w-24" />
            <Skeleton className="h-7 w-28" />
          </div>
        ))}
      </div>
    </MitLabel>
  )
}

/** Chart-Fläche in Standard-Chart-Höhe. */
export function ChartSkeleton({ hoehe = 'h-64', label }: { hoehe?: string; label?: string }) {
  return (
    <MitLabel label={label}>
      <Skeleton className={`w-full ${hoehe}`} />
    </MitLabel>
  )
}

/** Tabellen-Form: Kopfzeile + Zeilen-Balken. */
export function TabellenSkeleton({ zeilen = 6, label }: { zeilen?: number; label?: string }) {
  return (
    <MitLabel label={label}>
      <div className="space-y-2" aria-hidden="true">
        <Skeleton className="h-4 w-1/2" />
        {Array.from({ length: zeilen }, (_, i) => (
          <Skeleton key={i} className="h-8 w-full" />
        ))}
      </div>
    </MitLabel>
  )
}
